from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Actual:
    start_time: datetime
    publish_time: datetime
    generation: float


@dataclass(frozen=True)
class Forecast:
    start_time: datetime
    publish_time: datetime
    generation: float


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp is missing a timezone: {value}")
    return parsed.astimezone(UTC)


class DataStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS actuals (
                    start_time TEXT PRIMARY KEY,
                    publish_time TEXT NOT NULL,
                    generation REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS forecasts (
                    start_time TEXT NOT NULL,
                    publish_time TEXT NOT NULL,
                    generation REAL NOT NULL,
                    PRIMARY KEY (start_time, publish_time)
                );
                CREATE INDEX IF NOT EXISTS forecasts_publish_time
                    ON forecasts (publish_time);
                CREATE TABLE IF NOT EXISTS refresh_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_attempt TEXT,
                    last_success TEXT,
                    last_error TEXT,
                    actual_rows INTEGER NOT NULL DEFAULT 0,
                    forecast_rows INTEGER NOT NULL DEFAULT 0
                );
                INSERT OR IGNORE INTO refresh_state (id) VALUES (1);
                """
            )

    def record_refresh_attempt(self, attempted_at: datetime) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE refresh_state SET last_attempt = ?, last_error = NULL WHERE id = 1",
                (utc_iso(attempted_at),),
            )

    def record_refresh_success(
        self,
        completed_at: datetime,
        actual_rows: int,
        forecast_rows: int,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE refresh_state
                SET last_success = ?, last_error = NULL, actual_rows = ?, forecast_rows = ?
                WHERE id = 1
                """,
                (utc_iso(completed_at), actual_rows, forecast_rows),
            )

    def record_refresh_error(self, message: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE refresh_state SET last_error = ? WHERE id = 1",
                (message[:1000],),
            )

    def refresh_state(self) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT last_attempt, last_success, last_error, actual_rows, forecast_rows
                FROM refresh_state WHERE id = 1
                """
            ).fetchone()
        return dict(row)

    def prune_history(self, keep_after: datetime) -> None:
        cutoff = utc_iso(keep_after)
        with self.connect() as connection:
            connection.execute(
                """
                DELETE FROM actuals
                WHERE start_time < ?
                  AND NOT (start_time >= '2026-01-01T00:00:00Z'
                           AND start_time < '2026-02-01T00:00:00Z')
                """,
                (cutoff,),
            )
            connection.execute(
                """
                DELETE FROM forecasts
                WHERE start_time < ?
                  AND NOT (start_time >= '2026-01-01T00:00:00Z'
                           AND start_time < '2026-02-01T00:00:00Z')
                """,
                (cutoff,),
            )

    def replace_records(self, actuals: list[Actual], forecasts: list[Forecast]) -> tuple[int, int]:
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO actuals (start_time, publish_time, generation)
                VALUES (?, ?, ?)
                ON CONFLICT(start_time) DO UPDATE SET
                    publish_time = excluded.publish_time,
                    generation = excluded.generation
                WHERE excluded.publish_time >= actuals.publish_time
                """,
                [
                    (utc_iso(row.start_time), utc_iso(row.publish_time), row.generation)
                    for row in actuals
                ],
            )
            connection.executemany(
                """
                INSERT INTO forecasts (start_time, publish_time, generation)
                VALUES (?, ?, ?)
                ON CONFLICT(start_time, publish_time) DO UPDATE SET
                    generation = excluded.generation
                """,
                [
                    (utc_iso(row.start_time), utc_iso(row.publish_time), row.generation)
                    for row in forecasts
                ],
            )
        return len(actuals), len(forecasts)

    def load_actuals(self) -> list[Actual]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT start_time, publish_time, generation FROM actuals ORDER BY start_time"
            ).fetchall()
        return [
            Actual(
                parse_timestamp(row["start_time"]),
                parse_timestamp(row["publish_time"]),
                float(row["generation"]),
            )
            for row in rows
        ]

    def load_forecasts(self) -> list[Forecast]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT start_time, publish_time, generation
                FROM forecasts
                ORDER BY start_time, publish_time
                """
            ).fetchall()
        return [
            Forecast(
                parse_timestamp(row["start_time"]),
                parse_timestamp(row["publish_time"]),
                float(row["generation"]),
            )
            for row in rows
        ]

    def counts(self) -> dict[str, int]:
        with self.connect() as connection:
            actual_count = connection.execute("SELECT COUNT(*) FROM actuals").fetchone()[0]
            forecast_count = connection.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
        return {"actuals": int(actual_count), "forecasts": int(forecast_count)}
