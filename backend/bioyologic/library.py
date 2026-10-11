"""Contenido de la Biblioteca de la app: microorganismos, protocolos y guías."""

from __future__ import annotations

from pathlib import Path

import cv2

from .synthetic import SPECIES, draw_plate

ENTRIES: list[dict] = [
    # ------------------------------------------------------------ microorganismos
    {
        "id": "e-coli", "category": "bacterias", "species": "E.coli",
        "title": "Escherichia coli", "subtitle": "Bacilo gramnegativo · Enterobacteria",
        "tags": ["Gram −", "Anaerobio facultativo", "37 °C"],
        "sections": [
            ["Descripción", "Bacilo gramnegativo, móvil y anaerobio facultativo. Habita el intestino de "
             "animales de sangre caliente y se usa como indicador de contaminación fecal en aguas y alimentos."],
            ["Morfología de colonia", "En agar nutritivo, tras 18–24 h a 37 °C, forma colonias circulares, "
             "convexas, lisas y de borde entero, de 2–3 mm y color blanco crema o beige. En agar MacConkey "
             "aparecen rosadas porque fermenta la lactosa."],
            ["Qué esperar en Bioyologic", "Forma predominante circular, borde entero, color beige y "
             "circularidad alta (> 0,85)."],
        ],
    },
    {
        "id": "s-aureus", "category": "bacterias", "species": "S.aureus",
        "title": "Staphylococcus aureus", "subtitle": "Coco grampositivo · Estafilococo",
        "tags": ["Gram +", "Coagulasa +", "37 °C"],
        "sections": [
            ["Descripción", "Coco grampositivo que se agrupa en racimos. Forma parte de la microbiota de la "
             "piel y las mucosas, pero es un patógeno oportunista importante."],
            ["Morfología de colonia", "Colonias circulares, lisas, brillantes y convexas, de 1–3 mm, con "
             "pigmento amarillo dorado característico. En agar sangre suele producir beta-hemólisis y en agar "
             "manitol salado vira el medio a amarillo."],
            ["Qué esperar en Bioyologic", "Colonias pequeñas y circulares de color amarillo; muchas se "
             "clasifican como puntiformes si miden menos de 1 mm."],
        ],
    },
    {
        "id": "p-aeruginosa", "category": "bacterias", "species": "P.aeruginosa",
        "title": "Pseudomonas aeruginosa", "subtitle": "Bacilo gramnegativo · No fermentador",
        "tags": ["Gram −", "Aerobio estricto", "Pigmentado"],
        "sections": [
            ["Descripción", "Bacilo gramnegativo aerobio estricto, muy ubicuo en suelo y agua. Es un patógeno "
             "oportunista con resistencia intrínseca a numerosos antibióticos."],
            ["Morfología de colonia", "Colonias planas, extendidas y de borde irregular, a menudo con brillo "
             "metálico. Produce pigmentos difusibles (piocianina, verde azulado; pioverdina, amarillo "
             "verdoso) y un olor afrutado característico. Crece a 42 °C."],
            ["Qué esperar en Bioyologic", "Color verdoso, borde ondulado y solidez algo menor que en las "
             "colonias circulares."],
        ],
    },
    {
        "id": "b-subtilis", "category": "bacterias", "species": "B.subtilis",
        "title": "Bacillus subtilis", "subtitle": "Bacilo grampositivo · Esporulado",
        "tags": ["Gram +", "Forma esporas", "30–37 °C"],
        "sections": [
            ["Descripción", "Bacilo grampositivo del suelo, formador de endosporas resistentes al calor. Se "
             "usa como organismo modelo y como control en ensayos farmacopeicos."],
            ["Morfología de colonia", "Colonias grandes, irregulares, secas y rugosas, de aspecto mate y "
             "borde ondulado o lobulado, color blanquecino a crema. Pueden extenderse por la superficie del "
             "agar."],
            ["Qué esperar en Bioyologic", "Forma irregular, borde lobulado, solidez baja (< 0,85) y "
             "diámetros mayores que el resto de especies."],
        ],
    },
    {
        "id": "c-albicans", "category": "bacterias", "species": "C.albicans",
        "title": "Candida albicans", "subtitle": "Levadura · Hongo (no bacteria)",
        "tags": ["Levadura", "Sabouraud", "25–37 °C"],
        "sections": [
            ["Descripción", "Levadura comensal de las mucosas humanas. No es una bacteria, pero se incluye en "
             "los ensayos de control microbiológico y en el dataset AGAR como microorganismo de referencia."],
            ["Morfología de colonia", "Colonias blancas a crema, lisas, cremosas y convexas, con olor a "
             "levadura. En agar Sabouraud se ven bien a las 24–48 h."],
            ["Qué esperar en Bioyologic", "Colonias circulares, blancas, de borde entero y contraste alto "
             "con el agar."],
        ],
    },
    # ------------------------------------------------------------ protocolos
    {
        "id": "diluciones", "category": "protocolos",
        "title": "Diluciones seriadas decimales", "subtitle": "Protocolo · Preparación de la muestra",
        "tags": ["10⁻¹ a 10⁻⁸", "Diluyente estéril"],
        "sections": [
            ["Objetivo", "Reducir la concentración de microorganismos para obtener placas con 30–300 colonias."],
            ["Procedimiento", "1. Prepara tubos con 9 mL de diluyente estéril (solución salina 0,85 % o agua "
             "de peptona).\n2. Transfiere 1 mL de la muestra al primer tubo: dilución 10⁻¹.\n3. Agita en "
             "vórtex 5–10 s.\n4. Con una punta nueva, pasa 1 mL del tubo anterior al siguiente: 10⁻², 10⁻³…\n"
             "5. Siembra las diluciones con las que esperes obtener entre 30 y 300 colonias."],
            ["Consejos", "Cambia de punta en cada paso para no arrastrar células, y etiqueta cada tubo antes "
             "de empezar."],
        ],
    },
    {
        "id": "siembra-superficie", "category": "protocolos",
        "title": "Siembra en superficie", "subtitle": "Protocolo · Extensión con asa de Drigalski",
        "tags": ["0,1 mL", "Asa de Drigalski"],
        "sections": [
            ["Objetivo", "Repartir un volumen conocido de muestra sobre el agar para obtener colonias aisladas "
             "y contables."],
            ["Procedimiento", "1. Usa placas con el agar seco (sin gotas en la superficie).\n2. Deposita "
             "0,1 mL de la dilución en el centro de la placa.\n3. Extiende con el asa de Drigalski estéril, "
             "girando la placa, hasta que el líquido se absorba.\n4. Incuba la placa invertida a la "
             "temperatura indicada (p. ej. 37 °C, 24–48 h)."],
            ["En Bioyologic", "Indica volumen = 0,1 mL y la dilución sembrada para obtener las UFC/mL."],
        ],
    },
    {
        "id": "siembra-profundidad", "category": "protocolos",
        "title": "Siembra en profundidad", "subtitle": "Protocolo · Vertido en placa",
        "tags": ["1 mL", "Agar a 45 °C"],
        "sections": [
            ["Objetivo", "Contar microorganismos en volúmenes mayores (1 mL) incorporando la muestra al agar."],
            ["Procedimiento", "1. Pipetea 1 mL de la dilución en una placa vacía.\n2. Añade 15–20 mL de agar "
             "fundido y atemperado a 45 °C.\n3. Mezcla con movimientos suaves en forma de ocho.\n4. Deja "
             "solidificar e incuba invertida."],
            ["Ten en cuenta", "Las colonias que crecen dentro del agar son más pequeñas y lenticulares; la "
             "morfología no es comparable con la de superficie."],
        ],
    },
    {
        "id": "calculo-ufc", "category": "protocolos",
        "title": "Cálculo de UFC/mL", "subtitle": "Protocolo · Interpretación del recuento",
        "tags": ["30–300 colonias", "Fórmula"],
        "sections": [
            ["Fórmula", "UFC/mL = número de colonias / (dilución × volumen sembrado en mL)."],
            ["Ejemplo", "150 colonias en la dilución 10⁻⁴ sembrando 0,1 mL:\n150 / (10⁻⁴ × 0,1) = "
             "1,5 × 10⁷ UFC/mL."],
            ["Rango contable", "Usa placas con 30–300 colonias. Con menos de 30, el resultado es solo "
             "estimado; con más de 300, la placa es incontable y debe repetirse con una dilución mayor. "
             "Bioyologic marca automáticamente cada caso."],
        ],
    },
    # ------------------------------------------------------------ guías
    {
        "id": "fotografiar", "category": "guias",
        "title": "Cómo fotografiar la placa", "subtitle": "Guía · Captura con el móvil",
        "tags": ["Iluminación", "Encuadre"],
        "sections": [
            ["Antes de la foto", "Limpia la tapa o retírala si hay condensación. Coloca la placa sobre un "
             "fondo oscuro y mate."],
            ["Iluminación", "Usa luz difusa y uniforme (luz de día indirecta o una lámpara con difusor). "
             "Evita el flash y los reflejos directos sobre el agar."],
            ["Encuadre", "Sostén el móvil paralelo a la placa y ajusta el borde de la placa al círculo guía "
             "de la cámara. Así Bioyologic calcula la escala en milímetros. No uses zoom digital."],
        ],
    },
    {
        "id": "morfologia", "category": "guias",
        "title": "Interpretar la morfología", "subtitle": "Guía · Descriptores de Bioyologic",
        "tags": ["Forma", "Borde", "Color"],
        "sections": [
            ["Forma", "Puntiforme (< 1 mm), circular (circularidad ≥ 0,80 y relación de aspecto ≤ 1,25) o "
             "irregular."],
            ["Borde", "Entero (solidez ≥ 0,95), ondulado (≥ 0,85) o lobulado (< 0,85). La solidez compara el "
             "área de la colonia con la de su envolvente convexa."],
            ["Color y contraste", "Color medio de la colonia y diferencia de color ΔE con el agar, que da una "
             "idea aproximada de la opacidad. La elevación no se puede medir desde una foto cenital."],
        ],
    },
    {
        "id": "bioseguridad", "category": "guias",
        "title": "Bioseguridad en el laboratorio", "subtitle": "Guía · Buenas prácticas",
        "tags": ["BSL-2", "Residuos"],
        "sections": [
            ["Manipulación", "Trabaja con bata y guantes, cerca del mechero o en cabina de bioseguridad. "
             "Muchas especies (p. ej. S. aureus o P. aeruginosa) requieren nivel de bioseguridad 2."],
            ["Fotografía", "Fotografía las placas cerradas siempre que sea posible. Si abres la tapa, hazlo "
             "dentro de la cabina."],
            ["Residuos", "Desecha placas y material contaminado en contenedores de riesgo biológico para su "
             "esterilización en autoclave."],
        ],
    },
]

CATEGORIES = {"bacterias": "Microorganismos", "protocolos": "Protocolos", "guias": "Guías"}


def get_entry(entry_id: str) -> dict | None:
    return next((e for e in ENTRIES if e["id"] == entry_id), None)


def entry_image(entry: dict, cache_dir: Path) -> Path:
    """Imagen ilustrativa (placa sintética) de la entrada, generada una vez y cacheada."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{entry['id']}.jpg"
    if path.exists():
        return path
    seed = sum(map(ord, entry["id"]))
    sp = [s for s in SPECIES if s.name == entry.get("species")] or None
    img, _ = draw_plate(1024, 70 if sp else 45, seed=seed, species=sp)
    crop = img[262:762, 262:762]  # zona central, para que las colonias se aprecien
    cv2.imwrite(str(path), cv2.resize(crop, (480, 480), interpolation=cv2.INTER_AREA),
                [cv2.IMWRITE_JPEG_QUALITY, 88])
    return path
