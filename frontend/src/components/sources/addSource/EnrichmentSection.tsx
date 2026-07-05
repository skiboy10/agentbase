import { useEffect, useRef, useState } from 'react'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { taxonomyApi } from '../../../services/api/taxonomy'
import { providersApi } from '../../../services/api/providers'
import type { Taxonomy } from '../../../services/api/types/taxonomy'

interface EnrichmentSectionProps {
  enrichmentEnabled: boolean
  setEnrichmentEnabled: (value: boolean) => void
  taxonomyId: string
  setTaxonomyId: (value: string) => void
  model: string
  setModel: (value: string) => void
}

interface ModelOption {
  id: string
  provider: string
}

// Classification runs an instruction-following LLM. Embedding / reranker models
// are listed by the providers endpoint but can't classify, so filter them out.
const NON_CHAT_MODEL = /embed|rerank/i

// Preferred default provider for local classification.
const PREFERRED_PROVIDER = 'ollama'

export default function EnrichmentSection({
  enrichmentEnabled,
  setEnrichmentEnabled,
  taxonomyId,
  setTaxonomyId,
  model,
  setModel,
}: EnrichmentSectionProps) {
  const [taxonomies, setTaxonomies] = useState<Taxonomy[]>([])
  const [models, setModels] = useState<ModelOption[]>([])
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  // Tracks the latest model prop so the async default-selection below never
  // reads a stale closure value (e.g. the edit dialog populating an existing
  // source while the model list is still loading).
  const modelRef = useRef(model)
  modelRef.current = model

  useEffect(() => {
    if (!enrichmentEnabled || loaded) return
    let active = true
    setLoading(true)
    Promise.all([
      taxonomyApi.list().catch((e) => {
        console.error(e)
        return [] as Taxonomy[]
      }),
      providersApi
        .listModels()
        .then((data) =>
          data
            .filter((m) => !NON_CHAT_MODEL.test(m.id))
            .map((m) => ({ id: m.id, provider: m.provider || 'unknown' })),
        )
        .catch((e) => {
          console.error(e)
          return [] as ModelOption[]
        }),
    ])
      .then(([tax, mdls]) => {
        if (!active) return
        setTaxonomies(tax)
        setModels(mdls)
        setLoaded(true)
        // Default to the first preferred-provider model once the list is known,
        // but only if the parent hasn't already supplied one (modelRef is the
        // live value, so an existing source's model is never clobbered).
        if (mdls.length > 0 && !modelRef.current) {
          const preferred = mdls.find((m) => m.provider === PREFERRED_PROVIDER) ?? mdls[0]
          setModel(preferred.id)
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- setModel is a stable setter
  }, [enrichmentEnabled, loaded])

  // Models grouped by provider for the dropdown.
  const providers = Array.from(new Set(models.map((m) => m.provider)))
  // An existing source may reference a model that's no longer advertised
  // (provider removed, renamed). Keep it selectable so editing doesn't drop it.
  // Guard truthiness so a null/undefined model can't reach Radix's SelectItem.
  const modelMissing = !!model && !models.some((m) => m.id === model)

  return (
    <div className="p-3 border rounded-lg space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <Label className="text-sm font-medium">Enrichment</Label>
          <p className="text-xs text-muted-foreground">
            Classify documents with a taxonomy after indexing
          </p>
        </div>
        <Switch checked={enrichmentEnabled} onCheckedChange={setEnrichmentEnabled} />
      </div>

      {enrichmentEnabled && (
        <div className="space-y-3 pt-1">
          <div className="space-y-1">
            <Label className="text-xs">Taxonomy</Label>
            {loading ? (
              <p className="text-xs text-muted-foreground">Loading taxonomies...</p>
            ) : taxonomies.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No taxonomies found. Create one in the Taxonomy settings first.
              </p>
            ) : (
              <>
                <Select value={taxonomyId} onValueChange={setTaxonomyId}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="Select taxonomy" />
                  </SelectTrigger>
                  <SelectContent>
                    {taxonomies.map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        {t.name}
                        {t.term_count !== undefined && (
                          <span className="ml-1 text-muted-foreground">({t.term_count} terms)</span>
                        )}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {!taxonomyId && (
                  <p className="text-xs text-amber-500">
                    Pick a taxonomy to enable enrichment, or turn enrichment off to continue.
                  </p>
                )}
              </>
            )}
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Classification Model</Label>
            {loading ? (
              <p className="text-xs text-muted-foreground">Loading models...</p>
            ) : models.length === 0 && !modelMissing ? (
              <p className="text-xs text-muted-foreground">
                No models available. Configure a provider in Providers settings first.
              </p>
            ) : (
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger className="h-8 text-xs font-mono">
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((provider) => (
                    <SelectGroup key={provider}>
                      <SelectLabel className="text-xs capitalize">{provider}</SelectLabel>
                      {models
                        .filter((m) => m.provider === provider)
                        .map((m) => (
                          <SelectItem key={m.id} value={m.id} className="text-xs font-mono">
                            {m.id}
                          </SelectItem>
                        ))}
                    </SelectGroup>
                  ))}
                  {modelMissing && (
                    <SelectGroup>
                      <SelectLabel className="text-xs">Current</SelectLabel>
                      <SelectItem value={model} className="text-xs font-mono">
                        {model}
                      </SelectItem>
                    </SelectGroup>
                  )}
                </SelectContent>
              </Select>
            )}
            <p className="text-xs text-muted-foreground">
              LLM used to classify documents against the taxonomy
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
