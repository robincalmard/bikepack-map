"""Minimal ChatGPT MCP connectivity probe for cloud deploy (Render).

One tool, no widgets. The only non-stock piece is answering ChatGPT's
`server/discover` probe (protocol 2026-07-28), which stock mcp 1.x rejects
with HTTP 400 before initialize runs.
"""

from __future__ import annotations

import os
from typing import Any

import mcp.shared.version as mcp_version
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

if "2026-07-28" not in mcp_version.SUPPORTED_PROTOCOL_VERSIONS:
    mcp_version.SUPPORTED_PROTOCOL_VERSIONS = [
        *mcp_version.SUPPORTED_PROTOCOL_VERSIONS,
        "2026-07-28",
    ]

HANDSHAKE_VERSIONS = [
    v for v in mcp_version.SUPPORTED_PROTOCOL_VERSIONS if v != "2026-07-28"
]

mcp = FastMCP(
    name="chatgpt-mcp-hello",
    instructions="Connectivity probe. Call hello with an optional name.",
    host="0.0.0.0",
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


@mcp.tool()
def hello(name: str = "world") -> str:
    """Return a greeting. Use this to verify the ChatGPT MCP connection."""
    return f"Hello, {name}!"


_mcp_app = mcp.streamable_http_app()


async def app(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] == "http":
        path = (scope.get("path") or "").rstrip("/") or "/"
        method = scope.get("method") or ""
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        if (
            method == "POST"
            and path == "/mcp"
            and headers.get("mcp-method") == "server/discover"
        ):
            body = b""
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body += message.get("body", b"")
                if not message.get("more_body"):
                    break

            req_id: Any = "openai-mcp-discover"
            try:
                import json

                payload = json.loads(body.decode("utf-8") or "{}")
                if "id" in payload:
                    req_id = payload["id"]
            except Exception:
                pass

            async def _done_receive() -> dict[str, Any]:
                return {"type": "http.disconnect"}

            response = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "supportedVersions": HANDSHAKE_VERSIONS,
                        "capabilities": {"tools": {"listChanged": False}},
                        "instructions": "Connectivity probe. Call the hello tool.",
                        "resultType": "complete",
                        "cacheScope": "public",
                    },
                }
            )
            await response(scope, _done_receive, send)
            return

    await _mcp_app(scope, receive, send)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
    )
