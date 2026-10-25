# WindLens

WindLens is a day-ahead wind forecast intelligence app for a UK electricity buyer. It answers two questions using national wind data from Elexon BMRS only:

1. What wind generation forecast was available at the buyer's decision cutoff for a selected delivery day?
2. How accurate were those cutoff-safe forecasts, and how did error vary by time of day and forecast horizon?

The app keeps the January 2026 challenge pilot and adds a **live-updating view** for current and upcoming delivery days.

**Deployed app:** `https://YOUR-HEROKU-APP.herokuapp.com` (deployment placeholder; see [Heroku deployment](#heroku-deployment)).

> **Decision-support scope:** live means automatic Elexon polling every 15 minutes, not a real-time market feed or a guarantee of source publication latency. WindLens is not a demand forecast, dispatch instruction, or procurement recommendation. It does not include demand, prices, other fuels, or regional data.

## Product at a glance

- **Day-ahead view:** choose a delivery day and decision cutoff, compare the eligible forecast with actual generation, and see forecast energy, peak, minimum, coverage, and a historical uncertainty range.
- **Live Elexon refresh:** the backend refreshes at startup and every 15 minutes, with a manual refresh button, last-success timestamp, and stale/error status.
- **Rolling delivery dates:** January pilot dates remain available alongside recent history and upcoming forecast delivery days.
- **Forecast accuracy:** choose the most recent 30 days or the January pilot; view MAE, RMSE, MAPE, signed bias, P90/P95 absolute error, error through time, error distribution, error by hour, and error by forecast horizon.
- **Cutoff integrity:** a target period uses only the latest forecast published at or before the previous delivery day's cutoff. The default is **09:00 Europe/London**; the UI lets the analyst change it.
- **Cached data:** normalized Elexon data is stored in SQLite. Normal app requests read the local cache and do not call Elexon.
- **API:** FastAPI validation and interactive OpenAPI documentation at `/docs`.

## Verified Elexon data contract

The source documentation was reviewed before implementation:

- [FUELHH stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
- [WINDFOR stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)

The verified data endpoints are:

- `GET https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream`
  - Query parameters: `settlementDateFrom`, `settlementDateTo`, and `fuelType=WIND`.
  - Response: JSON array of records including `startTime`, `publishTime`, `fuelType`, `settlementDate`, and numeric `generation`.
- `GET https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream`
  - Query parameters: `publishDateTimeFrom` and `publishDateTimeTo`.
  - Response: JSON array of records including `startTime`, `publishTime`, and numeric `generation`.

The stream endpoint was queried against historical January 2026 dates to verify these paths, parameter names, payload shapes, and data cadence. `FUELHH` returned 48 half-hourly actual records per settlement day. The queried `WINDFOR` snapshots returned hourly target periods. The analysis therefore performs an **exact `startTime` join**; it does not interpolate an hourly forecast into artificial half-hourly forecasts.

## Analysis methodology and assumptions

### Live refresh and freshness

On startup, the backend bootstraps the previous 35 delivery days, current actuals, and forecast publications covering three upcoming delivery days. Later refreshes run every 15 minutes and re-fetch the latest two days plus the next three days to capture publication changes and revised actuals. The overlapping windows make SQLite upserts idempotent and support the rolling 30-day accuracy view. Cache pruning preserves the January 2026 pilot.

`GET /api/metadata` reports whether the cache is live, delayed, degraded, or still starting; the UI checks this status every 30 seconds. `POST /api/refresh` triggers an on-demand refresh and is rate-limited to one manual request per 30 seconds. Failed upstream refreshes are logged and shown in the UI; the existing cache remains available. The manual refresh button does not bypass Elexon's publication schedule.

The cache retains up to 120 days of rolling source records plus the January 2026 pilot. The delivery-date picker includes upcoming dates only when their configured decision cutoff has passed; the API rejects a not-yet-occurred cutoff rather than presenting an incomplete snapshot as the final decision-time forecast. These cadence and retention settings are demo defaults. A production multi-instance deployment should use shared persistent storage and a single scheduled ingestion worker rather than a separate SQLite database/background loop in every web instance.

### Forecast that was available to the buyer

For each forecast target period on delivery day `D`:

1. Interpret Elexon `publishTime` and `startTime` as timezone-aware UTC timestamps.
2. Convert `startTime` to `Europe/London` to identify delivery day and local hour.
3. Construct the decision timestamp on `D - 1` at the configured cutoff in `Europe/London`.
4. Keep only forecasts with `publishTime <= decision timestamp`.
5. Select the latest eligible publication for each exact `startTime`.
6. Join to actual `FUELHH` wind generation by exact `startTime`.

This rule is also applied to metrics and historical uncertainty calibration. A forecast published after the cutoff can never replace the selected forecast, even if it is present in the cache. The default cutoff is configurable with `DEFAULT_CUTOFF=09:00` and through the UI/API. **09:00 UK time is an explicit pilot assumption, not a claim about the client's actual trading deadline.** Change it to the client's approved deadline before operational use.

### Accuracy and uncertainty

- Error is `forecast MW - actual MW`; positive bias means wind was over-forecast.
- MAE is the mean absolute error; RMSE is the square root of mean squared error; bias is the mean signed error.
- MAPE is mean absolute percentage error over non-zero actual values only. If all actuals are zero, MAPE is reported as unavailable, not as zero.
- The rolling accuracy window can include the current, incomplete delivery day; matched-period counts reflect only exact forecast/actual pairs available so far. Use completed dates for historical comparisons.
- P90/P95 are empirical quantiles of absolute error.
- Horizon is the number of elapsed hours from selected `publishTime` to target `startTime`; the horizon chart groups observations into labeled hour bands.
- Hour-of-day analysis uses the local `Europe/London` hour of the target interval.
- The daily forecast energy estimate sums hourly forecast MW multiplied by the observed one-hour forecast interval. Peak/minimum remain MW.
- The dashboard's shaded range is forecast ± P90 absolute error measured only on earlier delivery days in the local cache (up to the prior 31 days); the lower edge is floored at zero. This is an empirical, retrospective calibration aid, **not** a probability guarantee, confidence interval, or demand-adjusted safe-buy quantity.

### Time zones, missing values, and duplicates

Timestamps are stored in UTC and converted to `Europe/London` for cutoff and presentation. This keeps cutoff logic correct across UK daylight-saving transitions; January 2026 is on GMT. Duplicate actual start times retain the row with the latest `publishTime`. Forecasts are uniquely keyed by `(startTime, publishTime)`, and duplicate records for that key are idempotently upserted. Rows missing a required timestamp or numeric generation are skipped and logged during refresh. Forecast/actual comparisons include exact timestamp matches only; unmatched data is reflected in dashboard coverage and excluded from error metrics.

## Directory and file guide

```text
.
├── backend/
│   ├── app/
│   │   ├── analysis.py       # Cutoff selection, joins, metrics, chart payloads
│   │   ├── config.py         # Environment-driven settings
│   │   ├── data_store.py     # SQLite schema, cache reads, idempotent upserts
│   │   ├── elexon.py         # Verified BMRS requests and response validation
│   │   ├── main.py           # FastAPI routes, live scheduler, OpenAPI, static serving
│   │   ├── refresh_data.py   # Historical cache refresh command
│   │   └── refresh_service.py # Rolling refresh, pruning, and failure reporting
│   ├── data/
│   │   └── wind.sqlite3      # Bundled local analysis cache
│   ├── tests/
│   │   ├── test_analysis.py  # Cutoff, duplicate target, and metric tests
│   │   ├── test_api.py       # FastAPI endpoint and input validation tests
│   │   └── test_refresh.py   # Refresh bootstrap and rolling-window tests
│   ├── Dockerfile            # API container
│   ├── pyproject.toml        # Ruff and pytest configuration
│   └── requirements.txt      # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/       # Reusable charts, cards, controls, load states
│   │   ├── pages/            # Day-ahead dashboard and accuracy analysis
│   │   ├── api.ts            # Typed fetch helper and error handling
│   │   ├── types.ts          # API response types
│   │   └── styles.css        # Responsive application design
│   ├── Dockerfile            # Static Nginx frontend
│   ├── nginx.conf            # SPA fallback and API reverse proxy
│   ├── package.json          # Vite, React, Recharts, ESLint, Prettier
│   └── vite.config.ts        # Local API proxy
├── Dockerfile                # Single-image Heroku deployment
├── docker-compose.yml        # Local multi-container application
├── .env.example              # Non-secret configuration template
├── ARCHITECTURE.md           # Design rationale and data flow
└── DEMO_SCRIPT.md            # Two-part, 10-minute demo outline and script
```

## Run locally

### Option A: Docker Compose (recommended)

Requirements: Docker Desktop with Compose enabled.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open the app at [http://localhost:5173](http://localhost:5173) and the API docs at [http://localhost:8000/docs](http://localhost:8000/docs). The bundled sample cache makes the app usable immediately; the backend then bootstraps recent live data and refreshes every 15 minutes.

Use the app's **Refresh data** button, or trigger a refresh through the API:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/refresh
```

The SQLite file at `backend/data/wind.sqlite3` is mounted as persistent local data, so refreshed records survive container restarts.

### Option B: Run the services directly

In PowerShell, from the project root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

The bundled database should be present at `backend\data\wind.sqlite3`. FastAPI starts the live refresh task automatically. To run the January historical import manually:

```powershell
$env:DATABASE_PATH = "data\wind.sqlite3"
Set-Location backend
python -m app.refresh_data
uvicorn app.main:app --reload
```

In a second PowerShell window:

```powershell
Set-Location frontend
npm ci
npm run dev
```

The Vite server proxies `/api` to `http://127.0.0.1:8000`. `LIVE_REFRESH_ENABLED=false` disables background polling when using an external scheduler or running offline tests.

## Tests, lint, and build

From the project root:

```powershell
Set-Location backend
python -m pip install -r requirements.txt
python -m pip install pytest httpx ruff
python -m pytest
python -m ruff check app tests
Set-Location ..\frontend
npm ci
npm run lint
npm run build
```

The backend tests cover strict cutoff selection (including a forecast after cutoff), London-local day selection, metric calculations and zero-actual MAPE, API validation, rate-limited manual refresh, and the bootstrap-to-incremental refresh window.

## Configuration

Copy `.env.example` to `.env` before running Compose. Settings:

| Variable | Default | Purpose |
|---|---|---|
| `DEFAULT_CUTOFF` | `09:00` | Previous-day decision cutoff in UK local time |
| `DATABASE_PATH` | `backend/data/wind.sqlite3` locally | SQLite cache location |
| `ELEXON_API_BASE` | `https://data.elexon.co.uk/bmrs/api/v1` | BMRS API base URL |
| `DATA_START` | `2025-12-24` | Start date for the historical import command |
| `DATA_END` | `2026-01-31` | End date for the historical import command |
| `LIVE_REFRESH_ENABLED` | `true` | Enable automatic startup and periodic refresh |
| `REFRESH_INTERVAL_SECONDS` | `900` | Automatic Elexon refresh interval (15 minutes) |
| `CACHE_HISTORY_DAYS` | `120` | Rolling source history retained; January pilot is preserved |

No API key or other secret is required for the public data endpoints used by this pilot.

## Heroku deployment

This app is packaged as one Heroku container: the root `Dockerfile` builds the React frontend and serves it from FastAPI alongside the REST API. A Heroku account and Heroku CLI/container registry access are required; deployment is not represented as complete until you run these steps with your account.

1. Install and authenticate the [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli), and install Docker Desktop.
2. From the project root, create a uniquely named app:

   ```powershell
   heroku login
   heroku create YOUR-UNIQUE-WINDLENS-NAME
   heroku container:login
   ```

3. Build and deploy the root container:

   ```powershell
   heroku container:push web -a YOUR-UNIQUE-WINDLENS-NAME
   heroku container:release web -a YOUR-UNIQUE-WINDLENS-NAME
   heroku open -a YOUR-UNIQUE-WINDLENS-NAME
   ```

4. Enable the refresh settings:

   ```powershell
   heroku config:set LIVE_REFRESH_ENABLED=true REFRESH_INTERVAL_SECONDS=900 CACHE_HISTORY_DAYS=120 -a YOUR-UNIQUE-WINDLENS-NAME
   ```

5. Verify `/`, `/docs`, `/api/health`, `/api/metadata`, live delivery dates, and the January 2026 pilot in a private/incognito browser window. Replace the deployed-app placeholder near the top of this README with the public URL.

The image includes the sample SQLite cache for first launch, and one web dyno can poll Elexon while it is running. **Heroku's container filesystem is ephemeral**, so refreshed cache data is not durable across dyno restarts or releases; multiple dynos also do not share the SQLite file and could run duplicate pollers. For a reliable public deployment, attach persistent/shared storage (for example Heroku Postgres), disable per-web-instance background refresh, and run one scheduled ingestion worker. The live status only describes the last successful fetch and does not imply a real-time feed.

## Demo video outline and script

The suggested script and timing for the 5-minute client pitch and 5-minute technical walkthrough are in [DEMO_SCRIPT.md](./DEMO_SCRIPT.md). The project does not create or upload a YouTube video; record the walkthrough, set it to unlisted, then add its URL when submitting.

## AI assistance

Built by Er. Pankaj Kumar with support from AI tools. AI tools assisted with application scaffolding, implementation, documentation, and test development. The endpoint parameters and response formats were independently checked against Elexon documentation and live historical responses, and the analysis logic is covered by tests. A human reviewer should validate operational assumptions and deployment configuration before use.
