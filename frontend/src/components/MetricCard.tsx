import { Info } from 'lucide-react'

export default function MetricCard({
  label,
  value,
  unit,
  detail,
  tooltip,
}: {
  label: string
  value: string
  unit: string
  detail: string
  tooltip: string
}) {
  return (
    <article className="metric-card">
      <div className="metric-label">
        <span>{label}</span>
        <span className="tooltip-anchor" tabIndex={0} aria-label={tooltip}>
          <Info size={15} />
          <span className="tooltip-content" role="tooltip">
            {tooltip}
          </span>
        </span>
      </div>
      <div className="metric-value">
        {value}
        <span>{unit}</span>
      </div>
      <div className="metric-detail">{detail}</div>
    </article>
  )
}
