# bikepack-map

A ChatGPT plugin that pins a bikepacking itinerary on a map.

You describe the trip in ChatGPT. ChatGPT writes the plan, then calls this Python server with **place names**. The server geocodes them and shows a MapLibre map in the chat.

v1 is pins only (start, overnights, waypoints). Routing and elevation come later.

## Architecture (logic vs ChatGPT wire)

| Layer | Where | How you work on it |
|---|---|---|
| **Trip logic** | `trip/` (geocoding, later routing) | Local unit tests — no MCP, no tunnel |
| **MCP adapter** | `server.py` / `hello_mcp/` | Thin wrappers that call `trip/` |
| **ChatGPT connectivity** | Deployed HTTPS `/mcp` (Render) | Paste URL into ChatGPT |

Local Windows + antivirus has been unreliable for the ChatGPT MCP handshake. Develop logic locally; prove the ChatGPT wire on Render.

```powershell
# Logic only (fast feedback)
pip install -r requirements-dev.txt
pytest tests/ -q
```

## Setup (full local MCP server)

```powershell
cd C:\Users\calma\Dev\bikepack-map
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`.

## Deploy free (Render) — connectivity first

**Step A — hello probe** (`hello_mcp/`): one `hello` tool, proves ChatGPT can talk to your server.

1. Push this repo to GitHub.
2. [render.com](https://render.com) → **New → Web Service** → this repo.
3. Settings:
   - **Root directory:** `hello_mcp`
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. After deploy, ChatGPT MCP URL: `https://<service>.onrender.com/mcp`
5. Ask ChatGPT to call `hello`.

**Step B — full app:** same flow with root directory empty / repo root, start `uvicorn server:app --host 0.0.0.0 --port $PORT`.

Free services sleep after ~15 minutes idle; the first request after that can take about a minute.

## Connect ChatGPT (local tunnel)

ChatGPT cannot reach localhost. While developing, tunnel the port (ngrok / cloudflared), **or** use the Render URL above.

Then in ChatGPT: **Plugins → Add custom MCP server** → paste `https://<host>/mcp` → create / install.

In a new chat, type `@bikepack-map` (or whatever you named the plugin) and:

> I want a 3 day bikepacking trip from Saint-Rémy-de-Provence, paved only, under 100 km and 1000 m elevation per day.

ChatGPT should answer in text, then call `show_trip_map` with the towns it proposed.

## Tools

| Tool | What it does |
|---|---|
| `show_trip_map` | Geocode names and render the map widget |
| `geocode_places` | Same geocoding, no map (for inspection) |

ChatGPT must pass **names**, not coordinates. Nominatim looks them up.

## Notes

- Nominatim is for light personal use; results are cached in memory.
- After you change tools, refresh the plugin in ChatGPT so it reloads the schema.
