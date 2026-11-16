"""Prueba local de las celdas del notebook (descarga remota de coco.json, datos adicionales, conversión,
evaluación, comparación con el modelo actual y exportación) con datasets sintéticos que tienen la misma
estructura que los reales, y el modelo YOLO local.

    python training/test_notebook.py
"""

import json
import sys
import tempfile
import zipfile
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(HERE))

import make_notebook as nb  # noqa: E402
from bioyologic.synthetic import draw_plate  # noqa: E402

MODELO = ROOT / "models" / "bioyologic.pt"


def make_coco(img_dir: Path, coco_path: Path, prefix: str, n: int, seed: int, subdirs: bool, size: int = 2400) -> int:
    coco = {"images": [], "annotations": [], "categories": [{"id": 1, "name": f"{prefix}1"}, {"id": 2, "name": f"{prefix}2"}]}
    total = 0
    for i in range(n):
        img, labels = draw_plate(size, 40, seed=seed + i)
        code = f"{prefix}{i % 2 + 1}"
        name = f"{code}_{i:02d}.jpg"
        folder = img_dir / code if subdirs else img_dir
        folder.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(folder / name), img)
        coco["images"].append({"id": i + 1, "file_name": name, "width": size, "height": size})
        for l in labels:
            coco["annotations"].append({"id": len(coco["annotations"]) + 1, "image_id": i + 1, "category_id": i % 2 + 1,
                                        "bbox": [l["x"], l["y"], l["width"], l["height"]]})
        total += len(labels)
    coco_path.write_text(json.dumps(coco))
    return total


def make_agar(folder: Path, n: int, seed: int) -> None:
    """Formato AGAR: un .json por foto. Añade una placa «incontable» (sin cajas), que debe descartarse."""
    folder.mkdir(parents=True)
    for i in range(n):
        img, labels = draw_plate(1200, 20, seed=seed + i)
        cv2.imwrite(str(folder / f"{i}.jpg"), img)
        (folder / f"{i}.json").write_text(json.dumps({"colonies_number": len(labels), "labels": [
            {"class": "E.coli", "x": l["x"], "y": l["y"], "width": l["width"], "height": l["height"]} for l in labels]}))
    cv2.imwrite(str(folder / "99.jpg"), img)
    (folder / "99.json").write_text(json.dumps({"colonies_number": -1, "labels": []}))


def main() -> None:
    # 1) Celda de descarga: el lector de ZIP remoto extrae coco.json del label.zip real de Zenodo.
    dl_src = nb.DOWNLOAD.split("SOURCES = []")[0]
    ns: dict = {}
    exec(dl_src, ns)
    url = "https://zenodo.org/api/records/18256864/files/label.zip/content"
    coco = json.loads(ns["remote_zip_read"](url, ns["remote_zip_entries"](url), "label/coco_json/coco.json"))
    assert len(coco["images"]) == 950 and len(coco["categories"]) == 19
    print("OK: coco.json extraído del ZIP remoto de Zenodo (950 imágenes, 19 especies)")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        # Estructura tipo Makrai (imágenes sueltas) y tipo clínico (subcarpetas por especie).
        n1 = make_coco(work / "raw" / "makrai", work / "raw" / "makrai" / "annot_COCO.json", "sp", 6, 500, False)
        n2 = make_coco(work / "raw" / "clinical" / "images", work / "raw" / "clinical" / "coco.json", "ab", 6, 600, True)

        def preparar(extra: list) -> dict:
            ns: dict = {}
            exec(nb.CONFIG, ns)
            ns.update(WORK=work, RAW=work / "raw", DATASET=work / "yolo", SPLIT=(0.5, 0.25, 0.25), EXTRA=extra,
                      BASELINE=str(MODELO), SOURCES=[
                          ("makrai", work / "raw" / "makrai" / "annot_COCO.json", work / "raw" / "makrai"),
                          ("clinical", work / "raw" / "clinical" / "coco.json", work / "raw" / "clinical" / "images")])
            exec(nb.EXTRAS, ns)
            exec(nb.CONVERT, ns)
            return ns

        # 2) Sin datos adicionales: igual que siempre.
        ns = preparar([])
        assert len(ns["samples"]) == 12, "no se encontraron todas las imágenes"
        assert sum(len(b) for _, b in ns["samples"]) == n1 + n2
        assert any(p.read_text().strip() for p in (work / "yolo" / "labels" / "train").glob("*.txt"))
        assert ns["BASELINE_PT"] == MODELO and ns["EXTRA_SOURCES"] == [] and ns["TEST_SAMPLES"] == ns["TEST_BASE"]
        test_base = [str(p) for p, _ in ns["TEST_BASE"]]
        assert len(test_base) == 3
        print("OK: conversión de los dos datasets base")

        # 3) Con datos adicionales: un .zip en formato COCO (con los MISMOS nombres de archivo que Makrai) y una
        #    carpeta en formato AGAR. El test de los datasets base no puede cambiar.
        lab = work / "lab_src"
        make_coco(lab / "fotos", lab / "coco.json", "sp", 6, 700, False, size=1200)
        with zipfile.ZipFile(work / "lab.zip", "w") as z:
            for p in lab.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(lab))
        make_agar(work / "agar", 5, 800)
        ns = preparar([{"name": "lab", "path": str(work / "lab.zip")},
                       {"name": "agar", "path": str(work / "agar"), "max_plates": 4}])
        assert [str(p) for p, _ in ns["TEST_BASE"]] == test_base, "el test base cambió al añadir datos"
        assert [s[0] for s in ns["EXTRA_SOURCES"]] == ["lab", "agar"]
        assert len(ns["TEST_EXTRA"]["lab"]) == 2 and len(ns["TEST_EXTRA"]["agar"]) == 1   # 6 y 4 placas (5 con tope 4)
        assert ns["summary"]["train"]["placas"] == 6 + 3 + 2
        for part in ("train", "val", "test"):   # ninguna tesela pisó a otra
            assert len(list((work / "yolo" / "images" / part).glob("*.jpg"))) == ns["summary"][part]["teselas"]
        train = [p.name for p in (work / "yolo" / "images" / "train").glob("*.jpg")]
        assert any(t.startswith("lab_") for t in train) and any(t.startswith("agar_") for t in train)
        for subset in ("base", "lab", "agar"):
            assert (work / "yolo" / f"data_{subset}.yaml").exists()
            assert (work / "yolo" / f"test_{subset}.txt").read_text().strip()
        print("OK: datos adicionales (COCO en .zip y AGAR) sin tocar el test base")

        # 4) Evaluación, comparación con el modelo actual y exportación.
        from ultralytics import YOLO
        ns["YOLO"] = YOLO
        ns["BEST"] = MODELO
        exec(nb.EVAL, ns)
        compare = nb.COMPARE.replace("plots=False,", "plots=False, workers=0,")
        exec(compare, ns)
        assert set(ns["COMPARISON"]) == {"base", "lab", "agar"}
        for r in ns["COMPARISON"].values():
            assert r["actual"] == r["nuevo"] and r["nuevo"]["placas"] > 0
        # El mismo modelo no es «mejor» que sí mismo: se conserva el actual.
        assert ns["VERDICT"] == "conservar"
        exec(nb.EXPORT, ns)
        meta = json.loads((work / "bioyologic.json").read_text())
        assert meta["max_side"] == ns["MAX_SIDE"] and meta["datasets"] == ["makrai", "clinical", "lab", "agar"]
        with zipfile.ZipFile(work / "bioyologic_detector.zip") as z:
            guardado = json.loads(z.read("comparacion.json"))
        assert guardado["veredicto"] == "conservar" and guardado["motivos"]

        # Un modelo que cuenta mejor en los datos nuevos y no empeora en los base: se reemplaza.
        mejor = compare.replace('"nuevo": measure(BEST, subset, plates)}',
                                '"nuevo": {**measure(BEST, subset, plates), "MAE": -1.0}}')
        assert mejor != compare
        exec(mejor, ns)
        assert ns["VERDICT"] == "reemplazar"
    print("OK: evaluación, comparación con el modelo actual y exportación funcionan")


if __name__ == "__main__":
    main()
