"""Genera el poster A0.

    uv run python -m planisferio.poster            # SVG + PDF + PNG a 200 dpi
    uv run python -m planisferio.poster --dpi 300  # PNG mas grande
    uv run python -m planisferio.poster --no-png   # solo vectorial

El PNG se rasteriza con Inkscape. A0 a 200 dpi son 9362x6622 px; a 300 dpi
son 139 Mpx, que muchos visores no abren comodos.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from .render import Style, render

A0 = Style(
    mode="zones", theme="cia", projection="miller",
    page_mm=(1189.0, 841.0), margin_mm=38, header_mm=80, footer_mm=78,
    hour_ruler=True, ruler_h_mm=26, show_dst=False,
    sea_zones=True, sea_fade=0.0, band_tint=False, solar_lines=True,
    label_size_pt=7.5, label_min_pop=0, offset_pt=10, ocean_pt=10,
    title_pt=44, subtitle_pt=17, legend_pt=11, credit_pt=8,
    land_edge_w=0.3, zone_edge_w=0.65, dateline_w=1.8,
    title="HUSOS HORARIOS DEL MUNDO",
    subtitle="husos reales sobre las bandas teóricas de 15°",
    credit="tzdata 2026c · timezone-boundary-builder · Natural Earth 10m",
)


def rasterize(svg: Path, dpi: int) -> Path | None:
    if shutil.which("inkscape") is None:
        print("  aviso: sin inkscape, no se genera PNG")
        return None
    png = svg.with_suffix(".png")
    subprocess.run(
        ["inkscape", "--export-type=png", f"--export-dpi={dpi}",
         f"--export-filename={png}", str(svg)],
        check=True, capture_output=True)
    mb = png.stat().st_size / 1e6
    print(f"  PNG a {dpi} dpi: {png} ({mb:.0f} MB)")
    return png


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
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args()

    _clean_stale("planisferio_a0")
    svg = render(A0, outfile="planisferio_a0")
    print(f"  vectorial: {svg} y {svg.with_suffix('.pdf')}")
    if not args.no_png:
        rasterize(svg, args.dpi)


if __name__ == "__main__":
    main()
