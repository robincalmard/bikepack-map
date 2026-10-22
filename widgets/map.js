const ROLE_COLOR = {
  start: "#16a34a",
  finish: "#dc2626",
  overnight: "#2563eb",
  waypoint: "#ea580c",
  poi: "#7c3aed",
};

let map;
let markers = [];
let lastPayload = "";

function payloadFromHost() {
  const out = window.openai && window.openai.toolOutput;
  if (out && Array.isArray(out.places)) return out;
  return null;
}

function pinIcon(color) {
  return L.divIcon({
    className: "",
    html:
      '<div style="width:14px;height:14px;border-radius:50%;background:' +
      color +
      ';border:2px solid white;box-shadow:0 0 0 1px rgba(0,0,0,.25)"></div>',
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function renderPlaces(data) {
  const serialized = JSON.stringify(data || {});
  if (serialized === lastPayload) return;
  lastPayload = serialized;
  const places = (data && data.places) || [];
  const found = places.filter((p) => p.found && p.lat != null && p.lon != null);
  const missing = places.filter((p) => !p.found).map((p) => p.name);
  const status = document.getElementById("status");
  status.textContent = missing.length
    ? `Showing ${found.length} places. Not found: ${missing.join(", ")}`
    : `Showing ${found.length} places`;

  if (!map) {
    const center = found.length ? [found[0].lat, found[0].lon] : [43.79, 4.83];
    map = L.map("map", { zoomControl: true }).setView(center, found.length ? 11 : 6);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap",
    }).addTo(map);
  }

  markers.forEach((marker) => marker.remove());
  markers = [];
  const latlngs = [];
  found.forEach((place) => {
    const color = ROLE_COLOR[place.role] || "#334155";
    const day = place.day != null ? ` · day ${place.day}` : "";
    const marker = L.marker([place.lat, place.lon], { icon: pinIcon(color) })
      .addTo(map)
      .bindPopup(`${place.name} (${place.role || "place"}${day})`);
    markers.push(marker);
    latlngs.push([place.lat, place.lon]);
  });

  if (latlngs.length === 1) {
    map.setView(latlngs[0], 11);
  } else if (latlngs.length > 1) {
    map.fitBounds(latlngs, { padding: [48, 48], maxZoom: 12 });
  }
  setTimeout(() => map.invalidateSize(), 50);
}

function boot() {
  const initial = payloadFromHost();
  if (initial) renderPlaces(initial);

  window.addEventListener("message", (event) => {
    if (event.source !== window.parent) return;
    const message = event.data;
    if (!message || message.jsonrpc !== "2.0") return;
    if (message.method === "ui/notifications/tool-result") {
      const params = message.params || {};
      const structured =
        params.structuredContent ||
        (params.result && params.result.structuredContent);
      if (structured) renderPlaces(structured);
    }
  });

  setInterval(() => {
    const next = payloadFromHost();
    if (next) renderPlaces(next);
  }, 1500);
}

boot();
