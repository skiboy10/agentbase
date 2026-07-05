import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Loader2, Search } from 'lucide-react'
import { taxonomyApi } from '../services/api/taxonomy'
import type { Taxonomy } from '../services/api/types/taxonomy'
import {
  TaxonomyCard,
  CreateTaxonomyDialog,
  EditTaxonomyDialog,
  DeleteTaxonomyDialog,
} from '../components/taxonomy'
import { PageHeader, ErrorBanner, StatsGrid, WorkflowHint } from '@/components'
import { HelpTooltip } from '@/components/HelpTooltip'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { CheckCircle2, FileStack, Tags as TagsIcon } from 'lucide-react'

export default function TaxonomyPage() {
  const navigate = useNavigate()
  const [taxonomies, setTaxonomies] = useState<Taxonomy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  // Dialog state
  const [showCreate, setShowCreate] = useState(false)
  const [editTarget, setEditTarget] = useState<Taxonomy | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Taxonomy | null>(null)

  const fetchTaxonomies = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await taxonomyApi.list()
      setTaxonomies(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load taxonomies')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchTaxonomies() }, [fetchTaxonomies])

  const filteredTaxonomies = useMemo(() => {
    if (!search.trim()) return taxonomies
    const q = search.toLowerCase()
    return taxonomies.filter(
      t =>
        t.name.toLowerCase().includes(q) ||
        (t.description ?? '').toLowerCase().includes(q)
    )
  }, [taxonomies, search])

  const totalTerms = taxonomies.reduce((acc, t) => acc + (t.term_count ?? 0), 0)

  const handleCreated = (taxonomy: Taxonomy) => {
    setTaxonomies(prev => [taxonomy, ...prev])
  }

  const handleSaved = (updated: Taxonomy) => {
    setTaxonomies(prev => prev.map(t => t.id === updated.id ? updated : t))
  }

  const handleDeleted = (id: string) => {
    setTaxonomies(prev => prev.filter(t => t.id !== id))
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        <PageHeader
          title="Taxonomy"
          description="Manage controlled vocabularies for classifying and enriching documents."
          helpKey="taxonomy.page"
          action={{ label: 'New Taxonomy', icon: <Plus className="w-4 h-4 mr-2" />, onClick: () => setShowCreate(true) }}
          extra={<WorkflowHint />}
        />

        {!loading && (
          <StatsGrid stats={[
            { label: 'Taxonomies', value: taxonomies.length },
            { label: 'Total Terms', value: totalTerms },
            { label: 'Avg Terms / Taxonomy', value: taxonomies.length > 0 ? Math.round(totalTerms / taxonomies.length) : 0 },
          ]} />
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        )}

        {!loading && (
          <>
            {/* Search bar */}
            {taxonomies.length > 0 && (
              <div className="flex items-center gap-4 mb-6">
                <div className="relative flex-1 max-w-xs">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    placeholder="Search taxonomies..."
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    className="pl-9"
                  />
                </div>
                <span className="text-sm text-muted-foreground ml-auto">
                  {filteredTaxonomies.length} taxonomy{filteredTaxonomies.length !== 1 ? 's' : ''}
                </span>
              </div>
            )}

            {/* Taxonomy list */}
            {filteredTaxonomies.length > 0 && (
              <div className="space-y-4">
                {filteredTaxonomies.map((taxonomy) => (
                  <TaxonomyCard
                    key={taxonomy.id}
                    taxonomy={taxonomy}
                    onViewDetails={t => navigate(`/taxonomy/${t.id}`)}
                    onEdit={setEditTarget}
                    onDelete={setDeleteTarget}
                  />
                ))}
              </div>
            )}

            {/* Search empty state */}
            {filteredTaxonomies.length === 0 && taxonomies.length > 0 && (
              <div className="text-center py-8">
                <p className="text-muted-foreground">No taxonomies match your search</p>
              </div>
            )}

            {/* No taxonomies at all — getting-started card */}
            {taxonomies.length === 0 && (
              <div className="mt-4 space-y-6">
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <TagsIcon className="w-5 h-5 text-primary" />
                      Getting started with taxonomies
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-3">
                      <div className="flex items-start gap-3">
                        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-semibold">1</div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <TagsIcon className="w-3.5 h-3.5 text-muted-foreground" />
                            <span className="text-sm font-medium text-foreground">Create a taxonomy</span>
                            <HelpTooltip helpKey="taxonomy.what" side="right" />
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">Give it a name and a short description for the domain it will cover.</p>
                        </div>
                      </div>
                      <div className="flex items-start gap-3">
                        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-semibold">2</div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <TagsIcon className="w-3.5 h-3.5 text-muted-foreground" />
                            <span className="text-sm font-medium text-foreground">Add facets and terms with keywords</span>
                            <HelpTooltip helpKey="taxonomy.facets" side="right" />
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">Organise terms into facets such as Platform, Product, or Topic. Add keywords so the classifier knows what to look for.</p>
                        </div>
                      </div>
                      <div className="flex items-start gap-3">
                        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-semibold">3</div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <FileStack className="w-3.5 h-3.5 text-muted-foreground" />
                            <span className="text-sm font-medium text-foreground">Index and enrich sources</span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">Go to Sources and run enrichment. The LLM will classify each chunk against your taxonomy terms.</p>
                        </div>
                      </div>
                      <div className="flex items-start gap-3">
                        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-semibold">4</div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <CheckCircle2 className="w-3.5 h-3.5 text-muted-foreground" />
                            <span className="text-sm font-medium text-foreground">Review suggestions and check coverage</span>
                            <HelpTooltip helpKey="taxonomy.suggestions" side="right" />
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">Approve or reject LLM-proposed terms, then check the Coverage tab to see how well documents are classified.</p>
                        </div>
                      </div>
                    </div>
                    <div className="mt-5 pt-4 border-t border-border">
                      <Button onClick={() => setShowCreate(true)}>
                        <Plus className="w-4 h-4 mr-1.5" />
                        New Taxonomy
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}
          </>
        )}

        {/* Dialogs */}
        <CreateTaxonomyDialog
          open={showCreate}
          onOpenChange={setShowCreate}
          onCreated={handleCreated}
        />
        <EditTaxonomyDialog
          taxonomy={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={handleSaved}
        />
        <DeleteTaxonomyDialog
          taxonomy={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onDeleted={handleDeleted}
        />
      </div>
    </div>
  )
}
