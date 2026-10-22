"""Offline checks for the multi-stop map tool (no server, no Nominatim)."""

from __future__ import annotations

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from server import WIDGET_HTML, show_trip_map


def test_widget_html_fits_several_pins() -> None:
    assert 'overnight: "#2563eb"' in WIDGET_HTML
    assert 'finish: "#dc2626"' in WIDGET_HTML
    assert "fitBounds" in WIDGET_HTML


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
    assert result.meta["openai/outputTemplate"].startswith("ui://widget/")


@pytest.mark.asyncio
async def test_show_trip_map_reports_geocode_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(_places: list[dict]) -> list[dict]:
        raise TimeoutError("timed out")

    monkeypatch.setattr("server.resolve_places", boom)
    with pytest.raises(ToolError, match=r"Geocoding failed for .* \(TimeoutError\)"):
        await show_trip_map([{"name": "Paris", "role": "start"}])
