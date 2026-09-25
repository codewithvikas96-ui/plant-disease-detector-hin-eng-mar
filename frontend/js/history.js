/* Scan history, kept on the phone only.

   Each entry stores a 160 px thumbnail and the class name, not the advisory
   text, so reopening a scan re-fetches the advice in whatever language the
   farmer uses now. localStorage can be missing or full (private mode, old
   phones), so every access is wrapped and the app works without it. */

const KEY = "scans.v1";
const MAX = 40;

function read() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || [];
  } catch {
    return [];
  }
}

function write(list) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
    return true;
  } catch {
    return false;
  }
}

export function listScans() {
  return read();
}

export async function saveScan(file, entry) {
  const thumb = await thumbnail(file).catch(() => null);
  const list = read();
  list.unshift({ id: Date.now(), ts: Date.now(), thumb, ...entry });
  list.length = Math.min(list.length, MAX);
  // Quota errors: drop the oldest until it fits.
  while (!write(list) && list.length > 1) list.pop();
}

export function clearScans() {
  try { localStorage.removeItem(KEY); } catch { /* nothing stored */ }
}

async function thumbnail(file, side = 160) {
  const bitmap = await createImageBitmap(file);
  const scale = side / Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = side;
  const w = bitmap.width * scale;
  const h = bitmap.height * scale;
  canvas.getContext("2d").drawImage(bitmap, (side - w) / 2, (side - h) / 2, w, h);
  bitmap.close?.();
  return canvas.toDataURL("image/jpeg", 0.7);
}

/** One list row. Built with DOM calls, never innerHTML, since labels come from the server. */
export function scanRow(scan, { label, when, onOpen }) {
  const li = document.createElement("li");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "scan-item";
  btn.addEventListener("click", () => onOpen(scan));

  const img = document.createElement("img");
  img.alt = "";
  if (scan.thumb) img.src = scan.thumb;

  const meta = document.createElement("span");
  meta.className = "meta";
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = label;
  const sub = document.createElement("span");
  sub.className = "sub";
  sub.textContent = when;
  name.style.display = sub.style.display = "block";
  meta.append(name, sub);

  const dot = document.createElement("span");
  dot.className = `sev-dot sev-${scan.severity || "unknown"}`;

  btn.append(img, meta, dot);
  li.appendChild(btn);
  return li;
}
