"""Pipeline completo: detecciones YOLO -> morfología -> conteo -> imagen anotada."""

from __future__ import annotations

import colorsys
from datetime import datetime

import cv2
import numpy as np

from ..detection.detector import Detection
from .counting import summarize
from .morphology import describe_colony


def class_color(class_id: int) -> tuple[int, int, int]:
    """Color BGR distinto y estable por clase."""
    h = (0.5 + class_id * 0.618033988749895) % 1.0  # clase 0 = cian: contrasta con agar rojo y beige
    r, g, b = colorsys.hsv_to_rgb(h, 0.85, 1.0)
    return int(b * 255), int(g * 255), int(r * 255)


def analyze(image: np.ndarray, detections: list[Detection], *,
            mm_per_px: float | None = None, dilution: float | None = None,
            volume_ml: float | None = None, min_confidence: float = 0.0,
            species: dict | None = None) -> tuple[dict, np.ndarray]:
    """`species` = {identified, top: [top-3 de la placa]} del clasificador, si se usó."""
    """Devuelve (resultado serializable a JSON, imagen BGR anotada)."""
    annotated = image.copy()
    colonies = []
    dets = [d for d in detections if d.confidence >= min_confidence]
    dets.sort(key=lambda d: (d.y1 + d.y2, d.x1 + d.x2))  # numeración de arriba abajo

    thick = max(1, round(max(image.shape[:2]) / 800))
    for idx, d in enumerate(dets, start=1):
        morph, mask, (x0, y0) = describe_colony(image, (d.x1, d.y1, d.x2, d.y2), mm_per_px)
        color = class_color(d.class_id)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(annotated, contours, -1, color, thick, offset=(x0, y0))
        cv2.putText(annotated, str(idx), (int(d.x2) + 2, int(d.y1) + 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35 * thick, color, max(1, thick // 2), cv2.LINE_AA)
        colonies.append({
            "id": idx,
            "class_id": d.class_id,
            "class_name": d.class_name,
            "confidence": round(d.confidence, 4),
            "species_confidence": None if d.class_confidence is None else round(d.class_confidence, 4),
            "bbox": [round(v, 1) for v in (d.x1, d.y1, d.x2, d.y2)],
            "center": [round((d.x1 + d.x2) / 2, 1), round((d.y1 + d.y2) / 2, 1)],
            "morphology": morph.to_dict(),
        })

    summary = summarize(colonies, dilution, volume_ml)
    result = {
        "analyzed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "image_size": [image.shape[1], image.shape[0]],
        "mm_per_px": mm_per_px,
        "summary": summary.to_dict(),
        "colonies": colonies,
        "species": species,
    }
    return result, annotated
