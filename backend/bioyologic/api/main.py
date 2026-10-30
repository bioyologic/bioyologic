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
    BIOYOLOGIC_LOGIN_LIMIT    intentos de inicio de sesión o registro por minuto y por IP (por defecto 10)
    BIOYOLOGIC_CORS_ORIGINS   orígenes permitidos separados por comas (por defecto *)
    BIOYOLOGIC_SOURCE_URL     URL del código fuente (AGPL-3.0, sección 13)
    BIOYOLOGIC_CONTACT_EMAIL  correo del responsable del tratamiento de datos (Ley 1581 de 2012)
    BIOYOLOGIC_SMTP_*         envío de correos (ver bioyologic/mailer.py). Con SMTP configurado, las cuentas
                              nuevas deben verificar su correo y se puede recuperar la contraseña.

Cuentas: cada usuario solo ve sus proyectos y análisis. La app envía `Authorization: Bearer <token>`;
las imágenes y el PDF de un análisis se piden con la clave secreta `?key=` que viene en sus URLs.

Si existe app/build/web (flutter build web), la app se sirve en /app.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import threading
import time
import unicodedata
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__, mailer
from ..analysis.counting import combine_plates
from ..analysis.pipeline import analyze, recount
from ..analysis.quality import assess
from ..export import build_csv
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
LOGIN_LIMIT = int(os.environ.get("BIOYOLOGIC_LOGIN_LIMIT", "10"))
SOURCE_URL = os.environ.get("BIOYOLOGIC_SOURCE_URL", "https://github.com/bioyologic/bioyologic")
CONTACT_EMAIL = os.environ.get("BIOYOLOGIC_CONTACT_EMAIL", "")
LICENSE = "AGPL-3.0-or-later"
# Versión de la política de privacidad que el usuario acepta al registrarse.
PRIVACY_VERSION = "2026-10"

app = FastAPI(title="Bioyologic API", version=__version__,
              description="Conteo y caracterización de colonias bacterianas en placas de Petri. "
                          f"Software libre ({LICENSE}).",
              license_info={"name": LICENSE, "url": "https://www.gnu.org/licenses/agpl-3.0.html"})
app.add_middleware(CORSMiddleware, allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Bioyologic-Reason"],
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
    """URLs de imágenes y PDF con la clave secreta del análisis (no se pueden adivinar)."""
    aid, key = a["id"], a.pop("access_key")
    a.pop("user_id", None)
    version = a.pop("annotated_version", 0)
    a["image_urls"] = {k: f"/analyses/{aid}/image/{k}?key={key}" for k in IMAGE_KINDS}
    if version:
        a["image_urls"]["annotated"] += f"&v={version}"
    a["report_url"] = f"/analyses/{aid}/report/{quote(pdf_name(a['sample_name']))}?key={key}"
    return a


def _project_out(p: dict) -> dict:
    cover, key = p.pop("cover_analysis_id", None), p.pop("cover_access_key", None)
    p.pop("user_id", None)
    p["cover_url"] = f"/analyses/{cover}/image/thumb?key={key}" if cover else None
    p["progress"] = min(1.0, p["analyses_count"] / max(1, p["target_samples"]))
    return p


_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def _limit(request: Request, bucket: str, limit: int, message: str) -> None:
    """Límite simple por IP y por tipo de petición. En memoria, por proceso."""
    if limit <= 0:
        return
    # Detrás de Caddy (deploy/Caddyfile) la IP real llega en X-Real-IP, que el proxy sobrescribe
    # siempre; X-Forwarded-For no se usa porque el cliente puede falsificarlo.
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "?")
    now, q = time.monotonic(), _hits[(bucket, ip)]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, message)
    q.append(now)


def rate_limit(request: Request) -> None:
    """Los análisis son el paso costoso."""
    _limit(request, "analyses", RATE_LIMIT, "Demasiados análisis seguidos. Espera un minuto.")


def login_limit(request: Request) -> None:
    """Frena los intentos de adivinar contraseñas."""
    _limit(request, "auth", LOGIN_LIMIT, "Demasiados intentos. Espera un minuto.")


_bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 store: Store = Depends(get_store)) -> dict:
    user = store.session_user(creds.credentials) if creds else None
    if user is None:
        raise HTTPException(401, "Inicia sesión para continuar", headers={"WWW-Authenticate": "Bearer"})
    return user


def verified_user(user: dict = Depends(current_user)) -> dict:
    """Cuenta con el correo verificado (solo se exige si el servidor puede enviar correos)."""
    if mailer.configured() and not user["email_verified"]:
        raise HTTPException(403, "Verifica tu correo para continuar",
                            headers={"X-Bioyologic-Reason": "email-not-verified"})
    return user


def _user_out(user: dict) -> dict:
    return user | {"verification_required": mailer.configured()}


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
            "privacy_version": PRIVACY_VERSION, "contact_email": CONTACT_EMAIL,
            "datasets": [
                {"name": "Makrai, L. et al. (2023). Annotated dataset for deep-learning-based bacterial "
                         "colony detection", "license": "CC BY 4.0",
                 "url": "https://doi.org/10.6084/m9.figshare.22022540"},
                {"name": "Du, J. (2026). Clinical Dataset of 19 Bacterial Colony Images", "license": "CC BY 4.0",
                 "url": "https://doi.org/10.5281/zenodo.18256864"}]}


@app.get("/model")
def model_info(detector: ColonyDetector = Depends(get_detector),
               species_clf: SpeciesClassifier | None = Depends(get_species)) -> dict:
    return {"classes": detector.names, "tile": detector.tile, "confidence": detector.conf,
            "species": None if species_clf is None else sorted(species_clf.names.values())}


@app.get("/stats")
def stats(store: Store = Depends(get_store), user: dict = Depends(verified_user)) -> dict:
    return store.stats(user["id"])


# --------------------------------------------------------------------- cuentas
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=120)
    role: str = Field("", max_length=120)
    institution: str = Field("", max_length=160)
    accept_privacy: bool = Field(..., description="Autorización del tratamiento de datos (Ley 1581 de 2012)")


class LoginIn(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=128)


class ProfilePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    role: str | None = Field(None, max_length=120)
    institution: str | None = Field(None, max_length=160)


class PasswordChange(BaseModel):
    current_password: str = Field(..., max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class DeleteAccount(BaseModel):
    password: str = Field(..., max_length=128)


class CodeIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=12)


class ForgotIn(BaseModel):
    email: str = Field(..., max_length=254)


class ResetIn(BaseModel):
    email: str = Field(..., max_length=254)
    code: str = Field(..., min_length=4, max_length=12)
    new_password: str = Field(..., min_length=8, max_length=128)


VERIFY_MINUTES = 30
RESET_MINUTES = 15


def _session(store: Store, user: dict) -> dict:
    return {"token": store.create_session(user["id"]), "user": _user_out(user)}


def _send_code(tasks: BackgroundTasks, store: Store, user: dict, purpose: str, minutes: int) -> None:
    code = store.new_code(user["id"], purpose, minutes)
    subject, text = mailer.code_email(code, purpose, minutes)
    tasks.add_task(mailer.send, user["email"], subject, text)  # sin hacer esperar a la app


@app.post("/auth/register", status_code=201)
def register(body: RegisterIn, tasks: BackgroundTasks, store: Store = Depends(get_store),
             _: None = Depends(login_limit)) -> dict:
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Correo electrónico no válido")
    if not body.accept_privacy:
        raise HTTPException(422, "Debes autorizar el tratamiento de tus datos para crear la cuenta")
    user = store.create_user(email=email, password=body.password, name=body.name.strip(),
                             role=body.role.strip(), institution=body.institution.strip(),
                             consent_version=PRIVACY_VERSION)
    if user is None:
        raise HTTPException(409, "Ya existe una cuenta con ese correo")
    if mailer.configured():
        _send_code(tasks, store, user, "verify", VERIFY_MINUTES)
    return _session(store, user)


@app.post("/auth/login")
def login(body: LoginIn, store: Store = Depends(get_store), _: None = Depends(login_limit)) -> dict:
    user = store.authenticate(body.email.strip().lower(), body.password)
    if user is None:
        raise HTTPException(401, "Correo o contraseña incorrectos")
    return _session(store, user)


@app.post("/auth/logout", status_code=204)
def logout(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
           store: Store = Depends(get_store)) -> Response:
    if creds:
        store.delete_session(creds.credentials)
    return Response(status_code=204)


@app.get("/auth/me")
def me(user: dict = Depends(current_user)) -> dict:
    return _user_out(user)


@app.patch("/auth/me")
def update_me(body: ProfilePatch, store: Store = Depends(get_store), user: dict = Depends(current_user)) -> dict:
    fields = {k: v.strip() for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    return _user_out(store.update_user(user["id"], **fields))


@app.post("/auth/verify")
def verify_email(body: CodeIn, store: Store = Depends(get_store), user: dict = Depends(current_user),
                 _: None = Depends(login_limit)) -> dict:
    """Confirma el correo con el código de 6 dígitos que se envió al registrarse."""
    if not user["email_verified"]:
        if not store.check_code(user["id"], "verify", body.code):
            raise HTTPException(400, "Código incorrecto o vencido. Pide uno nuevo.")
        store.set_verified(user["id"])
    return _user_out(store.get_user(user["id"]))


@app.post("/auth/verify/resend", status_code=204)
def resend_verification(tasks: BackgroundTasks, store: Store = Depends(get_store),
                        user: dict = Depends(current_user), _: None = Depends(login_limit)) -> Response:
    if not mailer.configured():
        raise HTTPException(503, "El servidor no tiene configurado el envío de correos")
    if not user["email_verified"]:
        _send_code(tasks, store, user, "verify", VERIFY_MINUTES)
    return Response(status_code=204)


@app.post("/auth/password/forgot", status_code=204)
def forgot_password(body: ForgotIn, tasks: BackgroundTasks, store: Store = Depends(get_store),
                    _: None = Depends(login_limit)) -> Response:
    """Envía un código para cambiar la contraseña. Responde igual exista o no la cuenta."""
    if not mailer.configured():
        contacto = f" Escribe a {CONTACT_EMAIL}." if CONTACT_EMAIL else ""
        raise HTTPException(503, "La recuperación por correo no está disponible en este servidor." + contacto)
    user = store.user_by_email(body.email.strip().lower())
    if user is not None:
        _send_code(tasks, store, user, "reset", RESET_MINUTES)
    return Response(status_code=204)


@app.post("/auth/password/reset")
def reset_password(body: ResetIn, store: Store = Depends(get_store), _: None = Depends(login_limit)) -> dict:
    """Cambia la contraseña con el código del correo; cierra las demás sesiones y entra de nuevo."""
    user = store.user_by_email(body.email.strip().lower())
    if user is None or not store.check_code(user["id"], "reset", body.code):
        raise HTTPException(400, "Código incorrecto o vencido. Pide uno nuevo.")
    store.set_password(user["id"], body.new_password)
    store.set_verified(user["id"])  # quien recibió el código controla el correo
    return _session(store, store.get_user(user["id"]))


@app.post("/auth/me/password", status_code=204)
def change_password(body: PasswordChange, store: Store = Depends(get_store),
                    user: dict = Depends(current_user), _: None = Depends(login_limit)) -> Response:
    if store.authenticate(user["email"], body.current_password) is None:
        raise HTTPException(403, "La contraseña actual no es correcta")
    store.set_password(user["id"], body.new_password)  # cierra todas las sesiones
    return Response(status_code=204)


@app.delete("/auth/me", status_code=204)
def delete_me(body: DeleteAccount, store: Store = Depends(get_store),
              user: dict = Depends(current_user), _: None = Depends(login_limit)) -> Response:
    """Derecho de supresión: borra la cuenta y todos sus datos, fotos incluidas."""
    if store.authenticate(user["email"], body.password) is None:
        raise HTTPException(403, "La contraseña no es correcta")
    store.delete_user(user["id"])
    return Response(status_code=204)


# Enlaces de descarga de un solo uso: el navegador los abre sin poder enviar el token.
_export_links: dict[str, tuple[int, float]] = {}


@app.post("/auth/me/export-link")
def export_link(user: dict = Depends(current_user)) -> dict:
    """Derecho de acceso: enlace de 5 minutos para descargar todos los datos del usuario."""
    now = time.monotonic()
    for t, (_, exp) in list(_export_links.items()):
        if exp < now:
            del _export_links[t]
    token = secrets.token_urlsafe(24)
    _export_links[token] = (user["id"], now + 300)
    return {"url": f"/auth/me/export?token={token}"}


@app.get("/auth/me/export")
def export_data(token: str, store: Store = Depends(get_store)) -> JSONResponse:
    uid, exp = _export_links.pop(token, (None, 0.0))
    if uid is None or exp < time.monotonic():
        raise HTTPException(404, "Enlace caducado. Vuelve a pedirlo desde la app.")
    data = store.export_user(uid)
    for a in data["analyses"]:
        _with_urls(a)
    for p in data["projects"]:
        _project_out(p)
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="bioyologic_mis_datos.json"'})


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
    sample_group: str = Form("", max_length=120, description="Muestra a la que pertenece la placa (diluciones/réplicas)"),
    store: Store = Depends(get_store),
    detector: ColonyDetector = Depends(get_detector),
    species_clf: SpeciesClassifier | None = Depends(get_species),
    user: dict = Depends(verified_user),
    _: None = Depends(rate_limit),
) -> dict:
    if dilution is not None and dilution <= 0:
        raise HTTPException(422, "La dilución debe ser > 0 (p. ej. 1e-4)")
    if volume_ml is not None and volume_ml <= 0:
        raise HTTPException(422, "El volumen debe ser > 0")
    if project_id is not None:
        _require(store.get_project(project_id, user["id"]), "Proyecto")
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
    result["quality"] = assess(img)
    saved = store.add_analysis(user_id=user["id"], sample_name=sample_name.strip(), result=result,
                               original=img, annotated=annotated, project_id=project_id,
                               dilution=dilution, volume_ml=volume_ml, notes=notes, sample_group=sample_group)
    return _with_urls(saved)


@app.get("/analyses")
def list_analyses(project_id: int | None = None, q: str = "", limit: int = 50, offset: int = 0,
                  store: Store = Depends(get_store), user: dict = Depends(verified_user)) -> list[dict]:
    return [_with_urls(a) for a in store.list_analyses(user["id"], project_id, q, min(limit, 200), offset)]


@app.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, store: Store = Depends(get_store), user: dict = Depends(verified_user)) -> dict:
    return _with_urls(_require(store.get_analysis(analysis_id, user["id"]), "Análisis"))


class AnalysisPatch(BaseModel):
    sample_name: str | None = Field(None, min_length=1, max_length=120)
    sample_group: str | None = Field(None, max_length=120, description="'' = quitar de la muestra")
    notes: str | None = None
    project_id: int | None = Field(None, description="0 = quitar del proyecto")


@app.patch("/analyses/{analysis_id}")
def update_analysis(analysis_id: int, body: AnalysisPatch, store: Store = Depends(get_store),
                    user: dict = Depends(verified_user)) -> dict:
    _require(store.get_analysis(analysis_id, user["id"], False), "Análisis")
    fields = body.model_dump(exclude_unset=True)
    if fields.get("project_id"):
        _require(store.get_project(fields["project_id"], user["id"]), "Proyecto")
    return _with_urls(store.update_analysis(analysis_id, user["id"], **fields))


class Added(BaseModel):
    x: float = Field(..., ge=0)
    y: float = Field(..., ge=0)
    r: float = Field(..., gt=1)


class Correction(BaseModel):
    removed: list[int] = Field(default_factory=list, max_length=5000)
    added: list[Added] = Field(default_factory=list, max_length=2000)


@app.put("/analyses/{analysis_id}/colonies")
def correct_colonies(analysis_id: int, body: Correction, store: Store = Depends(get_store),
                     user: dict = Depends(verified_user)) -> dict:
    """Corrección manual del conteo: quitar detecciones del modelo y agregar colonias que no vio.

    Se aplica siempre sobre las detecciones originales (listas vacías = deshacer la corrección), recalcula
    el conteo, las UFC/mL y la imagen anotada, y queda registrada en el análisis y en el reporte.
    """
    a = _require(store.get_analysis(analysis_id, user["id"], False), "Análisis")
    result = store.result_of(analysis_id, user["id"])
    image = cv2.imread(str(store.image_path(analysis_id, "original")), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(409, "No se encontró la foto original de este análisis")
    h, w = image.shape[:2]
    if any(c.x > w or c.y > h or c.r > min(w, h) / 4 for c in body.added):
        raise HTTPException(422, "Hay colonias agregadas fuera de la foto o demasiado grandes")
    detected_ids = {c["id"] for c in (result.get("detected_colonies") or result["colonies"]) if not c.get("manual")}
    if set(body.removed) - detected_ids:
        raise HTTPException(422, "Hay colonias para quitar que no existen en este análisis")
    new, annotated = recount(image, result, set(body.removed), [(c.x, c.y, c.r) for c in body.added],
                             a["dilution"], a["volume_ml"], by=user["name"])
    return _with_urls(store.save_result(analysis_id, user["id"], new, annotated))


@app.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: int, store: Store = Depends(get_store),
                    user: dict = Depends(verified_user)) -> Response:
    _require(store.delete_analysis(analysis_id, user["id"]) or None, "Análisis")
    return Response(status_code=204)


class DeleteMany(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=1000)


@app.post("/analyses/delete")
def delete_analyses(body: DeleteMany, store: Store = Depends(get_store), user: dict = Depends(verified_user)) -> dict:
    """Borra varios análisis a la vez (con sus fotos). Solo los del usuario: los ajenos se ignoran."""
    borrados = sum(store.delete_analysis(aid, user["id"]) for aid in set(body.ids))
    return {"deleted": borrados}


@app.get("/analyses/{analysis_id}/image/{kind}")
def analysis_image(analysis_id: int, kind: str, key: str = "", store: Store = Depends(get_store)) -> FileResponse:
    if kind not in IMAGE_KINDS:
        raise HTTPException(404, "Tipo de imagen no válido")
    expected = store.access_key(analysis_id)
    path = store.image_path(analysis_id, kind)
    # Misma respuesta si el análisis no existe o la clave no coincide: no revela qué ids existen.
    if not (expected and secrets.compare_digest(expected.encode(), key.encode())) or not path.exists():
        raise HTTPException(404, "Imagen no encontrada")
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=31536000, immutable"})


_NO_VALIDOS = set('\\/:*?"<>|')


def pdf_name(sample_name: str) -> str:
    """Nombre del archivo PDF = nombre del análisis ("prueba e coli" -> "prueba e coli.pdf").

    Solo se quitan los caracteres que Windows, Android o macOS no aceptan en un nombre de archivo.
    """
    limpio = "".join(" " if ch in _NO_VALIDOS or ord(ch) < 32 else ch for ch in sample_name)
    limpio = " ".join(limpio.split()).strip(" .")[:100] or "analisis"
    return f"{limpio}.pdf"


def _pdf_disposition(sample_name: str) -> str:
    """Cabecera de descarga. Las cabeceras HTTP solo admiten ASCII: un nombre sin tildes para todos los
    navegadores y el nombre exacto, con tildes, en `filename*` (RFC 6266) para los que lo entienden."""
    nombre = pdf_name(sample_name)
    ascii_ = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().replace('"', "") or "analisis.pdf"
    return f"inline; filename=\"{ascii_}\"; filename*=UTF-8''{quote(nombre)}"


@app.get("/analyses/{analysis_id}/report/{filename}")
@app.get("/analyses/{analysis_id}/report.pdf")
def analysis_report(analysis_id: int, key: str = "", store: Store = Depends(get_store)) -> Response:
    a = _require(store.get_analysis_by_key(analysis_id, key), "Análisis")
    pdf = build_report(a, store.image_path(analysis_id, "annotated"))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": _pdf_disposition(a["sample_name"])})


# --------------------------------------------------------------------- muestras (varias placas)
def _samples(store: Store, user_id: int, project_id: int | None = None, group: str | None = None) -> list[dict]:
    grupos: dict[tuple, list[dict]] = {}
    for pl in store.sample_plates(user_id, project_id, group):
        grupos.setdefault((pl["project_id"], pl["sample_group"]), []).append(pl)
    out = []
    for (pid, nombre), placas in grupos.items():
        res = combine_plates(placas)
        usadas = set(res["used"])
        out.append({
            "name": nombre, "project_id": pid, "project_name": placas[0]["project_name"],
            "last_at": max(pl["created_at"] for pl in placas),
            "result": res,
            "plates": [{"id": pl["id"], "sample_name": pl["sample_name"], "created_at": pl["created_at"],
                        "dilution": pl["dilution"], "volume_ml": pl["volume_ml"], "total": pl["total"],
                        "status": pl["status"], "cfu_per_ml": pl["cfu_per_ml"], "used": pl["id"] in usadas,
                        "thumb_url": f"/analyses/{pl['id']}/image/thumb?key={pl['access_key']}"} for pl in placas],
        })
    return sorted(out, key=lambda m: m["last_at"], reverse=True)


@app.get("/samples")
def list_samples(project_id: int | None = None, name: str | None = None, store: Store = Depends(get_store),
                 user: dict = Depends(verified_user)) -> list[dict]:
    """Muestras con varias placas (diluciones seriadas y réplicas) y su UFC/mL combinada (ISO 4833-1)."""
    return _samples(store, user["id"], project_id, name)


@app.get("/sample-groups")
def sample_groups(project_id: int | None = None, store: Store = Depends(get_store),
                  user: dict = Depends(verified_user)) -> list[str]:
    """Nombres de muestra ya usados, para sugerirlos al crear un análisis."""
    return store.groups(user["id"], project_id)


class ExportIn(BaseModel):
    project_id: int | None = None


# Enlaces de un solo uso (5 min) para descargar el CSV desde el navegador, que no puede enviar el token.
_csv_links: dict[str, tuple[int, int | None, float]] = {}


@app.post("/export-link")
def csv_export_link(body: ExportIn, store: Store = Depends(get_store), user: dict = Depends(verified_user)) -> dict:
    """Enlace para descargar en CSV (Excel) los análisis de un proyecto, o todos si no se indica proyecto."""
    nombre = "Bioyologic - todos los análisis"
    if body.project_id is not None:
        nombre = f"Bioyologic - {_require(store.get_project(body.project_id, user['id']), 'Proyecto')['name']}"
    now = time.monotonic()
    for t, (_, _, exp) in list(_csv_links.items()):
        if exp < now:
            del _csv_links[t]
    token = secrets.token_urlsafe(24)
    _csv_links[token] = (user["id"], body.project_id, now + 300)
    return {"url": f"/export/{quote(pdf_name(nombre)[:-4] + '.csv')}?token={token}"}


@app.get("/export/{filename}")
def csv_export(filename: str, token: str, store: Store = Depends(get_store)) -> Response:
    uid, project_id, exp = _csv_links.pop(token, (None, None, 0.0))
    if uid is None or exp < time.monotonic():
        raise HTTPException(404, "Enlace caducado. Vuelve a pedirlo desde la app.")
    analyses = store.list_analyses(uid, project_id, limit=1_000_000)
    muestras = {(m["project_id"], m["name"]): m["result"] for m in _samples(store, uid, project_id)}
    nombre = filename if filename.lower().endswith(".csv") else "bioyologic.csv"
    ascii_ = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().replace('"', "") or "bioyologic.csv"
    return Response(build_csv(analyses, muestras), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(nombre)}"})


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
def list_projects(store: Store = Depends(get_store), user: dict = Depends(verified_user)) -> list[dict]:
    return [_project_out(p) for p in store.list_projects(user["id"])]


@app.post("/projects", status_code=201)
def create_project(body: ProjectIn, store: Store = Depends(get_store), user: dict = Depends(verified_user)) -> dict:
    return _project_out(store.create_project(user["id"], body.name.strip(), body.description, body.target_samples))


@app.get("/projects/{project_id}")
def get_project(project_id: int, store: Store = Depends(get_store), user: dict = Depends(verified_user)) -> dict:
    return _project_out(_require(store.get_project(project_id, user["id"]), "Proyecto"))


@app.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectPatch, store: Store = Depends(get_store),
                   user: dict = Depends(verified_user)) -> dict:
    _require(store.get_project(project_id, user["id"]), "Proyecto")
    return _project_out(store.update_project(project_id, user["id"], **body.model_dump(exclude_unset=True)))


@app.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, store: Store = Depends(get_store), user: dict = Depends(verified_user)) -> Response:
    _require(store.delete_project(project_id, user["id"]) or None, "Proyecto")
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
