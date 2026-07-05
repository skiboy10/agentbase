import { useState, useMemo, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Search, Database, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import SourceCard from '../SourceCard'
import { SOURCE_KINDS, getSourceKind, type SourceKind } from '@/lib/sourceType'
import { SORT_OPTIONS, DEFAULT_SORT, parseSortKey, sortSources } from '@/lib/sourcesSort'
import type { Source } from '../../../services/api/types/sources'

interface SourcesTabProps {
  sources: Source[]
  loading: boolean
  deleting: string | null
  onAddSource: () => void
  onEdit: (source: Source) => void
  onManageUrls: (source: Source) => void
  onRefresh: (source: Source) => void
  onIndex: (id: string) => void
  onDelete: (id: string) => void
  onRetryFailed: (id: string) => void
  onForceSync: (id: string) => void
  onReEnrich: (id: string) => void
}

export function SourcesTab({
  sources,
  loading,
  deleting,
  onAddSource,
  onEdit,
  onManageUrls,
  onRefresh,
  onIndex,
  onDelete,
  onRetryFailed,
  onForceSync,
  onReEnrich,
}: SourcesTabProps) {
  // Filter state lives in the URL so views are shareable and survive refresh /
  // back-forward navigation (see docs/recipes/url-filter-persistence.md). The
  // `filter`/`status`/`type` keys are reserved in SearchFilters so the Search
  // tab (same URL) never mistakes them for taxonomy facets.
  const [searchParams, setSearchParams] = useSearchParams()
  const [expandedLogs, setExpandedLogs] = useState<string | null>(null)

  const searchQuery = searchParams.get('filter') ?? ''
  const statusFilter = searchParams.get('status') ?? 'all'
  // Invalid/stale values (e.g. ?sort=bogus) fall back to the default so the
  // Select never renders blank.
  const sortKey = parseSortKey(searchParams.get('sort'))
  const selectedKinds = useMemo<SourceKind[]>(() => {
    const raw = searchParams.get('type')
    if (!raw) return []
    const valid = new Set(SOURCE_KINDS.map((k) => k.kind))
    return raw.split(',').filter((k): k is SourceKind => valid.has(k as SourceKind))
  }, [searchParams])

  const setParam = useCallback(
    (key: string, value: string | null) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev)
          if (value) params.set(key, value)
          else params.delete(key)
          return params
        },
        { replace: true }
      )
    },
    [setSearchParams]
  )

  const toggleKind = useCallback(
    (kind: SourceKind) => {
      const next = selectedKinds.includes(kind)
        ? selectedKinds.filter((k) => k !== kind)
        : [...selectedKinds, kind]
      setParam('type', next.length ? next.join(',') : null)
    },
    [selectedKinds, setParam]
  )

  const filteredSources = useMemo(() => {
    let result = sources
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter(
        (s) => s.name.toLowerCase().includes(q) || s.source_path.toLowerCase().includes(q)
      )
    }
    if (statusFilter !== 'all') {
      result = result.filter((s) => s.status === statusFilter)
    }
    if (selectedKinds.length > 0) {
      result = result.filter((s) => {
        const kind = getSourceKind(s)
        return kind !== null && selectedKinds.includes(kind)
      })
    }
    return sortSources(result, sortKey)
  }, [sources, searchQuery, statusFilter, selectedKinds, sortKey])

  return (
    <>
      {/* Filter Bar */}
      <div className="flex flex-col gap-3 mb-6">
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Filter sources..."
              value={searchQuery}
              onChange={(e) => setParam('filter', e.target.value || null)}
              className="pl-9"
            />
          </div>
          <Tabs value={statusFilter} onValueChange={(v) => setParam('status', v === 'all' ? null : v)}>
            <TabsList>
              <TabsTrigger value="all">All</TabsTrigger>
              <TabsTrigger value="indexed">Indexed</TabsTrigger>
              <TabsTrigger value="indexing">Indexing</TabsTrigger>
              <TabsTrigger value="error">Error</TabsTrigger>
            </TabsList>
          </Tabs>
          <Select
            value={sortKey}
            onValueChange={(v) =>
              setParam('sort', v === DEFAULT_SORT ? null : v)
            }
          >
            <SelectTrigger className="w-52" aria-label="Sort sources">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SORT_OPTIONS.map(({ value, label }) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-sm text-muted-foreground ml-auto">
            {filteredSources.length} source{filteredSources.length !== 1 ? 's' : ''}
          </span>
        </div>

        {/* Type filter chips (multi-select) */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-muted-foreground mr-1">Type:</span>
          {SOURCE_KINDS.map(({ kind, label }) => {
            const active = selectedKinds.includes(kind)
            return (
              <Button
                key={kind}
                type="button"
                size="sm"
                variant={active ? 'default' : 'outline'}
                aria-pressed={active}
                className="h-7 text-xs"
                onClick={() => toggleKind(kind)}
              >
                {label}
              </Button>
            )
          })}
          {selectedKinds.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs gap-1"
              onClick={() => setParam('type', null)}
            >
              <X className="w-3 h-3" />
              Clear
            </Button>
          )}
        </div>
      </div>

      {/* Sources List */}
      <div className="space-y-4">
        {filteredSources.map((source) => (
          <SourceCard
            key={source.id}
            source={source}
            isDeleting={deleting === source.id}
            expandedLogs={expandedLogs === source.id}
            onToggleLogs={() =>
              setExpandedLogs((prev) => (prev === source.id ? null : source.id))
            }
            onEdit={() => onEdit(source)}
            onManageUrls={() => onManageUrls(source)}
            onRefresh={() => onRefresh(source)}
            onIndex={() => onIndex(source.id)}
            onDelete={() => {
              if (expandedLogs === source.id) setExpandedLogs(null)
              onDelete(source.id)
            }}
            onRetryFailed={() => onRetryFailed(source.id)}
            onForceSync={() => onForceSync(source.id)}
            onReEnrich={() => onReEnrich(source.id)}
          />
        ))}
      </div>

      {filteredSources.length === 0 && sources.length > 0 && !loading && (
        <div className="text-center py-8">
          <p className="text-muted-foreground">No sources match your filters</p>
        </div>
      )}

      {sources.length === 0 && !loading && (
        <div className="text-center py-12">
          <Database className="w-16 h-16 text-muted-foreground/50 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-muted-foreground mb-2">
            No sources
          </h3>
          <p className="text-muted-foreground/70 mb-4">
            Add directories or URLs to build your source library
          </p>
          <Button onClick={onAddSource}>Add Source</Button>
        </div>
      )}
    </>
  )
}
