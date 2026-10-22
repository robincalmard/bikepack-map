"""ChatGPT MCP app (v1): resolve one start place and show a map pin.

Uses trip.resolve_start for geocoding. Multi-stop / roles come later.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import mcp.shared.version as mcp_version
import mcp.types as types
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from trip import resolve_start

# ChatGPT probes with protocol 2026-07-28 via server/discover. Accept the
# header, then advertise only handshake versions so it falls back to initialize.
if "2026-07-28" not in mcp_version.SUPPORTED_PROTOCOL_VERSIONS:
    mcp_version.SUPPORTED_PROTOCOL_VERSIONS = [
        *mcp_version.SUPPORTED_PROTOCOL_VERSIONS,
        "2026-07-28",
    ]

HANDSHAKE_VERSIONS = [
    v for v in mcp_version.SUPPORTED_PROTOCOL_VERSIONS if v != "2026-07-28"
]
SERVER_INSTRUCTIONS = (
    "Bikepacking start map (v1). Call show_start_map with a single starting "
    "place name (not coordinates). The server geocodes it and shows one pin."
)

WIDGET_URI = "ui://widget/trip-map.html"
MIME_TYPE = "text/html+skybridge"
WIDGET_HTML = (Path(__file__).resolve().parent / "widgets" / "trip-map.html").read_text(
    encoding="utf8"
)


class ShowStartInput(BaseModel):
    name: str = Field(description="Starting place name to geocode, not coordinates.")


START_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Starting place name (do not invent latitude/longitude).",
        }
    },
    "required": ["name"],
    "additionalProperties": False,
}


def _widget_meta() -> dict[str, Any]:
    return {
        "ui": {"resourceUri": WIDGET_URI},
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Putting the start on a map",
        "openai/toolInvocation/invoked": "Start map ready",
        "openai/widgetAccessible": True,
    }


def _pin_for_widget(place: dict[str, Any]) -> dict[str, Any]:
    """Widget expects {places: [...]}; found starts get a green 'start' role."""
    pin = dict(place)
    if pin.get("found"):
        pin.setdefault("role", "start")
    return pin


def _summary(place: dict[str, Any]) -> str:
    if place.get("found"):
        return f"Mapped start: {place['name']}."
    return f"Not found: {place.get('name') or '(empty)'}."


mcp = FastMCP(
    name="bikepack-map",
    instructions=SERVER_INSTRUCTIONS,
    host="0.0.0.0",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


async def _send_json(send: Send, payload: dict[str, Any], status: int = 200) -> None:
    """Send JSON with an explicit Content-Length.

    On Python 3.14 + some ASGI stacks, Starlette Response ends up as
    Transfer-Encoding: chunked without chunk framing, which breaks ChatGPT.
    """
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


@mcp._mcp_server.list_tools()
async def _list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="show_start_map",
            title="Show start map",
            description=(
                "Geocode a single starting place name and show one pin on a map. "
                "Do not pass invented coordinates."
            ),
            inputSchema=dict(START_SCHEMA),
            _meta=_widget_meta(),
            annotations={
                "destructiveHint": False,
                "openWorldHint": True,
                "readOnlyHint": True,
            },
        ),
    ]


@mcp._mcp_server.list_resources()
async def _list_resources() -> list[types.Resource]:
    return [
        types.Resource(
            name="Trip map",
            title="Trip map",
            uri=WIDGET_URI,
            description="MapLibre widget for a geocoded start place",
            mimeType=MIME_TYPE,
            _meta=_widget_meta(),
        )
    ]


@mcp._mcp_server.list_resource_templates()
async def _list_resource_templates() -> list[types.ResourceTemplate]:
    return [
        types.ResourceTemplate(
            name="Trip map",
            title="Trip map",
            uriTemplate=WIDGET_URI,
            description="MapLibre widget for a geocoded start place",
            mimeType=MIME_TYPE,
            _meta=_widget_meta(),
        )
    ]


async def _handle_read_resource(req: types.ReadResourceRequest) -> types.ServerResult:
    if str(req.params.uri) != WIDGET_URI:
        return types.ServerResult(
            types.ReadResourceResult(contents=[], _meta={"error": "Unknown resource"})
        )
    return types.ServerResult(
        types.ReadResourceResult(
            contents=[
                types.TextResourceContents(
                    uri=WIDGET_URI,
                    mimeType=MIME_TYPE,
                    text=WIDGET_HTML,
                    _meta=_widget_meta(),
                )
            ]
        )
    )


async def _call_tool_request(req: types.CallToolRequest) -> types.ServerResult:
    name = req.params.name
    arguments = req.params.arguments or {}

    if name != "show_start_map":
        return types.ServerResult(
            types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Unknown tool: {name}")],
                isError=True,
            )
        )

    try:
        payload = ShowStartInput.model_validate(arguments)
    except Exception as exc:
        return types.ServerResult(
            types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Invalid input: {exc}")],
                isError=True,
            )
        )

    place = await resolve_start(payload.name)
    pin = _pin_for_widget(place)
    structured = {"places": [pin]}
    text = _summary(place)

    return types.ServerResult(
        types.CallToolResult(
            content=[types.TextContent(type="text", text=text)],
            structuredContent=structured,
            _meta=_widget_meta(),
        )
    )


mcp._mcp_server.request_handlers[types.CallToolRequest] = _call_tool_request
mcp._mcp_server.request_handlers[types.ReadResourceRequest] = _handle_read_resource

_starlette_app = mcp.streamable_http_app()


async def _health(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("bikepack-map ok")


_starlette_app.router.routes.insert(0, Route("/", endpoint=_health, methods=["GET"]))


async def app(scope: Scope, receive: Receive, send: Send) -> None:
    """Outer ASGI wrapper.

    Python 3.14 + Starlette on this machine emits Transfer-Encoding: chunked for
    POST responses without chunk framing, which ChatGPT rejects. We answer
    discover ourselves and re-emit other MCP responses with Content-Length.
    """
    if scope["type"] != "http":
        await _starlette_app(scope, receive, send)
        return

    path = scope.get("path") or ""
    method = scope.get("method") or ""
    if method != "POST" or path.rstrip("/") != "/mcp":
        await _starlette_app(scope, receive, send)
        return

    body = b""
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return
        body += message.get("body", b"")
        if not message.get("more_body"):
            break

    headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in scope.get("headers", [])
    }
    method_name = headers.get("mcp-method")
    req_id: Any = "openai-mcp-discover"
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
        method_name = method_name or payload.get("method")
        if "id" in payload:
            req_id = payload["id"]
    except Exception:
        pass

    sent = False

    async def replay_receive() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    if method_name == "server/discover":
        await _send_json(
            send,
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "supportedVersions": HANDSHAKE_VERSIONS,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                    "instructions": SERVER_INSTRUCTIONS,
                    "resultType": "complete",
                    "cacheScope": "public",
                },
            },
        )
        return

    status_code = 200
    response_headers: list[tuple[bytes, bytes]] = []
    chunks: list[bytes] = []

    async def buffer_send(message: dict[str, Any]) -> None:
        nonlocal status_code, response_headers
        if message["type"] == "http.response.start":
            status_code = int(message["status"])
            response_headers = [
                (k, v)
                for k, v in message.get("headers", [])
                if k.lower() not in {b"content-length", b"transfer-encoding"}
            ]
            return
        if message["type"] == "http.response.body":
            chunks.append(message.get("body", b"") or b"")
            if message.get("more_body"):
                return
            raw = b"".join(chunks)
            response_headers.append((b"content-length", str(len(raw)).encode("ascii")))
            await send(
                {
                    "type": "http.response.start",
                    "status": status_code,
                    "headers": response_headers,
                }
            )
            await send({"type": "http.response.body", "body": raw})

    await _starlette_app(scope, replay_receive, buffer_send)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    # uvicorn on Python 3.14/Windows breaks POST body framing; granian works.
    try:
        from granian import Granian
        from granian.constants import Interfaces

        Granian("server:app", address="0.0.0.0", port=port, interface=Interfaces.ASGI).serve()
    except Exception:
        import uvicorn

        uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
