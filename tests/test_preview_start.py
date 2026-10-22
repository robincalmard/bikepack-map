"""Offline checks for the local map preview injector (no Nominatim, no browser)."""

from __future__ import annotations

import json

from scripts.preview_start import INJECT_MARKER, _build_html


def test_build_html_injects_found_start_pin() -> None:
    place = {
        "name": "Paris",
        "found": True,
        "lat": 48.85,
        "lon": 2.35,
        "display_name": "Paris, France",
    }
    html = _build_html(place)
    assert INJECT_MARKER in html
    assert "window.openai" in html
    assert '"role": "start"' in html or '"role":"start"' in html
    # Payload parses as the widget expects
    start = html.index("toolOutput:") + len("toolOutput:")
    end = html.index("};", start)
    payload = json.loads(html[start:end].strip())
    assert payload["places"][0]["found"] is True
    assert payload["places"][0]["lat"] == 48.85
    assert payload["places"][0]["role"] == "start"


def test_build_html_injects_not_found_without_role() -> None:
    place = {"name": "pqris", "found": False}
    html = _build_html(place)
    start = html.index("toolOutput:") + len("toolOutput:")
    end = html.index("};", start)
    payload = json.loads(html[start:end].strip())
    assert payload["places"] == [{"name": "pqris", "found": False}]
