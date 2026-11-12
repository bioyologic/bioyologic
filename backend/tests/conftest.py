import os

# En los tests no se precarga el modelo real al arrancar la API.
os.environ["BIOYOLOGIC_WARMUP"] = "0"
# El límite de análisis por minuto se prueba aparte (test_rate_limit).
os.environ["BIOYOLOGIC_RATE_LIMIT"] = "0"
os.environ["BIOYOLOGIC_LOGIN_LIMIT"] = "0"


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _placas_sinteticas_pequenas(monkeypatch):
    """Las placas sintéticas de las pruebas miden 600-900 px: sin esto, todas tendrían el aviso de poca
    resolución. Las pruebas de ese aviso vuelven a poner el umbral real."""
    from bioyologic.analysis import quality
    monkeypatch.setattr(quality, "PLACA_PX_MIN", 0)
