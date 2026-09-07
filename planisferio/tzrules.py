"""Deriva offsets y reglas de DST directamente de tzdata via zoneinfo.

Nada hardcodeado: si cambia tzdata, cambia el mapa.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, available_timezones

PROBE_YEAR = 2026
ZERO = timedelta(0)


@dataclass(frozen=True)
class ZoneRule:
    tzid: str
    std_offset: timedelta          # offset legal sin DST
    dst_offset: timedelta | None   # offset con DST aplicado (None si no observa)
    dst_delta: timedelta           # magnitud del salto
    intervals: tuple[tuple[date, date], ...]  # tramos del anio con DST activo

    @property
    def observes_dst(self) -> bool:
        return self.dst_delta != ZERO

    @property
    def std_hours(self) -> float:
        return self.std_offset.total_seconds() / 3600

    @property
    def dst_hours(self) -> float | None:
        return None if self.dst_offset is None else self.dst_offset.total_seconds() / 3600

    @property
    def hemisphere(self) -> str | None:
        """Sur = el DST cruza el fin de anio (verano austral)."""
        if not self.observes_dst:
            return None
        return "S" if len(self.intervals) > 1 or self.intervals[0][0].month >= 9 else "N"


def _daily_dst_flags(tz: ZoneInfo, year: int) -> list[tuple[date, bool, timedelta]]:
    out, d = [], date(year, 1, 1)
    while d.year == year:
        aware = datetime(d.year, d.month, d.day, 12, tzinfo=tz)
        out.append((d, (aware.dst() or ZERO) != ZERO, aware.utcoffset()))
        d += timedelta(days=1)
    return out


def zone_rule(tzid: str, year: int = PROBE_YEAR) -> ZoneRule:
    tz = ZoneInfo(tzid)
    flags = _daily_dst_flags(tz, year)

    std_counts: dict[timedelta, int] = {}
    dst_counts: dict[timedelta, int] = {}
    for _, is_dst, off in flags:
        (dst_counts if is_dst else std_counts)[off] = \
            (dst_counts if is_dst else std_counts).get(off, 0) + 1

    if not dst_counts:
        std = max(std_counts, key=std_counts.get)
        return ZoneRule(tzid, std, None, ZERO, ())

    dst_off = max(dst_counts, key=dst_counts.get)
    std = max(std_counts, key=std_counts.get) if std_counts else dst_off

    intervals, start = [], None
    for d, is_dst, _ in flags:
        if is_dst and start is None:
            start = d
        elif not is_dst and start is not None:
            intervals.append((start, d - timedelta(days=1)))
            start = None
    if start is not None:
        intervals.append((start, date(year, 12, 31)))

    return ZoneRule(tzid, std, dst_off, dst_off - std, tuple(intervals))


def all_rules(year: int = PROBE_YEAR) -> dict[str, ZoneRule]:
    return {tz: zone_rule(tz, year) for tz in sorted(available_timezones())}
