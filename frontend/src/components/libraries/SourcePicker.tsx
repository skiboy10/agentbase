import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { Search, Loader2, RefreshCw } from 'lucide-react'
import { cn } from '../../lib/utils'
import { getSourceTypeMeta } from '@/lib/sourceType'
import { sourcesApi } from '../../services/api/sources'
import type { Source } from '../../services/api/types/sources'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface SourcePickerProps {
  /** IDs of sources already bound to this library — shown disabled with a hint. */
  boundSourceIds: Set<string>
  /** Currently selected source id (single-select). */
  value: string
  onChange: (sourceId: string) => void
}

export const statusVariant = (
  status: string
): 'default' | 'secondary' | 'destructive' | 'outline' => {
  if (status === 'indexed') return 'default'
  if (status === 'error') return 'destructive'
  return 'secondary'
}

export function SourcePicker({ boundSourceIds, value, onChange }: SourcePickerProps) {
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const listRef = useRef<HTMLUListElement>(null)
  /** Cancels the in-flight fetch — set on every load(), called on re-load and unmount. */
  const cancelRef = useRef<(() => void) | null>(null)

  const load = useCallback(() => {
    cancelRef.current?.()
    let cancelled = false
    cancelRef.current = () => {
      cancelled = true
    }
    setLoading(true)
    setError(null)
    sourcesApi
      .listSources()
      .then(data => {
        if (!cancelled) setSources(data)
      })
      .catch(err => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : 'Failed to load sources')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
  }, [])

  useEffect(() => {
    load()
    return () => {
      cancelRef.current?.()
    }
  }, [load])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return sources
    return sources.filter(s => s.name.toLowerCase().includes(q))
  }, [sources, search])

  /** Keyboard navigation within the list. */
  const handleListKeyDown = (e: React.KeyboardEvent<HTMLUListElement>) => {
    const items = listRef.current?.querySelectorAll<HTMLLIElement>('[role="option"]:not([aria-disabled="true"])')
    if (!items || items.length === 0) return

    const active = document.activeElement as HTMLElement
    const currentIndex = Array.from(items).indexOf(active as HTMLLIElement)

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      const next = items[currentIndex + 1] ?? items[0]
      next.focus()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      const prev = items[currentIndex - 1] ?? items[items.length - 1]
      prev.focus()
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      active.click()
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 border rounded-md">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="py-6 text-center border rounded-md space-y-2">
        <p className="text-sm text-destructive">{error}</p>
        <Button variant="ghost" size="sm" onClick={load}>
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {/* Search box */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
        <Input
          placeholder="Filter by name…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="pl-8"
          aria-label="Filter sources by name"
        />
      </div>

      {/* Source list */}
      <div className="border rounded-md overflow-y-auto max-h-56" role="presentation">
        {filtered.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            {search ? 'No sources match your filter.' : 'No sources available.'}
          </p>
        ) : (
          <ul
            ref={listRef}
            role="listbox"
            aria-label="Available sources"
            onKeyDown={handleListKeyDown}
          >
            {filtered.map(source => {
              const bound = boundSourceIds.has(source.id)
              const selected = value === source.id
              const meta = getSourceTypeMeta(source.source_type)
              const Icon = meta.icon

              return (
                <li
                  key={source.id}
                  role="option"
                  aria-selected={selected}
                  aria-disabled={bound}
                  tabIndex={bound ? -1 : 0}
                  onClick={() => {
                    if (!bound) onChange(selected ? '' : source.id)
                  }}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2.5 border-b last:border-b-0 transition-colors outline-none',
                    bound
                      ? 'opacity-50 cursor-not-allowed'
                      : 'cursor-pointer hover:bg-muted/50 focus-visible:bg-muted/50',
                    selected && !bound && 'bg-muted'
                  )}
                >
                  {/* Type icon chip */}
                  <div
                    className={cn(
                      'w-7 h-7 rounded-md flex items-center justify-center shrink-0',
                      meta.bg
                    )}
                  >
                    <Icon className={cn('w-3.5 h-3.5', meta.text)} />
                  </div>

                  {/* Name + badges */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-sm font-medium truncate">{source.name}</span>
                      <Badge variant="outline" className={cn('text-xs shrink-0', meta.text)}>
                        {meta.label}
                      </Badge>
                      <Badge
                        variant={statusVariant(source.status)}
                        className="text-xs shrink-0"
                      >
                        {source.status}
                      </Badge>
                      {bound && (
                        <Badge variant="outline" className="text-xs shrink-0 text-muted-foreground">
                          already in library
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground/70 mt-0.5">
                      {source.chunk_count} chunks
                    </p>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {sources.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {filtered.length} of {sources.length} source{sources.length !== 1 ? 's' : ''}
          {search ? ' match your filter' : ''}
        </p>
      )}
    </div>
  )
}
