"""Trabajo en equipo (proyectos compartidos con revisión) y siembras en incubación."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from bioyologic.api.main import app

from .test_api import _register, _upload, ctx  # noqa: F401  (ctx es un fixture)


def _cuenta(client, email: str, name: str) -> TestClient:
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {_register(client, email, name=name)['token']}"
    return c


def _equipo(client):
    """Ana (dueña) comparte su proyecto con Beto (analista) y Carla (revisora)."""
    beto = _cuenta(client, "beto@lab.co", "Beto Ruiz")
    carla = _cuenta(client, "carla@lab.co", "Carla Gómez")
    p = client.post("/projects", json={"name": "Agua de río"}).json()
    assert client.post(f"/projects/{p['id']}/members", json={"email": "BETO@lab.co"}).status_code == 201
    r = client.post(f"/projects/{p['id']}/members", json={"email": "carla@lab.co", "role": "revisor"})
    assert [m["role"] for m in r.json()] == ["owner", "analista", "revisor"]
    return p, beto, carla


def test_shared_project_members_see_and_add_plates(ctx):
    client, jpg, _ = ctx
    p, beto, carla = _equipo(client)
    otro = _cuenta(client, "intruso@lab.co", "Intruso")

    # Beto ve el proyecto compartido con su rol y sube una placa
    vista = beto.get("/projects").json()
    assert [(x["name"], x["my_role"], x["shared"]) for x in vista] == [("Agua de río", "analista", True)]
    a = _upload(beto, jpg, project_id=p["id"], sample_group="Punto 1", dilution=0.001, volume_ml=0.1).json()
    assert a["author_name"] == "Beto Ruiz" and a["is_mine"] and a["review"] == {"status": "pendiente"}

    # Ana y Carla lo ven; alguien de fuera no
    assert client.get(f"/analyses/{a['id']}").json()["is_mine"] is False
    assert [x["id"] for x in carla.get("/analyses", params={"project_id": p["id"]}).json()] == [a["id"]]
    assert otro.get(f"/analyses/{a['id']}").status_code == 404
    assert otro.get(f"/projects/{p['id']}/members").status_code == 404
    # La muestra combina placas de todos los miembros
    _upload(client, jpg, project_id=p["id"], sample_group="Punto 1", dilution=0.0001, volume_ml=0.1)
    assert len(carla.get("/samples", params={"project_id": p["id"]}).json()[0]["plates"]) == 2

    # Solo el autor edita o borra; solo la dueña administra el proyecto
    assert client.patch(f"/analyses/{a['id']}", json={"notes": "x"}).status_code == 403
    assert carla.delete(f"/analyses/{a['id']}").status_code == 403
    assert beto.patch(f"/projects/{p['id']}", json={"name": "Mío"}).status_code == 403
    assert beto.delete(f"/projects/{p['id']}").status_code == 403
    assert beto.post(f"/projects/{p['id']}/members", json={"email": "intruso@lab.co"}).status_code == 403
    # Los miembros ven nombres y roles, pero solo la dueña ve los correos
    assert {m["email"] for m in carla.get(f"/projects/{p['id']}/members").json()} == {None, "carla@lab.co"}
    assert client.post(f"/projects/{p['id']}/members", json={"email": "nadie@lab.co"}).status_code == 404


def test_review_flow_four_eyes_and_reset_after_correction(ctx):
    client, jpg, labels = ctx
    p, beto, carla = _equipo(client)
    a = _upload(beto, jpg, project_id=p["id"]).json()
    assert a["can_correct"] and not a["can_review"]

    # Carla (revisora) tiene la placa por revisar; Beto (analista) no puede revisar
    pendientes = carla.get("/analyses", params={"to_review": True}).json()
    assert [x["id"] for x in pendientes] == [a["id"]] and pendientes[0]["can_review"]
    assert beto.post(f"/analyses/{a['id']}/review", json={"status": "aprobado"}).status_code == 403
    # Devolver exige explicar qué corregir
    assert carla.post(f"/analyses/{a['id']}/review", json={"status": "devuelto"}).status_code == 422
    r = carla.post(f"/analyses/{a['id']}/review", json={"status": "devuelto", "note": "Hay un reflejo"})
    assert r.json()["review"]["status"] == "devuelto" and r.json()["review"]["by"] == "Carla Gómez"

    # Beto corrige: la revisión anterior deja de valer
    c = beto.put(f"/analyses/{a['id']}/colonies", json={"removed": [1], "added": []}).json()
    assert c["summary"]["total"] == len(labels) - 1 and c["review"] == {"status": "pendiente"}
    r = carla.post(f"/analyses/{a['id']}/review", json={"status": "aprobado"}).json()
    assert r["review"]["status"] == "aprobado"
    assert carla.get("/analyses", params={"to_review": True}).json() == []

    # El PDF y el CSV registran quién revisó
    assert client.get(r["report_url"]).content[:4] == b"%PDF"
    url = client.post("/export-link", json={"project_id": p["id"]}).json()["url"]
    csv = TestClient(app).get(url).content.decode("utf-8-sig")
    assert "Revisado por" in csv and "Carla Gómez" in csv and "Aprobado" in csv

    # Nadie aprueba su propio análisis, ni siquiera la dueña
    propio = _upload(client, jpg, project_id=p["id"]).json()
    assert client.post(f"/analyses/{propio['id']}/review", json={"status": "aprobado"}).status_code == 403
    assert carla.post(f"/analyses/{propio['id']}/review", json={"status": "aprobado"}).status_code == 200


def test_leaving_and_removing_members(ctx):
    client, jpg, _ = ctx
    p, beto, carla = _equipo(client)
    a = _upload(beto, jpg, project_id=p["id"]).json()
    # Beto sale: ya no ve el proyecto, pero su análisis sigue siendo suyo (y queda en el proyecto)
    me = beto.get("/auth/me").json()["id"]
    assert beto.delete(f"/projects/{p['id']}/members/{me}").status_code == 204
    assert beto.get("/projects").json() == []
    assert beto.get(f"/analyses/{a['id']}").status_code == 200
    assert client.get(f"/analyses/{a['id']}").status_code == 200
    # Carla no puede echar a nadie; la dueña sí
    carla_id = carla.get("/auth/me").json()["id"]
    otro = client.get(f"/projects/{p['id']}/members").json()
    assert carla.delete(f"/projects/{p['id']}/members/{otro[0]['user_id']}").status_code == 403
    assert client.delete(f"/projects/{p['id']}/members/{carla_id}").status_code == 204
    # Sin miembros el proyecto deja de ser compartido: no hay revisión
    assert client.get(f"/analyses/{a['id']}").json()["review"] is None


def test_deleting_owner_keeps_members_analyses(ctx):
    client, jpg, _ = ctx
    p, beto, _ = _equipo(client)
    a = _upload(beto, jpg, project_id=p["id"]).json()
    assert client.request("DELETE", "/auth/me", json={"password": "clave-segura-1"}).status_code == 204
    restante = beto.get(f"/analyses/{a['id']}").json()
    assert restante["project_id"] is None and beto.get("/projects").json() == []


def test_incubation_timer(ctx):
    client, jpg, _ = ctx
    p, beto, _ = _equipo(client)
    hace = (datetime.now().astimezone() - timedelta(hours=25)).isoformat()
    r = client.post("/incubations", json={"name": "Agua de río", "hours": 24, "temperature_c": 37,
                                          "seeded_at": hace, "project_id": p["id"], "plates": 2})
    assert r.status_code == 201, r.text
    inc = r.json()
    lista = datetime.fromisoformat(inc["ready_at"])
    assert abs((lista - datetime.fromisoformat(hace)).total_seconds() - 24 * 3600) < 1
    nueva = client.post("/incubations", json={"name": "Superficies", "hours": 48}).json()
    # Ordenadas: primero la que se lee antes; Beto ve la del proyecto compartido, no la personal de Ana
    assert [i["name"] for i in client.get("/incubations").json()] == ["Agua de río", "Superficies"]
    assert [i["name"] for i in beto.get("/incubations").json()] == ["Agua de río"]
    assert beto.delete(f"/incubations/{inc['id']}").status_code == 403

    # Cada placa analizada guarda cuántas horas incubó; con las 2 placas, la siembra se da por leída
    a = _upload(beto, jpg, project_id=p["id"], incubation_id=inc["id"]).json()
    assert a["incubation"]["hours"] == 24 and 24.9 <= a["incubation"]["read_after_hours"] <= 25.2
    assert client.get(a["report_url"]).content[:4] == b"%PDF"
    assert len(client.get("/incubations").json()) == 2
    _upload(client, jpg, project_id=p["id"], incubation_id=inc["id"])
    assert [i["name"] for i in client.get("/incubations").json()] == ["Superficies"]
    hechas = client.get("/incubations", params={"include_done": True}).json()
    assert hechas[-1]["name"] == "Agua de río" and hechas[-1]["analyses_count"] == 2

    # Marcar como leída a mano, y borrar
    assert client.patch(f"/incubations/{nueva['id']}", json={"done": True}).json()["done_at"]
    assert client.get("/incubations").json() == []
    assert client.delete(f"/incubations/{nueva['id']}").status_code == 204
    assert client.post("/incubations", json={"name": "x", "hours": 0}).status_code == 422
    assert _upload(client, jpg, incubation_id=9999).status_code == 404
