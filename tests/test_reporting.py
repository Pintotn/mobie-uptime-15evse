from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from mobie_uptime.db import Base
from mobie_uptime.models import Evse, StatusInterval
from mobie_uptime.reporting import calculate_uptime


def test_daily_uptime_875_percent() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        evse = Evse(
            uid="EVSE-001",
            first_seen_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            last_seen_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            active=True,
        )
        session.add(evse)
        session.flush()
        session.add_all(
            [
                StatusInterval(
                    evse_id=evse.id,
                    status="AVAILABLE",
                    valid_from=datetime(2026, 1, 1, 0, tzinfo=timezone.utc),
                    valid_to=datetime(2026, 1, 1, 6, tzinfo=timezone.utc),
                    first_observed_at=datetime(2026, 1, 1, 0, tzinfo=timezone.utc),
                    last_observed_at=datetime(2026, 1, 1, 6, tzinfo=timezone.utc),
                ),
                StatusInterval(
                    evse_id=evse.id,
                    status="OUTOFORDER",
                    valid_from=datetime(2026, 1, 1, 6, tzinfo=timezone.utc),
                    valid_to=datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
                    first_observed_at=datetime(2026, 1, 1, 6, tzinfo=timezone.utc),
                    last_observed_at=datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
                ),
                StatusInterval(
                    evse_id=evse.id,
                    status="CHARGING",
                    valid_from=datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
                    valid_to=datetime(2026, 1, 2, 0, tzinfo=timezone.utc),
                    first_observed_at=datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
                    last_observed_at=datetime(2026, 1, 2, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()

        rows = calculate_uptime(
            session,
            start=date(2026, 1, 1),
            end_inclusive=date(2026, 1, 1),
            period="daily",
            timezone_name="UTC",
        )

    assert len(rows) == 1
    assert rows[0]["uptime_percent"] == 87.5
    assert rows[0]["coverage_percent"] == 100.0


def test_compact_daily_report_survives_pruning() -> None:
    from mobie_uptime.models import DailyAggregate
    from mobie_uptime.reporting import (
        calculate_uptime_compact,
        materialize_daily_aggregates,
        prune_detailed_intervals,
    )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        evse = Evse(
            uid="EVSE-COMPACT",
            operator_name="Operador Teste",
            city="Lisboa",
            first_seen_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            last_seen_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            active=True,
        )
        session.add(evse)
        session.flush()
        session.add_all(
            [
                StatusInterval(
                    evse_id=evse.id,
                    status="AVAILABLE",
                    valid_from=datetime(2026, 1, 1, 0, tzinfo=timezone.utc),
                    valid_to=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
                    first_observed_at=datetime(2026, 1, 1, 0, tzinfo=timezone.utc),
                    last_observed_at=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
                ),
                StatusInterval(
                    evse_id=evse.id,
                    status="OUTOFORDER",
                    valid_from=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
                    valid_to=datetime(2026, 1, 2, 0, tzinfo=timezone.utc),
                    first_observed_at=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
                    last_observed_at=datetime(2026, 1, 2, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()

        written = materialize_daily_aggregates(session, date(2026, 1, 1), "UTC")
        session.commit()
        assert written == 3
        assert session.query(DailyAggregate).count() == 3

        deleted = prune_detailed_intervals(session, date(2026, 1, 2), "UTC")
        session.commit()
        assert deleted == 2

        rows = calculate_uptime_compact(
            session,
            start=date(2026, 1, 1),
            end_inclusive=date(2026, 1, 1),
            period="daily",
            timezone_name="UTC",
            group_by="network",
        )

    assert len(rows) == 1
    assert rows[0]["uptime_percent"] == 50.0
