from datetime import date, datetime, time, timedelta
from math import sqrt

import pandas as pd
import pytest

from app.analysis import (
    calculate_metrics,
    london_today,
    select_day_ahead_forecasts,
    validate_decision_cutoff,
)
from app.data_store import Forecast


def forecast(start: str, published: str, generation: float) -> Forecast:
    return Forecast(
        datetime.fromisoformat(start.replace("Z", "+00:00")),
        datetime.fromisoformat(published.replace("Z", "+00:00")),
        generation,
    )


def test_cutoff_uses_latest_forecast_not_published_after_local_cutoff() -> None:
    rows = [
        forecast("2026-01-01T00:00:00Z", "2025-12-31T08:30:00Z", 100.0),
        forecast("2026-01-01T00:00:00Z", "2025-12-31T09:00:00Z", 110.0),
        forecast("2026-01-01T00:00:00Z", "2025-12-31T09:30:00Z", 999.0),
        forecast("2026-01-01T01:00:00Z", "2025-12-31T08:30:00Z", 120.0),
    ]

    selected = select_day_ahead_forecasts(rows, date(2026, 1, 1), time(9, 0))

    assert [row.generation for row in selected] == [110.0, 120.0]


def test_cutoff_uses_uk_local_time_and_deduplicates_target_period() -> None:
    rows = [
        forecast("2026-01-15T12:00:00Z", "2026-01-14T08:30:00Z", 200.0),
        forecast("2026-01-15T12:00:00Z", "2026-01-14T09:30:00Z", 250.0),
    ]

    selected = select_day_ahead_forecasts(rows, date(2026, 1, 15), time(9, 0))

    assert len(selected) == 1
    assert selected[0].generation == 200.0


def test_metrics_include_signed_bias_and_ignore_zero_actuals_for_mape() -> None:
    frame = pd.DataFrame(
        {
            "forecast": [12.0, 0.0, 8.0],
            "actual": [10.0, 0.0, 10.0],
        }
    )

    metrics = calculate_metrics(frame)

    assert metrics["sample_count"] == 3
    assert metrics["mae"] == 4 / 3
    assert metrics["rmse"] == sqrt(8 / 3)
    assert metrics["mape"] == 20.0
    assert metrics["bias"] == 0.0


def test_metrics_return_null_mape_when_all_actuals_are_zero() -> None:
    frame = pd.DataFrame({"forecast": [3.0], "actual": [0.0]})

    assert calculate_metrics(frame)["mape"] is None


def test_future_decision_cutoff_is_not_presented_as_an_available_snapshot() -> None:
    with pytest.raises(ValueError, match="cutoff has not occurred"):
        validate_decision_cutoff(london_today() + timedelta(days=2), time(9, 0))
