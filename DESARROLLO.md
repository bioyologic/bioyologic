# Bioyologic · Instrucciones para desarrolladores

Cómo instalar, ejecutar, entrenar y desplegar Bioyologic. Para usar la app no hace falta nada de esto: basta con entrar a https://bioyologic.duckdns.org o instalar el APK. Volver al [README](README.md).

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

## Instalación y ejecución

**Servidor**

```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
.venv/Scripts/python -m uvicorn bioyologic.api.main:app --app-dir backend --port 8000
```

La documentación interactiva de la API está publicada en **https://bioyologic.duckdns.org/docs** (si corres el servidor en tu propio PC, también en `http://localhost:8000/docs`). Para producción basta `backend/requirements-server.txt` (ONNX Runtime, sin PyTorch). Las variables de configuración están en la cabecera de `backend/bioyologic/api/main.py` y en `deploy/.env.example`.

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
| `GET/POST/PATCH/DELETE /projects` | Proyectos (propios y compartidos; `my_role`: owner, analista o revisor) |
| `GET/POST /projects/{id}/members` · `PATCH/DELETE /projects/{id}/members/{user_id}` | Equipo del proyecto: invitar por correo, cambiar rol, quitar o salir |
| `POST /analyses/{id}/review` · `GET /analyses?to_review=true` | Aprobar o devolver el análisis de otro miembro; cola de pendientes |
| `GET/POST /incubations` · `PATCH/DELETE /incubations/{id}` | Siembras en incubación (recordatorio de lectura; `incubation_id` al analizar) |
| `GET /library` | Biblioteca de microorganismos y protocolos |
| `GET /about` | Licencia, código fuente, datasets y contacto de datos personales |
