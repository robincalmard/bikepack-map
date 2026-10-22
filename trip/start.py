"""v1 start-only trip resolve — one place name → pin-ready result.

No roles, days, or multi-stop itineraries yet. Call this from tests and
later from a single MCP tool / map pin. Geocoding stays in trip.geocode.
"""

from __future__ import annotations

from typing import Any

from trip.geocode import geocode_name


async def resolve_start(name: str) -> dict[str, Any]:
    """Resolve a single starting place name to coordinates.

    Returns:
      found True  → {name, found, lat, lon, display_name}
      found False → {name, found}  (no lat/lon)
    """
    cleaned = (name or "").strip()
    hit = await geocode_name(cleaned) if cleaned else None
    if not hit:
        return {"name": cleaned, "found": False}
    return {
        "name": cleaned,
        "found": True,
        "lat": hit["lat"],
        "lon": hit["lon"],
        "display_name": hit["display_name"],
    }
