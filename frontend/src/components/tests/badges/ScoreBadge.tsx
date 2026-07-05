import { cn } from '@/lib/utils'

interface ScoreBadgeProps {
  score: number | null | undefined
  className?: string
}

export function ScoreBadge({ score, className }: ScoreBadgeProps) {
  if (score === null || score === undefined) {
    return <span className={cn('text-xs text-muted-foreground', className)}>-</span>
  }

  const color =
    score >= 80 ? 'text-status-success bg-status-success/15' :
    score >= 50 ? 'text-status-warning bg-status-warning/15' :
    'text-status-error bg-status-error/15'

  return (
    <span className={cn('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', color, className)}>
      {Math.round(score)}
    </span>
  )
}
