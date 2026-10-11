"""Genera el icono de Bioyologic (hélice de ADN + hoja) para Android, iOS y web.

    python app/tool/make_icons.py
"""

import json
import math
from pathlib import Path

import cv2
import numpy as np

APP = Path(__file__).resolve().parents[1]
GREEN = (69, 92, 31)      # BGR de #1F5C45
MINT = (176, 208, 143)    # BGR de #8FD0B0
WHITE = (255, 255, 255)
SS = 4                    # superposición para suavizar bordes


def draw_logo(size: int, rounded: bool, pad: float = 0.0) -> np.ndarray:
    """Icono BGRA. `pad` deja margen (iconos adaptativos de Android)."""
    S = size * SS
    img = np.zeros((S, S, 4), np.uint8)
    if rounded:
        r = int(S * 0.22)
        cv2.rectangle(img, (r, 0), (S - r, S), (*GREEN, 255), -1)
        cv2.rectangle(img, (0, r), (S, S - r), (*GREEN, 255), -1)
        for cx, cy in [(r, r), (S - r, r), (r, S - r), (S - r, S - r)]:
            cv2.circle(img, (cx, cy), r, (*GREEN, 255), -1, cv2.LINE_AA)
    else:
        img[:] = (*GREEN, 255)

    inner = S * (1 - 2 * pad)
    off = S * pad
    w, h = inner * 0.36, inner * 0.62
    x0, y0 = off + (inner - w) / 2, off + inner * 0.19
    top, bottom = y0 + h * 0.30, y0 + h

    def pt(t: float, phase: float) -> tuple[int, int]:
        y = top + (bottom - top) * t
        x = x0 + w / 2 + w * 0.36 * math.sin(t * 2 * math.pi * 1.25 + phase)
        return int(x), int(y)

    for k in range(1, 8):
        t = k / 8
        cv2.line(img, pt(t, 0), pt(t, math.pi), (*WHITE, 255), max(1, int(w * 0.06)), cv2.LINE_AA)
    for phase, col in [(0.0, MINT), (math.pi, WHITE)]:
        pts = np.array([pt(i / 60, phase) for i in range(61)], np.int32)
        cv2.polylines(img, [pts], False, (*col, 255), int(w * 0.12), cv2.LINE_AA)
    # Hoja
    bx, by = pt(0, 0)
    leaf = []
    for i in range(41):
        t = i / 40
        leaf.append(((1 - t) ** 2 * bx + 2 * (1 - t) * t * (x0 + w * 0.05) + t ** 2 * (x0 + w * 0.62),
                     (1 - t) ** 2 * by + 2 * (1 - t) * t * (y0 + h * 0.12) + t ** 2 * y0))
    for i in range(41):
        t = i / 40
        leaf.append(((1 - t) ** 2 * (x0 + w * 0.62) + 2 * (1 - t) * t * (x0 + w * 0.80) + t ** 2 * bx,
                     (1 - t) ** 2 * y0 + 2 * (1 - t) * t * (y0 + h * 0.22) + t ** 2 * by))
    cv2.fillPoly(img, [np.array(leaf, np.int32)], (*MINT, 255), cv2.LINE_AA)
    return cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)


def save(img: np.ndarray, path: Path, size: int, alpha: bool = True) -> None:
    out = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    if not alpha:  # iOS no admite transparencia en el icono
        out = out[..., :3]
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), out)


def main() -> None:
    rounded = draw_logo(1024, rounded=True)
    square = draw_logo(1024, rounded=False)
    adaptive_fg = draw_logo(1024, rounded=False, pad=0.17)

    # Android: icono clásico + adaptativo
    res = APP / "android" / "app" / "src" / "main" / "res"
    for d, s in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        save(rounded, res / f"mipmap-{d}" / "ic_launcher.png", s)
        fg = adaptive_fg.copy()
        save(fg, res / f"mipmap-{d}" / "ic_launcher_foreground.png", int(s * 108 / 48))
    (res / "mipmap-anydpi-v26").mkdir(exist_ok=True)
    (res / "mipmap-anydpi-v26" / "ic_launcher.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/bio_green"/>\n'
        '    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>\n'
        '</adaptive-icon>\n')

    # iOS: respeta los nombres y tamaños del AppIcon existente
    icon_set = APP / "ios" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"
    for entry in json.loads((icon_set / "Contents.json").read_text())["images"]:
        if "filename" in entry:
            pts = float(entry["size"].split("x")[0])
            scale = int(entry["scale"].rstrip("x"))
            save(square, icon_set / entry["filename"], int(round(pts * scale)), alpha=False)

    # Web
    web = APP / "web"
    save(rounded, web / "favicon.png", 32)
    for name, s in [("Icon-192.png", 192), ("Icon-512.png", 512)]:
        save(rounded, web / "icons" / name, s)
    for name, s in [("Icon-maskable-192.png", 192), ("Icon-maskable-512.png", 512)]:
        save(adaptive_fg, web / "icons" / name, s)
    print("Iconos generados")


if __name__ == "__main__":
    main()
