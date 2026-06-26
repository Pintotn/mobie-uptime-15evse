from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import func, select

from .config import get_settings
from .db import init_db, session_scope
from .models import Evse, FetchRun
from .reporting import calculate_uptime_compact

settings = get_settings()
app = FastAPI(
    title="MOBI.E Uptime API",
    version="0.2.0-free",
    description="Consulta dos estados recolhidos e dos indicadores de uptime.",
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, object]:
    with session_scope() as session:
        last_dynamic = session.scalar(
            select(FetchRun)
            .where(FetchRun.source_type == "dynamic")
            .order_by(FetchRun.requested_at.desc())
            .limit(1)
        )
        evse_count = session.scalar(select(func.count(Evse.id))) or 0
    return {
        "status": "ok",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "evse_count": evse_count,
        "last_dynamic_fetch": None
        if last_dynamic is None
        else {
            "requested_at": last_dynamic.requested_at,
            "success": last_dynamic.success,
            "item_count": last_dynamic.item_count,
            "error": last_dynamic.error_message,
        },
    }


@app.get("/v1/uptime")
def uptime(
    start: date,
    end: date,
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly|quarterly|semiannual|annual)$"),
    group_by: str = Query(default="network", pattern="^(network|operator|city|site|evse)$"),
    operator: str | None = None,
    city: str | None = None,
    evse_uid: str | None = None,
) -> list[dict[str, object]]:
    if end < start:
        raise HTTPException(status_code=400, detail="end deve ser igual ou posterior a start")
    with session_scope() as session:
        return calculate_uptime_compact(
            session=session,
            start=start,
            end_inclusive=end,
            period=period,  # type: ignore[arg-type]
            timezone_name=settings.timezone,
            group_by=group_by,  # type: ignore[arg-type]
            operator=operator,
            city=city,
            evse_uid=evse_uid,
        )


@app.get("/v1/evses")
def evses(limit: int = Query(default=100, ge=1, le=5000), offset: int = Query(default=0, ge=0)) -> list[dict[str, object]]:
    with session_scope() as session:
        rows = session.scalars(select(Evse).order_by(Evse.uid).offset(offset).limit(limit)).all()
        return [
            {
                "uid": row.uid,
                "evse_id": row.evse_id,
                "site_id": row.site_id,
                "operator_id": row.operator_id,
                "operator_name": row.operator_name,
                "site_name": row.site_name,
                "city": row.city,
                "max_power_kw": row.max_power_kw,
                "is_24_7": row.is_24_7,
                "active": row.active,
            }
            for row in rows
        ]
