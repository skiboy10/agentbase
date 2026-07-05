import { useState, useCallback } from 'react'
import { sourcesApi } from '../services/api'
import type { SearchResult } from '../services/api/types/sources'
import type { SourcesFilters } from '../components/sources/SearchFilters'
import { useSourcesFilters } from '../components/sources/SearchFilters'

export interface UseSourcesSearchResult {
  sourcesQuery: string
  setSourcesQuery: (q: string) => void
  sourcesResults: SearchResult[] | null
  searching: boolean
  handleSourcesSearch: () => Promise<void>
  handleClearSearch: () => void
  sourcesFilters: SourcesFilters
  setSourcesFilters: (filters: SourcesFilters) => void
  hasActiveFilters: boolean
}

export function useSourcesSearch(
  selectedProjectId: string | null,
  onError?: (msg: string) => void
): UseSourcesSearchResult {
  const [sourcesQuery, setSourcesQuery] = useState('')
  const [sourcesResults, setSourcesResults] = useState<SearchResult[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [sourcesFilters, setSourcesFilters, hasActiveFilters] = useSourcesFilters()

  const handleSourcesSearch = useCallback(async () => {
    const q = sourcesQuery.trim()
    if (!q) return
    try {
      setSearching(true)

      // Build active filters generically — pass any facet key that has a value
      const activeFilters: Record<string, string> = {}
      for (const [key, val] of Object.entries(sourcesFilters)) {
        if (val) activeFilters[key] = val
      }

      const results = await sourcesApi.search(
        q,
        selectedProjectId || undefined,
        10,
        Object.keys(activeFilters).length > 0 ? activeFilters : undefined
      )
      setSourcesResults(results as SearchResult[])
    } catch (err) {
      onError?.(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setSearching(false)
    }
  }, [sourcesQuery, sourcesFilters, selectedProjectId, onError])

  const handleClearSearch = () => {
    setSourcesResults(null)
    setSourcesQuery('')
  }

  return {
    sourcesQuery,
    setSourcesQuery,
    sourcesResults,
    searching,
    handleSourcesSearch,
    handleClearSearch,
    sourcesFilters,
    setSourcesFilters,
    hasActiveFilters,
  }
}
