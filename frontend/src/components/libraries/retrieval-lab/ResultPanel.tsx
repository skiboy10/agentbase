import { Loader2, Search } from 'lucide-react'
import type { LibrarySearchResult } from '../../../services/api/types/library'
import ResultCard from './ResultCard'

interface ResultPanelProps {
  results: LibrarySearchResult[]
  loading: boolean
  searched: boolean
  latencyMs: number | null
  query: string
}

export default function ResultPanel({
  results,
  loading,
  searched,
  latencyMs,
  query,
}: ResultPanelProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!searched) {
    return (
      <div className="text-center py-8 text-muted-foreground/40">
        <Search className="w-6 h-6 mx-auto mb-2 opacity-40" />
        <p className="text-xs">Run a query to see results</p>
      </div>
    )
  }

  if (results.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground/50">
        <Search className="w-6 h-6 mx-auto mb-2 opacity-40" />
        <p className="text-xs">No results for &ldquo;{query}&rdquo;</p>
      </div>
    )
  }

  return (
    <div className="space-y-2 mt-3">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {results.length} result{results.length !== 1 ? 's' : ''}
        </span>
        {latencyMs != null && (
          <span className="font-mono">{latencyMs}ms</span>
        )}
      </div>
      {results.map((result, i) => (
        <ResultCard key={i} result={result} rank={i + 1} />
      ))}
    </div>
  )
}
