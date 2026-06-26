from __future__ import annotations

import gzip
from datetime import datetime
from pathlib import Path


def save_payload(base_dir: Path, source_type: str, timestamp: datetime, payload: bytes, sha256: str) -> str:
    directory = base_dir / source_type / timestamp.strftime("%Y/%m/%d")
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{timestamp.strftime('%H%M%S')}_{sha256[:12]}.xml.gz"
    path = directory / filename
    with gzip.open(path, "wb", compresslevel=6) as handle:
        handle.write(payload)
    return str(path)
