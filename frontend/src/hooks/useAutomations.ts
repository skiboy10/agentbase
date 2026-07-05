import { useCallback, useMemo, useState } from 'react'
import { sourcesApi } from '../services/api'
import type { Source, WatcherStatus } from '../services/api/types/sources'
import { useVisiblePolling } from './useVisiblePolling'
import { useWatcherStatus } from './useWatcherStatus'
import { useToast } from '@/hooks/use-toast'
import { deriveAutomations, summaryCounts } from '../lib/automations'
import type { Automation, AutomationSummary } from '../lib/automations'

const LIST_POLL_MS = 20_000

export interface UseAutomationsResult {
  automations: Automation[]
  summary: AutomationSummary
  watcherStatuses: Record<string, WatcherStatus | null>
  loading: boolean
  error: string | null
  pendingIds: Set<string>
  togglePause: (automation: Automation) => Promise<void>
  runNow: (automation: Automation) => Promise<void>
  refetch: () => Promise<void>
}

/**
 * Loads all sources, derives the per-source automations, and exposes
 * pause/resume + run-now actions. Polls the source list while the page is
 * visible, and layers live watcher status on top (15s) for running watchers.
 */
export function useAutomations(): UseAutomationsResult {
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())
  const { toast } = useToast()

  const refetch = useCallback(async () => {
    try {
      const data = await sourcesApi.listSources()
      setSources(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load automations')
    } finally {
      setLoading(false)
    }
  }, [])

  useVisiblePolling(refetch, { intervalMs: LIST_POLL_MS })

  const watcherStatuses = useWatcherStatus(sources)
  const automations = useMemo(() => deriveAutomations(sources), [sources])
  const summary = useMemo(() => summaryCounts(automations), [automations])

  const setPending = useCallback((rowId: string, on: boolean) => {
    setPendingIds((prev) => {
      const next = new Set(prev)
      if (on) next.add(rowId)
      else next.delete(rowId)
      return next
    })
  }, [])

  const togglePause = useCallback(
    async (automation: Automation) => {
      const { id, kind, source, enabled } = automation
      setPending(id, true)
      try {
        if (kind === 'watcher') {
          await sourcesApi.updateSource(source.id, { watch_enabled: !enabled })
          toast({
            title: enabled ? 'Watcher paused' : 'Watcher resumed',
            description: source.name,
          })
        } else {
          await sourcesApi.updateSource(source.id, {
            freshness_policy: enabled ? 'manual' : 'automatic',
          })
          toast({
            title: enabled ? 'Auto-refresh paused' : 'Auto-refresh resumed',
            description: source.name,
          })
        }
        await refetch()
      } catch (e) {
        toast({
          title: 'Action failed',
          description: e instanceof Error ? e.message : 'Could not update automation.',
          variant: 'destructive',
        })
      } finally {
        setPending(id, false)
      }
    },
    [refetch, setPending, toast],
  )

  const runNow = useCallback(
    async (automation: Automation) => {
      const { id, kind, source } = automation
      setPending(id, true)
      try {
        if (kind === 'watcher') {
          const res = await sourcesApi.syncWatcher(source.id)
          const changed = (res.new ?? 0) + (res.modified ?? 0) + (res.deleted ?? 0)
          toast({
            title: 'Sync complete',
            description:
              changed > 0
                ? `${res.new ?? 0} new · ${res.modified ?? 0} modified · ${res.deleted ?? 0} deleted`
                : 'No changes detected.',
          })
        } else {
          await sourcesApi.refreshSource(source.id, { mode: 'full' })
          toast({ title: 'Refresh started', description: source.name })
        }
        await refetch()
      } catch (e) {
        toast({
          title: 'Run failed',
          description: e instanceof Error ? e.message : 'Could not run automation.',
          variant: 'destructive',
        })
      } finally {
        setPending(id, false)
      }
    },
    [refetch, setPending, toast],
  )

  return {
    automations,
    summary,
    watcherStatuses,
    loading,
    error,
    pendingIds,
    togglePause,
    runNow,
    refetch,
  }
}
