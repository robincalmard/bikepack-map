# bikepack-map

A ChatGPT plugin that pins a bikepacking itinerary on a map.

You describe the trip in ChatGPT. ChatGPT writes the plan, then calls this Python server with **place names**. The server geocodes them and shows a MapLibre map in the chat.

v1 is pins only (start, overnights, waypoints). Routing and elevation come later.

## Setup

```powershell
cd C:\Users\calma\Dev\bikepack-map
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`.

## Deploy free (Render)

Easiest way for ChatGPT to reach the app (no local tunnel):

1. Push this repo to GitHub.
2. Sign up at [https://render.com](https://render.com) (free).
3. **New → Web Service** → connect the GitHub repo.
4. Settings:
   - **Runtime:** Python
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn server:app --host 0.0.0.0 --port $PORT`
5. Create the service (Free instance).
6. When live, your MCP URL is: `https://<your-service>.onrender.com/mcp`

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
