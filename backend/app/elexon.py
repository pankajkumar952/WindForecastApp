from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta

import httpx

from app.config import Settings
from app.data_store import Actual, Forecast, parse_timestamp

logger = logging.getLogger(__name__)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return parse_timestamp(value)
    except ValueError:
        return None


def _parse_rows(
    payload: object, record_type: type[Actual] | type[Forecast]
) -> list[Actual] | list[Forecast]:
    if not isinstance(payload, list):
        raise ValueError("Elexon returned a non-array response")

    records: list[Actual] | list[Forecast] = []
    invalid = 0
    for item in payload:
        if not isinstance(item, dict):
            invalid += 1
            continue
        start_time = _timestamp(item.get("startTime"))
        publish_time = _timestamp(item.get("publishTime"))
        generation = _number(item.get("generation"))
        if start_time is None or publish_time is None or generation is None:
            invalid += 1
            continue
        records.append(record_type(start_time, publish_time, generation))
    if invalid:
        logger.warning("Skipped %d Elexon rows with missing or invalid fields", invalid)
    return records


def fetch_elexon_data(
    settings: Settings, start_date: date, end_date: date
) -> tuple[list[Actual], list[Forecast]]:
    if end_date < start_date:
        raise ValueError("End date must be on or after start date")

    start_for_publications = datetime.combine(start_date - timedelta(days=1), time.min, tzinfo=UTC)
    end_for_publications = datetime.combine(end_date, time.max, tzinfo=UTC)
    with httpx.Client(base_url=settings.elexon_api_base, timeout=60.0) as client:
        actual_response = client.get(
            "/datasets/FUELHH/stream",
            params={
                "settlementDateFrom": start_date.isoformat(),
                "settlementDateTo": end_date.isoformat(),
                "fuelType": "WIND",
            },
        )
        actual_response.raise_for_status()
        forecast_response = client.get(
            "/datasets/WINDFOR/stream",
            params={
                "publishDateTimeFrom": start_for_publications.isoformat(),
                "publishDateTimeTo": end_for_publications.isoformat(),
            },
        )
        forecast_response.raise_for_status()

    actuals = _parse_rows(actual_response.json(), Actual)
    forecasts = _parse_rows(forecast_response.json(), Forecast)
    return actuals, forecasts
