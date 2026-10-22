"""ChatGPT MCP app: pin a start, or a list of named stops.

Uses MCP Python SDK v2 (protocol 2026-07-28) — same wire as hello_mcp —
so ChatGPT setup/discover succeeds. Geocoding via trip.resolve_start and
trip.resolve_places. Pins only: no route, GPX, or elevation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from trip import resolve_places, resolve_start

INSTRUCTIONS = (
    "Bikepacking map. Call show_trip_map with place names (not coordinates) "
    "to pin a trip. Each stop has a name, an optional role "
    "(start, overnight, finish, waypoint, or another label), and an optional "
    "day. Call show_start_map when only the starting place is known. "
    "Neither tool draws a route, GPX, or elevation. If a tool returns an "
    "error, say geocoding failed — do not invent a map or a cycling track. "
    "If some places are not found, say so from the tool text; do not invent "
    "coordinates for them."
)

WIDGET_URI = "ui://widget/trip-map-v2.html"
MIME_TYPE = "text/html+skybridge"
WIDGET_HTML = (Path(__file__).resolve().parent / "widgets" / "trip-map.html").read_text(
    encoding="utf8"
)


_WIDGET_ORIGINS = [
    "https://unpkg.com",
    "https://tile.openstreetmap.org",
]


def _widget_meta(
    *,
    invoking: str = "Putting the start on a map",
    invoked: str = "Start map ready",
) -> dict[str, Any]:
    return {
        "ui": {
            "resourceUri": WIDGET_URI,
            "csp": {
                "connectDomains": _WIDGET_ORIGINS,
                "resourceDomains": _WIDGET_ORIGINS,
            },
        },
        "openai/outputTemplate": WIDGET_URI,
        "openai/widgetCSP": {
            "connect_domains": _WIDGET_ORIGINS,
            "resource_domains": _WIDGET_ORIGINS,
        },
        "openai/toolInvocation/invoking": invoking,
        "openai/toolInvocation/invoked": invoked,
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


def _trip_summary(places: list[dict[str, Any]]) -> str:
    mapped = [place["name"] for place in places if place.get("found")]
    missing = [place["name"] for place in places if not place.get("found")]
    noun = "place" if len(mapped) == 1 else "places"
    text = f"Mapped {len(mapped)} {noun}"
    if mapped:
        text += ": " + ", ".join(mapped)
    text += "."
    if missing:
        text += " Not found: " + ", ".join(missing) + "."
    return text


class TripStop(BaseModel):
    """One named stop. Coordinates are looked up here; do not send them."""

    name: str = Field(description="Place name to geocode. Not coordinates.")
    role: str | None = Field(
        default=None,
        description="Optional pin role, such as start, overnight, finish, or waypoint.",
    )
    day: int | None = Field(
        default=None,
        description="Optional trip day number for this stop.",
    )


def _stop_dicts(places: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for place in places:
        if isinstance(place, BaseModel):
            normalized.append(place.model_dump())
        else:
            normalized.append(dict(place))
    return normalized


mcp = MCPServer("bikepack-map", instructions=INSTRUCTIONS)


@mcp.resource(
    WIDGET_URI,
    name="Trip map",
    title="Trip map",
    description="Leaflet map for geocoded trip places",
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


_TRIP_META = {
    "invoking": "Putting the trip on a map",
    "invoked": "Trip map ready",
}


@mcp.tool(
    name="show_trip_map",
    title="Show trip map",
    description=(
        "Geocode place names and show one pin per stop, in order. "
        "Each stop is a name plus an optional role and day. "
        "Does not draw a route, GPX, or elevation. Do not pass coordinates."
    ),
    meta=_widget_meta(**_TRIP_META),
    annotations=types.ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=True,
    ),
)
async def show_trip_map(places: list[TripStop]) -> types.CallToolResult:
    """Stops to geocode. Each item is a place name, not coordinates."""
    stops = _stop_dicts(places)
    try:
        resolved = await resolve_places(stops)
    except Exception as exc:
        raise ToolError(
            f"Geocoding failed for the trip ({type(exc).__name__}). Try again in a moment."
        ) from exc
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=_trip_summary(resolved))],
        structuredContent={"places": resolved},
        _meta=_widget_meta(**_TRIP_META),
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
