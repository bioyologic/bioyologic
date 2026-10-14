# Cómo contribuir

¡Gracias por tu interés en Bioyologic! Es software libre (AGPL-3.0) y las contribuciones son bienvenidas.

## Formas de ayudar

- **Reportar errores**: abre una *issue* con la foto (si se puede compartir), lo que esperabas y lo que pasó.
- **Fotos anotadas**: placas de otros laboratorios, medios y cámaras mejoran mucho el modelo. Indica la especie, el medio y la licencia de las fotos (preferible CC BY 4.0).
- **Código y documentación**: mejoras en la segmentación, la app, las traducciones o las guías.

## Entorno de desarrollo

```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/python -m pip install -r backend/requirements.txt
cd backend && ../.venv/Scripts/python -m pytest -q
cd app && flutter pub get && flutter test
```

## Cambios

1. Crea una rama desde `main`.
2. Mantén el estilo del código que rodea tu cambio y añade pruebas si cambias el comportamiento.
3. Comprueba que pasan `pytest` y `flutter test`.
4. Abre un *pull request* explicando qué cambia y por qué.

Al contribuir, aceptas que tu aporte se publique bajo la licencia AGPL-3.0-or-later del proyecto.

## Datos y privacidad

No subas al repositorio fotos de pacientes, datos personales ni la carpeta `data/store`. Los modelos (`*.pt`, `*.onnx`) van en el repositorio con **Git LFS**: instala Git LFS (`git lfs install`) antes de clonar para descargarlos.

## Conducta

Este proyecto sigue el [Código de conducta](CODE_OF_CONDUCT.md).
