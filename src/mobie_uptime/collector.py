from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import init_db, session_scope
from .http import DownloadResult, download_xml
from .models import CurrentState, Evse, FetchRun, StatusInterval
from .parsers.datex import DynamicStatusRecord, StaticEvseRecord, parse_dynamic, parse_static
from .raw_store import save_payload
from .statuses import normalize_status

logger = logging.getLogger(__name__)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _fetch_run_start(session: Session, source_type: str, requested_at: datetime) -> FetchRun:
    run = FetchRun(source_type=source_type, requested_at=requested_at, success=False)
    session.add(run)
    session.flush()
    return run


def _complete_run(
    run: FetchRun,
    result: DownloadResult,
    item_count: int,
    raw_path: str | None,
) -> None:
    run.completed_at = result.completed_at
    run.http_status = result.status_code
    run.success = True
    run.payload_sha256 = result.sha256
    run.item_count = item_count
    run.raw_path = raw_path


def _failed_run(session: Session, source_type: str, requested_at: datetime, exc: Exception) -> None:
    run = FetchRun(
        source_type=source_type,
        requested_at=requested_at,
        completed_at=datetime.now(timezone.utc),
        success=False,
        error_message=f"{type(exc).__name__}: {exc}",
    )
    session.add(run)


def _upsert_static(session: Session, records: list[StaticEvseRecord], observed_at: datetime) -> None:
    existing = {row.uid: row for row in session.scalars(select(Evse)).all()}
    for record in records:
        row = existing.get(record.uid)
        if row is None:
            row = Evse(
                uid=record.uid,
                first_seen_at=observed_at,
                last_seen_at=observed_at,
            )
            session.add(row)
            existing[record.uid] = row
        row.evse_id = record.evse_id
        row.site_id = record.site_id
        row.station_id = record.station_id
        row.operator_id = record.operator_id
        row.operator_name = record.operator_name
        row.site_name = record.site_name
        row.city = record.city
        row.postcode = record.postcode
        row.address = record.address
        row.latitude = record.latitude
        row.longitude = record.longitude
        row.max_power_kw = record.max_power_kw
        row.connector_count = record.connector_count
        row.is_24_7 = record.is_24_7
        row.active = True
        row.last_seen_at = observed_at
        row.raw_static_json = record.as_json()


def _ensure_evse(
    session: Session,
    evse_by_uid: dict[str, Evse],
    uid: str,
    observed_at: datetime,
    record: DynamicStatusRecord,
) -> Evse:
    row = evse_by_uid.get(uid)
    if row is None:
        row = Evse(
            uid=uid,
            site_id=record.site_id,
            station_id=record.station_id,
            active=True,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
        )
        session.add(row)
        evse_by_uid[uid] = row
    else:
        row.last_seen_at = observed_at
        row.active = True
        if not row.site_id and record.site_id:
            row.site_id = record.site_id
        if not row.station_id and record.station_id:
            row.station_id = record.station_id
    return row


def _transition(
    session: Session,
    evse: Evse,
    new_status: str,
    effective_at: datetime,
    observed_at: datetime,
    source_timestamp: datetime | None,
    fetch_run_id: int | None,
) -> None:
    new_status = normalize_status(new_status)
    current = session.get(CurrentState, evse.id)

    if current is None:
        interval = StatusInterval(
            evse_id=evse.id,
            status=new_status,
            valid_from=effective_at,
            valid_to=None,
            first_observed_at=observed_at,
            last_observed_at=observed_at,
            source_timestamp=source_timestamp,
            fetch_run_id=fetch_run_id,
        )
        session.add(interval)
        session.flush()
        session.add(
            CurrentState(
                evse_id=evse.id,
                status=new_status,
                status_since=effective_at,
                observed_at=observed_at,
                source_timestamp=source_timestamp,
                missing_streak=0,
                interval_id=interval.id,
            )
        )
        return

    current.observed_at = observed_at
    current.source_timestamp = source_timestamp
    current.missing_streak = 0
    open_interval = session.get(StatusInterval, current.interval_id)

    if current.status == new_status:
        if open_interval is not None:
            open_interval.last_observed_at = observed_at
            open_interval.fetch_run_id = fetch_run_id
        return

    transition_at = max(_as_utc(effective_at), _as_utc(current.status_since))
    if open_interval is not None:
        open_interval.valid_to = transition_at
        open_interval.last_observed_at = observed_at

    interval = StatusInterval(
        evse_id=evse.id,
        status=new_status,
        valid_from=transition_at,
        valid_to=None,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        source_timestamp=source_timestamp,
        fetch_run_id=fetch_run_id,
    )
    session.add(interval)
    session.flush()
    current.status = new_status
    current.status_since = transition_at
    current.interval_id = interval.id


def _mark_feed_gap_unknown(
    session: Session,
    gap_start: datetime,
    observed_at: datetime,
    fetch_run_id: int | None,
) -> None:
    current_rows = session.scalars(select(CurrentState)).all()
    for current in current_rows:
        if current.status == "UNKNOWN" or _as_utc(current.status_since) >= gap_start:
            continue
        evse = session.get(Evse, current.evse_id)
        if evse is not None:
            _transition(
                session,
                evse,
                "UNKNOWN",
                gap_start,
                observed_at,
                None,
                fetch_run_id,
            )


def _previous_dynamic_success(session: Session) -> FetchRun | None:
    return session.scalar(
        select(FetchRun)
        .where(FetchRun.source_type == "dynamic", FetchRun.success.is_(True))
        .order_by(FetchRun.completed_at.desc())
        .limit(1)
    )


def _apply_dynamic(
    session: Session,
    records: list[DynamicStatusRecord],
    observed_at: datetime,
    run: FetchRun,
    settings: Settings,
) -> None:
    # Carrega o estado de trabalho em poucas consultas. Isto evita dezenas de
    # milhares de SELECT por minuto num feed nacional.
    evse_by_uid = {row.uid: row for row in session.scalars(select(Evse)).all()}
    session.scalars(select(CurrentState)).all()
    session.scalars(select(StatusInterval).where(StatusInterval.valid_to.is_(None))).all()

    previous_success = _previous_dynamic_success(session)
    if previous_success and previous_success.completed_at:
        gap_start = _as_utc(previous_success.completed_at) + timedelta(seconds=settings.feed_stale_after_seconds)
        if observed_at > gap_start:
            _mark_feed_gap_unknown(session, gap_start, observed_at, run.id)

    # Cria primeiro as EVSE ainda desconhecidas e faz um único flush para obter IDs.
    for record in records:
        _ensure_evse(session, evse_by_uid, record.uid, observed_at, record)
    session.flush()

    seen_uids: set[str] = set()
    for record in records:
        seen_uids.add(record.uid)
        evse = evse_by_uid[record.uid]
        effective_at = record.source_timestamp or observed_at
        _transition(
            session,
            evse,
            record.status,
            effective_at,
            observed_at,
            record.source_timestamp,
            run.id,
        )

    if settings.is_snapshot_feed:
        current_rows = session.scalars(select(CurrentState)).all()
        for current in current_rows:
            evse = session.get(Evse, current.evse_id)
            if evse is None or evse.uid in seen_uids:
                continue
            current.missing_streak += 1
            if current.missing_streak >= settings.missing_feeds_before_unknown:
                _transition(
                    session,
                    evse,
                    "UNKNOWN",
                    observed_at,
                    observed_at,
                    None,
                    run.id,
                )


def ingest_static_payload(payload: bytes, observed_at: datetime | None = None, settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    observed_at = observed_at or datetime.now(timezone.utc)
    records = parse_static(payload)
    if settings.selected_evse_uids:
        records = [record for record in records if record.uid in settings.selected_evse_uids]
    with session_scope() as session:
        run = _fetch_run_start(session, "static", observed_at)
        _upsert_static(session, records, observed_at)
        run.completed_at = observed_at
        run.success = True
        run.item_count = len(records)
    return len(records)


def ingest_dynamic_payload(payload: bytes, observed_at: datetime | None = None, settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    observed_at = observed_at or datetime.now(timezone.utc)
    records = parse_dynamic(payload)
    if settings.selected_evse_uids:
        records = [record for record in records if record.uid in settings.selected_evse_uids]
    with session_scope() as session:
        run = _fetch_run_start(session, "dynamic", observed_at)
        _apply_dynamic(session, records, observed_at, run, settings)
        run.completed_at = observed_at
        run.success = True
        run.item_count = len(records)
    return len(records)


def collect_static(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    init_db()
    started = datetime.now(timezone.utc)
    try:
        result = download_xml(settings.mobie_static_url, settings)
        records = parse_static(result.payload)
        if settings.selected_evse_uids:
            records = [record for record in records if record.uid in settings.selected_evse_uids]
        raw_path = None
        if settings.save_raw_static:
            raw_path = save_payload(settings.raw_directory, "static", result.completed_at, result.payload, result.sha256)
        with session_scope() as session:
            run = _fetch_run_start(session, "static", result.requested_at)
            _upsert_static(session, records, result.completed_at)
            _complete_run(run, result, len(records), raw_path)
        logger.info("Static feed: %s EVSE", len(records))
        return len(records)
    except Exception as exc:  # noqa: BLE001
        with session_scope() as session:
            _failed_run(session, "static", started, exc)
        raise


def collect_dynamic(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    init_db()
    started = datetime.now(timezone.utc)
    try:
        result = download_xml(settings.mobie_dynamic_url, settings)
        records = parse_dynamic(result.payload)
        if settings.selected_evse_uids:
            records = [record for record in records if record.uid in settings.selected_evse_uids]
        raw_path = None
        if settings.save_raw_dynamic:
            raw_path = save_payload(settings.raw_directory, "dynamic", result.completed_at, result.payload, result.sha256)
        with session_scope() as session:
            run = _fetch_run_start(session, "dynamic", result.requested_at)
            _apply_dynamic(session, records, result.completed_at, run, settings)
            _complete_run(run, result, len(records), raw_path)
        logger.info("Dynamic feed: %s estados", len(records))
        return len(records)
    except Exception as exc:  # noqa: BLE001
        with session_scope() as session:
            _failed_run(session, "dynamic", started, exc)
        raise
