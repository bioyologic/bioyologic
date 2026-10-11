"""Carga datos de demostración: proyectos y análisis de placas sintéticas.

Cada análisis pasa por el pipeline real (detector YOLO + morfología + conteo).
También deja fotos de ejemplo en data/demo_photos/ para probar la subida desde la app.

Uso:
    python scripts/seed_demo.py            # añade los datos
    python scripts/seed_demo.py --reset    # borra la base de datos antes
"""

import argparse
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bioyologic.analysis.pipeline import analyze  # noqa: E402
from bioyologic.detection.detector import ColonyDetector  # noqa: E402
from bioyologic.storage import Store  # noqa: E402
from bioyologic.synthetic import SPECIES, draw_plate  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SIZE = 1600
PLATE_FRACTION = 0.92  # la placa sintética ocupa el 92 % del lado

PROJECTS = [
    ("Control de agua potable", "Recuento de aerobios en muestras de grifo (datos de demostración).", 6,
     [("E.coli",), ("E.coli", "C.albicans"), ("E.coli",)]),
    ("Superficies del laboratorio", "Hisopado de mesadas y campanas (datos de demostración).", 5,
     [("S.aureus",), ("S.aureus", "B.subtilis")]),
    ("Ensayo de Pseudomonas", "Seguimiento de P. aeruginosa en caldo (datos de demostración).", 4,
     [("P.aeruginosa",), ("P.aeruginosa",), ("P.aeruginosa", "E.coli")]),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "store")
    ap.add_argument("--weights", type=Path, default=ROOT / "models" / "bioyologic.pt")
    args = ap.parse_args()

    if args.reset and args.data.exists():
        shutil.rmtree(args.data)
    store = Store(args.data)
    det = ColonyDetector(args.weights)
    mm_per_px = 90 / (PLATE_FRACTION * SIZE)
    by_name = {s.name: s for s in SPECIES}

    n = 0
    total = sum(len(p[3]) for p in PROJECTS)
    now = datetime.now().astimezone().replace(second=0, microsecond=0)
    for name, desc, target, plates in PROJECTS:
        project = store.create_project(name, desc, target)
        for k, species in enumerate(plates):
            n += 1
            img, _ = draw_plate(SIZE, 35 + 25 * ((n * 7) % 5), seed=900 + n,
                                species=[by_name[s] for s in species])
            dilution = 10.0 ** -(3 + (n % 3))
            result, annotated = analyze(img, det.detect(img), mm_per_px=mm_per_px,
                                        dilution=dilution, volume_ml=0.1)
            # Fechas en el pasado, una placa cada ~18 h; la última, hace una hora.
            result["analyzed_at"] = (now - timedelta(hours=1 + 18 * (total - n))).isoformat(timespec="seconds")
            a = store.add_analysis(sample_name=f"Caja #{n}", result=result, original=img, annotated=annotated,
                                   project_id=project["id"], dilution=dilution, volume_ml=0.1)
            print(f"{project['name']} · {a['sample_name']}: {a['summary']['total']} colonias")

    photos = ROOT / "data" / "demo_photos"
    photos.mkdir(parents=True, exist_ok=True)
    for i, sp in enumerate(["S.aureus", "E.coli", "B.subtilis"]):
        img, labels = draw_plate(SIZE, 60, seed=4000 + i, species=[by_name[sp]])
        cv2.imwrite(str(photos / f"placa_{i + 1}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"Foto de ejemplo: placa_{i + 1}.jpg ({len(labels)} colonias reales)")
    print(f"Listo: {store.stats()}")


if __name__ == "__main__":
    main()
