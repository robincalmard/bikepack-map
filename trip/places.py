"""Multi-stop trip resolve — place names → pin-ready results.

Roles and days pass through. A geocoding error fails the whole list.
Geocoding stays in trip.geocode.
"""

from __future__ import annotations

from typing import Any

from trip.geocode import geocode_places


async def resolve_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve stop names to coordinates, in input order.

    Each item may include name, role, and day. A hit adds lat, lon, and
    display_name and keeps the input name. A miss is found False with no
    coordinates. A geocoding error fails the whole list.
    """
    return await geocode_places(places)
