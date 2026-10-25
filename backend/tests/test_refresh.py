from datetime import UTC, date, datetime, time, timedelta

from app.config import Settings
from app.data_store import DataStore
from app.refresh_service import refresh_cache


def test_refresh_bootstraps_recent_accuracy_then_uses_incremental_window(
    tmp_path, monkeypatch
) -> None:
    store = DataStore(tmp_path / "refresh.sqlite3")
    settings = Settings(
        database_path=tmp_path / "refresh.sqlite3",
        elexon_api_base="https://example.invalid",
        default_cutoff=time(9, 0),
        data_start=date(2025, 12, 24),
        data_end=date(2026, 1, 31),
    )
    windows: list[tuple[date, date]] = []

    def fetch(_settings, start_date: date, end_date: date):
        windows.append((start_date, end_date))
        return [], []

    monkeypatch.setattr("app.refresh_service.fetch_elexon_data", fetch)
    first_refresh = datetime(2026, 10, 25, 11, 0, tzinfo=UTC)

    first = refresh_cache(store, settings, first_refresh)
    second = refresh_cache(store, settings, first_refresh + timedelta(minutes=15))

    assert windows == [
        (date(2026, 9, 20), date(2026, 10, 28)),
        (date(2026, 10, 23), date(2026, 10, 28)),
    ]
    assert first["status"] == second["status"] == "success"
    assert store.refresh_state()["last_success"] == "2026-10-25T11:15:00Z"
