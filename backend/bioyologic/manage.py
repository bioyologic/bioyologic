"""Administración de la base de datos del servidor.

    python -m bioyologic.manage orphans               # cuántos datos quedaron sin dueño
    python -m bioyologic.manage claim CORREO          # se los asigna a una cuenta existente
    python -m bioyologic.manage delete-orphans --yes  # los borra (fotos incluidas)
    python -m bioyologic.manage users                 # cuentas registradas
    python -m bioyologic.manage export-coco --email CORREO   # placas corregidas → datos para reentrenar

Los datos sin dueño son los proyectos y análisis creados antes de las cuentas de usuario
(las pruebas del equipo): nadie los ve en la app hasta que se asignan o se borran.
Usa la misma carpeta que la API (variable BIOYOLOGIC_DATA).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

from .api.main import DEFAULT_DATA
from .storage import Store


def export_coco(store: Store, email: str, out: Path, project: str = "", species: str = "",
                everything: bool = False) -> tuple[int, int] | None:
    """Escribe en `out` (.zip) las fotos de una cuenta con sus colonias en formato COCO, listas para los
    notebooks de `training/` (variable EXTRA). Devuelve (placas, colonias), o None si la cuenta no existe.

    Solo entran los análisis que una persona comprobó: los que tienen el conteo corregido a mano y los
    aprobados en revisión. Con `everything` entran todos; úsalo solo si miraste cada placa, porque un análisis
    sin revisar enseña al modelo sus propios errores. Las colonias son las del conteo final (las quitadas a
    mano no están y las agregadas sí). Quedan fuera la papelera y las placas incontables.

    `species` es el nombre científico de lo sembrado en esas placas: sin él sirven para el detector (clase
    «colony»), con él también para el clasificador de especie.

    Solo se exportan las fotos de la cuenta indicada: para entrenar con las de otra persona hace falta su permiso.
    """
    users = store._all("SELECT id FROM users WHERE email = ?", (email.strip().lower(),))
    if not users:
        return None
    sql = """SELECT a.id, a.result_json, a.review_status FROM analyses a LEFT JOIN projects p ON p.id = a.project_id
             WHERE a.user_id = ? AND a.deleted_at IS NULL"""
    params: list = [users[0]["id"]]
    if project:
        sql += " AND p.name = ?"
        params.append(project)
    coco: dict = {"images": [], "annotations": [], "categories": [{"id": 1, "name": species or "colony"}]}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:   # los JPEG ya están comprimidos
        for row in store._all(sql + " ORDER BY a.id", tuple(params)):
            result = json.loads(row["result_json"])
            photo = store.image_path(row["id"], "original")
            checked = bool(result.get("correction")) or row["review_status"] == "aprobado"
            if not (checked or everything) or result["summary"].get("status") == "incontable" or not photo.exists():
                continue
            w, h = result.get("image_size") or (0, 0)
            name = f"{row['id']}.jpg"
            z.write(photo, f"images/{name}")
            coco["images"].append({"id": row["id"], "file_name": name, "width": w, "height": h})
            for c in result["colonies"]:
                x1, y1, x2, y2 = c["bbox"]
                coco["annotations"].append({
                    "id": len(coco["annotations"]) + 1, "image_id": row["id"], "category_id": 1, "iscrowd": 0,
                    "bbox": [round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)],
                    "area": round((x2 - x1) * (y2 - y1), 1)})
        z.writestr("coco.json", json.dumps(coco, ensure_ascii=False))
    return len(coco["images"]), len(coco["annotations"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bioyologic.manage", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("orphans", help="cuenta los datos sin dueño")
    claim = sub.add_parser("claim", help="asigna los datos sin dueño a una cuenta")
    claim.add_argument("email")
    delete = sub.add_parser("delete-orphans", help="borra los datos sin dueño")
    delete.add_argument("--yes", action="store_true", help="confirma el borrado")
    sub.add_parser("users", help="lista las cuentas")
    coco = sub.add_parser("export-coco", help="exporta las placas corregidas de una cuenta para reentrenar")
    coco.add_argument("--email", required=True, help="cuenta dueña de los análisis")
    coco.add_argument("--out", help="archivo .zip de salida (por defecto, entrenamiento.zip en la carpeta de datos)")
    coco.add_argument("--proyecto", default="", help="solo los análisis de este proyecto")
    coco.add_argument("--especie", default="", help="nombre científico de lo sembrado, p. ej. 'Escherichia coli'")
    coco.add_argument("--todas", action="store_true", help="incluye también los análisis sin corregir ni aprobar")
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
    elif args.cmd == "export-coco":
        out = Path(args.out) if args.out else store.root / "entrenamiento.zip"
        n = export_coco(store, args.email, out, args.proyecto, args.especie, args.todas)
        if n is None:
            print(f"No hay ninguna cuenta con el correo {args.email}", file=sys.stderr)
            store.close()
            return 1
        print(f"Exportadas {n[0]} placas con {n[1]} colonias a {out}")
        if not n[0]:
            print("Solo se exportan los análisis con el conteo corregido o aprobados en revisión "
                  "(usa --todas si comprobaste las demás placas una por una).")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
