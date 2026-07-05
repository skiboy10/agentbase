/** Semantic status variants used across the app */
export type StatusVariant = 'success' | 'warning' | 'info' | 'error' | 'neutral'

/** Returns Tailwind classes for text + background based on status variant */
export function statusClasses(variant: StatusVariant): {
  text: string
  bg: string
  border: string
  badge: string
  dot: string
} {
  switch (variant) {
    case 'success':
      return {
        text: 'text-status-success-foreground',
        bg: 'bg-status-success/15',
        border: 'border-status-success/25',
        badge: 'bg-status-success/15 text-status-success-foreground border border-status-success/25',
        dot: 'bg-status-success',
      }
    case 'warning':
      return {
        text: 'text-status-warning-foreground',
        bg: 'bg-status-warning/15',
        border: 'border-status-warning/25',
        badge: 'bg-status-warning/15 text-status-warning-foreground border border-status-warning/25',
        dot: 'bg-status-warning',
      }
    case 'info':
      return {
        text: 'text-status-info-foreground',
        bg: 'bg-status-info/15',
        border: 'border-status-info/25',
        badge: 'bg-status-info/15 text-status-info-foreground border border-status-info/25',
        dot: 'bg-status-info',
      }
    case 'error':
      return {
        text: 'text-status-error-foreground',
        bg: 'bg-status-error/15',
        border: 'border-status-error/25',
        badge: 'bg-status-error/15 text-status-error-foreground border border-status-error/25',
        dot: 'bg-status-error',
      }
    case 'neutral':
    default:
      return {
        text: 'text-muted-foreground',
        bg: 'bg-muted',
        border: 'border-border',
        badge: 'bg-muted text-muted-foreground border border-border',
        dot: 'bg-muted-foreground/50',
      }
  }
}

/** Map source statuses to semantic variants */
export function sourceStatusVariant(status: string): StatusVariant {
  switch (status) {
    case 'indexed': case 'completed': return 'success'
    case 'indexing': case 'processing': return 'info'
    case 'error': case 'failed': return 'error'
    case 'pending': case 'queued': return 'warning'
    default: return 'neutral'
  }
}

/** Map library statuses to semantic variants */
export function libraryStatusVariant(status: string): StatusVariant {
  switch (status) {
    case 'active': return 'success'
    case 'indexing': return 'info'
    case 'error': return 'error'
    default: return 'neutral'
  }
}

/** Map provider health to semantic variant */
export function providerHealthVariant(healthy: boolean): StatusVariant {
  return healthy ? 'success' : 'error'
}

/**
 * Shared watcher-status → display metadata.
 * Single source of truth used by AutomationRow, SourceCard, and EditSourceDialog.
 *
 * `colorClass` is a composite class string suitable for inline badge/text use
 * (e.g. `text-status-success border-status-success/50`).
 */
export interface WatchStatusMeta {
  variant: StatusVariant
  label: string
  colorClass: string
}

export function watchStatusMeta(status: string | null | undefined): WatchStatusMeta {
  switch (status) {
    case 'running':
      return {
        variant: 'success',
        label: 'Watching',
        colorClass: 'text-status-success border-status-success/50',
      }
    case 'degraded':
      return {
        variant: 'warning',
        label: 'Watching with errors',
        colorClass: 'text-status-warning border-status-warning/50',
      }
    case 'path_missing':
      return {
        variant: 'error',
        label: 'Path not found',
        colorClass: 'text-status-error border-status-error/50',
      }
    case 'error':
      return {
        variant: 'error',
        label: 'Watcher error',
        colorClass: 'text-status-error border-status-error/50',
      }
    case 'stopped':
    default:
      return {
        variant: 'neutral',
        label: 'Watcher stopped',
        colorClass: 'text-muted-foreground border-muted',
      }
  }
}
