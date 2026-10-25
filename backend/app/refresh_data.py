from __future__ import annotations

import argparse
import logging
from datetime import date

from app.config import get_settings
from app.data_store import DataStore
from app.elexon import fetch_elexon_data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and cache national wind actuals and forecasts from Elexon BMRS."
    )
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    args = parser.parse_args()

    settings = get_settings()
    start_date = args.start_date or settings.data_start
    end_date = args.end_date or settings.data_end
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    actuals, forecasts = fetch_elexon_data(settings, start_date, end_date)
    store = DataStore(settings.database_path)
    actual_count, forecast_count = store.replace_records(actuals, forecasts)
    logging.info(
        "Cached %s actual rows and %s forecast rows in %s",
        actual_count,
        forecast_count,
        settings.database_path,
    )


if __name__ == "__main__":
    main()
