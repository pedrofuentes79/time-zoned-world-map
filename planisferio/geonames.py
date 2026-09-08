"""Extrae nombres de islas del volcado de GeoNames.

Natural Earth trae 455 islas; GeoNames tiene decenas de miles. Se lee en
streaming desde el zip porque allCountries.txt son 12 millones de filas y
no entra comodo en memoria.

Fuente: https://download.geonames.org/export/dump/  (CC BY 4.0)
"""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

RAW = Path("data/raw")

# Codigos de caracteristica de GeoNames que nos interesan, en orden de
# importancia. ISLET queda afuera: son decenas de miles de rocas.
ISLAND_CODES = {
    "ARCH": 0,    # archipielago
    "ISLS": 1,    # grupo de islas
    "ISL": 2,     # isla
    "ATOL": 3,    # atolon
}

# Campos de allCountries.txt (sin encabezado)
GN_ID, GN_NAME, GN_LAT, GN_LON, GN_FCLASS, GN_FCODE = 0, 1, 4, 5, 6, 7
GN_CC, GN_POP, GN_DEM = 8, 14, 16

# Campos de alternateNamesV2.txt
ALT_GEOID, ALT_LANG, ALT_NAME, ALT_PREF = 1, 2, 3, 4


def _rows(zip_path: Path, member: str):
    with zipfile.ZipFile(zip_path) as z:
        with z.open(member) as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8", newline="")
            for row in csv.reader(text, delimiter="\t", quoting=csv.QUOTE_NONE):
                yield row


def islands() -> list[dict]:
    """Islas, archipielagos y atolones del volcado."""
    out = []
    for r in _rows(RAW / "geonames_all.zip", "allCountries.txt"):
        if len(r) < 19 or r[GN_FCLASS] != "T":
            continue
        code = r[GN_FCODE]
        if code not in ISLAND_CODES:
            continue
        try:
            lat, lon = float(r[GN_LAT]), float(r[GN_LON])
        except ValueError:
            continue
        out.append({
            "geonameid": r[GN_ID], "name": r[GN_NAME],
            "lat": lat, "lon": lon, "code": code,
            "cc": r[GN_CC], "rank_code": ISLAND_CODES[code],
            "pop": int(r[GN_POP] or 0),
        })
    return out


def spanish_names(ids: set[str]) -> dict[str, str]:
    """Nombre en espanol para los geonameid pedidos.

    Prefiere el marcado como preferente; si no hay, el primero que aparezca.
    """
    best: dict[str, str] = {}
    pref: set[str] = set()
    for r in _rows(RAW / "geonames_alt.zip", "alternateNamesV2.txt"):
        if len(r) < 5 or r[ALT_LANG] != "es":
            continue
        gid = r[ALT_GEOID]
        if gid not in ids:
            continue
        if gid in pref:
            continue
        best[gid] = r[ALT_NAME]
        if r[ALT_PREF] == "1":
            pref.add(gid)
    return best


CACHE = Path("data/cache")
ISLANDS_CSV = CACHE / "gn_islands.csv"


def build_cache() -> "pd.DataFrame":
    """Extrae islas con su nombre en espanol y las deja en un csv.

    Recorrer los 12 millones de filas tarda minutos, asi que se hace una
    sola vez. Se rehace si cambia alguno de los dos volcados.
    """
    import pandas as pd

    from . import cache_key
    key = cache_key.fingerprint(
        {"codes": sorted(ISLAND_CODES)},
        code=Path(__file__),
        data=str([(RAW / n).stat().st_size
                  for n in ("geonames_all.zip", "geonames_alt.zip")]))
    keyfile = CACHE / "_gn_islands.key"
    if ISLANDS_CSV.exists() and keyfile.exists() \
            and keyfile.read_text().strip() == key:
        return pd.read_csv(ISLANDS_CSV)

    print("  extrayendo islas de GeoNames (recorre 12M de filas)...")
    rows = islands()
    print(f"    {len(rows):,} islas; buscando nombres en español...")
    es = spanish_names({r["geonameid"] for r in rows})
    for r in rows:
        r["name_es"] = es.get(r["geonameid"], r["name"])
    df = pd.DataFrame(rows)
    CACHE.mkdir(parents=True, exist_ok=True)
    df.to_csv(ISLANDS_CSV, index=False)
    keyfile.write_text(key)
    print(f"    con nombre en español: {sum(1 for r in rows if r['geonameid'] in es):,}")
    return df
