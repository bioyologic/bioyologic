import math

import cv2
import numpy as np
import pytest

from bioyologic.analysis.counting import cfu_per_ml, plate_status, summarize
from bioyologic.analysis.morphology import describe_colony
from bioyologic.analysis.pipeline import analyze
from bioyologic.detection.datasets import build_yolo_dataset, load_agar
from bioyologic.detection.detector import Detection, merge_detections
from bioyologic.synthetic import draw_plate, write_agar_dataset


def _plate_with(shape_fn, size=200):
    img = np.full((size, size, 3), (60, 120, 150), np.uint8)
    shape_fn(img)
    return img


def test_circular_colony_measures():
    img = _plate_with(lambda im: cv2.circle(im, (100, 100), 30, (200, 220, 235), -1))
    m, _, _ = describe_colony(img, (70, 70, 130, 130), mm_per_px=0.05)
    assert m.segmented
    assert m.diameter_px == pytest.approx(60, rel=0.05)
    assert m.diameter_mm == pytest.approx(3.0, rel=0.05)
    assert m.circularity > 0.85
    assert m.form == "circular"
    assert m.margin == "entero"
    # Color medio cercano al dibujado (RGB = 235, 220, 200)
    assert all(abs(a - b) < 8 for a, b in zip(m.color_rgb, (235, 220, 200)))


def test_irregular_colony_is_lobulated():
    def star(im):
        pts = []
        for k in range(16):
            r = 40 if k % 2 == 0 else 18
            a = k * math.pi / 8
            pts.append((100 + r * math.cos(a), 100 + r * math.sin(a)))
        cv2.fillPoly(im, [np.array(pts, np.int32)], (200, 220, 235))
    img = _plate_with(star)
    m, _, _ = describe_colony(img, (60, 60, 140, 140))
    assert m.form == "irregular"
    assert m.margin == "lobulado"
    assert m.solidity < 0.85


def test_elongated_colony_aspect_ratio():
    img = _plate_with(lambda im: cv2.ellipse(im, (100, 100), (45, 15), 0, 0, 360, (200, 220, 235), -1))
    m, _, _ = describe_colony(img, (55, 85, 145, 115))
    assert m.aspect_ratio == pytest.approx(3.0, rel=0.15)
    assert m.eccentricity > 0.9


def test_counting_rules():
    assert plate_status(10) == "pocas"
    assert plate_status(150) == "contable"
    assert plate_status(500) == "incontable"
    # 150 colonias, dilución 10^-4, 0.1 mL sembrados -> 1.5e7 UFC/mL
    assert cfu_per_ml(150, 1e-4, 0.1) == pytest.approx(1.5e7)
    with pytest.raises(ValueError):
        cfu_per_ml(10, 0, 0.1)


def test_merge_detections_removes_tile_duplicates():
    full = Detection(100, 100, 120, 120, 0.9, 0, "a")
    partial = Detection(100, 100, 110, 120, 0.8, 0, "a")  # misma colonia cortada por el tile
    other = Detection(300, 300, 320, 320, 0.7, 0, "a")
    kept = merge_detections([partial, full, other])
    assert full in kept and other in kept and partial not in kept


def test_merge_keeps_full_extent_when_partial_box_is_more_confident():
    full = Detection(100, 100, 120, 120, 0.6, 0, "a")
    partial = Detection(100, 100, 110, 120, 0.9, 0, "a")
    (kept,) = merge_detections([partial, full])
    assert (kept.x1, kept.y1, kept.x2, kept.y2) == (100, 100, 120, 120)
    assert kept.confidence == 0.9


def test_pipeline_on_synthetic_plate_with_ground_truth_boxes():
    img, labels = draw_plate(800, 25, seed=3)
    dets = [Detection(l["x"], l["y"], l["x"] + l["width"], l["y"] + l["height"], 1.0,
                      0 if l["class"] == "E.coli" else 1, l["class"]) for l in labels]
    result, annotated = analyze(img, dets, mm_per_px=0.1, dilution=1e-3, volume_ml=0.1)
    s = result["summary"]
    assert s["total"] == len(labels)
    assert sum(s["by_class"].values()) == len(labels)
    assert s["cfu_per_ml"] == pytest.approx(len(labels) / 1e-4)
    seg_rate = np.mean([c["morphology"]["segmented"] for c in result["colonies"]])
    assert seg_rate > 0.9
    assert annotated.shape == img.shape and not np.array_equal(annotated, img)


def test_dataset_conversion_roundtrip(tmp_path):
    write_agar_dataset(tmp_path / "raw", n_images=5, size=512)
    samples = load_agar(tmp_path / "raw")
    assert len(samples) == 5
    summary = build_yolo_dataset(samples, tmp_path / "yolo", split=(0.6, 0.2, 0.2))
    assert sum(p["images"] for p in summary["splits"].values()) == 5
    assert sum(p["boxes"] for p in summary["splits"].values()) == sum(len(s.boxes) for s in samples)
    assert (tmp_path / "yolo" / "data.yaml").exists()
    line = next((tmp_path / "yolo" / "labels" / "train").glob("*.txt")).read_text().split("\n")[0]
    cls, *vals = line.split()
    assert 0 <= int(cls) < len(summary["classes"]) and all(0 <= float(v) <= 1 for v in vals)
