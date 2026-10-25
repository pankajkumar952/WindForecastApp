export type MetricSet = {
  sample_count: number
  mae: number | null
  rmse: number | null
  mape: number | null
  bias: number | null
  p90_absolute_error: number | null
  p95_absolute_error: number | null
}

export type DashboardPoint = {
  start_time: string
  time_label: string
  forecast_mw: number
  actual_mw: number | null
  publish_time: string
  lower_mw: number | null
  upper_mw: number | null
}

export type DashboardResponse = {
  delivery_date: string
  timezone: string
  decision_cutoff: string
  summary: {
    forecast_mwh: number | null
    peak_mw: number | null
    minimum_mw: number | null
    forecast_intervals: number
    matched_actual_intervals: number
    missing_actual_intervals: number
    uncertainty_p90_mw: number | null
    uncertainty_sample_count: number
  }
  series: DashboardPoint[]
}

export type AccuracyPoint = {
  start_time: string
  time_label: string
  error_mw: number
  forecast_mw: number
  actual_mw: number
  horizon_hours: number
}

export type AccuracyResponse = {
  start_date: string
  end_date: string
  timezone: string
  decision_cutoff: string
  metrics: MetricSet
  daily_coverage: Array<{ date: string; matched_intervals: number }>
  error_timeline: AccuracyPoint[]
  histogram: Array<{ bin_start: number; bin_end: number; count: number }>
  by_hour: Array<{
    hour: number
    label: string
    mae_mw: number
    bias_mw: number
    sample_count: number
  }>
  by_horizon: Array<{
    horizon: string
    mae_mw: number
    bias_mw: number
    sample_count: number
  }>
}

export type LiveMetadata = {
  timezone: string
  default_cutoff: string
  analysis_start: string
  analysis_end: string
  latest_delivery_date: string
  source: string
  refresh_interval_seconds: number
  refresh_enabled: boolean
  freshness: 'live' | 'stale' | 'degraded' | 'starting' | 'not_configured'
  last_refresh_attempt: string | null
  last_successful_refresh: string | null
  next_refresh: string | null
  last_refresh_error: string | null
  last_refresh_actual_rows: number
  last_refresh_forecast_rows: number
  cache: { actuals: number; forecasts: number }
}

export type RefreshResponse = {
  status: string
  completed_at: string
  actual_rows: number
  forecast_rows: number
  delivery_window: { start: string; end: string }
}
