import { useEffect, useRef, useCallback } from 'react'

/**
 * Event types emitted by the backend
 */
export type StudioEventType =
  | 'agent.created'
  | 'agent.updated'
  | 'agent.deleted'
  | 'knowledge.created'
  | 'knowledge.indexed'
  | 'knowledge.indexing'
  | 'knowledge.deleted'
  | 'source.created'
  | 'source.indexed'
  | 'source.indexing'
  | 'source.failed'
  | 'source.deleted'
  | 'source.updated'
  | 'extension.loaded'
  | 'extension.reloaded'
  | 'evaluation.questions_generated'
  | 'evaluation.run_completed'
  | 'evaluation.experiment_promoted'

/**
 * Event payload structure
 */
export interface StudioEvent {
  type: StudioEventType
  payload: {
    id?: string
    name?: string
    [key: string]: unknown
  }
  source: 'mcp' | 'api' | 'system'
  timestamp: string
}

/**
 * Callback handlers for different event types
 */
export interface StudioEventHandlers {
  onAgentCreated?: (payload: StudioEvent['payload']) => void
  onAgentUpdated?: (payload: StudioEvent['payload']) => void
  onAgentDeleted?: (payload: StudioEvent['payload']) => void
  onKnowledgeCreated?: (payload: StudioEvent['payload']) => void
  onKnowledgeIndexed?: (payload: StudioEvent['payload']) => void
  onKnowledgeIndexing?: (payload: StudioEvent['payload']) => void
  onKnowledgeDeleted?: (payload: StudioEvent['payload']) => void
  onSourceCreated?: (payload: StudioEvent['payload']) => void
  onSourceIndexed?: (payload: StudioEvent['payload']) => void
  onSourceIndexing?: (payload: StudioEvent['payload']) => void
  onSourceFailed?: (payload: StudioEvent['payload']) => void
  onSourceDeleted?: (payload: StudioEvent['payload']) => void
  onSourceUpdated?: (payload: StudioEvent['payload']) => void
  onExtensionLoaded?: (payload: StudioEvent['payload']) => void
  onExtensionReloaded?: (payload: StudioEvent['payload']) => void
  onQuestionsGenerated?: (payload: StudioEvent['payload']) => void
  onRunCompleted?: (payload: StudioEvent['payload']) => void
  onExperimentPromoted?: (payload: StudioEvent['payload']) => void
  onAnyEvent?: (event: StudioEvent) => void
}

/**
 * Hook for subscribing to real-time studio events via SSE
 *
 * Events are emitted when data is modified via MCP or API, enabling
 * the UI to update in real-time without polling.
 *
 * @example
 * ```tsx
 * useStudioEvents({
 *   onAgentCreated: () => refetchAgents(),
 *   onAgentUpdated: () => refetchAgents(),
 *   onAgentDeleted: () => refetchAgents(),
 * })
 * ```
 */
export function useStudioEvents(handlers: StudioEventHandlers) {
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const handlersRef = useRef(handlers)

  // Update handlers ref to avoid stale closures
  useEffect(() => {
    handlersRef.current = handlers
  }, [handlers])

  const connect = useCallback(() => {
    // Clean up any existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    // Connect to SSE endpoint
    const eventSource = new EventSource('/api/events')
    eventSourceRef.current = eventSource

    eventSource.onmessage = (event) => {
      try {
        const data: StudioEvent = JSON.parse(event.data)
        const h = handlersRef.current

        // Call the generic handler if provided
        if (h.onAnyEvent) {
          h.onAnyEvent(data)
        }

        // Call specific handlers based on event type
        switch (data.type) {
          case 'agent.created':
            h.onAgentCreated?.(data.payload)
            break
          case 'agent.updated':
            h.onAgentUpdated?.(data.payload)
            break
          case 'agent.deleted':
            h.onAgentDeleted?.(data.payload)
            break
          case 'knowledge.created':
            h.onKnowledgeCreated?.(data.payload)
            break
          case 'knowledge.indexed':
            h.onKnowledgeIndexed?.(data.payload)
            break
          case 'knowledge.indexing':
            h.onKnowledgeIndexing?.(data.payload)
            break
          case 'knowledge.deleted':
            h.onKnowledgeDeleted?.(data.payload)
            break
          case 'source.created':
            h.onSourceCreated?.(data.payload)
            break
          case 'source.indexed':
            h.onSourceIndexed?.(data.payload)
            break
          case 'source.indexing':
            h.onSourceIndexing?.(data.payload)
            break
          case 'source.failed':
            h.onSourceFailed?.(data.payload)
            break
          case 'source.deleted':
            h.onSourceDeleted?.(data.payload)
            break
          case 'source.updated':
            h.onSourceUpdated?.(data.payload)
            break
          case 'extension.loaded':
            h.onExtensionLoaded?.(data.payload)
            break
          case 'extension.reloaded':
            h.onExtensionReloaded?.(data.payload)
            break
          case 'evaluation.questions_generated':
            h.onQuestionsGenerated?.(data.payload)
            break
          case 'evaluation.run_completed':
            h.onRunCompleted?.(data.payload)
            break
          case 'evaluation.experiment_promoted':
            h.onExperimentPromoted?.(data.payload)
            break
        }
      } catch (err) {
        console.error('Failed to parse studio event:', err)
      }
    }

    eventSource.onerror = () => {
      // Close the errored connection
      eventSource.close()

      // Schedule reconnect after 5 seconds
      if (!reconnectTimeoutRef.current) {
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectTimeoutRef.current = null
          connect()
        }, 5000)
      }
    }
  }, [])

  useEffect(() => {
    connect()

    return () => {
      // Clean up on unmount
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [connect])
}
