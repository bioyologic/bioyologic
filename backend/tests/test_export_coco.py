"""Exportar las placas corregidas de una cuenta como datos de entrenamiento (manage export-coco)."""

import io
import json
import zipfile

import cv2
import numpy as np

from bioyologic import manage
from bioyologic.api.main import app, get_store

from .test_api import _register, _upload, ctx  # noqa: F401  (ctx es un fixture)


def _leer(path):
    with zipfile.ZipFile(path) as z:
        coco = json.loads(z.read("coco.json"))
        fotos = {n: z.read(n) for n in z.namelist() if n.startswith("images/")}
    return coco, fotos


def test_export_coco_solo_lo_revisado_y_con_el_conteo_final(ctx, tmp_path):
    client, jpg, labels = ctx
    store = app.dependency_overrides[get_store]()
    corregido = _upload(client, jpg, sample_name="corregida").json()
    _upload(client, jpg, sample_name="sin revisar")
    ids = [c["id"] for c in corregido["colonies"]]
    w, h = corregido["image_size"]
    r = client.put(f"/analyses/{corregido['id']}/colonies",
                   json={"removed": ids[:2], "added": [{"x": w / 2, "y": h / 2, "r": 12}]})
    assert r.status_code == 200, r.text

    out = tmp_path / "datos.zip"
    assert manage.export_coco(store, "ANA@lab.co", out) == (1, len(labels) - 1)
    coco, fotos = _leer(out)
    assert coco["categories"] == [{"id": 1, "name": "colony"}]
    assert [im["id"] for im in coco["images"]] == [corregido["id"]]
    assert list(fotos) == [f"images/{corregido['id']}.jpg"]
    # Las cajas están en píxeles de la foto que se exporta, dentro de ella, y en formato COCO (x, y, ancho, alto).
    foto = cv2.imdecode(np.frombuffer(fotos[f"images/{corregido['id']}.jpg"], np.uint8), cv2.IMREAD_COLOR)
    assert foto.shape[:2] == (h, w) == (coco["images"][0]["height"], coco["images"][0]["width"])
    cajas = [a["bbox"] for a in coco["annotations"]]
    assert all(x >= 0 and y >= 0 and bw > 0 and bh > 0 and x + bw <= w + 0.1 and y + bh <= h + 0.1
               for x, y, bw, bh in cajas)
    # La agregada a mano está (24 px de lado, centrada) y las dos quitadas no.
    assert [w / 2 - 12, h / 2 - 12, 24, 24] in cajas
    quitadas = [c["bbox"] for c in corregido["colonies"] if c["id"] in ids[:2]]
    assert not any([round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)] in cajas
                   for x1, y1, x2, y2 in quitadas)

    # Con --todas entran también las que nadie revisó; con especie, sirve para el clasificador.
    assert manage.export_coco(store, "ana@lab.co", out, species="Escherichia coli", everything=True)[0] == 2
    assert _leer(out)[0]["categories"][0]["name"] == "Escherichia coli"
    # La papelera no se exporta, y solo salen los análisis de esa cuenta.
    assert client.delete(f"/analyses/{corregido['id']}").status_code == 204
    assert manage.export_coco(store, "ana@lab.co", out) == (0, 0)
    _register(client, "otro@lab.co")
    assert manage.export_coco(store, "otro@lab.co", out, everything=True) == (0, 0)
    assert manage.export_coco(store, "nadie@lab.co", out) is None


def test_export_coco_por_proyecto_desde_la_linea_de_comandos(ctx, tmp_path, monkeypatch, capsys):
    client, jpg, _ = ctx
    p = client.post("/projects", json={"name": "E. coli"}).json()
    dentro = _upload(client, jpg, project_id=p["id"]).json()
    fuera = _upload(client, jpg).json()
    for a in (dentro, fuera):
        assert client.put(f"/analyses/{a['id']}/colonies",
                          json={"removed": [a["colonies"][0]["id"]], "added": []}).status_code == 200

    monkeypatch.setenv("BIOYOLOGIC_DATA", str(tmp_path))   # la misma carpeta que usa el almacén de la prueba
    assert manage.main(["export-coco", "--email", "ana@lab.co", "--proyecto", "E. coli",
                        "--especie", "Escherichia coli"]) == 0
    assert "Exportadas 1 placas" in capsys.readouterr().out
    coco, fotos = _leer(tmp_path / "entrenamiento.zip")
    assert [im["id"] for im in coco["images"]] == [dentro["id"]] and len(fotos) == 1
    assert zipfile.is_zipfile(io.BytesIO((tmp_path / "entrenamiento.zip").read_bytes()))
    assert manage.main(["export-coco", "--email", "nadie@lab.co"]) == 1
