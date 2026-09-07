"""Cacheo del paso caro de generalizacion.

El cierre morfologico sobre las costas tarda minutos. Se guarda el
resultado junto a una huella de las entradas; si la huella coincide, se
reusa. Cambiar cualquier constante de generalize.py invalida el cache.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CACHE = Path("data/cache")


def geometry_digest(gdf) -> str:
    """Huella de la geometria de entrada.

    Mirar el archivo fuente no alcanza: la entrada puede transformarse antes
    de llegar al paso caro (recortarla contra la costa, por ejemplo) sin que
    el archivo cambie. Eso daba un falso acierto y se reusaba un cache
    calculado sobre datos distintos.
    """
    h = hashlib.sha256()
    for geom in gdf.geometry:
        h.update(geom.wkb)
    return h.hexdigest()[:16]


def fingerprint(params: dict, code: Path | None = None,
                data: str | None = None) -> str:
    """La huella cubre entrada, parametros y codigo. Faltando cualquiera de
    los tres, el cache puede devolver un resultado que no corresponde."""
    payload = {"params": {k: params[k] for k in sorted(params)}}
    if data is not None:
        payload["data"] = data
    if code is not None and code.exists():
        payload["code"] = hashlib.sha256(code.read_bytes()).hexdigest()[:16]
    blob = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def load(name: str, key: str):
    keyfile = CACHE / f"_{name}.key"
    data = CACHE / f"_{name}.gpkg"
    if not (keyfile.exists() and data.exists()):
        return None
    if keyfile.read_text().strip() != key:
        return None
    import geopandas as gpd
    return gpd.read_file(data)


def save(name: str, key: str, gdf) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    gdf.to_file(CACHE / f"_{name}.gpkg", driver="GPKG")
    (CACHE / f"_{name}.key").write_text(key)
