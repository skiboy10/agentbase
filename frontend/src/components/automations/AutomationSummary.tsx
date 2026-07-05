import { cn } from '@/lib/utils'
import type { AutomationSummary as Summary } from '@/lib/automations'

export function AutomationSummary({ summary }: { summary: Summary }) {
  const items: { label: string; value: number; dot: string }[] = [
    { label: 'running', value: summary.running, dot: 'bg-status-success' },
    { label: 'paused', value: summary.paused, dot: 'bg-muted-foreground/50' },
    { label: 'need attention', value: summary.needsAttention, dot: 'bg-status-error' },
  ]
  return (
    <div className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-lg border border-border bg-card px-5 py-3.5 mb-6">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-2">
          <span className={cn('h-2 w-2 rounded-full', item.dot)} />
          <span className="text-lg font-semibold tabular-nums leading-none">{item.value}</span>
          <span className="text-sm text-muted-foreground">{item.label}</span>
        </div>
      ))}
    </div>
  )
}
