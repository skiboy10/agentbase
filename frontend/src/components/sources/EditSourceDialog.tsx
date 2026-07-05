import { useState, useEffect } from 'react'
import { Loader2, Play, Square, RefreshCw, AlertTriangle } from 'lucide-react'
import { sourcesApi, Source } from '../../services/api'
import { watchStatusMeta } from '@/lib/status'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import WatcherSection from './addSource/WatcherSection'
import EnrichmentSection from './addSource/EnrichmentSection'
import WatcherActivityDrawer from './WatcherActivityDrawer'

interface EditSourceDialogProps {
  source: Source | null
  onClose: () => void
  onSaved: (source: Source) => void
  onError: (error: string) => void
  initialFocus?: 'watcher'
}

export default function EditSourceDialog({
  source,
  onClose,
  onSaved,
  onError,
  initialFocus,
}: EditSourceDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)

  // Watcher config state
  const [watchEnabled, setWatchEnabled] = useState(false)
  const [watchMode, setWatchMode] = useState('auto')
  const [pollIntervalMinutes, setPollIntervalMinutes] = useState('5')
  const [debounceSeconds, setDebounceSeconds] = useState('30')
  const [maxFileSizeMb, setMaxFileSizeMb] = useState('50')

  // Enrichment config state
  const [enrichmentEnabled, setEnrichmentEnabled] = useState(false)
  const [enrichmentTaxonomyId, setEnrichmentTaxonomyId] = useState('')
  const [enrichmentModel, setEnrichmentModel] = useState('')

  // Watcher control state
  const [watcherAction, setWatcherAction] = useState<'start' | 'stop' | 'sync' | null>(null)
  const [watcherActionMsg, setWatcherActionMsg] = useState<string | null>(null)

  const isDirectory = source?.source_type === 'directory'

  useEffect(() => {
    if (source) {
      setName(source.name)
      setDescription(source.description || '')
      setWatchEnabled(source.watch_enabled)
      setWatchMode(source.watch_mode || 'auto')
      const pollSecs = source.watch_poll_interval_seconds ?? 300
      setPollIntervalMinutes(String(Math.round(pollSecs / 60)))
      setDebounceSeconds(String(source.watch_debounce_seconds ?? 30))
      setMaxFileSizeMb(String(source.watch_max_file_size_mb ?? 50))
      setEnrichmentEnabled(source.enrichment_enabled ?? false)
      setEnrichmentTaxonomyId(source.enrichment_taxonomy_id ?? '')
      setEnrichmentModel(source.enrichment_model ?? '')
    }
    // Reset action message when dialog opens
    setWatcherAction(null)
    setWatcherActionMsg(null)
  }, [source])

  // Auto-scroll to watcher section when opened with initialFocus="watcher"
  useEffect(() => {
    if (initialFocus === 'watcher' && source) {
      setTimeout(() => {
        const el = document.getElementById('edit-watcher-section')
        el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 150)
    }
  }, [initialFocus, source])

  const handleSave = async () => {
    if (!source) return

    try {
      setSaving(true)
      const payload: Parameters<typeof sourcesApi.updateSource>[1] = {
        name,
        description: description || undefined,
        enrichment_enabled: enrichmentEnabled,
        enrichment_taxonomy_id:
          enrichmentEnabled && enrichmentTaxonomyId ? enrichmentTaxonomyId : null,
        enrichment_model:
          enrichmentEnabled && enrichmentModel ? enrichmentModel : null,
      }

      if (isDirectory) {
        payload.watch_enabled = watchEnabled
        payload.watch_mode = watchMode
        payload.watch_poll_interval_seconds = parseInt(pollIntervalMinutes) * 60
        payload.watch_debounce_seconds = parseInt(debounceSeconds)
        payload.watch_max_file_size_mb = parseInt(maxFileSizeMb)
      }

      // Detect whether the enrichment config materially changed in a way
      // that requires reclassifying existing chunks.
      const needsReEnrich =
        enrichmentEnabled &&
        (enrichmentEnabled !== (source.enrichment_enabled ?? false) ||
          enrichmentTaxonomyId !== (source.enrichment_taxonomy_id ?? '') ||
          enrichmentModel !== (source.enrichment_model ?? ''))

      const updated = await sourcesApi.updateSource(source.id, payload)

      if (needsReEnrich) {
        try {
          await sourcesApi.reEnrich(source.id)
          setWatcherActionMsg(
            `Re-enrichment queued. ${
              updated.chunk_count?.toLocaleString() ?? '?'
            } chunks will be re-classified.`
          )
        } catch (reErr) {
          // Don't fail the whole save — the config was saved; surface the
          // re-enrich error separately so the user can retry via API or
          // a future re-enrich button.
          onError(
            `Source updated, but failed to queue re-enrichment: ${
              reErr instanceof Error ? reErr.message : String(reErr)
            }`
          )
        }
      }

      onSaved(updated)
      if (!needsReEnrich) onClose()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to update source')
    } finally {
      setSaving(false)
    }
  }

  const handleWatcherAction = async (action: 'start' | 'stop' | 'sync') => {
    if (!source) return
    setWatcherAction(action)
    setWatcherActionMsg(null)
    try {
      if (action === 'start') {
        await sourcesApi.startWatcher(source.id)
        setWatcherActionMsg('Watcher started.')
      } else if (action === 'stop') {
        await sourcesApi.stopWatcher(source.id)
        setWatcherActionMsg('Watcher stopped.')
      } else {
        const result = await sourcesApi.syncWatcher(source.id)
        const { new: n = 0, modified: m = 0, deleted: d = 0, unchanged: u = 0 } = result
        setWatcherActionMsg(`Sync complete: ${n} new, ${m} modified, ${d} deleted, ${u} unchanged.`)
      }
    } catch (err) {
      setWatcherActionMsg(err instanceof Error ? err.message : 'Action failed.')
    } finally {
      setWatcherAction(null)
    }
  }

  const isRunning = watchStatusMeta(source?.watch_status).variant === 'success'

  return (
    <Dialog open={!!source} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Source</DialogTitle>
          <DialogDescription>
            Update the name, description, and configuration for this source.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="edit-name">Name</Label>
            <Input
              id="edit-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Source name"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-description">Description (optional)</Label>
            <Textarea
              id="edit-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of this source"
              rows={3}
            />
          </div>

          {/* Enrichment — editable for any source type */}
          <Separator />
          <EnrichmentSection
            enrichmentEnabled={enrichmentEnabled}
            setEnrichmentEnabled={setEnrichmentEnabled}
            taxonomyId={enrichmentTaxonomyId}
            setTaxonomyId={setEnrichmentTaxonomyId}
            model={enrichmentModel}
            setModel={setEnrichmentModel}
          />

          {/* Editable watcher section for directory sources */}
          {isDirectory && (
            <>
              <Separator />
              <div id="edit-watcher-section" className="space-y-3">
                <Label className="text-muted-foreground">Directory Watcher</Label>
                <WatcherSection
                  watchEnabled={watchEnabled}
                  setWatchEnabled={setWatchEnabled}
                  watchMode={watchMode}
                  setWatchMode={setWatchMode}
                  pollIntervalMinutes={pollIntervalMinutes}
                  setPollIntervalMinutes={setPollIntervalMinutes}
                  debounceSeconds={debounceSeconds}
                  setDebounceSeconds={setDebounceSeconds}
                  maxFileSizeMb={maxFileSizeMb}
                  setMaxFileSizeMb={setMaxFileSizeMb}
                />

                {/* Last error alert */}
                {source?.watch_last_error && (
                  <Alert variant="destructive" className="py-2">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription className="text-xs ml-2">
                      {source.watch_last_error}
                    </AlertDescription>
                  </Alert>
                )}

                {/* Watcher control buttons */}
                <div className="flex items-center gap-2 flex-wrap">
                  <Label className="text-muted-foreground text-xs shrink-0">Controls:</Label>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!watchEnabled || !!watcherAction || isRunning}
                    onClick={() => handleWatcherAction('start')}
                    aria-label="Start watcher"
                  >
                    {watcherAction === 'start' ? (
                      <Loader2 className="w-3 h-3 animate-spin mr-1" />
                    ) : (
                      <Play className="w-3 h-3 mr-1" />
                    )}
                    Start
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!watchEnabled || !!watcherAction || !isRunning}
                    onClick={() => handleWatcherAction('stop')}
                    aria-label="Stop watcher"
                  >
                    {watcherAction === 'stop' ? (
                      <Loader2 className="w-3 h-3 animate-spin mr-1" />
                    ) : (
                      <Square className="w-3 h-3 mr-1" />
                    )}
                    Stop
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!watchEnabled || !!watcherAction}
                    onClick={() => handleWatcherAction('sync')}
                    aria-label="Force sync watcher"
                  >
                    {watcherAction === 'sync' ? (
                      <Loader2 className="w-3 h-3 animate-spin mr-1" />
                    ) : (
                      <RefreshCw className="w-3 h-3 mr-1" />
                    )}
                    Force Sync
                  </Button>
                </div>
                {watcherActionMsg && (
                  <p className="text-xs text-muted-foreground">{watcherActionMsg}</p>
                )}

                {/* Activity drawer — for sub-sources, show the parent root's activity */}
                {source && (
                  <WatcherActivityDrawer
                    sourceId={source.id}
                    parentSourceId={source.parent_source_id}
                  />
                )}
              </div>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={
              !name.trim() ||
              saving ||
              (enrichmentEnabled && !enrichmentTaxonomyId)
            }
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
            Save Changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
