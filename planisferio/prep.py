"""Preprocesa los datos crudos a un cache liviano listo para renderizar."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

from .tzrules import all_rules

RAW = Path("data/raw")
CACHE = Path("data/cache")
# La variante sin oceanos ya viene recortada a tierra con la costa de OSM.
# Intersectar contra Natural Earth dejaba slivers grises donde las dos
# costas no coinciden.
TZ_SRC = RAW / "combined-now.json"
TZ_SEA_SRC = RAW / "combined-with-oceans-now.json"

# Tolerancias en grados. A A0 (1189 mm de ancho) un grado son ~3.3 mm,
# asi que 0.003 grados son ~0.01 mm: por debajo de lo que imprime una maquina.
SIMPLIFY_ZONES = 0.003
SIMPLIFY_COUNTRIES = 0.003


def _vertices(gdf: gpd.GeoDataFrame) -> int:
    return int(sum(shapely.get_num_coordinates(g) for g in gdf.geometry))


def build() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    rules = all_rules()

    from . import cache_key
    from .zone_fixes import FIXES, OVERLAPS

    # La capa de tierra tambien se cachea: disolver, recortar contra Natural
    # Earth y simplificar son ~30 segundos que no cambian salvo que cambien
    # la fuente, los umbrales o las tablas de correccion.
    land_key = cache_key.fingerprint(
        {"SIMPLIFY_ZONES": SIMPLIFY_ZONES,
         "fixes": [f[0] for f in FIXES],
         "overlaps": [(o[0], o[3], o[4]) for o in OVERLAPS]},
        code=Path(__file__),
        data=str(TZ_SRC.stat().st_size))
    bands = cache_key.load("land", land_key)
    if bands is not None:
        print("capa de tierra: reusando cache")
    else:
        print("husos horarios (ya recortados a tierra en origen)...")
        tz = gpd.read_file(TZ_SRC)
        tz["std_hours"] = tz["tzid"].map(lambda t: rules[t].std_hours if t in rules else None)
        tz = tz[tz["std_hours"].notna()]

        print("  disolviendo por offset...")
        bands = tz.dissolve(by="std_hours", as_index=False)[["std_hours", "geometry"]]
        print(f"  vertices: {_vertices(bands):,}")

        # La fuente incluye aguas alrededor de islas remotas: Pacific/Easter es
        # un poligono de 66 grados^2 (la isla mide 0.015). Sin recortar, esas
        # manchas se dibujan como si fueran tierra.
        print("  recortando contra la tierra de Natural Earth...")
        land = gpd.read_file(RAW / "ne_10m_land.zip")[["geometry"]]
        try:
            islands = gpd.read_file(RAW / "ne_10m_minor_islands.zip")[["geometry"]]
            land = pd.concat([land, islands], ignore_index=True)
        except Exception:
            pass
        land_union = gpd.GeoDataFrame(land, crs="EPSG:4326").geometry.buffer(0).union_all()
        bands["geometry"] = bands.geometry.buffer(0).intersection(land_union)
        bands = bands[~bands.geometry.is_empty & bands.geometry.notna()]
        print(f"  vertices tras recorte: {_vertices(bands):,}")

        from .zone_fixes import apply as apply_fixes, resolve_overlaps
        bands, overlaps = resolve_overlaps(bands)
        for line in overlaps:
            print(f"  solape resuelto -> {line}")
        bands, applied = apply_fixes(bands)
        for line in applied:
            print(f"  correccion de huso -> {line}")

        bands["geometry"] = bands.geometry.simplify(SIMPLIFY_ZONES, preserve_topology=True)
        print(f"  vertices tras simplify({SIMPLIFY_ZONES}): {_vertices(bands):,}")
        cache_key.save("land", land_key, bands)

    bands.to_file(CACHE / "zones_land.gpkg", layer="zones", driver="GPKG")

    from .generalize import build as build_sea, params as sea_params
    key = cache_key.fingerprint(
        {**sea_params(), "SIMPLIFY_ZONES": SIMPLIFY_ZONES},
        code=Path(__file__).with_name("generalize.py"),
        # Se encadena con la clave de la tierra en vez de hashear su
        # geometria: al volver del gpkg la precision cambia y la huella no
        # coincidia, asi que el cache del mar fallaba siempre que el de
        # tierra acertaba.
        data=land_key)
    sea = cache_key.load("sea", key)
    if sea is not None:
        print("generalizacion del mar: reusando cache")
    else:
        print("generalizando los husos sobre el mar (paso lento)...")
        sea = build_sea(bands[["std_hours", "geometry"]].copy())
        cache_key.save("sea", key, sea)
    sea.to_file(CACHE / "zones_sea.gpkg", layer="zones", driver="GPKG")
    from .island_groups import build as build_groups
    panels, missing = build_groups(bands)
    if missing:
        print(f"  aviso: archipielagos sin islas cerca: {', '.join(missing)}")
    if len(panels):
        panels.to_file(CACHE / "island_panels.gpkg", layer="panels",
                       driver="GPKG")
        print(f"  archipielagos sombreados: {len(panels)}")
    print(f"  {len(sea)} husos, vertices: {_vertices(sea):,}")

    print("paises (Natural Earth 10m)...")
    co = gpd.read_file(RAW / "ne_10m_admin_0_countries.zip")
    keep = ["NAME_ES", "NAME_EN", "LABEL_X", "LABEL_Y", "POP_EST", "geometry"]
    co = co[keep].rename(columns={"NAME_ES": "name_es", "NAME_EN": "name_en"})
    co["geometry"] = co.geometry.simplify(SIMPLIFY_COUNTRIES, preserve_topology=True)
    co.to_file(CACHE / "countries.gpkg", layer="countries", driver="GPKG")
    print(f"  {len(co)} paises, vertices: {_vertices(co):,}")

    print("tabla de rotulos (paises + islas)...")
    from .label_data import build as build_labels
    lab = build_labels(co)
    lab.to_file(CACHE / "labels.gpkg", layer="labels", driver="GPKG")
    counts = lab["kind"].value_counts().to_dict()
    print(f"  {len(lab)} rotulos (" + ", ".join(
        f"{v} {k}" for k, v in sorted(counts.items())) + ")")

    print("nombres de mares y oceanos...")
    marine = gpd.read_file(RAW / "ne_10m_geography_marine_polys.zip")
    marine = marine[marine["scalerank"] <= 1].copy()
    # name_es pierde el Norte/Sur del Atlantico y el Pacifico; se reconstruye
    # desde la etiqueta inglesa, que si lo trae.
    def _es(r):
        base = (r.get("name_es") or r.get("label") or "").strip()
        lab = str(r.get("label") or "")
        if lab.upper().startswith("NORTH ") and "NORTE" not in base.upper():
            base += " NORTE"
        elif lab.upper().startswith("SOUTH ") and "SUR" not in base.upper():
            base += " SUR"
        return base.upper()
    marine["label_es"] = marine.apply(_es, axis=1)
    marine["is_ocean"] = marine["featurecla"] == "ocean"
    marine[["label_es", "is_ocean", "featurecla", "geometry"]].to_file(
        CACHE / "marine.gpkg", layer="marine", driver="GPKG")
    print(f"  {len(marine)} rotulos ({marine['is_ocean'].sum()} oceanos)")

    print("linea de cambio de fecha...")
    from .dateline import build as build_dateline
    dl = build_dateline(sea)
    dl.to_file(CACHE / "dateline.gpkg", layer="dateline", driver="GPKG")
    print(f"  {len(dl)} tramos")

    rows = [{
        "tzid": r.tzid, "std_hours": r.std_hours, "dst_hours": r.dst_hours,
        "dst_delta_h": r.dst_delta.total_seconds() / 3600, "hemisphere": r.hemisphere,
        "intervals": ";".join(f"{a}..{b}" for a, b in r.intervals),
    } for r in rules.values()]
    pd.DataFrame(rows).to_csv(CACHE / "rules.csv", index=False)

    offsets = sorted(float(v) for v in bands["std_hours"].unique())
    print(f"cache listo. {len(offsets)} husos con tierra.")

    from .checks import run as run_checks
    run_checks()


if __name__ == "__main__":
    build()
