"""Informe PDF de un análisis."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import CondPageBreak, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GREEN = colors.HexColor("#1F5C45")
LIGHT = colors.HexColor("#EAF3EE")
GRID = colors.HexColor("#C9D6CF")
MARGIN = 18 * mm
WIDTH = A4[0] - 2 * MARGIN  # ancho útil: todas las tablas lo ocupan entero y alineadas a la izquierda
MAX_IMG_H = 120 * mm

STATUS = {"contable": "Contable (30-300)", "pocas": "Pocas colonias (<30)",
          "incontable": "Incontable (>300)"}
GRAM = {"+": "Positivo", "-": "Negativo"}
MEDIO = {"blood": "Agar sangre", "chocolate": "Agar chocolate", "MacConkey": "Agar MacConkey",
         "Salmonella-Shigella": "Agar Salmonella-Shigella"}


def _txt(v) -> str:
    """Texto del usuario dentro de un Paragraph: se escapa (< > & no son etiquetas) y se respetan los saltos."""
    return escape(str(v)).replace("\n", "<br/>")


def _sci(v: float | None) -> str:
    if v is None:
        return "-"
    mant, exp = f"{v:.2e}".split("e")
    return f"{mant.replace('.', ',')} × 10<super>{int(exp)}</super>"


def _num(v, d: int = 2) -> str:
    return "-" if v is None else f"{v:.{d}f}".replace(".", ",")


def _dilucion(v: float) -> str:
    """1e-4 -> 1 × 10⁻⁴ (potencias de 10); otros valores con coma decimal."""
    mant, exp = f"{v:.6e}".split("e")
    m = float(mant)
    if abs(m - round(m)) < 1e-9:
        return f"{int(round(m))} × 10<super>{int(exp)}</super>"
    return f"{v:g}".replace(".", ",")


def _verbo(n: int, uno: str, varios: str) -> str:
    """"se quitó 1" / "se quitaron 2"."""
    return f"se {uno if n == 1 else varios} {n}"


def _leyenda(quitadas: int, agregadas: int) -> str:
    partes = (["tachadas en rojo las quitadas"] if quitadas else []) + (["en naranja las agregadas"] if agregadas else [])
    return f"En la imagen: {', '.join(partes)}." if partes else ""


def _fecha(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")


def _clase(name: str) -> str:
    """Nombre de la clase: las especies en cursiva; la clase genérica del detector, en español."""
    if name in ("colony", "colonia", ""):
        return "Colonia"
    return f"<i>{_txt(name)}</i>" if " " in name else _txt(name)


def _table(rows, fractions, header=True) -> Table:
    """Tabla al ancho útil; `fractions` reparte el ancho entre columnas (suman 1)."""
    t = Table(rows, colWidths=[WIDTH * f for f in fractions], repeatRows=1 if header else 0, hAlign="LEFT")
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, LIGHT]),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), GREEN),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


def _pie(sample: str):
    """Canvas que escribe en cada página "Bioyologic · muestra · Página n de N"."""
    corto = sample if len(sample) <= 70 else sample[:67] + "…"

    class Pie(rl_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._paginas = []

        def showPage(self):
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas)
            for estado in self._paginas:
                self.__dict__.update(estado)
                self.setFont("Helvetica", 7.5)
                self.setFillColor(colors.grey)
                self.drawString(MARGIN, 9 * mm, f"Bioyologic · {corto}")
                self.drawRightString(A4[0] - MARGIN, 9 * mm, f"Página {self._pageNumber} de {total}")
                super().showPage()
            super().save()

    return Pie


def build_report(analysis: dict, annotated_image: Path) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title=analysis["sample_name"], author="Bioyologic")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=GREEN, alignment=0, fontSize=20)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=GREEN, fontSize=12, spaceBefore=8)

    def titulo(texto: str) -> list:
        # Si quedan menos de 4 cm, la sección empieza en la página siguiente: el título nunca queda solo al
        # final, y una tabla larga empieza en la misma página y continúa en la siguiente (sin páginas a medias).
        return [CondPageBreak(40 * mm), Paragraph(texto, h2)]
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, textColor=colors.grey, leading=10)
    cell = ParagraphStyle("cell", parent=ss["Normal"], fontSize=8.5, leading=10.5)
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=9.5, leading=13)

    s = analysis["summary"]
    pred = s.get("predominant", {})
    story = [
        Paragraph("Bioyologic · Informe de análisis", h1),
        Paragraph(f"<b>{_txt(analysis['sample_name'])}</b> · {_txt(analysis.get('project_name') or 'Sin proyecto')}"
                  f" · {_fecha(analysis['created_at'])}", body),
        Spacer(1, 6 * mm),
    ]

    w, h = analysis.get("image_size") or (1, 1)
    img_w = 120 * mm
    img_h = img_w * h / w
    if img_h > MAX_IMG_H:  # foto vertical: se limita el alto para que el resumen quepa en la primera página
        img_w, img_h = img_w * MAX_IMG_H / img_h, MAX_IMG_H
    story += [Image(str(annotated_image), width=img_w, height=img_h), Spacer(1, 4 * mm)]

    unit = "mm" if "diameter_mm" in s["stats"] else "px"
    diam = s["stats"].get("diameter_mm") or s["stats"].get("diameter_px") or {}
    dec = 2 if unit == "mm" else 0
    dil = analysis.get("dilution")
    vol = analysis.get("volume_ml")
    ufc = _sci(s["cfu_per_ml"])
    if s["cfu_per_ml"] is not None and s["status"] != "contable":
        ufc += " (estimado: placa fuera del rango contable 30-300)"
    rows = [
        ["Total de colonias", str(s["total"])],
        ["Estado de la placa", STATUS.get(s["status"], s["status"])],
        ["UFC/mL", Paragraph(ufc, cell)],
        ["Dilución / volumen", Paragraph("-" if dil is None else f"{_dilucion(dil)} / {_num(vol)} mL", cell)],
        [f"Tamaño promedio ({unit})", f"{_num(diam.get('mean'), dec)} ± {_num(diam.get('std'), dec)}" if diam else "-"],
        ["Forma predominante", (pred.get("form") or "-").capitalize()],
        ["Borde predominante", (pred.get("margin") or "-").capitalize()],
        ["Color predominante", (pred.get("color") or "-").capitalize()],
    ]
    corr = analysis.get("correction")
    if corr:
        cambios = [t for n, t in ((len(corr["removed"]), _verbo(len(corr["removed"]), "quitó", "quitaron")),
                                  (len(corr["added"]), _verbo(len(corr["added"]), "agregó", "agregaron"))) if n]
        quien = corr.get("by") or ""
        # Correcciones antiguas guardaban el correo: no se imprime (dato personal en un PDF que se comparte).
        quien = f"por {_txt(quien)}, " if quien and "@" not in quien else ""
        rows.insert(1, ["Corrección manual", Paragraph(
            f"El modelo detectó {corr['detected_total']}; {' y '.join(cambios) or 'sin cambios'} a mano "
            f"({quien}{_fecha(corr['at'])}). " + _leyenda(len(corr["removed"]), len(corr["added"])), cell)])
    if analysis.get("sample_group"):
        rows.insert(0, ["Muestra", Paragraph(f"{_txt(analysis['sample_group'])} (una de sus placas)", cell)])
    story += [*titulo("Resumen"), _table(rows, [0.36, 0.64], header=False)]

    calidad = (analysis.get("quality") or {}).get("issues") or []
    if calidad:
        story += [*titulo("Calidad de la foto"),
                  _table([[Paragraph("• " + _txt(i["message"]), cell)] for i in calidad], [1.0], header=False),
                  Paragraph("El conteo se hizo igual; estas advertencias indican qué mejorar en la próxima foto.", small)]

    sp = analysis.get("species")
    if sp and sp.get("top"):
        title = "Especie probable" if sp.get("identified") else "Especie no identificada con seguridad (candidatas)"
        story += [*titulo(title),
                  _table([["Especie", "Probabilidad", "Gram", "Medio (entrenamiento)"]] +
                         [[Paragraph(f"<i>{_txt(c['name'])}</i>", cell), _num(100 * c["prob"], 1) + " %",
                           GRAM.get(c.get("gram"), "-"), Paragraph(_txt(MEDIO.get(c.get("agar"), c.get("agar") or "-")), cell)]
                          for c in sp["top"]],
                         [0.42, 0.16, 0.14, 0.28]),
                  Paragraph("Clasificación orientativa por votación de las colonias; confirmar con pruebas "
                            "microbiológicas.", small)]

    if s["by_class"]:
        story += [*titulo("Colonias por clase"),
                  _table([["Clase", "Colonias", "%"]] +
                         [[Paragraph(_clase(k), cell), str(v), _num(100 * v / max(1, s["total"]), 1)]
                          for k, v in sorted(s["by_class"].items(), key=lambda kv: -kv[1])],
                         [0.6, 0.2, 0.2])]

    colonies = analysis.get("colonies", [])
    if colonies:
        rows = [["#", "Clase", f"Diám. ({unit})", "Circ.", "Solidez", "Forma", "Borde", "Color"]]
        for c in colonies:
            m = c["morphology"]
            d = m.get("diameter_mm") if unit == "mm" else m.get("diameter_px")
            nombre = _clase(c["class_name"]) + (" <font color='#E08A1E'>(manual)</font>" if c.get("manual") else "")
            rows.append([f"+{c['id']}" if c.get("manual") else str(c["id"]), Paragraph(nombre, cell),
                         _num(d, dec), _num(m["circularity"]), _num(m["solidity"]), m["form"], m["margin"],
                         m["color_name"]])
        story += [*titulo(f"Detalle de colonias ({len(colonies)})"),
                  _table(rows, [0.06, 0.31, 0.11, 0.08, 0.09, 0.12, 0.12, 0.11])]

    if analysis.get("notes"):
        story += [*titulo("Notas"), Paragraph(_txt(analysis["notes"]), body)]

    story += [Spacer(1, 6 * mm), Paragraph(
        "Método: detección de colonias con YOLO e inferencia por teselas; segmentación de cada colonia "
        "por contraste de color (L*a*b*, Otsu) y descriptores morfológicos calculados sobre su contorno. "
        "UFC/mL = colonias / (dilución × volumen sembrado). Rango contable: 30-300 colonias. "
        "Herramienta de apoyo: los resultados deben ser revisados por personal cualificado.", small)]
    doc.build(story, canvasmaker=_pie(analysis["sample_name"]))
    return buf.getvalue()
