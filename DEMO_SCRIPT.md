# 10-minute demo outline and script

Record one continuous video of no more than 10 minutes. Keep the app open in a browser and the repository/terminal ready. Replace the final app URL after deployment; do not claim production readiness or procurement advice.

## Part 1 — Client pitch (0:00–5:00)

### 0:00–0:40 — The decision

> “Day-ahead buyers need a view of wind they could actually have known when the market decision was made. WindLens makes that decision-time information set visible, then puts historical forecast error beside it. This pilot uses national wind data from Elexon BMRS only.”

### 0:40–1:25 — Establish the assumption

Show the delivery-date and cutoff controls.

> “I’ve used 09:00 UK time on the previous day as a configurable pilot assumption. The important control is that the forecast is frozen at this timestamp. Anything published later is excluded, so the chart does not accidentally show hindsight.”

### 1:25–2:35 — Walk the day-ahead view

Select tomorrow's delivery date, point out the live freshness status, forecast, actual, forecast MWh, peak, minimum, and match count.

> “The app checks Elexon every 15 minutes and shows when the last refresh succeeded. For this delivery day, the cerulean line is the latest forecast that had arrived by the decision cutoff, and the neon rose line shows actual generation as Elexon publishes it. The summary gives the scale and number of exact forecast-to-actual matches. The source forecast is hourly and the actuals are half-hourly, so we don't invent half-hour forecasts.”

### 2:35–3:25 — Explain the uncertainty range

Point to the shaded band and its text.

> “The band adds and subtracts the 90th percentile absolute error seen on earlier cached delivery days, with the lower edge floored at zero. It is an empirical planning aid, not a guarantee and not a forecast of customer demand. A buyer can use it as context when considering how much wind to rely on.”

### 3:25–4:35 — Show forecast accuracy

Open Forecast accuracy, show the recent-30-day window and January pilot selector, then explain four metrics, error timeline, distribution, hour-of-day and horizon charts.

> “The accuracy page gives a quantitative view: MAE and RMSE for error size, MAPE with zero actuals excluded, and signed bias to reveal systematic over- or under-forecasting. The lower charts help locate when and at what lead time errors are larger.”

### 4:35–5:00 — Close the client section

> “The pilot gives the team a reproducible forecast snapshot and a transparent view of its limitations. Before an operational rollout, we would confirm the actual trading cutoff and add demand and market context.”

## Part 2 — Technical walkthrough (5:00–10:00)

### 5:00–5:50 — Architecture and source verification

Show `ARCHITECTURE.md`, `backend/app/refresh_service.py`, and `backend/app/elexon.py`.

> “The application has a React/Vite/TypeScript client and a FastAPI backend. A lifespan scheduler refreshes a SQLite cache at startup and every 15 minutes, and the UI can request a rate-limited manual refresh. Actual requests filter WIND by settlement date; forecast history is retrieved by publication-time bounds. Normal chart requests read SQLite, not the live market API.”

### 5:50–6:55 — Cutoff and time-zone safety

Show `backend/app/analysis.py` and the cutoff tests.

> “All source timestamps are parsed as UTC. The decision cutoff is constructed in Europe/London on the preceding date and converted to UTC. Forecasts later than the cutoff are excluded before selecting the latest publication per target. We keep the forecast publication history so a future update cannot overwrite the snapshot needed for historical replay.”

### 6:55–7:50 — Join and metrics

Point out exact `startTime` matching and metric code.

> “The observed forecast records are hourly and actuals half-hourly, so the evaluation uses exact matches only. Error is forecast minus actual; MAPE excludes zero actuals; quantiles are absolute-error percentiles. pandas builds the analysis frames, and the horizon and hour groups use the local target time.”

### 7:50–8:50 — API and tests

Open `/docs`, then show `backend/tests`.

> “FastAPI exposes health, metadata, dashboard, accuracy, and refresh endpoints with rolling date validation and clear cache/data errors. The unit tests cover cutoff leakage, London-local date selection, duplicate target periods, zero-safe MAPE, refresh bootstrap and incremental windows, and API rate limiting.”

### 8:50–9:35 — Containers and deployment

Show `docker-compose.yml`, frontend and backend Dockerfiles, and root `Dockerfile`.

> “Compose starts the API and frontend separately for local development. The root multi-stage Dockerfile compiles the UI and packages it with the API for a single Heroku container. The sample SQLite cache is bundled for first launch; Heroku's filesystem is ephemeral, which is documented as a production persistence limitation.”

### 9:35–10:00 — Handoff and limits

> “The key operational choices to confirm are the true buyer cutoff, forecast coverage expectations, and where the cache should live. The 15-minute polling is not a real-time streaming guarantee. This pilot intentionally excludes demand, prices, and other generation sources. For a multi-dyno deployment, move the cache to shared persistent storage and run a single scheduled ingester.”
