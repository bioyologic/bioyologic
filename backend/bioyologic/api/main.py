"""API REST de Bioyologic.

Arranque:
    uvicorn bioyologic.api.main:app --host 0.0.0.0 --port 8000

Variables de entorno:
    BIOYOLOGIC_MODEL          modelo detector (por defecto models/bioyologic.onnx si existe y
                              está onnxruntime; si no, models/bioyologic.pt)
    BIOYOLOGIC_SPECIES_MODEL  clasificador de especie (misma regla con bioyologic_species)
    BIOYOLOGIC_DATA           carpeta de la base de datos e imágenes (por defecto ../data/store)
    BIOYOLOGIC_MM_PER_PX      escala por defecto si la petición no permite calcularla
    BIOYOLOGIC_TILE           tamaño de tile para la inferencia (0 = sin teselado)
    BIOYOLOGIC_CONF           confianza mínima del detector
    BIOYOLOGIC_MAX_UPLOAD_MB  tamaño máximo de la foto (por defecto 15)
    BIOYOLOGIC_RATE_LIMIT     análisis por minuto y por IP (por defecto 20; 0 = sin límite)
    BIOYOLOGIC_CORS_ORIGINS   orígenes permitidos separados por comas (por defecto *)
    BIOYOLOGIC_SOURCE_URL     URL del código fuente (AGPL-3.0, sección 13)

Si existe app/build/web (flutter build web), la app se sirve en /app.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..analysis.pipeline import analyze
from ..detection.detector import ColonyDetector, Detection
from ..detection.onnx_backend import onnx_available
from ..detection.species import SpeciesClassifier
from ..library import CATEGORIES, ENTRIES, entry_image, get_entry
from ..report import build_report
from ..storage import IMAGE_KINDS, Store

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
MODELS = ROOT / "models"
DEFAULT_DATA = ROOT / "data" / "store"
WEB_BUILD = Path(os.environ.get("BIOYOLOGIC_WEB", ROOT / "app" / "build" / "web"))
MAX_UPLOAD_MB = float(os.environ.get("BIOYOLOGIC_MAX_UPLOAD_MB", "15"))
RATE_LIMIT = int(os.environ.get("BIOYOLOGIC_RATE_LIMIT", "20"))
SOURCE_URL = os.environ.get("BIOYOLOGIC_SOURCE_URL", "https://github.com/Godjuanjo/bioyologic")
LICENSE = "AGPL-3.0-or-later"

app = FastAPI(title="Bioyologic API", version=__version__,
              description="Conteo y caracterización de colonias bacterianas en placas de Petri. "
                          f"Software libre ({LICENSE}).",
              license_info={"name": LICENSE, "url": "https://www.gnu.org/licenses/agpl-3.0.html"})
app.add_middleware(CORSMiddleware, allow_methods=["*"], allow_headers=["*"],
                   allow_origins=os.environ.get("BIOYOLOGIC_CORS_ORIGINS", "*").split(","))


def _default_model(stem: str) -> Path:
    """Prefiere el modelo ONNX (más ligero, sin PyTorch) si está disponible."""
    onnx = MODELS / f"{stem}.onnx"
    return onnx if onnx.exists() and onnx_available() else MODELS / f"{stem}.pt"


# --------------------------------------------------------------------- dependencias
@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store(os.environ.get("BIOYOLOGIC_DATA", DEFAULT_DATA))


def _model_path() -> Path:
    return Path(os.environ.get("BIOYOLOGIC_MODEL") or _default_model("bioyologic"))


@lru_cache(maxsize=1)
def get_detector() -> ColonyDetector:
    weights = _model_path()
    if not weights.exists():
        raise HTTPException(503, f"Modelo no encontrado en {weights}. Entrénalo con el notebook de Colab.")
    tile = int(os.environ.get("BIOYOLOGIC_TILE", "640"))
    return ColonyDetector(weights, conf=float(os.environ.get("BIOYOLOGIC_CONF", "0.25")),
                          tile=tile or None)


@lru_cache(maxsize=1)
def get_species() -> SpeciesClassifier | None:
    """Clasificador de especie (opcional): None si no hay modelo instalado."""
    weights = Path(os.environ.get("BIOYOLOGIC_SPECIES_MODEL") or _default_model("bioyologic_species"))
    if not (weights.exists() and weights.with_suffix(".json").exists()):
        return None
    return SpeciesClassifier(weights)


def classify_species(img: np.ndarray, dets: list[Detection], clf: SpeciesClassifier | None):
    """Pone la especie en cada detección y devuelve la especie de la placa (o None)."""
    if clf is None or not dets:
        return dets, None
    res = clf.classify(img, [(d.x1, d.y1, d.x2, d.y2) for d in dets])
    ids = {n: i for i, n in clf.names.items()}
    out = [Detection(d.x1, d.y1, d.x2, d.y2, d.confidence, ids[name], name, prob)
           for d, (name, prob) in zip(dets, res.per_colony)]
    return out, {"identified": res.identified, "top": res.plate}


@app.on_event("startup")
def _warm_up() -> None:
    """Carga el modelo en segundo plano al arrancar: la primera foto no espera ~20 s."""
    def load() -> None:
        try:
            det = get_detector()
            det.detect(np.zeros((640, 640, 3), np.uint8))
            get_species()
            logging.getLogger("uvicorn").info("Modelo YOLO cargado")
        except Exception as e:  # sin modelo, la API sigue funcionando para consultar datos
            logging.getLogger("uvicorn").warning("No se pudo precargar el modelo: %s", e)
    if os.environ.get("BIOYOLOGIC_WARMUP", "1") == "1":
        threading.Thread(target=load, daemon=True).start()


# --------------------------------------------------------------------- utilidades
def _with_urls(a: dict) -> dict:
    aid = a["id"]
    a["image_urls"] = {k: f"/analyses/{aid}/image/{k}" for k in IMAGE_KINDS}
    a["report_url"] = f"/analyses/{aid}/report.pdf"
    return a


def _project_out(p: dict) -> dict:
    cover = p.get("cover_analysis_id")
    p["cover_url"] = f"/analyses/{cover}/image/thumb" if cover else None
    p["progress"] = min(1.0, p["analyses_count"] / max(1, p["target_samples"]))
    return p


_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    """Límite simple por IP para los análisis (el paso costoso). En memoria, por proceso."""
    if RATE_LIMIT <= 0:
        return
    # Detrás de Caddy (deploy/Caddyfile) la IP real llega en X-Real-IP, que el proxy sobrescribe
    # siempre; X-Forwarded-For no se usa porque el cliente puede falsificarlo.
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "?")
    now, q = time.monotonic(), _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "Demasiados análisis seguidos. Espera un minuto.")
    q.append(now)


def _require(obj, what: str):
    if obj is None:
        raise HTTPException(404, f"{what} no encontrado")
    return obj


def resolve_scale(image_shape, mm_per_px: float | None, plate_fraction: float | None,
                  plate_diameter_mm: float) -> float | None:
    """Escala de la foto en mm/píxel.

    Prioridad: valor explícito > círculo guía de la cámara > valor por defecto del servidor.
    `plate_fraction` es la fracción del lado corto de la foto que ocupa el diámetro
    de la placa cuando el usuario la ajusta al círculo guía.
    """
    if mm_per_px:
        return mm_per_px
    if plate_fraction:
        return plate_diameter_mm / (plate_fraction * min(image_shape[:2]))
    env = os.environ.get("BIOYOLOGIC_MM_PER_PX")
    return float(env) if env else None


# --------------------------------------------------------------------- sistema
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "model_available": _model_path().exists()}


@app.get("/about")
def about() -> dict:
    """Licencia y código fuente: la AGPL obliga a ofrecerlo a quien usa el servicio por red."""
    return {"name": "Bioyologic", "version": __version__, "license": LICENSE,
            "license_url": "https://www.gnu.org/licenses/agpl-3.0.html", "source_url": SOURCE_URL,
            "model": _model_path().name, "max_upload_mb": MAX_UPLOAD_MB,
            "datasets": [
                {"name": "Makrai et al. 2023", "license": "CC BY 4.0",
                 "url": "https://doi.org/10.6084/m9.figshare.22022540"},
                {"name": "Clinical Dataset of 19 Bacterial Colony Images (Zenodo)", "license": "CC BY 4.0",
                 "url": "https://doi.org/10.5281/zenodo.18256864"}]}


@app.get("/model")
def model_info(detector: ColonyDetector = Depends(get_detector),
               species_clf: SpeciesClassifier | None = Depends(get_species)) -> dict:
    return {"classes": detector.names, "tile": detector.tile, "confidence": detector.conf,
            "species": None if species_clf is None else sorted(species_clf.names.values())}


@app.get("/stats")
def stats(store: Store = Depends(get_store)) -> dict:
    return store.stats()


# --------------------------------------------------------------------- análisis
@app.post("/analyses", status_code=201)
async def create_analysis(
    image: UploadFile = File(..., description="Foto de la placa (JPG/PNG)"),
    sample_name: str = Form(..., min_length=1, max_length=120),
    project_id: int | None = Form(None),
    dilution: float | None = Form(None, description="Fracción sembrada, p. ej. 0.0001"),
    volume_ml: float | None = Form(None, description="Volumen sembrado en mL"),
    mm_per_px: float | None = Form(None, gt=0),
    plate_fraction: float | None = Form(None, gt=0, le=1.0),
    plate_diameter_mm: float = Form(90.0, gt=0),
    notes: str = Form(""),
    store: Store = Depends(get_store),
    detector: ColonyDetector = Depends(get_detector),
    species_clf: SpeciesClassifier | None = Depends(get_species),
    _: None = Depends(rate_limit),
) -> dict:
    if dilution is not None and dilution <= 0:
        raise HTTPException(422, "La dilución debe ser > 0 (p. ej. 1e-4)")
    if volume_ml is not None and volume_ml <= 0:
        raise HTTPException(422, "El volumen debe ser > 0")
    if project_id is not None:
        _require(store.get_project(project_id), "Proyecto")
    data = await image.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Imagen demasiado grande (máx. {MAX_UPLOAD_MB:g} MB)")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "No se pudo leer la imagen")

    scale = resolve_scale(img.shape, mm_per_px, plate_fraction, plate_diameter_mm)
    dets, species = classify_species(img, detector.detect(img), species_clf)
    result, annotated = analyze(img, dets, mm_per_px=scale, dilution=dilution,
                                volume_ml=volume_ml, species=species)
    saved = store.add_analysis(sample_name=sample_name.strip(), result=result, original=img,
                               annotated=annotated, project_id=project_id, dilution=dilution,
                               volume_ml=volume_ml, notes=notes)
    return _with_urls(saved)


@app.get("/analyses")
def list_analyses(project_id: int | None = None, q: str = "", limit: int = 50, offset: int = 0,
                  store: Store = Depends(get_store)) -> list[dict]:
    return [_with_urls(a) for a in store.list_analyses(project_id, q, min(limit, 200), offset)]


@app.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, store: Store = Depends(get_store)) -> dict:
    return _with_urls(_require(store.get_analysis(analysis_id), "Análisis"))


class AnalysisPatch(BaseModel):
    sample_name: str | None = Field(None, min_length=1, max_length=120)
    notes: str | None = None
    project_id: int | None = Field(None, description="0 = quitar del proyecto")


@app.patch("/analyses/{analysis_id}")
def update_analysis(analysis_id: int, body: AnalysisPatch, store: Store = Depends(get_store)) -> dict:
    _require(store.get_analysis(analysis_id, False), "Análisis")
    fields = body.model_dump(exclude_unset=True)
    if fields.get("project_id"):
        _require(store.get_project(fields["project_id"]), "Proyecto")
    return _with_urls(store.update_analysis(analysis_id, **fields))


@app.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: int, store: Store = Depends(get_store)) -> Response:
    _require(store.delete_analysis(analysis_id) or None, "Análisis")
    return Response(status_code=204)


@app.get("/analyses/{analysis_id}/image/{kind}")
def analysis_image(analysis_id: int, kind: str, store: Store = Depends(get_store)) -> FileResponse:
    if kind not in IMAGE_KINDS:
        raise HTTPException(404, "Tipo de imagen no válido")
    path = store.image_path(analysis_id, kind)
    if not path.exists():
        raise HTTPException(404, "Imagen no encontrada")
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/analyses/{analysis_id}/report.pdf")
def analysis_report(analysis_id: int, store: Store = Depends(get_store)) -> Response:
    a = _require(store.get_analysis(analysis_id), "Análisis")
    pdf = build_report(a, store.image_path(analysis_id, "annotated"))
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in a["sample_name"])
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="Bioyologic_{safe}.pdf"'})


# --------------------------------------------------------------------- proyectos
class ProjectIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    target_samples: int = Field(10, ge=1, le=10000)


class ProjectPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = None
    target_samples: int | None = Field(None, ge=1, le=10000)


@app.get("/projects")
def list_projects(store: Store = Depends(get_store)) -> list[dict]:
    return [_project_out(p) for p in store.list_projects()]


@app.post("/projects", status_code=201)
def create_project(body: ProjectIn, store: Store = Depends(get_store)) -> dict:
    return _project_out(store.create_project(body.name.strip(), body.description, body.target_samples))


@app.get("/projects/{project_id}")
def get_project(project_id: int, store: Store = Depends(get_store)) -> dict:
    return _project_out(_require(store.get_project(project_id), "Proyecto"))


@app.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectPatch, store: Store = Depends(get_store)) -> dict:
    _require(store.get_project(project_id), "Proyecto")
    return _project_out(store.update_project(project_id, **body.model_dump(exclude_unset=True)))


@app.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, store: Store = Depends(get_store)) -> Response:
    _require(store.delete_project(project_id) or None, "Proyecto")
    return Response(status_code=204)


# --------------------------------------------------------------------- biblioteca
@app.get("/library")
def library() -> dict:
    items = [{k: v for k, v in e.items() if k != "sections"} | {"image_url": f"/library/{e['id']}/image"}
             for e in ENTRIES]
    return {"categories": CATEGORIES, "entries": items}


@app.get("/library/{entry_id}")
def library_entry(entry_id: str) -> dict:
    e = _require(get_entry(entry_id), "Entrada")
    return e | {"image_url": f"/library/{entry_id}/image"}


@app.get("/library/{entry_id}/image")
def library_image(entry_id: str, store: Store = Depends(get_store)) -> FileResponse:
    e = _require(get_entry(entry_id), "Entrada")
    return FileResponse(entry_image(e, store.root / "library"), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


# --------------------------------------------------------------------- app web
if WEB_BUILD.exists():
    app.mount("/app", StaticFiles(directory=WEB_BUILD, html=True), name="web")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/app/")
