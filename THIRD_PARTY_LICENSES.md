# Licencias de terceros

Bioyologic se distribuye bajo **AGPL-3.0-or-later** (archivo `LICENSE`). Todas las piezas que usa tienen licencias compatibles con ella.

## Software

| Componente | Uso | Licencia |
|---|---|---|
| [Ultralytics YOLO](https://github.com/ultralytics/ultralytics) | Entrenamiento y detector/clasificador | AGPL-3.0 |
| [PyTorch](https://pytorch.org) | Entrenamiento (no hace falta en el servidor ONNX) | BSD-3-Clause |
| [ONNX Runtime](https://onnxruntime.ai) | Inferencia en el servidor | MIT |
| [ONNX](https://onnx.ai), [onnxslim](https://github.com/inisis/OnnxSlim) | Exportación de modelos | Apache-2.0, MIT |
| [OpenCV](https://opencv.org) | Segmentación y morfología | Apache-2.0 |
| [NumPy](https://numpy.org) | Cálculo numérico | BSD-3-Clause |
| [FastAPI](https://fastapi.tiangolo.com), [Pydantic](https://docs.pydantic.dev) | API REST | MIT |
| [Uvicorn](https://www.uvicorn.org) | Servidor HTTP | BSD-3-Clause |
| [python-multipart](https://github.com/Kludex/python-multipart) | Subida de fotos | Apache-2.0 |
| [ReportLab](https://www.reportlab.com/opensource/) (edición libre) | Informe PDF | BSD |
| [PyYAML](https://pyyaml.org) | Configuración del entrenamiento local | MIT |
| [PyMuPDF](https://pymupdf.readthedocs.io) | Solo para generar figuras del documento (`docs/make_figures.py`) | AGPL-3.0 |
| [Flutter](https://flutter.dev) y Dart SDK | App móvil | BSD-3-Clause |
| Paquetes Flutter: `http`, `intl`, `camera`, `image_picker`, `shared_preferences`, `url_launcher`, `cupertino_icons` | App móvil | BSD-3-Clause |
| [Caddy](https://caddyserver.com) | Proxy HTTPS del despliegue (`deploy/`) | Apache-2.0 |

## Datos

Las fotos de los datasets **no** se incluyen en el repositorio; los notebooks de `training/` las descargan de su fuente original.
Las tres fotos de ejemplo de `data/demo_photos/reales/` provienen de estos datasets y se redistribuyen con su atribución.

| Dataset | Uso | Licencia |
|---|---|---|
| Makrai, L. *et al.* (2023). *Scientific Data* 10:497. Figshare. [doi:10.6084/m9.figshare.22022540](https://doi.org/10.6084/m9.figshare.22022540) | Entrenamiento del detector y del clasificador | CC BY 4.0 |
| *Clinical Dataset of 19 Bacterial Colony Images.* Zenodo. [doi:10.5281/zenodo.18256864](https://doi.org/10.5281/zenodo.18256864) | Entrenamiento del detector y del clasificador | CC BY 4.0 |

## Modelos entrenados

`bioyologic.pt` / `.onnx` (detector) y `bioyologic_species.pt` / `.onnx` (clasificador de especie) se derivan de pesos preentrenados de Ultralytics y de los datasets anteriores. Se distribuyen bajo **AGPL-3.0**, con la atribución CC BY 4.0 a los datasets. Detalles en [`docs/model_card.md`](docs/model_card.md).
