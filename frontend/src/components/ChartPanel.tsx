import type { ReactNode } from 'react'

export default function ChartPanel({
  title,
  subtitle,
  children,
  className = '',
}: {
  title: string
  subtitle: string
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`chart-panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
      </div>
      {children}
    </section>
  )
}
