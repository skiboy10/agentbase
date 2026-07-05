import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Plus,
  Pencil,
  Trash2,
  Loader2,
  Search,
  Tag,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { taxonomyApi } from '../../services/api/taxonomy'
import type { TaxonomyTerm, TaxonomyTermCreate } from '../../services/api/types/taxonomy'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { HelpTooltip } from '@/components/HelpTooltip'

const TERMS_PAGE_SIZE = 50

interface FacetSectionProps {
  facet: string
  terms: TaxonomyTerm[]
  taxonomyId: string
  onTermDeleted: (termId: string) => void
  onTermUpdated: (term: TaxonomyTerm) => void
}

function FacetSection({ facet, terms, taxonomyId, onTermDeleted, onTermUpdated }: FacetSectionProps) {
  const [expanded, setExpanded] = useState(true)
  const [showCount, setShowCount] = useState(TERMS_PAGE_SIZE)
  const [editTerm, setEditTerm] = useState<TaxonomyTerm | null>(null)
  const [editValue, setEditValue] = useState('')
  const [editKeywords, setEditKeywords] = useState('')
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const visibleTerms = terms.slice(0, showCount)
  const hasMore = terms.length > showCount

  const handleEdit = (term: TaxonomyTerm) => {
    setEditTerm(term)
    setEditValue(term.value)
    setEditKeywords(term.keywords.join(', '))
  }

  const handleSaveEdit = async () => {
    if (!editTerm) return
    setSaving(true)
    try {
      const updated = await taxonomyApi.updateTerm(taxonomyId, editTerm.id, {
        value: editValue.trim(),
        keywords: editKeywords.split(',').map(k => k.trim()).filter(Boolean),
      })
      onTermUpdated(updated)
      setEditTerm(null)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (termId: string) => {
    setDeletingId(termId)
    try {
      await taxonomyApi.deleteTerm(taxonomyId, termId)
      onTermDeleted(termId)
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="mb-3">
      <div className="flex items-center gap-2 w-full group">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 flex-1 min-w-0 text-left py-1.5"
        >
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
          )}
          <Tag className="w-3.5 h-3.5 text-violet-400 shrink-0" />
          <span className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
            {facet}
          </span>
          <Badge variant="secondary" className="text-xs ml-1">
            {terms.length}
          </Badge>
        </button>
        <HelpTooltip helpKey="taxonomy.facets" side="right" className="opacity-60 group-hover:opacity-100 shrink-0" />
      </div>

      {expanded && (
        <div className="pl-6 space-y-1 mt-1">
          {visibleTerms.map((term) => (
            <div
              key={term.id}
              className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-muted/40 group/term"
            >
              <span className="text-sm text-foreground font-medium min-w-0 truncate">
                {term.value}
              </span>
              <div className="flex items-center gap-1 flex-wrap flex-1 min-w-0">
                {term.keywords.map((kw) => (
                  <Badge
                    key={kw}
                    variant="outline"
                    className="text-xs h-4 px-1 text-muted-foreground border-muted-foreground/30"
                  >
                    {kw}
                  </Badge>
                ))}
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover/term:opacity-100 transition-opacity shrink-0">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  aria-label={`Edit term ${term.value}`}
                  onClick={() => handleEdit(term)}
                >
                  <Pencil className="w-3 h-3" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-destructive hover:text-destructive"
                  aria-label={`Delete term ${term.value}`}
                  onClick={() => handleDelete(term.id)}
                  disabled={deletingId === term.id}
                >
                  {deletingId === term.id ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Trash2 className="w-3 h-3" />
                  )}
                </Button>
              </div>
            </div>
          ))}

          {hasMore && (
            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-muted-foreground h-7"
              onClick={() => setShowCount(c => c + TERMS_PAGE_SIZE)}
            >
              Show {Math.min(TERMS_PAGE_SIZE, terms.length - showCount)} more...
            </Button>
          )}
        </div>
      )}

      {/* Edit term dialog */}
      <Dialog open={!!editTerm} onOpenChange={(open) => !open && setEditTerm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Term</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Facet</Label>
              <Input value={facet} disabled />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-value">Value</Label>
              <Input
                id="edit-value"
                value={editValue}
                onChange={e => setEditValue(e.target.value)}
                placeholder="Term value"
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5">
                <Label htmlFor="edit-keywords">Keywords (comma-separated)</Label>
                <HelpTooltip helpKey="taxonomy.keywords" side="right" />
              </div>
              <Input
                id="edit-keywords"
                value={editKeywords}
                onChange={e => setEditKeywords(e.target.value)}
                placeholder="keyword1, keyword2"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTerm(null)}>Cancel</Button>
            <Button onClick={handleSaveEdit} disabled={saving || !editValue.trim()}>
              {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

interface AddTermDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  taxonomyId: string
  onTermAdded: (term: TaxonomyTerm) => void
}

function AddTermDialog({ open, onOpenChange, taxonomyId, onTermAdded }: AddTermDialogProps) {
  const [facet, setFacet] = useState('')
  const [value, setValue] = useState('')
  const [keywords, setKeywords] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setFacet('')
    setValue('')
    setKeywords('')
    setError(null)
  }

  const handleCreate = async () => {
    if (!facet.trim() || !value.trim()) return
    setSaving(true)
    setError(null)
    try {
      const data: TaxonomyTermCreate = {
        facet: facet.trim(),
        value: value.trim(),
        keywords: keywords.split(',').map(k => k.trim()).filter(Boolean),
      }
      const term = await taxonomyApi.addTerm(taxonomyId, data)
      onTermAdded(term)
      reset()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create term')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o) }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Term</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5">
              <Label htmlFor="add-facet">Facet</Label>
              <HelpTooltip helpKey="taxonomy.facets" side="right" />
            </div>
            <Input
              id="add-facet"
              value={facet}
              onChange={e => setFacet(e.target.value)}
              placeholder="e.g. product_type"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="add-value">Value</Label>
            <Input
              id="add-value"
              value={value}
              onChange={e => setValue(e.target.value)}
              placeholder="e.g. Widget"
            />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5">
              <Label htmlFor="add-keywords">Keywords (comma-separated)</Label>
              <HelpTooltip helpKey="taxonomy.keywords" side="right" />
            </div>
            <Input
              id="add-keywords"
              value={keywords}
              onChange={e => setKeywords(e.target.value)}
              placeholder="keyword1, keyword2"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => { reset(); onOpenChange(false) }}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={saving || !facet.trim() || !value.trim()}>
            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Add Term
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface TermsTabProps {
  taxonomyId: string
}

export function TermsTab({ taxonomyId }: TermsTabProps) {
  const [terms, setTerms] = useState<TaxonomyTerm[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [showAddDialog, setShowAddDialog] = useState(false)

  const fetchTerms = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await taxonomyApi.listTerms(taxonomyId)
      setTerms(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load terms')
    } finally {
      setLoading(false)
    }
  }, [taxonomyId])

  useEffect(() => { fetchTerms() }, [fetchTerms])

  const filteredTerms = useMemo(() => {
    if (!search.trim()) return terms
    const q = search.toLowerCase()
    return terms.filter(
      t =>
        t.value.toLowerCase().includes(q) ||
        t.facet.toLowerCase().includes(q) ||
        t.keywords.some(k => k.toLowerCase().includes(q))
    )
  }, [terms, search])

  const grouped = useMemo(() => {
    const map = new Map<string, TaxonomyTerm[]>()
    for (const term of filteredTerms) {
      const list = map.get(term.facet) ?? []
      list.push(term)
      map.set(term.facet, list)
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
  }, [filteredTerms])

  const handleTermAdded = (term: TaxonomyTerm) => {
    setTerms(prev => [...prev, term])
  }

  const handleTermDeleted = (termId: string) => {
    setTerms(prev => prev.filter(t => t.id !== termId))
  }

  const handleTermUpdated = (updated: TaxonomyTerm) => {
    setTerms(prev => prev.map(t => t.id === updated.id ? updated : t))
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
        <Button variant="outline" size="sm" className="mt-3" onClick={fetchTerms}>
          Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="mt-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3 mb-4">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search terms..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <span className="text-sm text-muted-foreground ml-auto">
          {filteredTerms.length} term{filteredTerms.length !== 1 ? 's' : ''}
          {search && ` matching "${search}"`}
        </span>
        <div className="flex items-center gap-1.5">
          <Button size="sm" onClick={() => setShowAddDialog(true)}>
            <Plus className="w-4 h-4 mr-1.5" />
            Add Term
          </Button>
          <HelpTooltip helpKey="taxonomy.terms" side="left" />
        </div>
      </div>

      {/* Facet sections */}
      {grouped.length === 0 ? (
        <div className="text-center py-12">
          <Tag className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-muted-foreground">
            {search ? 'No terms match your search' : 'No terms yet — add the first one'}
          </p>
          {!search && (
            <Button size="sm" className="mt-4" onClick={() => setShowAddDialog(true)}>
              <Plus className="w-4 h-4 mr-1.5" />
              Add Term
            </Button>
          )}
        </div>
      ) : (
        <div className={cn('divide-y divide-border/40')}>
          {grouped.map(([facet, facetTerms]) => (
            <FacetSection
              key={facet}
              facet={facet}
              terms={facetTerms}
              taxonomyId={taxonomyId}
              onTermDeleted={handleTermDeleted}
              onTermUpdated={handleTermUpdated}
            />
          ))}
        </div>
      )}

      <AddTermDialog
        open={showAddDialog}
        onOpenChange={setShowAddDialog}
        taxonomyId={taxonomyId}
        onTermAdded={handleTermAdded}
      />
    </div>
  )
}
