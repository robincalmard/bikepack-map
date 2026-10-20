"""Trip-planning domain logic (no MCP / HTTP).

Test and iterate on this package locally without ChatGPT or tunnels.
"""

from trip.geocode import geocode_name, geocode_places

__all__ = ["geocode_name", "geocode_places"]
