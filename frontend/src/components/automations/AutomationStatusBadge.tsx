import { cn } from '@/lib/utils'
import { statusClasses } from '@/lib/status'
import type { Automation } from '@/lib/automations'

// Live automations get a pulsing dot to read as "actively doing something".
const PULSE_STATUSES = new Set(['running', 'refreshing'])

export function AutomationStatusBadge({ automation }: { automation: Automation }) {
  const classes = statusClasses(automation.variant)
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap',
        classes.badge,
      )}
    >
      <span
        className={cn(
          'h-1.5 w-1.5 rounded-full',
          classes.dot,
          PULSE_STATUSES.has(automation.status) && 'animate-pulse',
        )}
      />
      {automation.statusLabel}
    </span>
  )
}
