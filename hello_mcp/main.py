"""Minimal ChatGPT MCP connectivity probe for cloud deploy (Render).

One tool, no widgets. Non-stock pieces required for ChatGPT:
- Answer `server/discover` (protocol 2026-07-28); stock mcp 1.x returns HTTP 400
- POST /mcp returns JSON (`json_response=True`) so setup is not an SSE event
- GET /mcp stays stock streamable HTTP (SSE). ChatGPT opens that during setup.
  Two workers so a free Render instance can hold SSE and still serve POST.
"""

from __future__ import annotations

import json
import os
from typing import Any

import mcp.shared.version as mcp_version
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import Receive, Scope, Send

if "2026-07-28" not in mcp_version.SUPPORTED_PROTOCOL_VERSIONS:
    mcp_version.SUPPORTED_PROTOCOL_VERSIONS = [
        *mcp_version.SUPPORTED_PROTOCOL_VERSIONS,
        "2026-07-28",
    ]

HANDSHAKE_VERSIONS = [
    v for v in mcp_version.SUPPORTED_PROTOCOL_VERSIONS if v != "2026-07-28"
]
INSTRUCTIONS = "Connectivity probe. Call hello with an optional name."

mcp = FastMCP(
    name="chatgpt-mcp-hello",
    instructions=INSTRUCTIONS,
    host="0.0.0.0",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


@mcp.tool()
def hello(name: str = "world") -> str:
    """Return a greeting. Use this to verify the ChatGPT MCP connection."""
    return f"Hello, {name}!"


_mcp_app = mcp.streamable_http_app()


async def _send_json(send: Send, payload: dict[str, Any], status: int = 200) -> None:
    """Send JSON with an explicit Content-Length."""
    raw = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(raw)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": raw})


async def _read_body(receive: Receive) -> bytes | None:
    body = b""
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return None
        body += message.get("body", b"")
        if not message.get("more_body"):
            return body


async def app(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await _mcp_app(scope, receive, send)
        return

    path = (scope.get("path") or "").rstrip("/") or "/"
    method = scope.get("method") or ""

    if method == "GET" and path == "/":
        await _send_json(send, {"ok": True, "mcp": "/mcp"})
        return

    if method == "POST" and path == "/mcp":
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        if headers.get("mcp-method") == "server/discover":
            body = await _read_body(receive)
            if body is None:
                return
            req_id: Any = "openai-mcp-discover"
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
                if "id" in payload:
                    req_id = payload["id"]
            except Exception:
                pass
            await _send_json(
                send,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "supportedVersions": HANDSHAKE_VERSIONS,
                        "capabilities": {"tools": {"listChanged": False}},
                        "instructions": INSTRUCTIONS,
                        "resultType": "complete",
                        "cacheScope": "public",
                    },
                },
            )
            return

    await _mcp_app(scope, receive, send)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    # uvicorn on Python 3.14/Windows breaks POST body framing; granian works
    # better for local use. Render (Python 3.12) is fine with either.
    try:
        from granian import Granian
        from granian.constants import Interfaces

        Granian(
            "main:app",
            address="0.0.0.0",
            port=port,
            interface=Interfaces.ASGI,
            workers=2,
        ).serve()
    except Exception:
        import uvicorn

        uvicorn.run("main:app", host="0.0.0.0", port=port, workers=2, reload=False)
