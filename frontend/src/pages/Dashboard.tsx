import { useCallback, useEffect, useState } from 'react'
import { Info, Wind } from 'lucide-react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { cutoffQuery, getJson } from '../api'
import ChartPanel from '../components/ChartPanel'
import CutoffControl from '../components/CutoffControl'
import { ErrorState, LoadingState } from '../components/LoadState'
import PageHeading from '../components/PageHeading'
import type { DashboardResponse } from '../types'

function londonToday() {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/London',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${value.year}-${value.month}-${value.day}`
}

function shiftDate(value: string, days: number) {
  const date = new Date(`${value}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

function optionsBetween(start: string, end: string) {
  const options = []
  for (let value = start; value <= end; value = shiftDate(value, 1)) {
    options.push({
      value,
      label: new Date(`${value}T12:00:00Z`).toLocaleDateString('en-GB', {
        timeZone: 'UTC',
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        year: value.slice(0, 4) === '2026' ? undefined : 'numeric',
      }),
    })
  }
  return options
}

function dateOptions(latestDeliveryDate?: string) {
  const today = londonToday()
  const recentStart = [shiftDate(today, -120), '2026-02-01'].reduce((a, b) =>
    a > b ? a : b,
  )
  const latest = latestDeliveryDate ?? today
  return {
    pilot: optionsBetween('2026-01-01', '2026-01-31'),
    live: optionsBetween(recentStart, latest),
  }
}

function number(value: number | null, digits = 0) {
  return value === null
    ? '—'
    : new Intl.NumberFormat('en-GB', { maximumFractionDigits: digits }).format(
        value,
      )
}

export default function Dashboard({
  cutoff,
  onCutoffChange,
  refreshVersion,
  latestDeliveryDate,
  pilotEndDate,
}: {
  cutoff: string
  onCutoffChange: (value: string) => void
  refreshVersion: number
  latestDeliveryDate?: string
  pilotEndDate: string
}) {
  const [selectedDate, setSelectedDate] = useState(londonToday)
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)

  const load = useCallback(
    (signal: AbortSignal) => {
      setLoading(true)
      setError('')
      getJson<DashboardResponse>(
        `/dashboard/${selectedDate}?${cutoffQuery(cutoff)}`,
        signal,
      )
        .then((response) => {
          if (!signal.aborted) setData(response)
        })
        .catch((reason: unknown) => {
          if (signal.aborted) return
          setError(
            reason instanceof Error ? reason.message : 'Unexpected API error',
          )
        })
        .finally(() => {
          if (!signal.aborted) setLoading(false)
        })
    },
    [cutoff, selectedDate],
  )

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load, refreshVersion, revision])

  useEffect(() => {
    if (latestDeliveryDate) setSelectedDate(latestDeliveryDate)
  }, [latestDeliveryDate])

  const chartData =
    data?.series.map((point) => ({
      ...point,
      uncertainty_width:
        point.upper_mw !== null && point.lower_mw !== null
          ? point.upper_mw - point.lower_mw
          : null,
    })) ?? []

  return (
    <div className="page-content">
      <PageHeading
        eyebrow="LIVE MARKET VIEW · UK NATIONAL WIND"
        title="Know your wind position."
        description="Live Elexon generation data and the forecast available before the day-ahead decision."
        actions={
          <div className="control-row">
            <label className="control-field date-control">
              <span>Delivery date</span>
              <select
                value={selectedDate}
                onChange={(event) => setSelectedDate(event.target.value)}
              >
                <optgroup label="January 2026 pilot">
                  {optionsBetween('2026-01-01', pilotEndDate).map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Recent and upcoming delivery days">
                  {dateOptions(latestDeliveryDate).live.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </optgroup>
              </select>
            </label>
            <CutoffControl value={cutoff} onChange={onCutoffChange} />
          </div>
        }
      />

      <div className="assumption-banner">
        <Info size={17} />
        <span>
          Forecast snapshot is frozen at <strong>{cutoff} UK time</strong> on
          the previous day. Later publications are excluded to prevent hindsight
          bias. Live actuals appear as Elexon publishes them.
        </span>
      </div>

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState
          message={error}
          onRetry={() => setRevision((value) => value + 1)}
        />
      ) : data ? (
        <>
          <section className="summary-grid">
            <article className="summary-card summary-primary">
              <div className="summary-card-top">
                <span className="summary-icon">
                  <Wind size={18} />
                </span>
                <span className="summary-label">Forecast energy</span>
              </div>
              <div className="summary-number">
                {number(data.summary.forecast_mwh, 0)}
                <small>MWh</small>
              </div>
              <span className="summary-note">
                Across forecast hourly intervals
              </span>
            </article>
            <article className="summary-card">
              <span className="summary-label">Peak forecast</span>
              <div className="summary-number">
                {number(data.summary.peak_mw)}
                <small>MW</small>
              </div>
              <span className="summary-note">Highest expected wind output</span>
            </article>
            <article className="summary-card">
              <span className="summary-label">Minimum forecast</span>
              <div className="summary-number">
                {number(data.summary.minimum_mw)}
                <small>MW</small>
              </div>
              <span className="summary-note">Lowest expected wind output</span>
            </article>
            <article className="summary-card">
              <span className="summary-label">Matched intervals</span>
              <div className="summary-number">
                {data.summary.matched_actual_intervals}
                <small> / {data.summary.forecast_intervals}</small>
              </div>
              <span className="summary-note">
                Forecast periods with actuals
              </span>
            </article>
          </section>

          <ChartPanel
            title="Forecast available at decision time"
            subtitle={`${new Date(
              `${data.delivery_date}T12:00:00`,
            ).toLocaleDateString('en-GB', {
              weekday: 'long',
              day: 'numeric',
              month: 'long',
              year: 'numeric',
            })} · ${data.summary.forecast_intervals} forecast periods`}
            className="main-chart-panel"
          >
            <div className="chart-legend">
              <span>
                <i className="legend-swatch forecast-swatch" />
                Forecast
              </span>
              <span>
                <i className="legend-swatch actual-swatch" />
                Actual
              </span>
              {data.summary.uncertainty_p90_mw !== null && (
                <span>
                  <i className="legend-swatch band-swatch" />
                  Historical P90 band
                </span>
              )}
            </div>
            <div className="chart-wrap chart-large">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={chartData}
                  margin={{ top: 12, right: 18, left: 4, bottom: 4 }}
                >
                  <CartesianGrid stroke="#26364a" vertical={false} />
                  <XAxis
                    dataKey="time_label"
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: '#9aafc3', fontSize: 11 }}
                    interval={3}
                  />
                  <YAxis
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: '#9aafc3', fontSize: 11 }}
                    tickFormatter={(value: number) =>
                      `${Math.round(value / 1000)}k`
                    }
                    width={43}
                  />
                  <Tooltip
                    labelFormatter={(label) => `${label} UK`}
                    formatter={(value, name) => [
                      value === null
                        ? 'No matched reading'
                        : `${number(Number(value))} MW`,
                      name === 'forecast_mw'
                        ? 'Forecast'
                        : name === 'actual_mw'
                          ? 'Actual'
                          : name,
                    ]}
                    contentStyle={{
                      borderRadius: 12,
                      border: '1px solid #30465e',
                      backgroundColor: '#111c29',
                      color: '#e8f4ff',
                      boxShadow: '0 8px 24px #00000040',
                    }}
                  />
                  <Area
                    dataKey="lower_mw"
                    stackId="uncertainty"
                    stroke="none"
                    fill="#00bfff"
                    fillOpacity={0}
                    isAnimationActive={false}
                  />
                  <Area
                    dataKey="uncertainty_width"
                    stackId="uncertainty"
                    stroke="none"
                    fill="#00bfff"
                    fillOpacity={0.2}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="forecast_mw"
                    name="forecast_mw"
                    stroke="#00bfff"
                    strokeWidth={2.8}
                    dot={false}
                    activeDot={{
                      r: 5,
                      fill: '#00bfff',
                      stroke: '#07111d',
                      strokeWidth: 2,
                    }}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="actual_mw"
                    name="actual_mw"
                    stroke="#ff3b91"
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                    activeDot={{
                      r: 5,
                      fill: '#ff3b91',
                      stroke: '#07111d',
                      strokeWidth: 2,
                    }}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className="chart-footnote">
              Elexon forecasts are hourly; actuals are half-hourly. Only exact
              `startTime` matches are compared—no interpolation is applied.
            </div>
          </ChartPanel>

          <div className="insight-row">
            <div className="insight-icon">
              <Info size={18} />
            </div>
            <div>
              <strong>
                {data.summary.uncertainty_p90_mw === null
                  ? 'Historical uncertainty is not available yet'
                  : `Wind planning range: forecast ± ${number(data.summary.uncertainty_p90_mw)} MW`}
              </strong>
              <p>
                {data.summary.uncertainty_p90_mw === null
                  ? 'There are no earlier matched days in the local cache to estimate a historical error range.'
                  : `The shaded range is based on the 90th percentile of absolute errors from ${data.summary.uncertainty_sample_count} matched intervals on earlier delivery days. It is a retrospective calibration aid, not a probability guarantee or a demand forecast.`}
              </p>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}
