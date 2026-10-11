"""Evalúa el error de CONTEO (no solo mAP) sobre placas completas anotadas.

El mAP mide la calidad de las cajas; para un contador de colonias la métrica
que importa al microbiólogo es cuánto se desvía el número total por placa.

Uso:
    python scripts/evaluate_counts.py --agar ../data/raw/agar_test
    python scripts/evaluate_counts.py --voc ../data/raw/makrai --limit 50
"""

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bioyologic.detection.datasets import load_agar, load_voc  # noqa: E402
from bioyologic.detection.detector import ColonyDetector  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agar", type=Path)
    ap.add_argument("--voc", type=Path)
    ap.add_argument("--weights", type=Path, default=ROOT / "models" / "bioyologic.pt")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--tile", type=int, default=640)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--csv", type=Path, default=ROOT / "runs" / "count_eval.csv")
    args = ap.parse_args()

    samples = (load_agar(args.agar) if args.agar else []) + (load_voc(args.voc) if args.voc else [])
    if args.limit:
        samples = samples[:args.limit]
    if not samples:
        raise SystemExit("Sin imágenes: indica --agar o --voc")

    det = ColonyDetector(args.weights, conf=args.conf, tile=args.tile or None)
    rows = []
    for s in samples:
        img = cv2.imread(str(s.image))
        if img is None:
            continue
        pred, true = len(det.detect(img)), len(s.boxes)
        rows.append((s.image.name, true, pred))
        print(f"{s.image.name}: real={true} pred={pred}")

    true = np.array([r[1] for r in rows], float)
    pred = np.array([r[2] for r in rows], float)
    err = pred - true
    nz = true > 0
    print("\n--- Error de conteo por placa ---")
    print(f"Placas: {len(rows)}")
    print(f"MAE:  {np.abs(err).mean():.2f} colonias")
    print(f"RMSE: {np.sqrt((err ** 2).mean()):.2f} colonias")
    print(f"Sesgo medio: {err.mean():+.2f} (positivo = sobreconteo)")
    if nz.any():
        print(f"MAPE: {100 * np.abs(err[nz] / true[nz]).mean():.1f} %")
    if len(rows) > 1 and true.std() > 0 and pred.std() > 0:
        print(f"Correlación de Pearson r: {np.corrcoef(true, pred)[0, 1]:.4f}")

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="") as f:
        csv.writer(f).writerows([("imagen", "real", "predicho"), *rows])
    print(f"Detalle en {args.csv}")


if __name__ == "__main__":
    main()
