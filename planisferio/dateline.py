"""La linea internacional de cambio de fecha.

No esta en ningun dataset: se deriva. Es el borde entre los husos mas
adelantados (+12 y mas) y los mas atrasados (-10 y menos), que en el
Pacifico son vecinos pese a tener 24 horas de diferencia.
"""
from __future__ import annotations

import warnings

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point
from shapely.ops import linemerge, unary_union

AHEAD = 12.0     # husos "de manana": +12, +12:45, +13, +14
BEHIND = -9.5    # husos "de ayer": -10, -11, -9:30...
# La interseccion de bordes deja miles de esquirlas numericas;
# solo interesan los tramos con largo real.
MIN_SEGMENT_DEG = 0.3


def build(sea: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        ahead = unary_union(list(sea[sea["std_hours"] >= AHEAD].geometry))
        behind = unary_union(list(sea[sea["std_hours"] <= BEHIND].geometry))
        if ahead.is_empty or behind.is_empty:
            return gpd.GeoDataFrame({"geometry": []}, crs=sea.crs)
        shared = ahead.boundary.intersection(behind.boundary)
    lines = [g for g in getattr(shared, "geoms", [shared])
             if not g.is_empty and g.geom_type == "LineString"]
    if not lines:
        return gpd.GeoDataFrame({"geometry": []}, crs=sea.crs)
    merged = linemerge(lines)
    geoms = [g for g in getattr(merged, "geoms", [merged])
             if g.length >= MIN_SEGMENT_DEG]
    geoms += _antimeridian_runs(sea)
    return gpd.GeoDataFrame({"geometry": geoms}, crs=sea.crs)


def _antimeridian_runs(sea: gpd.GeoDataFrame,
                       lat: tuple[float, float] = (-90.0, 90.0)):
    """El tramo principal corre sobre el antimeridiano, que aqui es el borde
    del mapa: alli los husos quedan cortados y nunca llegan a tocarse, asi
    que ese tramo hay que agregarlo a mano.

    Se recorre en latitud comprobando que huso hay a cada lado del corte.
    """
    ahead = sea[sea["std_hours"] >= AHEAD]
    behind = sea[sea["std_hours"] <= BEHIND]

    def side(gdf, lon, y):
        p = Point(lon, y)
        return any(g.contains(p) for g in gdf.geometry)

    runs, start = [], None
    ys = np.arange(lat[0] + 0.25, lat[1], 0.5)
    for y in ys:
        on = side(ahead, 179.75, y) and side(behind, -179.75, y)
        if on and start is None:
            start = y
        elif not on and start is not None:
            if y - start >= MIN_SEGMENT_DEG:
                runs.append((start, y))
            start = None
    if start is not None:
        runs.append((start, lat[1]))

    # Dibujada exactamente en 180 la linea cae sobre el borde del mapa y se
    # recorta a la mitad. Se corre unas decimas hacia adentro: a A0 son
    # ~2 mm, imperceptible, y el trazo se ve entero.
    out = []
    for y0, y1 in runs:
        for lon in (-179.4, 179.4):
            out.append(LineString([(lon, y0), (lon, y1)]))
    return out
