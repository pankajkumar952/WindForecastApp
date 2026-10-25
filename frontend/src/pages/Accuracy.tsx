import { useCallback, useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { cutoffQuery, getJson } from '../api'
import ChartPanel from '../components/ChartPanel'
import CutoffControl from '../components/CutoffControl'
import { ErrorState, LoadingState } from '../components/LoadState'
import MetricCard from '../components/MetricCard'
import PageHeading from '../components/PageHeading'
import type { AccuracyResponse } from '../types'

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

function last30DayStart() {
  const start = shiftDate(londonToday(), -29)
  return start < '2026-01-01' ? '2026-01-01' : start
}

function format(value: number | null, digits = 0) {
  return value === null
    ? '—'
    : new Intl.NumberFormat('en-GB', { maximumFractionDigits: digits }).format(
        value,
      )
}

export default function Accuracy({
  cutoff,
  onCutoffChange,
  refreshVersion,
}: {
  cutoff: string
  onCutoffChange: (value: string) => void
  refreshVersion: number
}) {
  const [startDate, setStartDate] = useState(last30DayStart)
  const [endDate, setEndDate] = useState(londonToday)
  const [data, setData] = useState<AccuracyResponse | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)

  const load = useCallback(
    (signal: AbortSignal) => {
      setLoading(true)
      setError('')
      getJson<AccuracyResponse>(
        `/accuracy?start_date=${startDate}&end_date=${endDate}&${cutoffQuery(cutoff)}`,
        signal,
      )
        .then(setData)
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === 'AbortError')
            return
          setError(
            reason instanceof Error ? reason.message : 'Unexpected API error',
          )
        })
        .finally(() => setLoading(false))
    },
    [cutoff, endDate, startDate],
  )

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load, refreshVersion, revision])

  const histogram =
    data?.histogram.map((bin) => ({
      ...bin,
      label: `${format(bin.bin_start / 1000, 0)}–${format(bin.bin_end / 1000, 0)}`,
    })) ?? []

  return (
    <div className="page-content">
      <PageHeading
        eyebrow={`FORECAST PERFORMANCE · ${startDate} TO ${endDate}`}
        title="Measure the forecast error."
        description="See how decision-time wind forecasts compared with realized output—and where errors concentrate."
        actions={
          <div className="accuracy-controls">
            <label className="control-field">
              <span>From</span>
              <input
                className="date-input"
                type="date"
                min="2026-01-01"
                max={endDate}
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
              />
            </label>
            <label className="control-field">
              <span>To</span>
              <input
                className="date-input"
                type="date"
                min={startDate}
                max={londonToday()}
                value={endDate}
                onChange={(event) => setEndDate(event.target.value)}
              />
            </label>
            <CutoffControl value={cutoff} onChange={onCutoffChange} />
          </div>
        }
      />
      <div className="assumption-banner">
        <span className="banner-spark">↗</span>
        <span>
          <span className="range-presets">
            <button
              className="preset-button"
              onClick={() => {
                setStartDate(last30DayStart())
                setEndDate(londonToday())
              }}
            >
              Recent 30 days
            </button>
            <button
              className="preset-button"
              onClick={() => {
                setStartDate('2026-01-01')
                setEndDate('2026-01-31')
              }}
            >
              January pilot
            </button>
          </span>
          All metrics use the latest forecast published by{' '}
          <strong>{cutoff} UK time</strong> on each delivery day’s predecessor.
          Error is forecast minus actual; positive bias means wind was
          over-forecast. The current delivery day may be partial; matched-period
          counts reflect actuals available so far.
        </span>
      </div>
      {loading ? (
        <LoadingState label="Calculating forecast accuracy…" />
      ) : error ? (
        <ErrorState
          message={error}
          onRetry={() => setRevision((value) => value + 1)}
        />
      ) : data ? (
        <>
          <section className="metric-grid">
            <MetricCard
              label="Mean absolute error"
              value={format(data.metrics.mae)}
              unit="MW"
              detail={`${data.metrics.sample_count.toLocaleString('en-GB')} matched periods`}
              tooltip="Average size of the forecast miss, without regard to whether the forecast was high or low."
            />
            <MetricCard
              label="Root mean square error"
              value={format(data.metrics.rmse)}
              unit="MW"
              detail="Penalizes larger misses more"
              tooltip="Square root of the mean squared forecast error. Larger errors have more influence than in MAE."
            />
            <MetricCard
              label="Mean absolute percentage error"
              value={format(data.metrics.mape, 1)}
              unit="%"
              detail="Zero actuals excluded"
              tooltip="Mean absolute error divided by absolute actual output, expressed as a percentage. Zero actual values are excluded because percentage error is undefined there."
            />
            <MetricCard
              label="Forecast bias"
              value={format(data.metrics.bias)}
              unit="MW"
              detail={
                data.metrics.bias === null
                  ? 'Not available'
                  : data.metrics.bias > 0
                    ? 'Over-forecast on average'
                    : data.metrics.bias < 0
                      ? 'Under-forecast on average'
                      : 'No average bias'
              }
              tooltip="Mean signed error (forecast − actual). Positive indicates over-forecast; negative indicates under-forecast."
            />
          </section>
          <div className="metric-footline">
            Absolute error P90:{' '}
            <strong>{format(data.metrics.p90_absolute_error)} MW</strong>
            <span>·</span>
            P95: <strong>{format(data.metrics.p95_absolute_error)} MW</strong>
            <span>·</span>
            <strong>{data.metrics.sample_count}</strong> hourly exact matches
          </div>

          <ChartPanel
            title="Forecast error over time"
            subtitle="Each point is one exact forecast-to-actual match · zero is a perfect forecast"
            className="wide-chart-panel"
          >
            <div className="chart-wrap chart-medium">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={data.error_timeline}
                  margin={{ top: 12, right: 16, left: 4, bottom: 4 }}
                >
                  <CartesianGrid stroke="#26364a" vertical={false} />
                  <XAxis
                    dataKey="time_label"
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: '#9aafc3', fontSize: 10 }}
                    interval={47}
                  />
                  <YAxis
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: '#9aafc3', fontSize: 11 }}
                    tickFormatter={(value: number) =>
                      `${format(value / 1000)}k`
                    }
                    width={44}
                  />
                  <ReferenceLine y={0} stroke="#60748a" strokeDasharray="4 4" />
                  <Tooltip
                    labelFormatter={(label) => `${label} UK`}
                    formatter={(value, name) => [
                      `${format(Number(value))} MW`,
                      name === 'error_mw' ? 'Forecast error' : String(name),
                    ]}
                    contentStyle={{
                      borderRadius: 12,
                      border: '1px solid #30465e',
                      backgroundColor: '#111c29',
                      color: '#e8f4ff',
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="error_mw"
                    stroke="#00bfff"
                    strokeWidth={1.6}
                    dot={false}
                    activeDot={{ r: 4 }}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </ChartPanel>

          <div className="chart-grid">
            <ChartPanel
              title="Error distribution"
              subtitle="How often forecast errors fell within each MW band"
            >
              <div className="chart-wrap chart-small">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={histogram}
                    margin={{ top: 12, right: 8, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid stroke="#26364a" vertical={false} />
                    <XAxis
                      dataKey="label"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: '#9aafc3', fontSize: 9 }}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: '#9aafc3', fontSize: 10 }}
                      width={28}
                    />
                    <Tooltip
                      formatter={(value) => [value, 'Intervals']}
                      labelFormatter={(label) => `${label} MW`}
                      contentStyle={{
                        borderRadius: 12,
                        border: '1px solid #30465e',
                        backgroundColor: '#111c29',
                        color: '#e8f4ff',
                      }}
                    />
                    <Bar dataKey="count" fill="#00bfff" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartPanel>
            <ChartPanel
              title="Error by hour of day"
              subtitle="Mean absolute error in UK local time"
            >
              <div className="chart-wrap chart-small">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart
                    data={data.by_hour}
                    margin={{ top: 12, right: 8, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid stroke="#26364a" vertical={false} />
                    <XAxis
                      dataKey="label"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: '#9aafc3', fontSize: 9 }}
                      interval={3}
                    />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: '#9aafc3', fontSize: 10 }}
                      width={34}
                    />
                    <Tooltip
                      formatter={(value) => [
                        `${format(Number(value))} MW`,
                        'MAE',
                      ]}
                      labelFormatter={(label) => `${label} UK`}
                      contentStyle={{
                        borderRadius: 12,
                        border: '1px solid #30465e',
                        backgroundColor: '#111c29',
                        color: '#e8f4ff',
                      }}
                    />
                    <Bar
                      dataKey="mae_mw"
                      fill="#00bfff80"
                      radius={[3, 3, 0, 0]}
                    />
                    <Line
                      dataKey="bias_mw"
                      stroke="#ff3b91"
                      strokeWidth={2}
                      dot={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </ChartPanel>
            <ChartPanel
              title="Error by forecast horizon"
              subtitle="Lead time from publication to target period"
              className="horizon-panel"
            >
              <div className="chart-wrap chart-small">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart
                    data={data.by_horizon}
                    margin={{ top: 12, right: 12, left: 2, bottom: 0 }}
                  >
                    <CartesianGrid stroke="#26364a" vertical={false} />
                    <XAxis
                      dataKey="horizon"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: '#9aafc3', fontSize: 10 }}
                    />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: '#9aafc3', fontSize: 10 }}
                      width={36}
                    />
                    <Tooltip
                      formatter={(value) => [
                        `${format(Number(value))} MW`,
                        'MAE',
                      ]}
                      contentStyle={{
                        borderRadius: 12,
                        border: '1px solid #30465e',
                        backgroundColor: '#111c29',
                        color: '#e8f4ff',
                      }}
                    />
                    <Bar
                      dataKey="mae_mw"
                      fill="#00bfff"
                      radius={[4, 4, 0, 0]}
                    />
                    <Line
                      dataKey="bias_mw"
                      stroke="#ff3b91"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </ChartPanel>
          </div>
          <div className="insight-row accuracy-note">
            <span className="insight-icon">i</span>
            <div>
              <strong>Read the diagnostics in context</strong>
              <p>
                Elexon provides hourly WINDFOR values and half-hourly FUELHH
                actuals. This evaluation uses exact timestamp matches only;
                errors are shown in MW and the reported energy/interval counts
                do not imply a demand forecast or a procurement recommendation.
              </p>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}
