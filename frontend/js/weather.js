/* Spray-timing card: one sentence verdict, then a 48-hour ribbon where green
   bars are good spraying hours and blue bars are rain, so the farmer can see
   the whole two days at a glance without reading a table. */

const LOC_KEY = "location.v1";

export function savedLocation() {
  try {
    return JSON.parse(localStorage.getItem(LOC_KEY));
  } catch {
    return null;
  }
}

/** Ask for the phone's location, rounded to ~1 km before it is stored or sent. */
export function requestLocation() {
  return new Promise((resolve, reject) => {
    if (!window.isSecureContext || !navigator.geolocation) return reject(new Error("https"));
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const loc = {
          lat: Math.round(pos.coords.latitude * 100) / 100,
          lon: Math.round(pos.coords.longitude * 100) / 100,
        };
        try { localStorage.setItem(LOC_KEY, JSON.stringify(loc)); } catch { /* session only */ }
        resolve(loc);
      },
      () => reject(new Error("denied")),
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 30 * 60 * 1000 },
    );
  });
}

const cache = new Map();

export async function fetchWeather(api, loc) {
  const key = `${loc.lat},${loc.lon}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < 15 * 60 * 1000) return hit.data;
  const res = await fetch(`${api}/api/weather?lat=${loc.lat}&lon=${loc.lon}`);
  if (!res.ok) throw new Error("weather");
  const data = await res.json();
  cache.set(key, { at: Date.now(), data });
  return data;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function icon(name) {
  const s = el("span", "ms", name);
  s.setAttribute("aria-hidden", "true");
  return s;
}

/** "Today 6 am", "Tomorrow 5 pm" in the farmer's language. With `sameDayAs`,
    the day is left out when it matches, so a range reads "Tomorrow 6 am to 9 am". */
function when(iso, s, now = new Date(), sameDayAs = null) {
  const d = new Date(iso);
  const time = new Intl.DateTimeFormat(s.locale, { hour: "numeric" }).format(d);
  if (sameDayAs && new Date(sameDayAs).toDateString() === d.toDateString()) return time;
  const day = Math.round((new Date(d.toDateString()) - new Date(now.toDateString())) / 86400000);
  const label = day <= 0 ? s.today : day === 1 ? s.tomorrow : s.dayAfter;
  return `${label} ${time}`;
}

function heading(s) {
  const h = el("h3");
  h.append(icon("water_drop"), el("span", null, s.wxTitle));
  return h;
}

/** Card asking for location, shown until the farmer grants it. */
export function renderLocationPrompt(box, s, onGrant) {
  box.replaceChildren(heading(s), el("p", "wx-row", s.wxNeedLoc));
  const btn = el("button", "secondary-btn");
  btn.type = "button";
  btn.append(icon("my_location"), el("span", null, s.wxUseLoc));
  btn.addEventListener("click", onGrant);
  box.appendChild(btn);
}

export function renderMessage(box, s, message) {
  box.replaceChildren(heading(s), el("p", "wx-row", message));
}

export function renderWeather(box, s, w) {
  const now = new Date();
  const first = w.windows[0];
  let verdict, tone;
  if (first && new Date(first.start) <= new Date(now.getTime() + 60 * 60 * 1000)) {
    const end = new Date(new Date(first.end).getTime() + 60 * 60 * 1000).toISOString();
    verdict = s.wxGoodNow(when(end, s, now, now));
    tone = "good";
  } else if (first) {
    const end = new Date(new Date(first.end).getTime() + 60 * 60 * 1000).toISOString();
    verdict = s.wxGoodAt(when(first.start, s, now), when(end, s, now, first.start));
    tone = "";
  } else {
    verdict = s.wxNoWindow;
    tone = "bad";
  }

  const pills = el("div", "wx-row");
  const risk = el("span", `wx-pill risk-${w.disease_risk}`);
  risk.append(icon("coronavirus"), el("span", null, s.wxRisk[w.disease_risk]));
  pills.appendChild(risk);
  if (w.rain.first_rain) {
    const rain = el("span", "wx-pill");
    rain.style.background = "#e3eefb";
    rain.style.color = "#1d4f91";
    rain.append(icon("rainy"), el("span", null, s.wxRainAt(when(w.rain.first_rain, s, now))));
    pills.appendChild(rain);
  }

  // One bar per forecast hour, starting now. Spray windows need 2+ hours, so a
  // lone "good" hour is drawn neutral to match the verdict above.
  const inWindow = (iso) => w.windows.some((x) => iso >= x.start && iso <= x.end);
  const hours = (w.hourly || []).slice(0, 48);
  const ribbon = el("div", "ribbon");
  for (const h of hours) {
    ribbon.appendChild(el("span", h.rain ? "rain" : h.good && inWindow(h.t) ? "good" : ""));
  }
  const fmt = new Intl.DateTimeFormat(s.locale, { hour: "numeric" });
  const axis = el("div", "ribbon-axis");
  for (const i of [0, 12, 24, 36, hours.length - 1]) {
    if (hours[i]) axis.appendChild(el("span", null, fmt.format(new Date(hours[i].t))));
  }

  const legend = el("div", "wx-legend");
  const g = el("span");
  const gi = el("i"); gi.style.background = "var(--leaf-2)";
  g.append(gi, s.wxLegendGood);
  const r = el("span");
  const ri = el("i"); ri.style.background = "var(--rain)";
  r.append(ri, s.wxLegendRain);
  legend.append(g, r);

  const c = w.current;
  box.replaceChildren(
    heading(s),
    el("p", `wx-verdict ${tone}`, verdict),
    pills,
    ribbon,
    axis,
    legend,
    el("p", "wx-row", s.wxNow(Math.round(c.temperature), Math.round(c.humidity), Math.round(c.wind))),
  );
}
