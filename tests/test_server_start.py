"""Offline checks for v1 MCP start-map helpers (no server, no Nominatim)."""

from __future__ import annotations

from server import _pin_for_widget, _summary


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


def test_summary_found_and_miss() -> None:
    assert _summary({"name": "Paris", "found": True}) == "Mapped start: Paris."
    assert _summary({"name": "pqris", "found": False}) == "Not found: pqris."
