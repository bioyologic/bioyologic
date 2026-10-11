"""El backend ONNX debe dar los mismos resultados que Ultralytics (.pt)."""

from pathlib import Path

import numpy as np
import pytest

from bioyologic.detection.onnx_backend import letterbox, onnx_available
from bioyologic.synthetic import draw_plate

MODELS = Path(__file__).resolve().parents[2] / "models"


def test_letterbox_keeps_aspect():
    img = np.zeros((300, 600, 3), np.uint8)
    out, r, left, top = letterbox(img, 640)
    assert out.shape == (640, 640, 3)
    assert r == pytest.approx(640 / 600) and left == 0 and top == 160


@pytest.mark.skipif(not (onnx_available() and (MODELS / "bioyologic.onnx").exists()
                         and (MODELS / "bioyologic.pt").exists()), reason="sin modelos exportados")
def test_onnx_matches_pytorch():
    pytest.importorskip("ultralytics")
    from bioyologic.detection.detector import ColonyDetector
    img, _ = draw_plate(1200, 40, seed=3)
    a = ColonyDetector(MODELS / "bioyologic.pt").detect(img)
    b = ColonyDetector(MODELS / "bioyologic.onnx").detect(img)
    assert abs(len(a) - len(b)) <= max(1, len(a) // 50)
    if a and b:
        ca = np.array([[(d.x1 + d.x2) / 2, (d.y1 + d.y2) / 2] for d in a])
        cb = np.array([[(d.x1 + d.x2) / 2, (d.y1 + d.y2) / 2] for d in b])
        nearest = np.linalg.norm(ca[:, None] - cb[None], axis=2).min(1)
        assert np.median(nearest) < 2.0
