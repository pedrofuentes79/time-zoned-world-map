"""Render del planisferio de husos horarios. Todo parametrizado."""
from __future__ import annotations

import colorsys
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import matplotlib as mpl
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle
from shapely.geometry import LineString, Point, box

from .palette import (CIA, CIA_BAND_A, CIA_BAND_B, CIA_CYCLE, INK, PAPER,
                      cycle_color, lighten, offset_label,
                      zone_color)

CACHE = Path("data/cache")
OUT = Path("out")

PROJECTIONS = {
    "equirectangular": "+proj=eqc +lon_0={lon0} +datum=WGS84 +units=m +no_defs",
    "miller":          "+proj=mill +lon_0={lon0} +datum=WGS84 +units=m +no_defs",
    "equal_earth":     "+proj=eqearth +lon_0={lon0} +datum=WGS84 +units=m +no_defs",
    "robinson":        "+proj=robin +lon_0={lon0} +datum=WGS84 +units=m +no_defs",
    "natural_earth":   "+proj=natearth +lon_0={lon0} +datum=WGS84 +units=m +no_defs",
}

# Proyecciones cuyo contorno es un ovalo: recortar latitud las deforma.
PSEUDOCYLINDRICAL = {"equal_earth", "robinson", "natural_earth"}

# Claves por NAME_EN, que es unico. NAME_ES tiene colisiones (los dos San Martin)
# y podria cambiar entre versiones de Natural Earth.
NAME_OVERRIDES: dict[str, str] = {
    "Falkland Islands": "Islas Malvinas",   # anclado a proposito
    "Saint Martin":     "San Martín (FR)",  # mitad francesa
    "Sint Maarten":     "San Martín (NL)",  # mitad neerlandesa
}


@dataclass
class Style:
    mode: str = "zones"             # "zones" | "bands"
    theme: str = "cia"              # "cia" | "paper" | "ink"
    sea_zones: bool = True          # husos nauticos pintados en el oceano
    sea_fade: float = 0.25          # cuanto se aclara el huso sobre el mar.
                                    # 0 = mar y tierra identicos (el huso se
                                    # lee como un bloque, pero se pierde la
                                    # costa); alto = parecen husos distintos
    band_tint: bool = False         # bandas teoricas como fondo (redundante
                                    # si sea_zones esta activo)
    band_tint_alpha: float = 0.30   # sobre el mar; mas alto lo enturbia
    sea_color: str | None = None    # None = el del tema
    zone_offsets: bool = True       # el offset escrito en cada huso
    offset_repeat_deg: float = 34.0 # cada cuantos grados de latitud se repite
    ocean_names: bool = True
    ocean_pt: float = 9.0
    dateline: bool = True
    dateline_w: float = 1.5
    dateline_label: bool = True
    dateline_text: str = "LÍNEA INTERNACIONAL DE CAMBIO DE FECHA"
    ruler_local_time: bool = True   # hora local cuando en UTC son las 12:00
    offset_pt: float = 8.0
    offset_min_area: float = 0.0012  # fraccion del area del mapa
    # Los husos fraccionarios llevan su numero aunque sean chicos: el
    # rayado dice que son fraccionarios pero no cual fraccion, y obligar
    # a ir a la regla por cada uno no sirve.
    offset_min_area_frac: float = 0.00002
    projection: str = "miller"
    lon0: float = 0.0
    lat_limits: tuple[float, float] = (-60.0, 85.0)

    page_mm: tuple[float, float] = (1189.0, 841.0)   # A0 apaisado
    margin_mm: float = 40.0
    header_mm: float = 95.0
    footer_mm: float = 130.0

    # capas
    hour_ruler: bool = False
    ruler_h_mm: float = 16.0
    ruler_on_top: bool = False      # por defecto va debajo del mapa
    solar_lines: bool = True
    zone_edges: bool = True
    show_labels: bool = True
    show_dst: bool = False
    show_graticule: bool = False

    # trazos
    land_edge_w: float = 0.4
    zone_edge_w: float = 0.5
    graticule_alpha: float = 0.10

    # bandas (modo "bands")
    band_sat: float = 0.34
    band_val: float = 0.78
    band_alpha: float = 0.92

    dst_hatch: str = "////"
    dst_hatch_alpha: float = 0.30

    # tipografia (pt)
    label_size_pt: float = 6.5
    label_min_pop: float = 0.0   # 0 = todos los paises
    title_pt: float = 34.0
    subtitle_pt: float = 15.0
    legend_pt: float = 9.0
    credit_pt: float = 8.0

    title: str = "LA HORA Y EL SOL"
    subtitle: str = "cuánto se aparta cada reloj de su meridiano solar"
    credit: str = ""


def theme_of(s: Style) -> dict:
    return {"paper": PAPER, "ink": INK, "cia": CIA}.get(s.theme, PAPER)


def band_color(hours: float, s: Style) -> str:
    hue = ((hours % 24) / 24.0) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, s.band_sat, s.band_val)
    return mpl.colors.to_hex((r, g, b))


def effective_limits(s: Style) -> tuple[float, float]:
    """Las pseudocilindricas se dibujan enteras: cortarlas rompe el ovalo."""
    return (-90.0, 90.0) if s.projection in PSEUDOCYLINDRICAL else s.lat_limits


def _clip(gdf: gpd.GeoDataFrame, s: Style) -> gpd.GeoDataFrame:
    lo, hi = effective_limits(s)
    clipper = box(s.lon0 - 179.999, lo, s.lon0 + 179.999, hi)
    out = gdf.copy()
    out["geometry"] = out.geometry.intersection(clipper)
    return out[~out.geometry.is_empty & out.geometry.notna()]


def render(s: Style, outfile: str | None = None) -> Path:
    crs = PROJECTIONS[s.projection].format(lon0=s.lon0)
    th = theme_of(s)
    mm = 1 / 25.4

    countries = gpd.read_file(CACHE / "countries.gpkg")
    fig = plt.figure(figsize=(s.page_mm[0] * mm, s.page_mm[1] * mm))
    fig.patch.set_facecolor(th["bg"])

    # --- caja del mapa, ajustada al aspecto real de la proyeccion ---
    lo, hi = effective_limits(s)
    frame = gpd.GeoDataFrame(
        {"geometry": [box(s.lon0 - 179.999, lo, s.lon0 + 179.999, hi)]},
        crs="EPSG:4326").to_crs(crs)
    minx, miny, maxx, maxy = frame.total_bounds
    box_w = s.page_mm[0] - 2 * s.margin_mm
    box_h = s.page_mm[1] - s.footer_mm - s.header_mm
    aspect = (maxx - minx) / (maxy - miny)
    if box_w / box_h > aspect:
        h_mm, w_mm = box_h, box_h * aspect
    else:
        w_mm, h_mm = box_w, box_w / aspect

    ax = fig.add_axes(((s.page_mm[0] - w_mm) / 2 / s.page_mm[0],
                       (s.footer_mm + (box_h - h_mm) / 2) / s.page_mm[1],
                       w_mm / s.page_mm[0], h_mm / s.page_mm[1]))
    ax.set_facecolor(th["bg"])
    ax.set_axis_off()
    ax.set_aspect("equal")

    if s.mode == "zones":
        _paint_zones(ax, crs, s, th)
    else:
        _paint_bands(ax, _clip(gpd.read_file(CACHE / 'bands.gpkg'), s).to_crs(crs), crs, s)

    if s.show_dst:
        _paint_dst(ax, crs, s, th)

    _clip(countries, s).to_crs(crs).boundary.plot(
        ax=ax, color=th["land_edge"], linewidth=s.land_edge_w, alpha=0.55, zorder=6)

    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)

    if s.dateline:
        _dateline(ax, crs, s, th)
    if s.ocean_names:
        _ocean_names(ax, crs, s, th)
    if s.show_graticule:
        _graticule(ax, crs, s, th)
    if s.show_labels:
        _labels(ax, countries, crs, s, th)

    if s.hour_ruler:
        _hour_ruler(fig, s, ax, th)
    _chrome(fig, s, ax, th)

    OUT.mkdir(exist_ok=True)
    path = OUT / f"{outfile or 'planisferio'}.svg"
    fig.savefig(path, format="svg", facecolor=th["bg"])
    fig.savefig(path.with_suffix(".pdf"), format="pdf", facecolor=th["bg"])
    plt.close(fig)
    return path

def _paint_bands(ax, bands, crs, s: Style) -> None:
    for _, row in bands.iterrows():
        gpd.GeoSeries([row.geometry], crs=crs).plot(
            ax=ax, color=band_color(row["std_hours"], s),
            alpha=s.band_alpha, linewidth=0, zorder=1)


def _paint_dst(ax, crs, s: Style, th: dict) -> None:
    dst = _clip(gpd.read_file(CACHE / "dst.gpkg"), s).to_crs(crs)
    with mpl.rc_context({"hatch.color": th["hatch"], "hatch.linewidth": 0.45}):
        for _, row in dst.iterrows():
            hatch = s.dst_hatch if row["hemisphere"] == "N" else "\\\\\\\\"
            gpd.GeoSeries([row.geometry], crs=crs).plot(
                ax=ax, facecolor="none", hatch=hatch, edgecolor="none",
                linewidth=0, zorder=3, alpha=s.dst_hatch_alpha)


def _graticule(ax, crs, s: Style, th: dict) -> None:
    lo, hi = effective_limits(s)
    lines = [LineString([(lon, y) for y in np.linspace(lo, hi, 90)])
             for lon in range(-180, 181, 15)]
    lines += [LineString([(x, lat) for x in np.linspace(-179.99, 179.99, 180)])
              for lat in range(-90, 91, 15) if lo <= lat <= hi]
    gpd.GeoSeries(lines, crs="EPSG:4326").to_crs(crs).plot(
        ax=ax, color=th["label"], linewidth=0.3, alpha=s.graticule_alpha, zorder=4)


def _labels(ax, countries: gpd.GeoDataFrame, crs, s: Style, th: dict) -> None:
    from .labels import place
    path = CACHE / "labels.gpkg"
    if not path.exists():
        return
    lab = gpd.read_file(path)
    stats = place(ax, lab, crs, s, th, NAME_OVERRIDES,
                  reserved=getattr(ax, "_reserved_boxes", []))
    print(f"  rotulos: {stats['placed']} en su lugar, {stats['moved']} corridos, "
          f"{stats['dropped']} sin espacio (de {stats['total']})")


# ---------------------------------------------------------------- chrome

def _hour_ruler(fig, s: Style, ax, th: dict) -> None:
    """Regla recta de 24 columnas. Recupera la lectura en columna que las
    proyecciones de meridiano curvo rompen."""
    pos = ax.get_position()
    gap = (s.margin_mm * 0.30) / s.page_mm[1]
    h = s.ruler_h_mm / s.page_mm[1]
    y = (pos.y1 + gap) if s.ruler_on_top else (pos.y0 - gap - h)
    rax = fig.add_axes((pos.x0, y, pos.width, h))
    # El mapa cubre 360 grados = 24 horas, no 25. Las celdas de -12 y +12
    # son medias: si se dibujan enteras, la regla se corre ~1% del ancho.
    rax.set_xlim(-12.0, 12.0); rax.set_ylim(0, 1); rax.set_axis_off()
    neutral = s.mode == "zones"
    extra = _fractional_by_column()
    for k in range(-12, 13):
        if not neutral:
            face = band_color(k, s)
        elif s.theme == "cia":
            face = cycle_color(k)
        else:
            face = zone_color(k, s.theme)
        left, right = max(k - 0.5, -12.0), min(k + 0.5, 12.0)
        rax.add_patch(Rectangle((left, 0), right - left, 1, facecolor=face,
                                edgecolor=th["zone_edge"] if neutral else th["bg"],
                                linewidth=0.5, alpha=1.0 if neutral else s.band_alpha))
        subs = extra.get(k, [])
        local = s.ruler_local_time
        y_main = 0.72 if (subs or local) else 0.5
        cx = (left + right) / 2
        rax.text(cx, y_main, f"{k:+d}" if k else "0", ha="center", va="center",
                 fontsize=s.legend_pt, fontweight="bold",
                 color=th["label"] if neutral else "#10141a")
        if local:
            # Hora local en ese huso cuando en UTC son las 12:00.
            hh = 12 + k
            rax.text(cx, 0.45, f"{24 if hh == 24 else hh % 24:02d}:00",
                     ha="center", va="center", fontsize=s.legend_pt * 0.78,
                     color=th["label"], alpha=0.9)
        for j, lab in enumerate(subs):
            rax.text(cx, 0.22 - j * 0.19, lab, ha="center", va="center",
                     fontsize=s.legend_pt * 0.62, color=th["label"], alpha=0.75)


def _fractional_by_column() -> dict[int, list[str]]:
    """Offsets que no son hora entera dentro de -12..+12, listados bajo su columna.

    Los que exceden +-12 (Chatham, Kiribati, Samoa) van a la columna donde
    esta su tierra: es ahi donde la linea de cambio de fecha hace el zigzag.
    """
    z = gpd.read_file(CACHE / "zones_land.gpkg")
    out: dict[int, list[str]] = {}
    for h in sorted(float(v) for v in z["std_hours"].unique()):
        whole = h == int(h)
        if whole and -12 <= h <= 12:
            continue
        minutes = round(abs(h - int(h)) * 60)
        label = f"{int(h):+d}" + (f":{minutes:02d}" if minutes else "")
        if abs(h) > 12:
            pt = z[z["std_hours"] == h].geometry.representative_point().iloc[0]
            col = int(round(pt.x / 15))
        else:
            col = int(h)
        out.setdefault(col, []).append(label)
    return out


def _chrome(fig, s: Style, ax, th: dict) -> None:
    """Titulo, leyendas y timeline, en una grilla sin superposiciones."""
    mmx = lambda v: v / s.page_mm[0]
    mmy = lambda v: v / s.page_mm[1]
    x0 = mmx(s.margin_mm)

    fig.text(x0, 1 - mmy(s.margin_mm), s.title, fontsize=s.title_pt,
             color=th["label"], fontweight="bold", va="top")
    fig.text(x0, 1 - mmy(s.margin_mm) - mmy(s.title_pt * 0.5), s.subtitle,
             fontsize=s.subtitle_pt, color=th["label"], alpha=0.6, va="top")
    if s.credit:
        fig.text(1 - x0, mmy(s.margin_mm * 0.4), s.credit, fontsize=s.credit_pt,
                 color=th["label"], alpha=0.45, ha="right")

    # Una sola franja inferior, dividida en dos columnas.
    band_h = mmy(s.footer_mm * 0.46)
    y = mmy(s.margin_mm * 1.5)
    if s.mode == "zones":
        _zones_key(fig, s, th, (x0, y, mmx(s.page_mm[0] * 0.62), band_h))
    if s.show_dst:
        _dst_block(fig, s, th, (x0 + mmx(s.page_mm[0] * 0.38), y,
                                mmx(s.page_mm[0] * 0.46), band_h))

def _dst_block(fig, s: Style, th: dict, rect) -> None:
    ax = fig.add_axes(rect); ax.set_axis_off()
    ax.set_xlim(0, 12); ax.set_ylim(0, 1)
    ax.text(0, 0.97, "HORARIO DE VERANO", fontsize=s.legend_pt * 0.92,
            color=th["label"], fontweight="bold", va="top")

    rules = pd.read_csv(CACHE / "rules.csv")
    dst = rules[rules["dst_delta_h"] != 0]
    x0, w = 4.6, 7.4

    def spans(iv: str) -> list[tuple[float, float]]:
        out = []
        for part in str(iv).split(";"):
            if ".." in part:
                a, b = part.split("..")
                f = lambda d: (int(d[5:7]) - 1) + (int(d[8:10]) - 1) / 31
                out.append((f(a), f(b)))
        return out

    with mpl.rc_context({"hatch.color": th["hatch"], "hatch.linewidth": 0.6}):
        for i, (hemi, hatch, label) in enumerate([
                ("N", s.dst_hatch, "hemisferio norte"),
                ("S", "\\\\\\\\", "hemisferio sur")]):
            sub = dst[dst["hemisphere"] == hemi]
            if sub.empty:
                continue
            y = 0.46 - i * 0.30
            ax.add_patch(Rectangle((0, y), 0.62, 0.22, facecolor=th["bg"],
                                   hatch=hatch, edgecolor=th["label"], linewidth=0.5))
            ax.text(0.85, y + 0.11, label, va="center", fontsize=s.legend_pt * 0.85,
                    color=th["label"])
            ax.text(3.5, y + 0.11, f"{len(sub)} zonas", va="center", ha="right",
                    fontsize=s.legend_pt * 0.72, color=th["label"], alpha=0.5)
            ax.add_patch(Rectangle((x0, y), w, 0.22, facecolor=th["label"],
                                   alpha=0.07, edgecolor="none"))
            for a, b in spans(sub.iloc[0]["intervals"]):
                ax.add_patch(Rectangle((x0 + w * a / 12, y), w * (b - a) / 12, 0.22,
                                       facecolor=th["label"], alpha=0.55, edgecolor="none"))
    for m, nm in enumerate("EFMAMJJASOND"):
        ax.text(x0 + w * (m + 0.5) / 12, 0.10, nm, ha="center", va="top",
                fontsize=s.legend_pt * 0.7, color=th["label"], alpha=0.5)


def _paint_zones(ax, crs, s: Style, th: dict) -> None:
    """Husos reales sobre las bandas teoricas, al modo del mapa de la CIA:
    paleta ciclica corta, rayado para los offsets fraccionarios y el numero
    escrito dentro de cada huso."""
    cia = s.theme == "cia"
    lo, hi = effective_limits(s)

    # 1. Fondo: mar y bandas teoricas de 15 grados, altura completa.
    if cia:
        sea = gpd.GeoDataFrame(
            {"geometry": [box(s.lon0 - 179.999, lo, s.lon0 + 179.999, hi)]},
            crs="EPSG:4326").to_crs(crs)
        sea.plot(ax=ax, color=s.sea_color or th["sea"], linewidth=0, zorder=0)
    if s.band_tint:
        cells, tints = [], []
        for k in range(-12, 13):
            west, east = max(15 * k - 7.5, -180), min(15 * k + 7.5, 180)
            if west >= east:
                continue
            cells.append(box(west, lo, east, hi))
            tints.append(CIA_BAND_A if k % 2 == 0 else CIA_BAND_B)
        bands = gpd.GeoDataFrame({"geometry": cells}, crs="EPSG:4326").to_crs(crs)
        for geom, tint in zip(bands.geometry, tints):
            gpd.GeoSeries([geom], crs=crs).plot(
                ax=ax, color=tint, linewidth=0, zorder=0.5,
                alpha=s.band_tint_alpha if cia else 1.0)

    # 2a. Husos nauticos: continuan la columna de color sobre el mar, mas
    # claros para que la tierra siga leyendose como tierra.
    sea_z = None
    if s.sea_zones:
        sea_z = _clip(gpd.read_file(CACHE / "zones_sea.gpkg"), s).to_crs(crs)
        for _, row in sea_z.iterrows():
            h = float(row["std_hours"])
            base = cycle_color(h) if cia else zone_color(h, s.theme)
            gpd.GeoSeries([row.geometry], crs=crs).plot(
                ax=ax, color=lighten(base, s.sea_fade), linewidth=0, zorder=0.6)

    # 2b. Husos sobre tierra, a color pleno.
    z = _clip(gpd.read_file(CACHE / "zones_land.gpkg"), s).to_crs(crs)
    for _, row in z.iterrows():
        h = float(row["std_hours"])
        col = cycle_color(h) if cia else zone_color(h, s.theme)
        gpd.GeoSeries([row.geometry], crs=crs).plot(
            ax=ax, color=col, linewidth=0, zorder=1)

    # 3. Los fraccionarios se distinguen por rayado, no por color aparte.
    if cia:
        frac = z[z["std_hours"] != z["std_hours"].astype(int)]
        if len(frac):
            with mpl.rc_context({"hatch.color": th["zone_edge"],
                                 "hatch.linewidth": 0.5}):
                frac.plot(ax=ax, facecolor="none", hatch="////",
                          edgecolor="none", linewidth=0, zorder=2, alpha=0.55)

    if s.solar_lines:
        ys = np.linspace(lo + 0.01, hi - 0.01, 180)
        lines = [LineString([(15 * k + 7.5, y) for y in ys]) for k in range(-12, 12)]
        gpd.GeoSeries(lines, crs="EPSG:4326").to_crs(crs).plot(
            ax=ax, color=th["solar_line"], linewidth=0.5, alpha=0.75,
            linestyle=(0, (3.0, 3.0)), zorder=4)

    if s.zone_edges:
        # El limite de huso sale SOLO de la capa de mar, que es la particion
        # completa del globo (incluye la tierra). El borde de la capa de
        # tierra es la linea de costa, no un limite de huso: dibujarlo
        # contorneaba cada isla y cada pais con el color de huso.
        edges = sea_z if sea_z is not None else z
        edges.boundary.plot(ax=ax, color=th["zone_edge"],
                            linewidth=s.zone_edge_w, alpha=0.95, zorder=5)

    reserved = _offset_labels(ax, z, s, th) if s.zone_offsets else []
    ax._reserved_boxes = reserved


def _offset_labels(ax, zones: gpd.GeoDataFrame, s: Style, th: dict) -> list:
    """Escribe el offset dentro de cada parte de huso lo bastante grande.

    Devuelve las cajas ocupadas para que los nombres no se le encimen: el
    "+5 1/2" caia sobre "INDIA".
    """
    from .labels import Box, text_box
    import matplotlib.patheffects as pe2
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    map_area = abs(xlim[1] - xlim[0]) * abs(ylim[1] - ylim[0])
    fig_w_in = ax.get_figure().get_size_inches()[0] * ax.get_position().width
    unit = abs(xlim[1] - xlim[0]) / (fig_w_in * 72.0)
    used: list = []
    parts = zones.explode(index_parts=False, ignore_index=True)
    parts["_a"] = parts.geometry.area
    frac = parts["std_hours"] != parts["std_hours"].astype(int)
    keep = parts[(parts["_a"] >= map_area * s.offset_min_area)
                 | (frac & (parts["_a"] >= map_area * s.offset_min_area_frac))]
    ymin, ymax = ylim
    step = (ymax - ymin) * (s.offset_repeat_deg / 180.0)
    for _, row in keep.iterrows():
        # Un huso alto lleva el numero repetido, como en los mapas murales:
        # se corta en fajas horizontales y cada faja recibe su etiqueta.
        g = row.geometry
        y0, y1 = g.bounds[1], g.bounds[3]
        n = max(1, int(round((y1 - y0) / step)))
        spots = []
        for i in range(n):
            band = box(g.bounds[0] - 1, y0 + (y1 - y0) * i / n,
                       g.bounds[2] + 1, y0 + (y1 - y0) * (i + 1) / n)
            piece = g.intersection(band)
            if piece.is_empty or piece.area < map_area * s.offset_min_area * 0.5:
                continue
            spots.append(piece.representative_point())
        if not spots:
            spots = [g.representative_point()]
        small = row["_a"] < map_area * s.offset_min_area
        for pt in spots:
            lab = offset_label(float(row["std_hours"]))
            tx, ty = pt.x, pt.y
            if small:
                # No entra adentro: se corre afuera y se ata con una guia.
                ty = g.bounds[3] + (ylim[1] - ylim[0]) * 0.018
                ax.plot([pt.x, tx], [pt.y, ty], color=th["zone_edge"],
                        linewidth=0.5, alpha=0.8, zorder=8.8)
            used.append(text_box(tx, ty, lab, s.offset_pt * unit))
            ax.text(tx, ty, lab, fontsize=s.offset_pt, ha="center",
                    va="center", color=th["zone_edge"], fontweight="bold",
                    zorder=9, path_effects=[pe2.withStroke(
                        linewidth=2.0, foreground=th["label_halo"])])
    return used


def _zones_key(fig, s: Style, th: dict, rect) -> None:
    ax = fig.add_axes(rect); ax.set_axis_off()
    ax.set_xlim(0, 6); ax.set_ylim(0, 1)
    ax.text(0, 0.97, "CÓMO LEERLO", fontsize=s.legend_pt * 0.92,
            color=th["label"], fontweight="bold", va="top")
    if s.theme == "cia":
        # Las tres filas comparten ancho de muestra (0.60) para que los
        # textos arranquen todos en la misma x.
        w = 0.60 / len(CIA_CYCLE)
        for i, col in enumerate(CIA_CYCLE):
            ax.add_patch(Rectangle((i * w, 0.60), w, 0.15, facecolor=col,
                                   edgecolor=th["zone_edge"], linewidth=0.3))
        ax.text(0.80, 0.675,
                "el color solo separa husos vecinos; no significa nada por sí mismo",
                va="center", fontsize=s.legend_pt * 0.78, color=th["label"])

        with mpl.rc_context({"hatch.color": th["zone_edge"], "hatch.linewidth": 0.5}):
            ax.add_patch(Rectangle((0, 0.36), 0.60, 0.15, facecolor=CIA_CYCLE[3],
                                   hatch="////", edgecolor=th["zone_edge"],
                                   linewidth=0.4))
        ax.text(0.80, 0.435, "rayado: husos de media o cuarto de hora",
                va="center", fontsize=s.legend_pt * 0.78, color=th["label"])

        # Solo tiene sentido explicar el contraste si existe.
        if s.sea_zones and s.sea_fade > 0.05:
            ax.add_patch(Rectangle((0, 0.12), 0.30, 0.15,
                                   facecolor=lighten(CIA_CYCLE[3], s.sea_fade),
                                   edgecolor=th["zone_edge"], linewidth=0.4))
            ax.add_patch(Rectangle((0.30, 0.12), 0.30, 0.15, facecolor=CIA_CYCLE[3],
                                   edgecolor=th["zone_edge"], linewidth=0.4))
            ax.plot([0.30, 0.30], [0.12, 0.27], color=th["land_edge"], linewidth=0.6)
            ax.text(0.80, 0.195,
                    "el tono claro es el huso náutico sobre el mar; el pleno, tierra firme",
                    va="center", fontsize=s.legend_pt * 0.78, color=th["label"])
        return
    items = [("hora entera, par", zone_color(0, s.theme)),
             ("hora entera, impar", zone_color(1, s.theme)),
             ("media o cuarto de hora", zone_color(5.5, s.theme))]
    for i, (label, col) in enumerate(items):
        y = 0.56 - i * 0.22
        ax.add_patch(Rectangle((0, y), 0.5, 0.16, facecolor=col,
                               edgecolor=th["zone_edge"], linewidth=0.6))
        ax.text(0.68, y + 0.08, label, va="center", fontsize=s.legend_pt * 0.8,
                color=th["label"])


def _dateline(ax, crs, s: Style, th: dict) -> None:
    path = CACHE / "dateline.gpkg"
    if not path.exists():
        return
    dl = _clip_lines(gpd.read_file(path), s).to_crs(crs)
    if dl.empty:
        return
    dl.plot(ax=ax, color=th["zone_edge"], linewidth=s.dateline_w,
            alpha=0.95, zorder=6)
    dl.plot(ax=ax, color=th["label_halo"], linewidth=s.dateline_w * 0.35,
            alpha=0.9, zorder=6.1, linestyle=(0, (1.5, 2.0)))
    if not s.dateline_label:
        return
    # Rotulo vertical sobre el tramo del antimeridiano, como en la referencia.
    import matplotlib.patheffects as pe4
    lo, hi = effective_limits(s)
    for lon in (-176.0, 176.0):
        pts = gpd.GeoSeries(
            [Point(lon, (max(lo, -55) + min(hi, 60)) / 2)],
            crs="EPSG:4326").to_crs(crs)
        ax.text(pts.iloc[0].x, pts.iloc[0].y, s.dateline_text,
                rotation=90, fontsize=s.legend_pt * 0.62, ha="center",
                va="center", color=th["zone_edge"], alpha=0.85, zorder=6.6,
                path_effects=[pe4.withStroke(linewidth=2.0,
                                             foreground=th["label_halo"])])


def _clip_lines(gdf: gpd.GeoDataFrame, s: Style) -> gpd.GeoDataFrame:
    lo, hi = effective_limits(s)
    clipper = box(s.lon0 - 179.999, lo, s.lon0 + 179.999, hi)
    out = gdf.copy()
    out["geometry"] = out.geometry.intersection(clipper)
    return out[~out.geometry.is_empty & out.geometry.notna()]


def _ocean_names(ax, crs, s: Style, th: dict) -> None:
    import matplotlib.patheffects as pe3
    path = CACHE / "marine.gpkg"
    if not path.exists():
        return
    lo, hi = effective_limits(s)
    m = gpd.read_file(path)
    pts = m.geometry.representative_point()
    keep = [(i, p) for i, p in zip(m.index, pts) if lo + 4 < p.y < hi - 4]
    if not keep:
        return
    idx = [i for i, _ in keep]
    proj = gpd.GeoSeries([p for _, p in keep], crs="EPSG:4326").to_crs(crs)
    for (i, _), pt in zip(keep, proj):
        row = m.loc[i]
        size = s.ocean_pt * (1.0 if row["is_ocean"] else 0.72)
        ax.text(pt.x, pt.y, row["label_es"], fontsize=size, ha="center",
                va="center", color=th["label"], style="italic", alpha=0.75,
                zorder=6.5, fontweight="normal",
                path_effects=[pe3.withStroke(linewidth=1.8,
                                             foreground=th["label_halo"])])
