"""Genera Bioyologic_entrenamiento.ipynb (notebook de Google Colab).

    python training/make_notebook.py

Las celdas de código están en CELLS; test_notebook.py ejecuta localmente las
de conversión, evaluación y exportación con datos sintéticos para comprobarlas.
"""

import json
from pathlib import Path

INTRO = """# Bioyologic · Entrenamiento del detector de colonias (Google Colab)

Entrena el detector YOLO de Bioyologic con fotos **reales** de placas de Petri de dos bases de datos públicas, sin registro:

| Dataset | Placas | Colonias | Especies | Licencia |
|---|---|---|---|---|
| Makrai L. *et al.* (2023) *Scientific Data* 10:497 · [doi:10.6084/m9.figshare.22022540](https://doi.org/10.6084/m9.figshare.22022540) | 369 | 56 865 | 24 (veterinarias) | CC BY 4.0 |
| Du, J. (2026). *Clinical Dataset of 19 Bacterial Colony Images* · [doi:10.5281/zenodo.18256864](https://doi.org/10.5281/zenodo.18256864) | 950 | 59 221 | 19 (clínicas) | CC BY 4.0 |

**Cómo usarlo**
1. `Entorno de ejecución → Cambiar tipo de entorno de ejecución → GPU T4`.
2. `Entorno de ejecución → Ejecutar todo`. Tarda unas 2 h (descarga ≈10 min, preparación ≈10 min, entrenamiento ≤ `TIME_HOURS`).
3. Al final se descarga **`bioyologic_detector.zip`** (`bioyologic.pt` + `bioyologic.json`): descomprímelo en `models/` y reinicia la API.

**Añadir más datos (opcional).** En la celda 2, `EXTRA` acepta carpetas o `.zip` con más fotos anotadas: las placas que corregiste en la app (`python -m bioyologic.manage export-coco`) u otro dataset público. Las placas de test de los dos datasets de la tabla **no cambian** al añadir datos: la celda 8 mide el modelo nuevo y el actual sobre esas mismas placas (y sobre las nuevas) y dice si conviene reemplazarlo.
"""

SETUP = """# 1. GPU y dependencias
!nvidia-smi --query-gpu=name,memory.total --format=csv || echo "⚠️ Sin GPU: activa T4 en 'Cambiar tipo de entorno de ejecución'"
%pip install -q ultralytics
import ultralytics, torch
print("ultralytics", ultralytics.__version__, "| CUDA:", torch.cuda.is_available())"""

CONFIG = """# 2. Configuración
from pathlib import Path

WORK = Path("/content")
RAW = WORK / "raw"                        # fotos y anotaciones originales
DATASET = WORK / "yolo"                   # dataset en formato YOLO

USE_MAKRAI = True       # 369 placas, 0,6 GB
USE_CLINICAL = True     # 950 placas, 5,6 GB

CLASS_MODE = "single"   # "single": una clase 'colony' (conteo) | "species": una clase por especie
MAX_SIDE = 2048         # las fotos se reducen a este lado máximo antes de teselar
TILE = 640              # tamaño de cada tesela (= imgsz de YOLO)
OVERLAP = 0.2           # solapamiento entre teselas
SPLIT = (0.8, 0.1, 0.1) # train / val / test, por PLACA (no por tesela)
SEED = 42

MODEL = "yolo11s.pt"    # n = más rápido, s = equilibrio, m = más preciso
EPOCHS = 60
TIME_HOURS = 1.5        # límite de tiempo de entrenamiento (las sesiones gratuitas de Colab son limitadas)
BATCH = 32

# --- Datos adicionales (opcional) -------------------------------------------------------------------
# Cada entrada es una carpeta o un .zip (por ejemplo en Google Drive) con fotos anotadas, en uno de dos formatos:
#   · COCO: un .json con "images", "annotations" y "categories", más las fotos. Es lo que genera
#     «python -m bioyologic.manage export-coco» con las placas que corregiste en la app.
#   · AGAR: un .json por foto con "labels" (Majchrowska et al. 2021, arXiv:2108.01234).
# "max_plates" (opcional) limita cuántas placas se usan, al azar, para que un dataset grande no domine.
# Antes de usar un dataset ajeno, revisa su licencia y cítalo en THIRD_PARTY_LICENSES.md.
EXTRA = [
    # {"name": "mi_lab", "path": "/content/drive/MyDrive/bioyologic/mi_lab.zip"},
    # {"name": "agar", "path": "/content/drive/MyDrive/agar", "max_plates": 1500},
]

# Modelo actual de Bioyologic: al final se compara con el nuevo en las MISMAS placas de test.
BASELINE = "https://github.com/bioyologic/bioyologic/raw/main/models/bioyologic.pt"   # "" = no comparar
FINETUNE = False        # True: el entrenamiento parte del modelo actual (útil si solo añades pocas fotos)"""

DOWNLOAD = """# 3. Descarga de los datasets
import json, struct, urllib.request, zipfile, zlib
from concurrent.futures import ThreadPoolExecutor

def http_range(url, start, end):
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
    return urllib.request.urlopen(req, timeout=300).read()

def remote_zip_entries(url):
    \"\"\"Índice de un ZIP remoto (también ZIP64) leyendo solo su directorio central.\"\"\"
    size = int(urllib.request.urlopen(urllib.request.Request(url, method="HEAD")).headers["Content-Length"])
    tail = http_range(url, max(0, size - 65558), size - 1)
    i = tail.rfind(b"PK\\x05\\x06")
    cd_size, cd_off = struct.unpack("<II", tail[i + 12:i + 20])
    if cd_off == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        j = tail.rfind(b"PK\\x06\\x06")
        cd_size, cd_off = struct.unpack("<QQ", tail[j + 40:j + 56])
    cd = http_range(url, cd_off, cd_off + cd_size - 1)
    entries, p = {}, 0
    while cd[p:p + 4] == b"PK\\x01\\x02":
        method = struct.unpack("<H", cd[p + 10:p + 12])[0]
        csize, usize = struct.unpack("<II", cd[p + 20:p + 28])
        n, e, c = struct.unpack("<HHH", cd[p + 28:p + 34])
        off = struct.unpack("<I", cd[p + 42:p + 46])[0]
        name = cd[p + 46:p + 46 + n].decode("utf-8", "replace")
        extra, q = cd[p + 46 + n:p + 46 + n + e], 0
        while q + 4 <= len(extra):
            hid, hlen = struct.unpack("<HH", extra[q:q + 4])
            if hid == 1:
                vals, k = extra[q + 4:q + 4 + hlen], 0
                if usize == 0xFFFFFFFF: usize = struct.unpack("<Q", vals[k:k + 8])[0]; k += 8
                if csize == 0xFFFFFFFF: csize = struct.unpack("<Q", vals[k:k + 8])[0]; k += 8
                if off == 0xFFFFFFFF: off = struct.unpack("<Q", vals[k:k + 8])[0]; k += 8
            q += 4 + hlen
        entries[name] = (method, csize, off)
        p += 46 + n + e + c
    return entries

def remote_zip_read(url, entries, name):
    method, csize, off = entries[name]
    n, e = struct.unpack("<HH", http_range(url, off, off + 29)[26:30])
    data = http_range(url, off + 30 + n + e, off + 30 + n + e + csize - 1)
    return data if method == 0 else zlib.decompress(data, -15)

def download(url, dest, size=None, parts=1):
    \"\"\"Descarga a disco; con parts > 1, en trozos paralelos (Zenodo limita ~1 MB/s por conexión).\"\"\"
    if dest.exists() and (size is None or dest.stat().st_size == size):
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    if parts == 1:
        with urllib.request.urlopen(url, timeout=300) as r, open(tmp, "wb") as f:
            while chunk := r.read(8 << 20):
                f.write(chunk)
    else:
        total = int(urllib.request.urlopen(urllib.request.Request(url, method="HEAD")).headers["Content-Length"])
        with open(tmp, "wb") as f:
            f.truncate(total)
        step = -(-total // parts)
        def piece(i):
            start, end = i * step, min(total, (i + 1) * step) - 1
            req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "r+b") as f:
                f.seek(start)
                while chunk := r.read(8 << 20):
                    f.write(chunk)
        with ThreadPoolExecutor(parts) as pool:
            list(pool.map(piece, range(parts)))
    tmp.rename(dest)

SOURCES = []   # (nombre, coco.json, carpeta de imágenes)

if USE_MAKRAI:
    d = RAW / "makrai"
    d.mkdir(parents=True, exist_ok=True)
    meta = json.load(urllib.request.urlopen("https://api.figshare.com/v2/articles/22022540"))
    files = [f for f in meta["files"] if f["name"].lower().endswith(".jpg") or f["name"] == "annot_COCO.json"]
    with ThreadPoolExecutor(16) as pool:
        list(pool.map(lambda f: download(f["download_url"], d / f["name"], f["size"]), files))
    SOURCES.append(("makrai", d / "annot_COCO.json", d))
    print(f"Makrai: {len(files)} archivos")

if USE_CLINICAL:
    d = RAW / "clinical"
    d.mkdir(parents=True, exist_ok=True)
    base = "https://zenodo.org/api/records/18256864/files"
    # Las etiquetas (label.zip, 2,6 GB) incluyen JSON de LabelMe con la imagen embebida:
    # solo se extrae coco.json (~1 MB) leyendo ese fragmento del ZIP remoto.
    if not (d / "coco.json").exists():
        url = f"{base}/label.zip/content"
        (d / "coco.json").write_bytes(remote_zip_read(url, remote_zip_entries(url), "label/coco_json/coco.json"))
    if not (d / "images").exists():
        download(f"{base}/images.zip/content", d / "images.zip", parts=16)
        with zipfile.ZipFile(d / "images.zip") as z:
            z.extractall(d)
        (d / "images.zip").unlink()
    SOURCES.append(("clinical", d / "coco.json", d / "images"))
    print("Clinical: listo")

!du -sh {RAW}/*"""

EXTRAS = """# 3b. Datos adicionales (EXTRA) y modelo actual (BASELINE)
import json, random, urllib.request, zipfile

IMG_EXT = (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG")

def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None

def is_coco(d):
    return isinstance(d, dict) and {"images", "annotations", "categories"} <= d.keys()

def agar_to_coco(folder, limit, seed):
    # AGAR trae un .json por foto: {"labels": [{"class", "x", "y", "width", "height"}], "colonies_number": n}.
    # Las placas «incontables» no tienen cajas y se descartan; las vacías (0 colonias) sí valen.
    anns = sorted(Path(folder).rglob("*.json"))
    random.Random(seed).shuffle(anns)
    coco, cats = {"images": [], "annotations": [], "categories": []}, {}
    for ann in anns:
        if limit and len(coco["images"]) >= limit:
            break
        d = read_json(ann)
        img = next((ann.with_suffix(e) for e in IMG_EXT if ann.with_suffix(e).exists()), None)
        if img is None or not isinstance(d, dict) or "labels" not in d:
            continue
        if not d["labels"] and d.get("colonies_number", 0) != 0:
            continue
        iid = len(coco["images"]) + 1
        coco["images"].append({"id": iid, "file_name": img.name})
        for lb in d["labels"]:
            cid = cats.setdefault(str(lb["class"]), len(cats) + 1)
            coco["annotations"].append({"id": len(coco["annotations"]) + 1, "image_id": iid, "category_id": cid,
                                        "bbox": [lb["x"], lb["y"], lb["width"], lb["height"]]})
    coco["categories"] = [{"id": i, "name": n} for n, i in cats.items()]
    return coco

if any(str(e["path"]).startswith("/content/drive") for e in EXTRA):
    from google.colab import drive
    drive.mount("/content/drive")

EXTRA_SOURCES = []   # (nombre, coco.json, carpeta de imágenes, máximo de placas)
for e in EXTRA:
    name, src = e["name"], Path(e["path"])
    assert name not in ("base", "makrai", "clinical") and name not in [x[0] for x in EXTRA_SOURCES], \\
        f"Nombre no válido o repetido en EXTRA: {name}"
    assert src.exists(), f"EXTRA «{name}»: no existe {src}"
    folder = src
    if src.suffix.lower() == ".zip":
        folder = RAW / "extra" / name
        if not folder.exists():
            with zipfile.ZipFile(src) as z:
                z.extractall(folder)
    coco_path = next((p for p in sorted(folder.rglob("*.json"))[:20] if is_coco(read_json(p))), None)
    kind = "COCO"
    if coco_path is None:
        kind = "AGAR"
        coco = agar_to_coco(folder, e.get("max_plates"), SEED)
        assert coco["images"], f"EXTRA «{name}»: en {src} no hay fotos anotadas en formato COCO ni AGAR"
        coco_path = RAW / "extra" / f"{name}_coco.json"
        coco_path.parent.mkdir(parents=True, exist_ok=True)
        coco_path.write_text(json.dumps(coco), encoding="utf-8")
    EXTRA_SOURCES.append((name, coco_path, folder, e.get("max_plates")))
    print(f"EXTRA «{name}»: formato {kind}, {len(read_json(coco_path)['images'])} fotos anotadas")
if not EXTRA:
    print("Sin datos adicionales: se entrena solo con los datasets base.")

BASELINE_PT = None
if BASELINE:
    BASELINE_PT = Path(BASELINE) if Path(BASELINE).exists() else WORK / ("actual_" + BASELINE.split("/")[-1])
    if not BASELINE_PT.exists():
        urllib.request.urlretrieve(BASELINE, BASELINE_PT)
    print("Modelo actual para comparar:", BASELINE_PT.name, f"({BASELINE_PT.stat().st_size / 1e6:.0f} MB)")"""

CONVERT = """# 4. Conversión COCO → YOLO con teselado
import json, random, shutil
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np

def tile_starts(length, tile, overlap):
    if length <= tile:
        return [0]
    step = int(tile * (1 - overlap))
    starts = list(range(0, length - tile, step))
    starts.append(length - tile)
    return starts

def load_coco(src_name, coco_path, img_dir):
    # Cada muestra: (ruta de la imagen, [(nombre_clase, x, y, w, h), ...])
    coco = json.loads(Path(coco_path).read_text(encoding="utf-8"))
    cats = {c["id"]: f"{src_name}:{c['name']}" for c in coco["categories"]}
    index = {p.name: p for p in Path(img_dir).rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")}
    boxes = {}
    for a in coco["annotations"]:
        boxes.setdefault(a["image_id"], []).append((cats[a["category_id"]], *a["bbox"]))
    out = [(index[Path(im["file_name"]).name], boxes.get(im["id"], []))
           for im in coco["images"] if Path(im["file_name"]).name in index]
    print(f"{src_name}: {len(out)}/{len(coco['images'])} imágenes, {sum(len(b) for _, b in out)} colonias")
    return out

def split(items):
    n = len(items)
    n_tr, n_va = int(n * SPLIT[0]), int(n * SPLIT[1])
    return {"train": items[:n_tr], "val": items[n_tr:n_tr + n_va], "test": items[n_tr + n_va:]}

samples = []
for src_name, coco_path, img_dir in SOURCES:
    samples += load_coco(src_name, coco_path, img_dir)
# Los datasets base se reparten SIEMPRE igual (misma semilla, sin mezclarlos con los datos adicionales):
# su test son las mismas placas con las que se midió el modelo actual, que nunca las vio al entrenar.
random.Random(SEED).shuffle(samples)
parts = split(samples)
TEST_BASE, TEST_EXTRA, SUBSET = list(parts["test"]), {}, {}
for src_name, coco_path, img_dir, limit in EXTRA_SOURCES:
    items = load_coco(src_name, coco_path, img_dir)
    random.Random(SEED).shuffle(items)
    items = items[:limit] if limit else items
    extra = split(items)
    for part in parts:
        parts[part] = parts[part] + extra[part]
    TEST_EXTRA[src_name] = extra["test"]
    SUBSET.update({path: src_name for path, _ in items})

names = ["colony"] if CLASS_MODE == "single" else sorted({b[0] for items in parts.values() for _, bs in items for b in bs})
cls_index = {n: i for i, n in enumerate(names)}

def cls_of(name):
    return 0 if CLASS_MODE == "single" else cls_index[name]

shutil.rmtree(DATASET, ignore_errors=True)

def convert(item, part):
    path, bxs = item
    img = cv2.imread(str(path))
    if img is None:
        return 0, 0, []
    scale = min(1.0, MAX_SIDE / max(img.shape[:2]))
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    boxes = [(cls_of(c), x * scale, y * scale, (x + w) * scale, (y + h) * scale) for c, x, y, w, h in bxs]
    H, W = img.shape[:2]
    stem = f"{path.parent.name}_{path.stem}"
    if path in SUBSET:   # dos fuentes adicionales pueden traer archivos con el mismo nombre
        stem = f"{SUBSET[path]}_{stem}"
    n_boxes, files = 0, []
    for y0 in tile_starts(H, TILE, OVERLAP):
        for x0 in tile_starts(W, TILE, OVERLAP):
            crop = img[y0:y0 + TILE, x0:x0 + TILE]
            th, tw = crop.shape[:2]
            lines = []
            for c, x1, y1, x2, y2 in boxes:
                cx1, cy1 = max(x1 - x0, 0), max(y1 - y0, 0)
                cx2, cy2 = min(x2 - x0, tw), min(y2 - y0, th)
                full = (x2 - x1) * (y2 - y1)
                vis = max(0, cx2 - cx1) * max(0, cy2 - cy1)
                if full <= 0 or vis / full < 0.5:   # colonia cortada: se guarda si se ve ≥ 50 %
                    continue
                lines.append(f"{c} {(cx1 + cx2) / 2 / tw:.6f} {(cy1 + cy2) / 2 / th:.6f} "
                             f"{(cx2 - cx1) / tw:.6f} {(cy2 - cy1) / th:.6f}")
            name = f"{stem}_{x0}_{y0}"
            cv2.imwrite(str(DATASET / "images" / part / f"{name}.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
            (DATASET / "labels" / part / f"{name}.txt").write_text("\\n".join(lines))
            files.append(str(DATASET / "images" / part / f"{name}.jpg"))
            n_boxes += len(lines)
    return len(files), n_boxes, files

summary, test_files = {}, {}
for part, items in parts.items():
    (DATASET / "images" / part).mkdir(parents=True)
    (DATASET / "labels" / part).mkdir(parents=True)
    with ThreadPoolExecutor(4) as pool:
        res = list(pool.map(lambda it: convert(it, part), items))
    summary[part] = {"placas": len(items), "teselas": sum(r[0] for r in res), "cajas": sum(r[1] for r in res)}
    if part == "test":
        for (path, _), r in zip(items, res):
            test_files.setdefault(SUBSET.get(path, "base"), []).extend(r[2])

def write_yaml(file, test):
    (DATASET / file).write_text(
        f"path: {DATASET.as_posix()}\\ntrain: images/train\\nval: images/val\\ntest: {test}\\n"
        + "names:\\n" + "".join(f"  {i}: '{nm}'\\n" for i, nm in enumerate(names)))

write_yaml("data.yaml", "images/test")
# Una lista de teselas de test por origen: la celda 8 mide cada uno por separado.
for subset, files in test_files.items():
    (DATASET / f"test_{subset}.txt").write_text("\\n".join(files))
    write_yaml(f"data_{subset}.yaml", f"test_{subset}.txt")
TEST_SAMPLES = parts["test"]
print(json.dumps(summary, indent=2, ensure_ascii=False))
print("Placas de test:", {"base": len(TEST_BASE), **{k: len(v) for k, v in TEST_EXTRA.items()}})"""

PREVIEW = """# 5. Comprobación visual de algunas teselas con sus etiquetas
import matplotlib.pyplot as plt

tiles = sorted((DATASET / "images" / "train").glob("*.jpg"))
random.Random(1).shuffle(tiles)
tiles = [t for t in tiles if (DATASET / "labels" / "train" / f"{t.stem}.txt").read_text().strip()][:6]
fig, axes = plt.subplots(1, len(tiles), figsize=(4 * len(tiles), 4))
for ax, t in zip(np.atleast_1d(axes), tiles):
    img = cv2.cvtColor(cv2.imread(str(t)), cv2.COLOR_BGR2RGB)
    h, w = img.shape[:2]
    for line in (DATASET / "labels" / "train" / f"{t.stem}.txt").read_text().split("\\n"):
        if line.strip():
            _, cx, cy, bw, bh = map(float, line.split())
            cv2.rectangle(img, (int((cx - bw / 2) * w), int((cy - bh / 2) * h)),
                          (int((cx + bw / 2) * w), int((cy + bh / 2) * h)), (255, 0, 0), 2)
    ax.imshow(img); ax.axis("off"); ax.set_title(t.stem[:22], fontsize=8)
plt.show()"""

TRAIN = """# 6. Entrenamiento
from ultralytics import YOLO

model = YOLO(str(BASELINE_PT) if FINETUNE and BASELINE_PT is not None and CLASS_MODE == "single" else MODEL)
model.train(
    data=str(DATASET / "data.yaml"), epochs=EPOCHS, time=TIME_HOURS, imgsz=TILE, batch=BATCH,
    patience=15, workers=2, project=str(WORK / "runs"), name="bioyologic", exist_ok=True, cos_lr=True,
    # La orientación de una placa no tiene significado biológico:
    fliplr=0.5, flipud=0.5, degrees=180, scale=0.3, mosaic=1.0,
    hsv_h=0.01, hsv_s=0.4, hsv_v=0.3,
)
BEST = Path(model.trainer.best)
metrics = YOLO(str(BEST)).val(data=str(DATASET / "data.yaml"), split="test", imgsz=TILE)
print(f"TEST  mAP50={metrics.box.map50:.3f}  mAP50-95={metrics.box.map:.3f}  "
      f"P={metrics.box.mp:.3f}  R={metrics.box.mr:.3f}")"""

EVAL = """# 7. Error de CONTEO en placas completas de test (lo que importa al microbiólogo)
# Misma inferencia que el backend de Bioyologic: reducción a MAX_SIDE, teselas y fusión por IoS.
def merge(dets, thr=0.6):
    if not dets:
        return []
    b = np.array([d[:4] for d in dets], np.float32)
    areas = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    order = sorted(range(len(dets)), key=lambda i: (dets[i][4], areas[i]), reverse=True)
    sup = np.zeros(len(dets), bool)
    out = []
    for i in order:
        if sup[i]:
            continue
        inter = (np.clip(np.minimum(b[i, 2], b[:, 2]) - np.maximum(b[i, 0], b[:, 0]), 0, None)
                 * np.clip(np.minimum(b[i, 3], b[:, 3]) - np.maximum(b[i, 1], b[:, 1]), 0, None))
        grp = (inter / np.maximum(np.minimum(areas[i], areas), 1e-6) > thr) & ~sup
        sup |= grp
        g = b[grp]
        out.append((g[:, 0].min(), g[:, 1].min(), g[:, 2].max(), g[:, 3].max(), dets[i][4]))
    return out

def count_colonies(model, img, conf=0.25):
    scale = min(1.0, MAX_SIDE / max(img.shape[:2]))
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    H, W = img.shape[:2]
    offs = [(x, y) for y in tile_starts(H, TILE, OVERLAP) for x in tile_starts(W, TILE, OVERLAP)]
    dets = []
    for i in range(0, len(offs), 16):
        batch = offs[i:i + 16]
        for (ox, oy), r in zip(batch, model.predict([img[y:y + TILE, x:x + TILE] for x, y in batch],
                                                    conf=conf, imgsz=TILE, verbose=False)):
            for (x1, y1, x2, y2), c in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()):
                dets.append((x1 + ox, y1 + oy, x2 + ox, y2 + oy, float(c)))
    return len(merge(dets)) if len(offs) > 1 else len(dets)

def count_errors(model, plates, conf=0.25):
    rows = []
    for path, bxs in plates:
        img = cv2.imread(str(path))
        if img is not None:
            rows.append((f"{path.parent.name}/{path.name}", len(bxs), count_colonies(model, img, conf)))
    true = np.array([r[1] for r in rows], float)
    pred = np.array([r[2] for r in rows], float)
    err, nz = pred - true, true > 0
    return {"placas": len(rows), "rows": rows, "true": true, "pred": pred,
            "MAE": float(np.abs(err).mean()) if rows else 0.0,
            "RMSE": float(np.sqrt((err ** 2).mean())) if rows else 0.0,
            "sesgo": float(err.mean()) if rows else 0.0,
            "MAPE": float(100 * np.abs(err[nz] / true[nz]).mean()) if nz.any() else 0.0}

best_model = YOLO(str(BEST))
res = count_errors(best_model, TEST_SAMPLES)
rows, true, pred = res["rows"], res["true"], res["pred"]
print(f"Placas de test: {len(rows)}")
print(f"MAE  {res['MAE']:.2f} colonias | RMSE {res['RMSE']:.2f} | sesgo {res['sesgo']:+.2f}")
if (true > 0).any():
    print(f"MAPE {res['MAPE']:.1f} %")
if len(rows) > 1 and true.std() > 0 and pred.std() > 0:
    print(f"Pearson r = {np.corrcoef(true, pred)[0, 1]:.4f}")
for name, t, p in sorted(rows, key=lambda r: -abs(r[2] - r[1]))[:5]:
    print(f"  {name}: real {t}  predicho {p}")"""

COMPARE = """# 8. ¿Conviene reemplazar el modelo actual? Los dos se miden sobre las mismas placas de test
TOL_MAPE = 0.3    # puntos de MAPE que el nuevo puede perder en las placas base (ruido entre entrenamientos)
TOL_MAP = 0.005   # ídem para mAP50

def measure(weights, subset, plates):
    m = YOLO(str(weights))
    v = m.val(data=str(DATASET / f"data_{subset}.yaml"), split="test", imgsz=TILE, plots=False, verbose=False,
              project=str(WORK / "runs"), name="comparacion", exist_ok=True)
    c = count_errors(m, plates)
    return {"placas": c["placas"], "mAP50": round(float(v.box.map50), 4), "precision": round(float(v.box.mp), 4),
            "recall": round(float(v.box.mr), 4), "MAE": round(c["MAE"], 2), "MAPE": round(c["MAPE"], 2),
            "sesgo": round(c["sesgo"], 2)}

COMPARISON, VERDICT = {}, None
if BASELINE_PT is None or CLASS_MODE != "single":
    print("No se compara: BASELINE está vacío o CLASS_MODE no es 'single'.")
else:
    for subset, plates in {"base": TEST_BASE, **TEST_EXTRA}.items():
        if plates:
            COMPARISON[subset] = {"actual": measure(BASELINE_PT, subset, plates),
                                  "nuevo": measure(BEST, subset, plates)}
    print(f"{'Test':<14}{'Modelo':<8}{'Placas':>7}{'mAP50':>8}{'P':>7}{'R':>7}{'MAE':>7}{'MAPE %':>8}{'Sesgo':>7}")
    for subset, r in COMPARISON.items():
        for who in ("actual", "nuevo"):
            m = r[who]
            print(f"{subset:<14}{who:<8}{m['placas']:>7}{m['mAP50']:>8.3f}{m['precision']:>7.3f}{m['recall']:>7.3f}"
                  f"{m['MAE']:>7.2f}{m['MAPE']:>8.1f}{m['sesgo']:>+7.2f}")

    # Regla: el nuevo no puede contar ni detectar peor en las placas base y, si hay datos nuevos, tiene que
    # contar mejor en ellos. Sin datos nuevos, tiene que mejorar el conteo en las placas base.
    reasons, notes = [], []
    base = COMPARISON.get("base")
    extras = {k: v for k, v in COMPARISON.items() if k != "base"}
    if not COMPARISON:
        reasons.append("no hay placas de test con las que comparar")
    if base:
        a, n = base["actual"], base["nuevo"]
        if n["MAPE"] > a["MAPE"] + TOL_MAPE:
            reasons.append(f"cuenta peor en las placas base (MAPE {a['MAPE']:.1f} % → {n['MAPE']:.1f} %)")
        if n["mAP50"] < a["mAP50"] - TOL_MAP:
            reasons.append(f"detecta peor en las placas base (mAP50 {a['mAP50']:.3f} → {n['mAP50']:.3f})")
        if not extras and n["MAPE"] >= a["MAPE"]:
            reasons.append("sin datos nuevos, tampoco mejora el conteo en las placas base")
    for subset, r in extras.items():
        a, n = r["actual"], r["nuevo"]
        if n["MAE"] >= a["MAE"]:
            reasons.append(f"no cuenta mejor en «{subset}» (MAE {a['MAE']:.2f} → {n['MAE']:.2f} colonias)")
        if n["placas"] < 10:
            notes.append(f"«{subset}» solo tiene {n['placas']} placa(s) de test: su resultado es poco fiable")
    for src in EXTRA_SOURCES:
        if not TEST_EXTRA.get(src[0]):
            notes.append(f"«{src[0]}» tiene tan pocas placas que ninguna quedó para test")
    VERDICT = "conservar" if reasons else "reemplazar"
    print()
    if VERDICT == "reemplazar":
        print("✅ El modelo NUEVO es mejor: se puede reemplazar el actual.")
    else:
        print("❌ CONSERVA el modelo actual. El nuevo:")
        for r in reasons:
            print("   ·", r)
    for n in notes:
        print("⚠️", n)
    (WORK / "comparacion.json").write_text(json.dumps(
        {"veredicto": VERDICT, "motivos": reasons, "avisos": notes, "resultados": COMPARISON},
        indent=2, ensure_ascii=False), encoding="utf-8")"""

EXPORT = """# 9. Exportar el modelo para Bioyologic
out_pt = WORK / "bioyologic.pt"
shutil.copy(BEST, out_pt)
(WORK / "bioyologic.json").write_text(json.dumps({
    "max_side": MAX_SIDE, "tile": TILE, "imgsz": TILE, "classes": names,
    "datasets": [s[0] for s in SOURCES] + [s[0] for s in EXTRA_SOURCES],
}, indent=2))
# Un solo archivo: Chrome bloquea las descargas múltiples automáticas.
import zipfile
bundle = WORK / "bioyologic_detector.zip"
with zipfile.ZipFile(bundle, "w") as z:
    z.write(out_pt, out_pt.name)
    z.write(WORK / "bioyologic.json", "bioyologic.json")
    if (WORK / "comparacion.json").exists():
        z.write(WORK / "comparacion.json", "comparacion.json")
if VERDICT == "conservar":
    print("⚠️ Este modelo NO superó al actual (celda 8): no lo copies a models/. Se descarga solo para revisarlo.")
try:
    from google.colab import files
    files.download(str(bundle))
except ImportError:
    print("Copia manualmente:", bundle)"""

OUTRO = """## Siguiente paso
**Solo si la celda 8 dice que el modelo nuevo es mejor** (o si no había modelo actual con el que comparar):

1. Copia `bioyologic.pt` y `bioyologic.json` en `Bioyologic/models/`, sustituyendo los anteriores.
2. Ejecuta `python backend/scripts/export_onnx.py` (el servidor usa la versión ONNX) y las pruebas del backend.
3. Actualiza las cifras de `MODEL_CARD.md` y del `README.md` con las de `comparacion.json`, y añade los datos nuevos a `THIRD_PARTY_LICENSES.md` si son de terceros.
4. Sube el cambio y actualiza el servidor.

Si la celda 8 dice que conserves el modelo actual, no cambies nada: el modelo nuevo cuenta peor en alguna parte.

*Opcional:* `CLASS_MODE = "species"` entrena una clase por especie (43 en total). Con 15–50 placas por especie el conteo es bueno, pero la clasificación por especie será limitada."""

CELLS = [("markdown", INTRO), ("code", SETUP), ("code", CONFIG), ("code", DOWNLOAD), ("code", EXTRAS),
         ("code", CONVERT), ("code", PREVIEW), ("code", TRAIN), ("code", EVAL), ("code", COMPARE),
         ("code", EXPORT), ("markdown", OUTRO)]


def build() -> dict:
    def cell(kind, src):
        lines = src.split("\n")
        c = {"cell_type": kind, "metadata": {},
             "source": [l + "\n" for l in lines[:-1]] + [lines[-1]]}
        if kind == "code":
            c |= {"execution_count": None, "outputs": []}
        return c

    return {
        "cells": [cell(k, s) for k, s in CELLS],
        "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "T4"},
                     "kernelspec": {"name": "python3", "display_name": "Python 3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 0,
    }


if __name__ == "__main__":
    out = Path(__file__).with_name("Bioyologic_entrenamiento.ipynb")
    out.write_text(json.dumps(build(), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Notebook escrito en {out}")
