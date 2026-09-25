# Changelog

## 2.0.0 — September 2026

### Accuracy
- **Field fine-tuning** (`training/finetune_field.py`): the PlantVillage model is fine-tuned on
  PlantDoc field photos mixed 1:1 with a PlantVillage sample. Numbers in `MODEL_CARD.md`.
- **Calibrated confidence** by temperature scaling, so "80 %" means roughly 80 % correct.
- **Offline unknown-photo check**: class prototypes and energy thresholds stored in the
  checkpoint flag photos that are not a leaf the model knows.
- **Grad-CAM heatmap** returned with every prediction and drawn as a spotlight on the phone.
- **Five Maharashtra crops** (cotton, soybean, sugarcane, onion, pomegranate — 15 classes)
  added to the knowledge base, recognised by the AI vision model; the CNN can learn them with
  `--extra-dir`.
- Checkpoints load with `weights_only=True`.

### AI assistant (Groq, optional)
- **Second opinion**: an independent vision model checks every photo; verdicts agree /
  disagree / not a leaf / unknown / extended crop.
- **Krishi Mitra chat** in Marathi, Hindi and English, streamed, grounded in the remedy
  database, aware of both advisories when the models disagree and of the local forecast.
- **Voice questions** via Whisper, answered aloud.
- Per-visitor rate limiting; startup warning when a configured Groq model is retired.

### Farmer tools
- **Live camera guide**: light, glare, leaf coverage, movement and sharpness checks.
- **Cost per acre** for each product, with acreage control, and an **organic option**.
- **Spray timing** from Open-Meteo: spray windows, rain warning, humidity disease risk.
- **Scan history** on the phone, reopenable in any language, offline for seen advisories.
- **Outbreak map** (opt-in, ~5 km anonymous cells) with a nearby-outbreak alert.

### Interface
- Redesigned for sunlight: Baloo 2 and Mukta (Devanagari-first) from Google Fonts, Material
  Symbols icons instead of emoji, bottom tab bar, photo-first result, bill-style cost card.
- Indigo reserved for everything the online AI says.
- Desktop view: the app sits in a phone-width column over a blurred-foliage backdrop with
  taglines in all three languages (pure SVG/CSS, hidden on phones).
- A photo flagged as unknown greys out the disease name so the warning leads.
- Frontend split into ES modules; service worker caches modules, fonts and advisories.

### Data and safety
- **Streptocycline removed** from bacterial-spot remedies (antibiotics no longer permitted on
  crops in India).
- Structured `treatments`, `pathogen_type` and `spray_l_per_acre` for every class.
- `prices.json` and `organic.json` added.

### Project
- Backend restructured into the `app` package: `config`, `routers/`, `services/`, `ml/`.
  Start command is now `uvicorn app.main:app --app-dir backend`.
- Runtime files moved to `backend/var/`.
- Test suite (`pytest`): data integrity, services, API.
- Documentation in `docs/`.

### Fixed
- Pressing Stop on the voice button restarted speech through the server voice.
- Installed phones never received app updates (cache-first service worker).
- `.gitignore` did not ignore the `.env` file.

## 1.0.0 — September 2026

- MobileNetV3-Large trained on PlantVillage (38 classes, 99.53 % validation accuracy).
- Remedies in Marathi, Hindi and English with voice output.
- Installable PWA; Cloudflare Tunnel deployment.
