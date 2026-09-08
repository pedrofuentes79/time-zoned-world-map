"""Genera el poster A0.

    uv run python -m planisferio.poster            # SVG + PDF + PNG a 200 dpi
    uv run python -m planisferio.poster --dpi 300  # PNG mas grande
    uv run python -m planisferio.poster --no-png   # solo vectorial

El PNG se rasteriza con Inkscape. A0 a 200 dpi son 9362x6622 px; a 300 dpi
son 139 Mpx, que muchos visores no abren comodos.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from .render import Style, render

A0 = Style(
    mode="zones", theme="cia", projection="miller",
    page_mm=(1189.0, 841.0), margin_mm=38, header_mm=80, footer_mm=78,
    hour_ruler=True, ruler_h_mm=26, show_dst=False,
    sea_zones=True, sea_fade=0.20, band_tint=False, solar_lines=True,
    label_size_pt=7.5, label_min_pop=0, offset_pt=10, ocean_pt=10,
    title_pt=44, subtitle_pt=17, legend_pt=11, credit_pt=8,
    land_edge_w=0.3, zone_edge_w=0.65, dateline_w=1.8,
    title="HUSOS HORARIOS DEL MUNDO",
    subtitle="husos reales sobre las bandas teóricas de 15°",
    credit="tzdata 2026c · timezone-boundary-builder · Natural Earth 10m",
)


def _clean_stale(keep: str) -> None:
    """Borra salidas de corridas anteriores.

    Tener dos generaciones de archivos conviviendo en out/ hizo que se
    revisara un mapa viejo creyendo que era el nuevo.
    """
    out = Path("out")
    if not out.exists():
        return
    for f in out.iterdir():
        if f.is_file() and not f.name.startswith(keep):
            f.unlink()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--formats", default="png,pdf",
                    help="png, pdf, svg separados por coma")
    # 400 dpi: a 200 una etiqueta de 2 pt medía 6 px de alto y salía como
    # manchón gris. El PDF no tiene tope y siempre es el mejor para detalle.
    ap.add_argument("--dpi", type=int, default=400)
    args = ap.parse_args()

    fmts = tuple(f.strip() for f in args.formats.split(",") if f.strip())
    _clean_stale("planisferio_a0")
    t = time.time()
    render(A0, outfile="planisferio_a0", formats=fmts, dpi=args.dpi)
    for f in fmts:
        p = Path("out") / f"planisferio_a0.{f}"
        print(f"  {p}  {p.stat().st_size / 1e6:.0f} MB")
    print(f"  {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
