"""Prueba local del notebook de especies con datos sintéticos (2 datasets, 4 especies),
un entrenamiento corto en CPU, la evaluación por placa y la exportación.

    python training/test_species_notebook.py
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

import make_species_notebook as nb  # noqa: E402
from bioyologic.synthetic import SPECIES, draw_plate  # noqa: E402


def make_coco(img_dir: Path, coco_path: Path, codes: list[str], species_idx: list[int], n: int, seed: int, subdirs: bool):
    coco = {"images": [], "annotations": [], "categories": [{"id": i + 1, "name": c} for i, c in enumerate(codes)]}
    for i in range(n):
        k = i % len(codes)
        img, labels = draw_plate(1200, 30, seed=seed + i, species=[SPECIES[species_idx[k]]])
        name = f"{codes[k]}_{i:02d}.jpg"
        folder = img_dir / codes[k] if subdirs else img_dir
        folder.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(folder / name), img)
        coco["images"].append({"id": i + 1, "file_name": name, "width": 1200, "height": 1200})
        for l in labels:
            coco["annotations"].append({"id": len(coco["annotations"]) + 1, "image_id": i + 1, "category_id": k + 1,
                                        "bbox": [l["x"], l["y"], l["width"], l["height"]]})
    coco_path.write_text(json.dumps(coco))


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        # Códigos reales del mapa: sp11 = E. coli (Makrai), sp21 = S. aureus; aba, eco del clínico.
        make_coco(work / "raw" / "makrai", work / "raw" / "makrai" / "annot_COCO.json", ["sp11", "sp21"], [0, 1], 8, 100, False)
        make_coco(work / "raw" / "clinical" / "images", work / "raw" / "clinical" / "coco.json", ["aba", "eco"], [2, 0], 8, 200, True)

        ns: dict = {}
        exec(nb.CONFIG, ns)
        ns.update(WORK=work, RAW=work / "raw", DATASET=work / "crops", EPOCHS=1, TIME_HOURS=None, BATCH=32,
                  MODEL="yolo11n-cls.pt", SOURCES=[
                      ("makrai", work / "raw" / "makrai" / "annot_COCO.json", work / "raw" / "makrai"),
                      ("clinical", work / "raw" / "clinical" / "coco.json", work / "raw" / "clinical" / "images")])
        exec(nb.CROPS, ns)
        assert ns["CLASSES"] == ["Acinetobacter baumannii", "Escherichia coli", "Staphylococcus aureus"], ns["CLASSES"]
        assert ns["summary"]["test"]["placas"] >= 3
        exec(nb.TRAIN.replace("time=TIME_HOURS, ", "").replace(", workers=2", ", workers=0, device='cpu'"), ns)
        exec(nb.EVAL, ns)
        exec(nb.EXPORT, ns)
        meta = json.loads((work / "bioyologic_species.json").read_text(encoding="utf-8"))
        assert set(meta["classes"]) == set(ns["CLASSES"]) and meta["pad"] == ns["PAD"]
        assert meta["species_info"]["Escherichia coli"]["gram"] == "-"
    print("OK: recortes por especie, entrenamiento, evaluación por placa y exportación funcionan")


if __name__ == "__main__":
    main()
