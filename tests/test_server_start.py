"""Offline checks for v1 MCP start-map helpers (no server, no Nominatim)."""

from __future__ import annotations

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from server import WIDGET_HTML, _pin_for_widget, _summary, show_start_map


def test_pin_for_widget_adds_start_role_when_found() -> None:
    pin = _pin_for_widget(
        {
            "name": "Paris",
            "found": True,
            "lat": 48.85,
            "lon": 2.35,
            "display_name": "Paris, France",
        }
    )
    assert pin["role"] == "start"
    assert pin["found"] is True


def test_pin_for_widget_leaves_miss_without_role() -> None:
    pin = _pin_for_widget({"name": "pqris", "found": False})
    assert pin == {"name": "pqris", "found": False}


def test_widget_html_contains_the_map() -> None:
    assert "tile.openstreetmap.org" in WIDGET_HTML
    assert "leaflet" in WIDGET_HTML
    assert "/widget/map.js" not in WIDGET_HTML


def test_summary_found_and_miss() -> None:
    assert _summary({"name": "Paris", "found": True}) == "Mapped start: Paris."
    assert _summary({"name": "pqris", "found": False}) == "Not found: pqris."


@pytest.mark.asyncio
async def test_show_start_map_returns_one_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(name: str) -> dict:
        return {
            "name": name,
            "found": True,
            "lat": 48.85,
            "lon": 2.35,
            "display_name": "Paris, France",
        }

    monkeypatch.setattr("server.resolve_start", fake_resolve)
    result = await show_start_map("Paris")

    assert result.is_error is False
    assert result.content[0].text == "Mapped start: Paris."
    place = result.structured_content["places"][0]
    assert place["name"] == "Paris"
    assert place["found"] is True
    assert place["role"] == "start"
    assert place["lat"] == 48.85
    assert place["lon"] == 2.35
    assert result.meta["openai/outputTemplate"].startswith("ui://widget/")


@pytest.mark.asyncio
async def test_show_start_map_reports_geocode_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(_name: str) -> dict:
        raise TimeoutError("timed out")

    monkeypatch.setattr("server.resolve_start", boom)
    with pytest.raises(ToolError, match=r"Geocoding failed for 'Paris' \(TimeoutError\)"):
        await show_start_map("Paris")
