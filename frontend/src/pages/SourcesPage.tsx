import { useState } from 'react'
import { Database, Upload } from 'lucide-react'
import { cn } from '../lib/utils'
import type { Source } from '../services/api/types/sources'
import {
  AddSourceDialog,
  EditSourceDialog,
  ManageURLsDialog,
  RefreshSourceDialog,
} from '../components/sources'
import { SourcesTab, SearchTab } from '../components/sources/tabs'
import { useSources } from '../hooks/useSources'
import { useSourcesSearch } from '../hooks/useSourcesSearch'
import { PageHeader, ErrorBanner, StatsGrid, WorkflowHint } from '@/components'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

export default function SourcesPage() {
  const {
    sources,
    loading,
    error,
    setError,
    qdrantHealth,
    deleting,
    deleteConfirmId,
    setDeleteConfirmId,
    confirmDeleteSource,
    handleIndexSource,
    handleDeleteSource,
    handleRetryFailed,
    handleSourceAdded,
    handleSourceUpdated,
    handleRefreshStarted,
  } = useSources(null)

  const {
    sourcesQuery,
    setSourcesQuery,
    sourcesResults,
    searching,
    handleSourcesSearch,
    handleClearSearch,
    sourcesFilters,
    setSourcesFilters,
    hasActiveFilters,
  } = useSourcesSearch(null, setError)

  // Modal state
  const [showAddModal, setShowAddModal] = useState(false)
  const [editSource, setEditSource] = useState<Source | null>(null)
  const [urlManageSource, setUrlManageSource] = useState<Source | null>(null)
  const [refreshSource, setRefreshSource] = useState<Source | null>(null)

  if (loading) {
    return (
      <div className="p-6 h-full overflow-y-auto" role="status" aria-busy="true">
        <span className="sr-only">Loading sources…</span>
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="space-y-2">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-4 w-72" />
          </div>
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg" />
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        <PageHeader
          title="Sources"
          description="Ingest, index, and manage the documents that power agent knowledge retrieval"
          helpKey="sources.page"
          action={{ label: 'Add Source', icon: <Upload className="w-5 h-5 mr-2" />, onClick: () => setShowAddModal(true) }}
          extra={
            <div className="space-y-2">
              <WorkflowHint />
              {qdrantHealth && (
                <div className={cn(
                  'p-3 rounded-lg text-sm flex items-center gap-2',
                  qdrantHealth.healthy
                    ? 'bg-status-success/15 text-status-success-foreground'
                    : 'bg-destructive/30 text-destructive'
                )}>
                  <Database className="w-4 h-4" />
                  Qdrant: {qdrantHealth.message}
                </div>
              )}
            </div>
          }
        />

        {/* Sub-sources are filtered *views* over their parent root's documents and
            chunks, so their counts overlap the parent's — sum only root sources to
            avoid inflating the document/chunk totals. */}
        <StatsGrid stats={[
          { label: 'Sources', value: sources.length },
          { label: 'Documents', value: sources.reduce((acc, s) => acc + (s.parent_source_id ? 0 : s.document_count), 0) },
          { label: 'Chunks', value: sources.reduce((acc, s) => acc + (s.parent_source_id ? 0 : s.chunk_count), 0), helpKey: 'sources.chunks' },
        ]} />

        {/* Tab Structure */}
        <Tabs defaultValue="sources">
          <TabsList className="mb-6">
            <TabsTrigger value="sources">Sources</TabsTrigger>
            <TabsTrigger value="search">Search Test</TabsTrigger>
          </TabsList>

          <TabsContent value="sources">
            <SourcesTab
              sources={sources}
              loading={loading}
              deleting={deleting}
              onAddSource={() => setShowAddModal(true)}
              onEdit={setEditSource}
              onManageUrls={setUrlManageSource}
              onRefresh={setRefreshSource}
              onIndex={handleIndexSource}
              onDelete={handleDeleteSource}
              onRetryFailed={handleRetryFailed}
              onForceSync={handleIndexSource}
              onReEnrich={handleIndexSource}
            />
          </TabsContent>

          <TabsContent value="search">
            <SearchTab
              sourcesQuery={sourcesQuery}
              onQueryChange={setSourcesQuery}
              sourcesResults={sourcesResults}
              searching={searching}
              sourcesFilters={sourcesFilters}
              onFiltersChange={setSourcesFilters}
              hasActiveFilters={hasActiveFilters}
              onSearch={handleSourcesSearch}
              onClear={handleClearSearch}
            />
          </TabsContent>
        </Tabs>

        {/* Dialogs */}
        <AddSourceDialog
          open={showAddModal}
          onOpenChange={setShowAddModal}
          onSourceAdded={handleSourceAdded}
          onError={setError}
        />

        <EditSourceDialog
          source={editSource}
          onClose={() => setEditSource(null)}
          onSaved={handleSourceUpdated}
          onError={setError}
        />

        <ManageURLsDialog
          source={urlManageSource}
          onClose={() => setUrlManageSource(null)}
          onUpdated={handleSourceUpdated}
          onError={setError}
        />

        <RefreshSourceDialog
          source={refreshSource}
          onClose={() => setRefreshSource(null)}
          onRefreshStarted={handleRefreshStarted}
          onError={setError}
        />

        {/* Delete confirmation */}
        <AlertDialog open={!!deleteConfirmId} onOpenChange={(open) => !open && setDeleteConfirmId(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete Source</AlertDialogTitle>
              <AlertDialogDescription>
                This will permanently delete this source and all its indexed documents and chunks. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={confirmDeleteSource} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  )
}
