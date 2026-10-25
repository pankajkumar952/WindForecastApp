# Architecture

## Overview

WindLens is a small, cache-first full-stack application. React and Recharts present buyer-oriented views; FastAPI provides validated JSON endpoints and OpenAPI docs; pandas performs dataframe joins and grouped error analysis; SQLite stores normalized Elexon records for repeatable, fast reads.

```text
Elexon BMRS streams
        │ startup + scheduled/manual refresh
        ▼
refresh_service.py ──► elexon.py ──► normalize ──► SQLite
                                                       │
                                                       ▼
                                         FastAPI API ─────► refresh metadata
                                              │ JSON              │
                                              └────────┬──────────┘
                                                       ▼
                                      React + TypeScript + Recharts
```

## Key choices

- **Separate source ingestion from request handling.** A FastAPI lifespan task refreshes the cache at startup and every 15 minutes; `POST /api/refresh` supports a rate-limited manual refresh. Dashboard requests never call Elexon directly, so views continue to use the last successful cache when the source is temporarily unavailable.
- **Bootstrap then overlap.** The first live refresh loads 35 recent delivery days for rolling accuracy; later passes re-fetch a two-day overlap plus three forecast days ahead. Idempotent upserts capture revised publications and actuals without repeating a full history download on each cycle.
- **Expose data freshness.** `/api/metadata` and the UI report last success, next scheduled refresh, cache counts, and a degraded state after source failures. The UI polls status every 30 seconds and reloads charts after a successful refresh.
- **Preserve source timestamps and publication history.** Forecast records are keyed by target and publication time, rather than storing only the latest forecast. This is necessary to reconstruct the information set available at a historical cutoff.
- **Make leakage prevention the selection rule.** `analysis.py` converts the previous-day cutoff from `Europe/London` to UTC, discards later publications, and picks the latest remaining publication per exact target. The same selector feeds the dashboard and accuracy results.
- **Do not manufacture forecast observations.** The observed Elexon response cadence is hourly for WINDFOR and half-hourly for FUELHH. Exact timestamp joins make the evaluation transparent; interpolation would change the measured model and is intentionally not applied.
- **Use SQLite as a simple portable cache.** It avoids an additional service for this small historical sample, supports idempotent refreshes, and can be bundled in the local/container pilot. Heroku's filesystem is ephemeral, so durable production refreshes require persistent storage.
- **Use a single deployment image on Heroku.** The root multi-stage Dockerfile compiles React and copies the static build into the FastAPI image. FastAPI serves `/api/*` and `/docs`, and serves the SPA for browser routes. Local Compose still uses separate frontend and API containers.
- **Keep a visible decision assumption.** 09:00 UK time is configurable and shown in the UI. The uncertainty band is based only on previous cached delivery days and is labeled as empirical context, not a risk guarantee.

## API

- `GET /api/health` — application and cache row counts.
- `GET /api/metadata` — timezone, supported dates, default cutoff, cache counts, and refresh status.
- `POST /api/refresh` — manually fetch Elexon data; limited to one manual request per 30 seconds.
- `GET /api/dashboard/{delivery_date}?cutoff=09:00` — selected forecast, exact-match actuals, energy summary, and prior-error P90 range.
- `GET /api/accuracy?start_date=2026-10-01&end_date=2026-10-25&cutoff=09:00` — rolling metrics and chart series; the January pilot remains available.
- `GET /docs` — interactive Swagger UI.

Dates start at 1 January 2026 (the pilot) and extend through current/upcoming delivery days. Accuracy windows are limited to 93 days. Invalid input returns a clear 422 response; an empty cache returns 503 with refresh instructions, and a day without an eligible forecast returns 404.

## Analysis data flow

1. Fetch actuals with the documented FUELHH settlement-date range and `fuelType=WIND`.
2. Fetch forecast publication history over a rolling publication-time window, preserving the publication rows needed to reconstruct each decision cutoff.
3. Parse timestamps as aware UTC, skip malformed required fields with a log warning, and upsert records into SQLite.
4. For each delivery day, derive the London-local cutoff and select one latest eligible forecast per target `startTime`.
5. Join selected forecasts to actuals on exact UTC `startTime`; compute signed error, percentage error only when actual is non-zero, quantiles, horizon buckets, and London-local hourly summaries.
6. Return typed-by-convention JSON payloads to the UI; frontend components own loading, error, formatting, and chart rendering.

## Limits and next steps

This is an analysis pilot rather than a production trading control. It has no demand/price inputs or authentication. The included SQLite scheduler is suitable for one local process or a single demo dyno only. Heroku's local filesystem is ephemeral and SQLite is not shared across dynos; production deployment needs persistent shared storage (for example Postgres), a separate single scheduled ingester, operational monitoring, and a confirmed business decision deadline.
