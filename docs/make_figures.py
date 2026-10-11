"""Genera las figuras del documento explicativo a partir de fotos REALES de los datasets.

    python docs/make_figures.py

Usa las muestras de data/raw/samples/ (2 fotos de Makrai et al. y 2 del dataset clínico
de Zenodo, con sus anotaciones COCO) y el propio código de Bioyologic.
"""

import json
import math
import sys
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from bioyologic.analysis.morphology import describe_colony, segment_colony  # noqa: E402
from bioyologic.analysis.pipeline import analyze  # noqa: E402
from bioyologic.detection.detector import Detection, merge_detections  # noqa: E402

S = ROOT / "data" / "raw" / "samples"
OUT = ROOT / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

GREEN, RED, BLUE, GREY = "#2E8B57", "#D64545", "#2F6FD6", "#888888"
plt.rcParams.update({"font.size": 11, "axes.titlesize": 12, "axes.titleweight": "bold",
                     "figure.dpi": 110, "savefig.bbox": "tight", "savefig.facecolor": "white"})


def load(name):
    """Imagen RGB + cajas COCO [(x1, y1, x2, y2)] + especie."""
    coco_file = "makrai_coco.json" if name.startswith("sp") else "clinical_coco.json"
    coco = json.loads((S / coco_file).read_text())
    im = next(i for i in coco["images"] if i["file_name"] == name)
    cats = {c["id"]: c["name"] for c in coco["categories"]}
    anns = [a for a in coco["annotations"] if a["image_id"] == im["id"]]
    boxes = [(a["bbox"][0], a["bbox"][1], a["bbox"][0] + a["bbox"][2], a["bbox"][1] + a["bbox"][3]) for a in anns]
    species = cats[anns[0]["category_id"]] if anns else "?"
    img = cv2.cvtColor(cv2.imread(str(S / name)), cv2.COLOR_BGR2RGB)
    return img, boxes, species


def save(fig, name):
    fig.savefig(OUT / name)
    plt.close(fig)
    print("figura:", name)


def tile_starts(length, tile, overlap):
    if length <= tile:
        return [0]
    step = int(tile * (1 - overlap))
    starts = list(range(0, length - tile, step))
    starts.append(length - tile)
    return starts


# ---------------------------------------------------------------- 1. datasets
def fig_datasets():
    items = [("sp05_img01.jpg", "Makrai et al. 2023"), ("sp21_img04.jpg", "Makrai et al. 2023"),
             ("eco_01.jpg", "Zenodo clínico"), ("sau_05.jpg", "Zenodo clínico")]
    names = {"eco": "E. coli", "sau": "S. aureus", "sp05": "especie sp05", "sp21": "especie sp21"}
    fig, axes = plt.subplots(1, 4, figsize=(17, 5.2), gridspec_kw={"wspace": 0.08})
    for ax, (name, src) in zip(axes, items):
        img, boxes, sp = load(name)
        ax.imshow(img)
        for x1, y1, x2, y2 in boxes:
            ax.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, ec="#00E676", lw=1.4))
        ax.set_title(f"{src}\n{names.get(sp, sp)} · {len(boxes)} colonias anotadas", fontsize=11)
        ax.axis("off")
    fig.suptitle("Fotos reales de los datasets con las cajas que anotaron los microbiólogos (verde)", y=1.02,
                 fontsize=13, fontweight="bold")
    save(fig, "01_datasets.png")


# ---------------------------------------------------------------- 2. teselas
def fig_teselas():
    img, boxes, _ = load("eco_01.jpg")
    MAX, TILE, OV = 2048, 640, 0.2
    s = MAX / max(img.shape[:2])
    small = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    bx = [(x1 * s, y1 * s, x2 * s, y2 * s) for x1, y1, x2, y2 in boxes]
    H, W = small.shape[:2]
    xs, ys = tile_starts(W, TILE, OV), tile_starts(H, TILE, OV)

    # Una tesela que corta alguna colonia, para el detalle.
    best = None
    for y0 in ys:
        for x0 in xs:
            cut = []
            for b in bx:
                cx1, cy1, cx2, cy2 = max(b[0] - x0, 0), max(b[1] - y0, 0), min(b[2] - x0, TILE), min(b[3] - y0, TILE)
                vis = max(0, cx2 - cx1) * max(0, cy2 - cy1) / ((b[2] - b[0]) * (b[3] - b[1]))
                if 0 < vis:
                    cut.append((b, vis))
            score = sum(1 for _, v in cut if v < 1) * 10 + len(cut)
            if best is None or score > best[0]:
                best = (score, x0, y0, cut)
    _, tx, ty, cut = best

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(16, 6.6), gridspec_kw={"width_ratios": [1.35, 1]})
    a1.imshow(small)
    colors = ["#FFB300", "#29B6F6", "#EC407A", "#9CCC65"]
    for i in range(len(xs) - 1):
        a1.axvspan(xs[i + 1], xs[i] + TILE, color="white", alpha=0.22, lw=0)
    for j in range(len(ys) - 1):
        a1.axhspan(ys[j + 1], ys[j] + TILE, color="white", alpha=0.22, lw=0)
    k = 0
    for j, y0 in enumerate(ys):
        for i, x0 in enumerate(xs):
            c = colors[(i + j) % 4]
            a1.add_patch(Rectangle((x0 + 3, y0 + 3), TILE - 6, TILE - 6, fill=False, ec=c, lw=2.2))
            a1.text(x0 + 14, y0 + 44, str(k + 1), color="white", fontsize=12, fontweight="bold",
                    bbox=dict(fc=c, ec="none", alpha=0.9, pad=2))
            k += 1
    a1.add_patch(Rectangle((tx, ty), TILE, TILE, fill=False, ec="white", lw=3.5, ls="--"))
    a1.set_title(f"Foto reducida a {W} × {H} px y cortada en {len(xs) * len(ys)} teselas de 640 px\n"
                 "(franjas claras = 20 % de solape entre teselas vecinas)")
    a1.axis("off")

    tile = small[ty:ty + TILE, tx:tx + TILE]
    a2.imshow(tile)
    for b, vis in cut:
        x1, y1, x2, y2 = b[0] - tx, b[1] - ty, b[2] - tx, b[3] - ty
        keep = vis >= 0.5
        col = "#00E676" if keep else "#FFD600"
        a2.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, ec=col, lw=2.4, ls="-" if keep else "--"))
        if vis < 0.999:
            tx_, ty_ = min(max((x1 + x2) / 2, 60), TILE - 60), min(max(y1 - 14, 24), TILE - 40)
            a2.text(tx_, ty_, f"{vis * 100:.0f} %", color=col, fontsize=11, fontweight="bold", ha="center",
                    bbox=dict(fc="black", ec="none", alpha=0.75, pad=2), clip_on=True)
    a2.set_xlim(0, TILE)
    a2.set_ylim(TILE, 0)
    a2.set_title("Detalle de la tesela marcada en blanco (etiquetas para YOLO)\n"
                 "verde = se etiqueta · amarillo discontinuo = cortada, visible < 50 %, se descarta")
    a2.axis("off")
    save(fig, "02_teselas.png")
    return len(xs) * len(ys)


# ---------------------------------------------------------------- 3. partición
def fig_particion():
    fig, ax = plt.subplots(figsize=(15, 3.4))
    n = 1319
    parts = [("Entrenamiento", 0.8, "#2F6FD6"), ("Validación", 0.1, "#8FB3EC"), ("Test", 0.1, "#C9D8F3")]
    x = 0
    for name, f, c in parts:
        ax.barh(0, f, left=x, color=c, ec="white", height=0.55)
        ax.text(x + f / 2, 0, f"{name}\n{int(n * f)} placas ({f * 100:.0f} %)", ha="center", va="center",
                fontsize=12, color="white" if f > 0.5 else "#123", fontweight="bold")
        x += f
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.6, 0.6)
    ax.axis("off")
    ax.set_title("Las 1.319 placas se reparten ANTES de cortar teselas: los trozos de una placa nunca se mezclan entre grupos",
                 fontsize=12.5)
    save(fig, "03_particion.png")


# ---------------------------------------------------------------- 4. fusión
def fig_fusion():
    img, boxes, _ = load("eco_01.jpg")
    MAX, TILE, OV = 2048, 640, 0.2
    s = MAX / max(img.shape[:2])
    small = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    bx = [(x1 * s, y1 * s, x2 * s, y2 * s) for x1, y1, x2, y2 in boxes]
    H, W = small.shape[:2]
    # Simula lo que ve el detector en cada tesela: cada colonia, recortada al borde de la tesela.
    dets = []
    for y0 in tile_starts(H, TILE, OV):
        for x0 in tile_starts(W, TILE, OV):
            for b in bx:
                c = (max(b[0], x0), max(b[1], y0), min(b[2], x0 + TILE), min(b[3], y0 + TILE))
                full = (b[2] - b[0]) * (b[3] - b[1])
                if c[2] > c[0] and c[3] > c[1] and (c[2] - c[0]) * (c[3] - c[1]) / full > 0.2:
                    conf = 0.55 + 0.4 * (c[2] - c[0]) * (c[3] - c[1]) / full
                    dets.append(Detection(*c, conf, 0, "colony"))
    merged = merge_detections(dets)

    # Zona ampliada: alrededor de las colonias que vieron varias teselas.
    dup_centres = [((d.x1 + d.x2) / 2, (d.y1 + d.y2) / 2) for d in dets
                   if sum(1 for e in dets if abs((e.x1 + e.x2) / 2 - (d.x1 + d.x2) / 2) < 40
                          and abs((e.y1 + e.y2) / 2 - (d.y1 + d.y2) / 2) < 40) > 1]
    cx, cy = np.median([c[0] for c in dup_centres]), np.median([c[1] for c in dup_centres])
    zx0, zy0 = int(max(0, cx - 300)), int(max(0, cy - 220))
    zx1, zy1 = min(W, zx0 + 600), min(H, zy0 + 440)
    tile_cols = ["#FFD600", "#00E5FF", "#FFFFFF", "#76FF03"]

    fig, axes = plt.subplots(1, 2, figsize=(16, 6.6))
    panels = [(axes[0], f"Antes: {len(dets)} cajas en toda la placa (cada tesela, un color)", True),
              (axes[1], f"Después de fusionar por IoS: {len(merged)} cajas = {len(bx)} colonias anotadas", False)]
    for ax, title, before in panels:
        ax.imshow(small)
        for x0 in tile_starts(W, TILE, OV):
            ax.axvline(x0, color="white", lw=1, ls=":")
            ax.axvline(x0 + TILE, color="white", lw=1, ls=":")
        for y0 in tile_starts(H, TILE, OV):
            ax.axhline(y0, color="white", lw=1, ls=":")
            ax.axhline(y0 + TILE, color="white", lw=1, ls=":")
        if before:
            k = 0
            for y0 in tile_starts(H, TILE, OV):
                for x0 in tile_starts(W, TILE, OV):
                    col = tile_cols[k % 4]
                    for b in bx:
                        c = (max(b[0], x0), max(b[1], y0), min(b[2], x0 + TILE), min(b[3], y0 + TILE))
                        full = (b[2] - b[0]) * (b[3] - b[1])
                        if c[2] > c[0] and c[3] > c[1] and (c[2] - c[0]) * (c[3] - c[1]) / full > 0.2:
                            off = (k % 4) * 1.5
                            ax.add_patch(Rectangle((c[0] - off, c[1] - off), c[2] - c[0] + 2 * off,
                                                   c[3] - c[1] + 2 * off, fill=False, ec=col, lw=2))
                    k += 1
        else:
            for d in merged:
                ax.add_patch(Rectangle((d.x1, d.y1), d.x2 - d.x1, d.y2 - d.y1, fill=False, ec="#00E676", lw=2.4))
        ax.set_xlim(zx0, zx1)
        ax.set_ylim(zy1, zy0)
        ax.set_title(title)
        ax.axis("off")
    fig.suptitle("Fusión de duplicados (zona ampliada): una colonia en el solape la ven 2 o 4 teselas, "
                 "a veces cortada; la fusión deja una caja completa por colonia", y=1.0, fontsize=12.5, fontweight="bold")
    save(fig, "04_fusion.png")
    return len(dets), len(merged), len(bx)


# ---------------------------------------------------------------- 5. segmentación
def pick_colony(img_bgr, boxes, prefer="big"):
    scores = []
    for b in boxes:
        w = b[2] - b[0]
        scores.append((w, b))
    scores.sort(key=lambda t: -t[0])
    return scores[len(scores) // 4][1] if prefer == "mid" else scores[0][1]


def fig_segmentacion():
    rgb, boxes, sp = load("sp05_img01.jpg")
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    box = pick_colony(bgr, boxes, "mid")
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    pad = max(3, int(max(bw, bh) * 0.3))
    x0, y0 = max(0, int(x1) - pad), max(0, int(y1) - pad)
    xe, ye = min(bgr.shape[1], int(math.ceil(x2)) + pad), min(bgr.shape[0], int(math.ceil(y2)) + pad)
    crop = bgr[y0:ye, x0:xe]
    ch, cw = crop.shape[:2]
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    ring = np.zeros((ch, cw), bool)
    rw = max(2, pad // 2)
    ring[:rw, :] = ring[-rw:, :] = True
    ring[:, :rw] = ring[:, -rw:] = True
    bg = np.median(lab[ring], axis=0)
    dist = cv2.GaussianBlur(np.linalg.norm(lab - bg, axis=2), (3, 3), 0)
    dist8 = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    otsu_t, otsu = cv2.threshold(dist8, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask, (mx, my), ok = segment_colony(bgr, box)
    morph, _, _ = describe_colony(bgr, box)
    rc = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

    fig, axes = plt.subplots(2, 3, figsize=(15, 10.5), gridspec_kw={"hspace": 0.28, "wspace": 0.08})
    axes = axes.ravel()
    a = axes[0]
    a.imshow(rc)
    a.add_patch(Rectangle((x1 - x0, y1 - y0), bw, bh, fill=False, ec="#00E676", lw=2))
    a.set_title("1. Recorte con margen\n(verde = caja de YOLO)")
    a = axes[1]
    ov = rc.copy()
    ov[ring] = (0.5 * ov[ring] + 0.5 * np.array([255, 152, 0])).astype(np.uint8)
    a.imshow(ov)
    swatch = cv2.cvtColor(np.uint8([[bg]]), cv2.COLOR_LAB2RGB)[0, 0] / 255
    a.add_patch(Rectangle((cw * 0.62, ch * 0.62), cw * 0.3, ch * 0.3, color=swatch, ec="black"))
    a.set_title("2. Anillo exterior (naranja)\n→ color del agar (cuadro)")
    a = axes[2]
    im = a.imshow(dist, cmap="magma")
    a.set_title("3. Distancia de color ΔE\nal agar (claro = colonia)")
    a = axes[3]
    a.imshow(otsu, cmap="gray")
    a.set_title(f"4. Umbral de Otsu\n(corte automático = {otsu_t:.0f} / 255)")
    a = axes[4]
    a.imshow(mask, cmap="gray")
    a.set_title("5. Máscara final: solo dentro de la caja,\nsin ruido ni huecos")
    a = axes[5]
    a.imshow(rc)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cnts, key=cv2.contourArea)
    a.plot(c[:, 0, 0] + mx - x0, c[:, 0, 1] + my - y0, color="#00E5FF", lw=2)
    a.set_title(f"6. Contorno medido: {morph.diameter_px:.0f} px de diámetro\n"
                f"circularidad {morph.circularity:.2f} · {morph.form}, borde {morph.margin}")
    for a in axes:
        a.axis("off")
    fig.suptitle(f"Segmentación de una colonia real (Makrai, especie {sp}): de la caja de YOLO al contorno exacto",
                 y=0.98, fontsize=14, fontweight="bold")
    save(fig, "05_segmentacion.png")


# ---------------------------------------------------------------- 6. descriptores
def fig_descriptores():
    pool = []
    for name in ["sp05_img01.jpg", "sp21_img04.jpg", "eco_01.jpg", "sau_05.jpg"]:
        rgb, boxes, sp = load(name)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        for b in boxes:
            if b[2] - b[0] < 30:
                continue
            m, mask, (mx, my) = describe_colony(bgr, b)
            if m.segmented:
                pool.append((m, mask, mx, my, bgr, sp))
    picks = [max(pool, key=lambda t: t[0].circularity), min(pool, key=lambda t: t[0].solidity),
             max(pool, key=lambda t: t[0].aspect_ratio), max(pool, key=lambda t: t[0].contrast)]
    titles = ["La más circular", "La de borde más irregular", "La más alargada", "La de más contraste"]
    fig, axes = plt.subplots(1, 4, figsize=(16, 5.2))
    for ax, (m, mask, mx, my, bgr, sp), t in zip(axes, picks, titles):
        h, w = mask.shape
        crop = cv2.cvtColor(bgr[my:my + h, mx:mx + w], cv2.COLOR_BGR2RGB)
        ax.imshow(crop)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        c = max(cnts, key=cv2.contourArea)
        hull = cv2.convexHull(c)
        ax.plot(*np.vstack([c[:, 0], c[:1, 0]]).T, color="#00E5FF", lw=2, label="contorno")
        ax.plot(*np.vstack([hull[:, 0], hull[:1, 0]]).T, color="#FFEB3B", lw=1.5, ls="--", label="envolvente convexa")
        if len(c) >= 5:
            (ex, ey), (ma, mi), ang = cv2.fitEllipse(c)
            from matplotlib.patches import Ellipse
            ax.add_patch(Ellipse((ex, ey), ma, mi, angle=ang, fill=False, ec="#FF4081", lw=1.3, ls=":"))
        ax.set_title(f"{t} ({sp})", fontsize=11.5)
        ax.text(0.02, -0.04, f"circularidad {m.circularity:.2f} · aspecto {m.aspect_ratio:.2f}\n"
                             f"solidez {m.solidity:.2f} · contraste ΔE {m.contrast:.0f}\n"
                             f"→ forma {m.form}, borde {m.margin}, color {m.color_name}",
                transform=ax.transAxes, va="top", fontsize=10.5)
        ax.axis("off")
    axes[0].legend(loc="upper left", fontsize=9, framealpha=0.85)
    fig.suptitle("Descriptores medidos sobre colonias reales: contorno (cian), envolvente convexa (amarillo) y elipse ajustada (rosa)",
                 y=1.02, fontsize=13, fontweight="bold")
    save(fig, "06_descriptores.png")


# ---------------------------------------------------------------- 7. conteo
def fig_conteo():
    rgb, boxes, sp = load("sp05_img01.jpg")
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    dets = [Detection(*b, 1.0, 0, "colonia") for b in boxes]
    mm = 90 / (0.95 * min(bgr.shape[:2]))
    result, ann = analyze(bgr, dets, mm_per_px=mm, dilution=1e-4, volume_ml=0.1)
    s = result["summary"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw={"width_ratios": [1.2, 1]})
    a1.imshow(cv2.cvtColor(ann, cv2.COLOR_BGR2RGB))
    a1.set_title("Imagen anotada que genera Bioyologic: cada colonia contorneada y numerada")
    a1.axis("off")
    d = s["stats"]["diameter_mm"]
    lines = [
        ("Total de colonias", f"{s['total']}"),
        ("Estado de la placa", {"pocas": "Pocas colonias (< 30)", "contable": "Contable (30–300)"}.get(s["status"], s["status"])),
        ("Siembra", "dilución 10⁻⁴ · 0,1 mL"),
        ("UFC/mL", f"{s['cfu_per_ml'] / 10 ** math.floor(math.log10(s['cfu_per_ml'])):.2f}".replace(".", ",")
         + f" × 10$^{{{math.floor(math.log10(s['cfu_per_ml']))}}}$"),
        ("Diámetro medio", f"{d['mean']:.2f} ± {d['std']:.2f} mm".replace(".", ",")),
        ("Forma predominante", s["predominant"]["form"]),
        ("Borde predominante", s["predominant"]["margin"]),
        ("Color predominante", s["predominant"]["color"]),
    ]
    a2.set_xlim(0, 1)
    a2.set_ylim(0, 1)
    a2.axis("off")
    a2.set_title("Resumen que calcula el servidor", loc="left")
    for i, (k, v) in enumerate(lines):
        y = 0.9 - i * 0.105
        a2.text(0.02, y, k, fontsize=13, color="#555")
        a2.text(0.98, y, v, fontsize=14, fontweight="bold", ha="right")
        a2.plot([0.02, 0.98], [y - 0.035, y - 0.035], color="#ddd", lw=1)
    a2.text(0.02, 0.02, f"Placa {sp} de Makrai et al. Cajas = anotaciones del dataset\n"
                         "(el modelo entrenado en Colab las sustituirá)", fontsize=10, color="#777")
    save(fig, "07_conteo.png")
    return s


# ---------------------------------------------------------------- fórmulas
def formula(name, tex, w=7.5, h=1.1, size=22):
    fig = plt.figure(figsize=(w, h))
    fig.text(0.5, 0.5, tex, ha="center", va="center", fontsize=size)
    save(fig, name)


if __name__ == "__main__":
    fig_datasets()
    n_tiles = fig_teselas()
    fig_particion()
    print("fusión:", fig_fusion())
    fig_segmentacion()
    fig_descriptores()
    print("conteo:", fig_conteo()["total"])
    formula("f_ios.png", r"$\mathrm{IoS} = \dfrac{\mathrm{área}(A \cap B)}{\min(\mathrm{área}(A),\ \mathrm{área}(B))}$")
    formula("f_escala.png", r"$\mathrm{mm\ por\ píxel} = \dfrac{\mathrm{diámetro\ de\ la\ placa\ (90\ mm)}}{0{,}80 \times \mathrm{lado\ corto\ de\ la\ foto\ (px)}}$", w=10)
    formula("f_ufc.png", r"$\mathrm{UFC/mL} = \dfrac{N_{\mathrm{colonias}}}{\mathrm{dilución} \times \mathrm{volumen\ sembrado\ (mL)}}$", w=9)
    formula("f_ufc_ejemplo.png", r"$\dfrac{60}{10^{-4} \times 0{,}1\ \mathrm{mL}} = 6{,}0 \times 10^{6}\ \mathrm{UFC/mL}$", w=7)
    formula("f_descriptores.png",
            r"$\mathrm{Circularidad} = \dfrac{4\pi A}{P^{2}} \qquad \mathrm{Solidez} = \dfrac{A}{A_{\mathrm{convexa}}} \qquad d_{\mathrm{eq}} = 2\sqrt{A/\pi}$",
            w=12)
