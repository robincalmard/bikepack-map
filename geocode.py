"""Compatibility re-export. Prefer `from trip.geocode import ...`."""

from trip.geocode import clear_cache, geocode_name, geocode_places

__all__ = ["clear_cache", "geocode_name", "geocode_places"]
