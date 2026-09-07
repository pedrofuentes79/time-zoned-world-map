# Borrador de issue

Repo: https://github.com/evansiroky/timezone-boundary-builder/issues

**Title:** Trindade and Martim Vaz resolve to America/Sao_Paulo instead of America/Noronha

---

**Body:**

The Brazilian oceanic islands of Trindade and Martim Vaz fall inside the
`America/Sao_Paulo` polygon (UTC-3). Per Brazilian law they belong in
`America/Noronha` (UTC-2).

| Island     | Lat      | Lon      | Current           | Expected        |
|------------|----------|----------|-------------------|-----------------|
| Trindade   | -20.57   | -29.33   | America/Sao_Paulo | America/Noronha |
| Martim Vaz | -20.52   | -28.88   | America/Sao_Paulo | America/Noronha |

```python
import geopandas as gpd
from shapely.geometry import Point
tz = gpd.read_file("combined-now.json")
pt = Point(-29.33, -20.57)          # Ilha da Trindade
print([r.tzid for _, r in tz.iterrows() if r.geometry.intersects(pt.buffer(0.05))])
# -> ['America/Sao_Paulo']
```

### Why UTC-2 is correct

- Lei 12.876/2013 places Fernando de Noronha, Atol das Rocas, and the
  Trindade e Martim Vaz archipelago in the UTC-2 zone, independently of the
  state that administers each one. (It restored the zone that Lei
  11.662/2008 had removed.)
- `zone1970.tab` describes `America/Noronha` as "Atlantic islands", plural.
- The islands are uninhabited except for a Brazilian Navy station on
  Trindade, so practical impact is small — but the boundary is wrong.

### Root cause

`downloadFromOverpass` builds the query as `relation["timezone"="<tzid>"]`
(index.js:471-486), without restricting to `boundary=timezone`. So any
relation carrying a `timezone` tag contributes to that zone.

Relation [54882](https://www.openstreetmap.org/relation/54882) (Espírito
Santo, `admin_level=4`, `boundary=administrative`) carries
`timezone=America/Sao_Paulo`, and among its members are the islands'
12 nm territorial-sea rings:

- way [770537922](https://www.openstreetmap.org/way/770537922) — Trindade
  (centre -20.5057, -29.3202; r ≈ 0.222° ≈ 13.3 nm; closed, 167 nodes)
- way [770537923](https://www.openstreetmap.org/way/770537923) — Martim Vaz
  (centre -20.4821, -28.8464; r ≈ 0.210° ≈ 12.6 nm; closed, 159 nodes)

Both are tagged `admin_level=2 border_type=territorial
boundary=administrative maritime=yes` — the same shape and tagging as the two
existing members of the `America/Noronha` relation
([15093973](https://www.openstreetmap.org/relation/15093973)): way
`1135490008` (Fernando de Noronha) and way `1135410780` (São Pedro e São
Paulo).

So the islands land in UTC-3 because Espírito Santo's relation is tagged for
that zone and its geometry includes them.

### Proposed fix (two halves — neither works alone)

1. **OSM:** add ways `770537922` and `770537923` as `outer` members of
   relation `15093973`.
2. **This repo:** in `timezones.json`, have `America/Sao_Paulo` subtract
   `America/Noronha` after its `init`, following the same pattern
   `America/Phoenix` already uses to subtract `America/Creston`:

   ```json
   "America/Sao_Paulo": [
     { "op": "init", "source": "overpass", "id": "America-Sao_Paulo-tz" },
     { "op": "difference", "source": "overpass", "id": "America-Noronha-tz" }
   ]
   ```

   This is also the same situation `America/Toronto` handles with a
   `manual-polygon` difference described as "Remove Bahamas included in raw
   OpenStreetMap relation" — a raw OSM relation that over-includes territory.
   A `manual-polygon` box around the archipelago would work too, but
   subtracting `America-Noronha-tz` stays correct on its own as the relation
   evolves.

Doing only (1) makes both Overpass queries return geometry covering the
islands, producing an `America/Noronha` ↔ `America/Sao_Paulo` overlap that
has no entry in `expectedZoneOverlaps.json`. Doing only (2) changes nothing,
since `America/Noronha` doesn't cover the islands yet.

I'm happy to make the OSM edit, but wanted to agree on the approach first
rather than push a change that breaks the build.

### Related: Atol das Rocas

Changeset [176723059](https://www.openstreetmap.org/changeset/176723059)
removed way `1135490007` (the territorial ring around Atol das Rocas) from
the same relation, with the rationale that Rocas is administratively part of
Rio Grande do Norte. That's the same class of problem: Rocas is legally UTC-2
under the same law, but its ring sits inside the Rio Grande do Norte relation,
so adding it to `America/Noronha` would produce the same kind of overlap
unless the corresponding zone also subtracts `America/Noronha`.

If the `difference` approach above is acceptable, it would fix both cases.
Happy to scope this to just Trindade/Martim Vaz if you'd rather keep them
separate.
