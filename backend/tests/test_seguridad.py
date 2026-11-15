"""Seguridad y rendimiento: cabeceras, límites por cuenta, fotos trampa, textos largos, Excel y listados."""

import csv
import io
import struct
from datetime import datetime, timedelta

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from bioyologic.api import main
from bioyologic.api.main import app
from bioyologic.export import build_csv
from bioyologic.storage import Store

from .test_api import _register, _upload, ctx  # noqa: F401  (ctx es un fixture)
from .test_correccion_y_correo import correo  # noqa: F401  (fixture)


def test_security_headers_on_every_response(ctx):
    client, jpg, _ = ctx
    for r in (client.get("/health"), client.get("/analyses"), TestClient(app).get("/analyses"),
              client.get("/no-existe")):
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert r.headers["Referrer-Policy"] == "no-referrer"  # las URLs con clave no salen del sitio
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
        assert "camera=(self)" in r.headers["Permissions-Policy"]
    # HSTS solo si la petición llegó por HTTPS (la cabecera la pone Caddy)
    assert "Strict-Transport-Security" not in client.get("/health").headers
    seguro = client.get("/health", headers={"X-Forwarded-Proto": "https"})
    assert seguro.headers["Strict-Transport-Security"] == main.HSTS
    # Los datos de la cuenta no se guardan en la caché del navegador...
    assert client.get("/analyses").headers["Cache-Control"] == "no-store"
    assert client.get("/auth/me").headers["Cache-Control"] == "no-store"
    # ...pero lo que sí debe guardarse conserva su propia regla
    a = _upload(client, jpg).json()
    assert "immutable" in client.get(a["image_urls"]["thumb"]).headers["Cache-Control"]
    assert client.get("/library").headers["Cache-Control"] == main.LIBRARY_CACHE


def test_account_locks_after_repeated_wrong_passwords(ctx, monkeypatch):
    monkeypatch.setattr(main, "LOGIN_FAILS", 3)
    anon = TestClient(app)
    mala = {"email": "ana@lab.co", "password": "no-es-esta-1"}
    buena = {"email": "Ana@Lab.co", "password": "clave-segura-1"}
    # Un acierto borra la cuenta de fallos
    assert [anon.post("/auth/login", json=mala).status_code for _ in range(2)] == [401, 401]
    assert anon.post("/auth/login", json=buena).status_code == 200
    assert [anon.post("/auth/login", json=mala).status_code for _ in range(3)] == [401, 401, 401]
    # Bloqueada: ni con la contraseña correcta, venga de la IP que venga
    assert anon.post("/auth/login", json=buena).status_code == 429
    assert anon.post("/auth/login", json=buena, headers={"X-Real-IP": "203.0.113.9"}).status_code == 429
    # Las demás cuentas no se enteran
    _register(anon, "beto@lab.co")
    assert anon.post("/auth/login", json={"email": "beto@lab.co", "password": "clave-segura-1"}).status_code == 200


def test_reset_password_unlocks_the_account(ctx, correo, monkeypatch):
    monkeypatch.setattr(main, "LOGIN_FAILS", 2)
    anon = TestClient(app)
    for _ in range(2):
        anon.post("/auth/login", json={"email": "ana@lab.co", "password": "no-es-esta-1"})
    assert anon.post("/auth/login", json={"email": "ana@lab.co", "password": "clave-segura-1"}).status_code == 429
    anon.post("/auth/password/forgot", json={"email": "ana@lab.co"})
    code = __import__("re").search(r"\b(\d{6})\b", correo[-1][2]).group(1)
    assert anon.post("/auth/password/reset", json={"email": "ana@lab.co", "code": code,
                                                   "new_password": "nueva-clave-9"}).status_code == 200
    assert anon.post("/auth/login", json={"email": "ana@lab.co", "password": "nueva-clave-9"}).status_code == 200


def test_few_code_emails_per_account(ctx, correo):
    """Nadie puede llenarle el buzón a otra persona pidiendo códigos sin parar."""
    anon = TestClient(app)
    codes = [anon.post("/auth/password/forgot", json={"email": "ana@lab.co"}).status_code for _ in range(6)]
    assert codes == [204] * 6  # la respuesta no cambia (no revela nada)
    assert len(correo) == main.MAIL_LIMIT


@pytest.mark.parametrize("password", ["12345678", "aaaaaaaa", "Password1", "carolina", "carolina@lab.co"])
def test_easy_passwords_are_rejected(ctx, password):
    r = TestClient(app).post("/auth/register", json={"email": "carolina@lab.co", "password": password,
                                                      "name": "Carolina", "accept_privacy": True})
    assert r.status_code == 422 and "fácil" in r.json()["detail"]


def test_easy_password_rejected_when_changing_it(ctx):
    client, _, _ = ctx
    r = client.post("/auth/me/password", json={"current_password": "clave-segura-1", "new_password": "11111111"})
    assert r.status_code == 422
    assert client.get("/auth/me").status_code == 200  # la sesión sigue: no se cambió nada


def test_image_pixels_reads_the_header():
    foto = np.zeros((300, 500, 3), np.uint8)
    assert main.image_pixels(cv2.imencode(".jpg", foto)[1].tobytes()) == 150_000
    assert main.image_pixels(cv2.imencode(".png", foto)[1].tobytes()) == 150_000
    assert main.image_pixels(b"no es una imagen") is None
    assert main.image_pixels(b"\xff\xd8\xff") is None  # JPEG cortado


def test_decompression_bomb_is_rejected_before_decoding(ctx, monkeypatch):
    """Un archivo de pocos KB que dice medir 40 000 × 40 000 px no llega a abrirse."""
    client, jpg, _ = ctx
    png = bytearray(cv2.imencode(".png", np.zeros((8, 8, 3), np.uint8))[1].tobytes())
    png[16:24] = struct.pack(">II", 40_000, 40_000)
    monkeypatch.setattr(cv2, "imdecode", lambda *a: pytest.fail("no debe decodificarse"))
    r = client.post("/analyses", files={"image": ("p.png", bytes(png), "image/png")}, data={"sample_name": "x"})
    assert r.status_code == 413 and "megapíxeles" in r.json()["detail"]


def test_photo_over_the_megapixel_limit(ctx, monkeypatch):
    client, jpg, _ = ctx
    monkeypatch.setattr(main, "MAX_MEGAPIXELS", 0.1)  # la placa de prueba mide 600 × 600 = 0,36 MP
    assert _upload(client, jpg).status_code == 413
    monkeypatch.setattr(main, "MAX_MEGAPIXELS", 64)
    assert _upload(client, jpg).status_code == 201
    assert client.post("/analyses", files={"image": ("p.jpg", b"basura", "image/jpeg")},
                       data={"sample_name": "x"}).status_code == 400


def test_analyses_wait_their_turn(ctx, monkeypatch):
    """Solo se analiza una foto a la vez; si la espera se alarga, el servidor lo dice en vez de colgarse."""
    client, jpg, _ = ctx
    monkeypatch.setattr(main, "QUEUE_SECONDS", 0.05)
    assert main._analysis_slots.acquire(timeout=1)  # otro análisis en curso
    try:
        r = _upload(client, jpg)
        assert r.status_code == 503 and "ocupado" in r.json()["detail"]
        assert client.get("/health").status_code == 200  # el resto del servidor sigue respondiendo
    finally:
        main._analysis_slots.release()
    assert _upload(client, jpg).status_code == 201


def test_list_limits_and_long_texts(ctx):
    client, jpg, _ = ctx
    for _ in range(3):
        assert _upload(client, jpg).status_code == 201
    # En SQLite «LIMIT -1» es «sin límite»: no se deja pasar
    assert len(client.get("/analyses", params={"limit": -1}).json()) == 1
    assert len(client.get("/analyses", params={"limit": 2, "offset": -5}).json()) == 2
    assert len(client.get("/analyses", params={"limit": 100_000}).json()) == 3
    # Textos libres con tope
    largo = "x" * (main.NOTES_MAX + 1)
    assert _upload(client, jpg, notes=largo).status_code == 422
    a = client.get("/analyses").json()[0]
    assert client.patch(f"/analyses/{a['id']}", json={"notes": largo}).status_code == 422
    assert client.patch(f"/analyses/{a['id']}", json={"notes": "x" * main.NOTES_MAX}).status_code == 200
    assert client.post("/projects", json={"name": "P", "description": largo}).status_code == 422


def test_csv_cells_cannot_be_formulas(ctx):
    client, jpg, _ = ctx
    p = client.post("/projects", json={"name": "+SUMA(A1)"}).json()
    a = _upload(client, jpg, project_id=p["id"], notes="@cmd\nsegunda línea").json()
    client.patch(f"/analyses/{a['id']}", json={"sample_name": "=HYPERLINK(\"http://malo\")"})
    quitar = client.get(f"/analyses/{a['id']}").json()["colonies"][0]["id"]
    client.put(f"/analyses/{a['id']}/colonies", json={"removed": [quitar], "added": []})
    filas = list(csv.reader(io.StringIO(build_csv(client.get("/analyses").json(), {}).decode("utf-8-sig")),
                            delimiter=";"))
    fila = dict(zip(filas[0], filas[1]))
    assert fila["Proyecto"] == "'+SUMA(A1)" and fila["Placa"].startswith("'=HYPERLINK")
    assert fila["Notas"] == "'@cmd segunda línea"
    assert fila["Corrección manual"] == "quitadas 1, agregadas 0"
    assert not any(c[:1] in "=+-@" for c in filas[1] if c)


def test_export_filename_is_cleaned(ctx):
    client, _, _ = ctx
    url = client.post("/export-link", json={}).json()["url"]
    token = url.split("token=")[1]
    r = TestClient(app).get(f"/export/a%0d%0aX-Mala:%201.csv?token={token}")
    assert r.status_code == 200 and "x-mala" not in r.headers
    assert "\r" not in r.headers["Content-Disposition"] and "\n" not in r.headers["Content-Disposition"]


def test_lists_do_not_read_the_colonies(tmp_path):
    """Los listados usan el resumen guardado aparte; las bases anteriores se rellenan al abrirlas."""
    store = Store(tmp_path)
    u = store.create_user(email="a@b.co", password="clave-segura-1", name="A", consent_version="t")
    result = {"summary": {"total": 2, "cfu_per_ml": None, "status": "pocas"}, "image_size": [8, 8],
              "colonies": [{"id": 1}, {"id": 2}], "detected_colonies": [{"id": 1}, {"id": 2}, {"id": 3}]}
    negro = np.zeros((8, 8, 3), np.uint8)
    a = store.add_analysis(user_id=u["id"], sample_name="Caja", result=result, original=negro, annotated=negro)
    assert len(a["colonies"]) == 2
    resumen = store._all("SELECT summary_json FROM analyses")[0]["summary_json"]
    assert "colonies" not in resumen and '"total": 2' in resumen
    # Con el resultado completo ilegible, listar sigue funcionando: no lo lee
    store._exec("UPDATE analyses SET result_json = '{roto'")
    assert store.list_analyses(u["id"])[0]["summary"]["total"] == 2
    assert store.get_analysis(a["id"], u["id"], with_colonies=False)["summary"]["status"] == "pocas"
    store.delete_analysis(a["id"], u["id"])
    assert store.list_trash(u["id"])[0]["summary"]["total"] == 2
    # Base de antes de esta versión: sin resumen
    import json
    store._exec("UPDATE analyses SET summary_json = NULL, result_json = ?", (json.dumps(result),))
    store.close()
    store = Store(tmp_path)
    assert '"total": 2' in store._all("SELECT summary_json FROM analyses")[0]["summary_json"]
    store.close()


def test_stale_sessions_and_codes_are_purged(tmp_path):
    store = Store(tmp_path)
    u = store.create_user(email="a@b.co", password="clave-segura-1", name="A", consent_version="t")
    vieja, nueva = store.create_session(u["id"]), store.create_session(u["id"])
    store.new_code(u["id"], "reset", 15)
    ayer = (datetime.now().astimezone() - timedelta(days=1)).isoformat(timespec="seconds")
    store._exec("UPDATE sessions SET expires_at = ? WHERE token_hash = ?", (ayer, __import__("hashlib").sha256(
        vieja.encode()).hexdigest()))
    store._exec("UPDATE codes SET expires_at = ?", (ayer,))
    assert store.purge_stale() == 2
    assert store.session_user(nueva)["id"] == u["id"] and store.session_user(vieja) is None
    assert store._all("SELECT COUNT(*) AS n FROM codes")[0]["n"] == 0
    store.close()


def test_rate_limit_memory_is_bounded(monkeypatch):
    monkeypatch.setattr(main, "_HITS_MAX", 50)
    for i in range(200):
        assert not main._too_many("auth", f"10.0.{i}.1", 5, record=False)  # consultas que no dejan huella
    main._too_many("auth", "198.51.100.7", 5)
    assert len(main._hits) <= 52
    # Y el límite sigue contando bien
    assert [main._too_many("x", "k", 2) for _ in range(3)] == [False, False, True]


def test_report_photo_is_reduced_for_the_pdf(tmp_path):
    from bioyologic.report import PDF_IMG_PX, _foto
    grande, chica = tmp_path / "g.jpg", tmp_path / "c.jpg"
    cv2.imwrite(str(grande), np.full((3000, 4000, 3), 120, np.uint8))
    cv2.imwrite(str(chica), np.full((600, 800, 3), 120, np.uint8))
    assert _foto(chica) == str(chica)
    reducida = cv2.imdecode(np.frombuffer(_foto(grande).getvalue(), np.uint8), cv2.IMREAD_COLOR)
    assert reducida.shape[:2] == (PDF_IMG_PX * 3 // 4, PDF_IMG_PX)
