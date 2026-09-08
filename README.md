# time-zoned-world-map

Un planisferio de husos horarios en A0, vectorial, generado desde datos que
se pueden volver a bajar. Pensado para imprimir y colgar.

Sigue la convención de dibujo del mapa *Standard Time Zones of the World*
de la CIA (dominio público): meridiano recto en mar abierto, la banda se
dobla siguiendo la costa del país que le corresponde, y los territorios
sueltos van en un recuadro con un brazo angosto hasta su banda.

Todo en español. Las Malvinas se llaman Islas Malvinas.

## Uso

```bash
uv sync
./scripts/download.sh          # ~800 MB a data/raw/
uv run python -m planisferio.prep     # construye data/cache/ y valida
uv run python -m planisferio.poster   # SVG + PDF + PNG a 200 dpi
```

Opciones del poster: `--dpi 300` para un PNG mas grande, `--no-png` para
saltear el rasterizado. A0 a 200 dpi son 9362x6622 px y unos 7 MB; a 300 dpi
son 139 Mpx, que muchos visores no abren comodos.

Cada corrida limpia `out/` antes de escribir: tener dos generaciones de
archivos conviviendo llevo a revisar un mapa viejo creyendo que era el nuevo.

Para mirarlo entero con zoom profundo, **Chromium** sobre el SVG o el PDF
(`chromium out/planisferio_a0.svg`, ctrl+rueda para acercar): es vectorial,
asi que no tiene tope de nitidez. Inkscape sirve igual y ademas permite
retocar. Evince topea el zoom antes de que se lean los rotulos de 7 pt.
QGIS no: esto ya es un grafico terminado, no datos geograficos.

`prep.py` tarda unos minutos la primera vez por el cierre morfológico de
las costas; el resultado queda cacheado con una huella de sus entradas,
sus parámetros y su código, así que las corridas siguientes son rápidas.

## Fuentes

| Dato | Fuente | Licencia |
|---|---|---|
| Reglas horarias y DST | tzdata, vía `zoneinfo` | dominio público |
| Límites de husos | [timezone-boundary-builder](https://github.com/evansiroky/timezone-boundary-builder) 2026c | ODbL |
| Costas, países, mares | Natural Earth 10m | dominio público |
| Nombres de islas | [GeoNames](https://download.geonames.org/export/dump/) | CC BY 4.0 |

Los offsets y el horario de verano **no están escritos en el código**: se
derivan de tzdata en tiempo de ejecución. Cuando un país cambia sus reglas,
alcanza con actualizar tzdata y volver a correr.

## Cómo está organizado

```
planisferio/
  tzrules.py      offsets y reglas de DST derivados de tzdata
  prep.py         construye el cache y corre las validaciones
  generalize.py   los husos sobre el mar, al modo de los mapas murales
  dateline.py     la línea de cambio de fecha, derivada de los husos
  zone_fixes.py   correcciones de huso sobre errores de la fuente
  label_data.py   tabla única de rótulos: países e islas
  labels.py       colocación con detección de colisiones
  palette.py      paletas, muestreadas del mapa de la CIA
  render.py       el render, todo parametrizado
  checks.py       invariantes del cache
```

### Casos especiales: tablas, no reglas

Los territorios raros están **enumerados con nombre**, no derivados de
umbrales. Se intentó al revés y no funcionó: cada regla nueva (por tamaño,
por distancia a la banda, por cercanía a tierra propia) arreglaba un caso y
rompía otro. La regla de cercanía, agregada para las islas al sur de Tierra
del Fuego, dejó a Islandia sin brazo porque tiene islotes al lado.

Filtrando automáticamente por "difiere de su banda" salían 762 candidatos;
por "difiere del huso de su país", 725; agregando aislamiento, 306. En los
tres casos el grueso eran pedazos de Rusia, Canadá e Indonesia.

Hay dos tablas, y la distinción importa:

- `TERRITORIES` en `generalize.py` decide **cómo se dibuja** algo cuyo dato
  ya es correcto (Islandia, Jan Mayen, Azores, Crozet…).
- `FIXES` en `zone_fixes.py` corrige **el dato** cuando la fuente está mal.
  Hoy tiene Trindade y Martim Vaz, que OSM ubica en `America/Sao_Paulo`
  cuando la ley brasileña las pone en el huso de Fernando de Noronha.

### Rotulos: desde la geometria, no desde el gazetteer

GeoNames tiene 175.000 islas. De esas, 78.000 caen dentro de masas
continentales (islas de rio, islotes costeros) y la mayoria del resto no se
ve a esta escala. El mapa aguanta unas 2.000 etiquetas: a 5 pt, con las
etiquetas cubriendo el 12% del papel, entran unas 4.000, y eso ya es denso.

Asi que se recorre al reves: cada poligono de isla de entre 0.01 y 5 grados
cuadrados recibe **una** etiqueta, con el mejor nombre que GeoNames tenga
adentro. Menos de 0.01 mide menos de 1 mm a A0.

La soberania se muestra solo en las dependencias, donde ADMIN y SOVEREIGNT
difieren en Natural Earth. Ponerla siempre llenaba el archipielago indonesio
de "(INDONESIA)" sin agregar nada.

### Invariantes

`prep.py` termina validando el cache. Cada bug que apareció durante el
desarrollo dejó ahí su chequeo:

```
[OK] sin franjas desbocadas          [OK] territorios nombrados resueltos
[OK] el mar queda cubierto           [OK] correcciones de huso aplicadas
[OK] los husos no se pisan           [OK] regla alineada con el mapa
[OK] la tierra cae en su huso        [OK] todo offset tiene columna
[OK] husos fraccionarios acotados
```

## Licencia

El código todavía no tiene licencia definida. Los datos conservan las suyas,
listadas arriba; en particular timezone-boundary-builder es ODbL, que pide
atribución si redistribuís el mapa.
