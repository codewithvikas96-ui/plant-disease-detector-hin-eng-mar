# पीक रोग ओळख · Plant Disease Detector

**Avishkar 2026** — a CNN that identifies crop leaf diseases from a phone photo and gives the
farmer the disease name, symptoms, remedy and prevention **in Marathi, Hindi or English**, with
voice output for farmers who cannot read.

**Documentation:** [product requirements](docs/PRD.md) · [architecture](docs/ARCHITECTURE.md) ·
[API](docs/API.md) · [model card](docs/MODEL_CARD.md) · [user guide (मराठी / English)](docs/USER_GUIDE.md) ·
[demo script](docs/DEMO_SCRIPT.md) · [all docs](docs/README.md)

---

## What it does

1. The farmer opens the app and points the camera at a leaf. A **live camera guide** checks
   light, glare, distance, shake and focus and tells them the one thing to fix.
2. A MobileNetV3 CNN — trained on PlantVillage, then **fine-tuned on real field photos** —
   classifies it into one of **38 classes** across **14 crops**.
3. The app shows the disease, a calibrated confidence bar, symptoms, a **remedy with exact
   dosage**, prevention, **the cost per acre** and an **organic alternative** — in the chosen
   language. A **heatmap** (Grad-CAM) shows which part of the leaf the model looked at.
4. **Listen** reads the whole advisory aloud in Marathi or Hindi.
5. If the photo is not a leaf the model knows, or it is under 60% confident, it says so instead
   of naming a disease — offline, without the AI.
6. **Spray timing** from the weather forecast: the next dry, calm hours, when rain is due, and
   how much the humidity favours fungal spread.
7. **History** of every scan on the phone, and an opt-in **outbreak map** of what neighbours
   are finding.
8. **AI assistant (optional, via Groq):** a second AI model checks the photo independently and
   also recognises **cotton, soybean, sugarcane, onion and pomegranate**; the farmer can ask
   follow-up questions, typed or **spoken**, and hear the answer read aloud.

---

## Setup

### One time

```bat
scripts\setup.bat
```

Creates `.venv\` inside this folder and installs everything there. Nothing touches your
system Python.

### Train the model

The model is not included — you train it yourself, which is the point of the project.

1. Upload `training/train_plantvillage.ipynb` to [Google Colab](https://colab.research.google.com)
2. `Runtime` → `Change runtime type` → **T4 GPU**
3. `Runtime` → `Run all` (~25 minutes)
4. The last cell downloads `plant_disease_model.pt` — put it in `backend/models/`

### Fine-tune it on field photos (recommended)

PlantVillage leaves are photographed on a plain background, so the model is far less accurate
on a farmer's photo. This step fixes most of that and adds the offline "not a leaf I know"
check and calibrated confidence. It runs on a laptop CPU (about an hour) — no GPU needed.

```bat
.venv\Scripts\python training\fetch_plantvillage_sample.py
git clone --depth 1 https://github.com/pratikkayal/PlantDoc-Dataset training\data\plantdoc
.venv\Scripts\python training\finetune_field.py
```

It prints before/after accuracy and writes `backend/models/plant_disease_model_field.pt`
(plus a `.json` with every number). Rename it to `plant_disease_model.pt` to use it. On
Windows a few PlantDoc files have `?` in their names and fail to check out; the rest are
enough.

**Adding crops to the CNN.** Put photos in folders named like the `remedies.json` keys —
`training/data/extra/Cotton___Bacterial_blight/*.jpg` — and run
`finetune_field.py --extra-dir training/data/extra`. The classifier grows new outputs for
them while keeping everything it already knows. Until then, those crops are recognised by the
Groq vision model.

### Turn on the AI assistant (optional, free)

1. Get a free API key at [console.groq.com/keys](https://console.groq.com/keys)
2. Paste it into `.env` (setup created it from `.env.example`):
   ```
   GROQ_API_KEY=gsk_...
   ```
3. Restart the server. The console prints `[ok] AI assistant on`.

Without a key everything else works exactly as before; the AI panel is simply hidden.

### Run

```bat
scripts\start.bat
```

Then open **http://localhost:8000**

**To demo on a phone:** connect the phone to the same Wi-Fi as the laptop and open the
address the server prints at startup (something like `http://192.168.0.104:8000`). On Android,
Chrome will offer *Add to Home screen* — it installs as a real app icon.

**Use the HTTPS tunnel URL for the full app.** Browsers only allow the live camera guide,
location (spray timing, outbreak map) and the microphone on `https://` or `localhost`. On a
plain `http://192.168.x.x` address the app falls back to the phone's own camera app and hides
the features that need location or the microphone. `scripts\tunnel.bat` gives you an HTTPS
link — see `docs/DEPLOY.md`.

---

## Accuracy on real field photos

Lab accuracy (99.5 % on PlantVillage) says little about a farmer's photo. Measured on the
PlantDoc test set of real field photos:

| | Original model | After field fine-tuning |
|---|---|---|
| Field photos, top-1 | 30.1 % | **66.5 %** |
| Field photos, top-3 | 58.1 % | **87.7 %** |
| Lab photos (PlantVillage holdout) | 99.6 % | 98.7 % |
| Calibration error (ECE) | 0.075 | **0.021** |
| Non-leaf photos flagged as unknown | — | **80 %** (4.8 % false alarms on real leaves) |

Full details, limitations and how to reproduce: [docs/MODEL_CARD.md](docs/MODEL_CARD.md).
The original checkpoint is kept as `backend/models/plant_disease_model_plantvillage.pt`.

## Farmer tools

| Feature | How it works |
|---|---|
| **Camera guide** | Four checks on the framed square, four times a second: brightness and glare (share of blown-out pixels), how much of the frame is leaf-coloured, frame-to-frame movement, and sharpness (variance of the Laplacian). The first failing check becomes the one instruction on screen. |
| **Heatmap** | Grad-CAM on the last convolutional block. The server sends a 7x7 grid (a few hundred bytes) plus the crop the model saw; the phone draws it as a spotlight — bright where the model looked, dimmed elsewhere. |
| **Unknown photo** | The fine-tuned checkpoint stores a prototype per class and two thresholds. A photo whose features are far from every prototype, or whose energy score is low, is flagged as "not a leaf I know" — offline. |
| **Cost per acre** | Each disease in `remedies.json` lists its products and dose per litre; `backend/data/prices.json` holds approximate prices. Cost = dose × 200 L/acre (400 for orchards) × price. Farmers set their own acreage. Edit the prices for your area. |
| **Organic option** | `backend/data/organic.json`, chosen by pathogen type (fungal, bacterial, virus vector, mite). |
| **Spray timing** | Open-Meteo forecast, free and keyless. Good hours are daylight, wind under 15 km/h, 8–32 °C, and no rain for the next 4 hours. Disease risk counts hours at 90%+ humidity and 15–28 °C. |
| **History** | Last 40 scans with thumbnails, stored only on the phone. Reopens in whatever language is selected, and works offline for advisories already seen. |
| **Outbreak map** | Off by default. When a farmer turns it on, each confident diagnosis sends only the disease name and a ~5 km grid cell (no photo, no IP). The home screen warns about the most-reported disease within 25 km. Leaflet from cdnjs, OpenStreetMap tiles. |

**Streptocycline removed.** The original advisory recommended Streptocycline for bacterial
spot. India no longer permits streptomycin and tetracycline on crops, so v2.0 of
`remedies.json` uses copper only and says so.

**The five Maharashtra crops** (cotton, soybean, sugarcane, onion, pomegranate — 15 classes)
were written for this app from common ICAR / state agricultural university recommendations.
Have an agronomist review them before relying on them.

---

## The AI assistant

The CNN stays the primary diagnosis — it is instant and runs on the laptop. Groq adds three
layers on top, each of which fails quietly if the internet or the key is missing:

| Feature | Groq model | What it does |
|---|---|---|
| **AI second opinion** | `qwen/qwen3.8-27b` (vision) | Looks at the same photo *without* being told the CNN's answer, then the server compares the two. Flags "this is not a leaf", "a different disease is likely", and photo problems (blurry, dark, too far). |
| **Krishi Mitra chat** | `openai/gpt-oss-120b` | Follow-up questions in Marathi, Hindi or English, streamed as they are generated. Suggested questions are one tap away. |
| **Voice questions** | `whisper-large-v3-turbo` | Tap the mic, speak in Marathi or Hindi, and the answer is read back aloud automatically. |

**Why the chat cannot invent a dose.** The browser sends only the class name; the server looks
up that disease's advisory in `remedies.json` and hands it to the model with instructions to
recommend only those products at those doses, never banned pesticides, and to send the
farmer to their KVK or the Kisan Call Centre (1800-180-1551) otherwise. When the vision model
disagrees with the CNN, both advisories are given, so the answer covers both possibilities.

**Why the second opinion matters.** On a real field photo of tomato *early* blight, the CNN
said *late* blight at 41% — PlantVillage is shot on plain backgrounds, field photos are not.
The vision model named early blight correctly. Showing a judge this disagreement, and the
app handling it honestly, is a stronger demo than a perfect score.

**Protecting your key.** On the public Cloudflare URL anyone can use the app, so each visitor
is limited to 20 AI requests a minute (`AI_RATE_LIMIT_PER_MIN` in `.env`). The key never
leaves the server.

**Models change.** Groq retires models regularly. The server checks at startup and prints
`[warn] Groq model '...' is not available` if one of yours has gone — set a current one in
`.env` from [console.groq.com/docs/models](https://console.groq.com/docs/models).

**Weather in answers.** When the farmer has shared their location, the chat also gets the
48-hour forecast, so "when should I spray?" is answered with actual hours.

---

## Project layout

```
backend/
  app/                     the FastAPI application (a Python package)
    main.py                app, startup, routers, serves the PWA
    config.py              every path, .env and constant in one place
    ratelimit.py           per-visitor limits that protect the Groq quota
    routers/               HTTP endpoints, grouped by what the farmer is doing
      diagnosis.py         /api/health, /api/classes, /api/predict, /api/advisory
      assistant.py         /api/ai/chat, /api/ai/second-opinion, /api/ai/transcribe
      field.py             /api/weather, /api/report, /api/outbreaks
      speech.py            /api/tts
    services/              the work behind the endpoints
      inference.py         CNN prediction, Grad-CAM, unknown-photo check
      assistant.py         Groq client: chat, vision, speech-to-text
      advice.py            cost per acre, organic options
      weather.py           Open-Meteo forecast -> spray windows, disease risk
      outbreaks.py         anonymous ~5 km disease reports (SQLite)
    ml/
      model.py             architecture + transforms, shared with training/
  data/                    knowledge that ships with the app (versioned)
    remedies.json          53 classes x {symptoms, remedy, prevention, treatments} x {en, hi, mr}
    prices.json            approximate product prices - edit for your area
    organic.json           organic options by pathogen type
  models/                  <- plant_disease_model.pt
  var/                     written while running: TTS cache, scans.db (git-ignored)

frontend/                  installable PWA (vanilla JS modules, no build step)
  index.html  sw.js  manifest.webmanifest
  css/styles.css
  js/app.js                screens, diagnosis, chat, voice
  js/camera.js             live camera guide
  js/heatmap.js            Grad-CAM spotlight
  js/history.js            scan history (on the phone)
  js/weather.js            spray-timing card
  js/map.js                outbreak map (Leaflet)
  js/i18n.js               every string in Marathi, Hindi, English
  icons/

training/
  train_plantvillage.ipynb      Colab notebook: data, training, evaluation, export
  fetch_plantvillage_sample.py  balanced PlantVillage sample for fine-tuning
  finetune_field.py             field fine-tuning, calibration, unknown-photo statistics
  data/                         downloaded datasets (git-ignored)

tests/                     pytest suite; fixtures/ holds a real field photo
scripts/                   setup.bat, start.bat, tunnel.bat, make_dummy_model.py
docs/DEPLOY.md             public HTTPS link with Cloudflare Tunnel

.env.example               copy to .env and add GROQ_API_KEY (.env is git-ignored)
requirements.txt           app dependencies
requirements-dev.txt       + pytest
```

### Running the tests

```bat
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

They check that every remedy is complete in all three languages, that the doses on the cost
card match the spoken advisory, that no antibiotic is recommended, the spray-window rules,
the outbreak-map anonymisation, rate limiting, and the API end to end. They never call Groq.

---

## Testing the app before the model is ready

```bat
.venv\Scripts\python scripts\make_dummy_model.py
```

Writes an **untrained** checkpoint so you can click through the whole app — upload, result
card, language switching, voice. Its predictions are random (~2.6% confidence, which is 1/38).
**Replace it with the real checkpoint before the presentation.**

---

## Notes for the viva

**Why MobileNetV3 and not ResNet50 or a custom CNN?**
The app has to run on a laptop CPU at the exhibition — there is no GPU on the demo machine.
MobileNetV3-Large does an image in ~30 ms on CPU and the checkpoint is 17 MB. A custom CNN
trained from scratch on 54k images would land around 90–95%; transfer learning from ImageNet
reaches ~99% because the low-level edge and texture filters come pre-learned.

**Why is the reported accuracy so high?**
PlantVillage images are all shot on a uniform background under good lighting, so ~99%
validation accuracy is a property of the dataset, not proof of field performance. Say this
before a judge points it out — it turns a weakness into evidence that you understand your
data. We measured it: on real field photos (PlantDoc) the original model scored **30 %**.
After fine-tuning on field photos it scores **66.5 % top-1 and 87.7 % top-3**, and the 60 %
confidence cut-off, the unknown-photo check and the AI second opinion cover the rest.

**Which classes does it confuse?**
Run section 8 of the notebook. Tomato *Early blight* vs *Target Spot* is the usual pair —
they genuinely look alike, both being brown ringed lesions. Know your top three confusions.

**Where do the remedies come from?**
`backend/data/remedies.json`, written against standard ICAR / Krishi Vigyan Kendra advisory
doses. Every result carries a disclaimer telling the farmer to confirm with their local
agriculture officer before spraying.

---

## Requirements

- Python 3.10+ (tested on 3.13)
- A Google account for Colab (free tier is enough)
- Internet for the voice feature — server-side speech uses gTTS. If the phone has an
  `hi-IN` voice installed the browser speaks it offline; almost no phone ships `mr-IN`, so
  Marathi falls back to the server.
