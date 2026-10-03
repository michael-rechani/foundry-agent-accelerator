import { CircleAlert, LoaderCircle, RefreshCw } from 'lucide-react'

export function ChatConfigStatus({
  error,
  onRetry,
}: {
  error: string
  onRetry: () => void
}) {
  return (
    <div className="config-status" role={error ? 'alert' : 'status'}>
      {error ? (
        <CircleAlert size={18} />
      ) : (
        <LoaderCircle size={18} className="spin" />
      )}
      <span>{error || 'Loading workspace configuration...'}</span>
      {error && (
        <button type="button" onClick={onRetry}>
          <RefreshCw size={16} /> Retry
        </button>
      )}
    </div>
  )
}
