import { AlertCircle, LoaderCircle } from 'lucide-react'

export function LoadingState({
  label = 'Loading cached analysis…',
}: {
  label?: string
}) {
  return (
    <div className="state-card" role="status">
      <LoaderCircle className="spinner" size={22} />
      <span>{label}</span>
    </div>
  )
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <div className="state-card error-state" role="alert">
      <AlertCircle size={22} />
      <div>
        <strong>We couldn’t load this view</strong>
        <p>{message}</p>
        <button className="text-button" onClick={onRetry}>
          Try again
        </button>
      </div>
    </div>
  )
}
