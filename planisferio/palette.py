"""Paletas. La de desviacion es divergente y apagada, pensada para impresion."""
from __future__ import annotations

PAPER = {
    "bg":          "#f2ece0",
    "land_edge":   "#3d3730",
    "zone_edge":   "#2b2620",
    "solar_line":  "#8a8073",
    "label":       "#2b2620",
    "label_halo":  "#f2ece0",
    "hatch":       "#3d3730",
}

CIA = {
    "bg":         "#f4efe2",
    "sea":        "#c3d4d8",
    "land_edge":  "#6b6255",
    "zone_edge":  "#8c3b28",
    "solar_line": "#b3a894",
    "label":      "#2b2620",
    "label_halo": "#ffffff",
    "hatch":      "#8c3b28",
}

INK = {
    "bg":          "#141922",
    "land_edge":   "#d9d2c4",
    "zone_edge":   "#f0e9db",
    "solar_line":  "#7c8797",
    "label":       "#f0e9db",
    "label_halo":  "#141922",
    "hatch":       "#f0e9db",
}


# Modo "zones": sin escala de color, solo tonos alternados para poder
# distinguir husos vecinos. Los offsets fraccionarios (:30, :45) llevan
# su propio tono porque son la rareza que vale la pena ver.
ZONES_PAPER = {"even": "#eae3d3", "odd": "#cabc9d", "frac": "#c19a5b", "sea": "#f2ece0"}
ZONES_INK   = {"even": "#2a3340", "odd": "#38434f", "frac": "#5c6472", "sea": "#141922"}


def zone_color(hours: float, theme: str = "paper") -> str:
    t = ZONES_PAPER if theme == "paper" else ZONES_INK
    if hours != int(hours):
        return t["frac"]
    return t["even"] if int(hours) % 2 == 0 else t["odd"]


# --- Paleta derivada del mapa "Standard Time Zones of the World" (CIA, dominio
# publico), muestreada directamente de la imagen de referencia. Es un ciclo
# corto: husos vecinos se distinguen sin necesitar 24 colores distintos.
CIA_CYCLE = ["#f0d2bd", "#dadfc2", "#f2e3c5", "#e5c98c",
             "#e1a780", "#c9d08a", "#a2b7b9"]
CIA_OCEAN = "#cfdada"
CIA_BAND_A = "#f7f0e2"   # tinte de la banda teorica, columnas pares
CIA_BAND_B = "#eee6d3"   # idem, impares
CIA_ZONE_EDGE = "#8c3b28"
CIA_OFFSET_TEXT = "#8c3b28"
CIA_LAND_EDGE = "#6b6255"


def cycle_color(hours: float) -> str:
    """Color del huso. Los fraccionarios heredan el de su hora base y se
    diferencian por rayado, como en el mapa de referencia."""
    return CIA_CYCLE[int(hours) % len(CIA_CYCLE)]


def offset_label(hours: float) -> str:
    """'+5:30' -> '+5½'. Notacion compacta del mapa de referencia."""
    whole = int(hours)
    frac = round(abs(hours - whole) * 60)
    mark = {0: "", 30: "½", 45: "¾", 15: "¼"}.get(frac, f":{frac:02d}")
    if whole == 0:
        return f"0{mark}" if hours >= 0 else f"-0{mark}"
    return f"{whole:+d}{mark}"


def lighten(hex_color: str, amount: float, toward: str = "#ffffff") -> str:
    """Mezcla hacia `toward`. amount=0 deja el color, 1 lo reemplaza."""
    def rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    a, b = rgb(hex_color), rgb(toward)
    m = tuple(round(x + (y - x) * amount) for x, y in zip(a, b))
    return "#%02x%02x%02x" % m


# --- paletas reducidas -------------------------------------------------
# El ciclo de la CIA usa 7 colores. Con menos, el mapa depende mas del
# limite de huso y del numero escrito que del relleno, y se acerca a un
# grabado antiguo. Cada una es un ciclo: la longitud decide cada cuantas
# bandas se repite un tono.

PALETTES = {
    # Dos tonos calidos alternados. Lo minimo para poder contar bandas.
    "duo": ["#e8dcc4", "#cbb894"],
    # Tres pasos del mismo ocre, como un grabado.
    "sepia": ["#efe6d2", "#dfd0b0", "#c9b68e"],
    # Cuatro tonos frios y calidos alternos, sin llegar al arcoiris.
    "cuatro": ["#e9e2cf", "#cfd8c4", "#e6cfb4", "#b9c6c8"],
}


def palette_color(hours: float, name: str) -> str:
    cyc = PALETTES[name]
    return cyc[int(hours) % len(cyc)]
