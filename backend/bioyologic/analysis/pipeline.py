"""Pipeline completo: detecciones YOLO -> morfología -> conteo -> imagen anotada.

`recount` aplica la corrección manual del usuario (quitar colonias detectadas, agregar las que faltaron)
sobre un análisis guardado, y deja registro de lo corregido.
"""

from __future__ import annotations

import colorsys
from collections import Counter
from datetime import datetime

import cv2
import numpy as np

from ..detection.detector import Detection
from .counting import summarize
from .morphology import describe_colony

MANUAL_COLOR = (0, 140, 255)   # BGR naranja: colonias agregadas a mano
REMOVED_COLOR = (60, 60, 230)  # BGR rojo: detecciones descartadas a mano


def class_color(class_id: int) -> tuple[int, int, int]:
    """Color BGR distinto y estable por clase."""
    h = (0.5 + class_id * 0.618033988749895) % 1.0  # clase 0 = cian: contrasta con agar rojo y beige
    r, g, b = colorsys.hsv_to_rgb(h, 0.85, 1.0)
    return int(b * 255), int(g * 255), int(r * 255)


def _thickness(image: np.ndarray) -> int:
    return max(1, round(max(image.shape[:2]) / 800))


def _draw_colony(annotated: np.ndarray, image: np.ndarray, bbox, color, label: str, thick: int) -> None:
    _, mask, (x0, y0) = describe_colony(image, tuple(bbox), None)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(annotated, contours, -1, color, thick, offset=(x0, y0))
    cv2.putText(annotated, label, (int(bbox[2]) + 2, int(bbox[1]) + 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35 * thick, color, max(1, thick // 2), cv2.LINE_AA)


def analyze(image: np.ndarray, detections: list[Detection], *,
            mm_per_px: float | None = None, dilution: float | None = None,
            volume_ml: float | None = None, min_confidence: float = 0.0,
            species: dict | None = None) -> tuple[dict, np.ndarray]:
    """Devuelve (resultado serializable a JSON, imagen BGR anotada).

    `species` = {identified, top: [top-3 de la placa]} del clasificador, si se usó.
    """
    annotated = image.copy()
    colonies = []
    dets = [d for d in detections if d.confidence >= min_confidence]
    dets.sort(key=lambda d: (d.y1 + d.y2, d.x1 + d.x2))  # numeración de arriba abajo

    thick = _thickness(image)
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


def recount(image: np.ndarray, result: dict, removed: set[int], added: list[tuple[float, float, float]],
            dilution: float | None, volume_ml: float | None, *, by: str = "") -> tuple[dict, np.ndarray]:
    """Corrección manual del conteo sobre un análisis guardado.

    `removed`: ids de colonias detectadas por el modelo que el usuario descarta.
    `added`: colonias que el modelo no vio, como (x, y, radio) en píxeles de la foto original.
    La corrección siempre se aplica sobre las detecciones originales del modelo, así que es idempotente:
    enviar listas vacías deshace cualquier corrección anterior.
    """
    detected = result.get("detected_colonies") or result["colonies"]
    detected = [c for c in detected if not c.get("manual")]
    mm = result.get("mm_per_px")
    h, w = image.shape[:2]
    keep = [c for c in detected if c["id"] not in removed]
    gone = [c for c in detected if c["id"] in removed]

    # Las colonias agregadas toman la clase más frecuente de la placa (la que el usuario no corrigió).
    clase = Counter(c["class_name"] for c in keep).most_common(1)
    clase_nombre, clase_id = (clase[0][0], next(c["class_id"] for c in keep if c["class_name"] == clase[0][0])) \
        if clase else ("colony", 0)
    next_id = max((c["id"] for c in detected), default=0) + 1
    manual = []
    for i, (x, y, r) in enumerate(added):
        box = (max(0.0, x - r), max(0.0, y - r), min(float(w), x + r), min(float(h), y + r))
        morph, _, _ = describe_colony(image, box, mm)
        manual.append({
            "id": next_id + i,
            "class_id": clase_id,
            "class_name": clase_nombre,
            "confidence": None,
            "species_confidence": None,
            "bbox": [round(v, 1) for v in box],
            "center": [round(x, 1), round(y, 1)],
            "morphology": morph.to_dict(),
            "manual": True,
        })

    annotated = image.copy()
    thick = _thickness(image)
    for c in keep:
        _draw_colony(annotated, image, c["bbox"], class_color(c["class_id"]), str(c["id"]), thick)
    for c in manual:
        _draw_colony(annotated, image, c["bbox"], MANUAL_COLOR, f"+{c['id']}", thick)
    for c in gone:  # se tachan, no se borran: queda a la vista qué se descartó
        x1, y1, x2, y2 = (int(v) for v in c["bbox"])
        cv2.line(annotated, (x1, y1), (x2, y2), REMOVED_COLOR, thick + 1, cv2.LINE_AA)
        cv2.line(annotated, (x1, y2), (x2, y1), REMOVED_COLOR, thick + 1, cv2.LINE_AA)

    colonies = keep + manual
    out = dict(result)
    out["colonies"] = colonies
    out["summary"] = summarize(colonies, dilution, volume_ml).to_dict()
    # La imagen anotada cambia en cada corrección: la versión va en su URL para que no se use la de caché.
    out["annotated_version"] = int(result.get("annotated_version", 0)) + 1
    if removed or added:
        out["detected_colonies"] = detected
        out["correction"] = {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "by": by,
            "detected_total": len(detected),
            "removed": sorted(c["id"] for c in gone),
            "added": [{"x": round(x, 1), "y": round(y, 1), "r": round(r, 1)} for x, y, r in added],
        }
    else:
        out.pop("detected_colonies", None)
        out.pop("correction", None)
    return out, annotated
