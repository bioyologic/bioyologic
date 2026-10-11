"""Prueba local de las celdas del notebook (descarga remota de coco.json, conversión,
evaluación y exportación) con dos datasets sintéticos en formato COCO con la misma
estructura que los reales, y el modelo YOLO local.

    python training/test_notebook.py
"""

import json
import sys
import tempfile
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(HERE))

import make_notebook as nb  # noqa: E402
from bioyologic.synthetic import draw_plate  # noqa: E402


def make_coco(img_dir: Path, coco_path: Path, prefix: str, n: int, seed: int, subdirs: bool) -> int:
    coco = {"images": [], "annotations": [], "categories": [{"id": 1, "name": f"{prefix}1"}, {"id": 2, "name": f"{prefix}2"}]}
    total = 0
    for i in range(n):
        img, labels = draw_plate(2400, 40, seed=seed + i)
        code = f"{prefix}{i % 2 + 1}"
        name = f"{code}_{i:02d}.jpg"
        folder = img_dir / code if subdirs else img_dir
        folder.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(folder / name), img)
        coco["images"].append({"id": i + 1, "file_name": name, "width": 2400, "height": 2400})
        for l in labels:
            coco["annotations"].append({"id": len(coco["annotations"]) + 1, "image_id": i + 1, "category_id": i % 2 + 1,
                                        "bbox": [l["x"], l["y"], l["width"], l["height"]]})
        total += len(labels)
    coco_path.write_text(json.dumps(coco))
    return total


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

        ns = {}
        exec(nb.CONFIG, ns)
        exec("from concurrent.futures import ThreadPoolExecutor", ns)
        ns.update(WORK=work, RAW=work / "raw", DATASET=work / "yolo", SPLIT=(0.5, 0.25, 0.25), SOURCES=[
            ("makrai", work / "raw" / "makrai" / "annot_COCO.json", work / "raw" / "makrai"),
            ("clinical", work / "raw" / "clinical" / "coco.json", work / "raw" / "clinical" / "images"),
        ])
        exec(nb.CONVERT, ns)
        assert len(ns["samples"]) == 12, "no se encontraron todas las imágenes"
        assert sum(len(b) for _, b in ns["samples"]) == n1 + n2
        assert any(p.read_text().strip() for p in (work / "yolo" / "labels" / "train").glob("*.txt"))

        from ultralytics import YOLO
        ns["YOLO"] = YOLO
        ns["BEST"] = ROOT / "models" / "bioyologic.pt"
        exec(nb.EVAL, ns)
        exec(nb.EXPORT, ns)
        meta = json.loads((work / "bioyologic.json").read_text())
        assert meta["max_side"] == ns["MAX_SIDE"] and meta["datasets"] == ["makrai", "clinical"]
    print("OK: conversión de ambos datasets, evaluación y exportación funcionan")


if __name__ == "__main__":
    main()
