"""Generador de placas de Petri sintéticas con anotaciones en formato AGAR.

Sirve para pruebas automáticas, para la demo y para comprobar el pipeline de
punta a punta sin datos reales. NO sustituye al entrenamiento con datos
reales (ver training/Bioyologic_entrenamiento.ipynb).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class Species:
    name: str
    color: tuple[int, int, int]   # BGR del centro de la colonia
    radius: tuple[int, int]       # rango de radio en px (placa de 1024 px)
    irregular: float              # 0 = circular, >0 = borde lobulado


# Aspecto aproximado sobre agar nutritivo (las cinco especies de AGAR).
SPECIES = [
    Species("E.coli", (175, 205, 225), (9, 16), 0.0),
    Species("S.aureus", (95, 195, 235), (5, 10), 0.0),
    Species("P.aeruginosa", (150, 185, 165), (8, 15), 0.12),
    Species("B.subtilis", (200, 215, 222), (10, 20), 0.30),
    Species("C.albicans", (235, 240, 242), (6, 12), 0.0),
]

AGAR_BGR = (120, 170, 200)


def _colony_polygon(rng, cx, cy, r, irregular):
    n = 48
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    if irregular > 0:
        k = rng.integers(5, 10)
        rad = r * (1 + irregular * (0.6 * np.sin(k * ang + rng.uniform(0, 6))
                                    + 0.4 * rng.uniform(-1, 1, n)))
    else:
        squash = rng.uniform(0.88, 1.0)
        rad = r * np.where(np.arange(n) % 2 == 0, 1.0, 1.0)
        ang_rot = rng.uniform(0, np.pi)
        x = rad * np.cos(ang) * 1.0
        y = rad * np.sin(ang) * squash
        xr = x * np.cos(ang_rot) - y * np.sin(ang_rot)
        yr = x * np.sin(ang_rot) + y * np.cos(ang_rot)
        return np.stack([cx + xr, cy + yr], 1).astype(np.int32)
    return np.stack([cx + rad * np.cos(ang), cy + rad * np.sin(ang)], 1).astype(np.int32)


def draw_plate(size: int = 1024, n_colonies: int = 40, seed: int | None = None,
               species: list[Species] | None = None) -> tuple[np.ndarray, list[dict]]:
    rng = np.random.default_rng(seed)
    if species is None:
        # Cada placa contiene 1-2 especies, como un cultivo puro o mixto.
        idx = rng.choice(len(SPECIES), size=int(rng.integers(1, 3)), replace=False)
        species = [SPECIES[i] for i in idx]

    # Fondo de mesa oscuro con gradiente suave.
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / size
    img = np.dstack([30 + 15 * yy, 32 + 15 * yy, 34 + 15 * xx]).astype(np.float32)

    c = size // 2
    plate_r = int(size * 0.46)
    agar = np.zeros((size, size), np.uint8)
    cv2.circle(agar, (c, c), plate_r, 1, -1)
    tint = np.array(AGAR_BGR, np.float32) * rng.uniform(0.92, 1.06, 3)
    # Viñeteado: el agar es algo más oscuro hacia el borde.
    d = np.sqrt((xx * size - c) ** 2 + (yy * size - c) ** 2) / plate_r
    shade = (1.0 - 0.12 * np.clip(d, 0, 1) ** 2)[..., None]
    img = np.where(agar[..., None] == 1, tint * shade, img)
    # Borde de la placa con reflejo.
    rim = img.copy()
    cv2.circle(rim, (c, c), plate_r, (215, 220, 225), 5, cv2.LINE_AA)
    cv2.ellipse(rim, (c, c), (plate_r - 8, plate_r - 8), 0, 200, 250, (250, 250, 250), 3, cv2.LINE_AA)
    img = 0.75 * rim + 0.25 * img

    labels: list[dict] = []
    tries = 0
    while len(labels) < n_colonies and tries < n_colonies * 60:
        tries += 1
        sp = species[rng.integers(len(species))]
        r = int(rng.integers(sp.radius[0], sp.radius[1] + 1) * size / 1024)
        r = max(3, r)
        ang, dist = rng.uniform(0, 2 * np.pi), rng.uniform(0, plate_r - r * 1.5 - 14)
        cx, cy = c + dist * np.cos(ang), c + dist * np.sin(ang)
        poly = _colony_polygon(rng, cx, cy, r, sp.irregular)
        x0, y0 = poly.min(0)
        x1, y1 = poly.max(0)
        # Sin solapamiento, para que el número real de colonias sea inequívoco.
        if any(not (x1 + 3 < l["x"] or l["x"] + l["width"] + 3 < x0 or
                    y1 + 3 < l["y"] or l["y"] + l["height"] + 3 < y0) for l in labels):
            continue
        # Se dibuja solo en la región de la colonia (mucho más rápido que a placa completa).
        rx0, ry0 = max(0, int(x0) - 2), max(0, int(y0) - 2)
        rx1, ry1 = min(size, int(x1) + 3), min(size, int(y1) + 3)
        mask = np.zeros((ry1 - ry0, rx1 - rx0), np.uint8)
        cv2.fillPoly(mask, [poly - [rx0, ry0]], 1, cv2.LINE_AA)
        # Volumen: centro más claro, borde más oscuro y ligeramente translúcido.
        dist_map = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
        h = np.clip(dist_map / max(1.0, r * 0.6), 0, 1)[..., None]
        col = np.array(sp.color, np.float32) * rng.uniform(0.94, 1.04)
        colony = col * (0.82 + 0.22 * h)
        alpha = (0.65 + 0.35 * h) * mask[..., None]
        roi = img[ry0:ry1, rx0:rx1]
        img[ry0:ry1, rx0:rx1] = roi * (1 - alpha) + colony * alpha
        labels.append({"id": len(labels) + 1, "class": sp.name, "x": int(x0), "y": int(y0),
                       "width": int(x1 - x0 + 1), "height": int(y1 - y0 + 1)})

    img = cv2.GaussianBlur(img, (3, 3), 0.6)
    img += rng.normal(0, 3, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8), labels


def write_agar_dataset(out: Path, n_images: int = 20, size: int = 1024, seed: int = 0) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    for i in range(n_images):
        img, labels = draw_plate(size, int(rng.integers(10, 90)), seed=seed + i)
        cv2.imwrite(str(out / f"{i}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        (out / f"{i}.json").write_text(json.dumps({
            "sample_id": i,
            "classes": sorted({l["class"] for l in labels}),
            "labels": labels,
            "colonies_number": len(labels),
            "background": "synthetic",
        }))
