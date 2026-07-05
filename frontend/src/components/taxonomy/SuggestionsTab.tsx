import { useState, useEffect, useCallback } from 'react'
import {
  Loader2,
  Lightbulb,
  Check,
  X,
  GitMerge,
  ArrowDownUp,
} from 'lucide-react'
import { taxonomyApi } from '../../services/api/taxonomy'
import type { TaxonomySuggestion, TaxonomyTerm } from '../../services/api/types/taxonomy'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { HelpTooltip } from '@/components/HelpTooltip'

interface MergeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  suggestion: TaxonomySuggestion | null
  taxonomyId: string
  onMerged: (suggestionId: string) => void
}

function MergeDialog({ open, onOpenChange, suggestion, taxonomyId, onMerged }: MergeDialogProps) {
  const [terms, setTerms] = useState<TaxonomyTerm[]>([])
  const [loadingTerms, setLoadingTerms] = useState(false)
  const [selectedTermId, setSelectedTermId] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !suggestion) return
    setLoadingTerms(true)
    setSelectedTermId('')
    setError(null)
    taxonomyApi
      .listTerms(taxonomyId)
      .then(data => setTerms(data.filter(t => t.facet === suggestion.facet)))
      .finally(() => setLoadingTerms(false))
  }, [open, suggestion, taxonomyId])

  const handleMerge = async () => {
    if (!suggestion || !selectedTermId) return
    setSaving(true)
    setError(null)
    try {
      await taxonomyApi.mergeSuggestion(taxonomyId, suggestion.id, selectedTermId)
      onMerged(suggestion.id)
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to merge suggestion')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Merge Suggestion</DialogTitle>
        </DialogHeader>
        {suggestion && (
          <div className="space-y-4 py-2">
            <p className="text-sm text-muted-foreground">
              Merge <strong className="text-foreground">{suggestion.suggested_value}</strong> into an
              existing term in the <strong className="text-foreground">{suggestion.facet}</strong> facet.
            </p>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="space-y-1.5">
              <Label>Target term</Label>
              {loadingTerms ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Loading terms...
                </div>
              ) : (
                <Select value={selectedTermId} onValueChange={setSelectedTermId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a term..." />
                  </SelectTrigger>
                  <SelectContent>
                    {terms.map(t => (
                      <SelectItem key={t.id} value={t.id}>
                        {t.value}
                      </SelectItem>
                    ))}
                    {terms.length === 0 && (
                      <div className="px-3 py-2 text-sm text-muted-foreground">
                        No terms in this facet
                      </div>
                    )}
                  </SelectContent>
                </Select>
              )}
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleMerge} disabled={saving || !selectedTermId}>
            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Merge
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface SuggestionsTabProps {
  taxonomyId: string
}

export function SuggestionsTab({ taxonomyId }: SuggestionsTabProps) {
  const [suggestions, setSuggestions] = useState<TaxonomySuggestion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actioning, setActioning] = useState<string | null>(null)
  const [mergeTarget, setMergeTarget] = useState<TaxonomySuggestion | null>(null)

  const fetchSuggestions = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await taxonomyApi.listSuggestions(taxonomyId)
      // Sort by frequency descending
      setSuggestions(data.slice().sort((a, b) => b.frequency - a.frequency))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load suggestions')
    } finally {
      setLoading(false)
    }
  }, [taxonomyId])

  useEffect(() => { fetchSuggestions() }, [fetchSuggestions])

  const handleApprove = async (suggestion: TaxonomySuggestion) => {
    setActioning(suggestion.id)
    try {
      await taxonomyApi.approveSuggestion(taxonomyId, suggestion.id)
      setSuggestions(prev => prev.filter(s => s.id !== suggestion.id))
    } finally {
      setActioning(null)
    }
  }

  const handleReject = async (suggestion: TaxonomySuggestion) => {
    setActioning(suggestion.id)
    try {
      await taxonomyApi.rejectSuggestion(taxonomyId, suggestion.id)
      setSuggestions(prev => prev.filter(s => s.id !== suggestion.id))
    } finally {
      setActioning(null)
    }
  }

  const handleMerged = (suggestionId: string) => {
    setSuggestions(prev => prev.filter(s => s.id !== suggestionId))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="py-6 text-center">
        <p className="text-sm text-destructive">{error}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={fetchSuggestions}>
          Retry
        </Button>
      </div>
    )
  }

  if (suggestions.length === 0) {
    return (
      <div className="text-center py-12">
        <Lightbulb className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
        <p className="text-muted-foreground">No pending suggestions</p>
        <p className="text-sm text-muted-foreground/60 mt-1">
          Suggestions appear when documents contain values not in the taxonomy
        </p>
      </div>
    )
  }

  return (
    <div className="mt-4 space-y-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <ArrowDownUp className="w-3.5 h-3.5" />
          Sorted by frequency
          <HelpTooltip helpKey="taxonomy.suggestions" side="right" />
        </div>
        <span className="text-sm text-muted-foreground">
          {suggestions.length} pending
        </span>
      </div>

      {suggestions.map((suggestion) => {
        const isActioning = actioning === suggestion.id
        return (
          <Card key={suggestion.id}>
            <CardContent className="py-3 px-4">
              <div className="flex items-center gap-3">
                {/* Facet + value */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge
                      variant="outline"
                      className="text-xs text-violet-400 border-violet-400/40 shrink-0"
                    >
                      {suggestion.facet}
                    </Badge>
                    <span className="font-semibold text-foreground truncate">
                      {suggestion.suggested_value}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                    <span>Seen {suggestion.frequency}x</span>
                    <span>{suggestion.sample_document_ids?.length ?? 0} doc{(suggestion.sample_document_ids?.length ?? 0) !== 1 ? 's' : ''}</span>
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex items-center gap-1 shrink-0">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-green-400 hover:text-green-300 hover:bg-green-400/10"
                    aria-label={`Approve suggestion ${suggestion.suggested_value}`}
                    onClick={() => handleApprove(suggestion)}
                    disabled={isActioning}
                  >
                    {isActioning ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Check className="w-4 h-4" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                    aria-label={`Reject suggestion ${suggestion.suggested_value}`}
                    onClick={() => handleReject(suggestion)}
                    disabled={isActioning}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-foreground"
                    aria-label={`Merge suggestion ${suggestion.suggested_value}`}
                    onClick={() => setMergeTarget(suggestion)}
                    disabled={isActioning}
                  >
                    <GitMerge className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )
      })}

      <MergeDialog
        open={!!mergeTarget}
        onOpenChange={(open) => !open && setMergeTarget(null)}
        suggestion={mergeTarget}
        taxonomyId={taxonomyId}
        onMerged={handleMerged}
      />
    </div>
  )
}
