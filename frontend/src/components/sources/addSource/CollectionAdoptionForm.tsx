import { useState, useEffect, useCallback } from 'react'
import { Loader2, Database, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DialogFooter } from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  sourcesApi,
  Source,
  QdrantCollectionInfo,
  AdoptCollectionRequest,
} from '../../../services/api'
import EnrichmentSection from './EnrichmentSection'

interface CollectionAdoptionFormProps {
  onSourceAdded: (source: Source) => void
  onError: (error: string) => void
  onClose: () => void
}

export default function CollectionAdoptionForm({
  onSourceAdded,
  onError,
  onClose,
}: CollectionAdoptionFormProps) {
  const [collections, setCollections] = useState<QdrantCollectionInfo[]>([])
  const [loadingCollections, setLoadingCollections] = useState(true)
  const [selectedCollection, setSelectedCollection] = useState<QdrantCollectionInfo | null>(null)
  const [adoptName, setAdoptName] = useState('')
  const [adoptDescription, setAdoptDescription] = useState('')
  const [adoptProvider, setAdoptProvider] = useState('ollama')
  const [adoptModel, setAdoptModel] = useState('mxbai-embed-large')
  const [adoptDimensions, setAdoptDimensions] = useState(1024)
  const [adopting, setAdopting] = useState(false)
  const [enrichmentEnabled, setEnrichmentEnabled] = useState(false)
  const [enrichmentTaxonomyId, setEnrichmentTaxonomyId] = useState('')
  const [enrichmentModel, setEnrichmentModel] = useState('')

  const loadCollections = useCallback(async () => {
    try {
      setLoadingCollections(true)
      const response = await sourcesApi.listCollections(true)
      setCollections(response.collections.filter((c) => !c.is_linked))
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load collections')
    } finally {
      setLoadingCollections(false)
    }
  }, [onError])

  useEffect(() => {
    loadCollections()
  }, [loadCollections])

  const handleAdoptCollection = async () => {
    if (!selectedCollection || !adoptName.trim()) return

    try {
      setAdopting(true)
      const request: AdoptCollectionRequest = {
        name: adoptName.trim(),
        collection_name: selectedCollection.name,
        description: adoptDescription.trim() || undefined,
        embedding_provider: adoptProvider,
        embedding_model: adoptModel,
        embedding_dimensions: adoptDimensions,
        enrichment_enabled: enrichmentEnabled,
        enrichment_taxonomy_id:
          enrichmentEnabled && enrichmentTaxonomyId ? enrichmentTaxonomyId : null,
        enrichment_model:
          enrichmentEnabled && enrichmentModel ? enrichmentModel : null,
      }
      const created = await sourcesApi.adoptCollection(request)
      // Adoption doesn't index, so when enrichment is enabled we kick off a
      // re-enrichment of the existing chunks against the chosen taxonomy.
      if (enrichmentEnabled && enrichmentTaxonomyId) {
        try {
          await sourcesApi.reEnrich(created.id)
        } catch (reErr) {
          // Don't block the adopt success path; surface separately.
          onError(
            `Source adopted, but failed to queue re-enrichment: ${
              reErr instanceof Error ? reErr.message : String(reErr)
            }`
          )
        }
      }
      onSourceAdded(created)
      onClose()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to adopt collection')
    } finally {
      setAdopting(false)
    }
  }

  if (loadingCollections) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Loading collections...</span>
      </div>
    )
  }

  if (collections.length === 0) {
    return (
      <div className="space-y-4 py-4">
        <div className="text-center py-8 text-muted-foreground">
          <Database className="w-12 h-12 mx-auto mb-2 opacity-50" />
          <p>No unlinked collections found in Qdrant.</p>
          <p className="text-sm mt-1">
            All existing collections are already linked to sources.
          </p>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </DialogFooter>
      </div>
    )
  }

  return (
    <div className="space-y-4 py-4">
      {/* Collection selection */}
      <div className="space-y-2">
        <Label>Select Collection</Label>
        <Select
          value={selectedCollection?.name || ''}
          onValueChange={(name) => {
            const coll = collections.find((c) => c.name === name)
            setSelectedCollection(coll || null)
            if (coll && coll.vector_size) {
              setAdoptDimensions(coll.vector_size)
            }
          }}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select a collection..." />
          </SelectTrigger>
          <SelectContent className="z-[100]">
            {collections.map((coll) => (
              <SelectItem key={coll.name} value={coll.name}>
                {coll.name} ({coll.points_count.toLocaleString()} chunks{coll.vector_size ? `, ${coll.vector_size}d` : ''})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {selectedCollection && (
        <>
          {/* Collection info */}
          <div className="p-3 bg-muted/50 rounded-lg text-sm">
            <div className="flex items-center gap-2 mb-2">
              <Database className="w-4 h-4 text-primary" />
              <span className="font-medium font-mono">
                {selectedCollection.name}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-muted-foreground text-xs">
              <div>Chunks: {selectedCollection.points_count.toLocaleString()}</div>
              {selectedCollection.vector_size && (
                <div>Dimensions: {selectedCollection.vector_size}</div>
              )}
            </div>
          </div>

          {/* Source name */}
          <div className="space-y-2">
            <Label htmlFor="adopt-name">Source Name</Label>
            <Input
              id="adopt-name"
              value={adoptName}
              onChange={(e) => setAdoptName(e.target.value)}
              placeholder="e.g., API Documentation"
            />
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="adopt-description">Description (optional)</Label>
            <Textarea
              id="adopt-description"
              value={adoptDescription}
              onChange={(e) => setAdoptDescription(e.target.value)}
              placeholder="Brief description of this source"
              rows={2}
            />
          </div>

          {/* Embedding configuration */}
          <div className="border rounded-lg p-3 space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <AlertTriangle className="w-4 h-4 text-yellow-500" />
              Embedding Configuration
            </div>
            <p className="text-xs text-muted-foreground">
              Specify the embedding model used to create this collection.
              Incorrect settings will cause search failures.
            </p>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="adopt-provider" className="text-xs">
                  Provider
                </Label>
                <Select value={adoptProvider} onValueChange={setAdoptProvider}>
                  <SelectTrigger id="adopt-provider">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="z-[100]">
                    <SelectItem value="ollama">Ollama</SelectItem>
                    <SelectItem value="openai">OpenAI</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1">
                <Label htmlFor="adopt-model" className="text-xs">
                  Model
                </Label>
                <Input
                  id="adopt-model"
                  value={adoptModel}
                  onChange={(e) => setAdoptModel(e.target.value)}
                  placeholder="mxbai-embed-large"
                  className="font-mono text-sm"
                />
              </div>
            </div>

            <div className="space-y-1">
              <Label htmlFor="adopt-dimensions" className="text-xs">
                Dimensions
              </Label>
              <Input
                id="adopt-dimensions"
                type="number"
                value={adoptDimensions}
                onChange={(e) =>
                  setAdoptDimensions(parseInt(e.target.value) || 0)
                }
                placeholder="1024"
              />
              <p className="text-xs text-muted-foreground">
                Common: mxbai-embed-large=1024, text-embedding-3-small=1536
              </p>
            </div>
          </div>

          <EnrichmentSection
            enrichmentEnabled={enrichmentEnabled}
            setEnrichmentEnabled={setEnrichmentEnabled}
            taxonomyId={enrichmentTaxonomyId}
            setTaxonomyId={setEnrichmentTaxonomyId}
            model={enrichmentModel}
            setModel={setEnrichmentModel}
          />
        </>
      )}

      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button
          onClick={handleAdoptCollection}
          disabled={
            !selectedCollection ||
            !adoptName.trim() ||
            adopting ||
            (enrichmentEnabled && !enrichmentTaxonomyId)
          }
        >
          {adopting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
          Adopt Collection
        </Button>
      </DialogFooter>
    </div>
  )
}
