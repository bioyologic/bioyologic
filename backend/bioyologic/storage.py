"""Persistencia: usuarios, proyectos y análisis en SQLite + imágenes en disco.

    <root>/bioyologic.db
    <root>/images/<id>_original.jpg | <id>_annotated.jpg | <id>_thumb.jpg

Cada proyecto y análisis pertenece a un usuario (`user_id`) y solo su dueño lo ve. Los datos
anteriores a las cuentas quedan sin dueño (`user_id` NULL): nadie los ve hasta que se asignan o se
borran con `python -m bioyologic.manage`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    institution TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    consent_at TEXT NOT NULL,
    consent_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    target_samples INTEGER NOT NULL DEFAULT 10,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    access_key TEXT,
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
"""

# Columnas añadidas después de la primera versión: las bases existentes se migran al abrir.
MIGRATIONS = {
    "projects": {"user_id": "INTEGER REFERENCES users(id) ON DELETE CASCADE"},
    "analyses": {"user_id": "INTEGER REFERENCES users(id) ON DELETE CASCADE", "access_key": "TEXT"},
}

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_analyses_project ON analyses(project_id);
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at);
CREATE INDEX IF NOT EXISTS idx_analyses_user ON analyses(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""

IMAGE_KINDS = ("original", "annotated", "thumb")
SESSION_DAYS = 30
USER_FIELDS = "id, email, name, role, institution, created_at, consent_at, consent_version"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _thumbnail(img: np.ndarray, size: int = 320) -> np.ndarray:
    h, w = img.shape[:2]
    side = min(h, w)
    y0, x0 = (h - side) // 2, (w - side) // 2
    return cv2.resize(img[y0:y0 + side, x0:x0 + side], (size, size), interpolation=cv2.INTER_AREA)


def hash_password(password: str, salt: bytes | None = None) -> str:
    """scrypt (biblioteca estándar): lento a propósito para frenar ataques de fuerza bruta."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, _ = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)


def _token_hash(token: str) -> str:
    # Solo se guarda el hash: quien lea la base de datos no puede usar las sesiones.
    return hashlib.sha256(token.encode()).hexdigest()


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
        self._migrate()
        self._db.executescript(INDEXES)

    def _migrate(self) -> None:
        for table, cols in MIGRATIONS.items():
            have = {r["name"] for r in self._db.execute(f"PRAGMA table_info({table})")}
            for col, decl in cols.items():
                if col not in have:
                    self._db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        for (aid,) in self._db.execute("SELECT id FROM analyses WHERE access_key IS NULL").fetchall():
            self._db.execute("UPDATE analyses SET access_key = ? WHERE id = ?", (secrets.token_urlsafe(16), aid))
        self._db.commit()

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

    # ---------------------------------------------------------------- usuarios
    def create_user(self, *, email: str, password: str, name: str, role: str = "", institution: str = "",
                    consent_version: str) -> dict | None:
        """None si el correo ya está registrado."""
        now = _now()
        try:
            cur = self._exec(
                """INSERT INTO users (email, name, role, institution, password_hash, created_at,
                       consent_at, consent_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (email, name, role, institution, hash_password(password), now, now, consent_version))
        except sqlite3.IntegrityError:
            return None
        return self.get_user(cur.lastrowid)

    def get_user(self, user_id: int) -> dict | None:
        rows = self._all(f"SELECT {USER_FIELDS} FROM users WHERE id = ?", (user_id,))
        return rows[0] if rows else None

    def authenticate(self, email: str, password: str) -> dict | None:
        rows = self._all("SELECT id, password_hash FROM users WHERE email = ?", (email,))
        if not rows:
            hash_password(password)  # mismo tiempo de respuesta exista o no el correo
            return None
        return self.get_user(rows[0]["id"]) if check_password(password, rows[0]["password_hash"]) else None

    def update_user(self, user_id: int, **fields) -> dict | None:
        allowed = {k: v for k, v in fields.items() if k in ("name", "role", "institution") and v is not None}
        if allowed:
            sets = ", ".join(f"{k} = ?" for k in allowed)
            self._exec(f"UPDATE users SET {sets} WHERE id = ?", (*allowed.values(), user_id))
        return self.get_user(user_id)

    def set_password(self, user_id: int, password: str) -> None:
        self._exec("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))
        self._exec("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def delete_user(self, user_id: int) -> None:
        """Supresión total (Ley 1581): cuenta, sesiones, proyectos, análisis y fotos."""
        for r in self._all("SELECT id FROM analyses WHERE user_id = ?", (user_id,)):
            self._remove_images(r["id"])
        self._exec("DELETE FROM analyses WHERE user_id = ?", (user_id,))
        self._exec("DELETE FROM projects WHERE user_id = ?", (user_id,))
        self._exec("DELETE FROM users WHERE id = ?", (user_id,))

    def export_user(self, user_id: int) -> dict:
        """Todo lo que el servidor guarda de un usuario, para el derecho de acceso."""
        return {"exported_at": _now(), "user": self.get_user(user_id),
                "projects": self.list_projects(user_id),
                "analyses": [self.get_analysis(a["id"], user_id)
                             for a in self.list_analyses(user_id, limit=1_000_000)]}

    # ---------------------------------------------------------------- sesiones
    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now().astimezone()
        self._exec("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                   (_token_hash(token), user_id, now.isoformat(timespec="seconds"),
                    (now + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")))
        return token

    def session_user(self, token: str) -> dict | None:
        rows = self._all("SELECT user_id, expires_at FROM sessions WHERE token_hash = ?", (_token_hash(token),))
        if not rows:
            return None
        if datetime.fromisoformat(rows[0]["expires_at"]) < datetime.now().astimezone():
            self.delete_session(token)
            return None
        return self.get_user(rows[0]["user_id"])

    def delete_session(self, token: str) -> None:
        self._exec("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    # ---------------------------------------------------------------- proyectos
    def create_project(self, user_id: int, name: str, description: str = "", target_samples: int = 10) -> dict:
        cur = self._exec(
            "INSERT INTO projects (user_id, name, description, target_samples, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, description, target_samples, _now()))
        return self.get_project(cur.lastrowid, user_id)

    _PROJECT_SELECT = """
        SELECT p.*, COUNT(a.id) AS analyses_count,
               COALESCE(SUM(a.total), 0) AS colonies_total,
               MAX(a.created_at) AS last_analysis_at,
               (SELECT id FROM analyses WHERE project_id = p.id
                ORDER BY created_at DESC, id DESC LIMIT 1) AS cover_analysis_id,
               (SELECT access_key FROM analyses WHERE project_id = p.id
                ORDER BY created_at DESC, id DESC LIMIT 1) AS cover_access_key
        FROM projects p LEFT JOIN analyses a ON a.project_id = p.id
    """

    def get_project(self, project_id: int, user_id: int) -> dict | None:
        rows = self._all(self._PROJECT_SELECT + " WHERE p.id = ? AND p.user_id = ? GROUP BY p.id",
                         (project_id, user_id))
        return rows[0] if rows else None

    def list_projects(self, user_id: int) -> list[dict]:
        return self._all(self._PROJECT_SELECT + " WHERE p.user_id = ?"
                         " GROUP BY p.id ORDER BY COALESCE(MAX(a.created_at), p.created_at) DESC", (user_id,))

    def update_project(self, project_id: int, user_id: int, **fields) -> dict | None:
        allowed = {k: v for k, v in fields.items()
                   if k in ("name", "description", "target_samples") and v is not None}
        if allowed:
            sets = ", ".join(f"{k} = ?" for k in allowed)
            self._exec(f"UPDATE projects SET {sets} WHERE id = ? AND user_id = ?",
                       (*allowed.values(), project_id, user_id))
        return self.get_project(project_id, user_id)

    def delete_project(self, project_id: int, user_id: int) -> bool:
        """Los análisis del proyecto no se borran: quedan sin proyecto."""
        return self._exec("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id)).rowcount > 0

    # ---------------------------------------------------------------- análisis
    def add_analysis(self, *, user_id: int, sample_name: str, result: dict, original: np.ndarray,
                     annotated: np.ndarray, project_id: int | None = None,
                     dilution: float | None = None, volume_ml: float | None = None,
                     notes: str = "") -> dict:
        s = result["summary"]
        cur = self._exec(
            """INSERT INTO analyses (user_id, access_key, project_id, sample_name, created_at, dilution,
                   volume_ml, mm_per_px, total, cfu_per_ml, status, notes, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, secrets.token_urlsafe(16), project_id, sample_name, result.get("analyzed_at", _now()),
             dilution, volume_ml, result.get("mm_per_px"), s["total"], s["cfu_per_ml"], s["status"], notes,
             json.dumps(result, ensure_ascii=False)))
        aid = cur.lastrowid
        q = [cv2.IMWRITE_JPEG_QUALITY, 90]
        cv2.imwrite(str(self.image_path(aid, "original")), original, q)
        cv2.imwrite(str(self.image_path(aid, "annotated")), annotated, q)
        cv2.imwrite(str(self.image_path(aid, "thumb")), _thumbnail(original), q)
        return self.get_analysis(aid, user_id)

    def image_path(self, analysis_id: int, kind: str) -> Path:
        if kind not in IMAGE_KINDS:
            raise ValueError(kind)
        return self.images / f"{analysis_id}_{kind}.jpg"

    def access_key(self, analysis_id: int) -> str | None:
        """Clave secreta de las imágenes y el PDF de un análisis (se envía en la URL)."""
        rows = self._all("SELECT access_key FROM analyses WHERE id = ? AND user_id IS NOT NULL", (analysis_id,))
        return rows[0]["access_key"] if rows else None

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

    def get_analysis(self, analysis_id: int, user_id: int, with_colonies: bool = True) -> dict | None:
        rows = self._all(self._ANALYSIS_SELECT + " WHERE a.id = ? AND a.user_id = ?", (analysis_id, user_id))
        return self._decode(rows[0], with_colonies) if rows else None

    def get_analysis_by_key(self, analysis_id: int, key: str) -> dict | None:
        expected = self.access_key(analysis_id)
        if not (expected and key and hmac.compare_digest(expected.encode(), key.encode())):
            return None
        rows = self._all(self._ANALYSIS_SELECT + " WHERE a.id = ?", (analysis_id,))
        return self._decode(rows[0], True) if rows else None

    def list_analyses(self, user_id: int, project_id: int | None = None, query: str = "",
                      limit: int = 50, offset: int = 0) -> list[dict]:
        where, params = ["a.user_id = ?"], [user_id]
        if project_id is not None:
            where.append("a.project_id = ?")
            params.append(project_id)
        if query:
            where.append("(a.sample_name LIKE ? OR p.name LIKE ?)")
            params += [f"%{query}%", f"%{query}%"]
        sql = self._ANALYSIS_SELECT + " WHERE " + " AND ".join(where)
        sql += " ORDER BY a.created_at DESC, a.id DESC LIMIT ? OFFSET ?"
        return [self._decode(r, False) for r in self._all(sql, (*params, limit, offset))]

    def update_analysis(self, analysis_id: int, user_id: int, **fields) -> dict | None:
        allowed = {k: v for k, v in fields.items() if k in ("sample_name", "notes", "project_id")}
        if "project_id" in allowed and allowed["project_id"] == 0:
            allowed["project_id"] = None  # 0 = quitar del proyecto
        allowed = {k: v for k, v in allowed.items() if v is not None or k == "project_id"}
        if allowed:
            sets = ", ".join(f"{k} = ?" for k in allowed)
            self._exec(f"UPDATE analyses SET {sets} WHERE id = ? AND user_id = ?",
                       (*allowed.values(), analysis_id, user_id))
        return self.get_analysis(analysis_id, user_id)

    def _remove_images(self, analysis_id: int) -> None:
        for kind in IMAGE_KINDS:
            self.image_path(analysis_id, kind).unlink(missing_ok=True)

    def delete_analysis(self, analysis_id: int, user_id: int) -> bool:
        ok = self._exec("DELETE FROM analyses WHERE id = ? AND user_id = ?", (analysis_id, user_id)).rowcount > 0
        if ok:
            self._remove_images(analysis_id)
        return ok

    # ---------------------------------------------------------------- resumen
    def stats(self, user_id: int) -> dict:
        return self._all("""SELECT COUNT(*) AS analyses, COALESCE(SUM(total), 0) AS colonies,
                                   (SELECT COUNT(*) FROM projects WHERE user_id = ?) AS projects
                            FROM analyses WHERE user_id = ?""", (user_id, user_id))[0]

    # ---------------------------------------------------------------- datos sin dueño
    def orphans(self) -> dict:
        """Proyectos y análisis creados antes de las cuentas de usuario."""
        return self._all("""SELECT (SELECT COUNT(*) FROM analyses WHERE user_id IS NULL) AS analyses,
                                   (SELECT COUNT(*) FROM projects WHERE user_id IS NULL) AS projects""")[0]

    def assign_orphans(self, user_id: int) -> dict:
        n = self.orphans()
        self._exec("UPDATE analyses SET user_id = ? WHERE user_id IS NULL", (user_id,))
        self._exec("UPDATE projects SET user_id = ? WHERE user_id IS NULL", (user_id,))
        return n

    def delete_orphans(self) -> dict:
        n = self.orphans()
        for r in self._all("SELECT id FROM analyses WHERE user_id IS NULL"):
            self._remove_images(r["id"])
        self._exec("DELETE FROM analyses WHERE user_id IS NULL")
        self._exec("DELETE FROM projects WHERE user_id IS NULL")
        return n
