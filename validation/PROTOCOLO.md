# Protocolo de validación de Bioyologic

Objetivo: medir, sobre **las mismas placas y las mismas fotos**, cuánto se equivoca Bioyologic frente al conteo manual y frente a otros softwares de conteo, con estadística que diga si las diferencias son significativas.

Gráfico de la metodología para la presentación: [`metodologia_validacion.png`](metodologia_validacion.png).

## 1. Cuántas placas

El profesor sugirió tres cajas de Petri. Sirven para mostrar el método, pero **no alcanzan para la significancia estadística**: con 3 placas la prueba de Wilcoxon nunca puede dar p < 0,05 (el p más pequeño posible con n = 3 es 0,25). Hace falta un mínimo de 6 placas y lo recomendable son 10 o más.

Propuesta que aprovecha el mismo trabajo de laboratorio:

| Factor | Niveles | Placas |
|---|---|---|
| Muestras (cepa o muestra de agua/alimento disponible) | 2 | |
| Diluciones seriadas | 10⁻⁴, 10⁻⁵, 10⁻⁶ | |
| Réplicas por dilución | 2 | |
| **Total** | 2 × 3 × 2 | **12 placas** |

Las tres diluciones dan placas con pocas, medias y muchas colonias, así que también se prueba el rango contable (30–300) y lo que pasa fuera de él. Si solo hay tiempo para 3 placas, el script de análisis igual calcula los errores y lo advierte en los resultados.

## 2. Preparación

1. Siembra en superficie de 0,1 mL de cada dilución en agar nutritivo (o el medio disponible).
2. Incubar 24 h a 37 °C.
3. Marcar cada placa por debajo con un código (P01, P02…). **No** escribir la dilución donde se vea en la foto.

## 3. Foto

1. Una foto por placa, dentro de la caja de iluminación, con la placa **cerrada**.
2. Mismo celular, misma altura (la tapa de la caja la fija) y misma luz para todas.
3. Guardar las fotos con el código: `P01.jpg`, `P02.jpg`…

## 4. Conteos

Todos los métodos cuentan **la misma foto** (o la misma placa, en el caso del conteo manual):

| Método | Quién / cómo | Qué registrar |
|---|---|---|
| Manual | Laura, Juan y Samuel, **cada uno por separado y sin ver los conteos de los demás** (ciego), con contador de clic sobre la placa | Conteo y tiempo en segundos |
| Bioyologic | App, con la foto de la placa | Conteo y tiempo |
| OpenCFU | Programa gratuito (opencfu.sourceforge.net), con la misma foto | Conteo y tiempo |
| Segundo software | ImageJ / Fiji (gratuito) con su procedimiento de conteo de partículas, u otro disponible | Conteo y tiempo |

Anotar todo en [`plantilla_conteos.csv`](plantilla_conteos.csv): una fila por conteo (placa, método, observador, conteo, segundos). Para más placas, copiar las filas cambiando el código.

## 5. Análisis

```bash
python validation/analizar_validacion.py validation/plantilla_conteos.csv
```

El script calcula, por cada método frente al promedio del conteo manual:

| Medida | Qué responde |
|---|---|
| **MAPE** (error absoluto medio, %) | ¿Cuánto se equivoca en promedio? Meta Must have M1: ≤ 5 % |
| **Sesgo** y **límites de acuerdo de Bland–Altman** | ¿Cuenta de más o de menos? ¿Entre qué valores cae el 95 % de sus diferencias? |
| **r de Pearson** y **CCC de Lin** | ¿Sigue la misma tendencia que el manual? ¿Coincide de verdad (no solo correlaciona)? |
| **Wilcoxon** (método vs manual) | ¿Cuenta distinto del manual de forma sistemática? |
| **TOST** (equivalencia, ±5 %) | ¿Se puede afirmar con significancia que su error está dentro de ±5 %? |
| **Friedman** + **Wilcoxon por pares (Holm)** | ¿Qué método se equivoca menos, y la diferencia es significativa? |
| **CV entre observadores** | ¿Cuánto varían las personas entre sí? Es la vara para juzgar al software |
| **Segundos por placa** | ¿Cuánto tiempo ahorra? |

Genera `resultados/resultados.md` (tablas listas para el documento), `errores_por_placa.csv`, `bland_altman.png` y `error_por_metodo.png` (listas para las diapositivas).

Se usan pruebas no paramétricas (Wilcoxon, Friedman) porque con pocas placas no se puede suponer normalidad. Nivel de significancia: α = 0,05.

## 6. Qué se reporta

1. Tabla de errores por método (MAPE, sesgo, límites de acuerdo, CCC, tiempo).
2. Gráfico de error por método y gráfico de Bland–Altman.
3. Frase de conclusión con los p-valores, por ejemplo: *"Bioyologic tuvo un MAPE de X % (meta ≤ 5 %), significativamente menor que OpenCFU (p = …), y su error fue equivalente al conteo manual dentro de ±5 % (TOST, p = …)."*
4. Limitaciones: número de placas, un solo medio de cultivo, una sola especie si es el caso.
