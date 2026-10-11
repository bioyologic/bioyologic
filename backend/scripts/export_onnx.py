"""Exporta los modelos de Bioyologic a ONNX para el servidor sin PyTorch.

    python backend/scripts/export_onnx.py

Crea models/bioyologic.onnx y models/bioyologic_species.onnx junto a los .pt.
Los .json de configuración sirven para ambos formatos.
Requiere: pip install onnx onnxslim onnxruntime
"""

import json
from pathlib import Path

from ultralytics import YOLO

MODELS = Path(__file__).resolve().parents[2] / "models"

for stem, task, default_size in [("bioyologic", "detect", 640), ("bioyologic_species", "classify", 160)]:
    pt = MODELS / f"{stem}.pt"
    if not pt.exists():
        print(f"No existe {pt}, se omite")
        continue
    meta = json.loads(pt.with_suffix(".json").read_text(encoding="utf-8")) if pt.with_suffix(".json").exists() else {}
    out = YOLO(str(pt), task=task).export(format="onnx", imgsz=meta.get("imgsz", default_size),
                                          dynamic=True, simplify=True)
    print("Exportado:", out)
