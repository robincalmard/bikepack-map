"""Multi-stop product surface: resolve_places — names → pin-ready places.

Offline tests mock geocoding. The live test hits Nominatim.
"""

from __future__ import annotations

import pytest

from trip import clear_cache, resolve_places

_PARIS_LAT = (48.5, 49.1)
_PARIS_LON = (2.0, 2.7)
_LYON_LAT = (45.6, 45.9)
_LYON_LON = (4.6, 5.0)


def _hit(name: str) -> dict:
    return {"lat": 45.0, "lon": 6.0, "display_name": f"{name}, Alps"}


# --- Offline -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_places_keep_input_order(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_cache()

    async def fake_name(name: str):
        return {"lat": len(name), "lon": 1.0, "display_name": name}

    monkeypatch.setattr("trip.geocode.geocode_name", fake_name)
    places = await resolve_places(
        [
            {"name": "Paris"},
            {"name": "Lyon"},
            {"name": "Briançon"},
        ]
    )
    assert [place["name"] for place in places] == ["Paris", "Lyon", "Briançon"]


@pytest.mark.asyncio
async def test_hit_keeps_the_input_name(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_cache()

    async def fake_name(name: str):
        return {
            "lat": 48.85,
            "lon": 2.35,
            "display_name": "Paris, Île-de-France, France",
        }

    monkeypatch.setattr("trip.geocode.geocode_name", fake_name)
    place = (
        await resolve_places([{"name": "Paris", "role": "start", "day": 1}])
    )[0]
    assert place["name"] == "Paris"
    assert place["found"] is True
    assert place["lat"] == 48.85
    assert place["lon"] == 2.35
    assert place["display_name"] == "Paris, Île-de-France, France"
    assert place["role"] == "start"
    assert place["day"] == 1


@pytest.mark.asyncio
async def test_roles_and_days_pass_through(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_cache()

    async def fake_name(name: str):
        return _hit(name)

    monkeypatch.setattr("trip.geocode.geocode_name", fake_name)
    places = await resolve_places(
        [
            {"name": "Paris", "role": "start", "day": 1},
            {"name": "Briançon", "role": "overnight", "day": 2},
            {"name": "Nice", "role": "finish", "day": 3},
        ]
    )
    assert [(p["role"], p["day"]) for p in places] == [
        ("start", 1),
        ("overnight", 2),
        ("finish", 3),
    ]


@pytest.mark.asyncio
async def test_miss_in_the_middle_has_no_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_cache()

    async def fake_name(name: str):
        if name == "pqris":
            return None
        return _hit(name)

    monkeypatch.setattr("trip.geocode.geocode_name", fake_name)
    places = await resolve_places(
        [
            {"name": "Paris", "role": "start"},
            {"name": "pqris", "role": "overnight"},
            {"name": "Lyon", "role": "finish"},
        ]
    )
    assert places[0]["found"] is True
    assert places[2]["found"] is True
    assert places[1] == {
        "name": "pqris",
        "role": "overnight",
        "day": None,
        "found": False,
    }
    assert "lat" not in places[1]
    assert "lon" not in places[1]


@pytest.mark.asyncio
async def test_blank_names_are_not_found() -> None:
    clear_cache()
    places = await resolve_places([{"name": ""}, {"name": "   "}])
    assert places == [
        {"name": "", "role": "waypoint", "day": None, "found": False},
        {"name": "", "role": "waypoint", "day": None, "found": False},
    ]
    assert "lat" not in places[0]
    assert "lat" not in places[1]


@pytest.mark.asyncio
async def test_empty_list() -> None:
    clear_cache()
    assert await resolve_places([]) == []


@pytest.mark.asyncio
async def test_missing_role_defaults_and_unknown_role_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_cache()

    async def fake_name(name: str):
        return _hit(name)

    monkeypatch.setattr("trip.geocode.geocode_name", fake_name)
    places = await resolve_places(
        [
            {"name": "Paris"},
            {"name": "Gap", "role": "camp", "day": 2},
        ]
    )
    assert places[0]["role"] == "waypoint"
    assert places[0]["day"] is None
    assert places[1]["role"] == "camp"
    assert places[1]["day"] == 2


@pytest.mark.asyncio
async def test_geocode_error_fails_the_whole_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_cache()

    async def fake_name(name: str):
        if name == "Lyon":
            raise TimeoutError("timed out")
        return _hit(name)

    monkeypatch.setattr("trip.geocode.geocode_name", fake_name)
    with pytest.raises(TimeoutError):
        await resolve_places(
            [
                {"name": "Paris", "role": "start"},
                {"name": "Lyon", "role": "finish"},
            ]
        )


@pytest.mark.asyncio
async def test_off_chain_stop_is_held_and_confirmed_stop_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_cache()
    coords = {
        "Gap": (45.0, 6.0),
        "Orange": (48.5, 6.2),
        "Avignon": (45.0, 6.5),
    }

    async def fake_name(name: str):
        lat, lon = coords[name]
        return {"lat": lat, "lon": lon, "display_name": f"{name}, France"}

    monkeypatch.setattr("trip.geocode.geocode_name", fake_name)
    places = await resolve_places(
        [
            {"name": "Gap", "role": "start", "day": 1},
            {"name": "Orange", "role": "overnight", "day": 2},
            {"name": "Avignon", "role": "finish", "day": 3},
        ]
    )
    assert places[1]["needs_confirmation"] is True
    assert places[1]["name"] == "Orange"
    assert "needs_confirmation" not in places[0]
    assert "needs_confirmation" not in places[2]

    accepted = await resolve_places(
        [
            {"name": "Gap", "role": "start", "day": 1},
            {"name": "Orange", "role": "overnight", "day": 2, "confirmed": True},
            {"name": "Avignon", "role": "finish", "day": 3},
        ]
    )
    assert accepted[1]["confirmed"] is True
    assert "needs_confirmation" not in accepted[1]
    assert accepted[1]["lat"] == 48.5


# --- Live --------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_paris_typo_and_lyon() -> None:
    clear_cache()
    places = await resolve_places(
        [
            {"name": "Paris", "role": "start", "day": 1},
            {"name": "pqris", "role": "overnight", "day": 2},
            {"name": "Lyon", "role": "finish", "day": 3},
        ]
    )
    assert [place["name"] for place in places] == ["Paris", "pqris", "Lyon"]

    paris, typo, lyon = places
    assert paris["found"] is True
    assert paris["role"] == "start"
    assert paris["day"] == 1
    assert _PARIS_LAT[0] <= paris["lat"] <= _PARIS_LAT[1]
    assert _PARIS_LON[0] <= paris["lon"] <= _PARIS_LON[1]

    assert typo == {
        "name": "pqris",
        "role": "overnight",
        "day": 2,
        "found": False,
    }
    assert "lat" not in typo
    assert "lon" not in typo

    assert lyon["found"] is True
    assert lyon["role"] == "finish"
    assert lyon["day"] == 3
    assert _LYON_LAT[0] <= lyon["lat"] <= _LYON_LAT[1]
    assert _LYON_LON[0] <= lyon["lon"] <= _LYON_LON[1]
