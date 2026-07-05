import { Pause, Play, RefreshCw, Settings2, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TableCell, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatTimeAgo } from '@/utils/sourcesFormatters'
import { formatTimeUntil } from '@/lib/automations'
import type { Automation } from '@/lib/automations'
import type { WatcherStatus } from '@/services/api/types/sources'
import { getSourceTypeMeta } from '@/lib/sourceType'
import { AutomationStatusBadge } from './AutomationStatusBadge'

function buildDetail(automation: Automation, watcherStatus?: WatcherStatus | null): string {
  const { kind, status, source } = automation
  if (kind === 'watcher') {
    switch (status) {
      case 'running':
        if (watcherStatus?.last_event_time) return `last event ${formatTimeAgo(watcherStatus.last_event_time).text}`
        return watcherStatus?.started_at ? 'no events yet' : 'watching'
      case 'starting':
        return 'starting…'
      case 'degraded':
        return source.watch_last_error || 'watching with errors'
      case 'path_missing':
        return 'path not found'
      case 'error':
        return source.watch_last_error || 'watcher error'
      case 'paused':
        return source.watch_last_heartbeat_at
          ? `last ran ${formatTimeAgo(source.watch_last_heartbeat_at).text}`
          : 'paused'
      case 'off':
        return 'never enabled'
      default:
        return ''
    }
  }
  // refresh
  switch (status) {
    case 'scheduled':
      return `next refresh ${formatTimeUntil(source.next_refresh_at)}`
    case 'pending':
      return 'next refresh unscheduled'
    case 'refreshing':
      return source.status === 'indexing' ? 'refreshing now' : 'due now'
    case 'paused':
      return source.last_indexed ? `manual · last run ${formatTimeAgo(source.last_indexed).text}` : 'manual'
    default:
      return ''
  }
}

interface AutomationRowProps {
  automation: Automation
  watcherStatus?: WatcherStatus | null
  /** True while a row action (pause/resume/run) is in flight — distinct from the 'pending' AutomationStatus. */
  actionPending: boolean
  onTogglePause: (automation: Automation) => void
  onRunNow: (automation: Automation) => void
  onConfigure: (automation: Automation) => void
}

export function AutomationRow({
  automation,
  watcherStatus,
  actionPending,
  onTogglePause,
  onRunNow,
  onConfigure,
}: AutomationRowProps) {
  const { source, enabled } = automation
  const typeMeta = getSourceTypeMeta(source.source_type)
  const TypeIcon = typeMeta.icon
  const detail = buildDetail(automation, watcherStatus)
  const ToggleIcon = enabled ? Pause : Play
  const toggleLabel = enabled ? 'Pause' : 'Resume'

  return (
    <TableRow>
      <TableCell className="py-3">
        <div className="flex items-center gap-2.5">
          <TypeIcon className="w-4 h-4 text-muted-foreground shrink-0" />
          <div className="min-w-0">
            <div className="font-medium truncate">{source.name}</div>
            <div className="text-xs text-muted-foreground truncate">{source.source_path}</div>
          </div>
        </div>
      </TableCell>
      <TableCell>
        <AutomationStatusBadge automation={automation} />
      </TableCell>
      <TableCell className="text-sm text-muted-foreground truncate">{detail}</TableCell>
      <TableCell>
        <div className="flex items-center justify-end gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                disabled={actionPending}
                onClick={() => onTogglePause(automation)}
                aria-label={toggleLabel}
              >
                {actionPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <ToggleIcon className="w-4 h-4" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{toggleLabel}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                disabled={actionPending}
                onClick={() => onRunNow(automation)}
                aria-label="Run now"
              >
                <RefreshCw className="w-4 h-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Run now</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => onConfigure(automation)}
                aria-label="Configure source"
              >
                <Settings2 className="w-4 h-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Configure source</TooltipContent>
          </Tooltip>
        </div>
      </TableCell>
    </TableRow>
  )
}
