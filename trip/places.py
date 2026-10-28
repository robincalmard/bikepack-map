"""Multi-stop trip resolve — place names → pin-ready results.

Roles, days, and an optional confirmed flag pass through. A geocoding
error fails the whole list. After geocoding, a stop that lands off the
chain is marked needs_confirmation and should stay off the map.
Geocoding stays in trip.geocode.
"""

from __future__ import annotations

from typing import Any

from trip.continuity import mark_discontinuities
from trip.geocode import geocode_places


async def resolve_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve stop names to coordinates, in input order.

    Each item may include name, role, day, and confirmed. A hit adds lat,
    lon, and display_name and keeps the input name. A miss is found False
    with no coordinates. A geocoding error fails the whole list. A hit that
    sits off the chain of the other stops is marked needs_confirmation.
    """
    return mark_discontinuities(await geocode_places(places))
