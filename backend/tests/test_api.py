import cv2
import pytest
from fastapi.testclient import TestClient

from bioyologic.api.main import app, get_detector, get_species, get_store, resolve_scale
from bioyologic.detection.species import SpeciesResult
from bioyologic.detection.detector import Detection
from bioyologic.storage import Store
from bioyologic.synthetic import draw_plate


class FakeDetector:
    """Devuelve las cajas reales de la placa sintética (aísla la API del modelo)."""

    names = {0: "E.coli", 1: "S.aureus"}
    tile = None
    conf = 0.25

    def __init__(self, labels):
        self.labels = labels

    def detect(self, image):
        return [Detection(l["x"], l["y"], l["x"] + l["width"], l["y"] + l["height"], 0.9,
                          0, l["class"]) for l in self.labels]


@pytest.fixture
def ctx(tmp_path):
    img, labels = draw_plate(600, 15, seed=7)
    store = Store(tmp_path)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_detector] = lambda: FakeDetector(labels)
    app.dependency_overrides[get_species] = lambda: None
    _, buf = cv2.imencode(".jpg", img)
    yield TestClient(app), buf.tobytes(), labels
    app.dependency_overrides.clear()
    store.close()


def _upload(client, jpg, **fields):
    data = {"sample_name": "Caja #1", **{k: str(v) for k, v in fields.items()}}
    return client.post("/analyses", files={"image": ("p.jpg", jpg, "image/jpeg")}, data=data)


def test_full_flow(ctx):
    client, jpg, labels = ctx
    p = client.post("/projects", json={"name": "Agua de río", "target_samples": 4}).json()
    assert p["analyses_count"] == 0 and p["cover_url"] is None

    r = _upload(client, jpg, project_id=p["id"], dilution=0.001, volume_ml=0.1, plate_fraction=0.92)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["summary"]["total"] == len(labels)
    assert a["summary"]["cfu_per_ml"] == pytest.approx(len(labels) / 1e-4)
    assert a["summary"]["predominant"]["color"]
    assert a["mm_per_px"] == pytest.approx(90 / (0.92 * 600))
    assert a["project_name"] == "Agua de río"
    assert len(a["colonies"]) == len(labels)

    # Imágenes y reporte
    for kind in ("original", "annotated", "thumb"):
        img = client.get(a["image_urls"][kind])
        assert img.status_code == 200 and img.content[:2] == b"\xff\xd8"
    pdf = client.get(a["report_url"])
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    # Listados, búsqueda y progreso del proyecto
    assert len(client.get("/analyses").json()) == 1
    assert client.get("/analyses", params={"q": "caja"}).json()[0]["id"] == a["id"]
    assert client.get("/analyses", params={"q": "zzz"}).json() == []
    assert "colonies" not in client.get("/analyses").json()[0]
    proj = client.get(f"/projects/{p['id']}").json()
    assert proj["analyses_count"] == 1 and proj["progress"] == 0.25
    assert proj["cover_url"] == f"/analyses/{a['id']}/image/thumb"

    # Edición
    upd = client.patch(f"/analyses/{a['id']}", json={"notes": "Repetir", "project_id": 0}).json()
    assert upd["notes"] == "Repetir" and upd["project_id"] is None
    assert client.get("/stats").json() == {"analyses": 1, "colonies": len(labels), "projects": 1}

    # Borrado
    assert client.delete(f"/analyses/{a['id']}").status_code == 204
    assert client.get(f"/analyses/{a['id']}").status_code == 404
    assert client.delete(f"/projects/{p['id']}").status_code == 204


def test_rejects_bad_input(ctx):
    client, jpg, _ = ctx
    assert client.post("/analyses", files={"image": ("x.jpg", b"nada", "image/jpeg")},
                       data={"sample_name": "x"}).status_code == 400
    assert _upload(client, jpg, dilution=-1).status_code == 422
    assert _upload(client, jpg, project_id=999).status_code == 404
    assert client.post("/projects", json={"name": ""}).status_code == 422


def test_library(ctx):
    client, _, _ = ctx
    lib = client.get("/library").json()
    assert set(lib["categories"]) == {"bacterias", "protocolos", "guias"}
    first = lib["entries"][0]
    assert "sections" not in first
    detail = client.get(f"/library/{first['id']}").json()
    assert detail["sections"]
    img = client.get(first["image_url"])
    assert img.status_code == 200 and img.content[:2] == b"\xff\xd8"


def test_resolve_scale():
    assert resolve_scale((1000, 800, 3), 0.05, 0.9, 90) == 0.05
    assert resolve_scale((1000, 800, 3), None, 0.9, 90) == pytest.approx(90 / 720)


def test_health():
    assert TestClient(app).get("/health").json()["status"] == "ok"


class FakeSpecies:
    """Clasifica todas las colonias como E. coli salvo la primera (S. aureus)."""

    names = {0: "Escherichia coli", 1: "Staphylococcus aureus"}

    def classify(self, image, boxes):
        per = [("Staphylococcus aureus", 0.6)] + [("Escherichia coli", 0.9)] * (len(boxes) - 1)
        top = [{"name": "Escherichia coli", "prob": 0.86, "gram": "-", "agar": "blood"},
               {"name": "Staphylococcus aureus", "prob": 0.1, "gram": "+", "agar": "blood"}]
        return SpeciesResult(per, top, True)


def test_species_classification(ctx):
    client, jpg, labels = ctx
    app.dependency_overrides[get_species] = lambda: FakeSpecies()
    a = _upload(client, jpg).json()
    assert a["species"]["identified"] is True
    assert a["species"]["top"][0]["name"] == "Escherichia coli"
    assert a["summary"]["by_class"] == {"Staphylococcus aureus": 1, "Escherichia coli": len(labels) - 1}
    assert a["summary"]["predominant"]["class"] == "Escherichia coli"
    assert a["colonies"][0]["species_confidence"] in (0.6, 0.9)
    # Se conserva al leer el análisis guardado y en el listado
    assert client.get(f"/analyses/{a['id']}").json()["species"]["top"][0]["prob"] == 0.86
    assert client.get("/analyses").json()[0]["species"]["identified"] is True


def test_about_license(ctx):
    client, _, _ = ctx
    a = client.get("/about").json()
    assert a["license"].startswith("AGPL-3.0")
    assert {"source_url", "datasets"} <= a.keys() and len(a["datasets"]) == 2


def test_rate_limit(ctx, monkeypatch):
    from bioyologic.api import main
    client, jpg, _ = ctx
    monkeypatch.setattr(main, "RATE_LIMIT", 2)
    monkeypatch.setattr(main, "_hits", main.defaultdict(main.deque))
    codes = [_upload(client, jpg).status_code for _ in range(3)]
    assert codes == [201, 201, 429]


def test_upload_size_limit(ctx, monkeypatch):
    from bioyologic.api import main
    client, jpg, _ = ctx
    monkeypatch.setattr(main, "MAX_UPLOAD_MB", len(jpg) / 2 / 1024 / 1024)
    assert _upload(client, jpg).status_code == 413
