import { Clock3 } from 'lucide-react'

export default function CutoffControl({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="control-field cutoff-control">
      <span>Decision cutoff</span>
      <span className="input-with-icon">
        <Clock3 size={16} />
        <input
          type="time"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-label="Decision cutoff in UK local time"
        />
      </span>
      <small>UK time, previous day</small>
    </label>
  )
}
