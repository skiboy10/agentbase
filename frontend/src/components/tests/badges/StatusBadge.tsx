import { cn } from '@/lib/utils'

interface StatusBadgeProps {
  status: string
  className?: string
}

const statusStyles: Record<string, string> = {
  completed: 'text-status-success bg-status-success/15',
  running: 'text-status-info bg-status-info/15',
  pending: 'text-status-warning bg-status-warning/15',
  failed: 'text-status-error bg-status-error/15',
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const style = statusStyles[status] ?? 'text-muted-foreground bg-muted'

  return (
    <span className={cn('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', style, className)}>
      {status}
    </span>
  )
}
