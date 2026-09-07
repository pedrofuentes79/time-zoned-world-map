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
  state that administers each one. (It restored the zone that Lei 11.662/2008
  had removed.)
- `zone1970.tab` describes `America/Noronha` as "Atlantic islands", plural.
- In OSM, relation
  [14906453](https://www.openstreetmap.org/relation/14906453)
  (`UTC−02:00 standard time`, `boundary=timezone`) already covers Trindade —
  someone has already mapped these islands as UTC-2. It has no `timezone=*`
  tag, so this project never sees it.

The islands are uninhabited except for a Brazilian Navy station on Trindade,
so practical impact is small — but the boundary is wrong.

### Root cause

This isn't a bug in the builder. `downloadFromOverpass` queries
`relation["timezone"="<tzid>"]` (index.js:471-486) and unions the results,
which is the right thing to do — the false statement is in OSM.

`America/Sao_Paulo` resolves to 10 relations: nine whole states tagged
directly (ES, RJ, RS, SC, PR, SP, MG, GO, DF) plus the dedicated
[19510840](https://www.openstreetmap.org/relation/19510840)
(`America/Sao_Paulo timezone`, `boundary=timezone`).

Relation [54882](https://www.openstreetmap.org/relation/54882) (Espírito
Santo, `admin_level=4`) is one of those nine, and among its members are the
islands' 12 nm territorial-sea rings:

- way [770537922](https://www.openstreetmap.org/way/770537922) — Trindade
  (centre -20.5057, -29.3202; r ≈ 0.222° ≈ 13.3 nm; closed, 167 nodes)
- way [770537923](https://www.openstreetmap.org/way/770537923) — Martim Vaz
  (centre -20.4821, -28.8464; r ≈ 0.210° ≈ 12.6 nm; closed, 159 nodes)

So ES's `timezone=America/Sao_Paulo` tag asserts that *all* of Espírito Santo
is UTC-3, which is false — the state administers two island groups that are
legally UTC-2.

### Why Fernando de Noronha works and this doesn't

Brazilian OSM data uses two different conventions:

- **Pernambuco:** relation `303702` carries **no** `timezone` tag. Its
  mainland is covered by the dedicated `America/Recife` relation
  ([15093974](https://www.openstreetmap.org/relation/15093974) — the *only*
  relation tagged `timezone=America/Recife`), and Fernando de Noronha by
  `America/Noronha`. The state splits cleanly, and the output is correct.
- **Espírito Santo / Rio Grande do Norte:** the state relation itself carries
  the `timezone` tag, so it's all-or-nothing and no exception can be carved
  out.

ES and RN are precisely the two states that Brazilian law splits, and both use
the pattern that can't express a split.

### Proposed fix (OSM only — nothing needed in this repo)

1. Remove `timezone=America/Sao_Paulo` from relation `54882` (Espírito Santo).
2. Add ways `770537922` and `770537923` as `outer` members of relation
   [15093973](https://www.openstreetmap.org/relation/15093973)
   (`America/Noronha`).

This is the Pernambuco pattern, applied to ES. Mainland Espírito Santo stays
in `America/Sao_Paulo` via `19510840`, which already covers it — I checked
`is_in(lat,lon)->.a; rel(pivot.a)["timezone"]` at three points spread across
the state (-18.55/-40.40, -21.10/-41.05, -19.40/-40.07) and `19510840`
covers all three, while Trindade (-20.5076/-29.3217) is covered only by
`54882`. So removing the tag doesn't open a hole.

Result: islands → Noronha, mainland ES → Sao_Paulo, no overlap, no
`difference` op, no config change here.

### Related: Atol das Rocas

Changeset [176723059](https://www.openstreetmap.org/changeset/176723059)
removed way `1135490007` (the territorial ring around Atol das Rocas) from the
`America/Noronha` relation, on the grounds that Rocas is administratively part
of Rio Grande do Norte.

That's the same situation: RN (relation `301079`) carries
`timezone=America/Fortaleza`, so adding Rocas to `America/Noronha` while RN
stays tagged would create an overlap. The same two-step fix would apply —
though `America/Fortaleza` currently pulls in five tagged states (RN, PB, CE,
PI, MA) plus relation `19507366`, so whether the dedicated relation covers
mainland RN would need checking first.

Happy to make these OSM edits, but given the revert above I'd rather agree on
the approach first.
