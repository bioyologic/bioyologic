"""Conteo de colonias, UFC/mL y estadísticas de la placa."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

import numpy as np

# Rango contable habitual de una placa de 90 mm (ISO 4833 / métodos estándar).
COUNTABLE_MIN = 30
COUNTABLE_MAX = 300


@dataclass
class CountSummary:
    total: int
    by_class: dict[str, int]
    status: str                  # contable | pocas (<30) | incontable (>300)
    cfu_per_ml: float | None     # UFC/mL; None si no se dio dilución/volumen
    dilution: float | None
    volume_ml: float | None
    stats: dict[str, dict[str, float]]
    predominant: dict[str, str | None]

    def to_dict(self) -> dict:
        return asdict(self)


def plate_status(n: int, lo: int = COUNTABLE_MIN, hi: int = COUNTABLE_MAX) -> str:
    if n < lo:
        return "pocas"        # TFTC: too few to count
    if n > hi:
        return "incontable"   # TNTC: too numerous to count
    return "contable"


def cfu_per_ml(n: int, dilution: float, volume_ml: float) -> float:
    """UFC/mL = colonias / (factor de dilución × volumen sembrado).

    `dilution` es la fracción sembrada; p. ej. la dilución 10⁻⁴ es 1e-4.
    """
    if dilution <= 0 or volume_ml <= 0:
        raise ValueError("dilución y volumen deben ser > 0")
    return n / (dilution * volume_ml)


def _describe(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    a = np.asarray(values, dtype=float)
    return {"mean": float(a.mean()), "std": float(a.std(ddof=1)) if len(a) > 1 else 0.0,
            "median": float(np.median(a)), "min": float(a.min()), "max": float(a.max())}


def summarize(colonies: list[dict], dilution: float | None = None,
              volume_ml: float | None = None) -> CountSummary:
    """`colonies`: lista de dicts con 'class_name' y 'morphology' (ver pipeline)."""
    n = len(colonies)
    by_class = dict(Counter(c["class_name"] for c in colonies))
    cfu = cfu_per_ml(n, dilution, volume_ml) if dilution and volume_ml else None

    stats: dict[str, dict[str, float]] = {}
    for key in ("diameter_mm", "diameter_px", "area_mm2", "circularity", "solidity", "contrast"):
        vals = [c["morphology"][key] for c in colonies if c["morphology"].get(key) is not None]
        if vals:
            stats[key] = _describe(vals)
    for key in ("form", "margin", "color_name"):
        stats[key] = dict(Counter(c["morphology"][key] for c in colonies))

    def most_common(counter: dict) -> str | None:
        return max(counter, key=counter.get) if counter else None

    predominant = {
        "class": most_common(by_class),
        "form": most_common(stats["form"]),
        "margin": most_common(stats["margin"]),
        "color": most_common(stats["color_name"]),
    }
    return CountSummary(n, by_class, plate_status(n), cfu, dilution, volume_ml, stats, predominant)
