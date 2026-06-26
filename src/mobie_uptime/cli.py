from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import typer

from .collector import collect_dynamic, collect_static, ingest_dynamic_payload, ingest_static_payload
from .config import get_settings
from .db import init_db, session_scope
from .reporting import (
    calculate_uptime_compact,
    materialize_daily_aggregates,
    prune_detailed_intervals,
    write_csv,
)
from .scheduler import run_scheduler

app = typer.Typer(no_args_is_help=True, help="Recolha DATEX II da MOBI.E e cálculo de uptime.")


def _configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _parse_date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{name} deve estar no formato YYYY-MM-DD") from exc


def _parse_datetime(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise typer.BadParameter("observed-at deve ser um timestamp ISO 8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@app.command("init-db")
def init_database() -> None:
    init_db()
    typer.echo("Base de dados inicializada.")


@app.command("collect-static")
def collect_static_command(verbose: bool = False) -> None:
    _configure_logging(verbose)
    count = collect_static()
    typer.echo(f"Dados estáticos recolhidos: {count} EVSE.")


@app.command("collect-dynamic")
def collect_dynamic_command(verbose: bool = False) -> None:
    _configure_logging(verbose)
    count = collect_dynamic()
    typer.echo(f"Dados dinâmicos recolhidos: {count} estados.")


@app.command("ingest-file")
def ingest_file(
    kind: Annotated[str, typer.Argument(help="static ou dynamic")],
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    observed_at: Annotated[str | None, typer.Option(help="Timestamp ISO; por defeito agora em UTC")] = None,
) -> None:
    init_db()
    payload = path.read_bytes()
    timestamp = _parse_datetime(observed_at)
    if kind.lower() == "static":
        count = ingest_static_payload(payload, timestamp)
    elif kind.lower() == "dynamic":
        count = ingest_dynamic_payload(payload, timestamp)
    else:
        raise typer.BadParameter("kind deve ser static ou dynamic")
    typer.echo(f"Registos processados: {count}")


@app.command("report")
def report(
    start: Annotated[str, typer.Option(help="Data inicial YYYY-MM-DD, inclusive")],
    end: Annotated[str, typer.Option(help="Data final YYYY-MM-DD, inclusive")],
    period: Annotated[str, typer.Option(help="daily, weekly, monthly, quarterly, semiannual ou annual")] = "daily",
    group_by: Annotated[str, typer.Option(help="network, operator, city, site ou evse")] = "network",
    operator: Annotated[str | None, typer.Option()] = None,
    city: Annotated[str | None, typer.Option()] = None,
    evse_uid: Annotated[str | None, typer.Option()] = None,
    output: Annotated[Path | None, typer.Option(help="Ficheiro CSV de saída")] = None,
) -> None:
    start_date = _parse_date(start, "start")
    end_date = _parse_date(end, "end")
    if end_date < start_date:
        raise typer.BadParameter("end deve ser igual ou posterior a start")
    valid_periods = {"daily", "weekly", "monthly", "quarterly", "semiannual", "annual"}
    valid_groups = {"network", "operator", "city", "site", "evse"}
    if period not in valid_periods:
        raise typer.BadParameter(f"period inválido: {period}")
    if group_by not in valid_groups:
        raise typer.BadParameter(f"group_by inválido: {group_by}")

    init_db()
    settings = get_settings()
    with session_scope() as session:
        rows = calculate_uptime_compact(
            session,
            start=start_date,
            end_inclusive=end_date,
            period=period,  # type: ignore[arg-type]
            timezone_name=settings.timezone,
            group_by=group_by,  # type: ignore[arg-type]
            operator=operator,
            city=city,
            evse_uid=evse_uid,
        )

    if output:
        write_csv(rows, output)
        typer.echo(f"Relatório gravado em {output}")
    else:
        typer.echo(json.dumps(rows, indent=2, ensure_ascii=False, default=str))


@app.command("scheduler")
def scheduler_command(verbose: bool = False) -> None:
    _configure_logging(verbose)
    run_scheduler()


@app.command("maintain")
def maintain(
    days: Annotated[int, typer.Option(help="Dias completos recentes a recalcular")] = 3,
    retention_days: Annotated[int, typer.Option(help="Dias de detalhe a conservar")] = 14,
) -> None:
    """Cria resumos compactos e remove detalhe antigo para poupar espaço."""
    if days < 1:
        raise typer.BadParameter("days deve ser pelo menos 1")
    if retention_days < days + 1:
        raise typer.BadParameter("retention-days deve ser superior a days")

    init_db()
    settings = get_settings()
    today_local = datetime.now(ZoneInfo(settings.timezone)).date()
    written = 0
    deleted = 0
    with session_scope() as session:
        for offset in range(days, 0, -1):
            target_day = today_local - timedelta(days=offset)
            written += materialize_daily_aggregates(
                session,
                local_day=target_day,
                timezone_name=settings.timezone,
            )
        cutoff = today_local - timedelta(days=retention_days)
        deleted = prune_detailed_intervals(
            session,
            cutoff_local_day=cutoff,
            timezone_name=settings.timezone,
        )

    typer.echo(
        f"Manutenção concluída: {written} agregados gravados; "
        f"{deleted} intervalos antigos removidos."
    )
