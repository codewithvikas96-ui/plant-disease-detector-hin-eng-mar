# API reference

Base URL: the server itself (`http://localhost:8000`, the LAN address, or the tunnel URL).
Interactive docs with a "Try it out" button: **`/docs`** (Swagger UI).

All endpoints are under `/api`. Responses are JSON unless stated. Errors use FastAPI's shape:
`{"detail": "message"}`.

Common parameter: **`lang`** — `mr` (default), `hi` or `en`. It selects the language of every
text field in the response.

| Endpoint | Method | Purpose | Needs internet |
|---|---|---|---|
| [`/api/health`](#get-apihealth) | GET | Model and feature status | No |
| [`/api/classes`](#get-apiclasses) | GET | Every crop/disease the app can name | No |
| [`/api/predict`](#post-apipredict) | POST | Diagnose a leaf photo | No |
| [`/api/advisory/{class}`](#get-apiadvisoryclass_name) | GET | Advisory for a class, no photo | No |
| [`/api/tts`](#post-apitts) | POST | Speech MP3 for Marathi/Hindi | Yes |
| [`/api/weather`](#get-apiweather) | GET | Spray windows and disease risk | Yes |
| [`/api/report`](#post-apireport) | POST | Add an anonymous outbreak report | No |
| [`/api/outbreaks`](#get-apioutbreaks) | GET | Outbreak map data | No |
| [`/api/ai/second-opinion`](#post-apiaisecond-opinion) | POST | Vision-model check of the photo | Yes, Groq key |
| [`/api/ai/chat`](#post-apiaichat) | POST | Follow-up questions, streamed | Yes, Groq key |
| [`/api/ai/transcribe`](#post-apiaitranscribe) | POST | Speech to text | Yes, Groq key |

---

## Diagnosis

### `GET /api/health`

```json
{
  "status": "ok",
  "model_loaded": true,
  "arch": "mobilenet_v3_large",
  "num_classes": 38,
  "metrics": { "field_accuracy": 0.665, "field_top3": 0.877, "lab_accuracy": 0.987, "temperature": 0.773, "...": "..." },
  "languages": ["mr", "hi", "en"],
  "confidence_threshold": 0.6,
  "ai": {
    "enabled": true,
    "chat_model": "openai/gpt-oss-120b",
    "vision_model": "qwen/qwen3.8-27b",
    "stt_model": "whisper-large-v3-turbo"
  },
  "features": { "heatmap": true, "unknown_detection": true, "calibrated": true }
}
```

`features.unknown_detection` and `calibrated` are true only with a checkpoint from
`training/finetune_field.py`. The LAN address is deliberately **not** returned here (the
tunnel would publish it); the server prints it to the console instead.

### `GET /api/classes`

| Query | Type | Default |
|---|---|---|
| `lang` | `mr` \| `hi` \| `en` | `mr` |

```json
{
  "count": 53,
  "language": "en",
  "classes": [
    { "class_name": "Apple___Apple_scab", "crop": "Apple", "disease": "Apple Scab",
      "healthy": false, "severity": "medium", "cnn": true }
  ]
}
```

`cnn: false` marks crops only the AI vision model can name (cotton, onion, …).

### `POST /api/predict`

Multipart form with one field **`file`** (JPEG, PNG, WebP, HEIC/HEIF; ≤ 12 MB). Query: `lang`.

```bash
curl -X POST "http://localhost:8000/api/predict?lang=en" -F "file=@leaf.jpg;type=image/jpeg"
```

```json
{
  "language": "en",
  "inference_ms": 58.1,
  "low_confidence": false,
  "confidence_threshold": 0.6,
  "prediction": {
    "class_name": "Tomato___Late_blight",
    "confidence": 0.6002,
    "healthy": false,
    "severity": "high",
    "pathogen": "Phytophthora infestans (oomycete)",
    "crop": "Tomato",
    "disease": "Late Blight",
    "symptoms": "Large irregular greasy grey-green patches…",
    "remedy": "This spreads very fast in cool humid weather. Spray Cymoxanil…",
    "prevention": "Do not plant tomato next to potato…"
  },
  "alternatives": [ { "class_name": "Pepper,_bell___healthy", "confidence": 0.0482, "...": "..." } ],
  "unknown": { "is_unknown": false, "checked": true, "similarity": 0.647, "energy": 5.07 },
  "heatmap": {
    "grid": [[0.42, 0.37, 0.45, 0.0, 0.45, 0.72, 0.61], "… 7 rows"],
    "box": [0.0614, 0.1615, 0.8772, 0.6769]
  },
  "advice": {
    "spray_litres_per_acre": 200,
    "chemical": [
      { "product": "Cymoxanil 8% + Mancozeb 64% WP", "dose": 3, "unit": "g",
        "qty_per_acre": 600, "cost_per_acre": 660 },
      { "product": "Metalaxyl 8% + Mancozeb 64% WP", "dose": 2.5, "unit": "g",
        "qty_per_acre": 500, "cost_per_acre": 500 }
    ],
    "organic": {
      "text": "Bordeaux mixture 1% (allowed in organic farming)…",
      "items": [ { "product": "Pseudomonas fluorescens 1% WP", "dose": 10, "unit": "g",
                   "qty_per_acre": 2000, "cost_per_acre": 300 } ]
    },
    "currency": "INR",
    "price_note": "Approximate 2026 retail prices…"
  },
  "disclaimer": "This is an AI-based advisory tool. Confirm…",
  "speech_text": "Tomato. Disease: Late Blight. Confidence 60 %. Symptoms: …"
}
```

| Field | Meaning |
|---|---|
| `confidence` | Temperature-calibrated softmax probability of the top class |
| `low_confidence` | `true` when confidence < 0.6 **or** the photo is unknown |
| `unknown.is_unknown` | Features far from every class, or energy below threshold. `checked: false` means the checkpoint has no statistics |
| `heatmap.grid` | 7×7 Grad-CAM values 0–1, row-major, top-left first |
| `heatmap.box` | `[x, y, w, h]` of the centre crop the model saw, as fractions of the photo |
| `advice` | `null` for healthy leaves. `dose` is per litre of water; `unit` is `g`, `ml` or `l` (ready-mixed spray) |

| Status | When |
|---|---|
| 400 | Empty or unreadable image |
| 413 | Larger than 12 MB |
| 415 | Not an image type |
| 503 | No trained checkpoint in `backend/models/` |

### `GET /api/advisory/{class_name}`

The same `prediction`, `advice`, `disclaimer` and `speech_text` as `/predict`, without a photo
and without confidence. Used to reopen history and for crops only the vision model knows.
URL-encode the class name (it can contain commas, brackets and spaces).

```bash
curl "http://localhost:8000/api/advisory/Cotton___Bacterial_blight?lang=mr"
```

404 for an unknown class.

### `POST /api/tts`

```json
{ "text": "टोमॅटो. रोग: …", "lang": "mr" }
```

Returns `audio/mpeg`. `text` ≤ 2000 characters. Cached on disk by text hash, so repeating an
advisory is instant. 503 if gTTS cannot reach Google.

---

## Field tools

### `GET /api/weather`

| Query | Type |
|---|---|
| `lat` | −90 … 90 |
| `lon` | −180 … 180 |

```json
{
  "current": { "temperature": 22.8, "humidity": 85, "wind": 10.8, "precipitation": 0.0 },
  "windows": [
    { "start": "2026-09-25T06:00:00", "end": "2026-09-25T08:00:00", "hours": 3 }
  ],
  "rain": { "next_24h_mm": 0.0, "max_probability": 67.0, "first_rain": "2026-09-25T13:00:00" },
  "hourly": [ { "t": "2026-09-25T00:00:00", "good": false, "rain": false }, "… 48 entries" ],
  "disease_risk": "high",
  "humid_hours": 12,
  "timezone": "Asia/Kolkata"
}
```

Times are local to the location, without offset. A **window** is ≥ 2 consecutive hours that
are daylight (06–18), wind < 15 km/h, 8–32 °C, and dry (< 30 % rain chance, < 0.2 mm) for the
next 4 hours. **Disease risk** counts hours in the next 48 at ≥ 90 % humidity and 15–28 °C:
≥ 10 high, ≥ 4 medium. Cached 30 minutes per ~1 km. 503 if Open-Meteo is unreachable.

### `POST /api/report`

```json
{ "class_name": "Tomato___Late_blight", "lat": 18.52, "lon": 73.86, "source": "cnn" }
```

`source` is `cnn` or `vision`. Returns `{"stored": true, "cell_km": 5}`, or
`{"stored": false}` for healthy classes. Location is snapped to the centre of a 0.05° cell
(~5.5 km) before storage. 10 reports per visitor per minute (429 beyond).

### `GET /api/outbreaks`

| Query | Default | Range |
|---|---|---|
| `days` | 30 | 1–365 |
| `lang` | `mr` | |

```json
{
  "days": 30,
  "cell_km": 5,
  "cells": [
    { "lat": 18.525, "lon": 73.875, "class_name": "Tomato___Late_blight", "count": 2,
      "last_ts": 1790271190, "crop": "Tomato", "disease": "Late Blight", "severity": "high" }
  ]
}
```

---

## AI assistant

All three return **503** when `GROQ_API_KEY` is not set, and **429** beyond
`AI_RATE_LIMIT_PER_MIN` (default 20) per visitor per minute. Behind the Cloudflare tunnel the
visitor is identified by `CF-Connecting-IP`. Upstream failures map to 429 (Groq busy), 503
(key rejected or model retired) or 502.

### `POST /api/ai/second-opinion`

Multipart `file` (the same image), query `lang` and **`cnn_class`** (the CNN's answer).

```json
{
  "is_plant_leaf": true,
  "best_match": "Tomato___Early_blight",
  "quality_issue": "none",
  "verdict": "disagrees",
  "best_match_label": "Tomato — Early Blight",
  "model": "qwen/qwen3.8-27b"
}
```

| `verdict` | Meaning |
|---|---|
| `agrees` | Same class as the CNN |
| `disagrees` | A different class the CNN also knows |
| `extended` | A class only the vision model knows (cotton, onion, …) — fetch its advisory |
| `unknown` | A leaf, but not any known class |
| `not_leaf` | Not a plant leaf |

`quality_issue`: `none`, `blurry`, `dark`, `too_far`, `multiple_leaves`.

### `POST /api/ai/chat`

```json
{
  "lang": "mr",
  "messages": [ { "role": "user", "content": "फवारणी कधी करावी?" } ],
  "class_name": "Tomato___Late_blight",
  "confidence": 0.93,
  "low_confidence": false,
  "alternatives": ["Tomato___Early_blight"],
  "vision_match": null,
  "lat": 18.52,
  "lon": 73.86
}
```

| Field | Limit |
|---|---|
| `messages` | 1–16, alternating; the last must be `user`; each ≤ 1500 characters |
| `alternatives` | ≤ 5 class names |
| `vision_match` | The second opinion's class when it disagreed; both advisories are then given to the model |
| `lat`, `lon` | Optional; adds the 48-hour forecast to the model's context |

Response: **`text/plain` streamed** as it is generated. Read it incrementally:

```js
const reader = res.body.getReader();
const decoder = new TextDecoder();
for (;;) {
  const { done, value } = await reader.read();
  if (done) break;
  answer += decoder.decode(value, { stream: true });
}
```

The server looks up the advisory from `class_name`; advisory text sent by the client is never
used, so doses cannot be injected.

### `POST /api/ai/transcribe`

Multipart `file` (webm, ogg, mp4, mp3, wav, m4a; ≤ 5 MB), query `lang`.

```json
{ "text": "टोमॅटोच्या पानांवर करपा रोग आला आहे, कोणते औषध फवारू?", "language": "mr" }
```
