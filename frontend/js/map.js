/* Regional outbreak map (Leaflet from cdnjs, OpenStreetMap tiles).

   Leaflet is ~40 KB and only needed on this tab, so it is loaded the first
   time the farmer opens the map, pinned with a subresource-integrity hash. */

const LEAFLET = {
  css: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css",
  cssSri: "sha512-h9FcoyWjHcOcmEVkxOfTLnmZFWIH0iZhZT1H2TbOq55xssQGEJHEaIm+PgoUaZbRvQTNTluNOEfb1ZRy6D3BOw==",
  js: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js",
  jsSri: "sha512-puJW3E/qXDqYp9IfhAI54BJEaWIfloJ7JWs7OeD5i6ruC9JZL1gERT1wjtwXFlh7CjE7ZJ+/vcRZRkIYIb6p4g==",
};

const SEVERITY_COLOUR = { high: "#b3261e", medium: "#e3a21a", low: "#e3a21a" };
const MAHARASHTRA = [19.4, 76.2];

let leafletReady = null;
let map = null;
let layer = null;

function loadLeaflet() {
  if (window.L) return Promise.resolve();
  leafletReady ??= new Promise((resolve, reject) => {
    const css = document.createElement("link");
    Object.assign(css, { rel: "stylesheet", href: LEAFLET.css, integrity: LEAFLET.cssSri, crossOrigin: "anonymous" });
    document.head.appendChild(css);
    const js = document.createElement("script");
    Object.assign(js, { src: LEAFLET.js, integrity: LEAFLET.jsSri, crossOrigin: "anonymous" });
    js.onload = resolve;
    js.onerror = () => { leafletReady = null; reject(new Error("leaflet")); };
    document.head.appendChild(js);
  });
  return leafletReady;
}

/** Group rows from /api/outbreaks into one marker per grid cell. */
function byCell(cells) {
  const out = new Map();
  for (const c of cells) {
    const key = `${c.lat},${c.lon}`;
    if (!out.has(key)) out.set(key, { lat: c.lat, lon: c.lon, total: 0, rows: [] });
    const cell = out.get(key);
    cell.total += c.count;
    cell.rows.push(c);
  }
  return [...out.values()];
}

function popup(cell, s) {
  const box = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = s.mapReports(cell.total);
  box.appendChild(title);
  const ul = document.createElement("ul");
  ul.style.cssText = "margin:6px 0 0 16px;padding:0";
  for (const r of cell.rows) {
    const li = document.createElement("li");
    li.textContent = `${r.crop} — ${r.disease}: ${r.count}`;
    ul.appendChild(li);
  }
  box.appendChild(ul);
  return box;
}

export async function showMap({ api, lang, days, s, home, status }) {
  status.hidden = true;
  try {
    await loadLeaflet();
  } catch {
    status.textContent = s.mapError;
    status.hidden = false;
    return;
  }
  const L = window.L;
  if (!map) {
    map = L.map("map", { zoomControl: true }).setView(home ? [home.lat, home.lon] : MAHARASHTRA, home ? 9 : 6);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 16,
      attribution: "&copy; OpenStreetMap",
    }).addTo(map);
  }
  // The container was hidden while the tab was closed; Leaflet must re-measure.
  setTimeout(() => map.invalidateSize(), 50);

  let data;
  try {
    const res = await fetch(`${api}/api/outbreaks?days=${days}&lang=${lang}`);
    data = await res.json();
  } catch {
    status.textContent = s.mapError;
    status.hidden = false;
    return;
  }

  layer?.remove();
  layer = L.layerGroup().addTo(map);
  const cells = byCell(data.cells);
  for (const cell of cells) {
    const worst = cell.rows.some((r) => r.severity === "high") ? "high" : "medium";
    L.circleMarker([cell.lat, cell.lon], {
      radius: Math.min(10 + cell.total * 3, 30),
      color: SEVERITY_COLOUR[worst],
      fillColor: SEVERITY_COLOUR[worst],
      fillOpacity: 0.45,
      weight: 2,
    }).bindPopup(popup(cell, s)).addTo(layer);
  }
  if (!cells.length) {
    status.textContent = s.mapEmpty;
    status.hidden = false;
  }
}

/** Nearest reports around the farmer, for the alert on the home screen. */
export async function nearbyOutbreak(api, lang, home, radiusKm = 25) {
  const res = await fetch(`${api}/api/outbreaks?days=14&lang=${lang}`);
  if (!res.ok) return null;
  const { cells } = await res.json();
  const near = cells.filter((c) => distanceKm(home, c) <= radiusKm);
  if (!near.length) return null;
  const top = near.reduce((a, b) => (b.count > a.count ? b : a));
  const total = near.filter((c) => c.class_name === top.class_name).reduce((n, c) => n + c.count, 0);
  return { count: total, label: `${top.crop} — ${top.disease}` };
}

function distanceKm(a, b) {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}
