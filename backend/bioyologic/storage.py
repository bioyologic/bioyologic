"""Persistencia: usuarios, proyectos y análisis en SQLite + imágenes en disco.

    <root>/bioyologic.db
    <root>/images/<id>_original.jpg | <id>_annotated.jpg | <id>_thumb.jpg

Cada proyecto y análisis pertenece a un usuario (`user_id`). Un proyecto se puede compartir con otras
cuentas (`project_members`, rol analista o revisor): sus miembros ven y analizan las placas del proyecto, y
los revisores (y el dueño) aprueban o devuelven los análisis de los demás. Todo lo que no está en un
proyecto compartido solo lo ve su autor. Los datos anteriores a las cuentas quedan sin dueño (`user_id`
NULL): nadie los ve hasta que se asignan o se borran con `python -m bioyologic.manage`.

Las siembras en incubación (`incubations`) recuerdan cuándo leer las placas.

Borrar un análisis lo manda a la papelera (`deleted_at`): deja de verse en todas partes, pero su autor puede
recuperarlo durante TRASH_DAYS días. Después, o al vaciar la papelera, se borra definitivamente con sus fotos.
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
    consent_version TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS codes (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL,          -- verify | reset
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, purpose)
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
    sample_group TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    dilution REAL,
    volume_ml REAL,
    mm_per_px REAL,
    total INTEGER NOT NULL,
    cfu_per_ml REAL,
    status TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT '',
    reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reviewer_name TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT,
    review_note TEXT NOT NULL DEFAULT '',
    incubation_id INTEGER REFERENCES incubations(id) ON DELETE SET NULL,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS project_members (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,             -- analista | revisor (el dueño está en projects.user_id)
    added_at TEXT NOT NULL,
    PRIMARY KEY (project_id, user_id)
);
CREATE TABLE IF NOT EXISTS incubations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    sample_group TEXT NOT NULL DEFAULT '',
    plates INTEGER,
    seeded_at TEXT NOT NULL,
    hours REAL NOT NULL,
    temperature_c REAL,
    notes TEXT NOT NULL DEFAULT '',
    done_at TEXT,
    created_at TEXT NOT NULL
);
"""

# Columnas añadidas después de la primera versión: las bases existentes se migran al abrir.
MIGRATIONS = {
    # Las cuentas creadas antes de la verificación por correo quedan verificadas (DEFAULT 1).
    "users": {"email_verified": "INTEGER NOT NULL DEFAULT 1"},
    "projects": {"user_id": "INTEGER REFERENCES users(id) ON DELETE CASCADE"},
    "analyses": {"user_id": "INTEGER REFERENCES users(id) ON DELETE CASCADE", "access_key": "TEXT",
                 # Placas de una misma muestra (diluciones y réplicas) comparten este nombre.
                 "sample_group": "TEXT NOT NULL DEFAULT ''",
                 # Revisión en proyectos compartidos: '' (sin revisar) | aprobado | devuelto.
                 "review_status": "TEXT NOT NULL DEFAULT ''",
                 "reviewed_by": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
                 "reviewer_name": "TEXT NOT NULL DEFAULT ''",
                 "reviewed_at": "TEXT",
                 "review_note": "TEXT NOT NULL DEFAULT ''",
                 "incubation_id": "INTEGER REFERENCES incubations(id) ON DELETE SET NULL",
                 # Papelera: fecha en que se borró (NULL = activo).
                 "deleted_at": "TEXT"},
}

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_analyses_project ON analyses(project_id);
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at);
CREATE INDEX IF NOT EXISTS idx_analyses_user ON analyses(user_id);
CREATE INDEX IF NOT EXISTS idx_analyses_incubation ON analyses(incubation_id);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_members_user ON project_members(user_id);
CREATE INDEX IF NOT EXISTS idx_incubations_user ON incubations(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""

IMAGE_KINDS = ("original", "annotated", "thumb")
SESSION_DAYS = 30
USER_FIELDS = "id, email, name, role, institution, created_at, consent_at, consent_version, email_verified"
CODE_ATTEMPTS = 5  # intentos por código antes de invalidarlo
TRASH_DAYS = 30  # días que un análisis borrado se puede recuperar
MEMBER_ROLES = ("analista", "revisor")
REVIEW_STATES = ("aprobado", "devuelto")

# Proyectos a los que entra un usuario: los suyos y los compartidos con él (2 parámetros: user_id, user_id).
_MY_PROJECTS = "(SELECT id FROM projects WHERE user_id = ? UNION SELECT project_id FROM project_members WHERE user_id = ?)"


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
            if not self._db.execute("SELECT name FROM sqlite_master WHERE name = ?", (table,)).fetchone():
                continue
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
                       consent_at, consent_version, email_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (email, name, role, institution, hash_password(password), now, now, consent_version))
        # email_verified = 0 explícito: en bases migradas la columna tiene DEFAULT 1 (cuentas anteriores).
        except sqlite3.IntegrityError:
            return None
        return self.get_user(cur.lastrowid)

    def get_user(self, user_id: int) -> dict | None:
        rows = self._all(f"SELECT {USER_FIELDS} FROM users WHERE id = ?", (user_id,))
        if not rows:
            return None
        rows[0]["email_verified"] = bool(rows[0]["email_verified"])
        return rows[0]

    def user_by_email(self, email: str) -> dict | None:
        rows = self._all("SELECT id FROM users WHERE email = ?", (email,))
        return self.get_user(rows[0]["id"]) if rows else None

    def set_verified(self, user_id: int) -> None:
        self._exec("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))

    # ---------------------------------------------------------------- códigos de un solo uso
    def new_code(self, user_id: int, purpose: str, minutes: int) -> str:
        """Código de 6 dígitos (reemplaza al anterior del mismo tipo). Solo se guarda su hash."""
        code = f"{secrets.randbelow(10 ** 6):06d}"
        expires = (datetime.now().astimezone() + timedelta(minutes=minutes)).isoformat(timespec="seconds")
        self._exec("""INSERT INTO codes (user_id, purpose, code_hash, expires_at, attempts) VALUES (?, ?, ?, ?, 0)
                      ON CONFLICT (user_id, purpose) DO UPDATE SET code_hash = excluded.code_hash,
                      expires_at = excluded.expires_at, attempts = 0""",
                   (user_id, purpose, _token_hash(f"{purpose}:{user_id}:{code}"), expires))
        return code

    def check_code(self, user_id: int, purpose: str, code: str) -> bool:
        """True si el código es correcto y está vigente (y lo consume). Tras 5 fallos deja de servir."""
        rows = self._all("SELECT code_hash, expires_at, attempts FROM codes WHERE user_id = ? AND purpose = ?",
                         (user_id, purpose))
        if not rows:
            return False
        r = rows[0]
        if r["attempts"] >= CODE_ATTEMPTS or datetime.fromisoformat(r["expires_at"]) < datetime.now().astimezone():
            self._exec("DELETE FROM codes WHERE user_id = ? AND purpose = ?", (user_id, purpose))
            return False
        ok = hmac.compare_digest(r["code_hash"], _token_hash(f"{purpose}:{user_id}:{code.strip()}"))
        if ok:
            self._exec("DELETE FROM codes WHERE user_id = ? AND purpose = ?", (user_id, purpose))
        else:
            self._exec("UPDATE codes SET attempts = attempts + 1 WHERE user_id = ? AND purpose = ?", (user_id, purpose))
        return ok

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
        """Supresión total (Ley 1581): cuenta, sesiones, proyectos, análisis, siembras y fotos.

        Los análisis que otros miembros hicieron en sus proyectos compartidos siguen siendo de esos miembros
        (quedan sin proyecto), y en las revisiones que hizo su nombre se reemplaza."""
        for r in self._all("SELECT id FROM analyses WHERE user_id = ?", (user_id,)):
            self._remove_images(r["id"])
        self._exec("DELETE FROM analyses WHERE user_id = ?", (user_id,))
        self._exec("UPDATE analyses SET reviewer_name = 'Cuenta eliminada' WHERE reviewed_by = ?", (user_id,))
        self._exec("DELETE FROM incubations WHERE user_id = ?", (user_id,))
        self._exec("DELETE FROM projects WHERE user_id = ?", (user_id,))
        self._exec("DELETE FROM users WHERE id = ?", (user_id,))

    def export_user(self, user_id: int) -> dict:
        """Todo lo que el servidor guarda de un usuario, para el derecho de acceso."""
        return {"exported_at": _now(), "user": self.get_user(user_id),
                "projects": self.list_projects(user_id, own_only=True),
                "memberships": self._all(
                    """SELECT p.name AS project, m.role, m.added_at FROM project_members m
                       JOIN projects p ON p.id = m.project_id WHERE m.user_id = ?""", (user_id,)),
                "incubations": self._all("SELECT * FROM incubations WHERE user_id = ?", (user_id,)),
                "analyses": [self.get_analysis(a["id"], user_id)
                             for a in self.list_analyses(user_id, limit=1_000_000, mine_only=True)],
                "trash": self.list_trash(user_id)}

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
               COALESCE(SUM(CASE WHEN a.review_status = '' THEN 1 ELSE 0 END), 0) AS unreviewed_count,
               (SELECT COUNT(*) FROM project_members m WHERE m.project_id = p.id) AS members_count,
               (SELECT name FROM users u WHERE u.id = p.user_id) AS owner_name,
               (SELECT id FROM analyses WHERE project_id = p.id AND deleted_at IS NULL
                ORDER BY created_at DESC, id DESC LIMIT 1) AS cover_analysis_id,
               (SELECT access_key FROM analyses WHERE project_id = p.id AND deleted_at IS NULL
                ORDER BY created_at DESC, id DESC LIMIT 1) AS cover_access_key
        FROM projects p LEFT JOIN analyses a ON a.project_id = p.id AND a.deleted_at IS NULL
    """

    def _with_role(self, rows: list[dict], user_id: int) -> list[dict]:
        roles = self.roles(user_id)
        for p in rows:
            p["my_role"] = roles.get(p["id"], (None, False))[0]
        return rows

    def get_project(self, project_id: int, user_id: int) -> dict | None:
        """Proyecto propio o compartido con el usuario (`my_role`: owner | analista | revisor)."""
        rows = self._all(self._PROJECT_SELECT + f" WHERE p.id = ? AND p.id IN {_MY_PROJECTS} GROUP BY p.id",
                         (project_id, user_id, user_id))
        return self._with_role(rows, user_id)[0] if rows else None

    def list_projects(self, user_id: int, own_only: bool = False) -> list[dict]:
        where, params = (("p.user_id = ?", (user_id,)) if own_only
                         else (f"p.id IN {_MY_PROJECTS}", (user_id, user_id)))
        return self._with_role(self._all(
            self._PROJECT_SELECT + f" WHERE {where}"
            " GROUP BY p.id ORDER BY COALESCE(MAX(a.created_at), p.created_at) DESC", params), user_id)

    def roles(self, user_id: int) -> dict[int, tuple[str, bool]]:
        """{project_id: (rol del usuario, ¿compartido?)} de todos los proyectos a los que entra."""
        rows = self._all(
            """SELECT p.id, CASE WHEN p.user_id = ? THEN 'owner' ELSE m.role END AS role,
                      EXISTS (SELECT 1 FROM project_members x WHERE x.project_id = p.id) AS shared
               FROM projects p LEFT JOIN project_members m ON m.project_id = p.id AND m.user_id = ?
               WHERE p.user_id = ? OR m.user_id IS NOT NULL""", (user_id, user_id, user_id))
        return {r["id"]: (r["role"], bool(r["shared"])) for r in rows}

    def project_role(self, project_id: int | None, user_id: int) -> str | None:
        return None if project_id is None else self.roles(user_id).get(project_id, (None, False))[0]

    # ---------------------------------------------------------------- miembros de un proyecto
    def members(self, project_id: int) -> list[dict]:
        """Dueño y miembros del proyecto."""
        return self._all(
            """SELECT u.id AS user_id, u.name, u.email, 'owner' AS role, p.created_at AS added_at
               FROM projects p JOIN users u ON u.id = p.user_id WHERE p.id = ?
               UNION ALL
               SELECT u.id, u.name, u.email, m.role, m.added_at
               FROM project_members m JOIN users u ON u.id = m.user_id WHERE m.project_id = ?
               ORDER BY added_at""", (project_id, project_id))

    def set_member(self, project_id: int, user_id: int, role: str) -> None:
        if role not in MEMBER_ROLES:
            raise ValueError(role)
        self._exec("""INSERT INTO project_members (project_id, user_id, role, added_at) VALUES (?, ?, ?, ?)
                      ON CONFLICT (project_id, user_id) DO UPDATE SET role = excluded.role""",
                   (project_id, user_id, role, _now()))

    def remove_member(self, project_id: int, user_id: int) -> bool:
        return self._exec("DELETE FROM project_members WHERE project_id = ? AND user_id = ?",
                          (project_id, user_id)).rowcount > 0

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
                     notes: str = "", sample_group: str = "", incubation_id: int | None = None) -> dict:
        s = result["summary"]
        cur = self._exec(
            """INSERT INTO analyses (user_id, access_key, project_id, sample_name, sample_group, created_at,
                   dilution, volume_ml, mm_per_px, total, cfu_per_ml, status, notes, result_json, incubation_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, secrets.token_urlsafe(16), project_id, sample_name, sample_group.strip(),
             result.get("analyzed_at", _now()),
             dilution, volume_ml, result.get("mm_per_px"), s["total"], s["cfu_per_ml"], s["status"], notes,
             json.dumps(result, ensure_ascii=False), incubation_id))
        aid = cur.lastrowid
        q = [cv2.IMWRITE_JPEG_QUALITY, 90]
        cv2.imwrite(str(self.image_path(aid, "original")), original, q)
        cv2.imwrite(str(self.image_path(aid, "annotated")), annotated, q)
        cv2.imwrite(str(self.image_path(aid, "thumb")), _thumbnail(original), q)
        if incubation_id is not None:
            # Siembra con número de placas: se da por leída cuando se analizaron todas.
            self._exec("""UPDATE incubations SET done_at = ? WHERE id = ? AND done_at IS NULL AND plates IS NOT NULL
                          AND plates <= (SELECT COUNT(*) FROM analyses WHERE incubation_id = ? AND deleted_at IS NULL)""",
                       (_now(), incubation_id, incubation_id))
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
        SELECT a.*, p.name AS project_name, u.name AS author_name,
               (SELECT COUNT(*) FROM project_members m WHERE m.project_id = a.project_id) AS project_members
        FROM analyses a
        LEFT JOIN projects p ON p.id = a.project_id
        LEFT JOIN users u ON u.id = a.user_id
    """
    # Visible para el usuario: suyo o de un proyecto al que entra, y fuera de la papelera (3 parámetros: user_id × 3).
    _VISIBLE = f"(a.deleted_at IS NULL AND (a.user_id = ? OR a.project_id IN {_MY_PROJECTS}))"

    @staticmethod
    def _decode(row: dict, with_colonies: bool) -> dict:
        result = json.loads(row.pop("result_json"))
        row["summary"] = result["summary"]
        row["image_size"] = result.get("image_size")
        row["species"] = result.get("species")
        row["correction"] = result.get("correction")
        row["annotated_version"] = result.get("annotated_version", 0)
        row["quality"] = result.get("quality")
        row["incubation"] = result.get("incubation")
        # Revisión: solo tiene sentido en proyectos compartidos (sin miembros, nadie más revisa).
        estado = row.pop("review_status", "")
        row.pop("reviewed_by", None)
        quien, cuando, nota = row.pop("reviewer_name", ""), row.pop("reviewed_at", None), row.pop("review_note", "")
        if estado:
            row["review"] = {"status": estado, "by": quien, "at": cuando, "note": nota}
        else:
            row["review"] = {"status": "pendiente"} if row.get("project_members") else None
        row["shared"] = bool(row.pop("project_members", 0))
        if with_colonies:
            row["colonies"] = result["colonies"]
            # Detecciones del modelo que el usuario quitó a mano (para mostrarlas y poder restaurarlas).
            quitadas = set((result.get("correction") or {}).get("removed", []))
            row["removed_colonies"] = [c for c in result.get("detected_colonies", []) if c["id"] in quitadas]
        return row

    def get_analysis(self, analysis_id: int, user_id: int, with_colonies: bool = True) -> dict | None:
        """Análisis propio o de un proyecto compartido con el usuario."""
        rows = self._all(self._ANALYSIS_SELECT + f" WHERE a.id = ? AND {self._VISIBLE}",
                         (analysis_id, user_id, user_id, user_id))
        return self._decode(rows[0], with_colonies) if rows else None

    def result_of(self, analysis_id: int, user_id: int) -> dict | None:
        """Resultado completo guardado (incluye las detecciones originales si hubo corrección)."""
        rows = self._all(f"SELECT result_json FROM analyses a WHERE a.id = ? AND {self._VISIBLE}",
                         (analysis_id, user_id, user_id, user_id))
        return json.loads(rows[0]["result_json"]) if rows else None

    def save_result(self, analysis_id: int, user_id: int, result: dict, annotated: np.ndarray) -> dict | None:
        """Guarda un resultado recalculado (corrección manual) y su nueva imagen anotada.

        Quien llama comprueba antes que el usuario puede corregir. Si cambia el conteo, una aprobación
        anterior deja de valer: el análisis vuelve a quedar pendiente de revisión."""
        s = result["summary"]
        self._exec("""UPDATE analyses SET total = ?, cfu_per_ml = ?, status = ?, result_json = ?,
                          review_status = '', reviewed_by = NULL, reviewer_name = '', reviewed_at = NULL,
                          review_note = ''
                      WHERE id = ?""",
                   (s["total"], s["cfu_per_ml"], s["status"], json.dumps(result, ensure_ascii=False), analysis_id))
        cv2.imwrite(str(self.image_path(analysis_id, "annotated")), annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return self.get_analysis(analysis_id, user_id)

    def set_review(self, analysis_id: int, reviewer: dict | None, status: str, note: str = "") -> None:
        """Aprueba o devuelve un análisis (status '' borra la revisión)."""
        if status and status not in REVIEW_STATES:
            raise ValueError(status)
        if not status:
            reviewer, note = None, ""
        self._exec("""UPDATE analyses SET review_status = ?, reviewed_by = ?, reviewer_name = ?, reviewed_at = ?,
                          review_note = ? WHERE id = ?""",
                   (status, reviewer["id"] if reviewer else None, reviewer["name"] if reviewer else "",
                    _now() if status else None, note, analysis_id))

    def get_analysis_by_key(self, analysis_id: int, key: str) -> dict | None:
        expected = self.access_key(analysis_id)
        if not (expected and key and hmac.compare_digest(expected.encode(), key.encode())):
            return None
        rows = self._all(self._ANALYSIS_SELECT + " WHERE a.id = ? AND a.deleted_at IS NULL", (analysis_id,))
        return self._decode(rows[0], True) if rows else None

    def list_analyses(self, user_id: int, project_id: int | None = None, query: str = "",
                      limit: int = 50, offset: int = 0, mine_only: bool = False,
                      to_review: bool = False) -> list[dict]:
        """Análisis visibles (propios y de proyectos compartidos), o solo los propios con `mine_only`.

        `to_review`: los de otros miembros, sin revisar, en proyectos compartidos donde el usuario es dueño o
        revisor."""
        if mine_only:
            where, params = ["a.user_id = ? AND a.deleted_at IS NULL"], [user_id]
        else:
            where, params = [self._VISIBLE], [user_id, user_id, user_id]
        if to_review:
            where.append("""a.review_status = '' AND a.user_id != ? AND a.project_id IN (
                SELECT id FROM projects WHERE user_id = ?
                    AND EXISTS (SELECT 1 FROM project_members m WHERE m.project_id = projects.id)
                UNION SELECT project_id FROM project_members WHERE user_id = ? AND role = 'revisor')""")
            params += [user_id, user_id, user_id]
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
        allowed = {k: v for k, v in fields.items() if k in ("sample_name", "notes", "project_id", "sample_group")}
        if isinstance(allowed.get("sample_group"), str):
            allowed["sample_group"] = allowed["sample_group"].strip()
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
        """Manda el análisis a la papelera (solo su autor). Las fotos se conservan hasta que se vacía."""
        return self._exec("UPDATE analyses SET deleted_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                          (_now(), analysis_id, user_id)).rowcount > 0

    # ---------------------------------------------------------------- papelera
    def list_trash(self, user_id: int) -> list[dict]:
        """Análisis borrados por el usuario, el más reciente primero."""
        self.purge_expired()
        rows = self._all(self._ANALYSIS_SELECT + " WHERE a.user_id = ? AND a.deleted_at IS NOT NULL"
                         " ORDER BY a.deleted_at DESC, a.id DESC", (user_id,))
        out = []
        for r in rows:
            r = self._decode(r, False)
            r["purge_at"] = (datetime.fromisoformat(r["deleted_at"]) + timedelta(days=TRASH_DAYS)).isoformat(
                timespec="seconds")
            out.append(r)
        return out

    def restore_analyses(self, user_id: int, ids: list[int]) -> int:
        """Saca análisis de la papelera. Vuelven a su proyecto si sigue existiendo."""
        n = 0
        for aid in set(ids):
            n += self._exec("UPDATE analyses SET deleted_at = NULL WHERE id = ? AND user_id = ? AND deleted_at IS NOT NULL",
                            (aid, user_id)).rowcount
        return n

    def purge_analyses(self, user_id: int, ids: list[int] | None = None) -> int:
        """Borra definitivamente (con fotos) análisis de la papelera; sin `ids`, la vacía entera."""
        rows = self._all("SELECT id FROM analyses WHERE user_id = ? AND deleted_at IS NOT NULL", (user_id,))
        objetivo = [r["id"] for r in rows if ids is None or r["id"] in set(ids)]
        for aid in objetivo:
            self._exec("DELETE FROM analyses WHERE id = ?", (aid,))
            self._remove_images(aid)
        return len(objetivo)

    def purge_expired(self, days: int = TRASH_DAYS) -> int:
        """Borra definitivamente lo que lleva más de `days` días en la papelera."""
        limite = datetime.now().astimezone() - timedelta(days=days)
        viejos = [r["id"] for r in self._all("SELECT id, deleted_at FROM analyses WHERE deleted_at IS NOT NULL")
                  if datetime.fromisoformat(r["deleted_at"]) < limite]
        for aid in viejos:
            self._exec("DELETE FROM analyses WHERE id = ?", (aid,))
            self._remove_images(aid)
        return len(viejos)

    def sample_plates(self, user_id: int, project_id: int | None = None, group: str | None = None) -> list[dict]:
        """Placas que pertenecen a alguna muestra (sample_group no vacío), para agruparlas y combinarlas.

        En un proyecto compartido entran las placas de todos sus miembros."""
        where, params = [self._VISIBLE, "a.sample_group != ''"], [user_id, user_id, user_id]
        if project_id is not None:
            where.append("a.project_id = ?")
            params.append(project_id)
        if group is not None:
            where.append("a.sample_group = ?")
            params.append(group.strip())
        return self._all(
            """SELECT a.id, a.sample_name, a.sample_group, a.project_id, p.name AS project_name, a.created_at,
                      a.dilution, a.volume_ml, a.total, a.status, a.cfu_per_ml, a.access_key
               FROM analyses a LEFT JOIN projects p ON p.id = a.project_id
               WHERE """ + " AND ".join(where) + " ORDER BY a.created_at, a.id", tuple(params))

    def groups(self, user_id: int, project_id: int | None = None) -> list[str]:
        """Nombres de muestra ya usados (para sugerirlos al crear un análisis)."""
        sql = f"SELECT DISTINCT sample_group FROM analyses a WHERE {self._VISIBLE} AND sample_group != ''"
        params: tuple = (user_id, user_id, user_id)
        if project_id is not None:
            sql += " AND project_id = ?"
            params += (project_id,)
        return [r["sample_group"] for r in self._all(sql + " ORDER BY sample_group", params)]

    # ---------------------------------------------------------------- siembras en incubación
    _INCUBATION_SELECT = """
        SELECT i.*, p.name AS project_name, u.name AS created_by,
               (SELECT COUNT(*) FROM analyses x WHERE x.incubation_id = i.id AND x.deleted_at IS NULL) AS analyses_count
        FROM incubations i
        LEFT JOIN projects p ON p.id = i.project_id
        LEFT JOIN users u ON u.id = i.user_id
    """
    _INC_VISIBLE = f"(i.user_id = ? OR i.project_id IN {_MY_PROJECTS})"

    def create_incubation(self, user_id: int, *, name: str, hours: float, seeded_at: str | None = None,
                          project_id: int | None = None, sample_group: str = "", plates: int | None = None,
                          temperature_c: float | None = None, notes: str = "") -> dict:
        now = _now()
        cur = self._exec(
            """INSERT INTO incubations (user_id, project_id, name, sample_group, plates, seeded_at, hours,
                   temperature_c, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, project_id, name, sample_group.strip(), plates, seeded_at or now, hours, temperature_c,
             notes, now))
        return self.get_incubation(cur.lastrowid, user_id)

    def get_incubation(self, incubation_id: int, user_id: int) -> dict | None:
        rows = self._all(self._INCUBATION_SELECT + f" WHERE i.id = ? AND {self._INC_VISIBLE}",
                         (incubation_id, user_id, user_id, user_id))
        return rows[0] if rows else None

    def list_incubations(self, user_id: int, include_done: bool = False) -> list[dict]:
        """Siembras propias y de proyectos compartidos; sin `include_done`, solo las que faltan por leer."""
        where = f"{self._INC_VISIBLE}" + ("" if include_done else " AND i.done_at IS NULL")
        return self._all(self._INCUBATION_SELECT + f" WHERE {where} ORDER BY i.done_at IS NOT NULL, "
                         "datetime(i.seeded_at, '+' || CAST(i.hours * 60 AS INTEGER) || ' minutes'), i.id",
                         (user_id, user_id, user_id))

    def update_incubation(self, incubation_id: int, user_id: int, **fields) -> dict | None:
        allowed = {k: v for k, v in fields.items()
                   if k in ("name", "hours", "temperature_c", "notes", "plates", "done_at", "seeded_at")
                   and (v is not None or k in ("done_at", "temperature_c", "plates"))}
        if allowed:
            sets = ", ".join(f"{k} = ?" for k in allowed)
            self._exec(f"UPDATE incubations SET {sets} WHERE id = ?", (*allowed.values(), incubation_id))
        return self.get_incubation(incubation_id, user_id)

    def delete_incubation(self, incubation_id: int, user_id: int) -> bool:
        """Solo quien creó la siembra la borra; sus análisis se conservan."""
        return self._exec("DELETE FROM incubations WHERE id = ? AND user_id = ?",
                          (incubation_id, user_id)).rowcount > 0

    # ---------------------------------------------------------------- resumen
    def stats(self, user_id: int) -> dict:
        return self._all(f"""SELECT COUNT(*) AS analyses, COALESCE(SUM(total), 0) AS colonies,
                                    (SELECT COUNT(*) FROM projects WHERE id IN {_MY_PROJECTS}) AS projects
                             FROM analyses WHERE user_id = ? AND deleted_at IS NULL""", (user_id, user_id, user_id))[0]

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
