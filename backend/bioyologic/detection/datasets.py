"""Conversión de bases de datos públicas de colonias al formato YOLO.

Fuentes soportadas:
- AGAR (NeuroSYS, anotada por microbiólogos): cada imagen `N.jpg` tiene un
  `N.json` con {"labels": [{"x", "y", "width", "height", "class"}], ...}
  en píxeles absolutos (x, y = esquina superior izquierda).
- Pascal VOC (p. ej. Makrai et al. 2023, Scientific Data): `N.xml` con
  <object><name/><bndbox><xmin/>...</bndbox></object>.
- YOLO: `N.txt` con "cls cx cy w h" normalizados; se copia tal cual.

Salida (estructura estándar de Ultralytics):
    out/images/{train,val,test}/*.jpg
    out/labels/{train,val,test}/*.txt
    out/data.yaml
"""

from __future__ import annotations

import json
import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import cv2
import yaml

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass
class Box:
    cls: str
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class Sample:
    image: Path
    boxes: list[Box]


def _find_image(stem_path: Path) -> Path | None:
    for ext in IMG_EXTS:
        for cand in (stem_path.with_suffix(ext), stem_path.with_suffix(ext.upper())):
            if cand.exists():
                return cand
    return None


def load_agar(root: Path) -> list[Sample]:
    samples = []
    for ann in sorted(root.rglob("*.json")):
        img = _find_image(ann)
        if img is None:
            continue
        data = json.loads(ann.read_text(encoding="utf-8"))
        boxes = [
            Box(str(lb["class"]), lb["x"], lb["y"], lb["x"] + lb["width"], lb["y"] + lb["height"])
            for lb in data.get("labels", [])
        ]
        # En AGAR, las placas "uncountable" (incontables) no tienen cajas: se descartan.
        if boxes or data.get("colonies_number", 0) == 0:
            samples.append(Sample(img, boxes))
    return samples


def load_voc(root: Path) -> list[Sample]:
    samples = []
    for ann in sorted(root.rglob("*.xml")):
        img = _find_image(ann)
        if img is None:
            continue
        tree = ET.parse(ann).getroot()
        boxes = []
        for obj in tree.iter("object"):
            bb = obj.find("bndbox")
            boxes.append(Box(
                obj.findtext("name", "colony").strip(),
                float(bb.findtext("xmin")), float(bb.findtext("ymin")),
                float(bb.findtext("xmax")), float(bb.findtext("ymax")),
            ))
        samples.append(Sample(img, boxes))
    return samples


def load_yolo(root: Path, class_names: list[str]) -> list[Sample]:
    samples = []
    for lbl in sorted(root.rglob("*.txt")):
        img = _find_image(lbl)
        if img is None:
            continue
        im = cv2.imread(str(img))
        if im is None:
            continue
        h, w = im.shape[:2]
        boxes = []
        for line in lbl.read_text().split("\n"):
            parts = line.split()
            if len(parts) != 5:
                continue
            c, cx, cy, bw, bh = int(parts[0]), *map(float, parts[1:])
            name = class_names[c] if c < len(class_names) else str(c)
            boxes.append(Box(name, (cx - bw / 2) * w, (cy - bh / 2) * h,
                             (cx + bw / 2) * w, (cy + bh / 2) * h))
        samples.append(Sample(img, boxes))
    return samples


def _tiles(length: int, tile: int, overlap: float) -> list[int]:
    if length <= tile:
        return [0]
    step = int(tile * (1 - overlap))
    starts = list(range(0, length - tile, step))
    starts.append(length - tile)
    return starts


def _write_yolo(image, boxes: list[Box], class_ids: dict[str, int],
                img_out: Path, lbl_out: Path, min_visible: float = 0.5) -> int:
    h, w = image.shape[:2]
    lines = []
    for b in boxes:
        x1, y1 = max(0.0, b.x1), max(0.0, b.y1)
        x2, y2 = min(float(w), b.x2), min(float(h), b.y2)
        full = (b.x2 - b.x1) * (b.y2 - b.y1)
        vis = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        # Colonias cortadas por el borde del tile: se conservan si se ve >= 50 %.
        if full <= 0 or vis / full < min_visible:
            continue
        cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
        lines.append(f"{class_ids[b.cls]} {cx:.6f} {cy:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
    cv2.imwrite(str(img_out), image)
    lbl_out.write_text("\n".join(lines))
    return len(lines)


def build_yolo_dataset(samples: list[Sample], out: Path, *, single_class: bool = False,
                       split: tuple[float, float, float] = (0.8, 0.1, 0.1),
                       tile: int | None = None, overlap: float = 0.2,
                       seed: int = 42) -> dict:
    """Escribe el dataset YOLO y devuelve un resumen con el número de imágenes y cajas."""
    if single_class:
        for s in samples:
            for b in s.boxes:
                b.cls = "colony"
    names = sorted({b.cls for s in samples for b in s.boxes}) or ["colony"]
    class_ids = {n: i for i, n in enumerate(names)}

    # La partición se hace por imagen ORIGINAL, antes del teselado, para que
    # tiles de una misma placa no acaben a la vez en train y en test.
    rng = random.Random(seed)
    order = samples[:]
    rng.shuffle(order)
    n = len(order)
    n_train, n_val = int(n * split[0]), int(n * split[1])
    parts = {
        "train": order[:n_train],
        "val": order[n_train:n_train + n_val],
        "test": order[n_train + n_val:],
    }

    summary = {"classes": names, "splits": {}}
    for part, items in parts.items():
        img_dir, lbl_dir = out / "images" / part, out / "labels" / part
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
        n_imgs = n_boxes = 0
        for s in items:
            image = cv2.imread(str(s.image))
            if image is None:
                continue
            stem = f"{s.image.parent.name}_{s.image.stem}"
            if not tile:
                n_boxes += _write_yolo(image, s.boxes, class_ids,
                                       img_dir / f"{stem}.jpg", lbl_dir / f"{stem}.txt")
                n_imgs += 1
                continue
            h, w = image.shape[:2]
            for y0 in _tiles(h, tile, overlap):
                for x0 in _tiles(w, tile, overlap):
                    crop = image[y0:y0 + tile, x0:x0 + tile]
                    shifted = [Box(b.cls, b.x1 - x0, b.y1 - y0, b.x2 - x0, b.y2 - y0) for b in s.boxes]
                    name = f"{stem}_{x0}_{y0}"
                    n_boxes += _write_yolo(crop, shifted, class_ids,
                                           img_dir / f"{name}.jpg", lbl_dir / f"{name}.txt")
                    n_imgs += 1
        summary["splits"][part] = {"images": n_imgs, "boxes": n_boxes}

    data_yaml = {
        "path": str(out.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {i: n for n, i in class_ids.items()},
    }
    (out / "data.yaml").write_text(yaml.safe_dump(data_yaml, sort_keys=False, allow_unicode=True))
    return summary
