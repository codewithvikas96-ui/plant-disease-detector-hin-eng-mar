"""FastAPI server for the plant disease advisory PWA.

Run from the project root:
    .venv/Scripts/python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000

Binding to 0.0.0.0 is deliberate: judges open the app on their own phone over
the same Wi-Fi, so the server has to be reachable from the LAN, not just localhost.

Layout:
    routers/   HTTP endpoints, grouped by what the farmer is doing
    services/  the work behind them: CNN, Groq, costs, weather, outbreak map
    ml/        model architecture, shared with training/
"""

from __future__ import annotations

import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import FRONTEND_DIR, PORT
from app.routers import assistant as assistant_routes
from app.routers import diagnosis, field, speech
from app.services.assistant import assistant
from app.services.inference import ModelNotTrainedError, predictor


@asynccontextmanager
async def lifespan(_: FastAPI):
    warm_up()
    if assistant.enabled:
        for model in await assistant.missing_models():
            print(f"[warn] Groq model '{model}' is not available to this key - "
                  "set a current one in .env (https://console.groq.com/docs/models)")
    yield


app = FastAPI(
    title="Plant Disease Advisory API",
    description="CNN leaf-disease diagnosis with remedies in Marathi, Hindi and English, "
                "plus an optional Groq-powered assistant.",
    version="2.0.0",
    lifespan=lifespan,
)

# The PWA is served from this same origin in normal use. CORS stays open so the
# frontend can also be run from a separate dev server while you build it.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(diagnosis.router)
app.include_router(assistant_routes.router)
app.include_router(field.router)
app.include_router(speech.router)


def warm_up() -> None:
    """Load the checkpoint at boot so the first farmer does not wait for it."""
    try:
        predictor.load()
        field_acc = predictor.metrics.get("field_accuracy")
        print(f"[ok] model loaded: {predictor.arch}, {len(predictor.class_names)} classes"
              + (f", field accuracy {field_acc:.1%}" if isinstance(field_acc, (int, float)) else "")
              + (", unknown-photo check on" if predictor.ood else ""))
    except ModelNotTrainedError as exc:
        print(f"[warn] {exc}")

    if assistant.enabled:
        print(f"[ok] AI assistant on: chat={assistant.chat_model}, "
              f"vision={assistant.vision_model}, speech={assistant.stt_model}")
    else:
        print("[info] AI assistant off - add GROQ_API_KEY to .env to enable it")

    # Printed to the console only — never returned by the API, since the tunnel
    # would otherwise publish this machine's private address to the internet.
    print(f"[ok] open on a phone on the same Wi-Fi: {_lan_url()}")


# ------------------------------------------------------------- PWA static files
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    @app.get("/", include_in_schema=False)
    def root() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        # A service worker may only control pages at or below its own path, so
        # it has to be served from the site root, not from /app/.
        return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript")

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "manifest.webmanifest",
                            media_type="application/manifest+json")


def _lan_url() -> str:
    """Best-effort LAN address, so you can open the app on a phone over Wi-Fi."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # no packet is actually sent
            ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    return f"http://{ip}:{PORT}"
