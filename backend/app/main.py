from __future__ import annotations

import asyncio
import logging
import threading
import time as monotonic_time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analysis import (
    PILOT_START,
    accuracy_report,
    daily_dashboard,
    london_today,
    validate_decision_cutoff,
    validate_delivery_date,
)
from app.config import Settings, get_settings
from app.data_store import DataStore
from app.refresh_service import RefreshError, refresh_cache

logger = logging.getLogger(__name__)
LONDON = ZoneInfo("Europe/London")


def create_app(
    settings: Settings | None = None,
    database_path: Path | None = None,
) -> FastAPI:
    config = settings or get_settings()
    db_path = database_path or config.database_path
    store = DataStore(db_path)
    refresh_lock = threading.Lock()
    last_manual_refresh_at: float | None = None
    manual_refresh_cooldown_seconds = 30

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        store.initialize()
        refresh_task = asyncio.create_task(refresh_loop()) if config.live_refresh_enabled else None
        try:
            yield
        finally:
            if refresh_task is not None:
                refresh_task.cancel()
                try:
                    await refresh_task
                except asyncio.CancelledError:
                    pass

    def run_refresh(manual: bool) -> dict[str, object]:
        nonlocal last_manual_refresh_at
        if not refresh_lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409,
                detail="A data refresh is already in progress. Try again shortly.",
            )
        try:
            if manual:
                now_monotonic = monotonic_time.monotonic()
                if (
                    last_manual_refresh_at is not None
                    and now_monotonic - last_manual_refresh_at < manual_refresh_cooldown_seconds
                ):
                    retry_after = int(
                        manual_refresh_cooldown_seconds - (now_monotonic - last_manual_refresh_at)
                    )
                    raise HTTPException(
                        status_code=429,
                        detail=f"Please wait {retry_after} seconds before refreshing again.",
                        headers={"Retry-After": str(retry_after)},
                    )
                last_manual_refresh_at = now_monotonic
            try:
                return refresh_cache(store, config)
            except RefreshError as error:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"Elexon refresh failed. The last known cache remains available. {error}"
                    ),
                ) from error
        finally:
            refresh_lock.release()

    async def refresh_loop() -> None:
        while True:
            try:
                await asyncio.to_thread(run_refresh, False)
            except HTTPException as error:
                logger.warning("Scheduled Elexon refresh was not completed: %s", error.detail)
            await asyncio.sleep(config.refresh_interval_seconds)

    app = FastAPI(
        title="WindLens | UK Wind Forecast Intelligence",
        description=(
            "Rolling decision-cutoff wind generation forecasts and forecast "
            "accuracy, refreshed from Elexon BMRS."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.store = store
    app.state.settings = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    def load_data():
        counts = store.counts()
        if counts["actuals"] == 0 or counts["forecasts"] == 0:
            raise HTTPException(
                status_code=503,
                detail=(
                    "The local Elexon cache is empty. Check Elexon connectivity "
                    "or run `python -m app.refresh_data` from the backend directory."
                ),
            )
        return store.load_actuals(), store.load_forecasts()

    def validate_date_or_422(value: date, latest_offset_days: int = 7) -> None:
        try:
            validate_delivery_date(value, latest_offset_days)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/health")
    def health() -> dict[str, object]:
        counts = store.counts()
        refresh_state = store.refresh_state()
        return {
            "status": "ok" if counts["actuals"] and counts["forecasts"] else "degraded",
            "cache": counts,
            "refresh": refresh_state,
        }

    @app.get("/api/metadata")
    def metadata() -> dict[str, object]:
        now = datetime.now(UTC)
        refresh_state = store.refresh_state()
        last_success = refresh_state["last_success"]
        next_refresh = None
        if last_success:
            next_refresh = (
                datetime.fromisoformat(last_success.replace("Z", "+00:00"))
                + timedelta(seconds=config.refresh_interval_seconds)
            ).isoformat()
        last_error = refresh_state["last_error"]
        if last_error:
            freshness = "degraded"
        elif last_success:
            last_success_at = datetime.fromisoformat(last_success.replace("Z", "+00:00"))
            freshness = (
                "live"
                if (now - last_success_at).total_seconds() <= config.refresh_interval_seconds * 2
                else "stale"
            )
        else:
            freshness = "starting" if config.live_refresh_enabled else "not_configured"
        return {
            "timezone": "Europe/London",
            "default_cutoff": config.default_cutoff.isoformat(timespec="minutes"),
            "analysis_start": PILOT_START.isoformat(),
            "analysis_end": london_today().isoformat(),
            "latest_delivery_date": (
                london_today()
                + timedelta(
                    days=(
                        1
                        if datetime.now(LONDON).timetz().replace(tzinfo=None)
                        >= config.default_cutoff
                        else 0
                    )
                )
            ).isoformat(),
            "source": "Elexon BMRS",
            "refresh_interval_seconds": config.refresh_interval_seconds,
            "refresh_enabled": config.live_refresh_enabled,
            "freshness": freshness,
            "last_refresh_attempt": refresh_state["last_attempt"],
            "last_successful_refresh": last_success,
            "next_refresh": next_refresh,
            "last_refresh_error": last_error,
            "last_refresh_actual_rows": refresh_state["actual_rows"],
            "last_refresh_forecast_rows": refresh_state["forecast_rows"],
            "cache": store.counts(),
        }

    @app.post("/api/refresh")
    def refresh(response: Response) -> dict[str, object]:
        result = run_refresh(manual=True)
        response.headers["Cache-Control"] = "no-store"
        return result

    @app.get("/api/dashboard/{delivery_date}")
    def dashboard(
        delivery_date: date,
        cutoff: Annotated[time, Query()] = config.default_cutoff,
    ) -> dict[str, object]:
        try:
            validate_decision_cutoff(delivery_date, cutoff)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        actuals, forecasts = load_data()
        try:
            return daily_dashboard(actuals, forecasts, delivery_date, cutoff)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/accuracy")
    def accuracy(
        start_date: Annotated[date | None, Query()] = None,
        end_date: Annotated[date | None, Query()] = None,
        cutoff: Annotated[time, Query()] = config.default_cutoff,
    ) -> dict[str, object]:
        report_end = end_date or london_today()
        report_start = start_date or max(PILOT_START, report_end - timedelta(days=29))
        validate_date_or_422(report_start, latest_offset_days=0)
        validate_date_or_422(report_end, latest_offset_days=0)
        if report_end < report_start:
            raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
        if (report_end - report_start).days > 92:
            raise HTTPException(
                status_code=422,
                detail="Accuracy date ranges cannot exceed 93 days.",
            )
        actuals, forecasts = load_data()
        return accuracy_report(actuals, forecasts, report_start, report_end, cutoff)

    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
        static_root = static_dir.resolve()

        @app.get("/{full_path:path}", include_in_schema=False)
        def frontend(full_path: str) -> FileResponse:
            requested = (static_root / full_path).resolve()
            if full_path and requested.is_relative_to(static_root) and requested.is_file():
                return FileResponse(requested)
            return FileResponse(static_root / "index.html")

    return app


app = create_app()
