"""Control de calidad de la foto: borrosa, oscura, con reflejos, placa descentrada o muy lejos.

Los umbrales se calibraron con fotos reales de los dos datasets (Makrai et al. 2023; Du 2026) y con
versiones estropeadas a propósito: hay un margen amplio entre las fotos buenas y las malas, para no dar
falsas alarmas. Las advertencias no bloquean el análisis: dicen qué mejorar en la próxima foto.
"""

from __future__ import annotations

import cv2
import numpy as np

NITIDEZ_MIN = 1.2      # varianza del laplaciano / varianza de la imagen × 100 (buenas: 3-31; borrosas: < 0,8)
BRILLO_MIN = 65        # brillo medio (canal V) de la placa (buenas: 93-234; oscuras: < 60)
REFLEJO_MAX = 0.006    # fracción de la placa con brillo saturado y sin color (buenas: < 0,3 %; con reflejo: > 1 %)
DESCENTRADA_MAX = 0.15  # distancia del centro de la placa al de la foto, en lados cortos (buenas: < 0,05)
TAMANO_MIN = 0.55      # diámetro de la placa / lado corto de la foto (buenas: > 0,8)


def _reducir(img: np.ndarray, lado: int = 1024) -> np.ndarray:
    h, w = img.shape[:2]
    s = lado / max(h, w)
    return cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else img


def _placa(img: np.ndarray) -> tuple[float, float, float] | None:
    """Círculo de la placa: la mancha clara más grande (la placa resalta sobre el fondo)."""
    h, w = img.shape[:2]
    v = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2], (0, 0), 3)
    _, th = cv2.threshold(v, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    contornos, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return None
    c = max(contornos, key=cv2.contourArea)
    (x, y), r = cv2.minEnclosingCircle(c)
    if r < 0.15 * min(h, w) or cv2.contourArea(c) / (np.pi * r * r) < 0.55:
        return None
    return float(x), float(y), float(r)


def _donde(dx: float, dy: float) -> str:
    """Posición aproximada de un punto respecto al centro: 'arriba a la derecha', 'abajo', 'en el centro'..."""
    v = "arriba" if dy < -0.25 else "abajo" if dy > 0.25 else ""
    h = "a la izquierda" if dx < -0.25 else "a la derecha" if dx > 0.25 else ""
    return " ".join(p for p in (v, h) if p) or "en el centro"


def assess(image: np.ndarray) -> dict:
    """{"ok", "issues": [{"code", "message"}], "metrics": {...}} sobre una foto BGR."""
    img = _reducir(image)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, w = gray.shape
    placa = _placa(img)
    if placa:
        x, y, r = placa
        yy, xx = np.ogrid[:h, :w]
        region = (xx - x) ** 2 + (yy - y) ** 2 <= (r * 0.95) ** 2
    else:
        region = np.ones_like(gray, bool)

    nitidez = float(cv2.Laplacian(gray, cv2.CV_64F)[region].var() / max(float(gray[region].var()), 1.0) * 100)
    brillo = float(hsv[..., 2][region].mean())
    saturado = (hsv[..., 2] >= 245) & (hsv[..., 1] <= 40) & region
    reflejo = float(saturado.sum() / max(int(region.sum()), 1))
    metrics = {"sharpness": round(nitidez, 2), "brightness": round(brillo, 1), "glare": round(reflejo, 4),
               "plate_found": placa is not None}

    issues = []
    if placa is None:
        issues.append({"code": "no_plate", "message": "No se distingue bien el borde de la placa. Centra la placa "
                                                      "completa en la foto, sobre un fondo oscuro."})
    else:
        x, y, r = placa
        offset = float(np.hypot(x - w / 2, y - h / 2) / min(h, w))
        size = float(2 * r / min(h, w))
        metrics |= {"plate_offset": round(offset, 3), "plate_size": round(size, 3)}
        if offset > DESCENTRADA_MAX:
            issues.append({"code": "off_center",
                           "message": f"La placa está descentrada ({_donde((x - w / 2) / (w / 2), (y - h / 2) / (h / 2))}). "
                                      "Usa el círculo guía de la cámara."})
        if size < TAMANO_MIN:
            issues.append({"code": "too_far", "message": "La placa se ve pequeña: acércate para que ocupe casi toda "
                                                         "la foto y se vean las colonias pequeñas."})
    if nitidez < NITIDEZ_MIN:
        issues.append({"code": "blurry", "message": "La foto está borrosa: el conteo puede ser menos preciso. Toca "
                                                    "la pantalla para enfocar y mantén el celular quieto."})
    if brillo < BRILLO_MIN:
        issues.append({"code": "dark", "message": "La foto está muy oscura. Usa la caja de iluminación o más luz."})
    if reflejo > REFLEJO_MAX:
        ys, xs = np.nonzero(saturado)
        cx, cy, rr = placa if placa else (w / 2, h / 2, min(h, w) / 2)
        lugar = _donde((xs.mean() - cx) / rr, (ys.mean() - cy) / rr)
        issues.append({"code": "glare", "message": f"Hay reflejos de luz sobre la placa ({lugar}) que pueden contarse "
                                                   "como colonias. Usa la caja de iluminación o cambia el ángulo."})
    return {"ok": not issues, "issues": issues, "metrics": metrics}
