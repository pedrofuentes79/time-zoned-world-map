"""Genera el poster A0. Ejecutar con: uv run python -m planisferio.poster"""
from __future__ import annotations

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

if __name__ == "__main__":
    path = render(A0, outfile="planisferio_a0")
    print(f"escrito: {path} y {path.with_suffix('.pdf')}")
