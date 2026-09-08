"""Archipielagos que llevan sombreado, nombrados a mano.

Un grupo disperso se lee como puntos sueltos: Maldivas son 67 manchas de un
milimetro sin nada que las relacione. El panel tenue los agrupa.

Cuales llevan panel se decide aca y no por agrupado automatico. Se intento
al reves: con un radio de agrupado unico, subirlo para que entrara la cadena
hawaiana entera (24 grados) hacia que los grupos chicos se fusionaran o
superaran el tope de extension, y las Antillas desaparecian. No hay radio
que sirva para Maldivas y para Hawai a la vez.

El panel se ajusta a las islas reales que encuentra alrededor del punto, asi
que la tabla decide QUE se sombrea y los datos deciden DONDE.

    (nombre, lon, lat, radio en grados)
"""
from __future__ import annotations

import warnings

import geopandas as gpd
from shapely.geometry import Point, box
from shapely.ops import unary_union

GROUPS = [
    ("Islas Maldivas",          73.20,    3.50,   8.0),
    ("Archipiélago de Hawái", -163.00,   24.00,  14.0),
    ("Azores",                 -28.00,   38.50,   3.5),
    ("Cabo Verde",             -24.00,   15.50,   2.5),
    ("Islas Canarias",         -15.80,   28.30,   2.5),
    ("Islas Galápagos",        -90.50,   -0.50,   2.5),
    ("Islas Marquesas",       -139.50,   -9.00,   2.5),
    ("Archipiélago de Chagos",  72.40,   -6.30,   2.5),
    ("Seychelles",              55.50,   -4.60,   4.0),
    ("Antillas Menores",       -61.50,   15.50,   5.0),
    ("Islas Feroe",             -7.00,   62.00,   1.5),
    ("Islas Salomón",          159.50,   -8.50,   5.0),
    ("Islas Fiyi",             178.00,  -17.80,   3.0),
    # Las Aleutianas quedan afuera a proposito: su panel mide 29 x 21
    # grados y domina el Pacifico norte. Se agrega asi si se la quiere:
    #     ("Islas Aleutianas", -175.00, 52.00, 22.0),
]

# Islas que cuentan para ajustar el panel. El minimo tiene que ser muy chico:
# los atolones de Maldivas o Chagos son diminutos, y son justo el caso que
# el panel viene a resolver.
MIN_DEG2 = 0.00002
MAX_DEG2 = 2.0
PAD_DEG = 0.5
# Un rectangulo de canto vivo se lee como recuadro de huso, que es otra
# cosa. Redondeado se lee como sombreado.
CORNER_DEG = 0.45


def build(land: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, list[str]]:
    parts = land.explode(index_parts=False, ignore_index=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        parts["_area"] = parts.geometry.area
        small = parts[(parts["_area"] >= MIN_DEG2)
                      & (parts["_area"] <= MAX_DEG2)]
        rows, missing = [], []
        for name, lon, lat, radius in GROUPS:
            pt = Point(lon, lat)
            near = small[small.geometry.distance(pt) <= radius]
            if near.empty:
                missing.append(name)
                continue
            x0, y0, x1, y1 = unary_union(list(near.geometry)).bounds
            panel = box(x0 - PAD_DEG, y0 - PAD_DEG, x1 + PAD_DEG, y1 + PAD_DEG)
            r = min(CORNER_DEG, (x1 - x0 + 2 * PAD_DEG) / 4,
                    (y1 - y0 + 2 * PAD_DEG) / 4)
            if r > 0:
                panel = panel.buffer(-r).buffer(r, join_style="round")
            rows.append({"name": name, "n": len(near), "geometry": panel})
    return gpd.GeoDataFrame(rows, crs=land.crs), missing
