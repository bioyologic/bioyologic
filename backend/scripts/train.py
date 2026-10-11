"""Entrena el detector YOLO de colonias y copia el mejor modelo a models/.

Uso:
    python scripts/train.py                              # usa configs/train.yaml
    python scripts/train.py --epochs 1 --model yolo11n.pt --device cpu   # prueba rápida
    python scripts/train.py --export onnx tflite         # además exporta formatos móviles
"""

import argparse
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "train.yaml")
    ap.add_argument("--model")
    ap.add_argument("--data")
    ap.add_argument("--epochs", type=int)
    ap.add_argument("--imgsz", type=int)
    ap.add_argument("--batch", type=int)
    ap.add_argument("--device", help="'cpu', '0' (GPU 0)...")
    ap.add_argument("--name", default="bioyologic")
    ap.add_argument("--export", nargs="*", default=[], help="formatos: onnx tflite")
    args = ap.parse_args()

    from ultralytics import YOLO

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    for k in ("model", "epochs", "imgsz", "batch", "device"):
        if getattr(args, k) is not None:
            cfg[k] = getattr(args, k)
    # --data es relativo al directorio actual; el de la config, al propio archivo.
    config_data = cfg.pop("data")
    data = Path(args.data).resolve() if args.data else (args.config.parent / config_data).resolve()

    model = YOLO(cfg.pop("model"))
    model.train(data=str(data), project=str(ROOT.parent / "runs"), name=args.name,
                exist_ok=True, **cfg)

    best = Path(model.trainer.best)
    dest = ROOT.parent / "models" / "bioyologic.pt"
    dest.parent.mkdir(exist_ok=True)
    shutil.copy(best, dest)
    print(f"Mejor modelo copiado a {dest}")

    metrics = YOLO(str(dest)).val(data=str(data), split="test", imgsz=cfg.get("imgsz", 640),
                                  device=cfg.get("device"), project=str(ROOT.parent / "runs"),
                                  name=f"{args.name}_test", exist_ok=True)
    print(f"Test  mAP50={metrics.box.map50:.3f}  mAP50-95={metrics.box.map:.3f}  "
          f"P={metrics.box.mp:.3f}  R={metrics.box.mr:.3f}")

    for fmt in args.export:
        out = YOLO(str(dest)).export(format=fmt, imgsz=cfg.get("imgsz", 640))
        print(f"Exportado {fmt}: {out}")


if __name__ == "__main__":
    main()
