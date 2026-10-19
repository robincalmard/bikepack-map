"""ChatGPT MCP app: geocode trip places and render a map widget."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

import mcp.types as types
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from geocode import geocode_places

WIDGET_URI = "ui://widget/trip-map.html"
MIME_TYPE = "text/html+skybridge"
WIDGET_HTML = (Path(__file__).resolve().parent / "widgets" / "trip-map.html").read_text(
    encoding="utf8"
)

Role = Literal["start", "overnight", "waypoint", "finish", "poi"]


class PlaceIn(BaseModel):
    name: str = Field(description="Place name to geocode, not coordinates.")
    role: Role = Field(
        default="waypoint",
        description="start, overnight, waypoint, finish, or poi.",
    )
    day: int | None = Field(default=None, description="Trip day number, 1-based.")


class GeocodeInput(BaseModel):
    places: list[PlaceIn] = Field(description="Place names to resolve to coordinates.")


class ShowMapInput(BaseModel):
    places: list[PlaceIn] = Field(
        description="Start, overnights, finish, and key waypoints to pin on the map."
    )


PLACE_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Place name to geocode (do not invent latitude/longitude).",
        },
        "role": {
            "type": "string",
            "enum": ["start", "overnight", "waypoint", "finish", "poi"],
            "description": "Why this place is on the trip.",
        },
        "day": {
            "type": "integer",
            "description": "Optional 1-based day of the trip.",
        },
    },
    "required": ["name"],
    "additionalProperties": False,
}

PLACES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "places": {
            "type": "array",
            "minItems": 1,
            "items": PLACE_ITEM_SCHEMA,
        }
    },
    "required": ["places"],
    "additionalProperties": False,
}


def _widget_meta() -> dict[str, Any]:
    return {
        "ui": {"resourceUri": WIDGET_URI},
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Putting the trip on a map",
        "openai/toolInvocation/invoked": "Trip map ready",
        "openai/widgetAccessible": True,
    }


mcp = FastMCP(
    name="bikepack-map",
    instructions=(
        "Bikepacking trip map. After you propose an itinerary, call show_trip_map "
        "with start, overnight stops, finish, and notable waypoints as place names "
        "(not coordinates). Python geocodes the names. Call geocode_places first only "
        "if you need to inspect coordinates before rendering."
    ),
    stateless_http=True,
)


@mcp._mcp_server.list_tools()
async def _list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="geocode_places",
            title="Geocode places",
            description=(
                "Resolve place names to latitude/longitude. Use this when you need "
                "coordinates before mapping. Do not pass invented coordinates."
            ),
            inputSchema=deepcopy(PLACES_SCHEMA),
            annotations={
                "destructiveHint": False,
                "openWorldHint": True,
                "readOnlyHint": True,
            },
        ),
        types.Tool(
            name="show_trip_map",
            title="Show trip map",
            description=(
                "Call after proposing a bikepacking itinerary. Pass start, overnight "
                "stops, finish, and key waypoints as names. Renders an interactive map "
                "in the chat. Do not pass invented coordinates."
            ),
            inputSchema=deepcopy(PLACES_SCHEMA),
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
            description="MapLibre widget for geocoded trip places",
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
            description="MapLibre widget for geocoded trip places",
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


def _summary(resolved: list[dict[str, Any]]) -> str:
    found = [p for p in resolved if p.get("found")]
    missing = [p["name"] for p in resolved if not p.get("found")]
    lines = [f"Mapped {len(found)} of {len(resolved)} places."]
    for place in found:
        day = f" day {place['day']}" if place.get("day") is not None else ""
        lines.append(f"- {place['name']} ({place['role']}{day})")
    if missing:
        lines.append("Not found: " + ", ".join(missing))
    return "\n".join(lines)


async def _call_tool_request(req: types.CallToolRequest) -> types.ServerResult:
    name = req.params.name
    arguments = req.params.arguments or {}

    if name not in {"geocode_places", "show_trip_map"}:
        return types.ServerResult(
            types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Unknown tool: {name}")],
                isError=True,
            )
        )

    try:
        payload = ShowMapInput.model_validate(arguments)
    except Exception as exc:
        return types.ServerResult(
            types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Invalid input: {exc}")],
                isError=True,
            )
        )

    resolved = await geocode_places([p.model_dump() for p in payload.places])
    structured = {"places": resolved}
    text = _summary(resolved)

    if name == "geocode_places":
        return types.ServerResult(
            types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            )
        )

    return types.ServerResult(
        types.CallToolResult(
            content=[types.TextContent(type="text", text=text)],
            structuredContent=structured,
            _meta=_widget_meta(),
        )
    )


mcp._mcp_server.request_handlers[types.CallToolRequest] = _call_tool_request
mcp._mcp_server.request_handlers[types.ReadResourceRequest] = _handle_read_resource

app = mcp.streamable_http_app()

try:
    from starlette.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
except Exception:
    pass


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "").lower() in {"1", "true", "yes"}
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=reload)
