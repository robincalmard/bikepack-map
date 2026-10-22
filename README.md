# bikepack-map

A ChatGPT plugin that pins a bikepacking itinerary on a map.

You describe the trip in ChatGPT. ChatGPT writes the plan, then calls this Python server with **place names**. The server geocodes them and shows a MapLibre map in the chat.

v1 is pins only (start, overnights, waypoints). Routing and elevation come later.

**Current focus:** prove ChatGPT can call a tool on our server. Use the hello-world ladder below. Do not touch the full map app until Step 5 passes.

## Architecture (logic vs ChatGPT wire)

| Layer | Where | How you work on it |
|---|---|---|
| **Trip logic (v1)** | `trip.resolve_start` — one start name → pin-ready place | Local unit tests — no MCP, no tunnel |
| **Geocode helper** | `trip/geocode.py` (Nominatim) | Used by `resolve_start`; later multi-stop |
| **Hello MCP (wire first)** | `hello_mcp/` | Connectivity probe — one `hello` tool |
| **Map MCP** | `server.py` — `show_start_map`, `show_trip_map` | Local probe, then Render, then ChatGPT |
| **ChatGPT connectivity** | Deployed HTTPS `/mcp` (Render) | Paste URL after start-map probe PASSes |

Local Windows + antivirus has been unreliable for the ChatGPT MCP handshake. Develop logic locally; prove the ChatGPT wire on Render.

```powershell
# Trip logic only (fast feedback; no MCP)
pip install -r requirements-dev.txt
pytest tests/ -q -m "not live"          # offline (mocked) — default day-to-day
pytest tests/ -q -m live                # hits Nominatim (needs internet; pause HTTPS AV if SSL fails)
pytest tests/ -q                        # both
```

### Local one-pin preview (no ChatGPT)

Resolves a start name, writes `widgets/preview-start.html`, opens it in your browser:

```powershell
python scripts/preview_start.py              # Paris
python scripts/preview_start.py "Briançon"
python scripts/preview_start.py pqris        # expect no pin
```

`widgets/trip-map.html` stays the ChatGPT widget (untouched). Preview injects a fake `window.openai.toolOutput` for local viewing. Pause Avast HTTPS shield if Nominatim SSL fails.

### Local start-map MCP probe (no ChatGPT)

One tool: `show_start_map` with `{ "name": "Paris" }` → text + pin `structuredContent` + widget meta.

```powershell
# Terminal 1
python server.py

# Terminal 2 (pause Avast if Nominatim SSL fails)
python scripts/probe_start_mcp.py http://127.0.0.1:8000
```

**Pass:** every line `PASS`, including `tools/call` for Paris. Then deploy root `server.py` to Render and re-probe the public URL before ChatGPT.

---

## ChatGPT wire — gated validation ladder

Do these steps **in order**. Do not start the next step until the previous one passes. Prefer `hello_mcp/probe.py` over guessing from the ChatGPT UI.

### Step 1 — Local health

```powershell
cd hello_mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

`python main.py` serves MCP with the Python SDK v2. Default port is `8000` (`PORT` env overrides). Use the repo's Python 3.12 venv.

In another shell:

```powershell
curl http://127.0.0.1:8000/
```

**Pass:** `{"ok": true, "mcp": "/mcp"}` (HTTP 200).

### Step 2 — Local MCP handshake (still no ChatGPT)

With the server from Step 1 still running:

```powershell
cd hello_mcp
python probe.py http://127.0.0.1:8000
```

The probe checks, in order:

1. `GET /` health
2. `POST` `server/discover` on protocol `2026-07-28` (must list that version and `resultType: complete`)
3. `POST` `tools/list` on the same protocol (must include `hello` and `resultType: complete`)
4. `POST` `tools/call` `hello` → `Hello, Robin!`

**Pass:** every line prints `PASS` and exit code 0. **Fail:** fix `hello_mcp/` only; do not deploy.

### Step 3 — Deploy only `hello_mcp` to Render

Use the `chatgpt-mcp-hello` service in [`render.yaml`](render.yaml), or point an existing Web Service at `hello_mcp`:

| Setting | Value |
|---|---|
| Root directory | `hello_mcp` |
| Build | `pip install -r requirements.txt` |
| Start | `python main.py` |

After deploy (current live hello URL):

```powershell
curl https://bikepack-map.onrender.com/
```

Free tier cold starts can take ~1 minute — wake the service before probing.

**Pass:** same health JSON as Step 1 on the public URL.

### Step 4 — Same probe against Render

```powershell
cd hello_mcp
python probe.py https://bikepack-map.onrender.com
```

**Pass:** all gates green on HTTPS. **This is the critical gate.** If this fails, ChatGPT will also fail — debug with the probe, not inside ChatGPT.

Do **not** use ngrok/local tunnel for ChatGPT; use the Render URL only.

### Step 5 — Connect ChatGPT

Only after Step 4 is green:

1. Remove any previous custom MCP entry for this URL (a failed setup is not always cleared by refresh).
2. ChatGPT → **Plugins → Add custom MCP server** → paste `https://bikepack-map.onrender.com/mcp`
3. New chat, mention the plugin
4. Ask: *Call the hello tool with my name*
5. Expect a tool call and `Hello, …!`

**Pass:** ChatGPT shows a successful `hello` tool call. That is the end of hello-world.

**Fail:** capture the ChatGPT error; re-run Step 4 immediately. If Step 4 still passes, the issue is ChatGPT config/refresh, not the server.

### Step 6 — Start-map app (v1)

Only after Step 5 passes: deploy repo-root `server.py` (`uvicorn server:app`), run `python scripts/probe_start_mcp.py https://…`, then ask ChatGPT to call `show_start_map` with a place name (e.g. Paris) or `show_trip_map` with several named stops. Same ladder — never skip the probe. Routing and elevation come later.

---

## Working agreement

- One change at a time in `hello_mcp/`; re-run the probe after every change.
- Never debug ChatGPT and server changes in the same iteration.
- Prefer probe output over ChatGPT UI.
- Treat free Render cold starts as expected delay, not a broken deploy.
- Both `hello_mcp` and root `server.py` use MCP Python SDK v2 so ChatGPT's `2026-07-28` discover and tool calls succeed. Our older probe used `initialize` only — that can PASS while ChatGPT setup still FAILS.
- On some Windows machines, HTTP responses to paths with a `/mcp` segment are
  mangled (`Transfer-Encoding: chunked` without framing). `probe.py` tolerates
  that for local checks; **use Render HTTPS for ChatGPT** (Linux framing is fine).

## Full app tools (after hello works)

| Tool | What it does |
|---|---|
| `show_start_map` | Geocode one start name and show one pin |
| `show_trip_map` | Geocode a list of named stops and show one pin each |

ChatGPT must pass **names**, not coordinates. Nominatim looks them up.

## Notes

- Nominatim is for light personal use; results are cached in memory.
- After you change tools, refresh the plugin in ChatGPT so it reloads the schema.
- Free Render services sleep after ~15 minutes idle.
