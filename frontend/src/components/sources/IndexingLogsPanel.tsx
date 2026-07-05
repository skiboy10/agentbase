import { useState, useEffect, useCallback, useRef } from 'react'
import { X, RotateCcw, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import { sourcesApi, IndexingLog, IndexingLogsResponse } from '../../services/api'
import { formatDuration } from '../../utils/sourcesFormatters'
import LogStatusIcon, { getStatusColor } from './LogStatusIcon'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface IndexingLogsPanelProps {
  sourceId: string
  isIndexing: boolean
  onClose: () => void
  onRetry: () => void
}

export default function IndexingLogsPanel({
  sourceId,
  isIndexing,
  onClose,
  onRetry,
}: IndexingLogsPanelProps) {
  const [logs, setLogs] = useState<IndexingLog[]>([])
  const [summary, setSummary] = useState<IndexingLogsResponse['summary'] | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [retrying, setRetrying] = useState(false)
  const logsEndRef = useRef<HTMLDivElement>(null)

  const fetchLogs = useCallback(async () => {
    try {
      const statusFilter = filter === 'all' ? undefined : filter
      const response = await sourcesApi.getSourceLogs(sourceId, statusFilter)
      setLogs(response.logs)
      setSummary(response.summary)
    } catch (err) {
      console.error('Failed to fetch logs:', err)
    } finally {
      setLoading(false)
    }
  }, [sourceId, filter])

  useEffect(() => {
    fetchLogs()
    // Poll for updates if indexing is in progress
    if (isIndexing) {
      const interval = setInterval(fetchLogs, 2000)
      return () => clearInterval(interval)
    }
  }, [fetchLogs, isIndexing])

  // Auto-scroll to bottom when new logs come in during indexing
  useEffect(() => {
    if (isIndexing && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, isIndexing])

  const handleRetry = async () => {
    setRetrying(true)
    try {
      await onRetry()
    } finally {
      setRetrying(false)
    }
  }

  const filteredLogs =
    filter === 'all' ? logs : logs.filter((log) => log.status === filter)

  return (
    <Card className="mt-4">
      {/* Header */}
      <CardHeader className="py-3 px-4 flex-row items-center justify-between space-y-0">
        <div className="flex items-center gap-4">
          <CardTitle className="text-sm font-medium">Indexing Logs</CardTitle>
          {summary && (
            <div className="flex items-center gap-3 text-xs">
              <span className="text-green-400">{summary.done} done</span>
              <span className="text-destructive">{summary.failed} failed</span>
              {summary.in_progress > 0 && (
                <span className="text-yellow-400">
                  {summary.in_progress} in progress
                </span>
              )}
              <span className="text-muted-foreground">{summary.pending} pending</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Filter dropdown */}
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="h-7 w-24 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="done">Done</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
            </SelectContent>
          </Select>
          {/* Retry button */}
          {summary && summary.failed > 0 && !isIndexing && (
            <Button
              size="sm"
              variant="secondary"
              className="h-7 text-xs bg-orange-600 hover:bg-orange-500 text-white"
              onClick={handleRetry}
              disabled={retrying}
            >
              {retrying ? (
                <Loader2 className="w-3 h-3 animate-spin mr-1" />
              ) : (
                <RotateCcw className="w-3 h-3 mr-1" />
              )}
              Retry {summary.failed} Failed
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>
      </CardHeader>

      {/* Logs list */}
      <CardContent className="p-0">
        <ScrollArea className="h-64">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 text-muted-foreground animate-spin" />
            </div>
          ) : filteredLogs.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              {filter === 'all' ? 'No indexing logs yet' : `No ${filter} logs`}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {filteredLogs.map((log) => (
                <div
                  key={log.id}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2 text-xs',
                    log.status === 'failed' && 'bg-destructive/10'
                  )}
                >
                  <LogStatusIcon status={log.status} />
                  <span className={cn('w-16 flex-shrink-0', getStatusColor(log.status))}>
                    {log.status}
                  </span>
                  <span
                    className="flex-1 text-muted-foreground truncate font-mono"
                    title={log.url}
                  >
                    {log.url}
                  </span>
                  {log.scrape_duration_ms !== null && (
                    <span
                      className="text-muted-foreground w-16 text-right"
                      title="Scrape time"
                    >
                      {formatDuration(log.scrape_duration_ms)}
                    </span>
                  )}
                  {log.chunk_count !== null && (
                    <span
                      className="text-muted-foreground w-12 text-right"
                      title="Chunks"
                    >
                      {log.chunk_count} chunks
                    </span>
                  )}
                  {log.error_message && (
                    <span
                      className="text-destructive truncate max-w-48"
                      title={log.error_message}
                    >
                      {log.error_message}
                    </span>
                  )}
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
