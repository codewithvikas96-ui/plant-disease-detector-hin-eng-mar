/* Plant Disease Advisory — PWA front end.
   Scan (camera guide, diagnosis, heatmap, AI second opinion, cost, spray
   timing, chat), History and the outbreak Map. */

import { UI } from "./i18n.js";
import { drawHeatmap, clearHeatmap } from "./heatmap.js";
import { cameraSupported, openCamera } from "./camera.js";
import { listScans, saveScan, clearScans, scanRow } from "./history.js";
import {
  savedLocation, requestLocation, fetchWeather,
  renderWeather, renderLocationPrompt, renderMessage,
} from "./weather.js";
import { showMap, nearbyOutbreak } from "./map.js";

const API = ""; // same origin; set to "http://192.168.x.x:8000" only for a split dev setup

// English on first visit; after that, whatever the farmer last picked.
let lang = load("lang") || "en";
let selectedFile = null;
let lastUpload = null;   // the downscaled image, reused for the AI second opinion
let lastResult = null;   // the advisory currently on screen
let resultMode = null;   // "photo" (CNN on a photo) or "advisory" (history / AI-identified)
let resultPhotoUrl = null;
let aiEnabled = false;
let health = null;
let chat = [];
let chatBusy = false;
let opinionSeq = 0;
let lastOpinion = null;
let acres = Number(load("acres")) || 1;
let mapDays = 30;
let classNames = {};     // class_name -> {crop, disease} in the current language

const $ = (id) => document.getElementById(id);
const t = () => UI[lang];

function load(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function store(key, value) {
  try { localStorage.setItem(key, value); } catch { /* per-session only */ }
}

/* ------------------------------------------------------------- tabs */
function showView(name) {
  for (const v of ["scan", "history", "map"]) $(`view-${v}`).hidden = v !== name;
  document.querySelectorAll(".tab").forEach((b) => {
    const on = b.dataset.view === name;
    b.classList.toggle("is-active", on);
    if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  if (name === "history") renderHistory();
  if (name === "map") refreshMap();
  window.scrollTo({ top: 0 });
}
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
$("seeAllBtn").addEventListener("click", () => showView("history"));

/* ------------------------------------------------------------ language */
async function applyLanguage() {
  const s = t();
  document.documentElement.lang = s.htmlLang;
  // Keep the English name alongside, so the tab is recognisable in any language.
  document.title = lang === "en" ? s.title : `${s.title} | Plant Disease Detector`;

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const v = s[el.dataset.i18n];
    if (typeof v === "string") el.textContent = v;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = s[el.dataset.i18nPlaceholder];
  });
  $("micBtn").setAttribute("aria-label", s.micLabel);
  $("sendBtn").setAttribute("aria-label", s.sendLabel);
  $("cameraBtn").setAttribute("aria-label", s.takePhoto);
  document.querySelectorAll("#mapDays button").forEach((b) => { b.textContent = s.mapDays(b.dataset.days); });
  document.querySelectorAll(".lang-btn").forEach((b) => b.classList.toggle("is-active", b.dataset.lang === lang));

  renderSuggestions();
  renderFooter();
  await loadClassNames();
  renderRecent();
  refreshHomeWeather();
  refreshNearby();
  if (!$("view-history").hidden) renderHistory();
  if (!$("view-map").hidden) refreshMap();

  // Re-fetch the advisory in the new language so the whole result switches.
  if (lastResult) {
    if (resultMode === "photo" && selectedFile) diagnose();
    else openAdvisory(lastResult.prediction.class_name, { photoUrl: resultPhotoUrl, source: lastResult.source });
  }
}

document.querySelectorAll(".lang-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    stopSpeaking();
    lang = btn.dataset.lang;
    store("lang", lang);
    applyLanguage();
  });
});

async function loadClassNames() {
  try {
    const res = await fetch(`${API}/api/classes?lang=${lang}`);
    const data = await res.json();
    classNames = Object.fromEntries(data.classes.map((c) => [c.class_name, c]));
  } catch { /* history falls back to the label saved with each scan */ }
}

function labelFor(className, fallback) {
  const c = classNames[className];
  if (!c) return fallback || className.replace(/_+/g, " ");
  return c.healthy ? `${c.crop} — ${t().healthy}` : `${c.crop} — ${c.disease}`;
}

/* --------------------------------------------------------- image input */
$("cameraBtn").addEventListener("click", async () => {
  const opened = cameraSupported() && await openCamera({ t, onCapture: (f) => onImageChosen(f, true) });
  if (!opened) {
    if (cameraSupported()) setBanner(t().camDenied);
    $("fileInput").click(); // the phone's own camera app
  }
});

["fileInput", "galleryInput"].forEach((id) => {
  $(id).addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (file) onImageChosen(file, id === "fileInput");
    e.target.value = ""; // allow re-picking the same file
  });
});

function onImageChosen(file, fromCamera = false) {
  showView("scan");
  selectedFile = file;
  lastResult = null;
  resetChat();
  if (resultPhotoUrl) URL.revokeObjectURL(resultPhotoUrl);
  resultPhotoUrl = URL.createObjectURL(file);
  $("preview").src = resultPhotoUrl;
  $("home").hidden = true;
  $("previewSection").hidden = false;
  $("result").hidden = true;
  $("error").hidden = true;
  // A photo from the guided camera was already checked; go straight on.
  if (fromCamera) diagnose();
  else $("previewSection").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* Shrink before upload: a 4 MB phone photo becomes ~150 KB, which matters a lot
   on a 2G/3G village connection. The model only sees 224px anyway. */
async function downscale(file, maxSide = 720, quality = 0.85) {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.size < 900_000) return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close?.();
    const blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", quality));
    return blob ? new File([blob], "leaf.jpg", { type: "image/jpeg" }) : file;
  } catch {
    return file; // createImageBitmap can fail on HEIC; let the server try
  }
}

/* ----------------------------------------------------------- diagnosis */
$("diagnoseBtn").addEventListener("click", diagnose);
$("againBtn").addEventListener("click", goHome);

function goHome() {
  stopSpeaking();
  selectedFile = null;
  lastResult = null;
  resultMode = null;
  resetChat();
  $("previewSection").hidden = true;
  $("result").hidden = true;
  $("error").hidden = true;
  $("home").hidden = false;
  renderRecent();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function diagnose() {
  if (!selectedFile) return;
  if (!navigator.onLine) return showError(t().offline);

  stopSpeaking();
  $("loading").hidden = false;
  $("result").hidden = true;
  $("error").hidden = true;
  const firstTime = !lastResult; // language switches re-run this; save only once

  try {
    const upload = await downscale(selectedFile);
    const form = new FormData();
    form.append("file", upload, "leaf.jpg");
    const res = await fetch(`${API}/api/predict?lang=${lang}`, { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      if (res.status === 503) throw new Error(t().errNoModel);
      throw new Error(detail.detail || t().errGeneric);
    }

    lastUpload = upload;
    lastResult = await res.json();
    resultMode = "photo";
    $("previewSection").hidden = true;
    render(lastResult, { photoUrl: resultPhotoUrl });
    if (aiEnabled) secondOpinion(lastResult, upload);

    if (firstTime) {
      const p = lastResult.prediction;
      saveScan(selectedFile, {
        class_name: p.class_name, confidence: p.confidence, severity: p.severity,
        label: labelFor(p.class_name, `${p.crop} — ${p.disease}`),
        unknown: !!lastResult.unknown?.is_unknown, source: "cnn",
      });
      if (!lastResult.low_confidence) reportToMap(p.class_name, "cnn");
    }
  } catch (err) {
    showError(err instanceof TypeError ? t().errNetwork : err.message);
  } finally {
    $("loading").hidden = true;
  }
}

/** Advisory without a new photo: reopening history, or a crop only the AI knows. */
async function openAdvisory(className, { photoUrl = null, source = "cnn" } = {}) {
  stopSpeaking();
  $("home").hidden = true;
  $("previewSection").hidden = true;
  $("error").hidden = true;
  $("loading").hidden = false;
  try {
    const res = await fetch(`${API}/api/advisory/${encodeURIComponent(className)}?lang=${lang}`);
    if (!res.ok) throw new Error(t().errGeneric);
    lastResult = { ...(await res.json()), source };
    resultMode = "advisory";
    resultPhotoUrl = photoUrl;
    render(lastResult, { photoUrl });
  } catch (err) {
    showError(err instanceof TypeError ? t().errNetwork : err.message);
    $("home").hidden = false;
  } finally {
    $("loading").hidden = true;
  }
}

function render(data, { photoUrl }) {
  const s = t();
  const p = data.prediction;
  const sev = p.severity || "unknown";

  // Hero photo + heatmap
  const img = $("resultPhoto");
  const wrap = $("photoWrap");
  wrap.hidden = !photoUrl;
  clearHeatmap($("heatCanvas"));
  $("heatBar").hidden = !data.heatmap;
  if (photoUrl) {
    img.onload = () => data.heatmap && drawHeatmap($("heatCanvas"), img, data.heatmap);
    img.src = photoUrl;
  }
  wrap.classList.toggle("heat-off", !$("heatToggle").checked);

  $("diagnosis").className = `diagnosis sev-${sev}`;
  $("sourceBadge").hidden = data.source !== "vision";
  $("cropName").textContent = p.crop;
  $("diseaseName").textContent = p.healthy ? s.healthy : p.disease;
  const chip = $("severityChip");
  chip.textContent = s.severity[sev] || sev;
  chip.className = `chip sev-${sev}`;

  const hasConf = typeof p.confidence === "number";
  $("confidence").hidden = !hasConf;
  if (hasConf) {
    const pct = Math.round(p.confidence * 100);
    $("confidenceFill").style.width = `${pct}%`;
    $("confidenceFill").style.background =
      pct >= 80 ? "var(--leaf-2)" : pct >= 60 ? "var(--haldi)" : "var(--kumkum)";
    $("confidenceText").textContent = `${s.confidence} ${pct}%`;
  }

  const unknown = !!data.unknown?.is_unknown;
  $("unknownNote").hidden = !unknown;
  // A name the model cannot stand behind should not look like a verdict.
  $("diagnosis").classList.toggle("is-unknown", unknown);
  $("lowConfNote").hidden = !data.low_confidence || unknown;
  $("lowConfText").textContent = s.lowConf;

  $("symptoms").textContent = p.symptoms;
  $("remedy").textContent = p.remedy;
  $("prevention").textContent = p.prevention;
  $("pathogen").textContent = p.pathogen && p.pathogen !== "None" ? p.pathogen : "";
  $("disclaimer").textContent = data.disclaimer;

  const alts = data.alternatives || [];
  $("altBox").hidden = alts.length === 0;
  $("altList").replaceChildren(...alts.map((a) => {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = a.healthy ? `${a.crop} — ${s.healthy}` : `${a.crop} — ${a.disease}`;
    const pct = document.createElement("span");
    pct.textContent = `${Math.round(a.confidence * 100)}%`;
    li.append(name, pct);
    return li;
  }));

  renderCost(data.advice);
  $("aiCheck").hidden = true;
  $("aiChat").hidden = !aiEnabled;
  refreshResultWeather(p);

  setSpeaking(false);
  $("result").hidden = false;
  $("result").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("heatToggle").addEventListener("change", (e) => {
  $("photoWrap").classList.toggle("heat-off", !e.target.checked);
});
window.addEventListener("resize", () => {
  if (lastResult?.heatmap && !$("result").hidden) drawHeatmap($("heatCanvas"), $("resultPhoto"), lastResult.heatmap);
});

function showError(msg) {
  $("errorText").textContent = msg;
  $("error").hidden = false;
}

/* ------------------------------------------------------ cost per acre */
const rupees = (n) => new Intl.NumberFormat(t().locale, { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);

function billRows(items) {
  return items.map((item) => {
    const li = document.createElement("li");
    const left = document.createElement("span");
    const prod = document.createElement("span");
    prod.className = "prod";
    prod.textContent = item.product;
    const qty = document.createElement("span");
    qty.className = "qty";
    // A ready-mixed spray such as Bordeaux 1% is the spray itself: show the volume only.
    qty.textContent = item.unit === "l"
      ? `${Math.round(item.qty_per_acre * acres)} L`
      : `${item.dose} ${item.unit}/L · ${formatQty(item.qty_per_acre * acres, item.unit)}`;
    left.append(prod, qty);
    const lead = document.createElement("span");
    lead.className = "lead";
    const price = document.createElement("span");
    price.className = "price";
    price.textContent = item.cost_per_acre != null ? rupees(item.cost_per_acre * acres) : "—";
    li.append(left, lead, price);
    return li;
  });
}

function formatQty(q, unit) {
  if (unit === "g" && q >= 1000) return `${+(q / 1000).toFixed(2)} kg`;
  if (unit === "ml" && q >= 1000) return `${+(q / 1000).toFixed(2)} L`;
  return `${Math.round(q)} ${unit}`;
}

function renderCost(adv) {
  const card = $("costCard");
  card.hidden = !adv;
  if (!adv) return;
  const s = t();
  $("acreValue").textContent = acres;
  $("billSub").textContent = s.perSpray(adv.spray_litres_per_acre);
  const chem = adv.chemical || [];
  $("billList").replaceChildren(...(chem.length ? billRows(chem) : [Object.assign(document.createElement("li"), { textContent: s.noProduct })]));
  document.querySelector(".bill-choose").hidden = chem.length < 2;
  $("organicBlock").hidden = !adv.organic;
  if (adv.organic) {
    $("organicText").textContent = adv.organic.text;
    $("organicList").replaceChildren(...billRows(adv.organic.items));
  }
}

function setAcres(n) {
  acres = Math.min(100, Math.max(0.5, n));
  store("acres", acres);
  if (lastResult) renderCost(lastResult.advice);
}
$("acreMinus").addEventListener("click", () => setAcres(acres <= 1 ? 0.5 : acres - 1));
$("acrePlus").addEventListener("click", () => setAcres(acres < 1 ? 1 : acres + 1));

/* ------------------------------------------------------------ weather */
async function withWeather(box, onReady) {
  const s = t();
  const loc = savedLocation();
  if (!loc) {
    renderLocationPrompt(box, s, async () => {
      try {
        await requestLocation();
        refreshHomeWeather();
        refreshNearby();
        if (lastResult) refreshResultWeather(lastResult.prediction);
      } catch (err) {
        renderMessage(box, s, err.message === "https" ? s.wxLocHttps : s.wxLocDenied);
      }
    });
    return;
  }
  try {
    const w = await fetchWeather(API, loc);
    renderWeather(box, s, w);
    onReady?.(w);
  } catch {
    renderMessage(box, s, s.wxError);
  }
}

function refreshHomeWeather() {
  withWeather($("weatherHome"));
}

function refreshResultWeather(p) {
  const box = $("weatherResult");
  // Spray timing only matters when there is something to spray.
  if (p.healthy || !(lastResult?.advice?.chemical?.length || lastResult?.advice?.organic)) {
    box.replaceChildren();
    return;
  }
  withWeather(box);
}

async function refreshNearby() {
  const loc = savedLocation();
  $("nearbyAlert").hidden = true;
  if (!loc) return;
  try {
    const near = await nearbyOutbreak(API, lang, loc);
    if (near) {
      $("nearbyText").textContent = t().mapNearby(near.count, near.label);
      $("nearbyAlert").hidden = false;
    }
  } catch { /* no alert */ }
}

/* ------------------------------------------------------------ history */
const dateFmt = () => new Intl.DateTimeFormat(t().locale, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

function rowFor(scan) {
  return scanRow(scan, {
    label: labelFor(scan.class_name, scan.label),
    when: dateFmt().format(new Date(scan.ts)),
    onOpen: (sc) => { showView("scan"); resetChat(); openAdvisory(sc.class_name, { photoUrl: sc.thumb, source: sc.source }); },
  });
}

function renderRecent() {
  const scans = listScans().slice(0, 3);
  $("recentBlock").hidden = scans.length === 0;
  $("recentList").replaceChildren(...scans.map(rowFor));
}

function renderHistory() {
  const scans = listScans();
  $("historyList").replaceChildren(...scans.map(rowFor));
  $("historyEmpty").hidden = scans.length > 0;
  $("clearHistoryBtn").hidden = scans.length === 0;
}

$("clearHistoryBtn").addEventListener("click", () => {
  if (!confirm(t().histClearConfirm)) return;
  clearScans();
  renderHistory();
  renderRecent();
});

/* ---------------------------------------------------------------- map */
const sharing = () => load("share.v1") === "1";
$("shareToggle").checked = sharing();
$("shareToggle").addEventListener("change", async (e) => {
  if (e.target.checked && !savedLocation()) {
    try {
      await requestLocation();
    } catch (err) {
      e.target.checked = false;
      setBanner(err.message === "https" ? t().wxLocHttps : t().wxLocDenied, true);
      return;
    }
  }
  store("share.v1", e.target.checked ? "1" : "0");
  refreshHomeWeather();
});

document.querySelectorAll("#mapDays button").forEach((b) => b.addEventListener("click", () => {
  mapDays = Number(b.dataset.days);
  document.querySelectorAll("#mapDays button").forEach((x) => x.classList.toggle("is-active", x === b));
  refreshMap();
}));

function refreshMap() {
  showMap({ api: API, lang, days: mapDays, s: t(), home: savedLocation(), status: $("mapStatus") });
}

async function reportToMap(className, source) {
  const loc = savedLocation();
  if (!sharing() || !loc) return;
  try {
    await fetch(`${API}/api/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ class_name: className, lat: loc.lat, lon: loc.lon, source }),
    });
  } catch { /* the map is a bonus */ }
}

/* ------------------------------------------------------ AI second opinion */
/* The CNN answers instantly; this runs afterwards so it never slows the main
   result down. If it fails, the box simply stays hidden. */
async function secondOpinion(data, upload) {
  const seq = ++opinionSeq;
  lastOpinion = null;
  const box = $("aiCheck");
  box.className = "ai-check is-loading";
  $("aiCheckText").textContent = t().aiChecking;
  $("aiCheckTip").hidden = true;
  $("extendedBtn").hidden = true;
  box.hidden = false;

  try {
    const form = new FormData();
    form.append("file", upload, "leaf.jpg");
    const cls = encodeURIComponent(data.prediction.class_name);
    const res = await fetch(`${API}/api/ai/second-opinion?lang=${lang}&cnn_class=${cls}`, { method: "POST", body: form });
    if (!res.ok) throw new Error(res.status);
    const o = await res.json();
    if (seq !== opinionSeq) return; // a newer photo or language replaced this one
    lastOpinion = o;

    const s = t();
    const text = {
      agrees: s.aiAgrees,
      disagrees: s.aiDisagrees(o.best_match_label || ""),
      extended: s.aiExtended(o.best_match_label || ""),
      unknown: s.aiUnknown,
      not_leaf: s.aiNotLeaf,
    }[o.verdict];
    box.className = `ai-check verdict-${o.verdict === "extended" ? "disagrees" : o.verdict}`;
    $("aiCheckText").textContent = text || s.aiUnknown;

    const tip = s.quality[o.quality_issue];
    $("aiCheckTip").hidden = !tip || o.verdict === "agrees";
    $("aiCheckTip").textContent = tip || "";

    // The CNN cannot name this crop at all, so offer the AI's advisory.
    const ext = $("extendedBtn");
    ext.hidden = o.verdict !== "extended";
    ext.onclick = () => {
      const photo = resultPhotoUrl;
      resetChat();
      openAdvisory(o.best_match, { photoUrl: photo, source: "vision" });
      saveScan(selectedFile, {
        class_name: o.best_match, confidence: null,
        severity: null, label: o.best_match_label, source: "vision",
      });
      reportToMap(o.best_match, "vision");
    };
  } catch {
    if (seq === opinionSeq) box.hidden = true;
  }
}

/* ------------------------------------------------------------ AI chat */
function resetChat() {
  chat = [];
  opinionSeq++;
  lastOpinion = null;
  $("chatLog").replaceChildren();
  $("chatInput").value = "";
  setChatStatus("");
}

function renderSuggestions() {
  $("chatSuggestions").replaceChildren(...t().suggestions.map((q) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip-btn";
    b.textContent = q;
    b.addEventListener("click", () => sendChat(q));
    return b;
  }));
}

function setChatStatus(msg, isError = false) {
  const el = $("chatStatus");
  el.hidden = !msg;
  el.textContent = msg;
  el.classList.toggle("error", isError);
}

function addBubble(role, text) {
  const wrap = document.createElement("div");
  wrap.className = `bubble ${role}`;
  const body = document.createElement("p");
  body.textContent = text;
  wrap.appendChild(body);
  $("chatLog").appendChild(wrap);
  wrap.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return wrap;
}

function addBubbleSpeaker(wrap, text) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "bubble-speak";
  btn.setAttribute("aria-label", t().listen);
  btn.innerHTML = '<span class="ms fill" aria-hidden="true">volume_up</span>';
  btn.addEventListener("click", () => toggleSpeak(text, btn));
  wrap.appendChild(btn);
  return btn;
}

/* The model is told to answer in plain text because answers are read aloud,
   but strip stray markdown anyway so TTS never says "asterisk". */
const tidy = (text) => text.replace(/\*\*|__|`/g, "").replace(/^#+\s*/gm, "").trim();

$("chatForm").addEventListener("submit", (e) => {
  e.preventDefault();
  sendChat($("chatInput").value);
});

async function sendChat(text, { viaVoice = false } = {}) {
  text = (text || "").trim();
  if (!text || chatBusy || !lastResult) return;
  if (!navigator.onLine) return setChatStatus(t().offline, true);

  chatBusy = true;
  stopSpeaking();
  setChatStatus("");
  $("chatInput").value = "";
  $("sendBtn").disabled = true;

  chat.push({ role: "user", content: text });
  const userBubble = addBubble("user", text);
  const reply = addBubble("assistant", t().thinking);
  reply.classList.add("pending");
  const replyText = reply.querySelector("p");

  const p = lastResult.prediction;
  const loc = savedLocation();
  try {
    const res = await fetch(`${API}/api/ai/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lang,
        messages: chat.slice(-12),
        class_name: p.class_name,
        confidence: p.confidence,
        low_confidence: !!lastResult.low_confidence,
        alternatives: (lastResult.alternatives || []).map((a) => a.class_name),
        vision_match: lastOpinion?.verdict === "disagrees" ? lastOpinion.best_match : null,
        lat: loc?.lat ?? null,
        lon: loc?.lon ?? null,
      }),
    });
    if (!res.ok) throw new Error(res.status === 429 ? t().errBusy : t().errAI);

    // Stream the answer in as it is generated.
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let answer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      answer += decoder.decode(value, { stream: true });
      reply.classList.remove("pending");
      replyText.textContent = answer;
      reply.scrollIntoView({ block: "nearest" });
    }
    answer = tidy(answer + decoder.decode());
    if (!answer) throw new Error(t().errAI);

    replyText.textContent = answer;
    chat.push({ role: "assistant", content: answer });
    const speaker = addBubbleSpeaker(reply, answer);
    // Someone who asked by voice may not be able to read the answer either.
    if (viaVoice) toggleSpeak(answer, speaker);
  } catch (err) {
    chat.pop();
    userBubble.remove();
    reply.remove();
    $("chatInput").value = text;
    setChatStatus(err instanceof TypeError ? t().errNetwork : err.message || t().errAI, true);
  } finally {
    chatBusy = false;
    $("sendBtn").disabled = false;
  }
}

/* -------------------------------------------------------- voice question */
/* getUserMedia only exists on HTTPS or localhost, so the mic stays hidden on a
   plain http://192.168.x.x LAN address. The Cloudflare tunnel URL is HTTPS. */
const canRecord = !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
let recorder = null;
let recordTimer = null;

$("micBtn").addEventListener("click", async () => {
  if (recorder?.state === "recording") return recorder.stop();
  if (chatBusy) return;

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    return setChatStatus(t().errMic, true);
  }

  stopSpeaking();
  const chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  recorder.onstop = () => {
    clearTimeout(recordTimer);
    stream.getTracks().forEach((track) => track.stop());
    $("micBtn").classList.remove("recording");
    const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
    recorder = null;
    if (blob.size < 2000) return setChatStatus(t().errHeard, true); // a tap, not speech
    transcribeAndAsk(blob);
  };
  recorder.start();
  $("micBtn").classList.add("recording");
  setChatStatus(t().recording);
  recordTimer = setTimeout(() => recorder?.state === "recording" && recorder.stop(), 30_000);
});

async function transcribeAndAsk(blob) {
  setChatStatus(t().transcribing);
  $("micBtn").disabled = true;
  try {
    const type = blob.type.split(";")[0];
    const ext = { "audio/mp4": "mp4", "audio/ogg": "ogg", "audio/mpeg": "mp3" }[type] || "webm";
    const form = new FormData();
    form.append("file", blob, `question.${ext}`);
    const res = await fetch(`${API}/api/ai/transcribe?lang=${lang}`, { method: "POST", body: form });
    if (!res.ok) throw new Error(res.status === 429 ? t().errBusy : t().errAI);
    const { text } = await res.json();
    if (!text) throw new Error(t().errHeard);
    setChatStatus("");
    await sendChat(text, { viaVoice: true });
  } catch (err) {
    setChatStatus(err instanceof TypeError ? t().errNetwork : err.message, true);
  } finally {
    $("micBtn").disabled = false;
  }
}

/* --------------------------------------------------------------- voice */
/* Browser speech is instant and works offline, but almost no Android phone
   ships a Marathi (mr-IN) voice, so we fall back to the server's gTTS. */
const audio = $("ttsAudio");
let speaking = false;
let activeSpeakBtn = $("speakBtn");

$("speakBtn").addEventListener("click", () => {
  if (lastResult?.speech_text) toggleSpeak(lastResult.speech_text, $("speakBtn"));
});

function toggleSpeak(text, btn) {
  const wasThisOne = speaking && activeSpeakBtn === btn;
  stopSpeaking();
  if (!wasThisOne) speak(text, btn);
}

function findVoice(target) {
  const voices = speechSynthesis.getVoices();
  return (
    voices.find((v) => v.lang.replace("_", "-") === target) ||
    voices.find((v) => v.lang.replace("_", "-").startsWith(target.split("-")[0]))
  );
}

async function speak(text, btn = $("speakBtn")) {
  activeSpeakBtn = btn;
  setSpeaking(true);
  const voice = "speechSynthesis" in window ? findVoice(t().speechLang) : null;
  if (voice) {
    const utter = new SpeechSynthesisUtterance(text);
    utter.voice = voice;
    utter.lang = voice.lang;
    utter.rate = 0.9; // slightly slow — these are instructions to act on
    utter.onend = () => setSpeaking(false);
    utter.onerror = (e) => {
      // cancel() from the Stop button also lands here; that is not a failure.
      if (e.error === "interrupted" || e.error === "canceled") return setSpeaking(false);
      serverSpeak(text);
    };
    speechSynthesis.cancel();
    speechSynthesis.speak(utter);
  } else {
    await serverSpeak(text);
  }
}

async function serverSpeak(text) {
  const btn = activeSpeakBtn;
  if (btn === $("speakBtn")) $("speakLabel").textContent = t().loading;
  btn.disabled = true;
  try {
    const res = await fetch(`${API}/api/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text.slice(0, 2000), lang }),
    });
    if (!res.ok) throw new Error("tts failed");
    if (activeSpeakBtn !== btn) return;
    const url = URL.createObjectURL(await res.blob());
    audio.src = url;
    audio.onended = () => { setSpeaking(false); URL.revokeObjectURL(url); };
    audio.onerror = () => { setSpeaking(false); showError(t().errSpeech); };
    await audio.play();
    setSpeaking(true);
  } catch {
    setSpeaking(false);
    showError(t().errSpeech);
  } finally {
    btn.disabled = false;
  }
}

function setSpeaking(on) {
  speaking = on;
  const btn = activeSpeakBtn;
  btn.classList.toggle("speaking", on);
  btn.disabled = false;
  const iconEl = btn.querySelector(".ms");
  if (iconEl) iconEl.textContent = on ? "stop_circle" : "volume_up";
  if (btn === $("speakBtn")) $("speakLabel").textContent = on ? t().stop : t().listen;
}

function stopSpeaking() {
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  audio.pause();
  audio.currentTime = 0;
  setSpeaking(false);
}

if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = () => {};

/* --------------------------------------------------------- status/boot */
function setBanner(msg, isError = false) {
  const b = $("banner");
  b.hidden = !msg;
  b.textContent = msg || "";
  b.classList.toggle("error", isError);
}

async function checkHealth() {
  try {
    const res = await fetch(`${API}/api/health`);
    health = await res.json();
    aiEnabled = !!health.ai?.enabled;
    $("micBtn").hidden = !(aiEnabled && canRecord);
    if (!health.model_loaded) return setBanner(t().errNoModel, true);
    setBanner("");
    renderFooter();
  } catch {
    setBanner(t().errNetwork, true);
  }
}

function renderFooter() {
  if (!health?.model_loaded) return;
  const field = health.metrics?.field_accuracy;
  $("modelInfo").textContent =
    t().modelInfo(health.num_classes, typeof field === "number" ? `${(field * 100).toFixed(0)}%` : "") +
    (aiEnabled ? ` · ${t().aiOn}` : "");
}

window.addEventListener("online", () => { setBanner(""); checkHealth(); });
window.addEventListener("offline", () => setBanner(t().offline));

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}

checkHealth().then(applyLanguage);
