# Development guide

How to set up, change and test the project. Read [ARCHITECTURE.md](ARCHITECTURE.md) first for
the big picture.

## Setup

Windows, Python 3.10+ (tested on 3.12 and 3.13).

```bat
scripts\setup.bat
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

`setup.bat` creates `.venv\`, installs the app requirements, and copies `.env.example` to
`.env`. Put your Groq key in `.env` to enable the AI features (optional).

You need a checkpoint in `backend/models/plant_disease_model.pt`. Either train one (README),
or for UI work use an untrained stand-in:

```bat
.venv\Scripts\python scripts\make_dummy_model.py
```

## Run

```bat
scripts\start.bat
```

or, with auto-reload while editing Python:

```bat
.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Open `http://localhost:8000`. API docs: `http://localhost:8000/docs`.

The frontend has no build step: edit a file in `frontend/`, reload the page. The service worker
serves the network version first, so a normal reload is enough.

## Test

```bat
.venv\Scripts\python -m pytest
```

| File | Covers |
|---|---|
| `tests/test_remedies.py` | Data: all three languages, prices, doses match remedy text, no antibiotics |
| `tests/test_services.py` | Cost maths, spray windows, humidity risk, outbreak grid, rate limiter |
| `tests/test_api.py` | Endpoints end to end with the real checkpoint (skipped if none) |

Tests set `GROQ_API_KEY` to empty, so they never spend quota. The outbreak tests use a
temporary database.

The camera guide's frame checks are a pure function (`analyse()` in `frontend/js/camera.js`)
and can be exercised from the browser console on still images.

## Code conventions

**Python**
- Routers (`app/routers/`) validate input and turn errors into HTTP status codes. Services
  (`app/services/`) do the work and never raise `HTTPException`.
- Every path, environment variable and constant goes in `app/config.py`.
- Imports are absolute from the package: `from app.services.inference import predictor`.
- Comments explain *why*, especially anything that protects the farmer (thresholds, safety
  rules, privacy rounding).

**JavaScript**
- ES modules, no framework, no build step.
- Every user-visible string goes in `js/i18n.js`, in all three languages.
- Insert server text with `textContent` or DOM calls, never `innerHTML`.
- Wrap every `localStorage` access in `try/catch`; the app must work without it.

**CSS**
- Colours only through the tokens at the top of `styles.css`. `--neel` (indigo) is reserved
  for anything the online AI says, so farmers can tell it apart from the offline model.
- Tap targets at least 44 px; body text at least 16 px.

## Common tasks

### Add an API endpoint

1. Put the logic in a service (new file in `app/services/` or an existing one).
2. Add the route to the router that matches the task, or create a router and include it in
   `app/main.py`.
3. Add limits and paths to `app/config.py`.
4. Add a test in `tests/test_api.py` and document it in `docs/API.md`.

### Add a UI string

Add the key to all three language blocks in `frontend/js/i18n.js`. Static text: put
`data-i18n="key"` on the element. Dynamic text: `t().key`. Strings that interpolate values are
functions, so word order can differ per language.

### Add a disease or crop

See [DATA.md](DATA.md#adding-a-disease-or-crop).

### Change a Groq model

Set `GROQ_CHAT_MODEL`, `GROQ_VISION_MODEL` or `GROQ_STT_MODEL` in `.env` and restart. The
server warns at startup if a model is not available to your key. Current models:
<https://console.groq.com/docs/models>.

### Retrain or fine-tune

- Full training on PlantVillage: `training/train_plantvillage.ipynb` on Colab (GPU).
- Field fine-tuning on a laptop CPU (~40 min): see README, *Fine-tune it on field photos*.
  If post-processing fails, rerun calibration only with
  `python training/finetune_field.py --weights backend/models/plant_disease_model_field.raw.pt`.

## Git

- Work on a branch; `main` is the release branch.
- Never commit `.env`, datasets (`training/data/`), or runtime files (`backend/var/`) — all
  git-ignored.
- Run the tests before committing.
