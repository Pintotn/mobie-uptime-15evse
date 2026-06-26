from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from .config import Settings


@dataclass(frozen=True)
class DownloadResult:
    payload: bytes
    requested_at: datetime
    completed_at: datetime
    status_code: int
    sha256: str
    content_type: str | None


def download_xml(url: str, settings: Settings) -> DownloadResult:
    last_error: Exception | None = None
    headers = {
        "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.1",
        "User-Agent": settings.user_agent,
    }

    for attempt in range(1, settings.http_max_retries + 1):
        requested_at = datetime.now(timezone.utc)
        try:
            with httpx.Client(
                timeout=httpx.Timeout(settings.http_timeout_seconds),
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.content
            completed_at = datetime.now(timezone.utc)
            return DownloadResult(
                payload=payload,
                requested_at=requested_at,
                completed_at=completed_at,
                status_code=response.status_code,
                sha256=hashlib.sha256(payload).hexdigest(),
                content_type=response.headers.get("content-type"),
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < settings.http_max_retries:
                time.sleep(min(2 ** (attempt - 1), 10))

    assert last_error is not None
    raise last_error
