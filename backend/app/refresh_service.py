from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings
from app.data_store import DataStore
from app.elexon import fetch_elexon_data

logger = logging.getLogger(__name__)
LONDON = ZoneInfo("Europe/London")


class RefreshError(Exception):
    pass


def refresh_cache(
    store: DataStore,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, object]:
    started_at = now or datetime.now(UTC)
    local_today = started_at.astimezone(LONDON).date()
    last_success = store.refresh_state()["last_success"]
    lookback_days = 2 if last_success else 35
    start_date = local_today - timedelta(days=lookback_days)
    end_date = local_today + timedelta(days=3)
    store.record_refresh_attempt(started_at)

    try:
        actuals, forecasts = fetch_elexon_data(settings, start_date, end_date)
        actual_rows, forecast_rows = store.replace_records(actuals, forecasts)
        completed_at = now or datetime.now(UTC)
        store.prune_history(completed_at - timedelta(days=settings.cache_history_days))
        store.record_refresh_success(completed_at, actual_rows, forecast_rows)
    except (httpx.HTTPError, ValueError, OSError, sqlite3.Error) as error:
        message = f"{type(error).__name__}: {error}"
        store.record_refresh_error(message)
        logger.exception("Elexon cache refresh failed")
        raise RefreshError(message) from error

    logger.info(
        "Elexon cache refreshed: %d actual rows and %d forecast rows",
        actual_rows,
        forecast_rows,
    )
    return {
        "status": "success",
        "completed_at": completed_at.isoformat(),
        "actual_rows": actual_rows,
        "forecast_rows": forecast_rows,
        "delivery_window": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
    }
