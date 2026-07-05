import type { LucideIcon } from 'lucide-react'
import { Table, TableBody, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { Automation } from '@/lib/automations'
import type { WatcherStatus } from '@/services/api/types/sources'
import { AutomationRow } from './AutomationRow'

interface AutomationsTableProps {
  title: string
  icon: LucideIcon
  automations: Automation[]
  watcherStatuses: Record<string, WatcherStatus | null>
  pendingIds: Set<string>
  onTogglePause: (automation: Automation) => void
  onRunNow: (automation: Automation) => void
  onConfigure: (automation: Automation) => void
}

export function AutomationsTable({
  title,
  icon: Icon,
  automations,
  watcherStatuses,
  pendingIds,
  onTogglePause,
  onRunNow,
  onConfigure,
}: AutomationsTableProps) {
  if (automations.length === 0) return null

  return (
    <section className="mb-8">
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-4 h-4 text-muted-foreground" />
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</h2>
        <span className="text-xs text-muted-foreground">({automations.length})</span>
      </div>
      <div className="rounded-lg border border-border overflow-hidden">
        <Table className="table-fixed">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[44%]">Source</TableHead>
              <TableHead className="w-40">Status</TableHead>
              <TableHead className="w-48">Detail</TableHead>
              <TableHead className="w-24 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {automations.map((automation) => (
              <AutomationRow
                key={automation.id}
                automation={automation}
                watcherStatus={watcherStatuses[automation.source.id]}
                actionPending={pendingIds.has(automation.id)}
                onTogglePause={onTogglePause}
                onRunNow={onRunNow}
                onConfigure={onConfigure}
              />
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  )
}
