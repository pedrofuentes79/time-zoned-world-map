"""Notas explicativas sobre el mapa.

Para las rarezas que el dibujo no puede contar solo: un huso cuya hora
oficial no es la que se usa, una frontera que sorprende, una excepcion que
sin explicacion se lee como un error.

    (texto, lon, lat)
El texto va en varias lineas separadas por \\n; la primera hace de titulo.
"""
from __future__ import annotations

NOTES = [
    ("XINJIANG\nUTC+6 es la hora oficial;\nen la práctica se usa\nla de Pekín (UTC+8)",
     85.5, 39.2),
]
