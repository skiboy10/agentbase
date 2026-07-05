import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Database,
  Plus,
  Trash2,
  Loader2,
  AlertTriangle,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { getSourceTypeMeta } from '@/lib/sourceType'
import { libraryApi } from '../../services/api/library'
import type { LibrarySource } from '../../services/api/types/library'
import { useToast } from '@/hooks/use-toast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { SourcePicker, statusVariant } from './SourcePicker'

interface SourcesTabProps {
  kbId: string
  onError: (msg: string) => void
  onSourcesChanged?: () => Promise<void> | void
}

function formatDate(iso: string | null) {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export default function SourcesTab({ kbId, onError, onSourcesChanged }: SourcesTabProps) {
  const { toast } = useToast()
  const [sources, setSources] = useState<LibrarySource[]>([])
  const [loading, setLoading] = useState(true)

  // Add source dialog
  const [showAddDialog, setShowAddDialog] = useState(false)
  const [addSourceId, setAddSourceId] = useState('')
  const [addLoading, setAddLoading] = useState(false)

  // Remove confirmation
  const [removeTarget, setRemoveTarget] = useState<LibrarySource | null>(null)
  const [removing, setRemoving] = useState(false)

  const fetchSources = useCallback(async () => {
    try {
      setLoading(true)
      const data = await libraryApi.listSources(kbId)
      setSources(data)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load sources')
    } finally {
      setLoading(false)
    }
  }, [kbId, onError])

  useEffect(() => {
    fetchSources()
  }, [fetchSources])

  /** Set of source IDs already bound — passed to SourcePicker to mark as disabled. */
  const boundSourceIds = useMemo(() => new Set(sources.map(s => s.id)), [sources])

  const handleOpenAddDialog = () => {
    setAddSourceId('')
    setShowAddDialog(true)
  }

  const handleAddSource = async () => {
    if (!addSourceId.trim()) return
    try {
      setAddLoading(true)
      await libraryApi.addSource(kbId, { source_id: addSourceId.trim() })
      await fetchSources()
      await onSourcesChanged?.()
      setShowAddDialog(false)
      setAddSourceId('')
      toast({ title: 'Source added', description: 'The source has been attached to this library.' })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to add source'
      toast({ title: 'Failed to add source', description: message, variant: 'destructive' })
    } finally {
      setAddLoading(false)
    }
  }

  const handleRemoveSource = async () => {
    if (!removeTarget) return
    try {
      setRemoving(true)
      await libraryApi.removeSource(kbId, removeTarget.id)
      setSources(prev => prev.filter(s => s.id !== removeTarget.id))
      await onSourcesChanged?.()
      setRemoveTarget(null)
      toast({ title: 'Source removed', description: `"${removeTarget.name}" has been detached from this library.` })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to remove source'
      toast({ title: 'Failed to remove source', description: message, variant: 'destructive' })
    } finally {
      setRemoving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {sources.length} source{sources.length !== 1 ? 's' : ''} attached
        </p>
        <Button size="sm" onClick={handleOpenAddDialog}>
          <Plus className="w-4 h-4 mr-1.5" />
          Add Source
        </Button>
      </div>

      {/* Source list */}
      {sources.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground/60">
          <Database className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">No sources attached to this library.</p>
          <p className="text-xs mt-1">Add a source to begin indexing documents.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {sources.map(source => (
            <Card key={source.id}>
              <CardContent className="py-3 px-4">
                <div className="flex items-center gap-3">
                  {/* Icon */}
                  {(() => {
                    const meta = getSourceTypeMeta(source.source_type)
                    const Icon = meta.icon
                    return (
                      <div className={cn('w-8 h-8 rounded-md flex items-center justify-center shrink-0', meta.bg)}>
                        <Icon className={cn('w-4 h-4', meta.text)} />
                      </div>
                    )
                  })()}

                  {/* Main info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm text-foreground truncate">{source.name}</span>
                      <Badge variant={statusVariant(source.status)} className="text-xs shrink-0">
                        {source.status}
                      </Badge>
                      {source.watch_enabled && (
                        <Badge variant="outline" className="text-xs text-status-success border-status-success/40 shrink-0">
                          watching
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-4 mt-0.5 text-xs text-muted-foreground/70">
                      <span>{source.document_count} docs</span>
                      <span>{source.chunk_count} chunks</span>
                      <span>Last indexed: {formatDate(source.last_indexed)}</span>
                    </div>
                  </div>

                  {/* Remove */}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="shrink-0 text-muted-foreground hover:text-destructive"
                    onClick={() => setRemoveTarget(source)}
                    title="Remove source from library"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Add Source Dialog */}
      <Dialog open={showAddDialog} onOpenChange={open => { setShowAddDialog(open); if (!open) setAddSourceId('') }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Add Source</DialogTitle>
            <DialogDescription>
              Select a source to attach to this library. Sources already in this library are shown disabled.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <Label>Select source</Label>
            <SourcePicker
              boundSourceIds={boundSourceIds}
              value={addSourceId}
              onChange={setAddSourceId}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowAddDialog(false)}>Cancel</Button>
            <Button onClick={handleAddSource} disabled={addLoading || !addSourceId.trim()}>
              {addLoading && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Add Source
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Remove Confirmation Dialog */}
      <Dialog open={!!removeTarget} onOpenChange={open => !open && setRemoveTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-400" />
              Remove Source
            </DialogTitle>
            <DialogDescription>
              Remove <strong>{removeTarget?.name}</strong> from this library?
              The source itself will not be deleted — it will simply no longer be part of this library.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRemoveTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleRemoveSource} disabled={removing}>
              {removing && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
