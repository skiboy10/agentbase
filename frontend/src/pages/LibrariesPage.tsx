import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Library,
  Plus,
  Loader2,
  MoreHorizontal,
  FileText,
  Layers,
  Database,
  RefreshCw,
  Trash2,
  ChevronRight,
} from 'lucide-react'
import { cn } from '../lib/utils'
import { statusClasses, libraryStatusVariant } from '../lib/status'
import { libraryApi } from '../services/api/library'
import { useVisiblePolling } from '../hooks/useVisiblePolling'
import { PageHeader, ErrorBanner, StatsGrid, EmptyState as SharedEmptyState, WorkflowHint } from '@/components'
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
import type { Library as LibraryData, LibraryCreate } from '../services/api/types/library'
import { configApi } from '../services/api/config'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function statusColor(status: string): string {
  return statusClasses(libraryStatusVariant(status)).badge
}

// ─── Create Dialog ─────────────────────────────────────────────────────────────

interface CreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (kb: LibraryData) => void
  onError: (msg: string) => void
}

function CreateDialog({ open, onOpenChange, onCreated, onError }: CreateDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [embeddingProvider, setEmbeddingProvider] = useState('')
  const [embeddingModel, setEmbeddingModel] = useState('')
  const [saving, setSaving] = useState(false)

  type EmbeddingEntry = { provider: string; model: string; dimensions: number }

  const [allModels, setAllModels] = useState<EmbeddingEntry[]>([])
  const [providers, setProviders] = useState<string[]>([])
  const [filteredModels, setFilteredModels] = useState<EmbeddingEntry[]>([])

  // Load embedding config on open
  useEffect(() => {
    if (!open) return
    configApi.getEmbeddingConfig().then(config => {
      const available = config.available_models || []
      setAllModels(available)
      const providerSet = new Set(available.map((m: EmbeddingEntry) => m.provider))
      setProviders(Array.from(providerSet))
    }).catch(() => {
      setProviders([])
    })
  }, [open])

  // Filter models when provider changes
  useEffect(() => {
    if (!embeddingProvider) {
      setFilteredModels([])
      setEmbeddingModel('')
      return
    }
    setFilteredModels(allModels.filter(m => m.provider === embeddingProvider))
    setEmbeddingModel('')
  }, [embeddingProvider, allModels])

  const handleSubmit = async () => {
    if (!name.trim()) { onError('Name is required'); return }
    if (!embeddingProvider) { onError('Embedding provider is required'); return }
    if (!embeddingModel) { onError('Embedding model is required'); return }

    const payload: LibraryCreate = {
      name: name.trim(),
      description: description.trim() || undefined,
      embedding_provider: embeddingProvider,
      embedding_model: embeddingModel,
    }

    try {
      setSaving(true)
      const kb = await libraryApi.create(payload)
      onCreated(kb)
      onOpenChange(false)
      // Reset
      setName('')
      setDescription('')
      setEmbeddingProvider('')
      setEmbeddingModel('')
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to create library')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New Library</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="kb-name">Name</Label>
            <Input
              id="kb-name"
              placeholder="e.g. Work Documents"
              value={name}
              onChange={e => setName(e.target.value)}
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="kb-desc">Description <span className="text-muted-foreground font-normal">(optional)</span></Label>
            <Textarea
              id="kb-desc"
              placeholder="What kind of content lives here?"
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={2}
              className="resize-none"
            />
          </div>

          <div className="space-y-1.5">
            <Label>Embedding Provider</Label>
            <Select value={embeddingProvider} onValueChange={setEmbeddingProvider}>
              <SelectTrigger>
                <SelectValue placeholder="Select provider" />
              </SelectTrigger>
              <SelectContent>
                {providers.map(p => (
                  <SelectItem key={p} value={p}>{p}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>Embedding Model</Label>
            <Select
              value={embeddingModel}
              onValueChange={setEmbeddingModel}
              disabled={!embeddingProvider || filteredModels.length === 0}
            >
              <SelectTrigger>
                <SelectValue placeholder={
                  !embeddingProvider ? 'Select provider first' :
                  filteredModels.length === 0 ? 'No models configured' :
                  'Select model'
                } />
              </SelectTrigger>
              <SelectContent>
                {filteredModels.map(m => (
                  <SelectItem key={m.model} value={m.model}>
                    <span>{m.model}</span>
                    {m.dimensions ? (
                      <span className="ml-2 text-xs text-muted-foreground">{m.dimensions}d</span>
                    ) : null}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Create Library
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── KB Row Card ───────────────────────────────────────────────────────────────

interface KBCardProps {
  kb: LibraryData
  onView: () => void
  onDelete: () => void
  onRecalculate: () => void
}

function KBCard({ kb, onView, onDelete, onRecalculate }: KBCardProps) {
  return (
    <div
      className="group flex items-center gap-4 px-5 py-4 bg-card border border-border rounded-lg hover:border-primary/40 hover:bg-card/80 transition-all duration-150 cursor-pointer"
      onClick={onView}
    >
      {/* Icon */}
      <div className="flex-shrink-0 w-9 h-9 rounded-md bg-primary/10 flex items-center justify-center">
        <Library className="w-4 h-4 text-primary" />
      </div>

      {/* Name + description */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground truncate">{kb.name}</span>
          <span className={cn(
            'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border',
            statusColor(kb.status)
          )}>
            {kb.status}
          </span>
        </div>
        {kb.description && (
          <p className="text-xs text-muted-foreground truncate mt-0.5">{kb.description}</p>
        )}
      </div>

      {/* Stats */}
      <div className="hidden sm:flex items-center gap-6 flex-shrink-0">
        <Stat
          icon={<Database className="w-3.5 h-3.5" />}
          label="sources"
          value={formatCount(kb.source_count)}
        />
        <Stat
          icon={<FileText className="w-3.5 h-3.5" />}
          label="docs"
          value={formatCount(kb.document_count)}
        />
        <Stat
          icon={<Layers className="w-3.5 h-3.5" />}
          label="chunks"
          value={formatCount(kb.chunk_count)}
        />
      </div>

      {/* Embedding model badge */}
      <div className="hidden lg:block flex-shrink-0">
        <Badge variant="outline" className="text-[11px] font-mono px-2 py-0.5 text-muted-foreground">
          {kb.embedding_model}
        </Badge>
      </div>

      {/* Updated */}
      <div className="hidden xl:block flex-shrink-0 w-28 text-right">
        <span className="text-xs text-muted-foreground">{formatDate(kb.updated_at)}</span>
      </div>

      {/* Actions */}
      <div
        className="flex-shrink-0 ml-1"
        onClick={e => e.stopPropagation()}
      >
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <MoreHorizontal className="w-4 h-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuItem onClick={onView}>
              <ChevronRight className="w-3.5 h-3.5 mr-2" />
              View
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onRecalculate}>
              <RefreshCw className="w-3.5 h-3.5 mr-2" />
              Recalculate Stats
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={onDelete}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="w-3.5 h-3.5 mr-2" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex flex-col items-end gap-0.5">
      <div className="flex items-center gap-1 text-foreground">
        <span className="text-muted-foreground">{icon}</span>
        <span className="text-sm font-semibold tabular-nums">{value}</span>
      </div>
      <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</span>
    </div>
  )
}

// ─── Empty State (uses shared component) ──────────────────────────────────────

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function LibrariesPage() {
  const navigate = useNavigate()

  const [kbs, setKbs] = useState<LibraryData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

  const fetchKbs = useCallback(async (opts?: { silent?: boolean }) => {
    try {
      // Background polling must not trigger the full-page loading spinner —
      // it unmounts the page (including an open Create dialog) and wipes form state.
      if (!opts?.silent) setLoading(true)
      setError(null)
      const data = await libraryApi.list()
      setKbs(data)
    } catch (err) {
      // Don't surface transient poll failures as a banner over an open form.
      if (!opts?.silent) setError(err instanceof Error ? err.message : 'Failed to load libraries')
    } finally {
      if (!opts?.silent) setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchKbs()
  }, [fetchKbs])

  // Stable reference — an inline arrow would change every render and, since
  // useVisiblePolling depends on it, reset the interval (and re-poll) constantly.
  const pollKbs = useCallback(() => fetchKbs({ silent: true }), [fetchKbs])

  useVisiblePolling(pollKbs, { intervalMs: 15000 })

  const handleCreated = (kb: LibraryData) => {
    setKbs(prev => [kb, ...prev])
  }

  const handleDelete = async () => {
    const targetId = deleteConfirmId
    if (!targetId) return
    setDeleteConfirmId(null)
    try {
      setDeletingId(targetId)
      await libraryApi.delete(targetId)
      setKbs(prev => prev.filter(k => k.id !== targetId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete library')
    } finally {
      setDeletingId(null)
    }
  }

  const handleRecalculate = async (id: string) => {
    try {
      const updated = await libraryApi.recalculateStats(id)
      setKbs(prev => prev.map(k => k.id === id ? updated : k))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to recalculate stats')
    }
  }

  // Aggregate stats
  const totalDocs = kbs.reduce((sum, kb) => sum + kb.document_count, 0)
  const totalChunks = kbs.reduce((sum, kb) => sum + kb.chunk_count, 0)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-7 h-7 text-primary animate-spin" />
      </div>
    )
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto">

        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        <PageHeader
          title="Libraries"
          description="Curated document collections for RAG retrieval"
          helpKey="libraries.page"
          action={{ label: 'New Library', icon: <Plus className="w-4 h-4 mr-2" />, onClick: () => setShowCreate(true) }}
          extra={<WorkflowHint />}
        />

        {kbs.length > 0 && (
          <StatsGrid stats={[
            { label: 'Libraries', value: kbs.length },
            { label: 'Total Documents', value: totalDocs },
            { label: 'Total Chunks', value: totalChunks, helpKey: 'libraries.chunks' },
          ]} />
        )}

        {/* List */}
        {kbs.length === 0 ? (
          <SharedEmptyState
            icon={<Library className="w-16 h-16" />}
            title="No libraries yet"
            description="Libraries organize your documents for RAG retrieval. Create one to get started."
            action={{ label: 'New Library', onClick: () => setShowCreate(true) }}
          />
        ) : (
          <div className="space-y-2">
            {/* Column headers */}
            <div className="hidden sm:flex items-center gap-4 px-5 pb-1">
              <div className="w-9 flex-shrink-0" />
              <div className="flex-1 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">Name</div>
              <div className="hidden sm:flex items-center gap-6 flex-shrink-0">
                <span className="w-10 text-[11px] font-medium text-muted-foreground uppercase tracking-wider text-right">Sources</span>
                <span className="w-10 text-[11px] font-medium text-muted-foreground uppercase tracking-wider text-right">Docs</span>
                <span className="w-12 text-[11px] font-medium text-muted-foreground uppercase tracking-wider text-right">Chunks</span>
              </div>
              <div className="hidden lg:block w-40 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">Model</div>
              <div className="hidden xl:block w-28 text-[11px] font-medium text-muted-foreground uppercase tracking-wider text-right">Updated</div>
              <div className="w-8 flex-shrink-0" />
            </div>

            {kbs.map(kb => (
              <div
                key={kb.id}
                className={cn(deletingId === kb.id && 'opacity-50 pointer-events-none')}
              >
                <KBCard
                  kb={kb}
                  onView={() => navigate(`/libraries/${kb.id}`)}
                  onDelete={() => setDeleteConfirmId(kb.id)}
                  onRecalculate={() => handleRecalculate(kb.id)}
                />
              </div>
            ))}
          </div>
        )}

        {/* Delete confirmation */}
        <AlertDialog open={!!deleteConfirmId} onOpenChange={(open) => !open && setDeleteConfirmId(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete Library</AlertDialogTitle>
              <AlertDialogDescription>
                This will permanently delete this library and all its document bindings. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Create dialog */}
        <CreateDialog
          open={showCreate}
          onOpenChange={setShowCreate}
          onCreated={handleCreated}
          onError={setError}
        />
      </div>
    </div>
  )
}
