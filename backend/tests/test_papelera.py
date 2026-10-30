"""Papelera: lo borrado se puede recuperar durante 30 días o eliminar definitivamente."""

from datetime import datetime, timedelta

from .test_api import _register, _upload, ctx  # noqa: F401  (ctx es un fixture)


def test_trash_restore_and_purge(ctx, tmp_path):
    client, jpg, _ = ctx
    p = client.post("/projects", json={"name": "Agua"}).json()
    a = _upload(client, jpg, project_id=p["id"], sample_group="Punto 1").json()
    b = _upload(client, jpg).json()

    # Borrar: desaparece de listados, proyecto, muestras, estadísticas y PDF, pero las fotos siguen
    assert client.delete(f"/analyses/{a['id']}").status_code == 204
    assert [x["id"] for x in client.get("/analyses").json()] == [b["id"]]
    assert client.get(f"/analyses/{a['id']}").status_code == 404
    assert client.get(f"/projects/{p['id']}").json()["analyses_count"] == 0
    assert client.get("/samples").json() == []
    assert client.get("/stats").json()["analyses"] == 1
    assert client.get(a["report_url"]).status_code == 404
    assert list((tmp_path / "images").glob(f"{a['id']}_*"))
    papelera = client.get("/trash").json()
    assert [x["id"] for x in papelera] == [a["id"]]
    falta = datetime.fromisoformat(papelera[0]["purge_at"]) - datetime.fromisoformat(papelera[0]["deleted_at"])
    assert falta == timedelta(days=30)
    assert client.get(papelera[0]["image_urls"]["thumb"]).status_code == 200  # miniatura en la papelera

    # Restaurar: vuelve a su proyecto y a su muestra
    assert client.post("/trash/restore", json={"ids": [a["id"]]}).json() == {"restored": 1}
    assert client.get("/trash").json() == []
    assert client.get(f"/projects/{p['id']}").json()["analyses_count"] == 1
    assert len(client.get("/samples").json()) == 1

    # Eliminar definitivamente: sin vuelta atrás, fotos incluidas
    client.post("/analyses/delete", json={"ids": [a["id"], b["id"]]})
    assert client.post("/trash/purge", json={"ids": [a["id"]]}).json() == {"deleted": 1}
    assert not list((tmp_path / "images").glob(f"{a['id']}_*"))
    assert client.post("/trash/restore", json={"ids": [a["id"]]}).json() == {"restored": 0}
    # Vaciar toda la papelera
    assert client.post("/trash/purge", json={}).json() == {"deleted": 1}
    assert client.get("/trash").json() == []


def test_trash_is_private_and_expires(ctx):
    client, jpg, _ = ctx
    a = _upload(client, jpg).json()
    client.delete(f"/analyses/{a['id']}")
    from fastapi.testclient import TestClient
    from bioyologic.api.main import app, get_store
    otro = TestClient(app)
    otro.headers["Authorization"] = f"Bearer {_register(client, 'beto@lab.co')['token']}"
    assert otro.get("/trash").json() == []
    assert otro.post("/trash/restore", json={"ids": [a["id"]]}).json() == {"restored": 0}
    assert otro.post("/trash/purge", json={"ids": [a["id"]]}).json() == {"deleted": 0}

    # A los 30 días se borra solo
    store = app.dependency_overrides[get_store]()
    hace = (datetime.now().astimezone() - timedelta(days=31)).isoformat(timespec="seconds")
    store._exec("UPDATE analyses SET deleted_at = ? WHERE id = ?", (hace, a["id"]))
    assert client.get("/trash").json() == []
    assert store._all("SELECT id FROM analyses WHERE id = ?", (a["id"],)) == []
