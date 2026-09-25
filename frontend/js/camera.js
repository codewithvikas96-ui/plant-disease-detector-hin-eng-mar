/* Live camera with framing guidance.

   Most bad diagnoses start as bad photos: too dark, too far, shaken. Before
   the farmer presses the shutter, four checks run on the square inside the
   guide frame, about four times a second, on a 96 px copy of the frame:

     light      mean brightness, and the share of blown-out pixels (glare)
     closeness  share of plant-coloured pixels (green, yellow or brown)
     steadiness difference from the previous frame
     sharpness  variance of the Laplacian, the standard focus measure

   The first failing check becomes the one instruction on screen, so the
   farmer is only ever asked to fix one thing at a time.

   getUserMedia needs HTTPS or localhost; elsewhere openCamera() returns false
   and the caller falls back to the phone's own camera app. */

const SIZE = 96;
const CHECK_MS = 250;

const LIMITS = {
  dark: 55,          // mean luma below this: too dark
  clipped: 0.25,     // more than this share of blown-out pixels: glare
  plant: 0.35,       // at least this share of the frame should be leaf
  motion: 16,        // mean abs difference between checks
  sharp: 60,         // Laplacian variance below this: blurry
};

let stream = null;
let timer = null;
let prev = null;
let goodStreak = 0;

const $ = (id) => document.getElementById(id);

export const cameraSupported = () =>
  !!(navigator.mediaDevices?.getUserMedia && window.isSecureContext);

/**
 * @param {{t: () => object, onCapture: (file: File) => void}} opts
 * @returns {Promise<boolean>} false if the camera could not be opened
 */
export async function openCamera({ t, onCapture }) {
  if (!cameraSupported()) return false;
  const view = $("camera");
  const video = $("camVideo");

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    });
  } catch {
    return false;
  }

  view.hidden = false;
  view.classList.remove("ready");
  setStatus("hourglass_top", t().camStarting);
  video.srcObject = stream;
  await video.play().catch(() => {});

  const track = stream.getVideoTracks()[0];
  const caps = track.getCapabilities?.() || {};
  const flash = $("camFlash");
  flash.hidden = !caps.torch;
  $("camSpacer").hidden = !!caps.torch;
  flash.classList.remove("on");
  flash.onclick = async () => {
    const on = !flash.classList.contains("on");
    try {
      await track.applyConstraints({ advanced: [{ torch: on }] });
      flash.classList.toggle("on", on);
    } catch { /* torch not actually controllable */ }
  };
  flash.setAttribute("aria-label", t().camFlash);
  $("camClose").setAttribute("aria-label", t().camClose);

  $("camClose").onclick = closeCamera;
  $("camShutter").onclick = async () => {
    const file = await grab(video);
    closeCamera();
    if (file) onCapture(file);
  };

  prev = null;
  goodStreak = 0;
  timer = setInterval(() => check(video, t), CHECK_MS);
  return true;
}

export function closeCamera() {
  clearInterval(timer);
  timer = null;
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  $("camVideo").srcObject = null;
  $("camera").hidden = true;
}

function setStatus(icon, text) {
  $("camIcon").textContent = icon;
  $("camText").textContent = text;
}

/** Full-resolution still of the current frame, as a JPEG file. */
async function grab(video) {
  if (!video.videoWidth) return null;
  const scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.9));
  return blob ? new File([blob], "leaf.jpg", { type: "image/jpeg" }) : null;
}

const probe = document.createElement("canvas");
probe.width = probe.height = SIZE;
const pctx = probe.getContext("2d", { willReadFrequently: true });

function check(video, t) {
  if (!video.videoWidth) return;
  // The guide frame is a centred square; read that same square.
  const side = Math.min(video.videoWidth, video.videoHeight) * 0.72;
  const sx = (video.videoWidth - side) / 2;
  const sy = (video.videoHeight - side) / 2 - video.videoHeight * 0.06;
  pctx.drawImage(video, sx, Math.max(0, sy), side, side, 0, 0, SIZE, SIZE);
  const frame = analyse(pctx.getImageData(0, 0, SIZE, SIZE).data, prev);
  prev = frame.gray;

  const s = t();
  const messages = {
    dark: ["dark_mode", s.camDark],
    bright: ["light_mode", s.camBright],
    far: ["zoom_in", s.camFar],
    shaky: ["vibration", s.camShaky],
    blurry: ["center_focus_weak", s.camBlurry],
  };
  const problem = frame.problem && messages[frame.problem];

  // Require a few good checks in a row so the badge does not flicker.
  goodStreak = problem ? 0 : goodStreak + 1;
  const ready = goodStreak >= 3;
  $("camera").classList.toggle("ready", ready);
  if (ready) setStatus("check_circle", s.camReady);
  else if (problem) setStatus(...problem);
}

/**
 * The four checks on one SIZE x SIZE RGBA frame. Pure, so it can be tested
 * on still images. `problem` is the first check that fails, or null.
 */
export function analyse(data, prevGray = null) {
  const gray = new Float32Array(SIZE * SIZE);
  let sum = 0;
  let plant = 0;
  let clipped = 0;
  for (let i = 0, p = 0; i < data.length; i += 4, p++) {
    const r = data[i], g = data[i + 1], b = data[i + 2];
    const y = 0.299 * r + 0.587 * g + 0.114 * b;
    gray[p] = y;
    sum += y;
    // Sun glare saturates channels long before it lifts the average much.
    if (Math.max(r, g, b) >= 250) clipped++;
    if (isPlant(r, g, b)) plant++;
  }
  const mean = sum / gray.length;
  const plantShare = plant / gray.length;
  const clippedShare = clipped / gray.length;

  let motion = 0;
  if (prevGray) {
    for (let i = 0; i < gray.length; i++) motion += Math.abs(gray[i] - prevGray[i]);
    motion /= gray.length;
  }
  const sharp = laplacianVariance(gray);

  let problem = null;
  if (mean < LIMITS.dark) problem = "dark";
  else if (clippedShare > LIMITS.clipped) problem = "bright";
  else if (plantShare < LIMITS.plant) problem = "far";
  else if (motion > LIMITS.motion) problem = "shaky";
  else if (sharp < LIMITS.sharp) problem = "blurry";
  return { gray, mean, plantShare, clippedShare, motion, sharp, problem };
}

export const FRAME_SIZE = SIZE;

/** Leaf-coloured: green through yellow to brown, reasonably saturated. */
function isPlant(r, g, b) {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const v = max / 255;
  const sat = max ? (max - min) / max : 0;
  if (v < 0.12 || sat < 0.18) return false;
  let h;
  if (max === r) h = ((g - b) / (max - min)) * 60;
  else if (max === g) h = (2 + (b - r) / (max - min)) * 60;
  else h = (4 + (r - g) / (max - min)) * 60;
  if (h < 0) h += 360;
  return h >= 18 && h <= 170;
}

function laplacianVariance(gray) {
  let n = 0, mean = 0, m2 = 0;
  for (let y = 1; y < SIZE - 1; y++) {
    for (let x = 1; x < SIZE - 1; x++) {
      const i = y * SIZE + x;
      const lap = gray[i - SIZE] + gray[i + SIZE] + gray[i - 1] + gray[i + 1] - 4 * gray[i];
      n++;
      const d = lap - mean;
      mean += d / n;
      m2 += d * (lap - mean);
    }
  }
  return m2 / n;
}
