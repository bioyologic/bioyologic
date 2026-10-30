"""Exportación de análisis a CSV para Excel.

Formato pensado para Excel en español (Colombia): separador ";", coma decimal y codificación UTF-8 con BOM,
para que Excel abra el archivo con doble clic y muestre bien las tildes.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

COLUMNAS = [
    "Proyecto", "Muestra", "Placa", "Fecha", "Dilución", "Volumen (mL)", "Colonias", "Detectadas por el modelo",
    "Corrección manual", "Estado", "UFC/mL de la placa", "UFC/mL de la muestra (ISO 4833)", "UFC/mL de la muestra estimado",
    "Especie probable", "Probabilidad de la especie (%)", "Diámetro medio", "Unidad del diámetro", "Forma predominante",
    "Borde predominante", "Color predominante", "Avisos de calidad de la foto", "Notas",
]
ESTADO = {"contable": "Contable (30-300)", "pocas": "Pocas colonias (<30)", "incontable": "Incontable (>300)"}


def _n(v, d: int | None = None) -> str:
    """Número con coma decimal; vacío si no hay dato."""
    if v is None:
        return ""
    if d is None:
        return f"{v:.6g}".replace(".", ",")
    return f"{v:.{d}f}".replace(".", ",")


def _ufc(v) -> str:
    """UFC/mL como número entero (Excel lo puede sumar y graficar)."""
    return "" if v is None else f"{round(v):d}"


def build_csv(analyses: list[dict], samples: dict[tuple, dict]) -> bytes:
    """`analyses`: listado (sin colonias). `samples`: {(project_id, sample_group): resultado de combine_plates}."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(COLUMNAS)
    for a in sorted(analyses, key=lambda x: (x.get("project_name") or "", x.get("sample_group") or "", x["created_at"])):
        s = a["summary"]
        corr = a.get("correction")
        sp = a.get("species") or {}
        top = (sp.get("top") or [None])[0]
        stats = s.get("stats", {})
        unidad = "mm" if "diameter_mm" in stats else "px"
        diam = stats.get("diameter_mm") or stats.get("diameter_px") or {}
        pred = s.get("predominant") or {}
        grupo = a.get("sample_group") or ""
        muestra = samples.get((a.get("project_id"), grupo)) if grupo else None
        calidad = " | ".join(i["message"] for i in (a.get("quality") or {}).get("issues", []))
        w.writerow([
            a.get("project_name") or "", grupo, a["sample_name"],
            datetime.fromisoformat(a["created_at"]).strftime("%d/%m/%Y %H:%M"),
            _n(a.get("dilution")), _n(a.get("volume_ml")), s["total"],
            corr["detected_total"] if corr else s["total"],
            f"-{len(corr['removed'])} / +{len(corr['added'])}" if corr else "",
            ESTADO.get(s["status"], s["status"]), _ufc(s.get("cfu_per_ml")),
            _ufc(muestra["cfu_per_ml"]) if muestra else "", ("Sí" if muestra["estimated"] else "No") if muestra else "",
            (top["name"] if top and sp.get("identified") else "") if top else "",
            _n(100 * top["prob"], 1) if top and sp.get("identified") else "",
            _n(diam.get("mean"), 2 if unidad == "mm" else 0), unidad if diam else "",
            pred.get("form") or "", pred.get("margin") or "", pred.get("color") or "", calidad,
            (a.get("notes") or "").replace("\r", " ").replace("\n", " "),
        ])
    return ("﻿" + buf.getvalue()).encode("utf-8")
