import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Trash2,
  AlertTriangle,
  Loader2,
  Cpu,
  BarChart3,
} from 'lucide-react'
import { libraryApi } from '../../services/api/library'
import type { Library } from '../../services/api/types/library'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface SettingsTabProps {
  kb: Library
  onKbUpdated: (kb: Library) => void
  onError: (msg: string) => void
}

export default function SettingsTab({ kb, onKbUpdated, onError }: SettingsTabProps) {
  const navigate = useNavigate()

  const [recalcLoading, setRecalcLoading] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)

  const handleRecalcStats = async () => {
    try {
      setRecalcLoading(true)
      const updated = await libraryApi.recalcStats(kb.id)
      onKbUpdated(updated)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to recalculate stats')
    } finally {
      setRecalcLoading(false)
    }
  }

  const handleDeleteKB = async () => {
    try {
      setDeleteLoading(true)
      await libraryApi.deleteLibrary(kb.id)
      navigate('/libraries', { replace: true })
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to delete library')
      setDeleteLoading(false)
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Embedding model */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <Cpu className="w-4 h-4 text-emerald-400" />
            Embedding Model
          </CardTitle>
          <CardDescription className="text-xs">
            The embedding model used to index and search this library. Read-only.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {kb.embedding_provider && kb.embedding_model ? (
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="font-mono text-xs text-emerald-400 border-emerald-400/40">
                {kb.embedding_provider}/{kb.embedding_model}
              </Badge>
              {kb.embedding_dimensions && (
                <Badge variant="secondary" className="text-xs font-mono">
                  {kb.embedding_dimensions}d
                </Badge>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground/60">No embedding model configured.</p>
          )}
        </CardContent>
      </Card>

      {/* Operations */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Operations</CardTitle>
          <CardDescription className="text-xs">
            Maintenance actions for this library.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-foreground">Recalculate Stats</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Refresh the document and chunk counts shown in the header.
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={handleRecalcStats}
              disabled={recalcLoading}
              className="shrink-0"
            >
              {recalcLoading
                ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
                : <BarChart3 className="w-3.5 h-3.5 mr-1.5" />
              }
              Recalculate
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Danger zone */}
      <Card className="border-destructive/40">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm text-destructive flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            Danger Zone
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-foreground">Delete Library</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Permanently delete this library and all its indexed data.
                Attached sources will not be deleted from the Sources page.
              </p>
            </div>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => setShowDeleteDialog(true)}
              className="shrink-0"
            >
              <Trash2 className="w-3.5 h-3.5 mr-1.5" />
              Delete KB
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Delete confirmation */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-destructive" />
              Delete Library
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to permanently delete <strong>{kb.name}</strong>?
              All indexed data will be removed. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowDeleteDialog(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteKB} disabled={deleteLoading}>
              {deleteLoading && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Delete Permanently
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
