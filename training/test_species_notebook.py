"""Prueba local del notebook de especies con datos sintéticos (2 datasets base y uno adicional con una
especie nueva), un entrenamiento corto en CPU, la evaluación por placa, la comparación con el clasificador
actual y la exportación.

    python training/test_species_notebook.py
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

import make_species_notebook as nb  # noqa: E402
from bioyologic.synthetic import SPECIES, draw_plate  # noqa: E402

MODELO = ROOT / "models" / "bioyologic_species.pt"


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

        def preparar(extra: list) -> dict:
            ns: dict = {}
            exec(nb.CONFIG, ns)
            ns.update(WORK=work, RAW=work / "raw", DATASET=work / "crops", EPOCHS=1, TIME_HOURS=None, BATCH=32,
                      MODEL="yolo11n-cls.pt", EXTRA=extra, BASELINE=str(MODELO),
                      EXTRA_INFO={"Especie nueva": {"gram": "+", "agar": "nutrient"}}, SOURCES=[
                          ("makrai", work / "raw" / "makrai" / "annot_COCO.json", work / "raw" / "makrai"),
                          ("clinical", work / "raw" / "clinical" / "coco.json", work / "raw" / "clinical" / "images")])
            exec(nb.det.EXTRAS, ns)
            exec(nb.CROPS, ns)
            return ns

        # Sin datos adicionales: igual que siempre.
        ns = preparar([])
        assert ns["CLASSES"] == ["Acinetobacter baumannii", "Escherichia coli", "Staphylococcus aureus"], ns["CLASSES"]
        assert ns["summary"]["test"]["placas"] >= 3 and ns["TEST_PLATES"] == ns["TEST_BASE"]
        test_base = [(sp, str(it[0])) for sp, it in ns["TEST_BASE"]]

        # Con datos adicionales: un .zip con la especie como categoría (una ya conocida y una nueva) y una carpeta
        # exportada sin especie («colony»), que se traduce con "species". El test base no puede cambiar.
        lab = work / "lab_src"
        make_coco(lab / "fotos", lab / "coco.json", ["Escherichia coli", "Especie nueva"], [0, 1], 8, 300, False)
        with zipfile.ZipFile(work / "lab.zip", "w") as z:
            for p in lab.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(lab))
        make_coco(work / "app", work / "app" / "coco.json", ["colony"], [1], 4, 400, False)
        ns = preparar([{"name": "lab", "path": str(work / "lab.zip")},
                       {"name": "app", "path": str(work / "app"), "species": {"colony": "Staphylococcus aureus"}}])
        assert [(sp, str(it[0])) for sp, it in ns["TEST_BASE"]] == test_base, "el test base cambió al añadir datos"
        assert ns["CLASSES"] == ["Acinetobacter baumannii", "Escherichia coli", "Especie nueva", "Staphylococcus aureus"]
        assert sorted(sp for sp, _ in ns["TEST_EXTRA"]["lab"]) == ["Escherichia coli", "Especie nueva"]
        assert [sp for sp, _ in ns["TEST_EXTRA"]["app"]] == ["Staphylococcus aureus"]
        assert any(p.name.startswith("lab_") for p in (work / "crops" / "train" / "Especie_nueva").glob("*.jpg"))

        # Sin decir la especie, la fuente se rechaza con un mensaje claro.
        try:
            preparar([{"name": "app", "path": str(work / "app")}])
            raise SystemExit("debía rechazar una fuente sin especie")
        except AssertionError as e:
            assert "--especie" in str(e)
        ns = preparar([{"name": "lab", "path": str(work / "lab.zip")},
                       {"name": "app", "path": str(work / "app"), "species": {"colony": "Staphylococcus aureus"}}])

        exec(nb.TRAIN.replace("time=TIME_HOURS, ", "").replace(", workers=2", ", workers=0, device='cpu'"), ns)
        exec(nb.EVAL, ns)
        exec(nb.COMPARE, ns)
        assert set(ns["COMPARISON"]) == {"base", "lab", "app"} and ns["VERDICT"] in ("conservar", "reemplazar")
        for r in ns["COMPARISON"].values():
            assert r["actual"]["placas"] == r["nuevo"]["placas"] > 0 and 0 <= r["nuevo"]["top1"] <= 1
        exec(nb.EXPORT, ns)
        meta = json.loads((work / "bioyologic_species.json").read_text(encoding="utf-8"))
        assert set(meta["classes"]) == set(ns["CLASSES"]) and meta["pad"] == ns["PAD"]
        assert meta["species_info"]["Escherichia coli"]["gram"] == "-"
        assert meta["species_info"]["Especie nueva"] == {"gram": "+", "agar": "nutrient"}
        assert meta["datasets"] == ["makrai", "clinical", "lab", "app"]
        with zipfile.ZipFile(work / "bioyologic_species.zip") as z:
            assert json.loads(z.read("comparacion_especies.json"))["veredicto"] == ns["VERDICT"]
    print("OK: recortes por especie, datos adicionales, entrenamiento, comparación y exportación funcionan")


if __name__ == "__main__":
    main()
