import { useEffect, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { taxonomyApi } from '../../services/api/taxonomy'

// Generic filters: keys are facet names from the active taxonomy
export type SourcesFilters = Record<string, string | undefined>

interface SearchFiltersProps {
  filters: SourcesFilters
  onFiltersChange: (filters: SourcesFilters) => void
}

const NONE_VALUE = '__none__'

// URL search param keys reserved for routing and the Sources-tab filters
// (`filter`, `status`, `type`) — never treated as Search-tab taxonomy facets.
// The Sources and Search tabs share one URL, so these must be excluded here.
const RESERVED_PARAMS = new Set(['q', 'tab', 'filter', 'status', 'type'])

// Converts a facet key to a human-readable label
function facetLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function useSourcesFilters(): [SourcesFilters, (filters: SourcesFilters) => void, boolean] {
  const [searchParams, setSearchParams] = useSearchParams()

  // Read all non-reserved search params as filters
  const filters: SourcesFilters = {}
  for (const [key, value] of searchParams.entries()) {
    if (!RESERVED_PARAMS.has(key)) {
      filters[key] = value
    }
  }

  const hasActiveFilters = Object.values(filters).some(Boolean)

  const setFilters = useCallback(
    (next: SourcesFilters) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev)
          // Remove all existing filter keys (non-reserved) before applying new ones
          for (const key of Array.from(params.keys())) {
            if (!RESERVED_PARAMS.has(key)) {
              params.delete(key)
            }
          }
          // Apply the new filter values
          for (const [key, val] of Object.entries(next)) {
            if (val) {
              params.set(key, val)
            }
          }
          return params
        },
        { replace: true }
      )
    },
    [setSearchParams]
  )

  return [filters, setFilters, hasActiveFilters]
}

export default function SearchFilters({ filters, onFiltersChange }: SearchFiltersProps) {
  const [termsByFacet, setTermsByFacet] = useState<Record<string, string[]>>({})

  useEffect(() => {
    // Load terms from the first available taxonomy
    taxonomyApi
      .list()
      .then(async (taxonomies) => {
        if (taxonomies.length === 0) return
        const firstTaxonomy = taxonomies[0]
        const terms = await taxonomyApi.listTerms(firstTaxonomy.id)
        const grouped: Record<string, string[]> = {}
        for (const term of terms) {
          if (!grouped[term.facet]) grouped[term.facet] = []
          grouped[term.facet].push(term.value)
        }
        setTermsByFacet(grouped)
      })
      .catch(console.error)
  }, [])

  const handleChange = (facet: string, value: string) => {
    onFiltersChange({
      ...filters,
      [facet]: value === NONE_VALUE ? undefined : value,
    })
  }

  const handleClear = () => {
    // Build a cleared copy of filters with all keys set to undefined
    const cleared: SourcesFilters = {}
    for (const key of Object.keys(filters)) {
      cleared[key] = undefined
    }
    onFiltersChange(cleared)
  }

  const hasActive = Object.values(filters).some(Boolean)
  const facets = Object.keys(termsByFacet)

  if (facets.length === 0) return null

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <span className="text-xs text-muted-foreground">Filter by:</span>
      {facets.map((facet) => {
        const options = termsByFacet[facet]
        if (!options || options.length === 0) return null
        const label = facetLabel(facet)
        return (
          <Select
            key={facet}
            value={filters[facet] || NONE_VALUE}
            onValueChange={(val) => handleChange(facet, val)}
          >
            <SelectTrigger className="h-8 text-xs w-40">
              <SelectValue placeholder={label} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE_VALUE}>{label}: All</SelectItem>
              {options.map((opt) => (
                <SelectItem key={opt} value={opt}>
                  {opt}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )
      })}
      {hasActive && (
        <Button variant="ghost" size="sm" className="h-8 text-xs gap-1" onClick={handleClear}>
          <X className="w-3 h-3" />
          Clear filters
        </Button>
      )}
    </div>
  )
}
