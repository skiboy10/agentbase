import { useState, useCallback } from 'react'
import { Search, Loader2, Plus, FlaskConical } from 'lucide-react'
import { libraryApi } from '../../../services/api/library'
import type { LibrarySearchResult, LibrarySource } from '../../../services/api/types/library'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import ConfigPanel, { type SearchConfig } from './ConfigPanel'
import ResultPanel from './ResultPanel'

const LABELS = ['Config A', 'Config B', 'Config C']
const MAX_PANELS = 3
const MIN_PANELS = 2

function defaultConfig(): SearchConfig {
  return {
    mode: 'hybrid',
    vectorWeight: 0.7,
    topK: 5,
    rerank: true,
    sourceFilter: 'all',
  }
}

interface PanelResult {
  results: LibrarySearchResult[]
  loading: boolean
  searched: boolean
  latencyMs: number | null
}

interface RetrievalLabTabProps {
  kbId: string
  sources: LibrarySource[]
  onError: (msg: string) => void
}

export default function RetrievalLabTab({ kbId, sources, onError }: RetrievalLabTabProps) {
  const [query, setQuery] = useState('')
  const [configs, setConfigs] = useState<SearchConfig[]>([
    defaultConfig(),
    { ...defaultConfig(), mode: 'vector', rerank: false },
  ])
  const [panelResults, setPanelResults] = useState<PanelResult[]>([
    { results: [], loading: false, searched: false, latencyMs: null },
    { results: [], loading: false, searched: false, latencyMs: null },
  ])

  const updateConfig = (index: number, config: SearchConfig) => {
    setConfigs((prev) => prev.map((c, i) => (i === index ? config : c)))
  }

  const addPanel = () => {
    if (configs.length >= MAX_PANELS) return
    setConfigs((prev) => [...prev, { ...defaultConfig(), mode: 'deep' }])
    setPanelResults((prev) => [
      ...prev,
      { results: [], loading: false, searched: false, latencyMs: null },
    ])
  }

  const removePanel = (index: number) => {
    if (configs.length <= MIN_PANELS) return
    setConfigs((prev) => prev.filter((_, i) => i !== index))
    setPanelResults((prev) => prev.filter((_, i) => i !== index))
  }

  const runSearch = useCallback(async () => {
    const q = query.trim()
    if (!q) return

    // Set all panels to loading
    setPanelResults((prev) =>
      prev.map(() => ({ results: [], loading: true, searched: true, latencyMs: null }))
    )

    // Build and fire all searches in parallel
    const promises = configs.map(async (config, index) => {
      const start = Date.now()
      try {
        // Build source_ids scope
        const sourceIds =
          config.sourceFilter !== 'all'
            ? [config.sourceFilter]
            : undefined

        let results: LibrarySearchResult[]

        if (config.mode === 'deep') {
          const resp = await libraryApi.deepSearch({
            query: q,
            knowledge_base_id: kbId,
            source_ids: sourceIds,
            top_k: config.topK,
            rerank: config.rerank,
          })
          results = resp.results
        } else {
          results = await libraryApi.search(kbId, {
            query: q,
            knowledge_base_id: kbId,
            source_ids: sourceIds,
            top_k: config.topK,
            hybrid: config.mode === 'hybrid',
            vector_weight: config.mode === 'hybrid' ? config.vectorWeight : undefined,
            rerank: config.rerank,
          })
        }

        const latencyMs = Date.now() - start
        setPanelResults((prev) =>
          prev.map((r, i) =>
            i === index ? { results, loading: false, searched: true, latencyMs } : r
          )
        )
      } catch (err) {
        const latencyMs = Date.now() - start
        setPanelResults((prev) =>
          prev.map((r, i) =>
            i === index ? { results: [], loading: false, searched: true, latencyMs } : r
          )
        )
        onError(
          `${LABELS[index]}: ${err instanceof Error ? err.message : 'Search failed'}`
        )
      }
    })

    await Promise.allSettled(promises)
  }, [query, configs, kbId, onError])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') runSearch()
  }

  const anyLoading = panelResults.some((r) => r.loading)
  const gridCols =
    configs.length === 3 ? 'lg:grid-cols-3' : 'lg:grid-cols-2'

  return (
    <div className="space-y-4">
      {/* Query input */}
      <div className="flex gap-2 p-4 rounded-lg border border-border/60 bg-muted/20">
        <div className="relative flex-1">
          <FlaskConical className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Enter a query to compare retrieval configurations..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="pl-9"
          />
        </div>
        <Button onClick={runSearch} disabled={anyLoading || !query.trim()}>
          {anyLoading ? (
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
          ) : (
            <Search className="w-4 h-4 mr-2" />
          )}
          Run
        </Button>
        {configs.length < MAX_PANELS && (
          <Button variant="outline" size="sm" onClick={addPanel}>
            <Plus className="w-4 h-4 mr-1" />
            Add Config
          </Button>
        )}
      </div>

      {/* Config + Result panels grid */}
      <div className={`grid grid-cols-1 ${gridCols} gap-4`}>
        {configs.map((config, i) => (
          <div key={i} className="space-y-0">
            <ConfigPanel
              label={LABELS[i]}
              config={config}
              onChange={(c) => updateConfig(i, c)}
              onRemove={() => removePanel(i)}
              sources={sources}
              canRemove={configs.length > MIN_PANELS}
            />
            <ResultPanel
              results={panelResults[i]?.results ?? []}
              loading={panelResults[i]?.loading ?? false}
              searched={panelResults[i]?.searched ?? false}
              latencyMs={panelResults[i]?.latencyMs ?? null}
              query={query}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
