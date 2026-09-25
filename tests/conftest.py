"""Shared test setup.

Run from the project root:
    .venv\\Scripts\\python -m pytest
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT / "backend"))

# Tests must never spend Groq quota: an empty key switches the assistant off.
# load_dotenv does not override variables that are already set.
os.environ["GROQ_API_KEY"] = ""


@pytest.fixture(scope="session")
def remedies() -> dict:
    from app.services.inference import predictor
    return predictor.remedies


@pytest.fixture()
def scans_db(tmp_path, monkeypatch):
    """Point the outbreak map at a throwaway database."""
    from app.services import outbreaks
    monkeypatch.setattr(outbreaks, "DB_PATH", tmp_path / "scans.db")
    return tmp_path / "scans.db"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.config import MODEL_PATH
    from app.main import app

    if not MODEL_PATH.exists():
        pytest.skip("no trained checkpoint in backend/models/")
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def leaf_photo() -> bytes:
    return (FIXTURES / "leaf_in_hand.png").read_bytes()
