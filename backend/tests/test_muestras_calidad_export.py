"""UFC/mL de una muestra con varias placas (ISO 4833-1), calidad de la foto y exportación a CSV."""

import csv
import io

import cv2
import numpy as np
import pytest

from bioyologic.analysis.counting import combine_plates
from bioyologic.analysis.quality import assess
from bioyologic.synthetic import draw_plate

from .test_api import _upload, ctx  # noqa: F401  (ctx es un fixture)


def _p(i, total, exp, v=0.1):
    return {"id": i, "total": total, "dilution": 10.0 ** -exp, "volume_ml": v}


# ------------------------------------------------------------------ ISO 4833-1
def test_iso_two_successive_dilutions():
    # 10⁻³: 280 y 260; 10⁻⁴: 33 y 30 -> N = ΣC / (V × (n1 + 0,1·n2) × d1)
    r = combine_plates([_p(1, 280, 3), _p(2, 260, 3), _p(3, 33, 4), _p(4, 30, 4)])
    assert r["cfu_per_ml"] == pytest.approx(603 / (0.1 * (2 + 0.1 * 2) * 1e-3))
    assert r["used"] == [1, 2, 3, 4] and r["estimated"] is False


def test_iso_only_countable_plates_are_used():
    r = combine_plates([_p(1, 168, 4), _p(2, 215, 4), _p(3, 14, 5), _p(4, 25, 5), _p(5, 900, 3)])
    assert r["used"] == [1, 2]
    assert r["cfu_per_ml"] == pytest.approx(383 / (0.2 * 1e-4))
    assert r["warnings"] == []  # diferencias normales por azar (Poisson): sin aviso


def test_estimated_when_no_plate_is_countable():
    r = combine_plates([_p(1, 12, 4), _p(2, 3, 5)])
    assert r["estimated"] is True and r["used"] == [1] and "menos de 30" in r["rule"]
    r = combine_plates([_p(1, 0, 2)])
    assert r["cfu_per_ml"] is None and "menos de 1000 UFC/mL" in r["rule"]


def test_warnings_replicates_and_dilution_error():
    r = combine_plates([_p(1, 100, 4), _p(2, 160, 4), _p(3, 40, 5)])
    assert any("réplicas de 10⁻⁴" in w for w in r["warnings"])
    assert any("posible error en la dilución" in w for w in r["warnings"])


def test_plates_without_dilution_are_ignored():
    r = combine_plates([{"id": 1, "total": 50, "dilution": None, "volume_ml": None}])
    assert r["cfu_per_ml"] is None and r["warnings"]


# ------------------------------------------------------------------ calidad de la foto
def test_quality_good_and_bad_photos():
    img, _ = draw_plate(900, 60, seed=5)
    assert assess(img)["ok"] is True
    borrosa = cv2.GaussianBlur(img, (0, 0), 6)
    assert [i["code"] for i in assess(borrosa)["issues"]] == ["blurry"]
    oscura = (img * 0.25).astype(np.uint8)
    assert "dark" in {i["code"] for i in assess(oscura)["issues"]}
    reflejo = img.copy()
    cv2.circle(reflejo, (600, 300), 60, (255, 255, 255), -1)
    q = assess(reflejo)
    assert "glare" in {i["code"] for i in q["issues"]}
    assert "arriba a la derecha" in next(i["message"] for i in q["issues"] if i["code"] == "glare")


# ------------------------------------------------------------------ API: muestras y exportación
def test_samples_group_plates_and_export_csv(ctx):
    client, jpg, labels = ctx
    n = len(labels)
    p = client.post("/projects", json={"name": "Río Bogotá"}).json()
    ids = [_upload(client, jpg, project_id=p["id"], sample_group="Punto 1", dilution=d, volume_ml=0.1).json()["id"]
           for d in (0.001, 0.001, 0.0001)]
    _upload(client, jpg, project_id=p["id"], dilution=0.001, volume_ml=0.1)  # placa suelta: no es de ninguna muestra
    a = client.get(f"/analyses/{ids[0]}").json()
    assert a["sample_group"] == "Punto 1" and a["quality"]["ok"] is True

    muestras = client.get("/samples", params={"project_id": p["id"]}).json()
    assert [m["name"] for m in muestras] == ["Punto 1"] and len(muestras[0]["plates"]) == 3
    res = muestras[0]["result"]
    assert res["cfu_per_ml"] is not None and set(res["used"]) <= set(ids)
    assert client.get("/sample-groups", params={"project_id": p["id"]}).json() == ["Punto 1"]

    # Quitar una placa de la muestra
    client.patch(f"/analyses/{ids[2]}", json={"sample_group": ""})
    assert len(client.get("/samples").json()[0]["plates"]) == 2

    # CSV para Excel: BOM, ";" y coma decimal, una fila por placa del proyecto
    url = client.post("/export-link", json={"project_id": p["id"]}).json()["url"]
    assert "R%C3%ADo%20Bogot%C3%A1.csv" in url
    from fastapi.testclient import TestClient
    from bioyologic.api.main import app
    r = TestClient(app).get(url)  # sin token: el enlace de un solo uso basta
    assert r.status_code == 200 and r.content[:3] == b"\xef\xbb\xbf"
    filas = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    assert filas[0][:4] == ["Proyecto", "Muestra", "Placa", "Fecha"] and len(filas) == 1 + 4
    assert {f[1] for f in filas[1:]} == {"Punto 1", ""}
    assert all(f[0] == "Río Bogotá" for f in filas[1:]) and filas[1][6] == str(n)
    assert TestClient(app).get(url).status_code == 404  # un solo uso
    assert client.post("/export-link", json={"project_id": 999}).status_code == 404


def test_delete_many_only_own_analyses(ctx, tmp_path):
    client, jpg, _ = ctx
    ids = [_upload(client, jpg).json()["id"] for _ in range(3)]
    from fastapi.testclient import TestClient
    from bioyologic.api.main import app
    from .test_api import _register
    otro = TestClient(app)
    otro.headers["Authorization"] = f"Bearer {_register(client, 'beto@lab.co')['token']}"
    ajeno = _upload(otro, jpg).json()["id"]

    r = client.post("/analyses/delete", json={"ids": [ids[0], ids[1], ajeno, 9999]})
    assert r.json() == {"deleted": 2}  # el ajeno y el inexistente se ignoran
    assert [a["id"] for a in client.get("/analyses").json()] == [ids[2]]
    assert not list((tmp_path / "images").glob(f"{ids[0]}_*"))  # sus fotos también se borran
    assert otro.get(f"/analyses/{ajeno}").status_code == 200
    assert client.post("/analyses/delete", json={"ids": []}).status_code == 422
