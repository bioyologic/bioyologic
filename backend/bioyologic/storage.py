"""Persistencia: proyectos y análisis en SQLite + imágenes en disco.

    <root>/bioyologic.db
    <root>/images/<id>_original.jpg | <id>_annotated.jpg | <id>_thumb.jpg
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    target_samples INTEGER NOT NULL DEFAULT 10,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    sample_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    dilution REAL,
    volume_ml REAL,
    mm_per_px REAL,
    total INTEGER NOT NULL,
    cfu_per_ml REAL,
    status TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_project ON analyses(project_id);
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at);
"""

IMAGE_KINDS = ("original", "annotated", "thumb")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _thumbnail(img: np.ndarray, size: int = 320) -> np.ndarray:
    h, w = img.shape[:2]
    side = min(h, w)
    y0, x0 = (h - side) // 2, (w - side) // 2
    return cv2.resize(img[y0:y0 + side, x0:x0 + side], (size, size), interpolation=cv2.INTER_AREA)


class Store:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.images = self.root / "images"
        self.images.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.root / "bioyologic.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._db.execute(sql, params)
            self._db.commit()
            return cur

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, params).fetchall()]

    # ---------------------------------------------------------------- proyectos
    def create_project(self, name: str, description: str = "", target_samples: int = 10) -> dict:
        cur = self._exec(
            "INSERT INTO projects (name, description, target_samples, created_at) VALUES (?, ?, ?, ?)",
            (name, description, target_samples, _now()))
        return self.get_project(cur.lastrowid)

    _PROJECT_SELECT = """
        SELECT p.*, COUNT(a.id) AS analyses_count,
               COALESCE(SUM(a.total), 0) AS colonies_total,
               MAX(a.created_at) AS last_analysis_at,
               (SELECT id FROM analyses WHERE project_id = p.id
                ORDER BY created_at DESC, id DESC LIMIT 1) AS cover_analysis_id
        FROM projects p LEFT JOIN analyses a ON a.project_id = p.id
    """

    def get_project(self, project_id: int) -> dict | None:
        rows = self._all(self._PROJECT_SELECT + " WHERE p.id = ? GROUP BY p.id", (project_id,))
        return rows[0] if rows else None

    def list_projects(self) -> list[dict]:
        return self._all(self._PROJECT_SELECT +
                         " GROUP BY p.id ORDER BY COALESCE(MAX(a.created_at), p.created_at) DESC")

    def update_project(self, project_id: int, **fields) -> dict | None:
        allowed = {k: v for k, v in fields.items()
                   if k in ("name", "description", "target_samples") and v is not None}
        if allowed:
            sets = ", ".join(f"{k} = ?" for k in allowed)
            self._exec(f"UPDATE projects SET {sets} WHERE id = ?", (*allowed.values(), project_id))
        return self.get_project(project_id)

    def delete_project(self, project_id: int) -> bool:
        """Los análisis del proyecto no se borran: quedan sin proyecto."""
        return self._exec("DELETE FROM projects WHERE id = ?", (project_id,)).rowcount > 0

    # ---------------------------------------------------------------- análisis
    def add_analysis(self, *, sample_name: str, result: dict, original: np.ndarray,
                     annotated: np.ndarray, project_id: int | None = None,
                     dilution: float | None = None, volume_ml: float | None = None,
                     notes: str = "") -> dict:
        s = result["summary"]
        cur = self._exec(
            """INSERT INTO analyses (project_id, sample_name, created_at, dilution, volume_ml,
                   mm_per_px, total, cfu_per_ml, status, notes, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, sample_name, result.get("analyzed_at", _now()), dilution, volume_ml,
             result.get("mm_per_px"), s["total"], s["cfu_per_ml"], s["status"], notes,
             json.dumps(result, ensure_ascii=False)))
        aid = cur.lastrowid
        q = [cv2.IMWRITE_JPEG_QUALITY, 90]
        cv2.imwrite(str(self.image_path(aid, "original")), original, q)
        cv2.imwrite(str(self.image_path(aid, "annotated")), annotated, q)
        cv2.imwrite(str(self.image_path(aid, "thumb")), _thumbnail(original), q)
        return self.get_analysis(aid)

    def image_path(self, analysis_id: int, kind: str) -> Path:
        if kind not in IMAGE_KINDS:
            raise ValueError(kind)
        return self.images / f"{analysis_id}_{kind}.jpg"

    _ANALYSIS_SELECT = """
        SELECT a.*, p.name AS project_name FROM analyses a
        LEFT JOIN projects p ON p.id = a.project_id
    """

    @staticmethod
    def _decode(row: dict, with_colonies: bool) -> dict:
        result = json.loads(row.pop("result_json"))
        row["summary"] = result["summary"]
        row["image_size"] = result.get("image_size")
        row["species"] = result.get("species")
        if with_colonies:
            row["colonies"] = result["colonies"]
        return row

    def get_analysis(self, analysis_id: int, with_colonies: bool = True) -> dict | None:
        rows = self._all(self._ANALYSIS_SELECT + " WHERE a.id = ?", (analysis_id,))
        return self._decode(rows[0], with_colonies) if rows else None

    def list_analyses(self, project_id: int | None = None, query: str = "",
                      limit: int = 50, offset: int = 0) -> list[dict]:
        where, params = [], []
        if project_id is not None:
            where.append("a.project_id = ?")
            params.append(project_id)
        if query:
            where.append("(a.sample_name LIKE ? OR p.name LIKE ?)")
            params += [f"%{query}%", f"%{query}%"]
        sql = self._ANALYSIS_SELECT
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY a.created_at DESC, a.id DESC LIMIT ? OFFSET ?"
        return [self._decode(r, False) for r in self._all(sql, (*params, limit, offset))]

    def update_analysis(self, analysis_id: int, **fields) -> dict | None:
        allowed = {k: v for k, v in fields.items() if k in ("sample_name", "notes", "project_id")}
        if "project_id" in allowed and allowed["project_id"] == 0:
            allowed["project_id"] = None  # 0 = quitar del proyecto
        allowed = {k: v for k, v in allowed.items() if v is not None or k == "project_id"}
        if allowed:
            sets = ", ".join(f"{k} = ?" for k in allowed)
            self._exec(f"UPDATE analyses SET {sets} WHERE id = ?", (*allowed.values(), analysis_id))
        return self.get_analysis(analysis_id)

    def delete_analysis(self, analysis_id: int) -> bool:
        ok = self._exec("DELETE FROM analyses WHERE id = ?", (analysis_id,)).rowcount > 0
        for kind in IMAGE_KINDS:
            self.image_path(analysis_id, kind).unlink(missing_ok=True)
        return ok

    # ---------------------------------------------------------------- resumen
    def stats(self) -> dict:
        row = self._all("""SELECT COUNT(*) AS analyses, COALESCE(SUM(total), 0) AS colonies,
                                  (SELECT COUNT(*) FROM projects) AS projects
                           FROM analyses""")[0]
        return row
