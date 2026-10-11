import os

# En los tests no se precarga el modelo real al arrancar la API.
os.environ["BIOYOLOGIC_WARMUP"] = "0"
# El límite de análisis por minuto se prueba aparte (test_rate_limit).
os.environ["BIOYOLOGIC_RATE_LIMIT"] = "0"
