from __future__ import annotations

import csv
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import DailyAggregate, Evse, StatusInterval
from .statuses import StatusClass, classify_status

Period = Literal["daily", "weekly", "monthly", "quarterly", "semiannual", "annual"]
GroupBy = Literal["network", "operator", "city", "site", "evse"]


@dataclass(frozen=True)
class PeriodWindow:
    label_start: date
    start_utc: datetime
    end_utc: datetime


@dataclass
class Counters:
    up: float = 0.0
    down: float = 0.0
    unknown: float = 0.0
    excluded: float = 0.0

    def add(self, status_class: StatusClass, seconds: float) -> None:
        if status_class == StatusClass.UP:
            self.up += seconds
        elif status_class == StatusClass.DOWN:
            self.down += seconds
        elif status_class == StatusClass.EXCLUDED:
            self.excluded += seconds
        else:
            self.unknown += seconds

    def as_dict(self) -> dict[str, float | None]:
        eligible = self.up + self.down + self.unknown
        observed = self.up + self.down
        return {
            "up_seconds": round(self.up, 3),
            "down_seconds": round(self.down, 3),
            "unknown_seconds": round(self.unknown, 3),
            "excluded_seconds": round(self.excluded, 3),
            "eligible_seconds": round(eligible, 3),
            "uptime_percent": round(100 * self.up / eligible, 5) if eligible else None,
            "observed_uptime_percent": round(100 * self.up / observed, 5) if observed else None,
            "coverage_percent": round(100 * observed / eligible, 5) if eligible else None,
        }


def _month_add(d: date, months: int) -> date:
    month_index = d.year * 12 + (d.month - 1) + months
    return date(month_index // 12, month_index % 12 + 1, 1)


def _canonical_start(d: date, period: Period) -> date:
    if period == "daily":
        return d
    if period == "weekly":
        return d - timedelta(days=d.weekday())
    if period == "monthly":
        return date(d.year, d.month, 1)
    if period == "quarterly":
        month = 1 + 3 * ((d.month - 1) // 3)
        return date(d.year, month, 1)
    if period == "semiannual":
        return date(d.year, 1 if d.month <= 6 else 7, 1)
    return date(d.year, 1, 1)


def _next_start(d: date, period: Period) -> date:
    if period == "daily":
        return d + timedelta(days=1)
    if period == "weekly":
        return d + timedelta(days=7)
    if period == "monthly":
        return _month_add(d, 1)
    if period == "quarterly":
        return _month_add(d, 3)
    if period == "semiannual":
        return _month_add(d, 6)
    return date(d.year + 1, 1, 1)


def build_windows(start: date, end_inclusive: date, period: Period, timezone_name: str) -> list[PeriodWindow]:
    tz = ZoneInfo(timezone_name)
    query_start_local = datetime.combine(start, time.min, tzinfo=tz)
    query_end_local = datetime.combine(end_inclusive + timedelta(days=1), time.min, tzinfo=tz)

    cursor = _canonical_start(start, period)
    windows: list[PeriodWindow] = []
    while cursor <= end_inclusive:
        next_cursor = _next_start(cursor, period)
        raw_start = datetime.combine(cursor, time.min, tzinfo=tz)
        raw_end = datetime.combine(next_cursor, time.min, tzinfo=tz)
        clipped_start = max(raw_start, query_start_local)
        clipped_end = min(raw_end, query_end_local)
        if clipped_end > clipped_start:
            windows.append(
                PeriodWindow(
                    label_start=cursor,
                    start_utc=clipped_start.astimezone(timezone.utc),
                    end_utc=clipped_end.astimezone(timezone.utc),
                )
            )
        cursor = next_cursor
    return windows


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _group_key(evse: Evse, group_by: GroupBy) -> str:
    if group_by == "network":
        return "PORTUGAL"
    if group_by == "operator":
        return evse.operator_name or evse.operator_id or "UNKNOWN"
    if group_by == "city":
        return evse.city or "UNKNOWN"
    if group_by == "site":
        return evse.site_name or evse.site_id or "UNKNOWN"
    return evse.uid


def calculate_uptime(
    session: Session,
    start: date,
    end_inclusive: date,
    period: Period,
    timezone_name: str = "Europe/Lisbon",
    group_by: GroupBy = "network",
    operator: str | None = None,
    city: str | None = None,
    evse_uid: str | None = None,
) -> list[dict[str, object]]:
    windows = build_windows(start, end_inclusive, period, timezone_name)
    if not windows:
        return []

    overall_start = windows[0].start_utc
    overall_end = windows[-1].end_utc

    stmt = (
        select(StatusInterval, Evse)
        .join(Evse, Evse.id == StatusInterval.evse_id)
        .where(
            StatusInterval.valid_from < overall_end,
            (StatusInterval.valid_to.is_(None)) | (StatusInterval.valid_to > overall_start),
        )
        .order_by(StatusInterval.valid_from)
    )
    if operator:
        stmt = stmt.where((Evse.operator_id == operator) | (Evse.operator_name == operator))
    if city:
        stmt = stmt.where(Evse.city == city)
    if evse_uid:
        stmt = stmt.where(Evse.uid == evse_uid)

    starts = [window.start_utc for window in windows]
    aggregates: dict[tuple[int, str], Counters] = defaultdict(Counters)

    for interval, evse in session.execute(stmt).all():
        interval_start = max(_as_utc(interval.valid_from), overall_start)
        interval_end = min(_as_utc(interval.valid_to) if interval.valid_to else datetime.now(timezone.utc), overall_end)
        if interval_end <= interval_start:
            continue

        index = max(0, bisect_right(starts, interval_start) - 1)
        status_class = classify_status(interval.status)
        group = _group_key(evse, group_by)

        while index < len(windows):
            window = windows[index]
            if window.start_utc >= interval_end:
                break
            overlap_start = max(interval_start, window.start_utc)
            overlap_end = min(interval_end, window.end_utc)
            if overlap_end > overlap_start:
                aggregates[(index, group)].add(status_class, (overlap_end - overlap_start).total_seconds())
            index += 1

    rows: list[dict[str, object]] = []
    for (index, group), counters in sorted(aggregates.items(), key=lambda item: (item[0][0], item[0][1])):
        window = windows[index]
        row: dict[str, object] = {
            "period": period,
            "period_start": window.label_start.isoformat(),
            "window_start_utc": window.start_utc.isoformat(),
            "window_end_utc": window.end_utc.isoformat(),
            "group": group,
        }
        row.update(counters.as_dict())
        rows.append(row)
    return rows


def write_csv(rows: Iterable[dict[str, object]], output: Path) -> None:
    rows = list(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output.write_text("", encoding="utf-8")
        return
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


PERSISTED_GROUPS: set[str] = {"network", "operator", "city"}


def materialize_daily_aggregates(
    session: Session,
    local_day: date,
    timezone_name: str = "Europe/Lisbon",
    group_types: tuple[GroupBy, ...] = ("network", "operator", "city"),
) -> int:
    """Grava resumos diários compactos para retenção de longo prazo."""
    now = datetime.now(timezone.utc)
    written = 0
    for group_type in group_types:
        session.execute(
            delete(DailyAggregate).where(
                DailyAggregate.local_day == local_day,
                DailyAggregate.group_type == group_type,
            )
        )
        rows = calculate_uptime(
            session,
            start=local_day,
            end_inclusive=local_day,
            period="daily",
            timezone_name=timezone_name,
            group_by=group_type,
        )
        for row in rows:
            session.add(
                DailyAggregate(
                    local_day=local_day,
                    group_type=group_type,
                    group_key=str(row["group"]),
                    up_seconds=float(row["up_seconds"]),
                    down_seconds=float(row["down_seconds"]),
                    unknown_seconds=float(row["unknown_seconds"]),
                    excluded_seconds=float(row["excluded_seconds"]),
                    calculated_at=now,
                )
            )
            written += 1
    return written


def prune_detailed_intervals(
    session: Session,
    cutoff_local_day: date,
    timezone_name: str = "Europe/Lisbon",
) -> int:
    """Apaga apenas intervalos fechados anteriores ao dia de corte.

    Os resumos diários devem ser criados antes desta operação. Intervalos abertos
    são preservados, mesmo que tenham começado antes do corte.
    """
    tz = ZoneInfo(timezone_name)
    cutoff_utc = datetime.combine(cutoff_local_day, time.min, tzinfo=tz).astimezone(timezone.utc)
    result = session.execute(
        delete(StatusInterval).where(
            StatusInterval.valid_to.is_not(None),
            StatusInterval.valid_to <= cutoff_utc,
        )
    )
    return int(result.rowcount or 0)


def calculate_uptime_compact(
    session: Session,
    start: date,
    end_inclusive: date,
    period: Period,
    timezone_name: str = "Europe/Lisbon",
    group_by: GroupBy = "network",
    operator: str | None = None,
    city: str | None = None,
    evse_uid: str | None = None,
) -> list[dict[str, object]]:
    """Usa resumos diários quando existem e intervalos para os restantes dias.

    A retenção compacta suporta historicamente network, operator e city sem
    filtros adicionais. Site/EVSE e filtros detalhados dependem dos intervalos
    ainda retidos.
    """
    windows = build_windows(start, end_inclusive, period, timezone_name)
    if not windows:
        return []

    index_by_label = {window.label_start: index for index, window in enumerate(windows)}
    aggregates: dict[tuple[int, str], Counters] = defaultdict(Counters)
    persisted_days: set[date] = set()

    can_use_persisted = (
        group_by in PERSISTED_GROUPS
        and operator is None
        and city is None
        and evse_uid is None
    )

    if can_use_persisted:
        stmt = (
            select(DailyAggregate)
            .where(
                DailyAggregate.group_type == group_by,
                DailyAggregate.local_day >= start,
                DailyAggregate.local_day <= end_inclusive,
            )
            .order_by(DailyAggregate.local_day, DailyAggregate.group_key)
        )
        for row in session.scalars(stmt).all():
            persisted_days.add(row.local_day)
            label = _canonical_start(row.local_day, period)
            index = index_by_label.get(label)
            if index is None:
                continue
            counters = aggregates[(index, row.group_key)]
            counters.up += row.up_seconds
            counters.down += row.down_seconds
            counters.unknown += row.unknown_seconds
            counters.excluded += row.excluded_seconds

    cursor = start
    while cursor <= end_inclusive:
        if cursor not in persisted_days:
            day_rows = calculate_uptime(
                session,
                start=cursor,
                end_inclusive=cursor,
                period="daily",
                timezone_name=timezone_name,
                group_by=group_by,
                operator=operator,
                city=city,
                evse_uid=evse_uid,
            )
            label = _canonical_start(cursor, period)
            index = index_by_label.get(label)
            if index is not None:
                for row in day_rows:
                    counters = aggregates[(index, str(row["group"]))]
                    counters.up += float(row["up_seconds"])
                    counters.down += float(row["down_seconds"])
                    counters.unknown += float(row["unknown_seconds"])
                    counters.excluded += float(row["excluded_seconds"])
        cursor += timedelta(days=1)

    rows: list[dict[str, object]] = []
    for (index, group), counters in sorted(aggregates.items(), key=lambda item: (item[0][0], item[0][1])):
        window = windows[index]
        row: dict[str, object] = {
            "period": period,
            "period_start": window.label_start.isoformat(),
            "window_start_utc": window.start_utc.isoformat(),
            "window_end_utc": window.end_utc.isoformat(),
            "group": group,
        }
        row.update(counters.as_dict())
        rows.append(row)
    return rows
