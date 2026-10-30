"""Contenido de la Biblioteca de la app: microorganismos, protocolos de laboratorio y guías de uso.

Microorganismos: las 37 especies que reconoce el clasificador de Bioyologic, con el medio y el dataset de sus
fotos de entrenamiento. La imagen de cada ficha es una ilustración orientativa de sus colonias en ese medio
(no una foto real): se genera aquí y se guarda en caché.
"""

from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

MEDIOS = {
    "blood": "agar sangre", "chocolate": "agar chocolate", "MacConkey": "agar MacConkey",
    "Salmonella-Shigella": "agar Salmonella-Shigella (SS)", "nutrient": "agar nutritivo",
}
DATASETS = {
    "makrai": "Makrai et al. (2023), laboratorio de diagnóstico veterinario",
    "clinical": "Du (2026), muestras clínicas humanas",
}
BIOSEGURIDAD = {
    1: "Nivel de bioseguridad 1: bajo riesgo para personas sanas. Basta con las buenas prácticas de laboratorio "
       "(bata, lavado de manos, no comer ni beber en el laboratorio).",
    2: "Nivel de bioseguridad 2: puede causar enfermedad, sobre todo en personas con defensas bajas. Trabaja con "
       "bata y guantes, usa cabina de bioseguridad si hay riesgo de aerosoles, fotografía la placa cerrada y "
       "desecha el material en autoclave.",
    3: "Nivel de bioseguridad 3: el género Brucella se manipula en laboratorios de contención 3 (cabina de "
       "bioseguridad, acceso restringido, protección respiratoria). No abras estas placas fuera de esas "
       "instalaciones.",
}

# Aspecto para la ilustración: color BGR de la colonia, diámetro en mm, halo de hemólisis
# (beta, alfa, doble), tipo (lisa, irregular, seca, mucoide, puntiforme, swarming) y extras.
MICROS: list[dict] = [
    dict(species="Acinetobacter baumannii", forma="Cocobacilo gramnegativo", grupo="No fermentador",
         tags=["Gram −", "Aerobio estricto", "Oxidasa −"],
         que_es="Cocobacilo gramnegativo, inmóvil y aerobio estricto que no fermenta azúcares. Sobrevive semanas "
                "sobre superficies secas, equipos y manos.",
         importancia="Patógeno oportunista de hospitales: neumonía asociada a ventilación mecánica, bacteriemia "
                     "e infección de heridas en pacientes críticos. Las cepas resistentes a carbapenémicos están "
                     "en la categoría de prioridad crítica de la OMS.",
         colonias="En agar MacConkey crece con colonias incoloras o rosa pálido (no fermenta la lactosa), lisas, "
                  "convexas y de 1–2 mm, a veces algo mucoides. En agar sangre son blanco grisáceas y no "
                  "hemolíticas.",
         bsl=2, medios=["MacConkey"], datasets=["clinical"],
         look=dict(color=(185, 170, 205), mm=(1.2, 2.0), kind="lisa")),
    dict(species="Actinobacillus equuli", forma="Cocobacilo gramnegativo", grupo="Pasteurellaceae",
         tags=["Gram −", "Anaerobio facultativo", "Caballos"],
         que_es="Cocobacilo gramnegativo comensal de la boca y el tubo digestivo de los caballos.",
         importancia="Causa septicemia en potros recién nacidos (la «enfermedad del potro somnoliento»), además "
                     "de artritis y otras infecciones en equinos. En personas es raro, casi siempre por "
                     "mordeduras.",
         colonias="En agar sangre, colonias pequeñas (1–2 mm a las 24 h), grisáceas, lisas y a menudo pegajosas: "
                  "se adhieren al agar al tocarlas. La subespecie haemolyticus produce hemólisis.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(190, 195, 200), mm=(1.0, 1.8), kind="lisa")),
    dict(species="Actinobacillus pleuropneumoniae", forma="Cocobacilo gramnegativo", grupo="Pasteurellaceae",
         tags=["Gram −", "Requiere factor V (NAD)", "Cerdos"],
         que_es="Cocobacilo gramnegativo exclusivo del cerdo. La mayoría de las cepas necesitan NAD (factor V) "
                "para crecer, por eso se cultivan en agar chocolate.",
         importancia="Agente de la pleuroneumonía porcina, una enfermedad respiratoria grave y de gran impacto "
                     "económico en las granjas. No infecta a las personas.",
         colonias="En agar chocolate, colonias muy pequeñas (≈1 mm), grisáceas y translúcidas. En agar sangre "
                  "solo crece junto a una estría de Staphylococcus (satelitismo) y muestra hemólisis beta.",
         bsl=2, medios=["chocolate"], datasets=["makrai"],
         look=dict(color=(170, 180, 190), mm=(0.6, 1.1), kind="lisa")),
    dict(species="Aeromonas hydrophila", forma="Bacilo gramnegativo", grupo="Aeromonadaceae",
         tags=["Gram −", "Oxidasa +", "Agua dulce"],
         que_es="Bacilo gramnegativo móvil y oxidasa positivo que vive en agua dulce y salobre.",
         importancia="Produce enfermedad en peces y anfibios. En personas causa gastroenteritis e infecciones de "
                     "heridas expuestas a agua (ríos, lagos).",
         colonias="En agar sangre, colonias grandes (2–3 mm), convexas, grisáceas o blanquecinas, normalmente "
                  "rodeadas de una zona amplia de hemólisis beta.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(200, 205, 210), mm=(2.0, 3.0), kind="lisa", halo="beta")),
    dict(species="Bacillus cereus", forma="Bacilo grampositivo", grupo="Esporulado",
         tags=["Gram +", "Forma esporas", "Alimentos"],
         que_es="Bacilo grampositivo grande, formador de endosporas resistentes al calor. Está en el suelo y en "
                "muchos alimentos (arroz, cereales, especias).",
         importancia="Causa intoxicación alimentaria: un cuadro de vómitos por su toxina emética (típico del "
                     "arroz cocido que se deja a temperatura ambiente) y otro diarreico por enterotoxinas.",
         colonias="Colonias grandes (3–7 mm), planas, secas, de aspecto granular o de vidrio esmerilado y borde "
                  "irregular, con hemólisis beta amplia en agar sangre.",
         bsl=2, medios=["blood"], datasets=["makrai", "clinical"],
         look=dict(color=(185, 195, 205), mm=(3.5, 6.0), kind="seca", halo="beta")),
    dict(species="Bibersteinia trehalosi", forma="Cocobacilo gramnegativo", grupo="Pasteurellaceae",
         tags=["Gram −", "Ovejas", "Antes Pasteurella"],
         que_es="Cocobacilo gramnegativo de las vías respiratorias de rumiantes; antes se llamaba Pasteurella "
                "trehalosi.",
         importancia="Causa septicemia en corderos y neumonía en ovejas. No afecta a las personas.",
         colonias="En agar sangre, colonias pequeñas (1–2 mm), grisáceas y lisas, con hemólisis beta débil.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(180, 185, 195), mm=(1.0, 1.8), kind="lisa", halo="beta_debil")),
    dict(species="Bordetella bronchiseptica", forma="Cocobacilo gramnegativo", grupo="Alcaligenaceae",
         tags=["Gram −", "Aerobio estricto", "Perros y cerdos"],
         que_es="Cocobacilo gramnegativo móvil que coloniza las vías respiratorias de muchos mamíferos.",
         importancia="Es una causa principal de la «tos de las perreras» en perros y participa en la rinitis "
                     "atrófica del cerdo. En personas, rara vez, en pacientes inmunodeprimidos.",
         colonias="En agar sangre, colonias pequeñas (≈1 mm a las 24 h), grisáceas y lisas, a veces con hemólisis "
                  "beta. También crece en agar MacConkey sin fermentar la lactosa.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(175, 180, 190), mm=(0.8, 1.3), kind="lisa", halo="beta_debil")),
    dict(species="Brucella ovis", forma="Cocobacilo gramnegativo", grupo="Brucellaceae",
         tags=["Gram −", "Crecimiento lento", "Bioseguridad 3"],
         que_es="Cocobacilo gramnegativo pequeño, de crecimiento lento, que necesita CO₂ (5–10 %) para crecer "
                "bien.",
         importancia="Causa epididimitis e infertilidad en carneros. A diferencia de otras especies de Brucella, "
                     "no se considera una causa importante de enfermedad en personas, pero el género se trata "
                     "como de alto riesgo en el laboratorio.",
         colonias="Tarda 3–4 días en verse. Colonias pequeñas, rugosas y no hemolíticas en agar sangre.",
         bsl=3, medios=["blood"], datasets=["makrai"],
         look=dict(color=(170, 180, 195), mm=(0.5, 1.0), kind="irregular")),
    dict(species="Burkholderia cepacia", forma="Bacilo gramnegativo", grupo="No fermentador",
         tags=["Gram −", "Aerobio", "Resistencia intrínseca"],
         que_es="Bacilo gramnegativo ambiental (suelo, agua, plantas), resistente de forma natural a muchos "
                "antibióticos y desinfectantes.",
         importancia="Infecta sobre todo a pacientes con fibrosis quística o con defensas bajas, y contamina "
                     "soluciones y productos farmacéuticos, lo que ha causado brotes hospitalarios.",
         colonias="En agar MacConkey, colonias incoloras (no fermenta la lactosa), que pueden ser pequeñas a las "
                  "24 h y algunas con pigmento amarillento.",
         bsl=2, medios=["MacConkey"], datasets=["clinical"],
         look=dict(color=(150, 190, 205), mm=(0.8, 1.6), kind="lisa")),
    dict(species="Clostridium perfringens", forma="Bacilo grampositivo", grupo="Anaerobio esporulado",
         tags=["Gram +", "Anaerobio", "Doble hemólisis"],
         que_es="Bacilo grampositivo grande y anaerobio: solo crece sin oxígeno. Forma esporas y vive en el suelo "
                "y en el intestino.",
         importancia="Causa gangrena gaseosa, intoxicación alimentaria (carnes cocinadas que se mantienen tibias) "
                     "y enterotoxemias en animales.",
         colonias="En agar sangre incubado en anaerobiosis, colonias de 2–4 mm, grisáceas, planas o algo elevadas, "
                  "con una doble zona de hemólisis: completa por dentro y parcial por fuera.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(170, 175, 185), mm=(2.0, 3.5), kind="irregular", halo="doble")),
    dict(species="Corynebacterium pseudotuberculosis", forma="Bacilo grampositivo", grupo="Corineforme",
         tags=["Gram +", "Ovejas y cabras", "Zoonosis rara"],
         que_es="Bacilo grampositivo corto (corineforme) que sobrevive dentro de los macrófagos.",
         importancia="Causa la linfadenitis caseosa de ovejas y cabras (abscesos en los ganglios) y abscesos "
                     "en caballos. Puede infectar, rara vez, a personas que trabajan con estos animales.",
         colonias="Colonias pequeñas (≈1 mm a las 48 h), blanquecinas y secas, que se pueden empujar enteras "
                  "sobre el agar; hemólisis beta débil en agar sangre.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(200, 215, 225), mm=(0.7, 1.2), kind="seca", halo="beta_debil")),
    dict(species="Corynebacterium striatum", forma="Bacilo grampositivo", grupo="Corineforme",
         tags=["Gram +", "Piel", "Multirresistente"],
         que_es="Bacilo grampositivo corineforme que forma parte de la microbiota normal de la piel.",
         importancia="Patógeno emergente en infecciones de catéteres, heridas y prótesis; con frecuencia es "
                     "resistente a muchos antibióticos.",
         colonias="En agar sangre, colonias pequeñas (1–2 mm), blancas, lisas, húmedas y no hemolíticas.",
         bsl=2, medios=["blood"], datasets=["clinical"],
         look=dict(color=(220, 228, 232), mm=(1.0, 1.8), kind="lisa")),
    dict(species="Enterobacter cloacae", forma="Bacilo gramnegativo", grupo="Enterobacteria",
         tags=["Gram −", "Lactosa +", "Hospitalario"],
         que_es="Bacilo gramnegativo de la familia de las enterobacterias; vive en el intestino, el agua y el "
                "suelo.",
         importancia="Causa infecciones urinarias, de heridas y bacteriemias en pacientes hospitalizados. Produce "
                     "enzimas (AmpC, a veces carbapenemasas) que lo hacen resistente a muchos antibióticos.",
         colonias="En agar MacConkey, colonias rosadas (fermenta la lactosa), de 2–3 mm, lisas y a veces algo "
                  "mucoides.",
         bsl=2, medios=["MacConkey"], datasets=["clinical"],
         look=dict(color=(140, 80, 215), mm=(2.0, 3.0), kind="lisa")),
    dict(species="Enterococcus casseliflavus", forma="Coco grampositivo", grupo="Enterococo",
         tags=["Gram +", "Pigmento amarillo", "Móvil"],
         que_es="Coco grampositivo del intestino y de las plantas; a diferencia de otros enterococos, es móvil y "
                "suele tener pigmento amarillo.",
         importancia="Causa infecciones oportunistas ocasionales. Tiene una resistencia natural de bajo nivel a "
                     "la vancomicina (gen vanC), algo a tener en cuenta en el antibiograma.",
         colonias="En agar sangre, colonias pequeñas (1–2 mm), a menudo amarillentas, con hemólisis alfa o sin "
                  "hemólisis.",
         bsl=2, medios=["blood"], datasets=["clinical"],
         look=dict(color=(120, 215, 230), mm=(1.0, 1.6), kind="lisa", halo="alfa")),
    dict(species="Enterococcus faecium", forma="Coco grampositivo", grupo="Enterococo",
         tags=["Gram +", "Intestinal", "ERV"],
         que_es="Coco grampositivo del intestino humano y animal, muy resistente a condiciones adversas (sal, "
                "temperatura, desinfectantes).",
         importancia="Causa infecciones urinarias, bacteriemias y endocarditis en hospitales. Las cepas "
                     "resistentes a vancomicina (ERV) son de alta prioridad para la OMS.",
         colonias="En agar sangre, colonias pequeñas (1–2 mm), grisáceas y lisas, con hemólisis alfa o sin "
                  "hemólisis.",
         bsl=2, medios=["blood"], datasets=["clinical"],
         look=dict(color=(195, 200, 205), mm=(1.0, 1.6), kind="lisa", halo="alfa")),
    dict(species="Erysipelothrix rhusiopathiae", forma="Bacilo grampositivo", grupo="Erysipelotrichaceae",
         tags=["Gram +", "Colonias diminutas", "Zoonosis"],
         que_es="Bacilo grampositivo delgado que vive en cerdos, aves y peces.",
         importancia="Causa la erisipela porcina. En personas produce el erisipeloide, una lesión de la piel "
                     "típica de quienes manipulan carne o pescado.",
         colonias="Colonias diminutas (0,1–0,5 mm a las 24 h), transparentes, con una zona estrecha de hemólisis "
                  "alfa a las 48 h.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(185, 190, 200), mm=(0.3, 0.6), kind="puntiforme", halo="alfa")),
    dict(species="Escherichia coli", forma="Bacilo gramnegativo", grupo="Enterobacteria",
         tags=["Gram −", "Lactosa +", "Indicador fecal"],
         que_es="Bacilo gramnegativo móvil y anaerobio facultativo del intestino de los animales de sangre "
                "caliente.",
         importancia="Es el indicador de contaminación fecal en agua y alimentos. Algunas cepas causan diarrea, "
                     "infecciones urinarias, sepsis o, como la O157:H7, síndrome urémico hemolítico.",
         colonias="Colonias grandes (2–3 mm), grisáceas, lisas y húmedas; algunas cepas son hemolíticas en agar "
                  "sangre. En MacConkey son rosadas porque fermenta la lactosa.",
         bsl=2, medios=["nutrient", "blood"], datasets=["makrai", "clinical"],
         look=dict(color=(195, 200, 205), mm=(2.0, 3.0), kind="lisa", agar="blood")),
    dict(species="Glaesserella parasuis", forma="Cocobacilo gramnegativo", grupo="Pasteurellaceae",
         tags=["Gram −", "Requiere factor V (NAD)", "Cerdos"],
         que_es="Cocobacilo gramnegativo de las vías respiratorias del cerdo; antes se llamaba Haemophilus "
                "parasuis. Necesita NAD (factor V) para crecer.",
         importancia="Causa la enfermedad de Glässer en lechones: inflamación de las serosas, artritis y "
                     "meningitis.",
         colonias="En agar chocolate, colonias muy pequeñas y translúcidas a las 24–48 h.",
         bsl=2, medios=["chocolate"], datasets=["makrai"],
         look=dict(color=(165, 175, 185), mm=(0.4, 0.8), kind="puntiforme")),
    dict(species="Klebsiella pneumoniae", forma="Bacilo gramnegativo", grupo="Enterobacteria",
         tags=["Gram −", "Lactosa +", "Mucoide"],
         que_es="Bacilo gramnegativo inmóvil, con una cápsula gruesa que le da aspecto mucoide.",
         importancia="Causa neumonía, infecciones urinarias y bacteriemias, sobre todo en hospitales. Las cepas "
                     "productoras de carbapenemasas son de prioridad crítica para la OMS.",
         colonias="Colonias grandes, muy mucoides y brillantes; en MacConkey son rosadas porque fermenta la "
                  "lactosa. Algunas cepas forman un hilo al levantarlas con el asa.",
         bsl=2, medios=["blood", "nutrient", "MacConkey"], datasets=["makrai", "clinical"],
         look=dict(color=(150, 95, 220), mm=(2.5, 4.0), kind="mucoide", agar="MacConkey")),
    dict(species="Listeria monocytogenes", forma="Bacilo grampositivo", grupo="Listeriaceae",
         tags=["Gram +", "Crece a 4 °C", "Alimentos"],
         que_es="Bacilo grampositivo corto que puede crecer a temperatura de nevera.",
         importancia="Causa listeriosis por alimentos listos para consumir (quesos frescos, leche sin pasteurizar, "
                     "embutidos). Es grave en embarazadas, recién nacidos, personas mayores e inmunodeprimidas.",
         colonias="En agar sangre, colonias pequeñas (1–2 mm), grisáceas y translúcidas, con una zona estrecha "
                  "de hemólisis beta.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(180, 185, 195), mm=(0.9, 1.5), kind="lisa", halo="beta_estrecha")),
    dict(species="Morganella morganii", forma="Bacilo gramnegativo", grupo="Morganellaceae",
         tags=["Gram −", "Lactosa −", "Ureasa +"],
         que_es="Bacilo gramnegativo del intestino, pariente de Proteus pero sin su crecimiento en velo.",
         importancia="Causa infecciones urinarias y de heridas en pacientes hospitalizados; es resistente de forma "
                     "natural a la colistina. En el pescado produce histamina (intoxicación escombroide).",
         colonias="En agar MacConkey, colonias incoloras (no fermenta la lactosa), de 1–2 mm y lisas.",
         bsl=2, medios=["MacConkey"], datasets=["clinical"],
         look=dict(color=(190, 175, 210), mm=(1.2, 2.0), kind="lisa")),
    dict(species="Paenibacillus larvae", forma="Bacilo grampositivo", grupo="Esporulado",
         tags=["Gram +", "Abejas", "Forma esporas"],
         que_es="Bacilo grampositivo formador de esporas muy resistentes, que pueden durar décadas en la colmena.",
         importancia="Causa la loque americana, la enfermedad bacteriana más grave de las larvas de abeja; es de "
                     "declaración obligatoria en muchos países. No afecta a las personas.",
         colonias="Crecimiento lento. Colonias pequeñas, planas y grisáceas, de superficie lisa o algo rugosa.",
         bsl=1, medios=["blood"], datasets=["makrai"],
         look=dict(color=(185, 190, 200), mm=(0.8, 1.5), kind="irregular")),
    dict(species="Pasteurella multocida", forma="Cocobacilo gramnegativo", grupo="Pasteurellaceae",
         tags=["Gram −", "Oxidasa +", "Mordeduras"],
         que_es="Cocobacilo gramnegativo de la boca y las vías respiratorias de muchos animales, incluidos perros "
                "y gatos.",
         importancia="Causa cólera aviar, neumonías en bovinos y cerdos y rinitis atrófica porcina. En personas, "
                     "infecciones de heridas por mordeduras o arañazos de mascotas.",
         colonias="En agar sangre, colonias de 1–2 mm, grisáceas, lisas y no hemolíticas, con olor "
                  "característico. No crece en agar MacConkey.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(185, 190, 198), mm=(1.0, 1.8), kind="lisa")),
    dict(species="Proteus mirabilis", forma="Bacilo gramnegativo", grupo="Morganellaceae",
         tags=["Gram −", "Swarming", "Ureasa +"],
         que_es="Bacilo gramnegativo muy móvil del intestino. Su ureasa alcaliniza la orina.",
         importancia="Causa infecciones urinarias, sobre todo con sonda, y favorece los cálculos de estruvita.",
         colonias="En agar sangre se extiende como un velo en ondas concéntricas (swarming) que cubre la placa y "
                  "dificulta contar otras colonias. En MacConkey el velo se inhibe: colonias incoloras (no "
                  "fermenta la lactosa). Olor característico.",
         bsl=2, medios=["MacConkey"], datasets=["makrai"],
         look=dict(color=(195, 175, 210), mm=(1.5, 2.5), kind="lisa")),
    dict(species="Pseudomonas aeruginosa", forma="Bacilo gramnegativo", grupo="No fermentador",
         tags=["Gram −", "Aerobio estricto", "Pigmento verde"],
         que_es="Bacilo gramnegativo aerobio estricto, muy común en suelo y agua, que crece incluso a 42 °C.",
         importancia="Patógeno oportunista en hospitales (neumonía, quemaduras, fibrosis quística) con "
                     "resistencia natural a muchos antibióticos; las cepas resistentes a carbapenémicos son "
                     "prioridad para la OMS.",
         colonias="Colonias planas, extendidas, de borde irregular y brillo metálico, con hemólisis beta en agar "
                  "sangre. Produce pigmentos que tiñen el agar de verde azulado y un olor afrutado.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(150, 185, 160), mm=(2.0, 3.5), kind="irregular", halo="beta", tinte=(110, 120, 60))),
    dict(species="Pseudomonas putida", forma="Bacilo gramnegativo", grupo="No fermentador",
         tags=["Gram −", "Suelo", "Biotecnología"],
         que_es="Bacilo gramnegativo del suelo, muy versátil para degradar compuestos; se usa en "
                "biorremediación y biotecnología.",
         importancia="Rara vez causa infecciones, casi siempre en pacientes con catéteres o defensas bajas.",
         colonias="En agar sangre, colonias lisas y no hemolíticas. Produce un pigmento amarillo verdoso "
                  "fluorescente (pioverdina) pero no el azul de P. aeruginosa, y no crece a 42 °C.",
         bsl=1, medios=["blood"], datasets=["clinical"],
         look=dict(color=(170, 205, 200), mm=(1.5, 2.5), kind="lisa")),
    dict(species="Rhodococcus equi", forma="Cocobacilo grampositivo", grupo="Actinomiceto",
         tags=["Gram +", "Color salmón", "Potros"],
         que_es="Cocobacilo grampositivo del suelo y del estiércol, que sobrevive dentro de los macrófagos.",
         importancia="Causa neumonía con abscesos en potros de 1 a 6 meses. En personas, sobre todo en "
                     "inmunodeprimidas.",
         colonias="Colonias mucoides, irregulares, que parecen gotas, de color salmón o rosado que se intensifica "
                  "a los 3–4 días.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(140, 165, 235), mm=(2.0, 3.5), kind="mucoide")),
    dict(species="Salmonella enterica", forma="Bacilo gramnegativo", grupo="Enterobacteria",
         tags=["Gram −", "Lactosa −", "H₂S +"],
         que_es="Bacilo gramnegativo móvil con miles de serotipos (Enteritidis, Typhimurium, Typhi…).",
         importancia="Causa salmonelosis transmitida por alimentos (huevos, pollo, carne) y, el serotipo Typhi, "
                     "la fiebre tifoidea.",
         colonias="En agar SS, colonias incoloras (no fermenta la lactosa) con el centro negro por la producción "
                  "de ácido sulfhídrico. En agar nutritivo, colonias grises y lisas de 2–3 mm.",
         bsl=2, medios=["nutrient", "Salmonella-Shigella"], datasets=["makrai", "clinical"],
         look=dict(color=(205, 210, 220), mm=(1.5, 2.5), kind="lisa", centro=(40, 40, 45),
                   agar="Salmonella-Shigella")),
    dict(species="Serratia marcescens", forma="Bacilo gramnegativo", grupo="Yersiniaceae",
         tags=["Gram −", "Pigmento rojo", "Hospitalario"],
         que_es="Bacilo gramnegativo ambiental; algunas cepas producen un pigmento rojo (prodigiosina), sobre todo "
                "a temperatura ambiente (25–30 °C).",
         importancia="Causa brotes de infección en hospitales (unidades neonatales, catéteres, respiradores).",
         colonias="En agar MacConkey, colonias incoloras o de fermentación tardía; algunas cepas se ven rojas o "
                  "rosadas.",
         bsl=2, medios=["MacConkey"], datasets=["clinical"],
         look=dict(color=(70, 60, 200), mm=(1.5, 2.5), kind="lisa")),
    dict(species="Staphylococcus aureus", forma="Coco grampositivo", grupo="Estafilococo",
         tags=["Gram +", "Coagulasa +", "Hemólisis beta"],
         que_es="Coco grampositivo que se agrupa en racimos. Vive en la piel y la nariz de muchas personas.",
         importancia="Causa desde infecciones de piel hasta neumonía, endocarditis e intoxicación alimentaria por "
                     "sus toxinas. Las cepas resistentes a meticilina (SARM) son prioridad para la OMS.",
         colonias="En agar sangre, colonias de 1–3 mm, lisas, brillantes y convexas, de color crema a amarillo "
                  "dorado, casi siempre rodeadas de hemólisis beta.",
         bsl=2, medios=["blood"], datasets=["makrai", "clinical"],
         look=dict(color=(140, 210, 235), mm=(1.5, 2.5), kind="lisa", halo="beta")),
    dict(species="Staphylococcus epidermidis", forma="Coco grampositivo", grupo="Estafilococo coagulasa negativo",
         tags=["Gram +", "Coagulasa −", "Biopelículas"],
         que_es="Coco grampositivo de la piel, el estafilococo más abundante en el cuerpo humano.",
         importancia="Forma biopelículas sobre catéteres, válvulas y prótesis y causa infecciones asociadas a "
                     "ellos. Es también el contaminante más frecuente de los hemocultivos.",
         colonias="En agar sangre, colonias blancas, lisas, de 1–2 mm y sin hemólisis.",
         bsl=2, medios=["blood"], datasets=["clinical"],
         look=dict(color=(225, 230, 235), mm=(1.2, 2.0), kind="lisa")),
    dict(species="Staphylococcus hyicus", forma="Coco grampositivo", grupo="Estafilococo",
         tags=["Gram +", "Cerdos", "Coagulasa variable"],
         que_es="Coco grampositivo de la piel del cerdo.",
         importancia="Causa la epidermitis exudativa del lechón («enfermedad del cerdo grasiento»), por sus "
                     "toxinas exfoliativas.",
         colonias="En agar sangre, colonias blancas, lisas, de 1–2 mm, sin pigmento y sin hemólisis.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(215, 222, 228), mm=(1.2, 2.0), kind="lisa")),
    dict(species="Stenotrophomonas maltophilia", forma="Bacilo gramnegativo", grupo="No fermentador",
         tags=["Gram −", "Oxidasa −", "Resistencia intrínseca"],
         que_es="Bacilo gramnegativo ambiental (agua, suelo, grifos y equipos húmedos).",
         importancia="Causa infecciones en pacientes con ventilación mecánica o defensas bajas. Es resistente de "
                     "forma natural a los carbapenémicos, lo que limita el tratamiento.",
         colonias="En agar MacConkey, colonias incoloras (no fermenta la lactosa); en agar sangre pueden verse "
                  "amarillo pálido o lavanda, con olor a amoníaco.",
         bsl=2, medios=["MacConkey"], datasets=["clinical"],
         look=dict(color=(175, 185, 205), mm=(1.2, 2.0), kind="lisa")),
    dict(species="Streptococcus agalactiae", forma="Coco grampositivo", grupo="Estreptococo del grupo B",
         tags=["Gram +", "CAMP +", "Embarazo"],
         que_es="Coco grampositivo en cadenas que coloniza el intestino y la vagina de muchas personas sanas.",
         importancia="Causa sepsis y meningitis en recién nacidos; por eso se busca en las embarazadas al final "
                     "del embarazo. En el ganado causa mastitis.",
         colonias="En agar sangre, colonias de 1–2 mm, grisáceas y brillantes, con una zona estrecha de hemólisis "
                  "beta o sin ella.",
         bsl=2, medios=["blood"], datasets=["makrai", "clinical"],
         look=dict(color=(195, 200, 205), mm=(1.0, 1.6), kind="lisa", halo="beta_estrecha")),
    dict(species="Streptococcus pneumoniae", forma="Coco grampositivo", grupo="Neumococo",
         tags=["Gram +", "Hemólisis alfa", "Optoquina sensible"],
         que_es="Coco grampositivo que se agrupa en parejas (diplococo); muchas cepas tienen cápsula.",
         importancia="Principal causa de neumonía adquirida en la comunidad, y también de otitis, sinusitis y "
                     "meningitis. Hay vacunas contra sus serotipos más frecuentes.",
         colonias="Colonias pequeñas (≈1 mm) rodeadas de un halo verdoso de hemólisis alfa; con el tiempo se "
                  "hunden en el centro (aspecto de ficha de damas). Crece mejor con CO₂.",
         bsl=2, medios=["blood"], datasets=["clinical"],
         look=dict(color=(175, 190, 190), mm=(0.8, 1.2), kind="umbilicada", halo="alfa")),
    dict(species="Streptococcus pyogenes", forma="Coco grampositivo", grupo="Estreptococo del grupo A",
         tags=["Gram +", "Hemólisis beta", "Bacitracina sensible"],
         que_es="Coco grampositivo en cadenas, exclusivo del ser humano.",
         importancia="Causa faringitis («amigdalitis estreptocócica»), impétigo, escarlatina y, rara vez, fascitis "
                     "necrotizante; sus secuelas incluyen la fiebre reumática.",
         colonias="Colonias pequeñas (0,5–1 mm), grisáceas, rodeadas de un halo amplio y transparente de "
                  "hemólisis beta.",
         bsl=2, medios=["blood"], datasets=["clinical"],
         look=dict(color=(200, 205, 210), mm=(0.6, 1.0), kind="puntiforme", halo="beta_amplia")),
    dict(species="Trueperella pyogenes", forma="Bacilo grampositivo", grupo="Actinomiceto",
         tags=["Gram +", "Abscesos", "Rumiantes"],
         que_es="Bacilo grampositivo de las mucosas del ganado; antes se llamaba Arcanobacterium pyogenes.",
         importancia="Causa abscesos, mastitis, metritis y neumonías en bovinos, ovinos y cerdos.",
         colonias="Colonias diminutas a las 24 h (puntiformes), con hemólisis beta; crecen mejor a las 48 h y "
                  "con CO₂.",
         bsl=2, medios=["blood"], datasets=["makrai"],
         look=dict(color=(195, 200, 205), mm=(0.4, 0.8), kind="puntiforme", halo="beta")),
]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _micro_entry(m: dict) -> dict:
    medios = " y ".join(MEDIOS[x] for x in m["medios"])
    datos = " y ".join(DATASETS[d] for d in m["datasets"])
    medio_img = MEDIOS[m["look"].get("agar", m["medios"][0])]
    return {
        "id": _slug(m["species"]), "category": "microorganismos", "species": m["species"],
        "title": m["species"], "subtitle": f"{m['forma']} · {m['grupo']}",
        "tags": [*m["tags"], f"Bioseguridad {m['bsl']}"],
        "image_caption": f"Ilustración orientativa de sus colonias en {medio_img} (no es una foto real).",
        "sections": [
            ["Qué es", m["que_es"]],
            ["Por qué importa", m["importancia"]],
            ["Cómo son sus colonias", m["colonias"]],
            ["Bioseguridad", BIOSEGURIDAD[m["bsl"]] + " Sigue siempre la normativa de tu laboratorio."],
            ["En Bioyologic", f"El clasificador aprendió esta especie con fotos de placas en {medios} "
             f"({datos}). Si tu placa es de otro medio o de otra especie, la predicción puede fallar: es un dato "
             "orientativo y la identificación se confirma con pruebas microbiológicas."],
        ],
    }


# ------------------------------------------------------------------ protocolos y guías
OTRAS: list[dict] = [
    # Protocolos de laboratorio
    {
        "id": "diluciones", "category": "protocolos", "icon": "diluciones",
        "title": "Diluciones seriadas decimales", "subtitle": "Protocolo · Preparar la muestra",
        "tags": ["10⁻¹ a 10⁻⁸", "Diluyente estéril"],
        "sections": [
            ["Para qué", "Bajar la concentración de microorganismos hasta obtener placas con 30–300 colonias, "
             "que son las que se pueden contar con confianza."],
            ["Materiales", "Tubos con 9 mL de diluyente estéril (solución salina 0,85 % o agua de peptona), "
             "micropipeta de 1 mL con puntas estériles, vórtex y gradilla."],
            ["Paso a paso", "1. Rotula los tubos 10⁻¹, 10⁻², 10⁻³… antes de empezar.\n2. Pasa 1 mL de la "
             "muestra al primer tubo: es la dilución 10⁻¹.\n3. Agita 5–10 s en el vórtex.\n4. Con una punta "
             "nueva, pasa 1 mL de ese tubo al siguiente (10⁻²) y agita.\n5. Repite hasta la dilución que "
             "necesites.\n6. Siembra al menos dos diluciones seguidas, por duplicado."],
            ["Cómo elegir qué sembrar", "Si esperas unas 10⁶ UFC/mL y siembras 0,1 mL, la dilución 10⁻³ dará "
             "unas 100 colonias. Si no sabes cuánto esperar, siembra un rango amplio (p. ej. 10⁻² a 10⁻⁶)."],
            ["Errores frecuentes", "No cambiar de punta (arrastra bacterias y sobrestima el recuento), no agitar "
             "y tardar más de 15 minutos entre la dilución y la siembra."],
        ],
    },
    {
        "id": "siembra-superficie", "category": "protocolos", "icon": "siembra",
        "title": "Siembra en superficie", "subtitle": "Protocolo · Extensión con asa de Drigalski",
        "tags": ["0,1 mL", "Asa de Drigalski"],
        "sections": [
            ["Para qué", "Repartir un volumen conocido de muestra sobre el agar para obtener colonias aisladas, "
             "en la superficie, con su forma y color característicos. Es la siembra ideal para Bioyologic."],
            ["Paso a paso", "1. Usa placas con el agar seco, sin gotas.\n2. Rotula la placa por debajo (código, "
             "dilución y fecha), sin tapar el agar.\n3. Deposita 0,1 mL de la dilución en el centro.\n"
             "4. Extiende con el asa de Drigalski estéril girando la placa hasta que el líquido se absorba.\n"
             "5. Deja secar 5 minutos con la tapa puesta.\n6. Incuba la placa invertida (tapa abajo)."],
            ["En Bioyologic", "Indica volumen = 0,1 mL y la dilución sembrada; así la app calcula las UFC/mL."],
        ],
    },
    {
        "id": "siembra-profundidad", "category": "protocolos", "icon": "siembra",
        "title": "Siembra en profundidad", "subtitle": "Protocolo · Vertido en placa",
        "tags": ["1 mL", "Agar a 45 °C", "ISO 4833-1"],
        "sections": [
            ["Para qué", "Contar microorganismos en 1 mL de muestra mezclándola con el agar. Es el método de "
             "referencia de la ISO 4833-1 para el recuento de aerobios mesófilos en alimentos."],
            ["Paso a paso", "1. Pipetea 1 mL de la dilución en una placa vacía.\n2. Añade 15–20 mL de agar "
             "fundido y enfriado a 44–47 °C.\n3. Mezcla con movimientos suaves en forma de ocho.\n4. Deja "
             "solidificar e incuba invertida."],
            ["Ten en cuenta", "Las colonias que crecen dentro del agar son pequeñas y lenticulares: Bioyologic las "
             "cuenta, pero su forma, borde y especie no son comparables con las de una siembra en superficie."],
        ],
    },
    {
        "id": "incubacion", "category": "protocolos", "icon": "incubacion",
        "title": "Tiempos y temperaturas de incubación", "subtitle": "Protocolo · Cuándo leer las placas",
        "tags": ["24–72 h", "30–37 °C"],
        "sections": [
            ["Por qué importa", "Si lees antes de tiempo, las colonias pequeñas aún no se ven y el conteo sale "
             "bajo. Si lees tarde, las colonias crecen, se juntan y la placa puede volverse incontable."],
            ["Referencias habituales", "• Aerobios mesófilos en alimentos (ISO 4833-1): 30 °C, 72 h.\n"
             "• Coliformes (ISO 4832): 30 o 37 °C, 24 h.\n• E. coli β-glucuronidasa positiva (ISO 16649-2): "
             "44 °C, 18–24 h.\n• Mohos y levaduras (ISO 21527): 25 °C, 5 días.\n• Cultivos clínicos de rutina: "
             "35–37 °C, 18–48 h.\nSigue siempre el método que indique tu protocolo o la norma aplicable."],
            ["En Bioyologic", "Registra la siembra en Inicio → Incubación: la app te avisa cuando las placas estén "
             "listas y guarda en el informe cuántas horas incubaron de verdad."],
        ],
    },
    {
        "id": "calculo-ufc", "category": "protocolos", "icon": "calculo",
        "title": "Cálculo de UFC/mL", "subtitle": "Protocolo · Una placa y varias placas (ISO 4833-1)",
        "tags": ["30–300 colonias", "Fórmula"],
        "sections": [
            ["Una placa", "UFC/mL = colonias / (dilución × volumen sembrado en mL).\nEjemplo: 150 colonias en "
             "10⁻⁴ sembrando 0,1 mL → 150 / (10⁻⁴ × 0,1) = 1,5 × 10⁷ UFC/mL."],
            ["Varias placas de una muestra", "Con diluciones seguidas y réplicas, la ISO 4833-1 combina las "
             "placas contables de las dos diluciones más concentradas:\nN = ΣC / Σ(V × d)\nEjemplo: 10⁻³: 280 y "
             "260 colonias; 10⁻⁴: 33 y 30; V = 0,1 mL → N = 603 / 0,00022 ≈ 2,7 × 10⁶ UFC/mL."],
            ["Rango contable", "Usa placas con 30–300 colonias. Con menos de 30, el resultado es solo estimado; "
             "con más de 300, la placa es incontable y hay que repetir con una dilución mayor."],
            ["En Bioyologic", "Pon el mismo nombre de muestra a todas sus placas: la app aplica esta regla sola, te "
             "dice qué placas usó y te avisa si dos réplicas difieren más de lo esperable o si las diluciones no "
             "son coherentes."],
        ],
    },
    {
        "id": "controles", "category": "protocolos", "icon": "control",
        "title": "Controles de calidad del recuento", "subtitle": "Protocolo · Para confiar en el resultado",
        "tags": ["Blanco", "Duplicados"],
        "sections": [
            ["Control de esterilidad", "Incuba una placa sin sembrar de cada lote de medio y una con 0,1 mL del "
             "diluyente solo. Deben quedar sin colonias; si crecen, el material está contaminado."],
            ["Duplicados", "Siembra cada dilución por duplicado. Dos réplicas deben dar conteos parecidos: "
             "Bioyologic avisa si la diferencia supera lo esperable por azar (prueba de Poisson)."],
            ["Coherencia entre diluciones", "Entre dos diluciones decimales seguidas el conteo debe bajar unas 10 "
             "veces. Si no, revisa el pipeteo, la agitación o si hay colonias que se juntan."],
            ["Cepa de referencia", "De vez en cuando, cuenta una cepa control conocida para comprobar el medio, la "
             "incubación y el método."],
        ],
    },
    # Guías de uso de Bioyologic
    {
        "id": "flujo-completo", "category": "guias", "icon": "flujo",
        "title": "De la muestra al resultado", "subtitle": "Guía · El flujo completo en Bioyologic",
        "tags": ["Paso a paso"],
        "sections": [
            ["1. Antes de sembrar", "Crea un proyecto para el experimento (p. ej. «Agua del río, octubre») y, si "
             "trabajas en equipo, invita a tus compañeros desde el ícono de equipo."],
            ["2. Siembra", "Prepara las diluciones y siembra en superficie. Registra la siembra en Inicio → "
             "Incubación con las horas y la temperatura."],
            ["3. Lectura", "Cuando la app avise, abre la tarjeta de la siembra y toca «Analizar placa». Toma la "
             "foto dentro de la caja de iluminación."],
            ["4. Datos", "Indica la dilución, el volumen y el nombre de la muestra (el mismo en todas sus placas)."],
            ["5. Revisión", "Lee los avisos de calidad, revisa las colonias marcadas y corrige el conteo si hace "
             "falta. En equipo, un revisor aprueba o devuelve el análisis."],
            ["6. Resultado", "En Proyectos → la muestra verás la UFC/mL combinada. Descarga el informe PDF o "
             "exporta todo a Excel."],
        ],
    },
    {
        "id": "fotografiar", "category": "guias", "icon": "foto",
        "title": "Fotografiar con la caja de iluminación", "subtitle": "Guía · Fotos que se cuentan bien",
        "tags": ["Caja", "Encuadre", "Problemas comunes"],
        "sections": [
            ["Montaje", "Placa cerrada en el centro del fondo negro, anillo LED encendido apuntando al difusor y "
             "tapa puesta. Apoya el celular sobre el agujero de la tapa, sin zoom."],
            ["Encuadre", "El borde de la placa debe tocar el círculo guía: así la app sabe que 90 mm de placa "
             "ocupan el 80 % de la foto y mide las colonias en milímetros. Toca la pantalla para enfocar."],
            ["Sin caja", "Usa luz natural indirecta, un fondo oscuro mate y el celular paralelo a la placa. "
             "Evita el flash y las lámparas que se reflejen en la tapa."],
            ["Problemas comunes", "• Gotas en la tapa: deja la placa unos minutos a temperatura ambiente o "
             "límpiala por fuera.\n• Texto escrito encima del agar: escribe siempre por debajo y en el borde.\n"
             "• Agar muy oscuro (sangre, chocolate): sube la luz; las colonias deben contrastar con el fondo."],
        ],
    },
    {
        "id": "avisos-calidad", "category": "guias", "icon": "avisos",
        "title": "Qué significan los avisos de calidad", "subtitle": "Guía · Antes de confiar en el número",
        "tags": ["Borrosa", "Reflejos", "Descentrada"],
        "sections": [
            ["Borrosa", "La foto no tiene nitidez suficiente y las colonias pequeñas pueden perderse o unirse. "
             "Toca la pantalla para enfocar y no muevas el celular."],
            ["Oscura", "Falta luz y las colonias se confunden con el agar. Usa la caja de iluminación o más luz "
             "indirecta."],
            ["Reflejos", "Hay zonas blancas brillantes que el modelo puede contar como colonias (en una prueba, "
             "una placa de 30 colonias se contó como 33). Evita la luz directa o corrige el conteo."],
            ["Descentrada o lejos", "La placa no está centrada o se ve pequeña: la escala en mm deja de ser "
             "exacta y se pierden detalles. Ajusta la placa al círculo guía."],
            ["No se distingue la placa", "La app no encuentra el borde: revisa el encuadre y el fondo."],
            ["Qué hacer", "El conteo se hace igual, pero si hay avisos lo mejor es repetir la foto. Si no puedes, "
             "revisa las colonias marcadas y usa «Corregir conteo»."],
        ],
    },
    {
        "id": "corregir-conteo", "category": "guias", "icon": "corregir",
        "title": "Cuándo y cómo corregir el conteo", "subtitle": "Guía · Corrección manual con trazabilidad",
        "tags": ["Quitar", "Agregar", "Trazabilidad"],
        "sections": [
            ["Cuándo corregir", "• Reflejos, burbujas o polvo marcados como colonias.\n• Colonias pegadas que se "
             "contaron como una sola.\n• Colonias en el borde de la placa o muy pequeñas que el modelo no vio.\n"
             "• Texto o marcas sobre el agar."],
            ["Cómo", "En el resultado, toca «Corregir conteo». En modo Quitar, toca las detecciones erróneas (se "
             "tachan en rojo). En modo Agregar, toca las colonias que faltan (aparecen en naranja). Guarda: la "
             "app recalcula las UFC/mL."],
            ["Trazabilidad", "La corrección queda registrada con quién la hizo, cuándo y qué cambió, también en "
             "el PDF. Siempre se puede deshacer, porque se guardan las detecciones originales del modelo."],
        ],
    },
    {
        "id": "morfologia", "category": "guias", "icon": "morfologia",
        "title": "Interpretar la morfología", "subtitle": "Guía · Tamaño, forma, borde y color",
        "tags": ["Forma", "Borde", "Color"],
        "sections": [
            ["Tamaño", "Diámetro equivalente en mm (2 × √(área/π)), calculado con la escala del círculo guía. Si "
             "la foto no tiene escala, se muestra en píxeles."],
            ["Forma", "Puntiforme si mide menos de 1 mm; circular si su circularidad (4π × área / perímetro²) es "
             "≥ 0,80 y la relación de aspecto ≤ 1,25; si no, irregular."],
            ["Borde", "Entero si la solidez (área / área de su envolvente convexa) es ≥ 0,95; ondulado si es ≥ "
             "0,85; lobulado si es menor."],
            ["Color", "Color medio de la colonia en el espacio CIE L*a*b* y su nombre aproximado. Depende de la "
             "luz y del medio: compara solo fotos tomadas en las mismas condiciones."],
            ["Lo que no mide", "La elevación (plana, convexa…) y la textura al tacto: requieren mirar la placa "
             "de lado."],
        ],
    },
    {
        "id": "especie-probable", "category": "guias", "icon": "especie",
        "title": "Cómo leer la especie probable", "subtitle": "Guía · Alcance y límites del clasificador",
        "tags": ["37 especies", "Orientativo"],
        "sections": [
            ["Cómo se calcula", "Cada colonia se clasifica por separado y la placa promedia las probabilidades de "
             "todas. Si la especie ganadora no llega al 40 %, la app dice «no identificada» en lugar de adivinar."],
            ["Qué tan bien funciona", "En las placas de prueba acertó el 96,4 % de las colonias y la especie de "
             "todas las placas. Pero esas placas eran de los mismos medios y especies del entrenamiento."],
            ["Sus límites", "Solo conoce 37 especies (ver Microorganismos), fotografiadas sobre todo en agar "
             "sangre, chocolate, MacConkey, SS y nutritivo. En otro medio, en cultivos mixtos o con una especie "
             "que no conoce, puede equivocarse con seguridad aparente."],
            ["Cómo usarla", "Como una pista para decidir qué pruebas hacer (Gram, catalasa, oxidasa, pruebas "
             "bioquímicas o MALDI-TOF), nunca como identificación definitiva ni como diagnóstico."],
        ],
    },
    {
        "id": "equipo", "category": "guias", "icon": "equipo",
        "title": "Trabajo en equipo y revisión", "subtitle": "Guía · Proyectos compartidos",
        "tags": ["Analista", "Revisor"],
        "sections": [
            ["Roles", "Dueño: crea el proyecto e invita. Analista: ve las placas del proyecto y agrega las suyas. "
             "Revisor: además corrige y aprueba o devuelve los análisis de los demás."],
            ["Revisión", "Los análisis de otros miembros quedan pendientes. El revisor los aprueba o los devuelve "
             "con una nota de qué corregir. Nadie aprueba su propio análisis, y si un conteo aprobado se corrige, "
             "vuelve a quedar pendiente."],
            ["Privacidad", "Los miembros ven las placas del proyecto y los nombres; el correo solo lo ve el dueño. "
             "Lo que no está en un proyecto compartido sigue siendo privado."],
        ],
    },
    {
        "id": "bioseguridad", "category": "guias", "icon": "bioseguridad",
        "title": "Bioseguridad al fotografiar placas", "subtitle": "Guía · Buenas prácticas",
        "tags": ["Placa cerrada", "Residuos"],
        "sections": [
            ["Placa cerrada", "Fotografía siempre la placa con la tapa puesta: Bioyologic está pensado para eso. "
             "Si necesitas abrirla, hazlo dentro de la cabina de bioseguridad."],
            ["El celular", "No lo apoyes sobre la mesa de trabajo ni lo toques con guantes contaminados. Límpialo "
             "con alcohol al 70 % al terminar."],
            ["Nivel de cada microorganismo", "Cada ficha de Microorganismos indica su nivel de bioseguridad. La "
             "mayoría son de nivel 2; el género Brucella requiere nivel 3."],
            ["Residuos", "Desecha placas y material contaminado en bolsas de riesgo biológico para su "
             "esterilización en autoclave."],
        ],
    },
]

ENTRIES: list[dict] = sorted((_micro_entry(m) for m in MICROS), key=lambda e: e["title"]) + OTRAS

CATEGORIES = {"microorganismos": "Microorganismos", "protocolos": "Protocolos", "guias": "Guías de uso"}

_LOOKS = {_slug(m["species"]): m for m in MICROS}


def get_entry(entry_id: str) -> dict | None:
    return next((e for e in ENTRIES if e["id"] == entry_id), None)


# ------------------------------------------------------------------ ilustraciones
_AGAR_BGR = {
    "blood": (38, 32, 150), "chocolate": (45, 62, 98), "MacConkey": (120, 60, 175),
    "Salmonella-Shigella": (95, 135, 215), "nutrient": (150, 195, 220),
}
_PX_MM = 16.0  # la ilustración muestra unos 30 mm de placa en 480 px


def _colonia(img, rng, cx, cy, r, look, agar):
    """Dibuja una colonia con su halo de hemólisis, forma y brillo."""
    halo = look.get("halo")
    if halo:
        ancho = {"beta": 1.9, "beta_amplia": 3.0, "beta_estrecha": 1.35, "beta_debil": 1.5,
                 "alfa": 1.6, "doble": 2.4}[halo]
        capa = img.copy()
        if halo == "alfa":
            color = tuple(int(0.55 * a + 0.45 * b) for a, b in zip(agar, (60, 120, 70)))
        else:
            fuerza = 0.25 if halo == "beta_debil" else 0.5
            color = tuple(int(a + fuerza * (235 - a) * (1 if i == 2 else 0.6)) for i, a in enumerate(agar))
        cv2.circle(capa, (cx, cy), int(r * ancho), color, -1, cv2.LINE_AA)
        if halo == "doble":
            cv2.circle(capa, (cx, cy), int(r * 1.5), tuple(int(a + 0.6 * (240 - a)) for a in agar), -1, cv2.LINE_AA)
        cv2.addWeighted(capa, 0.55, img, 0.45, 0, img)
    kind = look.get("kind", "lisa")
    n = 64
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    if kind in ("irregular", "seca"):
        # Borde irregular natural: suma de ondulaciones de distinta frecuencia y fase.
        rad = r * (1 + sum(rng.uniform(0.02, 0.09) / np.sqrt(k) * np.sin(k * ang + rng.uniform(0, 6))
                           for k in range(2, 9)))
    else:
        rad = r * (1 + 0.03 * np.sin(3 * ang + rng.uniform(0, 6)))
    pts = np.stack([cx + rad * np.cos(ang), cy + rad * np.sin(ang)], 1).astype(np.int32)
    color = np.array(look["color"], np.float32) * rng.uniform(0.94, 1.04)
    cv2.fillPoly(img, [pts], tuple(int(c) for c in np.clip(color, 0, 255)), cv2.LINE_AA)
    if kind != "seca":  # brillo de colonia húmeda
        cv2.circle(img, (int(cx - r * 0.3), int(cy - r * 0.3)), max(1, int(r * (0.35 if kind == "mucoide" else 0.22))),
                   (245, 248, 250), -1, cv2.LINE_AA)
    if kind == "umbilicada":
        cv2.circle(img, (cx, cy), max(1, int(r * 0.4)), tuple(int(c * 0.8) for c in look["color"]), -1, cv2.LINE_AA)
    if look.get("centro"):
        cv2.circle(img, (cx, cy), max(1, int(r * 0.45)), look["centro"], -1, cv2.LINE_AA)


def _ilustracion(look: dict, medio: str, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    size = 480
    agar = _AGAR_BGR[medio]
    if look.get("tinte"):  # pigmento que difunde en el agar
        agar = tuple(int(0.6 * a + 0.4 * t) for a, t in zip(agar, look["tinte"]))
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    base = np.array(agar, np.float32)
    shade = 1.0 + 0.06 * np.sin(xx / 70 + yy / 95) - 0.10 * (((xx - 240) ** 2 + (yy - 240) ** 2) / 240 ** 2)
    img = np.clip(base[None, None, :] * shade[..., None] + rng.normal(0, 2.5, (size, size, 1)), 0, 255).astype(np.uint8)
    lo, hi = look["mm"]
    n = int(np.clip(220 / ((lo + hi) / 2 + 0.6) ** 1.8, 7, 70))
    puestos: list[tuple[int, int, int]] = []
    for _ in range(n * 40):
        if len(puestos) >= n:
            break
        r = int(rng.uniform(lo, hi) * _PX_MM / 2)
        x, y = int(rng.uniform(r + 12, size - r - 12)), int(rng.uniform(r + 12, size - r - 12))
        if all((x - a) ** 2 + (y - b) ** 2 > (r + c + 10) ** 2 for a, b, c in puestos):
            puestos.append((x, y, max(r, 2)))
    for x, y, r in puestos:
        _colonia(img, rng, x, y, r, look, agar)
    return img


def entry_image(entry: dict, cache_dir: Path) -> Path:
    """Imagen de la ficha: ilustración de las colonias en su medio (microorganismos) o placa genérica."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{entry['id']}-v2.jpg"
    if path.exists():
        return path
    seed = sum(map(ord, entry["id"]))
    m = _LOOKS.get(entry["id"])
    if m:
        img = _ilustracion(m["look"], m["look"].get("agar", m["medios"][0]), seed)
    else:
        img = _ilustracion(dict(color=(215, 222, 228), mm=(1.2, 2.2), kind="lisa"), "nutrient", seed)
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return path
