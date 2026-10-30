"""Corrección manual del conteo, verificación del correo y recuperación de la contraseña."""

import re

import pytest
from fastapi.testclient import TestClient

from bioyologic import mailer
from bioyologic.api.main import app

from .test_api import _register, _upload, ctx  # noqa: F401  (ctx es un fixture)


def _client(token: str | None = None) -> TestClient:
    c = TestClient(app)
    if token:
        c.headers["Authorization"] = f"Bearer {token}"
    return c


# ------------------------------------------------------------------ corrección manual
def test_manual_correction_recounts_and_is_traceable(ctx):
    client, jpg, labels = ctx
    a = _upload(client, jpg, dilution=0.001, volume_ml=0.1).json()
    n = a["summary"]["total"]
    ids = [c["id"] for c in a["colonies"]]
    x, y = a["image_size"][0] / 2, a["image_size"][1] / 2

    r = client.put(f"/analyses/{a['id']}/colonies",
                   json={"removed": ids[:2], "added": [{"x": x, "y": y, "r": 12}]})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["summary"]["total"] == n - 1
    assert c["summary"]["cfu_per_ml"] == pytest.approx((n - 1) / 1e-4)
    assert c["correction"]["detected_total"] == n
    assert c["correction"]["removed"] == ids[:2] and len(c["correction"]["added"]) == 1
    assert c["correction"]["by"] == "Ana Pérez"  # el nombre, no el correo
    assert [col["id"] for col in c["removed_colonies"]] == ids[:2]
    manual = [col for col in c["colonies"] if col.get("manual")]
    assert len(manual) == 1 and manual[0]["morphology"]["diameter_px"] > 0
    assert c["image_urls"]["annotated"].endswith("&v=1")  # la app no usa la imagen vieja de caché
    assert client.get(c["image_urls"]["annotated"]).content[:2] == b"\xff\xd8"
    assert client.get(c["report_url"]).content[:4] == b"%PDF"
    # El listado y las estadísticas usan el conteo corregido
    assert client.get("/analyses").json()[0]["summary"]["total"] == n - 1

    # Corregir de nuevo parte siempre de lo que detectó el modelo; listas vacías = deshacer
    again = client.put(f"/analyses/{a['id']}/colonies", json={"removed": [ids[0]], "added": []}).json()
    assert again["summary"]["total"] == n - 1 and again["correction"]["removed"] == [ids[0]]
    undo = client.put(f"/analyses/{a['id']}/colonies", json={"removed": [], "added": []}).json()
    assert undo["summary"]["total"] == n and undo["correction"] is None
    assert undo["image_urls"]["annotated"].endswith("&v=3")


def test_manual_correction_validation(ctx):
    client, jpg, _ = ctx
    a = _upload(client, jpg).json()
    w, h = a["image_size"]
    url = f"/analyses/{a['id']}/colonies"
    assert client.put(url, json={"removed": [9999]}).status_code == 422
    assert client.put(url, json={"added": [{"x": w + 50, "y": 10, "r": 10}]}).status_code == 422
    assert client.put(url, json={"added": [{"x": 10, "y": 10, "r": w}]}).status_code == 422
    other = _client(_register(client, "otro@lab.co")["token"])
    assert other.put(url, json={"removed": []}).status_code == 404


# ------------------------------------------------------------------ correo
@pytest.fixture
def correo(monkeypatch):
    """Servidor con SMTP "configurado": los correos se guardan en una lista en vez de enviarse."""
    enviados = []
    monkeypatch.setenv("BIOYOLOGIC_SMTP_HOST", "smtp.prueba.test")
    monkeypatch.setattr(mailer, "send", lambda to, subject, text: enviados.append((to, subject, text)))
    return enviados


def _codigo(mail) -> str:
    return re.search(r"\b(\d{6})\b", mail[2]).group(1)


def test_email_verification_required_when_mail_is_configured(ctx, correo):
    client, jpg, _ = ctx  # ana@lab.co se creó sin SMTP: debe verificar ahora que el servidor envía correos
    body = _register(client, "nuevo@lab.co")
    assert body["user"]["email_verified"] is False and body["user"]["verification_required"] is True
    assert correo[-1][0] == "nuevo@lab.co" and "verificar" in correo[-1][1]
    nuevo = _client(body["token"])

    r = nuevo.get("/analyses")
    assert r.status_code == 403 and r.headers["x-bioyologic-reason"] == "email-not-verified"
    assert nuevo.get("/auth/me").status_code == 200  # el perfil sí se puede consultar
    assert nuevo.post("/auth/verify", json={"code": "000000"}).status_code == 400

    assert nuevo.post("/auth/verify/resend").status_code == 204
    me = nuevo.post("/auth/verify", json={"code": _codigo(correo[-1])}).json()
    assert me["email_verified"] is True
    assert nuevo.get("/analyses").status_code == 200


def test_code_stops_working_after_five_wrong_attempts(ctx, correo):
    client, _, _ = ctx
    nuevo = _client(_register(client, "nuevo@lab.co")["token"])
    code = _codigo(correo[-1])
    for _ in range(5):
        assert nuevo.post("/auth/verify", json={"code": "111111" if code != "111111" else "222222"}).status_code == 400
    assert nuevo.post("/auth/verify", json={"code": code}).status_code == 400


def test_password_recovery(ctx, correo):
    client, _, _ = ctx
    anon = _client()
    # Misma respuesta exista o no la cuenta (no revela qué correos están registrados)
    assert anon.post("/auth/password/forgot", json={"email": "nadie@lab.co"}).status_code == 204
    assert correo == []
    assert anon.post("/auth/password/forgot", json={"email": "ANA@lab.co"}).status_code == 204
    assert correo[-1][0] == "ana@lab.co" and "contraseña" in correo[-1][1]
    code = _codigo(correo[-1])

    bad = {"email": "ana@lab.co", "code": "000000" if code != "000000" else "999999", "new_password": "nueva-clave-1"}
    assert anon.post("/auth/password/reset", json=bad).status_code == 400
    r = anon.post("/auth/password/reset", json={"email": "ana@lab.co", "code": code, "new_password": "nueva-clave-1"})
    assert r.status_code == 200 and r.json()["user"]["email_verified"] is True
    assert client.get("/auth/me").status_code == 401  # la sesión anterior se cerró
    assert _client(r.json()["token"]).get("/analyses").status_code == 200
    assert anon.post("/auth/login", json={"email": "ana@lab.co", "password": "nueva-clave-1"}).status_code == 200
    # El código ya se usó
    assert anon.post("/auth/password/reset", json={"email": "ana@lab.co", "code": code,
                                                   "new_password": "otra-clave-22"}).status_code == 400


def test_without_mail_no_verification_and_no_recovery(ctx):
    client, _, _ = ctx
    me = client.get("/auth/me").json()
    assert me["verification_required"] is False
    assert client.get("/analyses").status_code == 200
    r = _client().post("/auth/password/forgot", json={"email": "ana@lab.co"})
    assert r.status_code == 503


def test_code_email_text():
    subject, text = mailer.code_email("123456", "reset", 15)
    assert "123456" in subject and "15 minutos" in text


def test_accounts_db_from_previous_version(tmp_path):
    """Base con cuentas pero sin verificación: las cuentas viejas quedan verificadas; las nuevas, no."""
    import sqlite3

    from bioyologic.storage import Store, hash_password

    db = sqlite3.connect(tmp_path / "bioyologic.db")
    db.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '', institution TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL, created_at TEXT NOT NULL, consent_at TEXT NOT NULL,
            consent_version TEXT NOT NULL);
    """)
    db.execute("INSERT INTO users (email, name, password_hash, created_at, consent_at, consent_version) "
               "VALUES ('vieja@lab.co', 'Vieja', ?, 'x', 'x', 'x')", (hash_password("clave-segura-1"),))
    db.commit()
    db.close()
    store = Store(tmp_path)
    assert store.user_by_email("vieja@lab.co")["email_verified"] is True
    nueva = store.create_user(email="nueva@lab.co", password="clave-segura-1", name="N", consent_version="t")
    assert nueva["email_verified"] is False
    store.close()


def test_report_with_special_characters_and_accents(ctx):
    """Nombres con tildes, < > y & y notas con saltos de línea: el PDF se genera y se puede descargar."""
    client, jpg, _ = ctx
    a = _upload(client, jpg, notes="Punto 3 <cerca del vertedero> & lluvia.\nRepetir si < 30.",
                **{"dilution": 0.0001, "volume_ml": 0.1}).json()
    client.patch(f"/analyses/{a['id']}", json={"sample_name": "Réplica <2> & ñandú · P01"})
    r = client.get(a["report_url"])
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    disp = r.headers["content-disposition"]
    assert disp.isascii() and "filename*=UTF-8''" in disp and "%C3%A9" in disp
    # El PDF se llama como el análisis (sin los caracteres que los sistemas no admiten en archivos)
    a2 = client.get(f"/analyses/{a['id']}").json()
    assert "/report/R%C3%A9plica%202%20%26%20%C3%B1and%C3%BA%20%C2%B7%20P01.pdf?key=" in a2["report_url"]
    assert "filename*=UTF-8''R%C3%A9plica%202%20%26%20%C3%B1and%C3%BA%20%C2%B7%20P01.pdf" in disp
    assert client.get(a2["report_url"]).content[:4] == b"%PDF"


def test_report_helpers():
    from bioyologic.report import _dilucion, _txt, _verbo
    assert _txt("a <b> & c\nd") == "a &lt;b&gt; &amp; c<br/>d"
    assert _dilucion(1e-4) == "1 × 10<super>-4</super>" and _dilucion(0.25) == "0,25"
    assert _verbo(1, "quitó", "quitaron") == "se quitó 1" and _verbo(2, "quitó", "quitaron") == "se quitaron 2"


def test_pdf_name():
    from bioyologic.api.main import pdf_name
    assert pdf_name("prueba e coli") == "prueba e coli.pdf"
    assert pdf_name("Caja 1/2: agua?") == "Caja 1 2 agua.pdf"
    assert pdf_name("   ") == "analisis.pdf"
