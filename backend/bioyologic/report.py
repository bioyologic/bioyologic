"""Informe PDF de un análisis."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

GREEN = colors.HexColor("#1F5C45")
LIGHT = colors.HexColor("#EAF3EE")

STATUS = {"contable": "Contable (30-300)", "pocas": "Pocas colonias (<30)",
          "incontable": "Incontable (>300)"}


def _sci(v: float | None) -> str:
    if v is None:
        return "-"
    mant, exp = f"{v:.2e}".split("e")
    return f"{mant.replace('.', ',')} × 10<super>{int(exp)}</super>"


def _num(v, d: int = 2) -> str:
    return "-" if v is None else f"{v:.{d}f}".replace(".", ",")


def _table(rows, col_widths, header=True) -> Table:
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, LIGHT]),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#C9D6CF")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), GREEN),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


def build_report(analysis: dict, annotated_image: Path) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Bioyologic - {analysis['sample_name']}")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=GREEN, alignment=0, fontSize=20)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=GREEN, fontSize=12, spaceBefore=8)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, textColor=colors.grey)
    cell = ParagraphStyle("cell", parent=ss["Normal"], fontSize=8.5)

    s = analysis["summary"]
    pred = s.get("predominant", {})
    created = datetime.fromisoformat(analysis["created_at"]).strftime("%d/%m/%Y %H:%M")
    story = [
        Paragraph("Bioyologic · Informe de análisis", h1),
        Paragraph(f"<b>{analysis['sample_name']}</b> · {analysis.get('project_name') or 'Sin proyecto'}"
                  f" · {created}", ss["Normal"]),
        Spacer(1, 6 * mm),
    ]

    img_w = 120 * mm
    w, h = analysis.get("image_size") or (1, 1)
    story.append(Image(str(annotated_image), width=img_w, height=img_w * h / w))
    story.append(Spacer(1, 4 * mm))

    diam = s["stats"].get("diameter_mm") or s["stats"].get("diameter_px") or {}
    unit = "mm" if "diameter_mm" in s["stats"] else "px"
    dil = analysis.get("dilution")
    rows = [
        ["Total de colonias", str(s["total"])],
        ["Estado de la placa", STATUS.get(s["status"], s["status"])],
        ["UFC/mL", Paragraph(_sci(s["cfu_per_ml"]), cell)],
        ["Dilución / volumen", "-" if dil is None else f"{dil:g} / {_num(analysis.get('volume_ml'))} mL"],
        [f"Tamaño promedio ({unit})", f"{_num(diam.get('mean'))} ± {_num(diam.get('std'))}" if diam else "-"],
        ["Forma predominante", (pred.get("form") or "-").capitalize()],
        ["Borde predominante", (pred.get("margin") or "-").capitalize()],
        ["Color predominante", (pred.get("color") or "-").capitalize()],
    ]
    story += [Paragraph("Resumen", h2), _table(rows, [60 * mm, 110 * mm], header=False)]

    sp = analysis.get("species")
    if sp and sp.get("top"):
        title = "Especie probable" if sp.get("identified") else "Especie no identificada con seguridad (candidatas)"
        story += [Paragraph(title, h2),
                  _table([["Especie", "Probabilidad", "Gram", "Medio (entrenamiento)"]] +
                         [[Paragraph(f"<i>{c['name']}</i>", cell), _num(100 * c["prob"], 1) + " %",
                           c.get("gram", "-"), c.get("agar", "-")] for c in sp["top"]],
                         [70 * mm, 30 * mm, 20 * mm, 50 * mm]),
                  Paragraph("Clasificación orientativa por votación de las colonias; confirmar con pruebas "
                            "microbiológicas.", small)]

    if s["by_class"]:
        story += [Paragraph("Colonias por clase", h2),
                  _table([["Clase", "Colonias", "%"]] +
                         [[k, str(v), _num(100 * v / max(1, s["total"]), 1)]
                          for k, v in sorted(s["by_class"].items(), key=lambda kv: -kv[1])],
                         [80 * mm, 40 * mm, 40 * mm])]

    colonies = analysis.get("colonies", [])
    if colonies:
        rows = [["#", "Clase", f"Diám. ({unit})", "Circ.", "Solidez", "Forma", "Borde", "Color"]]
        for c in colonies:
            m = c["morphology"]
            d = m.get("diameter_mm") if unit == "mm" else m.get("diameter_px")
            rows.append([str(c["id"]), c["class_name"], _num(d), _num(m["circularity"]),
                         _num(m["solidity"]), m["form"], m["margin"], m["color_name"]])
        story += [Paragraph(f"Detalle de colonias ({len(colonies)})", h2),
                  _table(rows, [10 * mm, 30 * mm, 22 * mm, 16 * mm, 18 * mm, 24 * mm, 22 * mm, 22 * mm])]

    if analysis.get("notes"):
        story += [Paragraph("Notas", h2), Paragraph(analysis["notes"], ss["Normal"])]

    story += [Spacer(1, 6 * mm), Paragraph(
        "Método: detección de colonias con YOLO e inferencia por teselas; segmentación de cada colonia "
        "por contraste de color (L*a*b*, Otsu) y descriptores morfológicos calculados sobre su contorno. "
        "UFC/mL = colonias / (dilución × volumen sembrado). Rango contable: 30-300 colonias.", small)]
    doc.build(story)
    return buf.getvalue()
