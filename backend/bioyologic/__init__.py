"""Bioyologic: sistema híbrido de conteo y caracterización de colonias bacterianas."""

import os

__version__ = "1.2.0"

# Tope de píxeles que OpenCV acepta decodificar (por defecto 1 gigapíxel = 3 GB de memoria). Un archivo de
# pocos MB puede declarar un tamaño enorme y tumbar el servidor: se limita antes de importar cv2. La API
# además rechaza antes de decodificar las fotos de más de BIOYOLOGIC_MAX_MEGAPIXELS (ver api/main.py).
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(128_000_000))
