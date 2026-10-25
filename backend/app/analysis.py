from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.data_store import Actual, Forecast

LONDON = ZoneInfo("Europe/London")
JANUARY_START = date(2026, 1, 1)
PILOT_START = date(2026, 1, 1)


def london_today() -> date:
    return datetime.now(LONDON).date()


def validate_delivery_date(value: date, latest_offset_days: int = 7) -> None:
    if value < JANUARY_START or value > london_today() + timedelta(days=latest_offset_days):
        raise ValueError(
            "Date must be on or after 1 January 2026 and no more than "
            f"{latest_offset_days} days ahead"
        )


def cutoff_in_utc(delivery_date: date, cutoff: time) -> datetime:
    local_cutoff = datetime.combine(delivery_date - timedelta(days=1), cutoff, tzinfo=LONDON)
    return local_cutoff.astimezone(ZoneInfo("UTC"))


def validate_decision_cutoff(delivery_date: date, cutoff: time) -> None:
    validate_delivery_date(delivery_date)
    if cutoff_in_utc(delivery_date, cutoff) > datetime.now(ZoneInfo("UTC")):
        raise ValueError(
            "The decision cutoff has not occurred yet; its latest forecast snapshot "
            "is not available."
        )


def select_day_ahead_forecasts(
    forecasts: Sequence[Forecast], delivery_date: date, cutoff: time
) -> list[Forecast]:
    cutoff_utc = cutoff_in_utc(delivery_date, cutoff)
    selected: dict[datetime, Forecast] = {}
    for forecast in forecasts:
        if forecast.start_time.astimezone(LONDON).date() != delivery_date:
            continue
        if forecast.publish_time > cutoff_utc:
            continue
        previous = selected.get(forecast.start_time)
        if previous is None or forecast.publish_time > previous.publish_time:
            selected[forecast.start_time] = forecast
    return sorted(selected.values(), key=lambda row: row.start_time)


def _joined_frame(
    actuals: Sequence[Actual],
    forecasts: Sequence[Forecast],
    delivery_date: date,
    cutoff: time,
) -> pd.DataFrame:
    selected = select_day_ahead_forecasts(forecasts, delivery_date, cutoff)
    actual_by_start: dict[datetime, Actual] = {}
    for actual in actuals:
        if actual.start_time.astimezone(LONDON).date() == delivery_date:
            previous = actual_by_start.get(actual.start_time)
            if previous is None or actual.publish_time > previous.publish_time:
                actual_by_start[actual.start_time] = actual

    records: list[dict[str, Any]] = []
    for forecast in selected:
        actual = actual_by_start.get(forecast.start_time)
        start_local = forecast.start_time.astimezone(LONDON)
        records.append(
            {
                "start_time": forecast.start_time,
                "local_time": start_local,
                "forecast": forecast.generation,
                "actual": actual.generation if actual else np.nan,
                "publish_time": forecast.publish_time,
                "error": forecast.generation - actual.generation if actual else np.nan,
                "horizon_hours": (forecast.start_time - forecast.publish_time).total_seconds()
                / 3600,
            }
        )
    return pd.DataFrame.from_records(
        records,
        columns=[
            "start_time",
            "local_time",
            "forecast",
            "actual",
            "publish_time",
            "error",
            "horizon_hours",
        ],
    )


def calculate_metrics(frame: pd.DataFrame) -> dict[str, float | int | None]:
    valid = frame.dropna(subset=["forecast", "actual"])
    if valid.empty:
        return {
            "sample_count": 0,
            "mae": None,
            "rmse": None,
            "mape": None,
            "bias": None,
            "p90_absolute_error": None,
            "p95_absolute_error": None,
        }

    errors = valid["forecast"] - valid["actual"]
    nonzero_actuals = valid.loc[valid["actual"] != 0, "actual"]
    mape: float | None = None
    if not nonzero_actuals.empty:
        mape = float(
            (
                (valid.loc[valid["actual"] != 0, "forecast"] - nonzero_actuals).abs()
                / nonzero_actuals.abs()
            ).mean()
            * 100
        )
    absolute_errors = errors.abs()
    return {
        "sample_count": int(len(valid)),
        "mae": float(absolute_errors.mean()),
        "rmse": float(math.sqrt(float((errors**2).mean()))),
        "mape": mape,
        "bias": float(errors.mean()),
        "p90_absolute_error": float(absolute_errors.quantile(0.90)),
        "p95_absolute_error": float(absolute_errors.quantile(0.95)),
    }


def _pairs_for_date(
    actuals: Sequence[Actual],
    forecasts: Sequence[Forecast],
    delivery_date: date,
    cutoff: time,
) -> pd.DataFrame:
    return _joined_frame(actuals, forecasts, delivery_date, cutoff).dropna(
        subset=["forecast", "actual"]
    )


def _energy_mwh(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None
    intervals = frame["start_time"].sort_values().diff().dt.total_seconds() / 3600
    typical_interval = float(intervals.dropna().median()) if intervals.notna().any() else 1.0
    if not math.isfinite(typical_interval) or typical_interval <= 0:
        typical_interval = 1.0
    return float(frame["forecast"].sum() * typical_interval)


def daily_dashboard(
    actuals: Sequence[Actual],
    forecasts: Sequence[Forecast],
    delivery_date: date,
    cutoff: time,
) -> dict[str, Any]:
    frame = _joined_frame(actuals, forecasts, delivery_date, cutoff)
    if frame.empty:
        raise LookupError("No eligible forecast is cached for this delivery date and cutoff")

    prior_dates = [delivery_date - timedelta(days=offset) for offset in range(1, 32)]
    historical_frames = [_pairs_for_date(actuals, forecasts, day, cutoff) for day in prior_dates]
    historical_errors = [
        abs(float(error))
        for history in historical_frames
        for error in history["error"].dropna().tolist()
    ]
    p90_error = float(np.quantile(historical_errors, 0.90)) if historical_errors else None

    observed_actuals = frame["actual"].dropna()
    forecast_values = frame["forecast"]
    series: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        value = {
            "start_time": row.local_time.isoformat(),
            "time_label": row.local_time.strftime("%H:%M"),
            "forecast_mw": float(row.forecast),
            "actual_mw": None if pd.isna(row.actual) else float(row.actual),
            "publish_time": row.publish_time.isoformat(),
        }
        if p90_error is not None:
            value["lower_mw"] = max(0.0, float(row.forecast) - p90_error)
            value["upper_mw"] = float(row.forecast) + p90_error
        else:
            value["lower_mw"] = None
            value["upper_mw"] = None
        series.append(value)

    return {
        "delivery_date": delivery_date.isoformat(),
        "timezone": "Europe/London",
        "decision_cutoff": datetime.combine(
            delivery_date - timedelta(days=1), cutoff, tzinfo=LONDON
        ).isoformat(),
        "summary": {
            "forecast_mwh": _energy_mwh(frame),
            "peak_mw": float(forecast_values.max()) if not forecast_values.empty else None,
            "minimum_mw": float(forecast_values.min()) if not forecast_values.empty else None,
            "forecast_intervals": int(len(frame)),
            "matched_actual_intervals": int(observed_actuals.count()),
            "missing_actual_intervals": int(frame["actual"].isna().sum()),
            "uncertainty_p90_mw": p90_error,
            "uncertainty_sample_count": int(len(historical_errors)),
        },
        "series": series,
    }


def _error_bucket(hours: float) -> str:
    if hours < 18:
        return "<18h"
    if hours < 24:
        return "18-24h"
    if hours < 30:
        return "24-30h"
    if hours < 36:
        return "30-36h"
    if hours < 42:
        return "36-42h"
    return "42h+"


def accuracy_report(
    actuals: Sequence[Actual],
    forecasts: Sequence[Forecast],
    start_date: date,
    end_date: date,
    cutoff: time,
) -> dict[str, Any]:
    daily_frames = [
        _pairs_for_date(actuals, forecasts, day, cutoff)
        for day in pd.date_range(start_date, end_date, freq="D").date
    ]
    available = [frame for frame in daily_frames if not frame.empty]
    combined = (
        pd.concat(available, ignore_index=True)
        if available
        else pd.DataFrame(
            columns=[
                "start_time",
                "local_time",
                "forecast",
                "actual",
                "publish_time",
                "error",
                "horizon_hours",
            ]
        )
    )
    metrics = calculate_metrics(combined)
    errors = combined["error"].dropna().to_numpy(dtype=float)
    histogram: list[dict[str, float | int]] = []
    if errors.size:
        counts, edges = np.histogram(errors, bins=min(20, max(5, int(np.sqrt(errors.size)))))
        histogram = [
            {
                "bin_start": float(edges[index]),
                "bin_end": float(edges[index + 1]),
                "count": int(count),
            }
            for index, count in enumerate(counts)
        ]

    error_timeline = [
        {
            "start_time": row.local_time.isoformat(),
            "time_label": f"{row.local_time:%d %b %H:%M}",
            "error_mw": float(row.error),
            "forecast_mw": float(row.forecast),
            "actual_mw": float(row.actual),
            "horizon_hours": float(row.horizon_hours),
        }
        for row in combined.itertuples(index=False)
    ]

    hourly: list[dict[str, Any]] = []
    horizons: list[dict[str, Any]] = []
    if not combined.empty:
        by_hour = combined.assign(hour=combined["local_time"].map(lambda item: item.hour))
        for hour, group in by_hour.groupby("hour", sort=True):
            hourly.append(
                {
                    "hour": int(hour),
                    "label": f"{int(hour):02d}:00",
                    "mae_mw": float(group["error"].abs().mean()),
                    "bias_mw": float(group["error"].mean()),
                    "sample_count": int(len(group)),
                }
            )
        by_horizon = combined.assign(horizon_bucket=combined["horizon_hours"].map(_error_bucket))
        bucket_order = ["<18h", "18-24h", "24-30h", "30-36h", "36-42h", "42h+"]
        for bucket in bucket_order:
            group = by_horizon[by_horizon["horizon_bucket"] == bucket]
            if not group.empty:
                horizons.append(
                    {
                        "horizon": bucket,
                        "mae_mw": float(group["error"].abs().mean()),
                        "bias_mw": float(group["error"].mean()),
                        "sample_count": int(len(group)),
                    }
                )

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "timezone": "Europe/London",
        "decision_cutoff": cutoff.isoformat(timespec="minutes"),
        "metrics": metrics,
        "daily_coverage": [
            {
                "date": day.isoformat(),
                "matched_intervals": int(len(frame)),
            }
            for day, frame in zip(
                pd.date_range(start_date, end_date, freq="D").date,
                daily_frames,
                strict=True,
            )
        ],
        "error_timeline": error_timeline,
        "histogram": histogram,
        "by_hour": hourly,
        "by_horizon": horizons,
    }
