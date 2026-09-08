"""Variante en proyeccion Equal Earth.

Equal Earth es equivalente en area, asi que Africa y Sudamerica salen con su
tamano real. El costo es que los meridianos se curvan y las bandas horarias
dejan de ser columnas rectas: para un mapa de husos eso cuesta legibilidad,
por eso la version principal usa Miller. Vale la pena verla igual.

    uv run python -m planisferio.poster_ee
"""
from __future__ import annotations

import argparse
import time
from dataclasses import replace
from pathlib import Path

from .poster import A0, _clean_stale
from .render import render

EE = replace(
    A0,
    projection="equal_earth",
    drop_antarctica=True,
    # Con los meridianos curvos la regla recta de arriba deja de alinearse
    # con las bandas, asi que actua solo como clave de color.
    hour_ruler=True,
    ruler_on_top=False,
    subtitle="husos reales · proyección Equal Earth, equivalente en área",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--formats", default="png,pdf")
    ap.add_argument("--dpi", type=int, default=400)
    args = ap.parse_args()
    fmts = tuple(f.strip() for f in args.formats.split(",") if f.strip())
    _clean_stale("planisferio_equal_earth", fmts)
    t = time.time()
    render(EE, outfile="planisferio_equal_earth", formats=fmts, dpi=args.dpi)
    for f in fmts:
        p = Path("out") / f"planisferio_equal_earth.{f}"
        print(f"  {p}  {p.stat().st_size / 1e6:.0f} MB")
    print(f"  {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
