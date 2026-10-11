"""Genera Bioyologic_especies.ipynb: clasificador de especie por colonia (Google Colab).

    python training/make_species_notebook.py

Segunda etapa del sistema: el detector (Bioyologic_entrenamiento.ipynb) encuentra las
colonias; este clasificador mira el recorte de cada colonia y dice su especie.
"""

import json
from pathlib import Path

import make_notebook as det

HERE = Path(__file__).resolve().parent
SPECIES_MAP = json.loads((HERE / "species_map.json").read_text(encoding="utf-8"))

INTRO = """# Bioyologic · Clasificador de especie por colonia (Google Colab)

Segunda etapa de Bioyologic: el **detector** ya encuentra y cuenta las colonias; este notebook entrena un **clasificador** (YOLO11-cls) que mira el recorte de cada colonia y dice su especie. La especie de la placa se decide por votación entre sus colonias.

Datos: los mismos dos datasets públicos (Makrai *et al.* 2023 y el dataset clínico de Zenodo), unificados por nombre de especie: **37 especies**.

**Cómo usarlo**: `Entorno de ejecución → Cambiar tipo → GPU T4` y `Ejecutar todo` (~1,5 h). Al final se descarga `bioyologic_species.zip` (modelo + configuración): descomprímelo en `models/`.

**Advertencia**: en estos datasets cada placa tiene una sola especie y cada especie se cultivó en su propio medio (sangre, MacConkey, etc.). El clasificador puede apoyarse en el color del agar además de en la colonia. Con fotos de otro laboratorio, la especie es orientativa y debe confirmarse con pruebas microbiológicas.
"""

CONFIG = f"""# 2. Configuración
from pathlib import Path

WORK = Path("/content")
RAW = WORK / "raw"
DATASET = WORK / "crops"                  # dataset de clasificación: split/especie/recorte.jpg

USE_MAKRAI = True
USE_CLINICAL = True

PAD = 0.30            # margen alrededor de la caja (se ve un poco de agar, como en el servidor)
CROP_SIZE = 160       # lado del recorte guardado (px)
MAX_PER_PLATE = 80    # recortes por placa como máximo (equilibra placas muy pobladas)
MIN_BOX = 12          # cajas más pequeñas (px) se descartan
SPLIT = (0.8, 0.1, 0.1)
SEED = 42

MODEL = "yolo11s-cls.pt"
IMGSZ = 160
EPOCHS = 40
TIME_HOURS = 1.0
BATCH = 256

# código de cada dataset -> especie (tablas 1 de ambos artículos)
SPECIES_MAP = {json.dumps(SPECIES_MAP["codes"], ensure_ascii=False)}"""

CROPS = """# 4. Recortes de colonias por especie (partición por placa dentro de cada especie)
import json, random, shutil
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np

def square_crop(img, box, pad=PAD):
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    side = max(x2 - x1, y2 - y1) * (1 + 2 * pad)
    h, w = img.shape[:2]
    a, b = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    c, d = int(min(w, cx + side / 2)), int(min(h, cy + side / 2))
    crop = img[b:d, a:c]
    return cv2.resize(crop, (CROP_SIZE, CROP_SIZE), interpolation=cv2.INTER_AREA) if crop.size else None

plates = defaultdict(list)   # especie -> [(ruta, [cajas])]
for src_name, coco_path, img_dir in SOURCES:
    coco = json.loads(Path(coco_path).read_text())
    cats = {c["id"]: SPECIES_MAP[f"{src_name}:{c['name']}"]["species"] for c in coco["categories"]}
    index = {p.name: p for p in Path(img_dir).rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")}
    by_img = defaultdict(list)
    for a in coco["annotations"]:
        x, y, w, h = a["bbox"]
        if max(w, h) >= MIN_BOX:
            by_img[a["image_id"]].append((cats[a["category_id"]], (x, y, x + w, y + h)))
    for im in coco["images"]:
        path = index.get(Path(im["file_name"]).name)
        boxes = by_img.get(im["id"], [])
        if path is None or not boxes:
            continue
        sp = max(set(b[0] for b in boxes), key=lambda s: sum(1 for b in boxes if b[0] == s))
        plates[sp].append((path, [b[1] for b in boxes]))

rng = random.Random(SEED)
parts = {"train": [], "val": [], "test": []}
for sp, items in sorted(plates.items()):
    rng.shuffle(items)
    n = len(items)
    n_te = max(1, round(n * SPLIT[2])) if n >= 3 else 0
    n_va = max(1, round(n * SPLIT[1])) if n >= 3 else 0
    parts["test"] += [(sp, it) for it in items[:n_te]]
    parts["val"] += [(sp, it) for it in items[n_te:n_te + n_va]]
    parts["train"] += [(sp, it) for it in items[n_te + n_va:]]

shutil.rmtree(DATASET, ignore_errors=True)

def export(args):
    part, sp, (path, boxes) = args
    img = cv2.imread(str(path))
    if img is None:
        return 0
    if len(boxes) > MAX_PER_PLATE:
        boxes = random.Random(str(path)).sample(boxes, MAX_PER_PLATE)
    folder = DATASET / part / sp.replace(" ", "_")
    folder.mkdir(parents=True, exist_ok=True)
    n = 0
    for k, b in enumerate(boxes):
        crop = square_crop(img, b)
        if crop is not None:
            cv2.imwrite(str(folder / f"{path.stem}_{k}.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
            n += 1
    return n

summary = {}
for part, items in parts.items():
    with ThreadPoolExecutor(4) as pool:
        counts = list(pool.map(export, [(part, sp, it) for sp, it in items]))
    summary[part] = {"placas": len(items), "recortes": sum(counts)}
TEST_PLATES = parts["test"]
CLASSES = sorted(plates)
print(json.dumps(summary, indent=2, ensure_ascii=False))
print(len(CLASSES), "especies:", ", ".join(CLASSES))"""

PREVIEW = """# 5. Un recorte de ejemplo por especie
import matplotlib.pyplot as plt
cols = 8
rows = -(-len(CLASSES) // cols)
fig, axes = plt.subplots(rows, cols, figsize=(2.2 * cols, 2.5 * rows))
for ax in axes.ravel():
    ax.axis("off")
for ax, sp in zip(axes.ravel(), CLASSES):
    files = sorted((DATASET / "train" / sp.replace(" ", "_")).glob("*.jpg"))
    if files:
        ax.imshow(cv2.cvtColor(cv2.imread(str(files[len(files) // 2])), cv2.COLOR_BGR2RGB))
    ax.set_title(sp, fontsize=8, style="italic")
plt.tight_layout(); plt.show()"""

TRAIN = """# 6. Entrenamiento del clasificador
from ultralytics import YOLO

model = YOLO(MODEL)
model.train(data=str(DATASET), epochs=EPOCHS, time=TIME_HOURS, imgsz=IMGSZ, batch=BATCH, patience=10,
            workers=2, project=str(WORK / "runs"), name="species", exist_ok=True, cos_lr=True,
            fliplr=0.5, flipud=0.5, degrees=180, hsv_h=0.01, hsv_s=0.3, hsv_v=0.3)
BEST = Path(model.trainer.best)
m = YOLO(str(BEST)).val(data=str(DATASET), split="test", imgsz=IMGSZ)
print(f"TEST por colonia: top-1 = {m.top1:.3f} · top-5 = {m.top5:.3f}")"""

EVAL = """# 7. Precisión por PLACA: votación entre las colonias de cada placa de test
from collections import Counter
clf = YOLO(str(BEST))
names = clf.names
ok, rows = 0, []
for sp, (path, boxes) in TEST_PLATES:
    img = cv2.imread(str(path))
    crops = [c for c in (square_crop(img, b) for b in boxes[:MAX_PER_PLATE]) if c is not None]
    probs = np.zeros(len(names))
    for i in range(0, len(crops), 128):
        for r in clf.predict(crops[i:i + 128], imgsz=IMGSZ, verbose=False):
            probs += r.probs.data.cpu().numpy()
    pred = names[int(probs.argmax())].replace("_", " ")
    ok += pred == sp
    rows.append((sp, pred, probs.max() / max(1, len(crops))))
print(f"Placas de test: {len(rows)} · especie correcta en {ok} ({100 * ok / len(rows):.1f} %)")
errors = Counter((t, p) for t, p, _ in rows if t != p)
for (t, p), n in errors.most_common(10):
    print(f"  {t} → confundida con {p} ({n} placa{'s' if n > 1 else ''})")"""

EXPORT = """# 8. Exportar para Bioyologic
out = WORK / "bioyologic_species.pt"
shutil.copy(BEST, out)
info = {v["species"]: {"gram": v["gram"], "agar": v["agar"]} for v in SPECIES_MAP.values()}
(WORK / "bioyologic_species.json").write_text(json.dumps({
    "pad": PAD, "imgsz": IMGSZ, "classes": [names[i].replace("_", " ") for i in range(len(names))],
    "species_info": info, "datasets": [s[0] for s in SOURCES],
}, indent=1, ensure_ascii=False))
# Un solo archivo: Chrome bloquea las descargas múltiples automáticas.
import zipfile
bundle = WORK / "bioyologic_species.zip"
with zipfile.ZipFile(bundle, "w") as z:
    z.write(out, out.name)
    z.write(WORK / "bioyologic_species.json", "bioyologic_species.json")
try:
    from google.colab import files
    files.download(str(bundle))
except ImportError:
    print("Copia manualmente:", bundle)"""

CELLS = [("markdown", INTRO), ("code", det.SETUP), ("code", CONFIG), ("code", det.DOWNLOAD),
         ("code", CROPS), ("code", PREVIEW), ("code", TRAIN), ("code", EVAL), ("code", EXPORT)]


def build() -> dict:
    saved = det.CELLS
    det.CELLS = CELLS
    try:
        nb = det.build()
    finally:
        det.CELLS = saved
    return nb


if __name__ == "__main__":
    out = HERE / "Bioyologic_especies.ipynb"
    out.write_text(json.dumps(build(), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Notebook escrito en {out}")
