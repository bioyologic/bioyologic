# Ficha de los modelos de Bioyologic (model card)

Bioyologic usa dos modelos en cadena. El **detector** encuentra cada colonia de la placa. El **clasificador** mira el recorte de cada colonia y estima su especie. La segmentación, la morfología y el cálculo de UFC son algoritmos clásicos y no forman parte de estos modelos.

| | Detector | Clasificador de especie |
|---|---|---|
| Archivos | `models/bioyologic.pt` · `.onnx` · `.json` | `models/bioyologic_species.pt` · `.onnx` · `.json` |
| Arquitectura | YOLO11s (detección), 1 clase: `colony` | YOLO11s-cls (clasificación), 37 especies |
| Entrada | Teselas de 640 px; la foto se reduce antes a un lado máximo de 2048 px | Recorte cuadrado de 160 px con un margen del 30 % alrededor de la colonia |
| Entrenamiento | `training/Bioyologic_entrenamiento.ipynb` (Google Colab, GPU T4) | `training/Bioyologic_especies.ipynb` (Google Colab, GPU T4) |
| Licencia | AGPL-3.0 (derivado de Ultralytics), con atribución CC BY 4.0 a los datos | Igual |

## Datos de entrenamiento

Dos datasets públicos anotados por microbiólogos, ambos con licencia CC BY 4.0:

- **Makrai *et al.* (2023)**, *Scientific Data* 10:497, [doi:10.6084/m9.figshare.22022540](https://doi.org/10.6084/m9.figshare.22022540). 369 placas, 56 865 colonias, 24 especies de origen veterinario.
- ***Clinical Dataset of 19 Bacterial Colony Images***, [doi:10.5281/zenodo.18256864](https://doi.org/10.5281/zenodo.18256864). 950 placas, 59 221 colonias, 19 especies clínicas.

Los datos se separan **por placa** (80 % entrenamiento, 10 % validación, 10 % test), así que ninguna foto de test se vio al entrenar. Las especies de ambos datasets se unificaron por nombre en 37 especies (`training/species_map.json`).

## Resultados en test

**Detector** (133 placas de test que el modelo no vio al entrenar):

| Métrica | Valor |
|---|---|
| mAP50 / mAP50-95 | 0,969 / 0,679 |
| Precisión / recall | 0,939 / 0,936 |
| Error absoluto medio del conteo por placa (MAE) | 2,26 colonias |
| RMSE del conteo | 6,58 colonias |
| Sesgo del conteo | +0,70 colonias |
| Error porcentual medio del conteo (MAPE) | 2,6 % |

**Clasificador de especie:**

| Métrica | Valor |
|---|---|
| Acierto por colonia (top-1) | 96,4 % |
| Acierto por placa (votación de sus colonias) | 134 de 134 placas (100 %) |

**Versión ONNX:** en 7 fotos reales comprobadas da los mismos conteos y las mismas especies y probabilidades que la versión PyTorch. Lo verifica también `backend/tests/test_onnx.py`.

## Uso previsto

- Contar colonias y describir su morfología en fotos cenitales de placas de Petri de 90 mm, para docencia, investigación y apoyo al trabajo de laboratorio.
- Sugerir la especie probable de la placa como **orientación**.

## Uso no previsto

- **No es un dispositivo médico.** No sirve para diagnosticar ni para decidir tratamientos.
- La especie que propone debe confirmarse con pruebas microbiológicas (Gram, bioquímicas, MALDI-TOF, etc.).

## Limitaciones conocidas

- **Sesgo del medio de cultivo:** en los datasets, cada especie se cultivó en un medio concreto (sangre, MacConkey, etc.). El clasificador puede apoyarse en el color del agar además de en la colonia. Con medios distintos o fotos de otro laboratorio, la especie es menos fiable.
- **Especies fuera de las 37:** el clasificador siempre elige una de las especies que conoce. Si la probabilidad media de la placa es menor del 40 %, la app la marca como «no identificada».
- **Placas mixtas:** el entrenamiento solo incluye placas con una única especie.
- **Colonias confluentes o muy pequeñas:** las colonias que se tocan pueden contarse como una sola y las de menos de 12 px pueden perderse. Con más de 300 colonias la placa se marca como incontable.
- **Condiciones de la foto:** reflejos, sombras o una cámara inclinada empeoran la detección. La escala en mm depende de ajustar la placa al círculo guía.
- **Elevación:** la elevación de la colonia no se puede medir con una foto 2D.

## Reentrenar o mejorar

1. Añadir fotos anotadas (formato COCO) de otros laboratorios y medios.
2. Ejecutar los notebooks de `training/`.
3. Copiar los modelos a `models/`.
4. Ejecutar `python backend/scripts/export_onnx.py` para generar las versiones ONNX.
