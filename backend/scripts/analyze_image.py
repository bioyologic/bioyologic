"""Analiza una o varias fotos de placas sin pasar por la API.

Uso:
    python scripts/analyze_image.py foto.jpg --mm-per-px 0.0275 --dilution 1e-4 --volume 0.1
Escribe <foto>_result.json y <foto>_annotated.jpg junto a cada imagen (o en --out).
"""

import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bioyologic.analysis.pipeline import analyze  # noqa: E402
from bioyologic.detection.detector import ColonyDetector  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--weights", type=Path, default=ROOT / "models" / "bioyologic.pt")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--tile", type=int, default=640, help="0 = sin teselado")
    ap.add_argument("--mm-per-px", type=float)
    ap.add_argument("--dilution", type=float)
    ap.add_argument("--volume", type=float)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    det = ColonyDetector(args.weights, conf=args.conf, tile=args.tile or None)
    for path in args.images:
        img = cv2.imread(str(path))
        if img is None:
            print(f"[!] No se pudo leer {path}")
            continue
        result, annotated = analyze(img, det.detect(img), mm_per_px=args.mm_per_px,
                                    dilution=args.dilution, volume_ml=args.volume)
        out = args.out or path.parent
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{path.stem}_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
        cv2.imwrite(str(out / f"{path.stem}_annotated.jpg"), annotated)
        s = result["summary"]
        cfu = f"  UFC/mL={s['cfu_per_ml']:.3g}" if s["cfu_per_ml"] else ""
        print(f"{path.name}: {s['total']} colonias {s['by_class']}  [{s['status']}]{cfu}")


if __name__ == "__main__":
    main()
