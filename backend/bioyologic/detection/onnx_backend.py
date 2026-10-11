"""Inferencia con modelos YOLO exportados a ONNX (onnxruntime), sin PyTorch ni Ultralytics.

Para el servidor en la nube: la imagen Docker pasa de ~2 GB a ~400 MB y usa menos RAM.
Los modelos se exportan con:

    python backend/scripts/export_onnx.py

El preprocesado y el postprocesado reproducen los de Ultralytics (letterbox con
relleno gris 114, RGB / 255, NMS), así que los resultados coinciden con los del `.pt`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import cv2
import numpy as np


def onnx_available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


class OnnxModel:
    def __init__(self, path: str | Path) -> None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0].name
        meta = self.session.get_modelmeta().custom_metadata_map
        self.names: dict[int, str] = {int(k): v for k, v in ast.literal_eval(meta["names"]).items()}

    def run(self, images: list[np.ndarray]) -> np.ndarray:
        """`images` BGR del mismo tamaño -> salida cruda del modelo."""
        batch = np.stack([im[..., ::-1] for im in images]).transpose(0, 3, 1, 2)
        batch = np.ascontiguousarray(batch, dtype=np.float32) / 255.0
        return self.session.run(None, {self.input: batch})[0]


def letterbox(img: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    """Escala sin deformar y rellena hasta `size` × `size` (centrado, gris 114)."""
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    nh, nw = round(h * r), round(w * r)
    if (nh, nw) != (h, w):
        img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    dx, dy = (size - nw) / 2, (size - nh) / 2
    top, left = round(dy - 0.1), round(dx - 0.1)
    bottom, right = round(dy + 0.1), round(dx + 0.1)
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return img, r, left, top


class OnnxDetector:
    """Detector YOLO (salida [B, 4 + clases, anclas]) con la misma interfaz que usa ColonyDetector."""

    def __init__(self, path: str | Path, max_det: int = 300) -> None:
        self.model = OnnxModel(path)
        self.names = self.model.names
        self.max_det = max_det

    def predict(self, images: list[np.ndarray], conf: float, iou: float, imgsz: int):
        """Devuelve, por imagen, (cajas xyxy, confianzas, clases) en píxeles de esa imagen."""
        boxed = [letterbox(im, imgsz) for im in images]
        out = self.model.run([b[0] for b in boxed])
        results = []
        for (_, r, left, top), im, pred in zip(boxed, images, out):
            p = pred.T                                   # anclas × (cx, cy, w, h, clases...)
            scores = p[:, 4:]
            cls = scores.argmax(1)
            sc = scores[np.arange(len(p)), cls]
            keep = sc > conf
            p, cls, sc = p[keep], cls[keep], sc[keep]
            xywh = p[:, :4].copy()
            xywh[:, :2] -= xywh[:, 2:] / 2
            # NMS por clase: se desplazan las cajas de cada clase para que no se solapen entre sí.
            shifted = np.hstack([xywh[:, :2] + cls[:, None] * 4096.0, xywh[:, 2:]])
            idx = cv2.dnn.NMSBoxes(shifted.tolist(), sc.tolist(), conf, iou) if len(sc) else []
            idx = np.array(idx, dtype=int).reshape(-1)[: self.max_det]
            xyxy = np.hstack([xywh[idx, :2], xywh[idx, :2] + xywh[idx, 2:]])
            xyxy[:, [0, 2]] = ((xyxy[:, [0, 2]] - left) / r).clip(0, im.shape[1])
            xyxy[:, [1, 3]] = ((xyxy[:, [1, 3]] - top) / r).clip(0, im.shape[0])
            results.append((xyxy, sc[idx], cls[idx]))
        return results


class OnnxClassifier:
    """Clasificador YOLO-cls: la salida ya son probabilidades (softmax)."""

    def __init__(self, path: str | Path) -> None:
        self.model = OnnxModel(path)
        self.names = self.model.names

    def predict(self, crops: list[np.ndarray], imgsz: int) -> np.ndarray:
        crops = [c if c.shape[:2] == (imgsz, imgsz) else
                 cv2.resize(c, (imgsz, imgsz), interpolation=cv2.INTER_LINEAR) for c in crops]
        return self.model.run(crops)
