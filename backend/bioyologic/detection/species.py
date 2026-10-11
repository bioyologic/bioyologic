"""Clasificador de especie por colonia (segunda etapa, YOLO11-cls).

El detector encuentra las colonias; este modelo mira el recorte cuadrado de cada
una (con el mismo margen que en el entrenamiento, `pad`) y devuelve la especie y
su probabilidad. La especie de la placa es el promedio de las probabilidades de
todas sus colonias.

Se activa si existe `models/bioyologic_species.onnx` o `.pt` (+ `.json`), generado con
training/Bioyologic_especies.ipynb.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# Por debajo de esta probabilidad media la placa se marca como «no identificada».
MIN_PLATE_PROB = 0.40


@dataclass
class SpeciesResult:
    per_colony: list[tuple[str, float]]       # (especie, probabilidad) por colonia
    plate: list[dict]                         # top-3 de la placa: {name, prob, gram, agar}
    identified: bool


def square_crop(img: np.ndarray, box, pad: float, size: int) -> np.ndarray | None:
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    side = max(x2 - x1, y2 - y1) * (1 + 2 * pad)
    h, w = img.shape[:2]
    a, b = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    c, d = int(min(w, cx + side / 2)), int(min(h, cy + side / 2))
    crop = img[b:d, a:c]
    return cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA) if crop.size else None


class SpeciesClassifier:
    def __init__(self, weights: str | Path, device: str | None = None) -> None:
        weights = Path(weights)
        meta = json.loads(weights.with_suffix(".json").read_text(encoding="utf-8"))
        if weights.suffix == ".onnx":
            from .onnx_backend import OnnxClassifier
            self.model = OnnxClassifier(weights)
        else:
            from ultralytics import YOLO
            self.model = YOLO(str(weights), task="classify")
        self.pad = float(meta.get("pad", 0.3))
        self.imgsz = int(meta.get("imgsz", 160))
        self.info: dict = meta.get("species_info", {})
        self.names = {i: n.replace("_", " ") for i, n in self.model.names.items()}
        self.device = device

    def _probs(self, crops: list[np.ndarray]) -> np.ndarray:
        if not hasattr(self.model, "export"):     # OnnxClassifier
            return self.model.predict(crops, self.imgsz)
        return np.stack([r.probs.data.cpu().numpy() for r in
                         self.model.predict(crops, imgsz=self.imgsz, device=self.device, verbose=False)])

    def classify(self, image: np.ndarray, boxes: list[tuple[float, float, float, float]]) -> SpeciesResult:
        crops, idx = [], []
        for i, b in enumerate(boxes):
            c = square_crop(image, b, self.pad, self.imgsz)
            if c is not None:
                crops.append(c)
                idx.append(i)
        n_cls = len(self.names)
        probs = np.zeros((len(boxes), n_cls), np.float32)
        for k in range(0, len(crops), 64):
            probs[idx[k:k + 64]] = self._probs(crops[k:k + 64])
        per = [(self.names[int(p.argmax())], float(p.max())) for p in probs]
        mean = probs[idx].mean(axis=0) if idx else np.zeros(n_cls)
        top = [int(i) for i in np.argsort(mean)[::-1][:3]]
        plate = [{"name": self.names[i], "prob": round(float(mean[i]), 4),
                  **self.info.get(self.names[i], {})} for i in top]
        return SpeciesResult(per, plate, bool(idx) and plate[0]["prob"] >= MIN_PLATE_PROB)
