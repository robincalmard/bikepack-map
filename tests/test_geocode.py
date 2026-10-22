"""Lower-level geocode helpers (used by resolve_start and later multi-stop).

Prefer tests/test_resolve_start.py for the v1 product surface.
"""

from __future__ import annotations

import pytest

from trip import geocode


@pytest.mark.asyncio
async def test_geocode_places_maps_a_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    geocode.clear_cache()

    async def fake_name(name: str):
        return {"lat": 45.0, "lon": 6.0, "display_name": f"{name}, Alps"}

    monkeypatch.setattr(geocode, "geocode_name", fake_name)
    result = await geocode.geocode_places(
        [{"name": "Briançon", "role": "start", "day": 1}]
    )
    assert result[0]["found"] is True
    assert result[0]["lat"] == 45.0
    assert result[0]["lon"] == 6.0
    assert result[0]["role"] == "start"
    assert result[0]["day"] == 1


@pytest.mark.asyncio
async def test_geocode_places_maps_a_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    geocode.clear_cache()

    async def fake_name(_name: str):
        return None

    monkeypatch.setattr(geocode, "geocode_name", fake_name)
    result = await geocode.geocode_places([{"name": "nope"}])
    assert result == [
        {"name": "nope", "role": "waypoint", "day": None, "found": False}
    ]
