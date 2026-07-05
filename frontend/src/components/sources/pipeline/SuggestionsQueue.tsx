import { useState, useEffect, useCallback } from 'react'
import { Loader2, Lightbulb, Check, X, GitMerge } from 'lucide-react'
import { taxonomyApi } from '../../../services/api/taxonomy'
import type { TaxonomySuggestion } from '../../../services/api/types/taxonomy'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/hooks/use-toast'

interface MergeRowProps {
  onConfirm: (value: string) => void
  onCancel: () => void
  saving: boolean
}

function MergeRow({ onConfirm, onCancel, saving }: MergeRowProps) {
  const [value, setValue] = useState('')
  return (
    <div className="flex items-center gap-2 mt-2">
      <Input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Merge into value..."
        className="h-7 text-sm"
        autoFocus
        onKeyDown={(e) => {
          if (e.key === 'Enter' && value.trim()) onConfirm(value.trim())
          if (e.key === 'Escape') onCancel()
        }}
      />
      <Button
        size="sm"
        className="h-7 px-2 text-xs"
        onClick={() => value.trim() && onConfirm(value.trim())}
        disabled={saving || !value.trim()}
      >
        {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Merge'}
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="h-7 px-2 text-xs"
        onClick={onCancel}
        disabled={saving}
      >
        Cancel
      </Button>
    </div>
  )
}

interface SuggestionsQueueProps {
  taxonomyId: string
}

export function SuggestionsQueue({ taxonomyId }: SuggestionsQueueProps) {
  const { toast } = useToast()
  const [suggestions, setSuggestions] = useState<TaxonomySuggestion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actioning, setActioning] = useState<string | null>(null)
  const [mergeOpen, setMergeOpen] = useState<string | null>(null)

  const fetchSuggestions = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await taxonomyApi.listSuggestions(taxonomyId, 'pending')
      setSuggestions(data.slice().sort((a, b) => b.frequency - a.frequency))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load suggestions')
    } finally {
      setLoading(false)
    }
  }, [taxonomyId])

  useEffect(() => { fetchSuggestions() }, [fetchSuggestions])

  const handleApprove = async (suggestion: TaxonomySuggestion) => {
    const saved = suggestions.slice()
    setSuggestions(prev => prev.filter(s => s.id !== suggestion.id))
    setActioning(suggestion.id)
    try {
      await taxonomyApi.approveSuggestion(taxonomyId, suggestion.id)
      toast({ title: 'Suggestion approved', description: `"${suggestion.suggested_value}" added to taxonomy.` })
    } catch (err) {
      setSuggestions(saved)
      toast({
        title: 'Approve failed',
        description: err instanceof Error ? err.message : 'Could not approve suggestion.',
        variant: 'destructive',
      })
    } finally {
      setActioning(null)
    }
  }

  const handleReject = async (suggestion: TaxonomySuggestion) => {
    const saved = suggestions.slice()
    setSuggestions(prev => prev.filter(s => s.id !== suggestion.id))
    setActioning(suggestion.id)
    try {
      await taxonomyApi.rejectSuggestion(taxonomyId, suggestion.id)
      toast({ title: 'Suggestion rejected', description: `"${suggestion.suggested_value}" dismissed.` })
    } catch (err) {
      setSuggestions(saved)
      toast({
        title: 'Reject failed',
        description: err instanceof Error ? err.message : 'Could not reject suggestion.',
        variant: 'destructive',
      })
    } finally {
      setActioning(null)
    }
  }

  const handleMerge = async (suggestion: TaxonomySuggestion, mergeValue: string) => {
    const saved = suggestions.slice()
    setSuggestions(prev => prev.filter(s => s.id !== suggestion.id))
    setMergeOpen(null)
    setActioning(suggestion.id)
    try {
      await taxonomyApi.mergeSuggestion(taxonomyId, suggestion.id, mergeValue)
      toast({ title: 'Suggestion merged', description: `"${suggestion.suggested_value}" merged into "${mergeValue}".` })
    } catch (err) {
      setSuggestions(saved)
      toast({
        title: 'Merge failed',
        description: err instanceof Error ? err.message : 'Could not merge suggestion.',
        variant: 'destructive',
      })
    } finally {
      setActioning(null)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-violet-400" />
            <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              Pending Suggestions
            </CardTitle>
          </div>
          {!loading && !error && (
            <Badge variant={suggestions.length > 0 ? 'secondary' : 'outline'}>
              {suggestions.length}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          Values seen in documents that are not yet in the taxonomy
        </p>
      </CardHeader>

      <CardContent className="pt-0">
        {loading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        )}

        {error && (
          <div className="py-4 text-center">
            <p className="text-sm text-destructive mb-3">{error}</p>
            <Button variant="outline" size="sm" onClick={fetchSuggestions}>
              Retry
            </Button>
          </div>
        )}

        {!loading && !error && suggestions.length === 0 && (
          <div className="py-8 text-center">
            <Lightbulb className="w-8 h-8 text-muted-foreground/30 mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">No pending suggestions</p>
            <p className="text-xs text-muted-foreground/60 mt-1">
              Suggestions appear when documents contain values not in the taxonomy
            </p>
          </div>
        )}

        {!loading && !error && suggestions.length > 0 && (
          <div className="space-y-2">
            {suggestions.map((suggestion) => {
              const isActioning = actioning === suggestion.id
              const isMerging = mergeOpen === suggestion.id
              return (
                <div
                  key={suggestion.id}
                  className="border border-border/60 rounded-md px-3 py-2.5"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge
                          variant="outline"
                          className="text-xs text-violet-400 border-violet-400/40 shrink-0"
                        >
                          {suggestion.facet}
                        </Badge>
                        <span className="font-semibold text-foreground text-sm truncate">
                          {suggestion.suggested_value}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Seen {suggestion.frequency}x
                        {suggestion.sample_document_ids?.length
                          ? ` · ${suggestion.sample_document_ids.length} doc${suggestion.sample_document_ids.length !== 1 ? 's' : ''}`
                          : ''}
                      </p>
                    </div>

                    <div className="flex items-center gap-0.5 shrink-0">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-green-400 hover:text-green-300 hover:bg-green-400/10"
                        aria-label={`Approve ${suggestion.suggested_value}`}
                        onClick={() => handleApprove(suggestion)}
                        disabled={isActioning || isMerging}
                      >
                        {isActioning ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Check className="w-3.5 h-3.5" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/10"
                        aria-label={`Reject ${suggestion.suggested_value}`}
                        onClick={() => handleReject(suggestion)}
                        disabled={isActioning || isMerging}
                      >
                        <X className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-foreground"
                        aria-label={`Merge ${suggestion.suggested_value}`}
                        onClick={() => setMergeOpen(isMerging ? null : suggestion.id)}
                        disabled={isActioning}
                      >
                        <GitMerge className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>

                  {isMerging && (
                    <MergeRow
                      saving={isActioning}
                      onConfirm={(val) => handleMerge(suggestion, val)}
                      onCancel={() => setMergeOpen(null)}
                    />
                  )}
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
