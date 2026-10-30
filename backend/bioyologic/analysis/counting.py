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


# ------------------------------------------------------------------ varias placas de una muestra
REPLICAS_Z = 2.58  # réplicas: diferencia máxima en desviaciones de Poisson (99 %)


def _exp(d: float) -> int:
    return round(float(np.log10(d)))


def _dil(d: float) -> str:
    """1e-4 -> '10⁻⁴' para los mensajes."""
    sup = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
    return f"10{str(_exp(d)).translate(sup)}" if abs(np.log10(d) - _exp(d)) < 1e-6 else f"{d:g}"


def combine_plates(plates: list[dict]) -> dict:
    """UFC/mL de una muestra a partir de varias placas (diluciones seriadas y réplicas), según ISO 4833-1.

    `plates`: [{"id", "total", "dilution", "volume_ml"}]. Se usan las placas contables (30-300 colonias) de
    las dos diluciones sucesivas más concentradas:

        N = ΣC / Σ(V × d)     (para el mismo V: ΣC / (V × (n1 + 0,1·n2) × d1), la fórmula de la norma)

    Si ninguna placa es contable, se estima con la dilución más cercana al rango y se marca como estimado.
    Devuelve cfu_per_ml, estimated, used (ids), rule (cómo se calculó) y warnings.
    """
    validas = [p for p in plates if p.get("dilution") and p.get("volume_ml")]
    ignoradas = len(plates) - len(validas)
    out = {"cfu_per_ml": None, "estimated": False, "used": [], "rule": "", "warnings": [], "plates": len(plates)}
    if ignoradas:
        out["warnings"].append(f"{ignoradas} placa(s) sin dilución o volumen: no entran en el cálculo.")
    if not validas:
        out["rule"] = "Faltan la dilución y el volumen sembrado de las placas."
        return out

    por_dil: dict[float, list[dict]] = {}
    for p in validas:
        por_dil.setdefault(p["dilution"], []).append(p)
    diluciones = sorted(por_dil, reverse=True)  # de la más concentrada (10⁻¹) a la más diluida
    contables = [d for d in diluciones if any(COUNTABLE_MIN <= p["total"] <= COUNTABLE_MAX for p in por_dil[d])]

    if contables:
        usar = contables[:1]
        # La siguiente dilución entra solo si es la sucesiva (10 veces más diluida) y también es contable.
        if len(contables) > 1 and abs(_exp(contables[0]) - _exp(contables[1])) == 1:
            usar.append(contables[1])
        usadas = [p for d in usar for p in por_dil[d] if COUNTABLE_MIN <= p["total"] <= COUNTABLE_MAX]
        out["rule"] = ("Promedio ponderado ISO 4833-1 de las placas contables (30-300) de "
                       + " y ".join(_dil(d) for d in usar) + ".")
    else:
        # Ninguna contable: la dilución cuyo promedio está más cerca del rango (en escala logarítmica).
        def distancia(d):
            m = max(float(np.mean([p["total"] for p in por_dil[d]])), 0.5)
            return 0.0 if COUNTABLE_MIN <= m <= COUNTABLE_MAX else min(abs(np.log10(m / COUNTABLE_MIN)),
                                                                        abs(np.log10(m / COUNTABLE_MAX)))
        d = min(diluciones, key=distancia)
        usadas = por_dil[d]
        out["estimated"] = True
        todas = [p["total"] for p in validas]
        motivo = ("todas las placas tienen menos de 30 colonias" if max(todas) < COUNTABLE_MIN
                  else "todas las placas tienen más de 300 colonias" if min(todas) > COUNTABLE_MAX
                  else "ninguna placa está en el rango contable (30-300)")
        out["rule"] = f"Estimado: {motivo}; se usa {_dil(d)}."

    suma_c = sum(p["total"] for p in usadas)
    suma_vd = sum(p["volume_ml"] * p["dilution"] for p in usadas)
    out["used"] = [p["id"] for p in usadas]
    out["cfu_per_ml"] = suma_c / suma_vd if suma_c else None
    if not suma_c:
        out["rule"] += f" Sin colonias: menos de {1 / suma_vd:.0f} UFC/mL."

    # Réplicas de la misma dilución que difieren más de lo esperable por azar. Los conteos de colonias siguen
    # una distribución de Poisson: dos réplicas a y b concuerdan si |a - b| <= 2,58·√(a + b) (99 %).
    for d in diluciones:
        cuentas = [p["total"] for p in por_dil[d]]
        a, b = max(cuentas), min(cuentas)
        if len(cuentas) >= 2 and a + b > 0 and (a - b) / float(np.sqrt(a + b)) > REPLICAS_Z:
            out["warnings"].append(f"Las réplicas de {_dil(d)} difieren más de lo esperable por azar "
                                   f"({', '.join(map(str, cuentas))} colonias): revisa la siembra o repite.")
    # Diluciones sucesivas incoherentes (se espera que la más diluida tenga ~10 veces menos)
    for d1, d2 in zip(diluciones, diluciones[1:]):
        if abs(_exp(d1) - _exp(d2)) != 1:
            continue
        m1 = float(np.mean([p["total"] for p in por_dil[d1]]))
        m2 = float(np.mean([p["total"] for p in por_dil[d2]]))
        if m1 <= COUNTABLE_MAX and m2 >= 10 and not 4 <= m1 / m2 <= 25:
            veces = f"{m1 / m2:.1f}".replace(".", ",")
            out["warnings"].append(f"De {_dil(d1)} a {_dil(d2)} las colonias bajan {veces} veces (se esperan ~10): "
                                   "posible error en la dilución.")
    return out
