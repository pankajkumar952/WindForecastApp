from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    elexon_api_base: str
    default_cutoff: time
    data_start: date
    data_end: date
    refresh_interval_seconds: int = 900
    cache_history_days: int = 120
    live_refresh_enabled: bool = False


def get_settings() -> Settings:
    return Settings(
        database_path=Path(os.getenv("DATABASE_PATH", "data/wind.sqlite3")),
        elexon_api_base=os.getenv(
            "ELEXON_API_BASE", "https://data.elexon.co.uk/bmrs/api/v1"
        ).rstrip("/"),
        default_cutoff=time.fromisoformat(os.getenv("DEFAULT_CUTOFF", "09:00")),
        data_start=date.fromisoformat(os.getenv("DATA_START", "2025-12-24")),
        data_end=date.fromisoformat(os.getenv("DATA_END", "2026-01-31")),
        refresh_interval_seconds=max(60, int(os.getenv("REFRESH_INTERVAL_SECONDS", "900"))),
        cache_history_days=max(60, int(os.getenv("CACHE_HISTORY_DAYS", "120"))),
        live_refresh_enabled=os.getenv("LIVE_REFRESH_ENABLED", "true").lower()
        in {"1", "true", "yes"},
    )
