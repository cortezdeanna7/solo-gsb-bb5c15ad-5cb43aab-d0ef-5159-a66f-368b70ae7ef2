"""SQLite 持久化：保存的计算条目。"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.getcwd(), "data", "app.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calculations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL DEFAULT '',
    expression    TEXT    NOT NULL,
    status        TEXT    NOT NULL,           -- ok | error
    value         REAL,
    uncertainty   REAL,
    unit          TEXT,
    si_value      REAL,
    si_uncertainty REAL,
    si_unit       TEXT,
    formatted     TEXT,
    dimension     TEXT,
    error         TEXT,
    created_at    TEXT    NOT NULL
)
"""


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        c.execute(_SCHEMA)


def insert_calc(name: str, expression: str, result: dict | None,
                status: str, error: str | None) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row = {
        "name": name,
        "expression": expression,
        "status": status,
        "value": None, "uncertainty": None, "unit": None,
        "si_value": None, "si_uncertainty": None, "si_unit": None,
        "formatted": None, "dimension": None,
        "error": error,
        "created_at": now,
    }
    if result is not None:
        row.update({
            "value": result["value"] if isinstance(result["value"], (int, float)) else None,
            "uncertainty": result["uncertainty"] if isinstance(result["uncertainty"], (int, float)) else None,
            "unit": result["unit"],
            "si_value": result["si"]["value"] if isinstance(result["si"]["value"], (int, float)) else None,
            "si_uncertainty": result["si"]["uncertainty"] if isinstance(result["si"]["uncertainty"], (int, float)) else None,
            "si_unit": result["si"]["unit"],
            "formatted": result["formatted"],
            "dimension": result["dimension"],
        })
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO calculations
               (name, expression, status, value, uncertainty, unit,
                si_value, si_uncertainty, si_unit, formatted, dimension,
                error, created_at)
               VALUES (:name, :expression, :status, :value, :uncertainty,
                       :unit, :si_value, :si_uncertainty, :si_unit,
                       :formatted, :dimension, :error, :created_at)""",
            row)
        row["id"] = cur.lastrowid
    return row


def list_calcs() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM calculations ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def delete_calc(cid: int) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM calculations WHERE id = ?", (cid,))
        return cur.rowcount > 0
