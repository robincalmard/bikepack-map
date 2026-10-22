"""Trip-planning domain logic (no MCP / HTTP).

Test and iterate on this package locally without ChatGPT or tunnels.

v1 public surface: resolve_start(name) → one pin-ready place.
"""

from trip.geocode import clear_cache, geocode_name, geocode_places
from trip.start import resolve_start

__all__ = [
    "clear_cache",
    "geocode_name",
    "geocode_places",
    "resolve_start",
]
