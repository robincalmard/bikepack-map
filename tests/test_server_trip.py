"""Offline checks for the multi-stop map tool (no server, no Nominatim)."""

from __future__ import annotations

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from server import WIDGET_HTML, show_trip_map
from trip.continuity import confirmation_text


def test_widget_html_fits_several_pins() -> None:
    assert "dayColor" in WIDGET_HTML
    assert "iconSvg" in WIDGET_HTML
    for role in ("start", "overnight", "finish", "waypoint", "poi"):
        assert role in WIDGET_HTML
    assert 'overnight: "#2563eb"' not in WIDGET_HTML
    assert "fitBounds" in WIDGET_HTML
    assert "needs_confirmation" in WIDGET_HTML
    assert "Continuity hold" in WIDGET_HTML
    assert "Continuity repair" in WIDGET_HTML


@pytest.mark.asyncio
async def test_show_trip_map_returns_every_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = [
        {
            "name": "Paris",
            "role": "start",
            "day": 1,
            "found": True,
            "lat": 48.85,
            "lon": 2.35,
            "display_name": "Paris, France",
        },
        {
            "name": "Briançon",
            "role": "overnight",
            "day": 2,
            "found": True,
            "lat": 44.9,
            "lon": 6.64,
            "display_name": "Briançon, France",
        },
        {
            "name": "pqris",
            "role": "finish",
            "day": 3,
            "found": False,
        },
    ]

    async def fake_resolve(places: list[dict]) -> list[dict]:
        assert [place["name"] for place in places] == ["Paris", "Briançon", "pqris"]
        return resolved

    monkeypatch.setattr("server.resolve_places", fake_resolve)
    result = await show_trip_map(
        [
            {"name": "Paris", "role": "start", "day": 1},
            {"name": "Briançon", "role": "overnight", "day": 2},
            {"name": "pqris", "role": "finish", "day": 3},
        ]
    )

    assert result.is_error is False
    assert result.content[0].text == (
        "Mapped 2 places: Paris, Briançon. Not found: pqris."
    )
    assert result.structured_content["places"] == resolved
    assert result.structured_content["continuity"] == {
        "status": "ok",
        "held": [],
        "accepted_confirmed": [],
    }
    assert result.meta["openai/outputTemplate"].startswith("ui://widget/")
    assert result.meta["openai/toolInvocation/invoked"] == "Trip map ready"


@pytest.mark.asyncio
async def test_show_trip_map_reports_geocode_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(_places: list[dict]) -> list[dict]:
        raise TimeoutError("timed out")

    monkeypatch.setattr("server.resolve_places", boom)
    with pytest.raises(ToolError, match=r"Geocoding failed for .* \(TimeoutError\)"):
        await show_trip_map([{"name": "Paris", "role": "start"}])


@pytest.mark.asyncio
async def test_show_trip_map_asks_to_confirm_a_held_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = {
        "name": "Orange",
        "role": "overnight",
        "day": 2,
        "found": True,
        "lat": 50.0,
        "lon": 2.0,
        "display_name": "Orange, Nord, France",
        "needs_confirmation": True,
        "nearby": [
            {"name": "Gap", "km": 640},
            {"name": "Avignon", "km": 610},
        ],
        "chain_km": 90,
    }
    resolved = [
        {
            "name": "Gap",
            "role": "start",
            "day": 1,
            "found": True,
            "lat": 44.56,
            "lon": 6.08,
            "display_name": "Gap, France",
        },
        held,
        {
            "name": "pqris",
            "role": "finish",
            "day": 3,
            "found": False,
        },
    ]

    async def fake_resolve(_places: list[dict]) -> list[dict]:
        return resolved

    monkeypatch.setattr("server.resolve_places", fake_resolve)
    result = await show_trip_map(
        [
            {"name": "Gap", "role": "start", "day": 1},
            {"name": "Orange", "role": "overnight", "day": 2},
            {"name": "pqris", "role": "finish", "day": 3},
        ]
    )

    assert result.is_error is False
    assert result.content[0].text == (
        "Continuity hold. Mapped 1 place: Gap. Not found: pqris. "
        + confirmation_text(held)
    )
    assert result.structured_content["places"][1]["needs_confirmation"] is True
    assert "lat" not in result.structured_content["places"][2]
    assert result.structured_content["continuity"]["status"] == "needs_confirmation"
    assert result.structured_content["continuity"]["held"][0]["name"] == "Orange"
    assert "need confirmation" in result.meta["openai/toolInvocation/invoked"]


@pytest.mark.asyncio
async def test_show_trip_map_passes_confirmed_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def fake_resolve(places: list[dict]) -> list[dict]:
        captured["places"] = places
        return []

    monkeypatch.setattr("server.resolve_places", fake_resolve)
    await show_trip_map(
        [{"name": "Orange", "role": "overnight", "day": 2, "confirmed": True}]
    )
    assert captured["places"][0]["confirmed"] is True


@pytest.mark.asyncio
async def test_show_trip_map_reports_continuity_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = [
        {
            "name": "Gap",
            "role": "start",
            "day": 1,
            "found": True,
            "lat": 44.56,
            "lon": 6.08,
            "display_name": "Gap, France",
        },
        {
            "name": "Orange",
            "role": "overnight",
            "day": 2,
            "found": True,
            "lat": 50.0,
            "lon": 2.0,
            "display_name": "Orange, Nord, France",
            "confirmed": True,
        },
        {
            "name": "Avignon",
            "role": "finish",
            "day": 3,
            "found": True,
            "lat": 43.95,
            "lon": 4.81,
            "display_name": "Avignon, France",
        },
    ]

    async def fake_resolve(_places: list[dict]) -> list[dict]:
        return resolved

    monkeypatch.setattr("server.resolve_places", fake_resolve)
    result = await show_trip_map(
        [
            {"name": "Gap", "role": "start", "day": 1},
            {"name": "Orange", "role": "overnight", "day": 2, "confirmed": True},
            {"name": "Avignon", "role": "finish", "day": 3},
        ]
    )

    assert result.content[0].text.startswith(
        "Continuity repair: kept 1 place after confirmation (Orange)."
    )
    assert result.structured_content["continuity"] == {
        "status": "accepted_confirmed",
        "held": [],
        "accepted_confirmed": ["Orange"],
    }
    assert "confirmed" in result.meta["openai/toolInvocation/invoked"]
