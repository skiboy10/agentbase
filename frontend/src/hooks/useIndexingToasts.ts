import { useRef } from 'react'
import { useToast } from '@/hooks/use-toast'
import { useStudioEvents } from './useStudioEvents'
import type { StudioEvent } from './useStudioEvents'

/**
 * Global indexing completion/failure toast listener.
 *
 * Mount once at Layout level. Fires a toast when a source.indexed or
 * source.failed event arrives, regardless of which page is active.
 *
 * Duplicate-event guard: tracks seen (source_id + timestamp) pairs so SSE
 * reconnects that replay the same event don't double-toast. The set is
 * bounded by pruning entries older than 60 s on each new event.
 */
export function useIndexingToasts(): void {
  const { toast } = useToast()

  // Key: "<source_id>|<timestamp>" — guards against SSE reconnect replays
  const seenRef = useRef<Map<string, number>>(new Map())

  function isDuplicate(payload: StudioEvent['payload'], timestamp: string): boolean {
    const id = typeof payload?.id === 'string' ? payload.id : String(payload?.id ?? '')
    const key = `${id}|${timestamp}`
    const now = Date.now()

    // Prune entries older than 60 s
    for (const [k, ts] of seenRef.current.entries()) {
      if (now - ts > 60_000) seenRef.current.delete(k)
    }

    if (seenRef.current.has(key)) return true
    seenRef.current.set(key, now)
    return false
  }

  useStudioEvents({
    onAnyEvent(event) {
      if (event.type !== 'source.indexed' && event.type !== 'source.failed') return

      // Defensive: a malformed SSE event may arrive without a payload
      const payload = event.payload
      if (!payload || typeof payload !== 'object') return

      if (isDuplicate(payload, event.timestamp)) return

      const name = typeof payload.name === 'string' ? payload.name : 'Source'

      if (event.type === 'source.indexed') {
        const chunkCount = typeof payload.chunk_count === 'number' ? payload.chunk_count : null
        const status = typeof payload.status === 'string' ? payload.status : 'indexed'
        const isError = status === 'error'

        if (isError) {
          toast({
            title: `${name} — indexing error`,
            description: 'The source indexed but reported an error. Check source details.',
            variant: 'destructive',
          })
        } else {
          toast({
            title: `${name} indexed`,
            description: chunkCount !== null ? `${chunkCount.toLocaleString()} chunk${chunkCount !== 1 ? 's' : ''} ready` : 'Indexing complete',
          })
        }
      } else if (event.type === 'source.failed') {
        const error = typeof payload.error === 'string' ? payload.error : undefined
        toast({
          title: `${name} — indexing failed`,
          description: error ?? 'An error occurred during indexing.',
          variant: 'destructive',
        })
      }
    },
  })
}
