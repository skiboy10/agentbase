import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Switch } from '@/components/ui/switch'
import { DialogFooter } from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { sourcesApi, Source, SourceCreate } from '../../../services/api'
import EmbeddingModelSelector from './EmbeddingModelSelector'
import EnrichmentSection from './EnrichmentSection'
import WatcherSection from './WatcherSection'
import { UseEmbeddingConfigResult } from './hooks/useEmbeddingConfig'

interface DirectorySourceFormProps {
  embedding: UseEmbeddingConfigResult
  onSourceAdded: (source: Source) => void
  onError: (error: string) => void
  onClose: () => void
}

const COMMON_EXTENSIONS = ['.pdf', '.pptx', '.docx', '.md', '.txt']

export default function DirectorySourceForm({
  embedding,
  onSourceAdded,
  onError,
  onClose,
}: DirectorySourceFormProps) {
  const [name, setName] = useState('')
  const [sourcePath, setSourcePath] = useState('')
  const [adding, setAdding] = useState(false)

  // Extension filter
  const [selectedExtensions, setSelectedExtensions] = useState<string[]>([])

  // Enrichment state
  const [enrichmentEnabled, setEnrichmentEnabled] = useState(false)
  const [enrichmentTaxonomyId, setEnrichmentTaxonomyId] = useState('')
  const [enrichmentModel, setEnrichmentModel] = useState('')

  // Watcher state
  const [watchEnabled, setWatchEnabled] = useState(false)
  const [watchMode, setWatchMode] = useState('auto')
  const [pollIntervalMinutes, setPollIntervalMinutes] = useState('5')
  const [debounceSeconds, setDebounceSeconds] = useState('60')
  const [maxFileSizeMb, setMaxFileSizeMb] = useState('50')

  // Sub-source mode: filtered view over an existing root directory source.
  // Roots and sub-sources share this form so the embedding/enrichment/watcher
  // sections are only shown when isSubSource is false.
  const [isSubSource, setIsSubSource] = useState(false)
  const [parentSourceId, setParentSourceId] = useState('')
  const [pathPrefix, setPathPrefix] = useState('')
  const [pathExcludesText, setPathExcludesText] = useState('')
  const [rootSources, setRootSources] = useState<Source[]>([])

  useEffect(() => {
    if (!isSubSource) return
    // Lazy-load the list of candidate root sources when the toggle flips on.
    sourcesApi
      .listSources()
      .then((all) => {
        setRootSources(
          all.filter((s) => s.source_type === 'directory' && !s.parent_source_id)
        )
      })
      .catch(() => {
        /* non-fatal — Select will show empty */
      })
  }, [isSubSource])

  const toggleExtension = (ext: string) => {
    setSelectedExtensions((prev) =>
      prev.includes(ext) ? prev.filter((e) => e !== ext) : [...prev, ext]
    )
  }

  const handleAddSource = async () => {
    if (isSubSource) {
      if (!name.trim() || !parentSourceId || !pathPrefix.trim()) return
    } else if (!name.trim() || !sourcePath.trim()) {
      return
    }

    try {
      setAdding(true)
      const excludesList = pathExcludesText
        .split('\n')
        .map((line) => line.trim())
        .filter((line) => line.length > 0)

      if (isSubSource) {
        // Sub-source: backend computes everything else from the parent root.
        const createPayload: SourceCreate = {
          name: name.trim(),
          source_type: 'directory',
          // source_path is ignored on the backend when parent_source_id is set,
          // but the API contract still requires a string. Pass the prefix.
          source_path: pathPrefix.trim(),
          parent_source_id: parentSourceId,
          path_prefix: pathPrefix.trim(),
          path_excludes: excludesList.length > 0 ? excludesList : undefined,
        }
        const created = await sourcesApi.addSource(createPayload)
        onSourceAdded(created)
        onClose()
        return
      }

      const embeddingParams = embedding.getEmbeddingParams()
      const createPayload: SourceCreate = {
        name: name.trim(),
        source_type: 'directory',
        source_path: sourcePath.trim(),
        embedding_provider: embeddingParams.provider,
        embedding_model: embeddingParams.model,
        // Enrichment
        enrichment_enabled: enrichmentEnabled,
        enrichment_taxonomy_id: enrichmentEnabled && enrichmentTaxonomyId ? enrichmentTaxonomyId : undefined,
        enrichment_model: enrichmentEnabled && enrichmentModel ? enrichmentModel : undefined,
        // Watcher
        watch_enabled: watchEnabled,
        watch_extensions: selectedExtensions.length > 0 ? selectedExtensions : undefined,
        watch_mode: watchEnabled ? watchMode : undefined,
        watch_poll_interval_seconds: watchEnabled
          ? parseInt(pollIntervalMinutes, 10) * 60
          : undefined,
        watch_debounce_seconds: watchEnabled ? parseInt(debounceSeconds, 10) : undefined,
        watch_max_file_size_mb: watchEnabled ? parseInt(maxFileSizeMb, 10) : undefined,
        path_excludes: excludesList.length > 0 ? excludesList : undefined,
      }
      const created = await sourcesApi.addSource(createPayload)
      onSourceAdded(created)
      onClose()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to add source')
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="space-y-4 py-4">
      {/* Sub-source toggle: choose between standalone root and filtered view */}
      <div className="flex items-center justify-between p-3 border rounded-lg">
        <div>
          <Label className="text-sm font-medium">Sub-source of existing root</Label>
          <p className="text-xs text-muted-foreground">
            Create a filtered view over an existing directory root instead of a new root.
            Sub-sources don't run their own watcher or index — they share the parent's chunks.
          </p>
        </div>
        <Switch checked={isSubSource} onCheckedChange={setIsSubSource} />
      </div>

      <div className="space-y-2">
        <Label htmlFor="source-name">Source Name</Label>
        <Input
          id="source-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={
            isSubSource ? 'e.g., ACME Q4 Plan' : 'e.g., Product Documentation'
          }
        />
      </div>

      {isSubSource ? (
        <>
          <div className="space-y-2">
            <Label htmlFor="parent-root">Parent Root</Label>
            <Select value={parentSourceId} onValueChange={setParentSourceId}>
              <SelectTrigger id="parent-root">
                <SelectValue placeholder="Select a directory root..." />
              </SelectTrigger>
              <SelectContent>
                {rootSources.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name} ({s.source_path})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="path-prefix">Path Prefix</Label>
            <Input
              id="path-prefix"
              value={pathPrefix}
              onChange={(e) => setPathPrefix(e.target.value)}
              placeholder="/data/documents/acme/q4-plan"
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Must sit under the parent root. Queries against this sub-source
              return only chunks whose folder ancestors include this path.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="path-excludes-sub">Path Excludes (one per line)</Label>
            <textarea
              id="path-excludes-sub"
              value={pathExcludesText}
              onChange={(e) => setPathExcludesText(e.target.value)}
              placeholder="/data/documents/acme/q4-plan/drafts"
              className="w-full min-h-[60px] rounded-md border bg-background p-2 text-sm font-mono"
            />
          </div>
        </>
      ) : (
        <div className="space-y-2">
          <Label htmlFor="source-path">Directory Path</Label>
          <Input
            id="source-path"
            value={sourcePath}
            onChange={(e) => setSourcePath(e.target.value)}
            placeholder="/data/documents/my-docs"
            className="font-mono text-sm"
          />
          <p className="text-xs text-muted-foreground">
            Path inside the Docker container (e.g., /data/documents/...)
          </p>
        </div>
      )}

      {/* Root-only configuration — sub-sources inherit everything from their parent. */}
      {!isSubSource && (
        <>
          {/* File extension filter */}
          <div className="space-y-2">
            <Label className="text-sm">File Types</Label>
            <p className="text-xs text-muted-foreground">
              Filter to specific file types. Leave all unchecked to include all supported types.
            </p>
            <div className="flex flex-wrap gap-3">
              {COMMON_EXTENSIONS.map((ext) => (
                <div key={ext} className="flex items-center gap-1.5">
                  <Checkbox
                    id={`ext-${ext}`}
                    checked={selectedExtensions.includes(ext)}
                    onCheckedChange={() => toggleExtension(ext)}
                  />
                  <Label htmlFor={`ext-${ext}`} className="text-xs font-mono cursor-pointer">
                    {ext}
                  </Label>
                </div>
              ))}
            </div>
          </div>

          <EmbeddingModelSelector
            embeddingConfig={embedding.embeddingConfig}
            useCustomEmbedding={embedding.useCustomEmbedding}
            onUseCustomChange={embedding.setUseCustomEmbedding}
            selectedProvider={embedding.selectedProvider}
            onProviderChange={embedding.setSelectedProvider}
            selectedModel={embedding.selectedModel}
            onModelChange={embedding.setSelectedModel}
            idPrefix="dir-embed"
          />

          {/* Enrichment section */}
          <EnrichmentSection
            enrichmentEnabled={enrichmentEnabled}
            setEnrichmentEnabled={setEnrichmentEnabled}
            taxonomyId={enrichmentTaxonomyId}
            setTaxonomyId={setEnrichmentTaxonomyId}
            model={enrichmentModel}
            setModel={setEnrichmentModel}
          />

          {/* Watcher section */}
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

          {/* Root-level path excludes */}
          <div className="space-y-2">
            <Label htmlFor="path-excludes-root">Path Excludes (one per line)</Label>
            <textarea
              id="path-excludes-root"
              value={pathExcludesText}
              onChange={(e) => setPathExcludesText(e.target.value)}
              placeholder="/data/documents/private"
              className="w-full min-h-[60px] rounded-md border bg-background p-2 text-sm font-mono"
            />
            <p className="text-xs text-muted-foreground">
              Subfolders under this root that the watcher skips and that
              searches against this source filter out.
            </p>
          </div>
        </>
      )}

      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button
          onClick={handleAddSource}
          disabled={
            !name.trim() ||
            (isSubSource ? !parentSourceId || !pathPrefix.trim() : !sourcePath.trim()) ||
            adding ||
            (!isSubSource && enrichmentEnabled && !enrichmentTaxonomyId)
          }
        >
          {adding && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
          Add Source
        </Button>
      </DialogFooter>
    </div>
  )
}
