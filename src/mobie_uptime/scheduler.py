from __future__ import annotations

import logging
import signal
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .collector import collect_dynamic, collect_static
from .config import Settings, get_settings
from .db import init_db

logger = logging.getLogger(__name__)


def run_scheduler(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    init_db()
    stopping = False

    def stop_handler(*_: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    tz = ZoneInfo(settings.timezone)
    next_dynamic = 0.0
    last_static_date = None

    while not stopping:
        now_monotonic = time.monotonic()
        local_now = datetime.now(tz)

        if now_monotonic >= next_dynamic:
            try:
                collect_dynamic(settings)
            except Exception:  # noqa: BLE001
                logger.exception("Falha na recolha dinâmica")
            next_dynamic = time.monotonic() + settings.poll_seconds

        if local_now.hour >= settings.static_refresh_hour and last_static_date != local_now.date():
            try:
                collect_static(settings)
                last_static_date = local_now.date()
            except Exception:  # noqa: BLE001
                logger.exception("Falha na recolha estática")

        time.sleep(1)
