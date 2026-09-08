"""Generaliza los husos sobre el mar al modo de los mapas murales clasicos.

En mar abierto el limite es el meridiano teorico. Cerca de un continente la
banda se dobla siguiendo la costa. Los territorios sueltos se encierran en
un recuadro, y algunos ademas llevan un brazo angosto que los une con su
banda, como las Azores o Jan Mayen en el mapa de la CIA.

No es la forma fisica de las aguas territoriales: es una convencion de
dibujo, mas legible que el poligono real.

Sobre el diseno de este modulo
------------------------------
Los casos raros se enumeran en TERRITORIES, con nombre. No se derivan de
reglas automaticas. Se intento al reves y no funciono: cada regla nueva
(por tamano, por distancia a la banda, por cercania a tierra propia)
arreglaba un caso y rompia otro, porque la geografia no se deja capturar
por umbrales. La regla de cercania, agregada para las islas al sur de
Tierra del Fuego, dejo a Islandia sin brazo porque tiene islotes al lado
que cuentan como tierra propia.

Lo automatico se limita a lo que es seguro: un recuadro suelto, sin brazo,
para cualquier isla chica que caiga fuera de su banda. Sin brazos
automaticos no hay corredores largos, que es de donde salian las franjas
que cruzaban el mapa entero.
"""
from __future__ import annotations

import warnings

import geopandas as gpd
from shapely.geometry import Point, box
from shapely.ops import nearest_points, unary_union

# --- recuadros automaticos ---------------------------------------------
# Trozo de tierra que se considera isla y puede llevar recuadro.
ISLAND_MIN_DEG2 = 0.015      # por debajo son rocas: encajonarlas es ruido
ISLAND_MAX_DEG2 = 12.0       # por encima es continente
ISLAND_PAD = 1.5             # margen del recuadro, en grados
CLUSTER_ENVELOPE_MAX_RATIO = 2.6   # cuan disperso puede ser un archipielago
# Una isla pegada a tierra de su mismo huso no necesita recuadro: ya esta
# conectada. Esta regla antes dejaba a Islandia sin brazo (tiene islotes al
# lado); ahora es segura porque los casos nombrados no pasan por aca.
NEAR_OWN_LAND_DEG = 2.0

# --- brazos -------------------------------------------------------------
CONNECTOR_PAD = 0.7          # semialtura del corredor; mas fino que un recuadro
# Un archipielago son varias partes: el recuadro las abarca a todas, no
# solo a la mas cercana al punto de la tabla. Sin esto, en las Islas del
# Principe Eduardo quedaba Marion adentro y la otra afuera.
GROUP_RADIUS_DEG = 3.0
# Alcance en el que "arm+" busca la tierra principal de su huso.
ARM_PLUS_REACH_DEG = 12.0

# --- contorno mar adentro ----------------------------------------------
# Un continente que sobresale de su banda no lleva el limite calcado sobre
# su costa. Se usa un CIERRE morfologico (dilatar y contraer): rellena
# fiordos y bahias sin agrandar el reclamo. Una dilatacion pura hacia que
# cada continente invadiera las bandas vecinas.
CLOSING_DEG = 1.3
OFFSHORE_PAD = 0.35
# El relleno de fiordos lo hace el cierre, no esto: aca solo se bajan
# vertices. A 0.7 grados (~78 km) convertia la costa de mares chicos en
# segmentos rectos larguisimos, y el Golfo Persico quedaba como un poligono
# angular arbitrario.
OFFSHORE_SIMPLIFY = 0.2
# Solo las masas de tierra grandes aportan contorno mar adentro. Sobre
# atolones dispersos el cierre los une en manchas y el simplify las vuelve
# triangulos arbitrarios: asi se veia la Polinesia Francesa. Las islas
# chicas ya tienen el mecanismo de recuadro, que se lee como intencional.
OFFSHORE_MIN_DEG2 = 12.0


# Modos:
#   "arm"   recuadro angosto + brazo hasta su banda
#   "arm+"  ademas se estira hasta la tierra de su mismo huso, fundiendo
#           territorio y continente en una sola forma (nadie lo usa hoy)
#   "box"   recuadro suelto, sin brazo
#   "none"  sin recuadro; queda solo el contorno mar adentro
#
#            nombre             lon      lat    huso   modo
TERRITORIES = [
    ("Islandia",              -19.00,   64.90,   0.0, "arm"),
    ("Jan Mayen",              -8.44,   70.99,   1.0, "arm"),
    ("Azores",                -28.00,   38.50,  -1.0, "arm"),
    # Sin brazo: el corredor hacia su banda tendria que atravesar Marruecos
    # y el Sahara Occidental, que son UTC+1. La CIA tambien los deja sueltos.
    ("Madeira",               -16.90,   32.70,   0.0, "box"),
    ("Islas Canarias",        -15.60,   28.10,   0.0, "box"),
    # Su borde este queda a 0.2 grados de la banda de UTC-1, asi que el
    # recuadro ya la toca y no se genera brazo. Con altura de corredor las
    # islas lo llenaban por completo: como caja respira.
    ("Cabo Verde",            -23.60,   15.10,  -1.0, "box"),
    ("Isla de Pascua",       -109.35,  -27.13,  -6.0, "arm"),
    # La Isla Grande cae dentro de la banda pero Oahu y Kauai no, y Maui
    # queda descartada por estar pegada a una mayor: el archipielago se
    # dibujaba como puntos sueltos. Agrupado se lee como una unidad.
    ("Hawái",                -157.50,   20.50, -10.0, "box"),
    # Kerguelen y Amsterdam caen dentro de la banda de UTC+5; Crozet no.
    ("Islas Crozet",           51.50,  -46.40,   5.0, "arm"),
    # Marion queda a 0.075 grados de la banda de UTC+2, asi que el recuadro
    # ya la toca; solo hacia falta que abarcara tambien la isla menor.
    ("Islas del Príncipe Eduardo", 37.75, -46.85, 2.0, "box"),
    ("Islas Malvinas",        -59.00,  -51.80,  -3.0, "arm"),
    # Territorios britanicos del Atlantico sur y del Indico: todos por
    # debajo del umbral de recuadro automatico, asi que sin entrada aqui
    # quedaban como puntos sueltos del color equivocado.
    ("Ascensión",             -14.37,   -7.95,   0.0, "arm"),
    ("Tristán de Acuña",      -12.28,  -37.11,   0.0, "arm"),
    ("Isla Gough",             -9.88,  -40.32,   0.0, "arm"),
    ("Archipiélago de Chagos", 72.42,   -7.31,   6.0, "arm"),
    # UTC+10:30 no tiene banda teorica propia (solo la tienen las horas
    # enteras), asi que no hay adonde estirar: recuadro suelto.
    ("Lord Howe",             159.08,  -31.55,  10.5, "box"),
    # Auckland, Campbell y las demas subantarticas son todas UTC+12 igual
    # que Nueva Zelanda. Sueltas quedaban como recuadros aislados; con
    # "arm+" el huso se estira y se lee como una sola zona.
    ("Subantárticas de N.Z.",  167.50,  -51.50,  12.0, "arm+"),
    # UTC+5:30 no tiene banda propia y comparte color con la banda de UTC+5
    # donde caen: sin recuadro se leen como si fueran +5.
    ("Islas Laquedivas",       72.64,   10.57,   5.5, "box"),
    ("Islas Cocos",            96.87,  -12.17,   6.5, "box"),
]


def params() -> dict:
    return {
        "ISLAND_MIN_DEG2": ISLAND_MIN_DEG2, "ISLAND_MAX_DEG2": ISLAND_MAX_DEG2,
        "ISLAND_PAD": ISLAND_PAD, "CONNECTOR_PAD": CONNECTOR_PAD,
        "CLUSTER_ENVELOPE_MAX_RATIO": CLUSTER_ENVELOPE_MAX_RATIO,
        "CLOSING_DEG": CLOSING_DEG, "OFFSHORE_PAD": OFFSHORE_PAD,
        "OFFSHORE_SIMPLIFY": OFFSHORE_SIMPLIFY,
        "OFFSHORE_MIN_DEG2": OFFSHORE_MIN_DEG2,
        "TERRITORIES": [(t[0], t[4]) for t in TERRITORIES],
    }


def _theoretical_band(k: float, lat: tuple[float, float]):
    """Las bandas de 15 grados existen solo para las horas enteras.

    Dandole banda propia a un huso fraccionario, -3:30 reclamaba una franja
    de polo a polo en el Atlantico Sur, con un limite invisible porque
    comparte color con -3.
    """
    if k != int(k):
        return None
    west, east = max(15 * k - 7.5, -180.0), min(15 * k + 7.5, 180.0)
    if west >= east:
        return None
    return box(west, lat[0], east, lat[1])


def _polygons_only(geom):
    """Recortar contra el mundo puede devolver una GeometryCollection con
    lineas sueltas, y sobre eso .boundary da None mas adelante."""
    parts = [g for g in getattr(geom, "geoms", [geom])
             if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty]
    return unary_union(parts) if parts else geom


def _merge_clusters(rects: list) -> list:
    """Fusiona recuadros que se tocan y los reemplaza por uno solo."""
    merged = unary_union(rects)
    out = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        for g in getattr(merged, "geoms", [merged]):
            env = g.envelope
            out.append(env if env.area <= g.area * CLUSTER_ENVELOPE_MAX_RATIO else g)
    return out


def _nearest_part(parts: gpd.GeoDataFrame, hours: float, lon: float, lat_: float):
    """Todas las partes de ese huso cercanas al punto, como una sola pieza.

    Devuelve la union, no la parte mas cercana: un archipielago tiene que
    quedar entero dentro de su recuadro.
    """
    cand = parts[parts["std_hours"] == hours]
    if cand.empty:
        return None
    pt = Point(lon, lat_)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        d = cand.geometry.distance(pt)
        group = cand[d <= GROUP_RADIUS_DEG]
        if group.empty:
            group = cand.loc[[d.idxmin()]]
        return unary_union(list(group.geometry))


def _near_own_land(row, parts: gpd.GeoDataFrame, sindex) -> bool:
    """La isla tiene tierra MAS GRANDE de su mismo huso a un paso.

    El tamano importa: sirve para no encajonar islotes pegados a su
    continente, pero un archipielago tiene islotes propios y esos no deben
    contar. Socotra (0.30 grados^2) quedaba sin recuadro porque sus propios
    satelites (0.00 a 0.01) disparaban la regla.
    """
    g = row.geometry
    x0, y0, x1, y1 = g.bounds
    d = NEAR_OWN_LAND_DEG
    hits = list(sindex.intersection((x0 - d, y0 - d, x1 + d, y1 + d)))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        for i in hits:
            other = parts.iloc[i]
            if other["std_hours"] != row["std_hours"]:
                continue
            if other.geometry.equals(g):
                continue
            if other["_area"] <= row["_area"]:
                continue
            if other.geometry.distance(g) < d:
                return True
    return False


def _borders_other_zone(geom, parts: gpd.GeoDataFrame, sindex) -> bool:
    """El trozo limita por tierra con otro huso.

    Entonces no es una isla sino un enclave dentro de una masa continental,
    y no le corresponde recuadro. Eucla (UTC+8:45) limita con UTC+8 y
    UTC+9:30; su recuadro le metia una caja en la Gran Bahia Australiana.
    """
    x0, y0, x1, y1 = geom.bounds
    d = 0.15
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        for j in sindex.intersection((x0 - d, y0 - d, x1 + d, y1 + d)):
            other = parts.iloc[j]
            if other.geometry.equals(geom):
                continue
            if other.geometry.distance(geom) < d:
                return True
    return False


def _build_boxes(parts: gpd.GeoDataFrame, lat: tuple[float, float]):
    """Recuadros automaticos para islas chicas, y los casos nombrados.

    Devuelve tambien las partes que recibieron recuadro: son las islas que
    difieren de su banda, es decir las que vale la pena rotular en el mapa.
    """
    boxes: dict[float, list] = {}
    arms: dict[float, list] = {}
    boxed: list = []
    named = {(t[0]) for t in TERRITORIES}
    skip_geoms = []

    for name, lon, la, h, mode in TERRITORIES:
        geom = _nearest_part(parts, float(h), lon, la)
        if geom is not None:
            skip_geoms.append(geom)

    small = parts[(parts["_area"] >= ISLAND_MIN_DEG2)
                  & (parts["_area"] <= ISLAND_MAX_DEG2)]
    sindex = parts.sindex
    parts_r = parts.reset_index(drop=True)
    for _, r in small.iterrows():
        h = float(r["std_hours"])
        if any(r.geometry.equals(g) for g in skip_geoms):
            continue                      # lo maneja su entrada nombrada
        x0, y0, x1, y1 = r.geometry.bounds
        band = _theoretical_band(h, lat)
        if band is not None and band.contains(box(x0, y0, x1, y1)):
            continue                      # ya cae dentro de su banda
        if _near_own_land(r, parts, sindex):
            continue                      # su continente esta al lado
        if _borders_other_zone(r.geometry, parts_r, sindex):
            continue                      # enclave continental, no una isla
        boxes.setdefault(h, []).append(
            box(x0 - ISLAND_PAD, max(y0 - ISLAND_PAD, lat[0]),
                x1 + ISLAND_PAD, min(y1 + ISLAND_PAD, lat[1])))
        boxed.append({"std_hours": h, "named": None, "geometry": r.geometry})
    boxes = {h: _merge_clusters(v) for h, v in boxes.items()}

    unresolved = []
    for name, lon, la, h, mode in TERRITORIES:
        h = float(h)
        geom = _nearest_part(parts, h, lon, la)
        if geom is None:
            unresolved.append(name)
            continue
        boxed.append({"std_hours": h, "named": name, "geometry": geom})
        if mode == "none":
            continue
        x0, y0, x1, y1 = geom.bounds
        bx0, bx1 = x0 - ISLAND_PAD, x1 + ISLAND_PAD
        band = _theoretical_band(h, lat)
        if mode == "arm+":
            # Corredor hasta la tierra mas cercana del mismo huso, en la
            # direccion que haga falta. Estirar solo hacia el oeste no
            # servia para las subantarticas de Nueva Zelanda, que tienen su
            # continente al norte.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                # Se excluye lo que toca al grupo, no solo lo identico: el
                # grupo es una union de varias partes, asi que ninguna parte
                # suelta le era igual y sus propias islas quedaban como
                # candidatas. La mas cercana era ella misma, a distancia
                # cero, y el corredor colapsaba.
                same = parts[(parts["std_hours"] == h)
                             & (~parts.geometry.intersects(geom))]
                if not same.empty:
                    d = same.geometry.distance(geom)
                    same = same[d <= ARM_PLUS_REACH_DEG]
                if not same.empty:
                    # La tierra MAS GRANDE del huso, no la mas cercana:
                    # apuntando a la mas cercana el corredor se detenia en
                    # las Snares y no llegaba a Nueva Zelanda.
                    j = same["_area"].idxmax()
                    _, near = nearest_points(geom, same.loc[j].geometry)
                    # Rellena todo el area entre el grupo y su tierra, no un
                    # corredor angosto: el mar entre Stewart y las Auckland
                    # es parte del mismo huso y quedaba de otro color.
                    arms.setdefault(h, []).append(
                        box(min(bx0, near.x), min(y0 - ISLAND_PAD, near.y),
                            max(bx1, near.x), max(y1 + ISLAND_PAD, near.y)))
        if mode == "box" or band is None:
            boxes.setdefault(h, []).append(
                box(bx0, max(y0 - ISLAND_PAD, lat[0]),
                    bx1, min(y1 + ISLAND_PAD, lat[1])))
            continue
        # Recuadro y brazo comparten altura: el conjunto queda como un
        # corredor uniforme y no como un bloque con escalon.
        by0 = max(y0 - CONNECTOR_PAD, lat[0])
        by1 = min(y1 + CONNECTOR_PAD, lat[1])
        boxes.setdefault(h, []).append(box(bx0, by0, bx1, by1))
        w, e = band.bounds[0], band.bounds[2]
        if bx1 < w:
            arms.setdefault(h, []).append(box(bx1, by0, w, by1))
        elif bx0 > e:
            arms.setdefault(h, []).append(box(e, by0, bx0, by1))

    for h, v in arms.items():
        boxes.setdefault(h, []).extend(v)
    return boxes, unresolved, boxed


def _offshore_per_landmass(parts: gpd.GeoDataFrame) -> dict:
    """Contorno mar adentro, calculado por masa de tierra y no por huso.

    Groenlandia tiene tres husos. Inflando cada uno por separado, Thule
    generaba una cuna angular sobre la bahia de Baffin y Danmarkshavn, mas
    chico que el umbral, no generaba nada. El contorno es una propiedad de
    la costa, no del huso: se calcula una vez por masa de tierra y se
    reparte entre los husos que la componen, de mayor a menor superficie.
    """
    out: dict[float, list] = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        big = parts[parts["_area"] > OFFSHORE_MIN_DEG2]
        if big.empty:
            return {}
        masses = gpd.GeoSeries(
            [unary_union(list(big.geometry))]).explode(index_parts=False)
        for mass in masses:
            if mass.area <= OFFSHORE_MIN_DEG2:
                continue
            ring = (mass.buffer(CLOSING_DEG).buffer(-CLOSING_DEG)
                        .buffer(OFFSHORE_PAD)
                        .simplify(OFFSHORE_SIMPLIFY)
                        .buffer(0))
            here = big[big.geometry.intersects(mass)]
            if here.empty:
                continue
            order = (here.groupby("std_hours")["_area"].sum()
                         .sort_values(ascending=False))
            taken = None
            for h in order.index:
                own = unary_union(list(here[here["std_hours"] == h].geometry))
                claim = ring.intersection(own.buffer(CLOSING_DEG + OFFSHORE_PAD))
                if taken is not None:
                    claim = claim.difference(taken)
                if claim.is_empty:
                    continue
                out.setdefault(float(h), []).append(claim)
                taken = claim if taken is None else unary_union([taken, claim])
    return {h: unary_union(v) for h, v in out.items()}


def build(land_zones: gpd.GeoDataFrame,
          lat: tuple[float, float] = (-90.0, 90.0)) -> gpd.GeoDataFrame:
    parts = land_zones.explode(index_parts=False, ignore_index=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        parts["_area"] = parts.geometry.area   # a proposito en grados^2

    boxes, unresolved, boxed = _build_boxes(parts, lat)
    if unresolved:
        print(f"  aviso: territorios sin resolver: {', '.join(unresolved)}")

    land_by_zone = {float(h): g for h, g in
                    land_zones.set_index("std_hours").geometry.items()}
    offshore_by_zone = _offshore_per_landmass(parts)
    all_h = sorted(set(land_by_zone) | set(boxes)
                   | {float(k) for k in range(-12, 13)})

    # Cuatro niveles de prioridad, de mayor a menor:
    #   1. tierra     - es el dato, nunca se cede
    #   2. recuadros  - existen para sobresalir de la banda, asi que le ganan
    #   3. contorno mar adentro - el agua costera de un pais es de su huso
    #   4. banda teorica
    #
    # El contorno tiene que ganarle a la banda. Estando ambos en el mismo
    # nivel decidia el orden de procesamiento, y donde una costa cruza un
    # limite de banda quedaba una astilla del huso vecino pegada a la
    # costa: asi aparecia UTC-7 dentro del Golfo de Mexico.
    hard, mid, near, soft = {}, {}, {}, {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        for h in all_h:
            land = land_by_zone.get(h)
            hard[h] = land
            mid[h] = unary_union(boxes[h]) if boxes.get(h) else None
            offshore = offshore_by_zone.get(h)
            near[h] = offshore
            band = _theoretical_band(h, lat)
            soft[h] = band

        pieces = {h: ([hard[h]] if hard[h] is not None else []) for h in all_h}
        taken = unary_union([g for g in hard.values() if g is not None])
        for tier in (mid, near, soft):
            for h in all_h:
                g = tier.get(h)
                if g is None or getattr(g, "is_empty", True):
                    continue
                g = g.difference(taken)
                if not g.is_empty:
                    pieces[h].append(g)
                    taken = unary_union([taken, g])

        # El cierre morfologico empuja geometria mas alla de los polos y
        # deja esquirlas a lat -90.35, donde no existe latitud.
        world = box(-180.0, lat[0], 180.0, lat[1])
        rows = [{"std_hours": h,
                 "geometry": _polygons_only(
                     unary_union(pieces[h]).intersection(world))}
                for h in all_h if pieces[h]]
    out = gpd.GeoDataFrame(
        [r for r in rows if not r["geometry"].is_empty], crs=land_zones.crs)
    out.attrs["boxed"] = gpd.GeoDataFrame(boxed, crs=land_zones.crs) if boxed \
        else gpd.GeoDataFrame({"std_hours": [], "named": [], "geometry": []},
                              crs=land_zones.crs)
    # Los recuadros, aparte: el mapa los usa para sombrear suavemente el
    # grupo de islas, al modo de los mapas de referencia.
    panels = [{"std_hours": h, "geometry": g}
              for h, v in boxes.items() for g in v]
    out.attrs["panels"] = gpd.GeoDataFrame(panels, crs=land_zones.crs) if panels \
        else gpd.GeoDataFrame({"std_hours": [], "geometry": []},
                              crs=land_zones.crs)
    return out
