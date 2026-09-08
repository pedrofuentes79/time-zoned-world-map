"""Agrupa islas cercanas para sombrearlas como conjunto.

Un archipielago disperso se lee como puntos sueltos: Maldivas, Chagos o las
Marquesas son decenas de manchas de un milimetro sin nada que las relacione.
Los mapas de referencia las marcan con un panel tenue detras del grupo.

No sale de los recuadros de huso: esos existen solo cuando el huso difiere
de su banda, y son justo los grupos que ya se leen como unidad.
"""
from __future__ import annotations

import warnings

import geopandas as gpd
from shapely.geometry import box
from shapely.ops import unary_union

# Islas que entran al agrupado. El minimo tiene que ser muy chico: los
# atolones de Maldivas, Chagos o la cadena noroeste de Hawai miden
# milesimas de grado cuadrado y quedaban afuera, que era justo el caso que
# el panel viene a resolver. Por encima del maximo ya se leen solas.
MIN_DEG2 = 0.00002
MAX_DEG2 = 2.0
# Cuan cerca tienen que estar para contar como un grupo.
CLUSTER_DEG = 2.0
# Cuantas islas hacen falta. Con menos no es un archipielago.
MIN_ISLANDS = 4
# Margen del panel alrededor del grupo.
PAD_DEG = 0.5
# Radio de las esquinas: un rectangulo de canto vivo se lee como recuadro
# de huso, que es otra cosa. Redondeado se lee como sombreado.
CORNER_DEG = 0.45
# Un grupo desparramado no se sombrea: el panel taparia medio oceano. El
# tope tiene que dar para la cadena hawaiana entera, que mide 24 grados
# desde Kure hasta la Isla Grande.
MAX_SPAN_DEG = 26.0


def build(land: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    parts = land.explode(index_parts=False, ignore_index=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        parts["_area"] = parts.geometry.area
        small = parts[(parts["_area"] >= MIN_DEG2)
                      & (parts["_area"] <= MAX_DEG2)]
        if small.empty:
            return gpd.GeoDataFrame({"geometry": []}, crs=land.crs)

        blobs = unary_union([g.buffer(CLUSTER_DEG) for g in small.geometry])
        rows = []
        for blob in getattr(blobs, "geoms", [blobs]):
            inside = small[small.geometry.within(blob)]
            if len(inside) < MIN_ISLANDS:
                continue
            x0, y0, x1, y1 = unary_union(list(inside.geometry)).bounds
            if max(x1 - x0, y1 - y0) > MAX_SPAN_DEG:
                continue
            panel = box(x0 - PAD_DEG, y0 - PAD_DEG,
                        x1 + PAD_DEG, y1 + PAD_DEG)
            r = min(CORNER_DEG, (x1 - x0 + 2 * PAD_DEG) / 4,
                    (y1 - y0 + 2 * PAD_DEG) / 4)
            if r > 0:
                panel = panel.buffer(-r).buffer(r, join_style="round")
            rows.append({"n": len(inside), "geometry": panel})
    return gpd.GeoDataFrame(rows, crs=land.crs)
