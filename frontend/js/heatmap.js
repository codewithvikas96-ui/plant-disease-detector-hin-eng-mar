/* Draws the Grad-CAM grid from /api/predict over the photo as a spotlight.

   The server sends only a 7x7 grid of 0..1 values plus the crop box the model
   saw, a few hundred bytes instead of an image. The browser paints the grid
   onto a 7x7 canvas and scales it up with image smoothing, which gives the
   soft edges for free.

   A colour scale is hard to read on dark foliage in sunlight, so instead the
   parts the model ignored are dimmed and the part it used stays bright, with
   a turmeric glow on the strongest spots: "the bright part is where it looked". */

const VEIL = [22, 16, 10];
const GLOW = [227, 162, 26];

function colour(v) {
  if (v > 0.72) return [...GLOW, Math.round(90 * (v - 0.72) / 0.28)];
  return [...VEIL, Math.round(175 * (1 - v) ** 1.6)];
}

/** Where an object-fit: contain image actually sits inside its box. */
function containedRect(box, naturalW, naturalH) {
  const scale = Math.min(box.width / naturalW, box.height / naturalH);
  const w = naturalW * scale;
  const h = naturalH * scale;
  return { x: (box.width - w) / 2, y: (box.height - h) / 2, w, h };
}

export function drawHeatmap(canvas, img, heatmap) {
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!heatmap?.grid?.length || !img.naturalWidth) return;

  const rows = heatmap.grid.length;
  const cols = heatmap.grid[0].length;
  const small = document.createElement("canvas");
  small.width = cols;
  small.height = rows;
  const sctx = small.getContext("2d");
  const pixels = sctx.createImageData(cols, rows);
  heatmap.grid.flat().forEach((v, i) => pixels.data.set(colour(v), i * 4));
  sctx.putImageData(pixels, 0, 0);

  const photo = containedRect(rect, img.naturalWidth, img.naturalHeight);
  const [bx, by, bw, bh] = heatmap.box;
  const x = (photo.x + bx * photo.w) * dpr;
  const y = (photo.y + by * photo.h) * dpr;
  const w = bw * photo.w * dpr;
  const h = bh * photo.h * dpr;
  // The margins the centre crop cut off were never seen: dim them fully.
  ctx.fillStyle = `rgba(${VEIL.join(",")}, 0.69)`;
  ctx.fillRect(photo.x * dpr, photo.y * dpr, photo.w * dpr, photo.h * dpr);
  ctx.clearRect(x, y, w, h);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(small, x, y, w, h);
}

export function clearHeatmap(canvas) {
  canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
}
