"""Administración de la base de datos del servidor.

    python -m bioyologic.manage orphans               # cuántos datos quedaron sin dueño
    python -m bioyologic.manage claim CORREO          # se los asigna a una cuenta existente
    python -m bioyologic.manage delete-orphans --yes  # los borra (fotos incluidas)
    python -m bioyologic.manage users                 # cuentas registradas

Los datos sin dueño son los proyectos y análisis creados antes de las cuentas de usuario
(las pruebas del equipo): nadie los ve en la app hasta que se asignan o se borran.
Usa la misma carpeta que la API (variable BIOYOLOGIC_DATA).
"""

from __future__ import annotations

import argparse
import os
import sys

from .api.main import DEFAULT_DATA
from .storage import Store


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bioyologic.manage", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("orphans", help="cuenta los datos sin dueño")
    claim = sub.add_parser("claim", help="asigna los datos sin dueño a una cuenta")
    claim.add_argument("email")
    delete = sub.add_parser("delete-orphans", help="borra los datos sin dueño")
    delete.add_argument("--yes", action="store_true", help="confirma el borrado")
    sub.add_parser("users", help="lista las cuentas")
    args = ap.parse_args(argv)

    store = Store(os.environ.get("BIOYOLOGIC_DATA", DEFAULT_DATA))
    if args.cmd == "orphans":
        n = store.orphans()
        print(f"Sin dueño: {n['analyses']} análisis y {n['projects']} proyectos")
    elif args.cmd == "claim":
        rows = store._all("SELECT id FROM users WHERE email = ?", (args.email.strip().lower(),))
        if not rows:
            print(f"No hay ninguna cuenta con el correo {args.email}", file=sys.stderr)
            return 1
        n = store.assign_orphans(rows[0]["id"])
        print(f"Asignados a {args.email}: {n['analyses']} análisis y {n['projects']} proyectos")
    elif args.cmd == "delete-orphans":
        if not args.yes:
            n = store.orphans()
            print(f"Se borrarían {n['analyses']} análisis y {n['projects']} proyectos. Repite con --yes.")
            return 1
        n = store.delete_orphans()
        print(f"Borrados {n['analyses']} análisis y {n['projects']} proyectos")
    elif args.cmd == "users":
        for u in store._all("SELECT id, email, name, created_at FROM users ORDER BY id"):
            print(f"{u['id']:>4}  {u['email']:<40} {u['name']:<30} {u['created_at']}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
