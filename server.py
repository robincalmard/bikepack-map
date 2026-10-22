"""ChatGPT MCP app (v1): resolve one start place and show a map pin.

Uses MCP Python SDK v2 (protocol 2026-07-28) — same wire as hello_mcp —
so ChatGPT setup/discover succeeds. Geocoding via trip.resolve_start.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from trip import resolve_start

INSTRUCTIONS = (
    "Bikepacking start map (v1). Call show_start_map with one starting place "
    "name (not coordinates). It geocodes that name and shows one pin. "
    "It does not draw a route, GPX, or extra stops. If the tool returns an "
    "error, say geocoding failed — do not invent a map or a cycling track."
)

WIDGET_URI = "ui://widget/trip-map.html"
MIME_TYPE = "text/html+skybridge"
WIDGET_HTML = (Path(__file__).resolve().parent / "widgets" / "trip-map.html").read_text(
    encoding="utf8"
)


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


mcp = MCPServer("bikepack-map", instructions=INSTRUCTIONS)


@mcp.resource(
    WIDGET_URI,
    name="Trip map",
    title="Trip map",
    description="MapLibre widget for a geocoded start place",
    mime_type=MIME_TYPE,
    meta=_widget_meta(),
)
def trip_map_widget() -> str:
    return WIDGET_HTML


@mcp.tool(
    name="show_start_map",
    title="Show start map",
    description=(
        "Geocode one starting place name and show one pin. "
        "Does not draw a route or GPX. Do not pass invented coordinates."
    ),
    meta=_widget_meta(),
    annotations=types.ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=True,
    ),
)
async def show_start_map(name: str) -> types.CallToolResult:
    """Starting place name to geocode (not coordinates)."""
    try:
        place = await resolve_start(name)
    except Exception as exc:
        raise ToolError(
            f"Geocoding failed for {name!r} ({type(exc).__name__}). Try again in a moment."
        ) from exc
    pin = _pin_for_widget(place)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=_summary(place))],
        structuredContent={"places": [pin]},
        _meta=_widget_meta(),
        isError=False,
    )


@mcp.custom_route("/", methods=["GET"])
async def health(_request: Request) -> Response:
    return PlainTextResponse("bikepack-map ok")


# Render start: uvicorn server:app. DNS-rebinding protection would 421
# public hostnames until allowlisted.
app = mcp.streamable_http_app(
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
    )
