"""Prepara el dataset YOLO a partir de una o varias bases de datos públicas.

Ejemplos:
    # AGAR (descargada en data/raw/agar), teselada a 1024 px
    python scripts/prepare_dataset.py --agar ../data/raw/agar --tile 1024

    # AGAR + Makrai et al. (VOC) en una sola clase "colony"
    python scripts/prepare_dataset.py --agar ../data/raw/agar --voc ../data/raw/makrai --single-class
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bioyologic.detection.datasets import (  # noqa: E402
    build_yolo_dataset, load_agar, load_voc, load_yolo,
)

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agar", type=Path, action="append", default=[])
    ap.add_argument("--voc", type=Path, action="append", default=[])
    ap.add_argument("--yolo", type=Path, action="append", default=[])
    ap.add_argument("--yolo-names", nargs="*", default=["colony"],
                    help="nombres de clase de los datasets en formato YOLO")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "yolo")
    ap.add_argument("--single-class", action="store_true",
                    help="una única clase 'colony' (conteo independiente de la especie)")
    ap.add_argument("--tile", type=int, default=None, help="tamaño de tile en px (p. ej. 1024)")
    ap.add_argument("--overlap", type=float, default=0.2)
    ap.add_argument("--max-images", type=int, default=None,
                    help="limita el número de imágenes (pruebas rápidas)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    samples = []
    for p in args.agar:
        samples += load_agar(p)
    for p in args.voc:
        samples += load_voc(p)
    for p in args.yolo:
        samples += load_yolo(p, args.yolo_names)
    if not samples:
        raise SystemExit("No se encontraron imágenes anotadas. Revisa las rutas.")
    if args.max_images:
        samples = samples[:args.max_images]

    print(f"{len(samples)} imágenes, {sum(len(s.boxes) for s in samples)} colonias")
    summary = build_yolo_dataset(samples, args.out, single_class=args.single_class,
                                 tile=args.tile, overlap=args.overlap, seed=args.seed)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Dataset listo en {args.out / 'data.yaml'}")


if __name__ == "__main__":
    main()
