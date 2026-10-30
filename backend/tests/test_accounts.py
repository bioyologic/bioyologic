"""Cuentas de usuario y protección de datos personales (Ley 1581 de 2012)."""

import sqlite3

import cv2
import numpy as np
from fastapi.testclient import TestClient

from bioyologic.api.main import app
from bioyologic.storage import Store, check_password, hash_password

from .test_api import _register, _upload, ctx  # noqa: F401  (ctx es un fixture)


def _client(token: str | None = None) -> TestClient:
    c = TestClient(app)
    if token:
        c.headers["Authorization"] = f"Bearer {token}"
    return c


def test_requires_login(ctx):
    anon = _client()
    for path in ("/analyses", "/projects", "/stats", "/auth/me"):
        assert anon.get(path).status_code == 401
    assert anon.get("/analyses", headers={"Authorization": "Bearer inventado"}).status_code == 401
    # Lo público sigue abierto
    assert anon.get("/health").status_code == 200
    assert anon.get("/library").status_code == 200


def test_each_user_sees_only_their_data(ctx):
    client, jpg, _ = ctx
    p = client.post("/projects", json={"name": "Mío"}).json()
    a = _upload(client, jpg, project_id=p["id"]).json()

    other = _client(_register(client, "beto@lab.co")["token"])
    assert other.get("/analyses").json() == []
    assert other.get("/projects").json() == []
    assert other.get("/stats").json() == {"analyses": 0, "colonies": 0, "projects": 0}
    # Ni leer, ni editar, ni borrar lo ajeno
    assert other.get(f"/analyses/{a['id']}").status_code == 404
    assert other.patch(f"/analyses/{a['id']}", json={"notes": "x"}).status_code == 404
    assert other.delete(f"/analyses/{a['id']}").status_code == 404
    assert other.get(f"/projects/{p['id']}").status_code == 404
    assert other.delete(f"/projects/{p['id']}").status_code == 404
    # Ni guardar un análisis en un proyecto ajeno
    assert _upload(other, jpg, project_id=p["id"]).status_code == 404
    # El dueño conserva todo
    assert client.get(f"/analyses/{a['id']}").status_code == 200
    assert len(client.get("/analyses").json()) == 1


def test_images_need_the_secret_key(ctx):
    client, jpg, _ = ctx
    a = _upload(client, jpg).json()
    url, report = a["image_urls"]["thumb"], a["report_url"]
    assert "key=" in url and "access_key" not in a and "user_id" not in a
    anon = _client()
    # Con la clave funcionan sin token (así las abre la app y el navegador)
    assert anon.get(url).status_code == 200
    assert anon.get(report).content[:4] == b"%PDF"
    # Sin clave o con otra, no
    assert anon.get(f"/analyses/{a['id']}/image/thumb").status_code == 404
    assert anon.get(f"/analyses/{a['id']}/image/thumb?key=otra").status_code == 404
    assert anon.get(f"/analyses/{a['id']}/image/thumb?key=ñandú").status_code == 404
    assert anon.get(f"/analyses/{a['id']}/report.pdf?key=otra").status_code == 404


def test_register_login_logout(ctx):
    client, _, _ = ctx
    anon = _client()
    # Consentimiento obligatorio, correo válido y único, contraseña de 8+ caracteres
    base = {"email": "c@lab.co", "password": "clave-segura-1", "name": "C"}
    assert anon.post("/auth/register", json=base | {"accept_privacy": False}).status_code == 422
    assert anon.post("/auth/register", json=base | {"email": "no-es-correo", "accept_privacy": True}).status_code == 422
    assert anon.post("/auth/register", json=base | {"password": "corta", "accept_privacy": True}).status_code == 422
    assert anon.post("/auth/register", json=base | {"email": "ANA@lab.co", "accept_privacy": True}).status_code == 409

    me = client.get("/auth/me").json()
    assert me["email"] == "ana@lab.co" and me["consent_version"] and "password_hash" not in me

    assert anon.post("/auth/login", json={"email": "ana@lab.co", "password": "mala"}).status_code == 401
    assert anon.post("/auth/login", json={"email": "nadie@lab.co", "password": "x"}).status_code == 401
    tok = anon.post("/auth/login", json={"email": " Ana@Lab.co ", "password": "clave-segura-1"}).json()["token"]
    second = _client(tok)
    assert second.get("/auth/me").status_code == 200
    assert second.post("/auth/logout").status_code == 204
    assert second.get("/auth/me").status_code == 401
    assert client.get("/auth/me").status_code == 200  # la otra sesión sigue viva


def test_update_profile_and_password(ctx):
    client, _, _ = ctx
    me = client.patch("/auth/me", json={"name": "Ana P.", "institution": "PUJ"}).json()
    assert me["name"] == "Ana P." and me["institution"] == "PUJ"
    assert client.post("/auth/me/password", json={"current_password": "mala", "new_password": "otra-clave-2"}
                       ).status_code == 403
    assert client.post("/auth/me/password", json={"current_password": "clave-segura-1",
                                                  "new_password": "otra-clave-2"}).status_code == 204
    # Cambiar la contraseña cierra todas las sesiones
    assert client.get("/auth/me").status_code == 401
    assert _client().post("/auth/login", json={"email": "ana@lab.co", "password": "otra-clave-2"}).status_code == 200


def test_export_my_data(ctx):
    client, jpg, labels = ctx
    _upload(client, jpg)
    url = client.post("/auth/me/export-link").json()["url"]
    r = _client().get(url)  # el navegador lo abre sin token
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["user"]["email"] == "ana@lab.co"
    assert len(data["analyses"]) == 1 and len(data["analyses"][0]["colonies"]) == len(labels)
    assert _client().get(url).status_code == 404  # un solo uso


def test_delete_account_erases_everything(ctx, tmp_path):
    client, jpg, _ = ctx
    a = _upload(client, jpg).json()
    thumb = a["image_urls"]["thumb"]
    assert client.request("DELETE", "/auth/me", json={"password": "mala"}).status_code == 403
    assert client.request("DELETE", "/auth/me", json={"password": "clave-segura-1"}).status_code == 204
    assert client.get("/auth/me").status_code == 401
    assert _client().get(thumb).status_code == 404
    assert not list((tmp_path / "images").glob(f"{a['id']}_*"))
    # El correo queda libre para registrarse de nuevo
    assert _client().post("/auth/register", json={"email": "ana@lab.co", "password": "clave-segura-1",
                                                  "name": "Ana", "accept_privacy": True}).status_code == 201


def test_password_hash():
    h = hash_password("secreto123")
    assert h.startswith("scrypt$") and "secreto123" not in h
    assert check_password("secreto123", h) and not check_password("otro", h)
    assert hash_password("secreto123") != h  # sal distinta cada vez


def test_legacy_database_migrates_without_owner(tmp_path):
    """Una base de la versión sin cuentas se abre, y sus datos quedan ocultos hasta asignarlos."""
    db = sqlite3.connect(tmp_path / "bioyologic.db")
    db.executescript("""
        CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', target_samples INTEGER NOT NULL DEFAULT 10,
            created_at TEXT NOT NULL);
        CREATE TABLE analyses (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER,
            sample_name TEXT NOT NULL, created_at TEXT NOT NULL, dilution REAL, volume_ml REAL,
            mm_per_px REAL, total INTEGER NOT NULL, cfu_per_ml REAL, status TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '', result_json TEXT NOT NULL);
        INSERT INTO projects (name, created_at) VALUES ('Prueba', '2026-10-01T00:00:00');
        INSERT INTO analyses (project_id, sample_name, created_at, total, status, result_json)
            VALUES (1, 'Caja de prueba', '2026-10-01T00:00:00', 5, 'contable',
                    '{"summary": {"total": 5}, "colonies": []}');
    """)
    db.commit()
    db.close()
    cv2.imwrite(str(tmp_path / "1_thumb.jpg"), np.zeros((4, 4, 3), np.uint8))

    store = Store(tmp_path)
    assert store.orphans() == {"analyses": 1, "projects": 1}
    assert store.access_key(1) is None  # sin dueño, ni siquiera sus imágenes son accesibles
    user = store.create_user(email="a@b.co", password="clave-segura-1", name="A", consent_version="t")
    assert store.list_analyses(user["id"]) == []
    store.assign_orphans(user["id"])
    assert [a["sample_name"] for a in store.list_analyses(user["id"])] == ["Caja de prueba"]
    assert store.access_key(1)
    assert store.orphans() == {"analyses": 0, "projects": 0}
    store.close()


def test_login_rate_limit(ctx, monkeypatch):
    from bioyologic.api import main
    monkeypatch.setattr(main, "LOGIN_LIMIT", 3)
    monkeypatch.setattr(main, "_hits", main.defaultdict(main.deque))
    anon = _client()
    codes = [anon.post("/auth/login", json={"email": "ana@lab.co", "password": "mala"}).status_code
             for _ in range(4)]
    assert codes == [401, 401, 401, 429]
