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


# Solapes de la fuente: dos husos reclaman el mismo territorio y hay que
# decidir. Sin resolverlos, cual se ve depende del orden de dibujo.
#
#     (nombre, lon, lat, huso que gana, huso que cede)
OVERLAPS = [
    ("Xinjiang", 87.6, 43.8, 6.0, 8.0),
]
# Xinjiang: IANA lo mantiene como Asia/Urumqi en UTC+6, aunque el gobierno
# chino nunca reconocio esa hora y en la practica todo el pais usa la de
# Pekin. Se resuelve a favor de UTC+6, que es el criterio de la fuente de la
# que sale todo el resto del mapa. Para dibujar China como un huso unico,
# como hacen los mapas murales, invertir los dos ultimos campos.


def resolve_overlaps(bands: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, list[str]]:
    out = bands.copy()
    notes = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        for name, lon, lat, winner, loser in OVERLAPS:
            iw = out.index[out["std_hours"] == winner]
            il = out.index[out["std_hours"] == loser]
            if not len(iw) or not len(il):
                continue
            gw, gl = out.at[iw[0], "geometry"], out.at[il[0], "geometry"]
            shared = gw.intersection(gl)
            if shared.is_empty:
                continue
            out.at[il[0], "geometry"] = gl.difference(gw)
            notes.append(f"{name}: {shared.area:.0f} grados^2 a UTC{winner:+g} "
                         f"(cedidos por UTC{loser:+g})")
    return out, notes


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
