import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
import { UseEmbeddingConfigResult } from './hooks/useEmbeddingConfig'

interface YoutubeSourceFormProps {
  embedding: UseEmbeddingConfigResult
  onSourceAdded: (source: Source) => void
  onError: (error: string) => void
  onClose: () => void
}

// Light client-side check; the backend enforces the real host allowlist + SSRF.
const looksLikeYoutubeUrl = (url: string) =>
  /(^https?:\/\/)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)\//i.test(url.trim())

export default function YoutubeSourceForm({
  embedding,
  onSourceAdded,
  onError,
  onClose,
}: YoutubeSourceFormProps) {
  const [name, setName] = useState('')
  const [channelUrl, setChannelUrl] = useState('')
  const [backfillMode, setBackfillMode] = useState<'all' | 'recent'>('recent')
  const [recentCount, setRecentCount] = useState('50')
  const [adding, setAdding] = useState(false)

  // Enrichment state (optional — same pattern as other source forms)
  const [enrichmentEnabled, setEnrichmentEnabled] = useState(false)
  const [enrichmentTaxonomyId, setEnrichmentTaxonomyId] = useState('')
  const [enrichmentModel, setEnrichmentModel] = useState('')

  const urlValid = looksLikeYoutubeUrl(channelUrl)

  const handleAddSource = async () => {
    if (!name.trim() || !channelUrl.trim() || !urlValid) return

    try {
      setAdding(true)
      const embeddingParams = embedding.getEmbeddingParams()
      const createPayload: SourceCreate = {
        name: name.trim(),
        source_type: 'youtube',
        source_path: channelUrl.trim(),
        embedding_provider: embeddingParams.provider,
        embedding_model: embeddingParams.model,
        youtube_backfill_mode: backfillMode,
        youtube_recent_count:
          backfillMode === 'recent' ? parseInt(recentCount, 10) || 50 : undefined,
        enrichment_enabled: enrichmentEnabled,
        enrichment_taxonomy_id:
          enrichmentEnabled && enrichmentTaxonomyId ? enrichmentTaxonomyId : undefined,
        enrichment_model:
          enrichmentEnabled && enrichmentModel ? enrichmentModel : undefined,
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
      <div className="space-y-2">
        <Label htmlFor="yt-name">Source Name</Label>
        <Input
          id="yt-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g., All-In Podcast"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="yt-url">Channel URL</Label>
        <Input
          id="yt-url"
          value={channelUrl}
          onChange={(e) => setChannelUrl(e.target.value)}
          placeholder="https://www.youtube.com/@channelname"
          className="font-mono text-sm"
        />
        <p className="text-xs text-muted-foreground">
          {channelUrl && !urlValid
            ? 'Enter a YouTube channel URL (youtube.com or youtu.be).'
            : 'One channel per source. New uploads are pulled automatically once a day.'}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="yt-backfill">Backfill</Label>
          <Select
            value={backfillMode}
            onValueChange={(v) => setBackfillMode(v as 'all' | 'recent')}
          >
            <SelectTrigger id="yt-backfill">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="recent">Recent videos only</SelectItem>
              <SelectItem value="all">All videos (full history)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {backfillMode === 'recent' && (
          <div className="space-y-2">
            <Label htmlFor="yt-count">How many</Label>
            <Input
              id="yt-count"
              type="number"
              min={1}
              value={recentCount}
              onChange={(e) => setRecentCount(e.target.value)}
            />
          </div>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {backfillMode === 'all'
          ? 'Pulls every video that has captions, oldest to newest. Large channels can take a while on the first index.'
          : 'Pulls the most recent N videos now; older ones are skipped. Videos without captions are skipped.'}
      </p>

      <EmbeddingModelSelector
        embeddingConfig={embedding.embeddingConfig}
        useCustomEmbedding={embedding.useCustomEmbedding}
        onUseCustomChange={embedding.setUseCustomEmbedding}
        selectedProvider={embedding.selectedProvider}
        onProviderChange={embedding.setSelectedProvider}
        selectedModel={embedding.selectedModel}
        onModelChange={embedding.setSelectedModel}
        idPrefix="yt-embed"
      />

      <EnrichmentSection
        enrichmentEnabled={enrichmentEnabled}
        setEnrichmentEnabled={setEnrichmentEnabled}
        taxonomyId={enrichmentTaxonomyId}
        setTaxonomyId={setEnrichmentTaxonomyId}
        model={enrichmentModel}
        setModel={setEnrichmentModel}
      />

      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button
          onClick={handleAddSource}
          disabled={
            !name.trim() ||
            !channelUrl.trim() ||
            !urlValid ||
            adding ||
            (enrichmentEnabled && !enrichmentTaxonomyId)
          }
        >
          {adding && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
          Add Source
        </Button>
      </DialogFooter>
    </div>
  )
}
