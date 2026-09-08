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
    # Islas oceanicas brasilenas, todas en UTC-2
    ("Fernando de Noronha", "BRASIL", -32.42,  -3.86),
    ("Trindade",            "BRASIL", -29.33, -20.57),
    ("San Pedro y San Pablo", "BRASIL", -29.35,  0.92),
    ("Atol das Rocas",      "BRASIL", -33.81,  -3.87),
    # Enclaves de Groenlandia con huso propio
    ("Danmarkshavn",        "DIN.",   -18.80,  76.80),
    ("Pituffik",            "DIN.",   -68.70,  76.55),
]


def _norm(name: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return s.lower().strip()


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
        ["SOVEREIGNT", "NAME_ES", "geometry"]]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        pts = reg.geometry.representative_point()
        pt_gdf = gpd.GeoDataFrame({"idx": reg.index}, geometry=pts, crs=reg.crs)
        joined = gpd.sjoin(pt_gdf, admin, how="left", predicate="within")

    sov_by_idx = dict(zip(joined["idx"], joined["SOVEREIGNT"]))
    for (i, r), pt in zip(reg.iterrows(), pts):
        name = r["NAME_ES"] or r["NAME"]
        if not name or _norm(name) in taken:
            continue           # ya esta rotulada como pais
        taken.add(_norm(name))
        sov = sov_by_idx.get(i)
        abbr = SOVEREIGN_OVERRIDES.get(name) or (
            SOVEREIGN_ABBR.get(sov) if sov else None)
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

    df = pd.DataFrame(rows)
    return gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
