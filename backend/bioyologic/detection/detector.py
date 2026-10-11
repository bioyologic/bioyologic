"""Detector de colonias basado en YOLO (Ultralytics).

Las colonias suelen medir entre 0,5 % y 2 % del ancho de la foto. Si se
redujera la imagen completa a 640 px, muchas quedarían en 2-3 píxeles. Por
eso la inferencia puede hacerse por tiles (teselas) solapados a resolución
nativa y después fusionar los resultados.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    class_id: int
    class_name: str
    class_confidence: float | None = None   # probabilidad de la especie (clasificador)

    def to_dict(self) -> dict:
        return asdict(self)


def _tile_starts(length: int, tile: int, overlap: float) -> list[int]:
    if length <= tile:
        return [0]
    step = max(1, int(tile * (1 - overlap)))
    starts = list(range(0, length - tile, step))
    starts.append(length - tile)
    return starts


def merge_detections(dets: list[Detection], ios_thr: float = 0.6) -> list[Detection]:
    """NMS sin distinguir clases usando intersección / área de la caja menor (IoS).

    Con IoU, la colonia cortada por el borde de un tile y la misma colonia
    completa en el tile vecino no se suprimen (IoU bajo). El IoS sí lo
    resuelve porque la caja parcial queda casi contenida en la completa.
    """
    if not dets:
        return []
    boxes = np.array([[d.x1, d.y1, d.x2, d.y2] for d in dets], dtype=np.float32)
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    # Prioridad: confianza, y a igualdad, la caja más grande (la no recortada).
    order = sorted(range(len(dets)), key=lambda i: (dets[i].confidence, areas[i]), reverse=True)
    merged: list[tuple[int, Detection]] = []
    suppressed = np.zeros(len(dets), bool)
    for i in order:
        if suppressed[i]:
            continue
        xx1 = np.maximum(boxes[i, 0], boxes[:, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[:, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[:, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[:, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        ios = inter / np.maximum(np.minimum(areas[i], areas), 1e-6)
        group = (ios > ios_thr) & ~suppressed
        suppressed |= group
        # La caja resultante es la unión del grupo: si la detección más confiable
        # era la mitad de una colonia cortada por el tile, se recupera completa.
        g = boxes[group]
        d = dets[i]
        merged.append((i, Detection(float(g[:, 0].min()), float(g[:, 1].min()),
                                    float(g[:, 2].max()), float(g[:, 3].max()),
                                    d.confidence, d.class_id, d.class_name)))
    return [d for _, d in sorted(merged, key=lambda t: t[0])]


class ColonyDetector:
    """Detector YOLO por tiles.

    Si junto al modelo existe `<modelo>.json` (lo genera el notebook de Colab),
    se usan sus valores de `max_side`, `tile` e `imgsz`: la foto se reduce al
    mismo tamaño máximo que se usó al entrenar para que las colonias tengan la
    misma escala en píxeles.
    """

    def __init__(self, weights: str | Path, conf: float = 0.25, iou: float = 0.5,
                 imgsz: int = 640, tile: int | None = 640, overlap: float = 0.2,
                 max_side: int | None = None, device: str | None = None) -> None:
        weights = Path(weights)
        meta_path = weights.with_suffix(".json")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        if weights.suffix == ".onnx":
            from .onnx_backend import OnnxDetector
            self.model = OnnxDetector(weights)
        else:
            from ultralytics import YOLO
            self.model = YOLO(str(weights))
        self.names: dict[int, str] = self.model.names
        self.conf, self.iou = conf, iou
        self.imgsz = meta.get("imgsz", imgsz)
        self.tile = meta.get("tile", tile) if tile else None
        self.max_side = meta.get("max_side", max_side)
        self.overlap, self.device = overlap, device

    def _predict(self, images: list[np.ndarray]):
        """Por imagen: (cajas xyxy, confianzas, clases) como arrays de NumPy."""
        if not hasattr(self.model, "export"):     # OnnxDetector
            return self.model.predict(images, self.conf, self.iou, self.imgsz)
        out = []
        for res in self.model.predict(images, conf=self.conf, iou=self.iou, imgsz=self.imgsz,
                                      device=self.device, verbose=False):
            b = res.boxes
            out.append((b.xyxy.cpu().numpy(), b.conf.cpu().numpy(), b.cls.cpu().numpy().astype(int)))
        return out

    def detect(self, image: np.ndarray) -> list[Detection]:
        """`image` en BGR (como lo devuelve cv2.imread). Cajas en píxeles de `image`."""
        scale = 1.0
        if self.max_side and max(image.shape[:2]) > self.max_side:
            scale = self.max_side / max(image.shape[:2])
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        dets = self._detect(image)
        if scale != 1.0:
            for d in dets:
                d.x1, d.y1, d.x2, d.y2 = d.x1 / scale, d.y1 / scale, d.x2 / scale, d.y2 / scale
        return dets

    def _detect(self, image: np.ndarray) -> list[Detection]:
        h, w = image.shape[:2]
        if not self.tile or max(h, w) <= self.tile:
            offsets, crops = [(0, 0)], [image]
        else:
            offsets = [(x, y) for y in _tile_starts(h, self.tile, self.overlap)
                       for x in _tile_starts(w, self.tile, self.overlap)]
            crops = [image[y:y + self.tile, x:x + self.tile] for x, y in offsets]

        dets: list[Detection] = []
        batch = 8
        for i in range(0, len(crops), batch):
            for (ox, oy), (xyxy, confs, clss) in zip(offsets[i:i + batch], self._predict(crops[i:i + batch])):
                for (x1, y1, x2, y2), c, k in zip(xyxy, confs, clss):
                    dets.append(Detection(float(x1 + ox), float(y1 + oy), float(x2 + ox),
                                          float(y2 + oy), float(c), int(k), self.names[int(k)]))
        return merge_detections(dets) if len(crops) > 1 else dets
