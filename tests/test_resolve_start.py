"""v1 product surface: resolve_start — one name → pin-ready place.

Offline tests mock geocode_name. Live tests hit Nominatim.
"""

from __future__ import annotations

import pytest

from trip import clear_cache, resolve_start

_PARIS_LAT = (48.5, 49.1)
_PARIS_LON = (2.0, 2.7)


# --- Offline -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_name_is_not_found() -> None:
    clear_cache()
    assert await resolve_start("") == {"name": "", "found": False}
    assert await resolve_start("   ") == {"name": "", "found": False}


@pytest.mark.asyncio
async def test_hit_returns_pin_ready_place(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_cache()

    async def fake_name(name: str):
        return {"lat": 48.85, "lon": 2.35, "display_name": f"{name}, France"}

    monkeypatch.setattr("trip.start.geocode_name", fake_name)

    place = await resolve_start("Paris")
    assert place == {
        "name": "Paris",
        "found": True,
        "lat": 48.85,
        "lon": 2.35,
        "display_name": "Paris, France",
    }


@pytest.mark.asyncio
async def test_miss_has_no_coordinates(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_cache()

    async def fake_name(_name: str):
        return None

    monkeypatch.setattr("trip.start.geocode_name", fake_name)
    place = await resolve_start("nope")
    assert place == {"name": "nope", "found": False}
    assert "lat" not in place
    assert "lon" not in place


# --- Live --------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_paris_is_found() -> None:
    clear_cache()
    place = await resolve_start("Paris")
    assert place["found"] is True
    assert place["name"] == "Paris"
    assert isinstance(place["lat"], float)
    assert isinstance(place["lon"], float)
    assert _PARIS_LAT[0] <= place["lat"] <= _PARIS_LAT[1]
    assert _PARIS_LON[0] <= place["lon"] <= _PARIS_LON[1]
    assert place.get("display_name")


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_typo_pqris_is_not_found() -> None:
    """v1 does not fuzzy-fix typos."""
    clear_cache()
    place = await resolve_start("pqris")
    assert place == {"name": "pqris", "found": False}


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_nonsense_name_is_not_found() -> None:
    clear_cache()
    place = await resolve_start("xyzzy-not-a-place-999")
    assert place == {"name": "xyzzy-not-a-place-999", "found": False}
