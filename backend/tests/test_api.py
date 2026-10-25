from datetime import UTC, date, datetime, time

from fastapi.testclient import TestClient

from app.config import Settings
from app.data_store import Actual, DataStore, Forecast
from app.main import create_app


def test_dashboard_endpoint_returns_cutoff_limited_forecast(tmp_path) -> None:
    database = tmp_path / "test.sqlite3"
    store = DataStore(database)
    store.replace_records(
        [
            Actual(
                datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
                100.0,
            )
        ],
        [
            Forecast(
                datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2025, 12, 31, 8, 30, tzinfo=UTC),
                110.0,
            ),
            Forecast(
                datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2025, 12, 31, 9, 30, tzinfo=UTC),
                999.0,
            ),
        ],
    )
    settings = Settings(
        database_path=database,
        elexon_api_base="https://data.elexon.co.uk/bmrs/api/v1",
        default_cutoff=time(9, 0),
        data_start=date(2025, 12, 24),
        data_end=date(2026, 1, 31),
    )

    with TestClient(create_app(settings, database)) as client:
        response = client.get("/api/dashboard/2026-01-01")
        invalid_date = client.get("/api/dashboard/2025-12-31")
        metadata = client.get("/api/metadata")

    assert response.status_code == 200
    assert response.json()["series"][0]["forecast_mw"] == 110.0
    assert response.json()["series"][0]["actual_mw"] == 100.0
    assert invalid_date.status_code == 422
    assert metadata.status_code == 200
    assert metadata.json()["freshness"] == "not_configured"


def test_manual_refresh_is_available_and_rate_limited(tmp_path, monkeypatch) -> None:
    database = tmp_path / "refresh.sqlite3"
    settings = Settings(
        database_path=database,
        elexon_api_base="https://example.invalid",
        default_cutoff=time(9, 0),
        data_start=date(2025, 12, 24),
        data_end=date(2026, 1, 31),
    )
    monkeypatch.setattr(
        "app.main.refresh_cache",
        lambda store, config: {
            "status": "success",
            "completed_at": "2026-10-25T11:00:00Z",
            "actual_rows": 48,
            "forecast_rows": 100,
            "delivery_window": {"start": "2026-10-23", "end": "2026-10-28"},
        },
    )

    with TestClient(create_app(settings, database)) as client:
        first = client.post("/api/refresh")
        second = client.post("/api/refresh")

    assert first.status_code == 200
    assert first.json()["forecast_rows"] == 100
    assert second.status_code == 429
