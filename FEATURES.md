# Feature inventory

Living list of product capabilities. When you add or change a feature, update this file in the same change.

Each entry has: **name**, **expected behavior**, **category**, **status**, **where it lives**, **out of scope**, **how to verify**.

Categories used so far: `trip logic`, `fact checking`, `MCP tool`, `UI`, `integration`, `validation`.

---

## Hello MCP wire

| | |
|---|---|
| **Expected behavior** | A minimal MCP server exposes one `hello` tool. Probes and ChatGPT can call it over HTTPS before the map app is trusted. |
| **Category** | integration, validation |
| **Status** | shipped |
| **Where it lives** | `hello_mcp/` |
| **Out of scope** | Geocoding, maps, trip planning |
| **How to verify** | `python hello_mcp/probe.py <base-url>`; ChatGPT: call `hello` with a name |

---

## Start map

| | |
|---|---|
| **Expected behavior** | ChatGPT passes one place name. The server geocodes it and shows one start pin (or reports not found). |
| **Category** | MCP tool, trip logic, UI |
| **Status** | shipped |
| **Where it lives** | `server.py` (`show_start_map`), `trip/start.py`, `widgets/trip-map.html` |
| **Out of scope** | Multiple stops, routes, elevation, continuity checks |
| **How to verify** | `pytest tests/test_resolve_start.py tests/test_server_start.py -q`; `python scripts/probe_start_mcp.py <base-url>`; ChatGPT: call `show_start_map` with Paris |

---

## Trip map (multi-stop pins)

| | |
|---|---|
| **Expected behavior** | ChatGPT passes an ordered list of named stops (optional role and day). Each found stop is pinned; misses are listed in the tool text. The map fits all drawn pins. |
| **Category** | MCP tool, trip logic, UI |
| **Status** | shipped |
| **Where it lives** | `server.py` (`show_trip_map`), `trip/places.py`, `trip/geocode.py`, `widgets/trip-map.html` |
| **Out of scope** | Routing, GPX, elevation, country-biased geocoding |
| **How to verify** | `pytest tests/test_resolve_places.py tests/test_server_trip.py -q -m "not live"`; probe `show_trip_map` with Paris and Lyon; ChatGPT: pin a short itinerary by name |

---

## Place geocoding (Nominatim)

| | |
|---|---|
| **Expected behavior** | Place names are looked up via Nominatim (cached, rate-limited). Hits return lat/lon and `display_name`; misses are `found: false` with no coordinates. ChatGPT must not invent coordinates. |
| **Category** | trip logic, integration |
| **Status** | shipped |
| **Where it lives** | `trip/geocode.py` |
| **Out of scope** | Fuzzy typo correction, country/region bias, alternate-hit selection |
| **How to verify** | `pytest tests/test_geocode.py tests/test_resolve_start.py -q -m "not live"`; live: `pytest -m live -q` |

---

## Continuity check (wrong-place hold)

| | |
|---|---|
| **Expected behavior** | After geocoding a multi-stop trip, a stop that lands off the chain of its neighbours is held off the map. Tool text asks ChatGPT to retry with a clearer name, or set `confirmed: true` if that geocoded place was intended. The tool result includes a `continuity` object (`needs_confirmation` or `accepted_confirmed`) so the hold/repair step is visible in ChatGPT and on the map banner. |
| **Category** | fact checking |
| **Status** | shipped |
| **Where it lives** | `trip/continuity.py`, wired in `trip/places.py` and `server.py`; widget skips `needs_confirmation` and shows hold/repair status |
| **Out of scope** | Judging whether a day is too long for the rider; broader itinerary fact-checking; auto-picking another Nominatim hit; detecting a rename-only retry without `confirmed` |
| **How to verify** | `pytest tests/test_continuity.py tests/test_resolve_places.py tests/test_server_trip.py -q -m "not live"`. In ChatGPT: prompt a trip with an ambiguous middle stop (e.g. Gap → Orange → Avignon). Expect tool text starting with `Continuity hold`, map banner in orange, and `structuredContent.continuity.status = needs_confirmation`. After ChatGPT sets `confirmed: true` (or a clearer name), expect `Continuity repair` / a full pin set. |

---

## Trip map pin presentation

| | |
|---|---|
| **Expected behavior** | Pins use role icons (start, overnight, finish, waypoint, …) and day-colored rings; a legend lists roles and days present on the map. Held or missing stops are named in the status line, not drawn as pins. |
| **Category** | UI |
| **Status** | shipped |
| **Where it lives** | `widgets/trip-map.html` |
| **Out of scope** | Route polylines, elevation profiles, basemap beyond OSM tiles |
| **How to verify** | `pytest tests/test_server_trip.py::test_widget_html_fits_several_pins -q`; local preview via `scripts/preview_start.py` for a single pin |

---

## MCP probes and Render deploy

| | |
|---|---|
| **Expected behavior** | Public `/mcp` on Render is probeable before ChatGPT is connected. Deploy starts the correct app module; free-tier cold starts are expected. |
| **Category** | integration, validation |
| **Status** | shipped |
| **Where it lives** | `hello_mcp/probe.py`, `scripts/probe_start_mcp.py`, `render.yaml`, `tests/test_render_config.py` |
| **Out of scope** | Local Windows tunnels as the ChatGPT path |
| **How to verify** | Probe the Render URL after deploy; `pytest tests/test_render_config.py -q` |
