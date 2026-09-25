"""Anonymous disease reports for the regional outbreak map.

Only farmers who switch on location sharing contribute, and each report is
reduced to a disease name, a date and a ~5 km grid cell before it is stored.
No IP address, photo or device identifier is kept.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing

from app.config import SCANS_DB

DB_PATH = SCANS_DB
CELL_DEG = 0.05  # ~5.5 km at Indian latitudes: shows a village cluster, not a farm

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            ts INTEGER NOT NULL,
            class_name TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            source TEXT NOT NULL
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS reports_ts ON reports (ts)")
    return conn


def snap(value: float) -> float:
    """Snap to the centre of a grid cell so the exact field cannot be recovered."""
    return round((int(value // CELL_DEG) + 0.5) * CELL_DEG, 4)


def record(class_name: str, lat: float, lon: float, source: str) -> None:
    with _lock, closing(_connect()) as conn, conn:
        conn.execute("INSERT INTO reports (ts, class_name, lat, lon, source) VALUES (?, ?, ?, ?, ?)",
                     (int(time.time()), class_name, snap(lat), snap(lon), source))


def summary(days: int) -> list[dict]:
    """Report counts per grid cell and disease over the last `days` days."""
    since = int(time.time()) - days * 86400
    with _lock, closing(_connect()) as conn, conn:
        rows = conn.execute("""
            SELECT lat, lon, class_name, COUNT(*), MAX(ts)
            FROM reports WHERE ts >= ?
            GROUP BY lat, lon, class_name
            ORDER BY COUNT(*) DESC""", (since,)).fetchall()
    return [{"lat": r[0], "lon": r[1], "class_name": r[2], "count": r[3], "last_ts": r[4]} for r in rows]
