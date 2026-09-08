"""Arma la tabla unica de rotulos: paises e islas juntos.

Van en una sola tabla porque compiten por el mismo espacio. Cuando las
islas se dibujaban aparte, se superponian con los nombres de paises: el
motor de colisiones no las veia.

La prioridad decide quien se queda con el mejor lugar. Los paises se
ordenan por superficie; las islas por el SCALERANK de Natural Earth, que
existe para esto (0 = Melanesia, Groenlandia; 7 = islotes).
"""
from __future__ import annotations

import warnings
from pathlib import Path

import geopandas as gpd
import pandas as pd

RAW = Path("data/raw")

# Abreviaturas de soberania, al modo de los mapas murales.
SOVEREIGN_ABBR = {
    "United Kingdom": "R.U.", "France": "FRANCIA", "United States of America": "EE.UU.",
    "Netherlands": "P. BAJOS", "Denmark": "DIN.", "Norway": "NOR.",
    "Portugal": "PORT.", "Spain": "ESP.", "Australia": "AUSTR.",
    "New Zealand": "N.Z.", "Chile": "CHILE", "Ecuador": "ECUADOR",
    "Brazil": "BRASIL", "Russia": "RUSIA", "China": "CHINA", "Japan": "JAPÓN",
    "India": "INDIA", "Italy": "ITALIA", "Greece": "GRECIA", "Canada": "CANADÁ",
    "Argentina": "ARG.", "Colombia": "COL.", "Venezuela": "VEN.",
    "Yemen": "YEMEN", "Oman": "OMÁN", "South Africa": "SUDÁFRICA",
    "Finland": "FINL.", "Sweden": "SUECIA", "Estonia": "EST.",
    "Indonesia": "INDONESIA", "Malaysia": "MALASIA", "Philippines": "FILIPINAS",
    "South Korea": "COREA S.", "Taiwan": "TAIWÁN", "Mexico": "MÉXICO",
    "Honduras": "HOND.", "Nicaragua": "NIC.", "Panama": "PANAMÁ",
    "Costa Rica": "C. RICA", "Cuba": "CUBA", "Turkey": "TURQUÍA",
    "Egypt": "EGIPTO", "Eritrea": "ERITREA", "Tanzania": "TANZANIA",
    "Mozambique": "MOZAMB.", "Kenya": "KENIA", "Croatia": "CROACIA",
    "Ireland": "IRLANDA", "Iceland": "ISLANDIA", "Germany": "ALEMANIA",
}


# Soberania asignada a mano, por encima del cruce con Natural Earth.
# Natural Earth refleja el control efectivo; este mapa se hace desde la
# posicion argentina, coherente con rotular el archipielago como Islas
# Malvinas y no como Falkland Islands.
# Por unidad administrativa: alcanza a cualquier isla del archipielago,
# aparezca hoy o mas adelante. Por nombre habia que enumerar islote por
# islote, y las que no llegaban a rotularse quedaban como config muerta.
ADMIN_SOVEREIGN_OVERRIDES = {
    "Falkland Islands": "ARGENTINA",
    "South Georgia and the Islands": "ARGENTINA",
}

SOVEREIGN_OVERRIDES = {
    "Isla Gran Malvina": "ARGENTINA",
    "Isla Soledad": "ARGENTINA",
    "San Pedro": "ARGENTINA",             # Georgia del Sur
    "Islas Sandwich del Sur": "ARGENTINA",
    # Sin poligono admin_0 encima, el cruce espacial no le asigna nada.
    "Archipiélago de Chagos": "R.U.",
}


# Territorios que Natural Earth no trae como isla nombrada. Sin esto
# quedan sin rotulo, aunque el mapa les dibuje su recuadro.
#     (nombre, soberania, lon, lat)
EXTRA_LABELS = [
    ("Ascensión",        "R.U.", -14.37,  -7.95),
    ("Tristán de Acuña", "R.U.", -12.28, -37.11),
    ("Isla Gough",       "R.U.",  -9.88, -40.32),
    ("Lord Howe",        "AUSTR.", 159.08, -31.55),
    ("Islas Cocos",      "AUSTR.",  96.87, -12.17),
    # Islas oceanicas brasilenas, todas en UTC-2
    ("Fernando de Noronha", "BRASIL", -32.42,  -3.86),
    ("Trindade",            "BRASIL", -29.33, -20.57),
    ("San Pedro y San Pablo", "BRASIL", -29.35,  0.92),
    ("Atol das Rocas",      "BRASIL", -33.81,  -3.87),
    # Enclaves de Groenlandia con huso propio
    ("Danmarkshavn",        "DIN.",   -18.80,  76.80),
    ("Pituffik",            "DIN.",   -68.70,  76.55),
]


# GeoNames devuelve el nombre ingles de varias islas menores de Malvinas.
# En un mapa en castellano no corresponde.
ISLAND_NAME_OVERRIDES = {
    "Weddell Island": "Isla San José",
    "Pebble Island": "Isla Borbón",
    "Saunders Island": "Isla Trinidad",
    "Keppel Island": "Isla de la Vigía",
    "Lively Island": "Isla Bougainville",
    "George Island": "Isla Jorge",
    "Speedwell Island": "Isla Águila",
    "Beaver Island": "Isla San Rafael",
    "New Island": "Isla Goicoechea",
    "Montagu Island": "Isla Montagu",
}


def _norm(name: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return s.lower().strip()


# Un poligono mas chico que esto mide menos de 1 mm a A0: rotularlo es
# poner un nombre sobre nada.
ISLAND_MIN_DEG2 = 0.01
# Por encima de esto es un continente o una isla mayor, que ya viene
# nombrada por Natural Earth.
ISLAND_MAX_DEG2 = 5.0
# Que isla merece rotulo. El archipielago patagonico, el delta del Amazonas
# y la costa noruega aportaban solos cientos de nombres sobre manchas de un
# milimetro, todas pegadas a su continente.
#
# Se muestra si cumple alguna de estas tres:
#   1. es grande en terminos absolutos
#   2. domina su vecindario: no hay tierra mucho mayor a la vuelta
#   3. GeoNames le registra un nombre en espanol propio, que solo tienen
#      5.657 de 175.000 y funciona como senal de notoriedad
#
# Ninguna alcanza sola. Por tamano se cuelan las patagonicas; por dominancia
# se pierden Chiloe, Sicilia y Vancouver, pegadas a un continente enorme; y
# la notoriedad falla justo donde el nombre local ya es espanol.
ISLAND_BIG_DEG2 = 0.75
DOMINANCE_RADIUS_DEG = 1.0
DOMINANCE_RATIO = 3.0


def _dominates(i: int, geom, area: float, parts: gpd.GeoDataFrame,
               sindex) -> bool:
    """No hay tierra mucho mas grande a la vuelta."""
    d = DOMINANCE_RADIUS_DEG
    x0, y0, x1, y1 = geom.bounds
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        for j in sindex.intersection((x0 - d, y0 - d, x1 + d, y1 + d)):
            if j == i:
                continue
            other = parts.iloc[j]
            if (other["_area"] >= area * DOMINANCE_RATIO
                    and other.geometry.distance(geom) < d):
                return False
    return True


def _islands_from_geometry(land: gpd.GeoDataFrame, taken: set,
                           rows_so_far: list[dict]) -> list[dict]:
    """Una etiqueta por poligono de isla, con el mejor nombre de GeoNames.

    Se va desde la geometria y no desde el gazetteer: GeoNames tiene 175.000
    islas, de las cuales 78.000 caen dentro de masas continentales (islas de
    rio, islotes costeros) y la mayoria del resto no se ve a esta escala. El
    mapa aguanta unas 2.000 etiquetas en total, asi que lo que manda es que
    el poligono exista y se vea.
    """
    import pandas as pd

    from .geonames import build_cache
    gn = build_cache()
    parts = land.explode(index_parts=False, ignore_index=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        parts["_area"] = parts.geometry.area
    all_parts = parts.reset_index(drop=True)
    all_ix = all_parts.sindex

    gn["has_es"] = gn["name_es"] != gn["name"]
    pts = gpd.GeoDataFrame(
        gn.copy(), geometry=gpd.points_from_xy(gn["lon"], gn["lat"]),
        crs="EPSG:4326")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        notable = set(gpd.sjoin(pts[pts["has_es"]], all_parts[["geometry"]],
                                how="inner", predicate="within")["index_right"])

    # Las que no pasan el corte no se descartan: van en cuerpo minusculo,
    # como capa de detalle. De lejos el mapa se lee limpio; de cerca
    # aparecen los nombres.
    # Se rotulan todas las que se ven; lo que cambia es el cuerpo. Una isla
    # va a la capa de detalle si no es grande ni domina su vecindario.
    #
    # La notoriedad (que GeoNames le registre nombre en espanol) no entra
    # aca: sirve para saber si vale la pena nombrarla, no de que tamano.
    # Dirk Hartog tiene nombre registrado pero mide 0.06 grados^2 pegada a
    # Australia, y le corresponde detalle, no un rotulo de 4 pt.
    sel, minor = [], set()
    for i, (g, a) in enumerate(zip(all_parts.geometry, all_parts["_area"])):
        if not (ISLAND_MIN_DEG2 <= a <= ISLAND_MAX_DEG2):
            continue
        sel.append(i)
        if not (a >= ISLAND_BIG_DEG2
                or _dominates(i, g, a, all_parts, all_ix)):
            minor.add(i)                  # se rotula, pero en detalle
    parts = all_parts.iloc[sel].reset_index(drop=True)
    minor_local = {k for k, i in enumerate(sel) if i in minor}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        j = gpd.sjoin(pts, parts[["_area", "geometry"]], how="inner",
                      predicate="within")
    # Mejor candidato por poligono: primero el que tiene nombre en espanol
    # propio, despues archipielago sobre isla suelta.
    j["has_es"] = j["has_es"].astype(int)
    j = j.sort_values(["index_right", "has_es", "rank_code"],
                      ascending=[True, False, True])
    best = j.groupby("index_right").first()

    # ADMIN y SOVEREIGNT solo difieren en las dependencias. Mostrar la
    # soberania cuando coinciden llenaba el archipielago indonesio de
    # "(INDONESIA)" sin agregar informacion.
    admin = gpd.read_file(RAW / "ne_10m_admin_0_countries.zip")[
        ["SOVEREIGNT", "ADMIN", "geometry"]]
    reps = parts.geometry.representative_point()
    rep_gdf = gpd.GeoDataFrame({"i": range(len(parts))},
                               geometry=reps.to_numpy(), crs=parts.crs)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        sov = gpd.sjoin(rep_gdf, admin, how="left", predicate="within")
    sov_by_i = {i: (so if so != ad else None)
                for i, so, ad in zip(sov["i"], sov["SOVEREIGNT"], sov["ADMIN"])}
    admin_by_i = dict(zip(sov["i"], sov["ADMIN"]))

    # Un poligono que ya tiene rotulo no recibe otro. Sin esto salian
    # "Isla Gran Nicobar" (Natural Earth) y "Great Nicobar Island"
    # (GeoNames) sobre la misma isla.
    placed_pts = gpd.GeoDataFrame(
        {"j": range(len(rows_so_far))},
        geometry=gpd.points_from_xy([r["lon"] for r in rows_so_far],
                                    [r["lat"] for r in rows_so_far]),
        crs="EPSG:4326")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        occupied = set(gpd.sjoin(placed_pts, parts[["geometry"]], how="inner",
                                 predicate="within")["index_right"])

    rows = []
    for i, r in best.iterrows():
        if i in occupied:
            continue
        name = ISLAND_NAME_OVERRIDES.get(r["name"], r["name_es"])
        if not name or _norm(name) in taken:
            continue
        taken.add(_norm(name))
        abbr = (SOVEREIGN_OVERRIDES.get(name)
                or ADMIN_SOVEREIGN_OVERRIDES.get(admin_by_i.get(i))
                or SOVEREIGN_ABBR.get(sov_by_i.get(i)))
        if abbr and _norm(abbr) == _norm(name):
            abbr = None
        pt = reps.iloc[i]
        area = float(parts.at[i, "_area"])
        rows.append({
            "kind": "island", "name": name, "sovereign": abbr,
            "priority": float(area), "lon": pt.x, "lat": pt.y,
            "rank": 8 if i in minor_local else (
                4 if area > 0.5 else (5 if area > 0.05 else 6)),
        })
    return rows


# Ciudades. SCALERANK 0 son las capitales mundiales; 4 llega a 1128, que es
# donde el papel empieza a llenarse. Se puede subir, pero compiten con las
# islas por el mismo espacio.
CITY_MAX_SCALERANK = 4


def _cities(taken: set) -> list[dict]:
    cities = gpd.read_file(RAW / "ne_10m_populated_places.zip")
    cities = cities[cities["SCALERANK"] <= CITY_MAX_SCALERANK]
    rows = []
    for _, c in cities.iterrows():
        name = c["NAME_ES"] or c["NAME"]
        if not name or _norm(name) in taken:
            continue
        taken.add(_norm(name))
        sr = int(c["SCALERANK"])
        rows.append({
            "kind": "city", "name": name, "sovereign": None,
            # Por debajo de los paises, por encima de las islas menores.
            "priority": float(100 - sr),
            "lon": float(c.geometry.x), "lat": float(c.geometry.y),
            "rank": sr,
        })
    return rows


def build(countries: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    rows = []

    # --- paises: prioridad por superficie proyectada aproximada ---
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        areas = countries.geometry.area
    for (_, c), a in zip(countries.iterrows(), areas):
        rows.append({
            "kind": "country", "name": c["name_es"], "sovereign": None,
            "priority": float(a) * 1000.0,     # los paises mandan
            "lon": float(c["LABEL_X"]), "lat": float(c["LABEL_Y"]),
            "rank": 0,
        })
    taken = {_norm(r["name"]) for r in rows}

    # --- islas y archipielagos ---
    reg = gpd.read_file(RAW / "ne_10m_geography_regions_polys.zip")
    # reset_index es necesario: al construir el GeoDataFrame de puntos con
    # una columna desde sub.index, pandas crea un indice nuevo y realinea la
    # geometria contra el, desfasando ids y puntos. Asi Hainan salia noruega.
    reg = reg[reg["FEATURECLA"].isin(["Island", "Island group"])].reset_index(drop=True)
    admin = gpd.read_file(RAW / "ne_10m_admin_0_countries.zip")[
        ["SOVEREIGNT", "ADMIN", "NAME_ES", "geometry"]]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        pts = reg.geometry.representative_point()
        pt_gdf = gpd.GeoDataFrame({"idx": reg.index}, geometry=pts, crs=reg.crs)
        joined = gpd.sjoin(pt_gdf, admin, how="left", predicate="within")

    # Solo se muestra la soberania de las dependencias: ADMIN y SOVEREIGNT
    # difieren ahi. En una isla del propio pais no agrega nada.
    sov_by_idx = {i: (so if so != ad else None)
                  for i, so, ad in zip(joined["idx"], joined["SOVEREIGNT"],
                                       joined["ADMIN"])}
    admin_by_idx = dict(zip(joined["idx"], joined["ADMIN"]))
    for (i, r), pt in zip(reg.iterrows(), pts):
        name = r["NAME_ES"] or r["NAME"]
        if not name or _norm(name) in taken:
            continue           # ya esta rotulada como pais
        taken.add(_norm(name))
        sov = sov_by_idx.get(i)
        abbr = (SOVEREIGN_OVERRIDES.get(name)
                or ADMIN_SOVEREIGN_OVERRIDES.get(admin_by_idx.get(i))
                or (SOVEREIGN_ABBR.get(sov) if sov else None))
        if abbr and _norm(abbr) == _norm(name):
            abbr = None        # la isla es el pais
        rank = int(r["SCALERANK"]) if pd.notna(r["SCALERANK"]) else 7
        rows.append({
            "kind": "island", "name": name, "sovereign": abbr,
            "priority": float(8 - rank),      # por debajo de cualquier pais
            "lon": float(pt.x), "lat": float(pt.y), "rank": rank,
        })

    for name, sov, lon, lat in EXTRA_LABELS:
        if _norm(name) in taken:
            continue
        taken.add(_norm(name))
        rows.append({"kind": "island", "name": name, "sovereign": sov,
                     "priority": 3.0, "lon": lon, "lat": lat, "rank": 5})

    rows += _cities(taken)

    land = gpd.read_file("data/cache/zones_land.gpkg")
    rows += _islands_from_geometry(land, taken, rows)

    df = pd.DataFrame(rows)
    return gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
