import { useState, useEffect, useCallback } from 'react'
import {
  FilePlus,
  FileEdit,
  FileX,
  Play,
  Square,
  RefreshCw,
  AlertTriangle,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Loader2,
} from 'lucide-react'
import { sourcesApi } from '../../services/api'
import type { WatcherEvent } from '../../services/api/types/sources'
import { formatTimeAgo } from '../../utils/sourcesFormatters'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '../../lib/utils'

interface WatcherActivityDrawerProps {
  sourceId: string
  // When viewing a sub-source, pass the parent root's id so the drawer can
  // display the activity that drives this view (sub-sources don't own a
  // watcher of their own).
  parentSourceId?: string | null
}

function eventIcon(eventType: string) {
  switch (eventType) {
    case 'created': return <FilePlus className="w-3 h-3 shrink-0" />
    case 'modified': return <FileEdit className="w-3 h-3 shrink-0" />
    case 'deleted': return <FileX className="w-3 h-3 shrink-0" />
    case 'started': return <Play className="w-3 h-3 shrink-0" />
    case 'stopped': return <Square className="w-3 h-3 shrink-0" />
    case 'recovery': return <RefreshCw className="w-3 h-3 shrink-0" />
    case 'error': return <AlertTriangle className="w-3 h-3 shrink-0" />
    case 'degraded': return <AlertCircle className="w-3 h-3 shrink-0" />
    default: return <AlertCircle className="w-3 h-3 shrink-0" />
  }
}

function severityColor(severity: string): string {
  switch (severity) {
    case 'error': return 'text-red-400'
    case 'warn': return 'text-amber-400'
    default: return 'text-muted-foreground'
  }
}

function truncatePath(path: string | null, maxLen = 48): string {
  if (!path) return ''
  if (path.length <= maxLen) return path
  return '…' + path.slice(-(maxLen - 1))
}

export default function WatcherActivityDrawer({ sourceId, parentSourceId }: WatcherActivityDrawerProps) {
  const [open, setOpen] = useState(false)
  const [events, setEvents] = useState<WatcherEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const PAGE_SIZE = 20
  // Sub-sources don't own a watcher; aggregate the parent root's activity.
  const effectiveSourceId = parentSourceId ?? sourceId

  const fetchEvents = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await sourcesApi.listWatcherEvents(effectiveSourceId, { limit: PAGE_SIZE })
      setEvents(data)
      setHasMore(data.length === PAGE_SIZE)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load events')
    } finally {
      setLoading(false)
    }
  }, [effectiveSourceId])

  useEffect(() => {
    if (open) fetchEvents()
  }, [open, fetchEvents])

  const loadMore = async () => {
    if (events.length === 0) return
    const oldest = events[events.length - 1]
    setLoadingMore(true)
    try {
      const data = await sourcesApi.listWatcherEvents(effectiveSourceId, {
        limit: PAGE_SIZE,
        before: oldest.timestamp,
      })
      setEvents((prev) => [...prev, ...data])
      setHasMore(data.length === PAGE_SIZE)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more events')
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors py-1">
          {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          Recent Activity
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-2 border rounded-md overflow-hidden">
          {loading && (
            <div className="flex items-center justify-center py-4 text-xs text-muted-foreground gap-2">
              <Loader2 className="w-3 h-3 animate-spin" />
              Loading events…
            </div>
          )}
          {!loading && error && (
            <p className="text-xs text-red-400 p-3">{error}</p>
          )}
          {!loading && !error && events.length === 0 && (
            <p className="text-xs text-muted-foreground p-3 italic">No recent activity.</p>
          )}
          {!loading && events.length > 0 && (
            <div className="divide-y divide-border">
              {events.map((evt) => (
                <div key={evt.id} className="flex items-start gap-2 px-3 py-2">
                  <span className={cn('mt-0.5', severityColor(evt.severity))}>
                    {eventIcon(evt.event_type)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className={cn('text-xs font-medium capitalize', severityColor(evt.severity))}>
                        {evt.event_type}
                      </span>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {formatTimeAgo(evt.timestamp).text}
                      </span>
                    </div>
                    {evt.file_path && (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <p className="text-xs text-muted-foreground font-mono truncate cursor-default">
                              {truncatePath(evt.file_path)}
                            </p>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs break-all text-xs">
                            {evt.file_path}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    )}
                    {evt.message && (
                      <p className="text-xs text-muted-foreground/70 mt-0.5">{evt.message}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          {hasMore && (
            <div className="p-2 border-t">
              <Button
                variant="ghost"
                size="sm"
                className="w-full text-xs"
                onClick={loadMore}
                disabled={loadingMore}
              >
                {loadingMore && <Loader2 className="w-3 h-3 animate-spin mr-1" />}
                Load more
              </Button>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
