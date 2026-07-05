/**
 * Create, Edit, and Delete dialogs for taxonomies
 */
import { useState, useEffect } from 'react'
import { Loader2 } from 'lucide-react'
import { taxonomyApi } from '../../services/api/taxonomy'
import type { Taxonomy } from '../../services/api/types/taxonomy'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'

// ─── Create Dialog ────────────────────────────────────────────────────────────

interface CreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (taxonomy: Taxonomy) => void
}

export function CreateTaxonomyDialog({ open, onOpenChange, onCreated }: CreateDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setName('')
    setDescription('')
    setError(null)
  }

  const handleCreate = async () => {
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      const taxonomy = await taxonomyApi.create({
        name: name.trim(),
        description: description.trim() || undefined,
      })
      onCreated(taxonomy)
      reset()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create taxonomy')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o) }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Taxonomy</DialogTitle>
          <DialogDescription>
            Create a structured vocabulary for classifying documents.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="space-y-1.5">
            <Label htmlFor="tax-name">Name</Label>
            <Input
              id="tax-name"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Product Taxonomy"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tax-desc">Description</Label>
            <Input
              id="tax-desc"
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="What this taxonomy classifies"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => { reset(); onOpenChange(false) }}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={saving || !name.trim()}>
            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Create Taxonomy
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── Edit Dialog ──────────────────────────────────────────────────────────────

interface EditDialogProps {
  taxonomy: Taxonomy | null
  onClose: () => void
  onSaved: (taxonomy: Taxonomy) => void
}

export function EditTaxonomyDialog({ taxonomy, onClose, onSaved }: EditDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (taxonomy) {
      setName(taxonomy.name)
      setDescription(taxonomy.description ?? '')
      
      setError(null)
    }
  }, [taxonomy])

  const handleSave = async () => {
    if (!taxonomy || !name.trim()) return
    setSaving(true)
    setError(null)
    try {
      const updated = await taxonomyApi.update(taxonomy.id, {
        name: name.trim(),
        description: description.trim() || undefined,
      })
      onSaved(updated)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={!!taxonomy} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Taxonomy</DialogTitle>
          <DialogDescription>Update the taxonomy name or description.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="space-y-1.5">
            <Label htmlFor="edit-tax-name">Name</Label>
            <Input
              id="edit-tax-name"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="edit-tax-desc">Description</Label>
            <Input
              id="edit-tax-desc"
              value={description}
              onChange={e => setDescription(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving || !name.trim()}>
            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── Delete Confirmation ──────────────────────────────────────────────────────

interface DeleteDialogProps {
  taxonomy: Taxonomy | null
  onClose: () => void
  onDeleted: (id: string) => void
}

export function DeleteTaxonomyDialog({ taxonomy, onClose, onDeleted }: DeleteDialogProps) {
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleDelete = async () => {
    if (!taxonomy) return
    setDeleting(true)
    setError(null)
    try {
      await taxonomyApi.delete(taxonomy.id)
      onDeleted(taxonomy.id)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Dialog open={!!taxonomy} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete Taxonomy</DialogTitle>
          <DialogDescription>
            This will permanently delete{' '}
            <strong className="text-foreground">{taxonomy?.name}</strong> and all its
            terms. This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        {error && <p className="text-sm text-destructive mb-4">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
            {deleting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
