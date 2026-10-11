"""Genera un dataset sintético en formato AGAR para probar el pipeline.

Uso:
    python scripts/make_synthetic.py --n 60 --out ../data/raw/synthetic
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bioyologic.synthetic import write_agar_dataset  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "raw" / "synthetic")
    args = ap.parse_args()
    write_agar_dataset(args.out, args.n, args.size)
    print(f"{args.n} placas sintéticas en {args.out}")
