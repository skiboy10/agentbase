import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { sourcesApi } from '../services/api'
import type { Source } from '../services/api/types/sources'

export interface UseSourcesResult {
  sources: Source[]
  loading: boolean
  error: string | null
  setError: (error: string | null) => void
  qdrantHealth: { healthy: boolean; message: string } | null
  deleting: string | null
  deleteConfirmId: string | null
  setDeleteConfirmId: (id: string | null) => void
  confirmDeleteSource: () => Promise<void>
  fetchData: () => Promise<void>
  handleIndexSource: (id: string) => Promise<void>
  handleDeleteSource: (id: string) => void
  handleRetryFailed: (id: string) => Promise<void>
  handleSourceAdded: (source: Source) => void
  handleSourceUpdated: (source: Source) => void
  handleRefreshStarted: (source: Source, urlCount: number, message: string) => void
}

export function useSources(selectedProjectId: string | null): UseSourcesResult {
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [qdrantHealth, setQdrantHealth] = useState<{ healthy: boolean; message: string } | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [, setIndexingSources] = useState<Set<string>>(new Set())
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const [sourcesData, healthData] = await Promise.all([
        sourcesApi.listSources(selectedProjectId || undefined),
        sourcesApi.health(),
      ])
      setSources(sourcesData)
      setQdrantHealth(healthData.qdrant)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sources')
    } finally {
      setLoading(false)
    }
  }, [selectedProjectId])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Stable key for indexing sources — prevents useEffect re-firing on every render
  const indexingKey = useMemo(
    () => sources.filter((s) => s.status === 'indexing').map((s) => s.id).join(','),
    [sources]
  )

  // Poll for indexing status
  useEffect(() => {
    const indexingIds = indexingKey ? indexingKey.split(',') : []
    setIndexingSources(new Set(indexingIds))

    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }

    if (indexingIds.length > 0) {
      const poll = async () => {
        try {
          const statusPromises = indexingIds.map((id) =>
            sourcesApi.getSourceStatus(id).catch(() => null)
          )
          const statuses = await Promise.all(statusPromises)
          const anyFinished = statuses.some((s) => s && s.status !== 'indexing')

          if (anyFinished) {
            const updatedSources = await sourcesApi.listSources()
            setSources(updatedSources)
          } else {
            setSources((prevSources) =>
              prevSources.map((source) => {
                const status = statuses.find((s) => s?.source_id === source.id)
                if (status) {
                  return {
                    ...source,
                    status: status.status,
                    progress: status.progress,
                    progress_total: status.progress_total,
                    progress_message: status.progress_message,
                    progress_updated_at: status.progress_updated_at,
                    document_count: status.document_count,
                    chunk_count: status.chunk_count,
                    error_message: status.error_message,
                  }
                }
                return source
              })
            )
          }
        } catch (err) {
          console.error('Polling error:', err)
        }
      }

      pollingRef.current = setInterval(poll, 2000)

      return () => {
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
      }
    }
  }, [indexingKey])

  const handleSourceAdded = (source: Source) => {
    setSources((prev) => [source, ...prev])
  }

  const handleSourceUpdated = (source: Source) => {
    setSources((prev) => prev.map((s) => (s.id === source.id ? source : s)))
  }

  const handleIndexSource = async (id: string) => {
    try {
      setError(null)
      await sourcesApi.indexSource(id)
      setSources((prevSources) =>
        prevSources.map((source) =>
          source.id === id
            ? {
                ...source,
                status: 'indexing',
                progress: 0,
                progress_total: 0,
                progress_message: 'Starting indexing...',
                progress_updated_at: new Date().toISOString(),
                error_message: null,
              }
            : source
        )
      )
      setIndexingSources((prev) => new Set([...prev, id]))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start indexing')
    }
  }

  const handleDeleteSource = (id: string) => {
    setDeleteConfirmId(id)
  }

  const confirmDeleteSource = async () => {
    const targetId = deleteConfirmId
    if (!targetId) return
    setDeleteConfirmId(null)
    try {
      setDeleting(targetId)
      await sourcesApi.deleteSource(targetId)
      setSources((prev) => prev.filter((s) => s.id !== targetId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete source')
    } finally {
      setDeleting(null)
    }
  }

  const handleRetryFailed = async (id: string) => {
    try {
      setError(null)
      const result = await sourcesApi.retryFailed(id)

      if (result.status === 'no_failures') {
        return
      }

      setSources((prevSources) =>
        prevSources.map((source) =>
          source.id === id
            ? {
                ...source,
                status: 'indexing',
                progress: 0,
                progress_total: result.retry_count || 0,
                progress_message: `Retrying ${result.retry_count} failed URLs...`,
                progress_updated_at: new Date().toISOString(),
                error_message: null,
              }
            : source
        )
      )
      setIndexingSources((prev) => new Set([...prev, id]))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry failed URLs')
    }
  }

  const handleRefreshStarted = (
    source: Source,
    urlCount: number,
    message: string
  ) => {
    setSources((prev) =>
      prev.map((s) =>
        s.id === source.id
          ? {
              ...s,
              status: 'indexing',
              progress: 0,
              progress_total: urlCount,
              progress_message: message,
              progress_updated_at: new Date().toISOString(),
              error_message: null,
            }
          : s
      )
    )
    setIndexingSources((prev) => new Set([...prev, source.id]))
  }

  return {
    sources,
    loading,
    error,
    setError,
    qdrantHealth,
    deleting,
    deleteConfirmId,
    setDeleteConfirmId,
    confirmDeleteSource,
    fetchData,
    handleIndexSource,
    handleDeleteSource,
    handleRetryFailed,
    handleSourceAdded,
    handleSourceUpdated,
    handleRefreshStarted,
  }
}
