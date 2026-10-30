# Bioyologic

**Conteo y caracterización de bacterias desde tu celular.** Bioyologic cuenta las colonias de una placa de Petri a partir de una foto, mide cada una (tamaño, forma, borde y color), calcula las UFC/mL y estima la especie.

**Pruébalo:** https://bioyologic.duckdns.org · app Android: `dist/Bioyologic.apk` (se genera con `flutter build apk`)

Software libre bajo [AGPL-3.0-or-later](LICENSE) · [Ficha de los modelos](MODEL_CARD.md) · [Privacidad](PRIVACIDAD.md) · [Licencias de terceros](THIRD_PARTY_LICENSES.md) · [Cómo contribuir](CONTRIBUTING.md)

Proyecto de Diseño en Bioingeniería, Pontificia Universidad Javeriana · Laura Suárez · Juan José Martínez · Samuel Núñez

---

## Qué hace

| Función | Detalle |
|---|---|
| **Conteo automático** | Detector YOLO11s por teselas: encuentra también las colonias pequeñas y separa las que se tocan |
| **Caracterización** | Por colonia: diámetro en mm, circularidad, solidez, forma, borde y color (L\*a\*b\*, Otsu y contornos) |
| **UFC/mL** | De cada placa, y **de la muestra completa** con varias diluciones y réplicas según **ISO 4833-1** |
| **Especie probable** | Clasificador YOLO11s-cls de 37 especies (orientativo) |
| **Corrección manual** | Quitar detecciones erróneas y agregar colonias que faltaron; queda registrada (trazabilidad) |
| **Calidad de la foto** | Avisa si está borrosa, oscura, con reflejos, descentrada o lejos |
| **Informe PDF** | Con la imagen anotada, el resumen, la especie y el detalle de cada colonia |
| **Exportar a Excel** | CSV por proyecto o de todos los análisis |
| **Cuentas privadas** | Cada usuario ve solo sus datos; verificación del correo y recuperación de contraseña (Ley 1581 de 2012) |
| **Organización** | Proyectos con gráfico de UFC/mL por muestra, historial con búsqueda, borrado de uno o varios análisis, biblioteca de microorganismos y protocolos |

**Resultados en test** (133 placas que el modelo nunca vio): error de conteo **MAPE 2,6 %**, mAP50 0,969, precisión 0,939, recall 0,936; especie correcta en el 96,4 % de las colonias y en las 134 placas; 3–7 s por foto en CPU. Detalles y límites en la [ficha de los modelos](MODEL_CARD.md).

**Bioyologic no es un dispositivo médico:** es una herramienta de apoyo y sus resultados deben ser revisados por personal cualificado.

## Cómo funciona

```
 Datasets públicos: Makrai et al. (2023) + Du (2026), CC BY 4.0
          │  training/*.ipynb  (Google Colab, GPU T4)
          ▼
 models/bioyologic.onnx  ·  models/bioyologic_species.onnx
          │
 ┌────────┴──────────────────────────────────────────────────────────────────┐
 │ Servidor FastAPI (backend/) · Docker · Caddy (HTTPS) · Oracle Cloud        │
 │  foto ─▶ calidad ─▶ YOLO por teselas ─▶ fusión ─▶ segmentación y medida    │
 │       ─▶ especie ─▶ UFC/mL ─▶ SQLite + imágenes ─▶ PDF · CSV                │
 └────────┬──────────────────────────────────────────────────────────────────┘
          │ HTTPS + token de sesión
 ┌────────┴──────────────────┐
 │ App Flutter (Android, web) │
 └───────────────────────────┘
```

## Estructura

```
Bioyologic/
├── app/          App Flutter (Android y web)
├── backend/      Servidor: API, análisis de imagen, base de datos, PDF, correos y pruebas
├── training/     Notebooks de Google Colab para entrenar el detector y el clasificador
├── models/       Modelos entrenados (.onnx para el servidor, .pt para reentrenar) · Git LFS
├── deploy/       Despliegue en la nube: Docker Compose, Caddy, copias de seguridad, actualización
├── validation/   Protocolo y estadística para validar contra el conteo manual y otros softwares
└── data/         Fotos de ejemplo
```

## Desarrollo

**Servidor**

```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
.venv/Scripts/python -m uvicorn bioyologic.api.main:app --app-dir backend --port 8000
```

La documentación interactiva de la API queda en http://localhost:8000/docs. Para producción basta `backend/requirements-server.txt` (ONNX Runtime, sin PyTorch). Las variables de configuración están en la cabecera de `backend/bioyologic/api/main.py` y en `deploy/.env.example`.

**App**

```bash
cd app
flutter pub get
flutter run                                    # emulador Android: servidor http://10.0.2.2:8000
flutter build web --base-href /app/            # el servidor la publica en /app
flutter build apk --release --dart-define=BIOYOLOGIC_SERVER=https://bioyologic.duckdns.org
```

**Entrenar los modelos:** abre `training/Bioyologic_entrenamiento.ipynb` (detector) o `training/Bioyologic_especies.ipynb` (especie) en Google Colab con GPU T4 y ejecuta todo. Copia los archivos que descarga en `models/`. Para el servidor, `python backend/scripts/export_onnx.py` genera los `.onnx`.

**Desplegar:** [`deploy/README.md`](deploy/README.md) explica la instalación en Oracle Cloud. Para actualizar el servidor desde el PC: `sh deploy/actualizar_desde_pc.sh`.

**Pruebas**

```bash
cd backend && ../.venv/Scripts/python -m pytest -q
cd app && flutter test
```

## API principal

| Ruta | Para qué |
|---|---|
| `POST /auth/register` · `/auth/login` · `/auth/verify` · `/auth/password/forgot` · `/auth/password/reset` | Cuentas, verificación del correo y recuperación de contraseña |
| `POST /analyses` | Analiza una foto (dilución, volumen, muestra y proyecto opcionales) |
| `GET /analyses` · `GET/PATCH/DELETE /analyses/{id}` · `POST /analyses/delete` | Historial, detalle, edición y borrado de uno o varios |
| `PUT /analyses/{id}/colonies` | Corrección manual del conteo |
| `GET /analyses/{id}/report/{nombre}.pdf` | Informe PDF |
| `GET /samples` | Muestras con varias placas y su UFC/mL combinada (ISO 4833-1) |
| `POST /export-link` | Enlace de descarga del CSV para Excel |
| `GET/POST/PATCH/DELETE /projects` | Proyectos |
| `GET /library` | Biblioteca de microorganismos y protocolos |
| `GET /about` | Licencia, código fuente, datasets y contacto de datos personales |

## Licencia y créditos

Copyright © 2026 Juan José Martínez y el equipo Bioyologic. Software libre bajo la **GNU Affero General Public License v3 o posterior** ([LICENSE](LICENSE)), sin ninguna garantía. La AGPL-3.0 viene de Ultralytics YOLO: quien ofrezca Bioyologic como servicio en red debe dar acceso a su código fuente (la API lo indica en `GET /about` y la app en *Perfil → Acerca de*).

Los modelos se entrenaron con los datasets de **Makrai, L. et al. (2023)** y **Du, J. (2026)**, ambos CC BY 4.0. Las citas completas están en [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) y [CITATION.cff](CITATION.cff).
