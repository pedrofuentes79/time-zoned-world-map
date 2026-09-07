"""Invariantes del cache. Corren al final de prep.py.

Cada bug que aparecio en este proyecto dejo aca su chequeo, para que no
vuelva sin avisar.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box
from shapely.ops import unary_union

CACHE = Path("data/cache")
LAT = (-90.0, 90.0)


@dataclass
class Result:
    name: str
    ok: bool
    detail: str

    def __str__(self) -> str:
        return f"  [{'OK ' if self.ok else 'FALLA'}] {self.name}: {self.detail}"


def _no_runaway_pieces(sea: gpd.GeoDataFrame) -> Result:
    """Un conector desbocado produce una pieza ancha y baja que cruza el mapa."""
    bad = []
    for _, r in sea.iterrows():
        for g in getattr(r.geometry, "geoms", [r.geometry]):
            x0, y0, x1, y1 = g.bounds
            if (x1 - x0) > 60 and (y1 - y0) < 25:
                bad.append(f"UTC{r['std_hours']:+g} {x1 - x0:.0f}°x{y1 - y0:.0f}°")
    return Result("sin franjas desbocadas", not bad,
                  "ninguna" if not bad else f"{len(bad)}: {', '.join(bad[:4])}")


def _sea_covers_world(sea: gpd.GeoDataFrame) -> Result:
    """El mar no puede quedar con huecos sin huso."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        world = box(-180, LAT[0], 180, LAT[1])
        covered = unary_union(list(sea.geometry))
        gap = world.difference(covered)
        pct = gap.area / world.area * 100
    return Result("el mar queda cubierto", pct < 0.5,
                  f"{pct:.2f}% sin huso")


def _sea_no_overlap(sea: gpd.GeoDataFrame) -> Result:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        total = sum(g.area for g in sea.geometry)
        merged = unary_union(list(sea.geometry)).area
        pct = (total - merged) / merged * 100 if merged else 0.0
    return Result("los husos no se pisan", pct < 0.5, f"{pct:.2f}% solapado")


def _land_inside_own_zone(land: gpd.GeoDataFrame,
                          sea: gpd.GeoDataFrame) -> Result:
    """Cada trozo de tierra debe caer dentro del huso de su mismo offset."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        sea_by_h = {float(r["std_hours"]): r.geometry for _, r in sea.iterrows()}
        worst, worst_h = 0.0, None
        for _, r in land.iterrows():
            h = float(r["std_hours"])
            if h not in sea_by_h:
                continue
            out = r.geometry.difference(sea_by_h[h].buffer(0.02))
            frac = out.area / r.geometry.area * 100 if r.geometry.area else 0
            if frac > worst:
                worst, worst_h = frac, h
    return Result("la tierra cae en su huso", worst < 1.0,
                  f"peor caso UTC{worst_h:+g}: {worst:.2f}% afuera"
                  if worst_h is not None else "sin desvios")


def _fractional_zones_stay_local(land: gpd.GeoDataFrame,
                                 sea: gpd.GeoDataFrame) -> Result:
    """Un huso fraccionario no tiene banda teorica propia.

    Cuando la tenia, -3:30 reclamaba una franja de polo a polo en el
    Atlantico Sur. Era invisible en el mapa porque comparte color con -3:
    solo se notaba por una linea de limite en medio de un bloque uniforme.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        land_by_h = {float(r["std_hours"]): r.geometry for _, r in land.iterrows()}
        worst, worst_h = 0.0, None
        for _, r in sea.iterrows():
            h = float(r["std_hours"])
            if h == int(h) or h not in land_by_h:
                continue
            lb, sb = land_by_h[h].bounds, r.geometry.bounds
            spread = max(sb[3] - sb[1] - (lb[3] - lb[1]), 0.0)
            if spread > worst:
                worst, worst_h = spread, h
    return Result("husos fraccionarios acotados", worst < 30.0,
                  f"peor caso UTC{worst_h:+g}: {worst:.1f}° de latitud de mas"
                  if worst_h is not None else "sin desvios")


def _named_territories_resolve(land: gpd.GeoDataFrame,
                               sea: gpd.GeoDataFrame) -> Result:
    """Cada territorio de la tabla debe encontrar su tierra y, si pidio
    brazo, terminar conectado a su banda.

    Sin esto, un cambio de datos o un dedazo en las coordenadas hace que el
    territorio simplemente no reciba su recuadro, sin ningun aviso.
    """
    from shapely.geometry import Point
    from .generalize import TERRITORIES, _theoretical_band
    bad = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        parts = land.explode(index_parts=False, ignore_index=True)
        for name, lon, la, h, mode in TERRITORIES:
            h = float(h)
            cand = parts[parts["std_hours"] == h]
            pt = Point(lon, la)
            if cand.empty or cand.geometry.distance(pt).min() > 2.0:
                bad.append(f"{name} (sin tierra)")
                continue
            if mode != "arm":
                continue
            band = _theoretical_band(h, LAT)
            zone = sea[sea["std_hours"] == h]
            if band is None or zone.empty:
                continue
            # La pieza que contiene al territorio debe tocar su banda.
            piece = None
            for g in zone.geometry:
                for q in getattr(g, "geoms", [g]):
                    if q.distance(pt) < 1.0:
                        piece = q
                        break
            if piece is None or not piece.intersects(band):
                bad.append(f"{name} (sin brazo)")
    return Result("territorios nombrados resueltos", not bad,
                  f"los {len(TERRITORIES)} de la tabla"
                  if not bad else ", ".join(bad))


def _zone_fixes_applied(land: gpd.GeoDataFrame) -> Result:
    """Cada correccion de huso debe estar reflejada en el cache."""
    from shapely.geometry import Point
    from .zone_fixes import FIXES
    bad = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        parts = land.explode(index_parts=False, ignore_index=True)
        for name, lon, lat, correct in FIXES:
            pt = Point(lon, lat)
            d = parts.geometry.distance(pt)
            if d.min() > 1.0:
                bad.append(f"{name} (no encontrada)")
                continue
            got = float(parts.at[d.idxmin(), "std_hours"])
            if got != correct:
                bad.append(f"{name} (UTC{got:+g}, deberia UTC{correct:+g})")
    return Result("correcciones de huso aplicadas", not bad,
                  f"las {len(FIXES)} de la tabla" if not bad else ", ".join(bad))


def _ruler_matches_map() -> Result:
    """La regla cubre 24 horas, igual que los 360 grados del mapa."""
    worst = 0.0
    for k in range(-11, 12):
        ruler = (k + 0.5 + 12.0) / 24.0
        mapa = (15 * k + 7.5 + 180.0) / 360.0
        worst = max(worst, abs(ruler - mapa))
    mm = worst * 1189
    return Result("regla alineada con el mapa", mm < 0.2,
                  f"desvio maximo {mm:.3f} mm sobre A0")


def _offsets_have_a_column(land: gpd.GeoDataFrame) -> Result:
    """Ningun offset real puede quedar fuera de la regla."""
    from .render import _fractional_by_column
    extra = {lab for labs in _fractional_by_column().values() for lab in labs}
    missing = []
    for h in sorted(float(v) for v in land["std_hours"].unique()):
        if h == int(h) and -12 <= h <= 12:
            continue
        whole = int(h)
        mins = round(abs(h - whole) * 60)
        lab = f"{whole:+d}" + (f":{mins:02d}" if mins else "")
        if lab not in extra:
            missing.append(lab)
    return Result("todo offset tiene columna", not missing,
                  "todos" if not missing else f"faltan {missing}")


def run() -> bool:
    land = gpd.read_file(CACHE / "zones_land.gpkg")
    sea = gpd.read_file(CACHE / "zones_sea.gpkg")
    results = [
        _no_runaway_pieces(sea),
        _sea_covers_world(sea),
        _sea_no_overlap(sea),
        _land_inside_own_zone(land, sea),
        _fractional_zones_stay_local(land, sea),
        _named_territories_resolve(land, sea),
        _zone_fixes_applied(land),
        _ruler_matches_map(),
        _offsets_have_a_column(land),
    ]
    print("\ninvariantes:")
    for r in results:
        print(r)
    ok = all(r.ok for r in results)
    print("  ->", "todo bien" if ok else "HAY FALLAS")
    return ok
