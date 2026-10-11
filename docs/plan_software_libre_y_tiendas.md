# Plan para mañana: software libre, servidor en la nube y publicación en tiendas

Documento de trabajo para decidir y ejecutar.

**Estado (11/10/2026):** está hecho todo lo de código y documentación de las secciones 1 y 2:
- Licencia y documentos: `LICENSE` (AGPL-3.0), `THIRD_PARTY_LICENSES.md`, `CITATION.cff`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `docs/model_card.md` y `docs/privacidad.md`.
- Pantallas «Acerca de» y «Privacidad» en la app, y endpoint `/about` en la API.
- Modelos ONNX con un servidor sin PyTorch.
- Despliegue con `Dockerfile` y `deploy/` (Docker Compose, HTTPS con Caddy, copias de seguridad).
- Límite de tamaño de foto y de análisis por minuto.

**Falta lo que requiere tus cuentas:** crear el repositorio público y subir el código, crear la VM en Oracle y el dominio en DuckDNS, y desplegar. Tras el despliegue: quitar el HTTP sin cifrar de la app y compilar con `--dart-define=BIOYOLOGIC_SERVER=https://...`.

---

## 1. Software libre (lo que probablemente pide el profesor)

> No me dijiste qué pidió exactamente el profesor. Esto cubre lo habitual; mañana conviene confirmarlo.

### El punto clave: Ultralytics YOLO es AGPL-3.0

Bioyologic usa Ultralytics (YOLO11) para entrenar y para detectar. Ultralytics tiene dos licencias ([ultralytics.com/license](https://ultralytics.com/license)):

- **AGPL-3.0 (gratis):** obliga a que todo el proyecto que lo usa, incluidos los modelos entrenados, sea código abierto bajo AGPL-3.0. Esto aplica también si se ofrece como servicio por red (servidor/API).
- **Licencia Enterprise (de pago):** solo hace falta para un producto cerrado o comercial.

**Conclusión:** para un proyecto académico, lo natural es publicar Bioyologic como software libre bajo **AGPL-3.0**. Así se cumple la licencia de Ultralytics y, de paso, lo que pide un curso de software libre.

### Licencias de todas las piezas (todas compatibles con AGPL-3.0)

| Pieza | Licencia | Notas |
|---|---|---|
| Ultralytics YOLO11 | AGPL-3.0 | Obliga a AGPL el conjunto |
| PyTorch, NumPy | BSD-3 | |
| OpenCV | Apache-2.0 | |
| FastAPI | MIT | |
| Uvicorn | BSD-3 | |
| ReportLab | BSD | |
| PyYAML | MIT | |
| Flutter y paquetes (http, camera, image_picker, shared_preferences, url_launcher, intl) | BSD-3 / Apache-2.0 | |
| PyMuPDF | AGPL-3.0 | Solo lo usa el script de figuras del documento |
| Dataset Makrai et al. 2023 | CC BY 4.0 | Exige atribución; no redistribuimos las fotos |
| Dataset clínico de Zenodo | CC BY 4.0 | Exige atribución |
| Modelos entrenados (`bioyologic.pt`, `bioyologic_species.pt`) | AGPL-3.0 | Por Ultralytics; los datos piden atribución CC BY |

### Qué haría para publicarlo como software libre

1. Repositorio público en GitHub, GitLab o Codeberg (Codeberg es la opción 100 % software libre).
2. Archivos estándar:
   - `LICENSE`: AGPL-3.0.
   - `README` con la cita de los datasets.
   - `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` y `CITATION.cff` (para que otros citen el proyecto).
   - `THIRD_PARTY_LICENSES.md` con la tabla de arriba.
   - **Model card** (cómo se entrenaron los modelos, métricas y límites) y **dataset card**.
3. En la app, pantalla «Acerca de»: licencia AGPL-3.0 y enlace al código fuente. La AGPL (sección 13) obliga a ofrecer el código a quien usa el servidor por red.
4. **F-Droid**, la tienda de apps libres de Android: muy alineado con un curso de software libre. Admite apps Flutter sin servicios de Google. Bioyologic no usa Google Play Services, así que cumple.
5. Antes de publicar: quitar del repositorio cosas personales (datos de demostración, rutas locales) y mantener `data/` y `models/` fuera de git. Los modelos se suben como *release* o a Hugging Face Hub.

---

## 2. Servidor en la nube: alternativas y viabilidad

**El problema:** hoy la app solo funciona si el servidor corre en tu PC. Para una app publicada, el servidor debe estar en internet con HTTPS, o el análisis debe hacerse dentro del móvil.

### Opciones comparadas (precios y límites de 2026; hay que confirmarlos al crear la cuenta)

| Opción | Costo | Ventajas | Inconvenientes | Para Bioyologic |
|---|---|---|---|---|
| **Oracle Cloud Always Free** (VM ARM) | 0 € | Máquina virtual siempre encendida, 2 OCPU y 12 GB de RAM ([recortado en 2026](https://infoq.com/news/2026/07/oracle-cloud-free-tier-limits/)); disco persistente (SQLite e imágenes se conservan) | Pide tarjeta para verificar la cuenta; a veces no hay capacidad ARM en la región; tú administras el servidor | **Recomendada** para el proyecto |
| **Hugging Face Spaces** (Docker, CPU gratis) | 0 € | Lo más fácil; ideal para una demo pública | Se duerme tras 48 h sin uso; el disco se borra al reiniciar (se perderían los análisis); las condiciones del plan gratis están cambiando ([fuente](https://discuss.huggingface.co/t/question-about-the-cpu-basic-quota-limit/176628)) | Bueno como demo, no como servidor principal |
| **Google Cloud Run** | 0 € dentro de la cuota gratuita (2 M peticiones/mes, solo en regiones de EE. UU.) | Escala solo y no hay servidor que mantener | Arranque en frío lento (imagen de ~2 GB con PyTorch); necesita Cloud Storage y una base de datos aparte para guardar; se cobra si te pasas | Viable, más complejo |
| **Modelo dentro del móvil** (sin servidor) | 0 € | Funciona sin internet, máxima privacidad, sin servidor que mantener | Hay que portar la segmentación y las medidas a Dart (opencv_dart) y exportar los modelos a TFLite/Core ML; app ~30–50 MB más pesada; más lenta en móviles viejos | La mejor solución a largo plazo; mucho trabajo |

### Recomendación

1. **Fase 1 (para el proyecto):** servidor en **Oracle Cloud Always Free**.
   - Docker con FastAPI.
   - **HTTPS** gratis con Caddy + Let's Encrypt y un dominio gratuito (DuckDNS).
   - Copia de seguridad diaria de `data/store`.
   - Respaldo si Oracle no da capacidad: Hugging Face Spaces como demo.
2. **Optimización recomendada:** exportar los modelos a **ONNX** y servirlos con `onnxruntime` en lugar de PyTorch. La imagen pasa de ~2 GB a ~400 MB, arranca más rápido y usa menos RAM. Encaja bien en el plan gratuito.
3. **Fase 2 (opcional, futuro):** modelo dentro del móvil, para que funcione sin conexión.

**¿Es viable? Sí.** Un análisis tarda unos segundos en CPU, que basta para un proyecto académico y algunos usuarios. El costo puede ser 0 €. Los riesgos son la verificación con tarjeta en Oracle, la falta de capacidad ARM y que alguien debe mantener el servidor.

**Cambios necesarios en el código:**
- Dockerfile.
- Variables de entorno.
- Quitar el HTTP sin cifrar de la app (`usesCleartextTraffic` en Android, `NSAllowsArbitraryLoads` en iOS).
- URL del servidor por defecto apuntando a la nube.
- Límite de tamaño y de peticiones por usuario.
- Política de privacidad: las fotos se suben a un servidor.

---

## 3. Publicar en Google Play

| Requisito | Detalle | Estado |
|---|---|---|
| Cuenta de desarrollador | 25 USD, pago único | Falta (la crea el usuario) |
| **Prueba cerrada obligatoria** | Cuentas personales creadas después de nov. 2023: **12 testers durante 14 días seguidos** antes de poder publicar ([fuente](https://www.testerscommunity.com/blog/google-play-closed-testing-requirements-2026)). Las cuentas de organización (con D-U-N-S) están exentas | Hay que conseguir 12 testers (compañeros) |
| Firma de la app | Crear un keystore de *upload*; hoy la APK release va firmada con la clave de depuración | Falta |
| Formato | App Bundle (`flutter build appbundle`) | Fácil |
| Identificador | `com.bioyologic.bioyologic` (definitivo una vez publicado) | Revisar el nombre |
| Servidor HTTPS | Sin él la app no funciona fuera de tu red | Ver sección 2 |
| Política de privacidad | URL pública (puede ser una página de GitHub) | Falta |
| Formulario «Seguridad de los datos» | Declarar fotos, uso de la cámara y que no hay cuentas de usuario | Falta |
| Clasificación de contenido y público objetivo | Cuestionario en Play Console | Falta |
| Política de apps de salud | Declarar que **no es un dispositivo médico** y que los resultados son orientativos (la app ya muestra el aviso) | Revisar textos |
| Ficha de la tienda | Icono 512 px, gráfico destacado 1024 × 500, capturas de pantalla, descripción | Hay capturas; falta el gráfico |

**Calendario realista:** 1 día para dejar todo listo, más **14 días de prueba cerrada**, más 1–7 días de revisión de Google.

## 4. Publicar en App Store (iPhone)

| Requisito | Detalle |
|---|---|
| Apple Developer Program | 99 USD al año |
| Compilar para iOS | Necesita macOS con Xcode. Sin Mac: **Codemagic** (plan gratuito con Mac en la nube) o GitHub Actions con runner macOS |
| Firma | Certificados y perfiles de aprovisionamiento (Codemagic lo automatiza) |
| Probar | TestFlight antes de enviar a revisión |
| Revisión de Apple | Pauta 1.4.1 (salud): no prometer diagnósticos y explicar el método; textos de permisos de cámara y fotos (ya están); manifiesto de privacidad; HTTPS obligatorio |
| Ficha | Capturas de iPhone 6,7" y 6,5", descripción, política de privacidad |

**Calendario realista:** 2–3 días de configuración, más 1–3 días de revisión. Apple rechaza a menudo las primeras versiones de apps de salud; hay que dejar claro que es una herramienta educativa o de apoyo.

---

## 5. Orden propuesto para mañana

1. Confirmar qué pidió exactamente el profesor de software libre.
2. Decidir: licencia AGPL-3.0 y repositorio público (GitHub o Codeberg).
3. Decidir el servidor: Oracle Always Free (+ Hugging Face como demo) o el modelo en el móvil.
4. Preparar el repositorio libre (licencias, README, model card) → publicar.
5. Desplegar el servidor con HTTPS → apuntar la app a él.
6. Google Play: crear la cuenta → keystore → App Bundle → prueba cerrada con 12 testers (empieza el reloj de 14 días).
7. En paralelo, F-Droid, que no exige cuenta de pago ni prueba de 14 días.
8. App Store: cuando haya cuenta de Apple; compilar con Codemagic.

**Lo que tienes que hacer tú (no puedo hacerlo yo):** crear y pagar las cuentas (Google, Apple, Oracle) y meter datos de tarjeta, aceptar contratos y términos, invitar a los 12 testers.
