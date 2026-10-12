"""Lanza oracle_retry.py en segundo plano (sin ventana) y guarda su salida en oracle_retry.log.

Lo usa la tarea programada de Windows «Bioyologic Oracle» con pythonw.exe:
    .venv\\Scripts\\pythonw.exe deploy\\oracle_retry_bg.py
"""

import runpy
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

log = open(HERE / "oracle_retry.log", "a", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr = log
print(f"\n=== Inicio {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)
sys.argv = [str(HERE / "oracle_retry.py")]
runpy.run_path(str(HERE / "oracle_retry.py"), run_name="__main__")
print(f"=== Fin {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)
