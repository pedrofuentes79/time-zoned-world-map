"""Colocacion de rotulos con deteccion de colisiones.

Paises, islas y numeros de huso pasan todos por aca, porque compiten por
el mismo espacio. Cuando cada capa se dibujaba por su cuenta, los nombres
de islas caian sobre los de paises y el "+5 1/2" sobre "INDIA".

Orden: primero se reservan los numeros de huso, que son el dato del mapa;
despues los paises por superficie; al final las islas por SCALERANK.
"""
from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import matplotlib.patheffects as pe

# Candidatos de desplazamiento, en multiplos de la altura de linea.
OFFSETS = [
    (0.0, 0.0),
    (0.0, 1.2), (0.0, -1.2),
    (1.0, 0.0), (-1.0, 0.0),
    (0.9, 0.9), (-0.9, 0.9), (0.9, -0.9), (-0.9, -0.9),
    (0.0, 2.4), (0.0, -2.4),
    (2.0, 0.0), (-2.0, 0.0),
    (1.8, 1.8), (-1.8, 1.8), (1.8, -1.8), (-1.8, -1.8),
    (0.0, 3.8), (0.0, -3.8), (3.2, 0.0), (-3.2, 0.0),
]

# Cuerpo relativo de los paises, por escalon de superficie.
COUNTRY_STEPS = (0.62, 0.78, 0.92, 1.06, 1.24)
# Cuerpo relativo de las islas, por SCALERANK de Natural Earth (0 = Melanesia,
# 7 = islote). Siempre por debajo de un pais: son informacion de detalle.
# Ciudades, por SCALERANK de Natural Earth (0 = Tokio, Nueva York).
CITY_BY_RANK = {0: 0.80, 1: 0.72, 2: 0.66, 3: 0.60, 4: 0.55}
CITY_DOT_PT = {0: 2.2, 1: 1.9, 2: 1.7, 3: 1.5, 4: 1.3}

# El rank 8 es la capa de detalle: islas menores, en cuerpo minusculo.
# A A0 son ~0.9 mm de altura: invisibles de lejos, legibles de cerca.
ISLAND_BY_RANK = {0: 0.72, 1: 0.72, 2: 0.62, 3: 0.62,
                  4: 0.54, 5: 0.54, 6: 0.48, 7: 0.44, 8: 0.26}
# La capa de detalle ademas retrocede en tono: achicar sola no alcanza,
# apinadas formaban una masa gris que se leia como ruido.
DETAIL_RANK = 8
DETAIL_ALPHA = 0.45


@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    def hits(self, other: "Box", pad: float = 0.0) -> bool:
        return not (self.x1 + pad < other.x0 or other.x1 + pad < self.x0
                    or self.y1 + pad < other.y0 or other.y1 + pad < self.y0)


def text_box(cx: float, cy: float, text: str, size_u: float) -> Box:
    w = len(text) * size_u * 0.60
    return Box(cx - w / 2, cy - size_u / 2, cx + w / 2, cy + size_u / 2)


def _country_factor(area: float, quantiles: list[float]) -> float:
    for i, q in enumerate(quantiles):
        if area <= q:
            return COUNTRY_STEPS[i]
    return COUNTRY_STEPS[-1]


def place(ax, labels: gpd.GeoDataFrame, crs, s, th,
          overrides: dict[str, str], reserved: list[Box] | None = None) -> dict:
    from .render import effective_limits
    lo, hi = effective_limits(s)
    c = labels[labels["lat"].between(lo + 1, hi - 1)].copy()
    if s.label_min_pop > 0 and "priority" in c:
        c = c[(c["kind"] == "country") | (c["priority"] > 0)]
    c = c.sort_values("priority", ascending=False)

    proj = c.to_crs(crs)
    xlim = ax.get_xlim()
    span_x = abs(xlim[1] - xlim[0]) or 1.0
    fig_w_in = ax.get_figure().get_size_inches()[0] * ax.get_position().width
    unit = span_x / (fig_w_in * 72.0)      # un punto tipografico en datos
    deg = span_x / 360.0                   # un grado de longitud en datos

    countries = c[c["kind"] == "country"]
    quantiles = ([0.0] * 4 if countries.empty else
                 countries["priority"].quantile([0.35, 0.60, 0.80, 0.93]).tolist())

    placed: list[Box] = list(reserved or [])
    stats = {"total": len(c), "placed": 0, "moved": 0, "dropped": 0}
    halo = [pe.withStroke(linewidth=1.5, foreground=th["label_halo"])]

    for (_, row), pt in zip(c.iterrows(), proj.geometry):
        kind = row["kind"]
        island = kind == "island"
        city = kind == "city"
        if city:
            size_pt = s.label_size_pt * CITY_BY_RANK.get(int(row["rank"]), 0.55)
            name = str(row["name"])
        elif island:
            size_pt = s.label_size_pt * ISLAND_BY_RANK.get(int(row["rank"]), 0.44)
            name = str(row["name"])
        else:
            size_pt = s.label_size_pt * _country_factor(row["priority"], quantiles)
            name = overrides.get(row["name"], row["name"]).upper()
        size_u = size_pt * unit
        sov = row["sovereign"] if isinstance(row["sovereign"], str) else None

        # Una isla chica se tapa a si misma si el nombre va centrado
        # encima: para esas se arranca a un costado. Una ciudad nunca lleva
        # el nombre sobre su propio punto.
        centred_ok = not (city or (island and int(row["rank"]) >= 4))
        candidates = OFFSETS if centred_ok else OFFSETS[1:]
        # El paso se mide contra el tamano de la isla, no solo contra el
        # cuerpo del texto: a 2 pt, correr "linea y media" son decimas de
        # milimetro y el nombre seguia cayendo encima.
        radius = 0.0
        own: Box | None = None
        if island:
            area = max(float(row["priority"]), 0.0)
            radius = (area / 3.14159) ** 0.5 * deg
            # Las islas mayores llevan el nombre encima a proposito; las
            # chicas no deben quedar tapadas por su propio rotulo.
            if int(row["rank"]) >= 4:
                own = Box(pt.x - radius, pt.y - radius,
                          pt.x + radius, pt.y + radius)
        half_w = len(name) * size_u * 0.30
        step_x = max(size_u * 3.2, radius + half_w + size_u * 0.6)
        step_y = max(size_u * 1.5, radius + size_u * 1.1)

        spot = None
        for i, (dx, dy) in enumerate(candidates):
            cx = pt.x + dx * step_x
            cy = pt.y + dy * step_y
            b = text_box(cx, cy, name, size_u)
            boxes = [b]
            if sov:
                boxes.append(text_box(cx, cy - size_u * 1.15,
                                      f"({sov})", size_u * 0.78))
            # No taparse a si misma, y no pisar lo ya colocado.
            if own is not None and any(bb.hits(own) for bb in boxes):
                continue
            if not any(bb.hits(p, pad=size_u * 0.16) for bb in boxes for p in placed):
                spot = (cx, cy, boxes, i)
                break
        if spot is None:
            stats["dropped"] += 1
            continue

        cx, cy, boxes, idx = spot
        placed.extend(boxes)
        stats["moved" if idx else "placed"] += 1
        # La capa de detalle no lleva guia: a ese cuerpo la linea pesa mas
        # que el nombre.
        if idx and not (island and int(row["rank"]) >= 8):
            ax.plot([pt.x, cx], [pt.y, cy], color=th["label"], linewidth=0.4,
                    alpha=0.7, zorder=7)
            ax.plot([pt.x], [pt.y], marker="o", markersize=0.9,
                    color=th["label"], alpha=0.8, zorder=7)
        if city:
            ax.plot([pt.x], [pt.y], marker="o",
                    markersize=CITY_DOT_PT.get(int(row["rank"]), 1.3),
                    color=th["label"], zorder=8.2,
                    markeredgecolor=th["label_halo"], markeredgewidth=0.3)
        detail = island and int(row["rank"]) >= DETAIL_RANK
        ax.text(cx, cy, name, fontsize=size_pt, ha="center", va="center",
                color=th["label"], zorder=8, path_effects=halo,
                alpha=DETAIL_ALPHA if detail else 1.0)
        if sov:
            ax.text(cx, cy - size_u * 1.15, f"({sov})", fontsize=size_pt * 0.78,
                    ha="center", va="center", color=th["label"], alpha=0.8,
                    zorder=8, path_effects=halo)
    return stats
