"""Lanza oracle_retry.py en segundo plano (sin ventana) y guarda su salida en un archivo de registro.

Lo usan las tareas programadas de Windows «Bioyologic Oracle…» con pythonw.exe:
    .venv\\Scripts\\pythonw.exe deploy\\oracle_retry_bg.py           (cuenta DEFAULT → oracle_retry.log)
    .venv\\Scripts\\pythonw.exe deploy\\oracle_retry_bg.py FRANKFURT (perfil FRANKFURT → oracle_retry_frankfurt.log)
"""

import runpy
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILE = sys.argv[1] if len(sys.argv) > 1 else "DEFAULT"
LOG = "oracle_retry.log" if PROFILE == "DEFAULT" else f"oracle_retry_{PROFILE.lower()}.log"

log = open(HERE / LOG, "a", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr = log
print(f"\n=== Inicio {datetime.now():%Y-%m-%d %H:%M:%S} · perfil {PROFILE} ===", flush=True)
sys.argv = [str(HERE / "oracle_retry.py"), "--profile", PROFILE]
runpy.run_path(str(HERE / "oracle_retry.py"), run_name="__main__")
print(f"=== Fin {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)
