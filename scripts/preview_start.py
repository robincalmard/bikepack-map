"""Local one-pin preview — no MCP, no ChatGPT.

Resolves a start place with trip.resolve_start, injects it into the map
widget as window.openai.toolOutput, and opens the result in your browser.

Usage:
  python scripts/preview_start.py
  python scripts/preview_start.py Paris
  python scripts/preview_start.py pqris
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trip import clear_cache, resolve_start  # noqa: E402

WIDGET = ROOT / "widgets" / "trip-map.html"
OUT = ROOT / "widgets" / "preview-start.html"

INJECT_MARKER = "<!-- preview-start: injected payload -->"


def _build_html(place: dict) -> str:
    """Widget expects {places: [...]}; pin-ready start gets a start role."""
    pin = dict(place)
    if pin.get("found"):
        pin.setdefault("role", "start")
    payload = {"places": [pin]}
    inject = (
        f"{INJECT_MARKER}\n"
        f"<script>\n"
        f"  window.openai = {{ toolOutput: {json.dumps(payload)} }};\n"
        f"</script>\n"
    )
    html = WIDGET.read_text(encoding="utf-8")
    if INJECT_MARKER in html:
        raise RuntimeError("Do not use trip-map.html as a previously injected file")
    # Inject before the widget script boots so payloadFromHost() sees data.
    needle = '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
    if needle not in html:
        raise RuntimeError("Unexpected widget HTML; cannot inject preview payload")
    return html.replace(needle, inject + needle, 1)


async def _run(name: str) -> dict:
    clear_cache()
    return await resolve_start(name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview one start pin on the map")
    parser.add_argument(
        "name",
        nargs="?",
        default="Paris",
        help='Place name to resolve (default: "Paris")',
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Write HTML only; do not open a browser",
    )
    args = parser.parse_args()

    place = asyncio.run(_run(args.name))
    OUT.write_text(_build_html(place), encoding="utf-8")

    if place.get("found"):
        print(f"Found: {place['name']} @ {place['lat']}, {place['lon']}")
    else:
        print(f"Not found: {place['name']!r} (map opens with no pin)")
    print(f"Wrote {OUT}")

    if not args.no_open:
        webbrowser.open(OUT.resolve().as_uri())


if __name__ == "__main__":
    main()
