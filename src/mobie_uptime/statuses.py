from __future__ import annotations

from enum import StrEnum


class StatusClass(StrEnum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"
    EXCLUDED = "excluded"


UP_STATUSES = {
    "AVAILABLE",
    "CHARGING",
    "RESERVED",
    "BLOCKED",
    "OCCUPIED",
}

DOWN_STATUSES = {
    "INOPERATIVE",
    "OUTOFORDER",
    "OUT_OF_ORDER",
    "FAULTED",
    "UNAVAILABLE",
    "OFFLINE",
}

EXCLUDED_STATUSES = {
    "PLANNED",
    "REMOVED",
}

_STATUS_ALIASES = {
    "AVAILABLE": "AVAILABLE",
    "FREE": "AVAILABLE",
    "OPERATIVE": "AVAILABLE",
    "OPERATIONAL": "AVAILABLE",
    "CHARGING": "CHARGING",
    "IN_USE": "CHARGING",
    "INUSE": "CHARGING",
    "OCCUPIED": "OCCUPIED",
    "RESERVED": "RESERVED",
    "BLOCKED": "BLOCKED",
    "INOPERATIVE": "INOPERATIVE",
    "NON_OPERATIONAL": "INOPERATIVE",
    "NONOPERATIONAL": "INOPERATIVE",
    "OUTOFORDER": "OUTOFORDER",
    "OUT_OF_ORDER": "OUTOFORDER",
    "FAULTED": "FAULTED",
    "UNAVAILABLE": "UNAVAILABLE",
    "OFFLINE": "OFFLINE",
    "PLANNED": "PLANNED",
    "REMOVED": "REMOVED",
    "UNKNOWN": "UNKNOWN",
}


def normalize_status(raw: str | None) -> str:
    if not raw:
        return "UNKNOWN"
    key = raw.strip().upper().replace("-", "_").replace(" ", "_")
    compact = key.replace("_", "")
    if key in _STATUS_ALIASES:
        return _STATUS_ALIASES[key]
    if compact in _STATUS_ALIASES:
        return _STATUS_ALIASES[compact]
    return "UNKNOWN"


def classify_status(status: str) -> StatusClass:
    normalized = normalize_status(status)
    if normalized in UP_STATUSES:
        return StatusClass.UP
    if normalized in DOWN_STATUSES:
        return StatusClass.DOWN
    if normalized in EXCLUDED_STATUSES:
        return StatusClass.EXCLUDED
    return StatusClass.UNKNOWN
