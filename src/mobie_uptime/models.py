from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class FetchRun(Base):
    __tablename__ = "fetch_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(16), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[Optional[int]] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    payload_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    item_count: Mapped[Optional[int]] = mapped_column(Integer)
    raw_path: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)


class Evse(Base):
    __tablename__ = "evse"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    evse_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    station_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    operator_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    operator_name: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    site_name: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(160), index=True)
    postcode: Mapped[Optional[str]] = mapped_column(String(32))
    address: Mapped[Optional[str]] = mapped_column(String(500))
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    max_power_kw: Mapped[Optional[float]] = mapped_column(Float)
    connector_count: Mapped[Optional[int]] = mapped_column(Integer)
    is_24_7: Mapped[Optional[bool]] = mapped_column(Boolean)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    raw_static_json: Mapped[Optional[str]] = mapped_column(Text)

    current_state: Mapped[Optional["CurrentState"]] = relationship(back_populates="evse", uselist=False)


class StatusInterval(Base):
    __tablename__ = "status_interval"
    __table_args__ = (
        Index("ix_interval_evse_time", "evse_id", "valid_from", "valid_to"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evse_id: Mapped[int] = mapped_column(ForeignKey("evse.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fetch_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fetch_run.id"))


class CurrentState(Base):
    __tablename__ = "current_state"

    evse_id: Mapped[int] = mapped_column(ForeignKey("evse.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    status_since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    missing_streak: Mapped[int] = mapped_column(Integer, default=0)
    interval_id: Mapped[int] = mapped_column(ForeignKey("status_interval.id"), unique=True)

    evse: Mapped[Evse] = relationship(back_populates="current_state")


class DailyUptime(Base):
    __tablename__ = "daily_uptime"
    __table_args__ = (
        UniqueConstraint("evse_id", "local_day", name="uq_daily_uptime_evse_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evse_id: Mapped[int] = mapped_column(ForeignKey("evse.id", ondelete="CASCADE"), index=True)
    local_day: Mapped[date] = mapped_column(Date, index=True)
    up_seconds: Mapped[float] = mapped_column(Float, default=0)
    down_seconds: Mapped[float] = mapped_column(Float, default=0)
    unknown_seconds: Mapped[float] = mapped_column(Float, default=0)
    excluded_seconds: Mapped[float] = mapped_column(Float, default=0)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DailyAggregate(Base):
    __tablename__ = "daily_aggregate"
    __table_args__ = (
        UniqueConstraint("local_day", "group_type", "group_key", name="uq_daily_aggregate_day_group"),
        Index("ix_daily_aggregate_lookup", "group_type", "local_day", "group_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    local_day: Mapped[date] = mapped_column(Date, index=True)
    group_type: Mapped[str] = mapped_column(String(32), index=True)
    group_key: Mapped[str] = mapped_column(String(255), index=True)
    up_seconds: Mapped[float] = mapped_column(Float, default=0)
    down_seconds: Mapped[float] = mapped_column(Float, default=0)
    unknown_seconds: Mapped[float] = mapped_column(Float, default=0)
    excluded_seconds: Mapped[float] = mapped_column(Float, default=0)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
