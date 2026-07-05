/**
 * LibraryPicker — multi-select list of libraries for agent binding.
 *
 * Mirrors the pattern established in frontend/src/components/libraries/SourcePicker.tsx:
 * search box, keyboard navigation, cancelRef cancellation, loading/error states.
 */
import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { Search, Loader2, RefreshCw, BookOpen } from 'lucide-react'
import { cn } from '../../../lib/utils'
import { libraryApi } from '../../../services/api/library'
import type { Library } from '../../../services/api/types/library'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

interface LibraryPickerProps {
  /** IDs of currently selected libraries. */
  selectedIds: string[]
  onToggle: (libraryId: string) => void
}

export function LibraryPicker({ selectedIds, onToggle }: LibraryPickerProps) {
  const [libraries, setLibraries] = useState<Library[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const listRef = useRef<HTMLUListElement>(null)
  /** Cancels the in-flight fetch on re-load or unmount. */
  const cancelRef = useRef<(() => void) | null>(null)

  const load = useCallback(() => {
    cancelRef.current?.()
    let cancelled = false
    cancelRef.current = () => { cancelled = true }
    setLoading(true)
    setError(null)
    libraryApi
      .list()
      .then(data => {
        if (!cancelled) setLibraries(data)
      })
      .catch(err => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : 'Failed to load libraries')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
  }, [])

  useEffect(() => {
    load()
    return () => { cancelRef.current?.() }
  }, [load])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return libraries
    return libraries.filter(l =>
      l.name.toLowerCase().includes(q) ||
      (l.description ?? '').toLowerCase().includes(q)
    )
  }, [libraries, search])

  const handleListKeyDown = (e: React.KeyboardEvent<HTMLUListElement>) => {
    const items = listRef.current?.querySelectorAll<HTMLLIElement>('[role="option"]')
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

  if (libraries.length === 0) {
    return (
      <div className="py-8 text-center border rounded-md">
        <BookOpen className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
        <p className="text-sm text-muted-foreground">No libraries available.</p>
        <p className="text-xs text-muted-foreground mt-1">
          Create a library and add sources to it first.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {/* Search box */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
        <Input
          placeholder="Filter by name or description…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="pl-8"
          aria-label="Filter libraries by name"
        />
      </div>

      {/* Library list */}
      <div className="border rounded-md overflow-y-auto max-h-64" role="presentation">
        {filtered.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            No libraries match your filter.
          </p>
        ) : (
          <ul
            ref={listRef}
            role="listbox"
            aria-label="Available libraries"
            aria-multiselectable="true"
            onKeyDown={handleListKeyDown}
          >
            {filtered.map(lib => {
              const selected = selectedIds.includes(lib.id)
              return (
                <li
                  key={lib.id}
                  role="option"
                  aria-selected={selected}
                  tabIndex={0}
                  onClick={() => onToggle(lib.id)}
                  className={cn(
                    'flex items-start gap-3 px-3 py-2.5 border-b last:border-b-0 transition-colors outline-none cursor-pointer',
                    'hover:bg-muted/50 focus-visible:bg-muted/50',
                    selected && 'bg-muted'
                  )}
                >
                  {/* Checkbox is presentation-only; interaction handled by the li */}
                  <Checkbox
                    checked={selected}
                    className="mt-0.5 shrink-0 pointer-events-none"
                    tabIndex={-1}
                    aria-hidden="true"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium truncate">{lib.name}</span>
                      {lib.status !== 'ready' && (
                        <Badge variant="secondary" className="text-xs shrink-0">
                          {lib.status}
                        </Badge>
                      )}
                    </div>
                    {lib.description && (
                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                        {lib.description}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground/70 mt-0.5">
                      {lib.source_count} {lib.source_count === 1 ? 'source' : 'sources'} &middot; {lib.chunk_count.toLocaleString()} chunks
                    </p>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        {selectedIds.length} {selectedIds.length === 1 ? 'library' : 'libraries'} selected
        {search && filtered.length < libraries.length
          ? ` · ${filtered.length} of ${libraries.length} shown`
          : ''}
      </p>
    </div>
  )
}
