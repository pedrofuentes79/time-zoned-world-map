"""Correcciones de huso sobre la fuente.

timezone-boundary-builder toma los limites de OpenStreetMap, y ahi hay
territorios mal asignados. Cada entrada nombra el lugar, su punto, el
offset correcto y la razon, para que se pueda auditar.

Es distinto de TERRITORIES en generalize.py: alli se corrigen formas de
dibujo, aca se corrige el dato.
"""
from __future__ import annotations

import warnings

import geopandas as gpd
from shapely.geometry import Point

#      nombre                 lon      lat    offset correcto
FIXES = [
    ("Ilha da Trindade",    -29.33,  -20.57,  -2.0),
    ("Martim Vaz",          -28.88,  -20.52,  -2.0),
]

# Por que, para cada una:
#   Trindade y Martim Vaz: OSM las pone en America/Sao_Paulo (UTC-3). La ley
#   brasilena las incluye en el huso de Fernando de Noronha (UTC-2), junto
#   con el Atol das Rocas. tzdata describe America/Noronha como "Atlantic
#   islands", en generico.


def apply(bands: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, list[str]]:
    """Mueve las partes nombradas al huso que les corresponde."""
    parts = bands.explode(index_parts=False, ignore_index=True)
    applied = []
    for name, lon, lat, correct in FIXES:
        pt = Point(lon, lat)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            d = parts.geometry.distance(pt)
            if d.min() > 1.0:
                continue
            idx = d.idxmin()
        before = float(parts.at[idx, "std_hours"])
        if before == correct:
            continue
        parts.at[idx, "std_hours"] = correct
        applied.append(f"{name}: UTC{before:+g} -> UTC{correct:+g}")
    out = parts.dissolve(by="std_hours", as_index=False)[["std_hours", "geometry"]]
    return out, applied
