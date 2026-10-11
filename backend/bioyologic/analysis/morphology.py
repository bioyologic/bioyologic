"""Segmentación y descriptores morfológicos de cada colonia.

Parte "clásica" del sistema híbrido: YOLO localiza la colonia (caja) y aquí,
dentro de esa caja, se segmenta su silueta por contraste de color frente al
agar circundante para medir tamaño, forma, borde y color.

Terminología morfológica (forma, borde) según la descripción macroscópica
habitual en microbiología. La elevación no puede medirse desde una foto
cenital 2D y no se estima.
"""

from __future__ import annotations

import colorsys
import math
from dataclasses import asdict, dataclass

import cv2
import numpy as np


@dataclass
class ColonyMorphology:
    area_px: float
    perimeter_px: float
    diameter_px: float          # diámetro equivalente (círculo de igual área)
    major_axis_px: float
    minor_axis_px: float
    aspect_ratio: float         # eje mayor / eje menor (1 = circular)
    eccentricity: float         # 0 = círculo, -> 1 = alargada
    circularity: float          # 4·pi·A / P²  (1 = círculo perfecto)
    solidity: float             # A / A(envolvente convexa)
    convexity: float            # P(envolvente convexa) / P
    color_rgb: tuple[int, int, int]
    color_hex: str
    color_name: str             # nombre aproximado: beige, amarillo, blanco...
    color_lab: tuple[float, float, float]
    color_std: float            # heterogeneidad de color dentro de la colonia
    contrast: float             # |ΔE| frente al agar (proxy de opacidad)
    form: str                   # puntiforme | circular | irregular
    margin: str                 # entero | ondulado | lobulado
    segmented: bool             # False si se usó la elipse de la caja como respaldo
    area_mm2: float | None = None
    diameter_mm: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _ring_mask(shape: tuple[int, int], width: int) -> np.ndarray:
    m = np.zeros(shape, np.uint8)
    m[:width, :] = m[-width:, :] = 1
    m[:, :width] = m[:, -width:] = 1
    return m.astype(bool)


def segment_colony(image: np.ndarray, box: tuple[float, float, float, float],
                   pad_ratio: float = 0.3) -> tuple[np.ndarray, tuple[int, int], bool]:
    """Devuelve (máscara uint8 del recorte, (x0, y0) del recorte, segmentación_ok)."""
    h, w = image.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    pad = max(3, int(max(bw, bh) * pad_ratio))
    x0, y0 = max(0, int(x1) - pad), max(0, int(y1) - pad)
    xe, ye = min(w, int(math.ceil(x2)) + pad), min(h, int(math.ceil(y2)) + pad)
    crop = image[y0:ye, x0:xe]
    ch, cw = crop.shape[:2]

    # Elipse inscrita en la caja: forma esperada y respaldo si falla la segmentación.
    prior = np.zeros((ch, cw), np.uint8)
    cx, cy = (x1 + x2) / 2 - x0, (y1 + y2) / 2 - y0
    cv2.ellipse(prior, (int(round(cx)), int(round(cy))),
                (max(1, int(bw / 2)), max(1, int(bh / 2))), 0, 0, 360, 1, -1)

    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    ring = _ring_mask((ch, cw), max(2, pad // 2))
    bg = np.median(lab[ring], axis=0)
    dist = np.linalg.norm(lab - bg, axis=2)
    dist = cv2.GaussianBlur(dist, (3, 3), 0)
    dist8 = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    _, mask = cv2.threshold(dist8, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Restringe a la caja (ligeramente ampliada) para no capturar colonias vecinas.
    box_mask = np.zeros_like(mask)
    gx, gy = int(bw * 0.1) + 1, int(bh * 0.1) + 1
    box_mask[max(0, int(y1 - y0) - gy):int(y2 - y0) + gy, max(0, int(x1 - x0) - gx):int(x2 - x0) + gx] = 1
    mask &= box_mask
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    ok = False
    if n > 1:
        # Componente con mayor solapamiento con la elipse esperada.
        overlaps = [(np.logical_and(labels == i, prior).sum(), i) for i in range(1, n)]
        best_overlap, best = max(overlaps)
        cand = (labels == best).astype(np.uint8)
        # Rellena huecos (colonias con centro claro o reflejos).
        contours, _ = cv2.findContours(cand, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cand = np.zeros_like(cand)
        cv2.drawContours(cand, contours, -1, 1, -1)
        ratio = cand.sum() / max(1, prior.sum())
        if best_overlap > 0 and 0.25 <= ratio <= 1.6:
            mask, ok = cand, True
    if not ok:
        mask = prior
    return mask, (x0, y0), ok


def color_name(rgb: tuple[int, int, int]) -> str:
    """Nombre de color en español para un color RGB medio de colonia."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    hue = h * 360
    if v < 0.22:
        return "negro"
    if s < 0.12:
        return "blanco" if v > 0.78 else "gris"
    if s < 0.35 and 20 <= hue < 65 and v > 0.55:
        return "beige"
    if hue < 15 or hue >= 340:
        return "rosa" if s < 0.5 and v > 0.6 else "rojo"
    if hue < 40:
        return "naranja" if v > 0.6 else "marrón"
    if hue < 70:
        return "amarillo" if v > 0.5 else "marrón"
    if hue < 170:
        return "verde"
    if hue < 260:
        return "azul"
    return "violeta"


def _classify_form(circularity: float, aspect: float, diameter_mm: float | None) -> str:
    if diameter_mm is not None and diameter_mm < 1.0:
        return "puntiforme"
    if circularity >= 0.80 and aspect <= 1.25:
        return "circular"
    return "irregular"


def _classify_margin(solidity: float, convexity: float) -> str:
    if solidity >= 0.95 and convexity >= 0.93:
        return "entero"
    if solidity >= 0.85:
        return "ondulado"
    return "lobulado"


def describe_colony(image: np.ndarray, box: tuple[float, float, float, float],
                    mm_per_px: float | None = None) -> tuple[ColonyMorphology, np.ndarray, tuple[int, int]]:
    mask, (x0, y0), ok = segment_colony(image, box)
    # En colonias grandes el borde píxel a píxel es dentado: infla el perímetro y hace
    # que una colonia redonda parezca irregular. Se suaviza con un elemento
    # proporcional a su tamaño (cierre + apertura) antes de medir.
    k = max(3, int(round(math.sqrt(float(mask.sum())) / 12)) | 1)
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    smooth = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_CLOSE, se), cv2.MORPH_OPEN, se)
    if smooth.sum() > 0.5 * mask.sum():
        mask = smooth
    crop = image[y0:y0 + mask.shape[0], x0:x0 + mask.shape[1]]
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cnt = max(contours, key=cv2.contourArea)

    area = float(mask.sum())
    # Perímetro sobre el contorno simplificado (tolerancia 0,4 % de su longitud):
    # quita el escalonado de los píxeles sin borrar lóbulos reales.
    raw_perim = float(cv2.arcLength(cnt, True))
    perim = float(cv2.arcLength(cv2.approxPolyDP(cnt, 0.004 * raw_perim, True), True)) or 1.0
    hull = cv2.convexHull(cnt)
    hull_area = float(cv2.contourArea(hull)) or area
    hull_perim = float(cv2.arcLength(hull, True))
    if len(cnt) >= 5:
        (_, _), (a1, a2), _ = cv2.fitEllipse(cnt)
        major, minor = max(a1, a2), max(1e-6, min(a1, a2))
    else:
        major = minor = 2 * math.sqrt(area / math.pi)
    diameter = 2 * math.sqrt(area / math.pi)
    # Corrección de discretización: en objetos pequeños el perímetro en píxeles
    # se sobreestima y la circularidad cae artificialmente; se limita a 1.
    circularity = min(1.0, 4 * math.pi * area / perim ** 2)
    solidity = min(1.0, area / hull_area) if hull_area > 0 else 1.0
    convexity = min(1.0, hull_perim / perim)
    aspect = major / minor
    ecc = math.sqrt(max(0.0, 1 - (minor / major) ** 2))

    m = mask.astype(bool)
    pix_bgr = crop[m].astype(np.float32)
    b, g, r = (int(round(v)) for v in pix_bgr.mean(axis=0))
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    # Escala L*a*b* real: L en [0,100], a y b centrados en 0.
    lab_real = np.stack([lab[..., 0] * 100 / 255, lab[..., 1] - 128, lab[..., 2] - 128], axis=-1)
    col_lab = lab_real[m].mean(axis=0)
    color_std = float(np.linalg.norm(lab_real[m].std(axis=0)))
    ring = cv2.dilate(mask, np.ones((7, 7), np.uint8)) - cv2.dilate(mask, np.ones((3, 3), np.uint8))
    bg_lab = lab_real[ring.astype(bool)].mean(axis=0) if ring.any() else col_lab
    contrast = float(np.linalg.norm(col_lab - bg_lab))

    diameter_mm = diameter * mm_per_px if mm_per_px else None
    morph = ColonyMorphology(
        area_px=area, perimeter_px=perim, diameter_px=diameter,
        major_axis_px=float(major), minor_axis_px=float(minor),
        aspect_ratio=float(aspect), eccentricity=float(ecc),
        circularity=float(circularity), solidity=float(solidity), convexity=float(convexity),
        color_rgb=(r, g, b), color_hex=f"#{r:02x}{g:02x}{b:02x}", color_name=color_name((r, g, b)),
        color_lab=tuple(round(float(v), 2) for v in col_lab),
        color_std=color_std, contrast=contrast,
        form=_classify_form(circularity, aspect, diameter_mm),
        margin=_classify_margin(solidity, convexity),
        segmented=ok,
        area_mm2=area * mm_per_px ** 2 if mm_per_px else None,
        diameter_mm=diameter_mm,
    )
    return morph, mask, (x0, y0)
