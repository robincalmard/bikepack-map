"""Trip-planning domain logic (no MCP / HTTP).

Test and iterate on this package locally without ChatGPT or tunnels.

Public surface:
  resolve_start(name) → one pin-ready place
  resolve_places(places) → pin-ready stops, in order
"""

from trip.geocode import clear_cache, geocode_name, geocode_places
from trip.places import resolve_places
from trip.start import resolve_start

__all__ = [
    "clear_cache",
    "geocode_name",
    "geocode_places",
    "resolve_places",
    "resolve_start",
]
