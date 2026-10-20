"""Local unit tests for trip logic — no MCP, no tunnel, no ChatGPT."""

from __future__ import annotations

import pytest

from trip import geocode


@pytest.mark.asyncio
async def test_geocode_places_empty_name() -> None:
    geocode.clear_cache()
    result = await geocode.geocode_places([{"name": "", "role": "start"}])
    assert result == [{"name": "", "role": "start", "day": None, "found": False}]


@pytest.mark.asyncio
async def test_geocode_places_maps_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    geocode.clear_cache()

    async def fake_name(name: str):
        return {"lat": 45.0, "lon": 6.0, "display_name": f"{name}, Alps"}

    monkeypatch.setattr(geocode, "geocode_name", fake_name)
    result = await geocode.geocode_places(
        [{"name": "Briançon", "role": "start", "day": 1}]
    )
    assert result[0]["found"] is True
    assert result[0]["lat"] == 45.0
    assert result[0]["role"] == "start"
