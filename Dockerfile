# Servidor de Bioyologic con los modelos ONNX (sin PyTorch). Funciona en x86-64 y ARM64
# (Oracle Cloud Ampere). Antes de construir:
#   python backend/scripts/export_onnx.py          -> models/*.onnx
#   cd app && flutter build web --base-href /app/  -> app/build/web (opcional)
# Construir y probar:
#   docker build -t bioyologic .
#   docker run -p 8000:8000 -v bioyologic-data:/data bioyologic
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BIOYOLOGIC_DATA=/data \
    BIOYOLOGIC_WEB=/srv/web

WORKDIR /srv
COPY backend/requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY backend/bioyologic backend/bioyologic
COPY models/*.onnx models/*.json models/
COPY app/build/web web
COPY LICENSE .

RUN useradd --create-home --uid 1000 bioyologic && mkdir -p /data && chown bioyologic /data
USER bioyologic
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "bioyologic.api.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
