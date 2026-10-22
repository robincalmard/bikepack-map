"""Nominatim geocoding with a process-local cache.

Nominatim is free for light personal use. Identify the app in User-Agent
and keep a 1 request/second pace. See https://operations.osmfoundation.org/policies/nominatim/
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "bikepack-map/0.1 (personal bikepacking planner)"
_MIN_INTERVAL_S = 1.0

_cache: dict[str, dict[str, Any] | None] = {}
_lock = asyncio.Lock()
_last_request_at = 0.0


def clear_cache() -> None:
    """Reset the process-local cache (useful in tests)."""
    _cache.clear()


async def geocode_name(name: str) -> dict[str, Any] | None:
    key = name.strip().lower()
    if not key:
        return None
    if key in _cache:
        return _cache[key]

    async with _lock:
        if key in _cache:
            return _cache[key]

        global _last_request_at
        now = time.monotonic()
        wait = _MIN_INTERVAL_S - (now - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)

        rows = None
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    timeout=12.0, headers={"User-Agent": USER_AGENT}
                ) as client:
                    response = await client.get(
                        NOMINATIM_URL,
                        params={"q": name, "format": "json", "limit": 1},
                    )
                    response.raise_for_status()
                    _last_request_at = time.monotonic()
                    rows = response.json()
                    break
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(1.0)
                    continue
                raise last_error

        if not rows:
            _cache[key] = None
            return None

        row = rows[0]
        result = {
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "display_name": row.get("display_name", name),
        }
        _cache[key] = result
        return result


async def geocode_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for place in places:
        name = (place.get("name") or "").strip()
        hit = await geocode_name(name) if name else None
        item = {
            "name": name,
            "role": place.get("role") or "waypoint",
            "day": place.get("day"),
        }
        if hit:
            item.update(hit)
            item["found"] = True
        else:
            item["found"] = False
        resolved.append(item)
    return resolved
