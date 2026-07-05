import { Button } from '@/components/ui/button'

/**
 * Dismissible error banner for displaying page-level errors
 */
export interface ErrorBannerProps {
  /** Error message to display */
  error: string | null
  /** Callback when user dismisses the error */
  onDismiss: () => void
}

export function ErrorBanner({ error, onDismiss }: ErrorBannerProps) {
  if (!error) return null

  return (
    <div className="mb-4 p-4 bg-destructive/20 border border-destructive rounded-lg text-destructive-foreground">
      {error}
      <Button
        variant="link"
        className="ml-4 text-destructive hover:text-destructive-foreground"
        onClick={onDismiss}
      >
        Dismiss
      </Button>
    </div>
  )
}