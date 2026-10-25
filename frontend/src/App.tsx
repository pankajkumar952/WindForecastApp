import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  LoaderCircle,
  RefreshCw,
  Wind,
} from 'lucide-react'
import { getJson, postJson } from './api'
import Dashboard from './pages/Dashboard'
import Accuracy from './pages/Accuracy'
import type { LiveMetadata, RefreshResponse } from './types'

function elapsed(value: string | null): string {
  if (!value) return 'Waiting for first refresh'
  const seconds = Math.max(
    0,
    Math.floor((Date.now() - Date.parse(value)) / 1000),
  )
  if (seconds < 60) return 'Updated just now'
  if (seconds < 3600) return `Updated ${Math.floor(seconds / 60)}m ago`
  return `Updated ${Math.floor(seconds / 3600)}h ago`
}

export default function App() {
  const [ukNow, setUkNow] = useState(() => new Date())
  const [cutoff, setCutoff] = useState('09:00')
  const [metadata, setMetadata] = useState<LiveMetadata | null>(null)
  const [refreshVersion, setRefreshVersion] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState('')
  const [metadataError, setMetadataError] = useState('')
  const previousRefresh = useRef<string | null>(null)
  const cutoffInitialized = useRef(false)

  useEffect(() => {
    const timer = window.setInterval(() => setUkNow(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const loadMetadata = useCallback(async (signal?: AbortSignal) => {
    const next = await getJson<LiveMetadata>('/metadata', signal)
    if (
      previousRefresh.current &&
      next.last_successful_refresh &&
      next.last_successful_refresh !== previousRefresh.current
    ) {
      setRefreshVersion((version) => version + 1)
    }
    previousRefresh.current = next.last_successful_refresh
    setMetadata(next)
    setMetadataError('')
    if (!cutoffInitialized.current) {
      setCutoff(next.default_cutoff)
      cutoffInitialized.current = true
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void loadMetadata(controller.signal).catch((error: unknown) => {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        setMetadataError(
          error instanceof Error ? error.message : 'API unavailable',
        )
      }
    })
    const timer = window.setInterval(() => {
      void loadMetadata().catch((error: unknown) => {
        setMetadataError(
          error instanceof Error ? error.message : 'API unavailable',
        )
      })
    }, 30_000)
    return () => {
      controller.abort()
      window.clearInterval(timer)
    }
  }, [loadMetadata])

  const refreshNow = async () => {
    setRefreshing(true)
    setRefreshError('')
    try {
      await postJson<RefreshResponse>('/refresh')
      setRefreshVersion((version) => version + 1)
      await loadMetadata()
    } catch (error) {
      setRefreshError(
        error instanceof Error
          ? error.message
          : 'Could not refresh Elexon data',
      )
      await loadMetadata().catch((error: unknown) => {
        setMetadataError(
          error instanceof Error ? error.message : 'API unavailable',
        )
      })
    } finally {
      setRefreshing(false)
    }
  }

  const freshness = metadataError
    ? 'degraded'
    : (metadata?.freshness ?? 'starting')
  const freshnessLabel = metadataError
    ? 'API unavailable'
    : freshness === 'live'
      ? 'Live data'
      : freshness === 'stale'
        ? 'Data delayed'
        : freshness === 'degraded'
          ? 'Refresh issue'
          : freshness === 'not_configured'
            ? 'Refresh disabled'
            : 'Connecting to Elexon'
  const ukDate = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/London',
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(ukNow)
  const ukTime = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/London',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZoneName: 'short',
  }).format(ukNow)

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="WindLens home">
          <span className="brand-mark">
            <Wind size={21} strokeWidth={2.4} />
          </span>
          <span>
            <strong>windlens</strong>
            <small>ENERGY INTELLIGENCE</small>
          </span>
        </a>
        <div className="nav-caption">WORKSPACE</div>
        <nav className="primary-nav" aria-label="Main navigation">
          <NavLink
            to="/"
            end
            aria-label="Day-ahead view"
            className={({ isActive }) => (isActive ? 'active' : '')}
          >
            <Activity size={18} />
            <span>Day-ahead view</span>
          </NavLink>
          <NavLink
            to="/accuracy"
            aria-label="Forecast accuracy"
            className={({ isActive }) => (isActive ? 'active' : '')}
          >
            <BarChart3 size={18} />
            <span>Forecast accuracy</span>
          </NavLink>
        </nav>
        <div className="sidebar-spacer" />
        <div className="source-card">
          <span className={`source-dot freshness-${freshness}`} />
          <div>
            <strong>Elexon BMRS</strong>
            <small>National wind · {freshnessLabel}</small>
          </div>
        </div>
        <div className="sidebar-footer">LIVE WIND · ELEXON BMRS</div>
      </aside>
      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Market intelligence</span>
            <span className="crumb-separator">/</span>
            <strong>Wind generation</strong>
          </div>
          <time className="uk-clock" dateTime={ukNow.toISOString()}>
            <span className="uk-clock-label">UK LOCAL TIME</span>
            <span className="uk-clock-date">{ukDate}</span>
            <span className="uk-clock-time">{ukTime}</span>
          </time>
          <div className="topbar-meta">
            <span
              className={`live-indicator freshness-${freshness}`}
              title={
                metadataError ||
                metadata?.last_refresh_error ||
                elapsed(metadata?.last_successful_refresh ?? null)
              }
            >
              <span /> {freshnessLabel}
            </span>
            <span className="topbar-divider" />
            <span className="freshness-age">
              {elapsed(metadata?.last_successful_refresh ?? null)}
            </span>
            <button
              className="refresh-button"
              onClick={() => void refreshNow()}
              disabled={refreshing}
              title={`Refresh from Elexon now. Automatic refresh every ${Math.round((metadata?.refresh_interval_seconds ?? 900) / 60)} minutes.`}
            >
              {refreshing ? (
                <LoaderCircle size={14} className="spinner" />
              ) : (
                <RefreshCw size={14} />
              )}
              <span>{refreshing ? 'Refreshing…' : 'Refresh data'}</span>
            </button>
          </div>
        </header>
        {(refreshError || metadataError) && (
          <div className="refresh-error" role="alert">
            <span>
              {refreshError ||
                `Could not check data freshness: ${metadataError}`}
            </span>
            <button
              onClick={() => {
                setRefreshError('')
                setMetadataError('')
              }}
              aria-label="Dismiss refresh error"
            >
              ×
            </button>
          </div>
        )}
        <Routes>
          <Route
            path="/"
            element={
              <Dashboard
                cutoff={cutoff}
                onCutoffChange={setCutoff}
                refreshVersion={refreshVersion}
                latestDeliveryDate={metadata?.latest_delivery_date}
                pilotEndDate="2026-01-31"
              />
            }
          />
          <Route
            path="/accuracy"
            element={
              <Accuracy
                cutoff={cutoff}
                onCutoffChange={setCutoff}
                refreshVersion={refreshVersion}
              />
            }
          />
        </Routes>
        <footer className="page-footer">
          <span>WindLens · Day-ahead decision support</span>
          <span>Data: Elexon BMRS · National wind only</span>
          <span>Built by Er. Pankaj Kumar</span>
        </footer>
      </main>
    </div>
  )
}
