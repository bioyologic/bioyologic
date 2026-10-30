"""Estadística de la validación: conteo manual vs Bioyologic vs otros softwares.

Uso:
    python docs/validation/analizar_validacion.py conteos.csv [--salida carpeta]

El CSV tiene una fila por conteo (ver plantilla_conteos.csv):

    placa,metodo,observador,conteo,segundos
    P01,manual,Laura,152,95
    P01,manual,Juan,148,110
    P01,manual,Samuel,155,102
    P01,Bioyologic,,150,5
    P01,OpenCFU,,131,20

- `metodo = manual` con varios observadores: la referencia de cada placa es el promedio de los
  observadores, y su desacuerdo entre sí mide cuánto varían las personas.
- Cualquier otro método se compara contra esa referencia, placa por placa, sobre la misma foto.
- `segundos` es opcional (tiempo por placa).

Salidas en la carpeta indicada: resultados.md (tablas y pruebas), errores_por_placa.csv,
bland_altman.png y error_por_metodo.png.

Requisitos: numpy, scipy, matplotlib.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

ALPHA = 0.05
MARGEN_EQUIVALENCIA = 5.0  # % (criterio Must have M1)


def leer(path: Path):
    """{metodo: {placa: [conteos]}}, {metodo: {placa: [segundos]}}"""
    conteos: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    tiempos: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not (row.get("conteo") or "").strip():
                continue  # fila de la plantilla aún sin llenar
            metodo, placa = row["metodo"].strip(), row["placa"].strip()
            conteos[metodo][placa].append(float(row["conteo"]))
            if (row.get("segundos") or "").strip():
                tiempos[metodo][placa].append(float(row["segundos"]))
    if not conteos:
        raise SystemExit("El CSV aún no tiene conteos: llena la columna conteo.")
    if "manual" not in conteos:
        raise SystemExit("El CSV necesita conteos con metodo = manual (la referencia).")
    return conteos, tiempos


def lin_ccc(x: np.ndarray, y: np.ndarray) -> float:
    """Coeficiente de concordancia de Lin: 1 = acuerdo perfecto (no solo correlación)."""
    mx, my = x.mean(), y.mean()
    cov = ((x - mx) * (y - my)).mean()
    return float(2 * cov / (x.var() + y.var() + (mx - my) ** 2))


def holm(pvals: list[float]) -> list[float]:
    order = np.argsort(pvals)
    adj, running = [0.0] * len(pvals), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvals) - rank) * pvals[i]))
        adj[i] = running
    return adj


def wilcoxon_p(d: np.ndarray) -> float | None:
    d = d[d != 0]
    return None if len(d) < 1 else float(stats.wilcoxon(d).pvalue)


def tost_p(pct_err: np.ndarray, margen: float) -> float | None:
    """Prueba de equivalencia (dos pruebas t de una cola): p < 0,05 = error dentro de ±margen."""
    if len(pct_err) < 3 or pct_err.std(ddof=1) == 0:
        return None
    p_inf = stats.ttest_1samp(pct_err, -margen, alternative="greater").pvalue
    p_sup = stats.ttest_1samp(pct_err, margen, alternative="less").pvalue
    return float(max(p_inf, p_sup))


def fmt_p(p: float | None) -> str:
    if p is None:
        return "n/d"
    return "p < 0,001" if p < 0.001 else "p = " + f"{p:.3f}".replace(".", ",")


def num(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # la consola de Windows no muestra ≤ ni χ² sin esto
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv", type=Path)
    ap.add_argument("--salida", type=Path, default=None, help="carpeta de resultados (por defecto, junto al CSV)")
    args = ap.parse_args(argv)
    out = args.salida or args.csv.parent / "resultados"
    out.mkdir(parents=True, exist_ok=True)

    conteos, tiempos = leer(args.csv)
    manual = conteos.pop("manual")
    ref = {p: float(np.mean(v)) for p, v in manual.items()}
    metodos = sorted(conteos, key=lambda m: (m.lower() != "bioyologic", m.lower()))
    placas = sorted(p for p in ref if all(p in conteos[m] for m in metodos))
    n = len(placas)
    if n == 0:
        raise SystemExit("No hay placas contadas por todos los métodos.")

    L = [f"# Resultados de la validación\n\n{n} placas contadas por todos los métodos: {', '.join(placas)}.\n"
         f"Referencia: promedio del conteo manual de cada placa.\n"]
    if n < 6:
        L.append(f"> **Atención:** con {n} placas la prueba de Wilcoxon no puede dar p < 0,05 (el mínimo "
                 "posible con n < 6 es mayor que 0,05). Las pruebas de significancia necesitan al menos 6 placas; "
                 "se recomiendan 10 o más.\n")

    # --- variabilidad entre personas
    obs = [v for v in manual.values() if len(v) > 1]
    if obs:
        cv = [100 * np.std(v, ddof=1) / np.mean(v) for v in obs]
        L.append(f"## Variación entre personas\n\nCoeficiente de variación entre observadores: "
                 f"**{num(np.mean(cv))} %** en promedio (rango {num(min(cv))}–{num(max(cv))} %). "
                 "Es el error típico de contar a mano: un software con un error parecido o menor iguala a las personas.\n")

    # --- métricas por método
    filas, pct, ba = [], {}, {}
    for m in metodos:
        x = np.array([ref[p] for p in placas])
        y = np.array([float(np.mean(conteos[m][p])) for p in placas])
        d, e = y - x, 100 * (y - x) / x
        pct[m], ba[m] = e, ((x + y) / 2, d)
        sd = d.std(ddof=1) if n > 1 else 0.0
        r = float(stats.pearsonr(x, y).statistic) if n > 2 else float("nan")
        t = [s for p in placas for s in tiempos[m].get(p, [])]
        filas.append({"metodo": m, "mape": np.abs(e).mean(), "sesgo": d.mean(), "sesgo_pct": e.mean(),
                      "loa": (d.mean() - 1.96 * sd, d.mean() + 1.96 * sd), "r": r, "ccc": lin_ccc(x, y),
                      "p_dif": wilcoxon_p(d), "p_eq": tost_p(e, MARGEN_EQUIVALENCIA),
                      "seg": np.mean(t) if t else None})

    t_manual = [s for v in tiempos.get("manual", {}).values() for s in v]
    L.append("## Error de cada método frente al conteo manual\n\n"
             "| Método | MAPE | Sesgo (colonias) | Sesgo (%) | Límites de acuerdo 95 % | r | CCC de Lin | "
             "¿Distinto del manual? (Wilcoxon) | ¿Equivalente ±5 %? (TOST) | Segundos por placa |\n"
             "|---|---|---|---|---|---|---|---|---|---|")
    for f in filas:
        L.append(f"| {f['metodo']} | {num(f['mape'])} % | {num(f['sesgo'])} | {num(f['sesgo_pct'])} % | "
                 f"{num(f['loa'][0])} a {num(f['loa'][1])} | {num(f['r'], 3)} | {num(f['ccc'], 3)} | "
                 f"{fmt_p(f['p_dif'])} | {fmt_p(f['p_eq'])} | "
                 f"{num(f['seg']) if f['seg'] is not None else 'n/d'} |")
    if t_manual:
        L.append(f"| Manual (referencia) | — | — | — | — | — | — | — | — | {num(np.mean(t_manual))} |")
    L.append("\n- **MAPE:** error absoluto medio en porcentaje. Meta Must have M1: ≤ 5 %.\n"
             "- **Sesgo:** si el método cuenta de más (+) o de menos (−) en promedio.\n"
             "- **Wilcoxon:** p < 0,05 indica que el método cuenta distinto del manual de forma sistemática.\n"
             "- **TOST:** p < 0,05 indica que el error está, con significancia estadística, dentro de ±5 %.\n")

    # --- comparación entre métodos
    if len(metodos) >= 2:
        abs_err = {m: np.abs(pct[m]) for m in metodos}
        L.append("## ¿Qué método se equivoca menos?\n")
        if len(metodos) >= 3 and n >= 3:
            fr = stats.friedmanchisquare(*abs_err.values())
            L.append(f"Prueba de Friedman sobre el error absoluto (%) de los {len(metodos)} métodos: "
                     f"χ² = {num(fr.statistic, 2)}, {fmt_p(fr.pvalue)}.\n")
        pares = list(itertools.combinations(metodos, 2))
        crudos = [wilcoxon_p(abs_err[a] - abs_err[b]) for a, b in pares]
        validos = [p for p in crudos if p is not None]
        ajust = iter(holm(validos)) if validos else iter([])
        L.append("| Comparación | Diferencia media del error absoluto | p (Wilcoxon, Holm) |\n|---|---|---|")
        for (a, b), p in zip(pares, crudos):
            pa = next(ajust) if p is not None else None
            L.append(f"| {a} vs {b} | {num((abs_err[a] - abs_err[b]).mean())} puntos % | {fmt_p(pa)} |")
        L.append("")

    (out / "resultados.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    with open(out / "errores_por_placa.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["placa", "referencia_manual", *[f"{m}_conteo" for m in metodos], *[f"{m}_error_pct" for m in metodos]])
        for i, p in enumerate(placas):
            w.writerow([p, round(ref[p], 2), *[round(float(np.mean(conteos[m][p])), 2) for m in metodos],
                        *[round(float(pct[m][i]), 2) for m in metodos]])

    graficas(out, metodos, pct, ba, placas)
    print((out / "resultados.md").read_text(encoding="utf-8"))
    print(f"Resultados en {out}")
    return 0


def graficas(out: Path, metodos, pct, ba, placas) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colores = ["#6B4FBB", "#E08A3C", "#2E7D5B", "#C0446B", "#3C7FC0"]
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=200)
    xs = np.arange(len(metodos))
    mape = [np.abs(pct[m]).mean() for m in metodos]
    ax.bar(xs, mape, color=colores[: len(metodos)], width=0.6)
    for i, m in enumerate(metodos):
        ax.scatter(np.full(len(placas), i) + np.random.default_rng(0).uniform(-0.12, 0.12, len(placas)),
                   np.abs(pct[m]), color="#1F1A3D", s=14, zorder=3)
        ax.text(i, mape[i], f"{mape[i]:.1f} %".replace(".", ","), ha="center", va="bottom", fontsize=10,
                fontweight="bold")
    ax.axhline(MARGEN_EQUIVALENCIA, ls="--", color="#999", lw=1)
    ax.text(-0.45, MARGEN_EQUIVALENCIA, "meta 5 %", va="bottom", ha="left", fontsize=9, color="#666")
    ax.set_xticks(xs, metodos)
    ax.set_ylabel("Error absoluto frente al conteo manual (%)")
    ax.set_title("Error por método (barra = MAPE, puntos = placas)", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "error_por_metodo.png")
    plt.close(fig)

    fig, axs = plt.subplots(1, len(metodos), figsize=(4.2 * len(metodos), 3.8), dpi=200, squeeze=False)
    for ax, m, c in zip(axs[0], metodos, colores):
        media, d = ba[m]
        sesgo, sd = d.mean(), d.std(ddof=1) if len(d) > 1 else 0.0
        ax.scatter(media, d, color=c, s=24)
        for v, ls in ((sesgo, "-"), (sesgo + 1.96 * sd, "--"), (sesgo - 1.96 * sd, "--")):
            ax.axhline(v, color="#1F1A3D", ls=ls, lw=1)
        ax.axhline(0, color="#bbb", lw=0.8)
        ax.set_title(m, fontsize=11)
        ax.set_xlabel("Promedio (método, manual)")
        ax.spines[["top", "right"]].set_visible(False)
    axs[0][0].set_ylabel("Método − manual (colonias)")
    fig.suptitle("Bland–Altman: sesgo (línea) y límites de acuerdo 95 % (discontinuas)", fontsize=11)
    fig.tight_layout()
    fig.savefig(out / "bland_altman.png")
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
