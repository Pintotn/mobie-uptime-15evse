from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    mobie_static_url: str = "https://pgm.mobie.pt/integration/nap/evChargingInfra"
    mobie_dynamic_url: str = "https://pgm.mobie.pt/integration/nap/evActualStatus"
    database_url: str = "sqlite:///./data/mobie_uptime.db"
    timezone: str = "Europe/Lisbon"
    poll_seconds: int = Field(default=60, ge=10)
    static_refresh_hour: int = Field(default=2, ge=0, le=23)
    http_timeout_seconds: float = Field(default=180.0, gt=0)
    http_max_retries: int = Field(default=3, ge=1, le=10)
    dynamic_feed_mode: str = "snapshot"
    missing_feeds_before_unknown: int = Field(default=3, ge=1)
    feed_stale_after_seconds: int = Field(default=300, ge=60)
    save_raw_static: bool = True
    save_raw_dynamic: bool = False
    raw_directory: Path = Path("./data/raw")
    user_agent: str = "mobie-uptime/0.3"
    evse_filter: str = ""

    @property
    def selected_evse_uids(self) -> set[str]:
        """EVSE UIDs permitidos, separados por vírgulas; vazio significa todos."""
        return {item.strip() for item in self.evse_filter.split(",") if item.strip()}

    @property
    def is_snapshot_feed(self) -> bool:
        return self.dynamic_feed_mode.strip().lower() == "snapshot"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
