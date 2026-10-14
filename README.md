# Bioyologic

Sistema híbrido de conteo y caracterización de colonias bacterianas en placas de Petri a partir de una foto.

**En línea:** app web en **https://bioyologic.duckdns.org/app/** · servidor en Oracle Cloud (Always Free, Fráncfort) · app Android en `dist/Bioyologic.apk`

**Software libre** bajo [AGPL-3.0-or-later](LICENSE) · [Licencias de terceros](THIRD_PARTY_LICENSES.md) · [Ficha de los modelos](docs/model_card.md) · [Privacidad](docs/privacidad.md) · [Cómo contribuir](CONTRIBUTING.md)

**Híbrido** = un detector de aprendizaje profundo (YOLO) localiza cada colonia, y técnicas clásicas de visión por computador (segmentación por contraste de color en L\*a\*b\*, Otsu, análisis de contornos) miden su morfología dentro de cada detección.

```
 Datasets públicos (Makrai 2023 + clínico Zenodo)
          │  training/Bioyologic_entrenamiento.ipynb  (Google Colab, GPU T4)
          ▼
   models/bioyologic.pt|.onnx + bioyologic.json
          │
 ┌────────┴───────────────────────────────────────────────────────────────┐
 │ API FastAPI (backend/)                                                 │
 │  foto ─▶ detector YOLO por teselas ─▶ morfología ─▶ conteo y UFC/mL    │
 │        ─▶ SQLite (proyectos, análisis) + imágenes ─▶ reporte PDF       │
 └────────┬───────────────────────────────────────────────────────────────┘
          │ HTTP / JSON
 ┌────────┴──────────────┐
 │ App Flutter Bioyologic│  Android · iOS · Web
 └───────────────────────┘
```

## Estructura

```
Bioyologic/
├── training/            Notebooks de Google Colab: detector y clasificador de especie
├── backend/
│   ├── bioyologic/
│   │   ├── detection/   Datasets, detector por teselas, clasificador de especie, backend ONNX
│   │   ├── analysis/    Morfología, conteo/UFC y pipeline con imagen anotada
│   │   ├── api/         API REST (también sirve la app web en /app)
│   │   ├── storage.py   Base de datos SQLite + imágenes
│   │   ├── report.py    Reporte PDF
│   │   ├── library.py   Contenido de la Biblioteca
│   │   └── synthetic.py Placas sintéticas (pruebas y demo)
│   ├── scripts/         prepare_dataset, train, export_onnx, analyze_image, evaluate_counts, seed_demo
│   └── tests/
├── app/                 App Flutter
├── models/              bioyologic(.pt|.onnx) y bioyologic_species(.pt|.onnx) + .json (Git LFS)
├── deploy/              Servidor en la nube: Docker Compose + Caddy (HTTPS) + copias de seguridad
├── docs/                Documento, figuras, ficha de los modelos, privacidad y plan
└── data/                store/ (BD e imágenes), raw/samples (fotos reales de ejemplo), demo_photos/
```

## 1. Entrenar el detector en Google Colab

1. Abre https://colab.research.google.com → *Subir* → `training/Bioyologic_entrenamiento.ipynb`.
2. *Entorno de ejecución → Cambiar tipo de entorno → GPU T4*.
3. *Entorno de ejecución → Ejecutar todo* (30–60 min).
4. Se descargan `bioyologic.pt` y `bioyologic.json`: cópialos en `models/` y reinicia la API.

El notebook descarga el dataset real de Makrai *et al.* (2023): 369 placas, 24 especies y 56 865 colonias anotadas, con licencia CC BY 4.0 ([doi:10.6084/m9.figshare.22022540](https://doi.org/10.6084/m9.figshare.22022540)).

Después lo convierte a YOLO: reduce cada foto a un máximo de 2048 px, la divide en teselas de 640 px y separa los datos por placa. Entrena YOLO11s y mide el **error de conteo por placa** en test (MAE, RMSE, MAPE y Pearson). El archivo `bioyologic.json` guarda la escala usada al entrenar, para que el servidor procese las fotos exactamente igual.

Para pruebas sin datos reales se pueden generar placas sintéticas y entrenar en local (`scripts/make_synthetic.py`, `scripts/prepare_dataset.py`, `scripts/train.py`).

## 2. Backend

En desarrollo (con PyTorch, para entrenar y exportar):

```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/python -m pip install -r backend/requirements.txt
.venv/Scripts/python backend/scripts/seed_demo.py --reset     # datos de demostración (opcional)
.venv/Scripts/python -m uvicorn bioyologic.api.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

La documentación interactiva de la API está en http://localhost:8000/docs.

**Servidor ligero (ONNX):** `python backend/scripts/export_onnx.py` crea `models/*.onnx`. Si existen, la API los usa en lugar de los `.pt`, con los mismos resultados. Para producción basta `pip install -r backend/requirements-server.txt`, sin PyTorch ni Ultralytics: unos 300 MB en lugar de 1,8 GB.

**En la nube:** [`deploy/README.md`](deploy/README.md) explica cómo desplegarlo en Oracle Cloud Always Free (gratis) con Docker, HTTPS automático y copias de seguridad diarias.

| Endpoint | Descripción |
|---|---|
| `POST /analyses` | Foto + `sample_name`, `project_id`, `dilution`, `volume_ml`, `plate_fraction` → analiza y guarda |
| `GET /analyses?project_id=&q=` · `GET/PATCH/DELETE /analyses/{id}` | Historial, detalle, edición |
| `GET /analyses/{id}/image/{original\|annotated\|thumb}` | Imágenes |
| `GET /analyses/{id}/report.pdf` | Reporte PDF |
| `GET/POST /projects` · `GET/PATCH/DELETE /projects/{id}` | Proyectos con progreso |
| `GET /library` · `GET /library/{id}` | Biblioteca (microorganismos, protocolos, guías) |
| `GET /stats` · `GET /health` · `GET /model` | Resumen y estado |
| `GET /about` | Licencia, enlace al código fuente y datasets (AGPL-3.0, sección 13) |

**Escala en mm:** la cámara de la app muestra un círculo guía que ocupa el 80 % del lado corto de la foto. Si la placa (90 mm) se ajusta a él, el servidor calcula los mm por píxel (`plate_fraction`). Para fotos de galería, la app pregunta si la placa ocupa toda la foto.

## 3. App Flutter

```bash
cd app
flutter pub get
flutter run                                   # Android/iOS (emulador: servidor http://10.0.2.2:8000)
flutter build web --base-href /app/           # versión web, servida por la API en http://localhost:8000/app
flutter build apk --release --dart-define=BIOYOLOGIC_SERVER=https://mi-servidor --dart-define=BIOYOLOGIC_SOURCE=https://url-del-repo
```

Pantallas: inicio con splash, bienvenida, inicio con resumen, cámara con círculo guía, nueva muestra, resultados (Resumen · Colonias · Morfología, y descarga del reporte), análisis, proyectos, biblioteca, perfil y configuración.

En un móvil real, configura el servidor en *Perfil → Configuración → Servidor*: `http://<IP del PC>:8000` en la misma red Wi-Fi, o la dirección `https://` del servidor en la nube.

## Qué mide

| Descriptor | Definición |
|---|---|
| Conteo total y por clase | Detecciones fusionadas entre teselas (NMS por intersección/área menor + unión de cajas) |
| Estado de la placa | contable (30–300), pocas (<30), incontable (>300) |
| UFC/mL | colonias / (dilución × volumen sembrado) |
| Diámetro, área | Círculo de igual área, en mm si se conoce la escala |
| Circularidad · aspecto · solidez | 4πA/P² · eje mayor/menor · A/A(envolvente convexa) |
| Forma | puntiforme (<1 mm), circular, irregular |
| Borde | entero (liso), ondulado, lobulado |
| Color | RGB, L\*a\*b\* y nombre (beige, amarillo, blanco…), contraste ΔE con el agar |

La elevación no se puede medir con una foto cenital 2D.

## Identificación de especie (opcional)

Segunda etapa: un clasificador YOLO11s-cls asigna cada colonia detectada a una de 37 especies, y la especie de la placa sale del promedio de sus colonias. En test acierta el 96,4 % de las colonias y las 134 placas.

- Entrenamiento: `training/Bioyologic_especies.ipynb` en Colab. Descarga `bioyologic_species.zip`; descomprímelo en `models/`.
- El servidor lo carga solo si existen `models/bioyologic_species.onnx` o `.pt`, y su `.json`. Sin él, la app muestra solo la detección.
- Correspondencia de códigos con especies: `training/species_map.json`, tomada de las tablas 1 de ambos artículos.
- **Límite:** cada especie de los datasets se cultivó en un medio concreto, así que el modelo puede apoyarse en el color del agar. Con fotos de otro laboratorio la especie es orientativa.

## Pruebas

```bash
cd backend && ../.venv/Scripts/python -m pytest -q
cd app && flutter test
.venv/Scripts/python training/test_notebook.py     # prueba local de las celdas del notebook
```

## Licencia

Copyright © 2026 Juan José Martínez.

Bioyologic es software libre: puedes redistribuirlo y modificarlo bajo los términos de la **GNU Affero General Public License** versión 3 o posterior, publicada por la Free Software Foundation. Se distribuye con la esperanza de que sea útil, pero **sin ninguna garantía**. Consulta el archivo [LICENSE](LICENSE).

La AGPL-3.0 viene de Ultralytics YOLO e implica que quien ofrezca Bioyologic, modificado o no, como servicio en red debe dar acceso a su código fuente. La API lo indica en `GET /about` y la app en *Perfil → Acerca de*.

Los modelos se entrenaron con datasets CC BY 4.0. Las citas están en [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) y en [CITATION.cff](CITATION.cff). **Bioyologic no es un dispositivo médico**: sus resultados son orientativos.
