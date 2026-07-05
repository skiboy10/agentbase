import { Search, Loader2, ArrowLeft } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import SearchFilters from '../SearchFilters'
import SearchResultCard from '../SearchResultCard'
import type { SourcesFilters } from '../SearchFilters'
import type { SearchResult } from '../../../services/api/types/sources'

interface SearchTabProps {
  sourcesQuery: string
  onQueryChange: (q: string) => void
  sourcesResults: SearchResult[] | null
  searching: boolean
  sourcesFilters: SourcesFilters
  onFiltersChange: (filters: SourcesFilters) => void
  hasActiveFilters: boolean
  onSearch: () => void
  onClear: () => void
}

export function SearchTab({
  sourcesQuery,
  onQueryChange,
  sourcesResults,
  searching,
  sourcesFilters,
  onFiltersChange,
  hasActiveFilters,
  onSearch,
  onClear,
}: SearchTabProps) {
  const isSearchView = sourcesResults !== null

  return (
    <>
      {/* Search Input Row */}
      <div className="mb-4">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Test a query against your indexed sources... (press Enter)"
              value={sourcesQuery}
              onChange={(e) => onQueryChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') onSearch()
              }}
              className="pl-9"
            />
          </div>
          <Button onClick={onSearch} disabled={!sourcesQuery.trim() || searching}>
            {searching && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
            Search
          </Button>
          {isSearchView && (
            <Button variant="ghost" onClick={onClear}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back
            </Button>
          )}
        </div>

        {/* Metadata filters */}
        <div className="mt-3">
          <SearchFilters filters={sourcesFilters} onFiltersChange={onFiltersChange} />
        </div>
      </div>

      {/* Results */}
      {isSearchView && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-foreground">
              {sourcesResults!.length > 0
                ? `${sourcesResults!.length} results for "${sourcesQuery}"`
                : `No results for "${sourcesQuery}"`}
              {hasActiveFilters && (
                <span className="ml-2 text-muted-foreground font-normal">(filtered)</span>
              )}
            </h2>
          </div>
          {sourcesResults!.length === 0 ? (
            <div className="text-center py-12">
              <Search className="w-12 h-12 text-muted-foreground/50 mx-auto mb-3" />
              <p className="text-muted-foreground">No matching documents found</p>
              <p className="text-sm text-muted-foreground/70 mt-1">
                Try adjusting your query or removing filters
              </p>
            </div>
          ) : (
            sourcesResults!.map((result, i) => (
              <SearchResultCard key={i} result={result} rank={i + 1} />
            ))
          )}
        </div>
      )}

      {/* Idle state — show hint when no search has been run */}
      {!isSearchView && (
        <div className="text-center py-12">
          <Search className="w-12 h-12 text-muted-foreground/50 mx-auto mb-3" />
          <p className="text-muted-foreground">Enter a query to test how well your indexed sources answer it</p>
          <p className="text-sm text-muted-foreground/70 mt-1">
            Searches raw source chunks directly — unlike Library search, which queries curated collections.
          </p>
        </div>
      )}
    </>
  )
}
