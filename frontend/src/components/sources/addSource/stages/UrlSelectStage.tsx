import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SiteTreeNode as SiteTreeNodeType } from '../../../../services/api'
import { flattenTree } from '../../../../utils/sourcesFormatters'
import SiteTreeNode from '../../SiteTreeNode'
import EmbeddingModelSelector from '../EmbeddingModelSelector'
import EnrichmentSection from '../EnrichmentSection'
import { UseEmbeddingConfigResult } from '../hooks/useEmbeddingConfig'

interface UrlSelectStageProps {
  name: string
  onNameChange: (name: string) => void
  siteTree: SiteTreeNodeType | null
  discoveredSitemapUrl: string | null
  selectedUrls: Set<string>
  expandedUrls: Set<string>
  adding: boolean
  onToggleUrl: (url: string) => void
  onExpandUrl: (url: string) => void
  onSelectAll: () => void
  onDeselectAll: () => void
  onExpandAll: () => void
  onCollapseAll: () => void
  onAdd: () => void
  onBack: () => void
  onClose: () => void
  embedding: UseEmbeddingConfigResult
  enrichmentEnabled: boolean
  setEnrichmentEnabled: (value: boolean) => void
  enrichmentTaxonomyId: string
  setEnrichmentTaxonomyId: (value: string) => void
  enrichmentModel: string
  setEnrichmentModel: (value: string) => void
}

export function UrlSelectStage({
  name,
  onNameChange,
  siteTree,
  discoveredSitemapUrl,
  selectedUrls,
  expandedUrls,
  adding,
  onToggleUrl,
  onExpandUrl,
  onSelectAll,
  onDeselectAll,
  onExpandAll,
  onCollapseAll,
  onAdd,
  onBack,
  onClose,
  embedding,
  enrichmentEnabled,
  setEnrichmentEnabled,
  enrichmentTaxonomyId,
  setEnrichmentTaxonomyId,
  enrichmentModel,
  setEnrichmentModel,
}: UrlSelectStageProps) {
  const totalUrls = siteTree ? flattenTree(siteTree).length : 0

  return (
    <div className="flex flex-col flex-1 min-h-0 py-4">
      {discoveredSitemapUrl && (
        <div className="mb-4 p-3 bg-status-success/15 border border-status-success/30 rounded-lg text-sm">
          <span className="text-status-success font-medium">Sitemap discovered:</span>
          <span className="text-status-success/80 font-mono ml-2 text-xs">
            {discoveredSitemapUrl}
          </span>
        </div>
      )}

      <div className="mb-4 space-y-2">
        <Label htmlFor="url-source-name">Source Name</Label>
        <Input
          id="url-source-name"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="e.g., API Reference"
        />
      </div>

      {siteTree && (
        <>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-muted-foreground">
              {selectedUrls.size} of {totalUrls} pages selected
            </span>
            <div className="flex gap-2">
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-xs"
                onClick={onSelectAll}
              >
                Select All
              </Button>
              <span className="text-muted-foreground/50">|</span>
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-xs"
                onClick={onDeselectAll}
              >
                Deselect All
              </Button>
              <span className="text-muted-foreground/50">|</span>
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-xs"
                onClick={onExpandAll}
              >
                Expand All
              </Button>
              <span className="text-muted-foreground/50">|</span>
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-xs"
                onClick={onCollapseAll}
              >
                Collapse All
              </Button>
            </div>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto border rounded-lg p-2 mb-4">
            <SiteTreeNode
              node={siteTree}
              selected={selectedUrls}
              expanded={expandedUrls}
              onToggle={onToggleUrl}
              onExpand={onExpandUrl}
              depth={0}
            />
          </div>
        </>
      )}

      <EmbeddingModelSelector
        embeddingConfig={embedding.embeddingConfig}
        useCustomEmbedding={embedding.useCustomEmbedding}
        onUseCustomChange={embedding.setUseCustomEmbedding}
        selectedProvider={embedding.selectedProvider}
        onProviderChange={embedding.setSelectedProvider}
        selectedModel={embedding.selectedModel}
        onModelChange={embedding.setSelectedModel}
        compact
      />

      <div className="mt-3">
        <EnrichmentSection
          enrichmentEnabled={enrichmentEnabled}
          setEnrichmentEnabled={setEnrichmentEnabled}
          taxonomyId={enrichmentTaxonomyId}
          setTaxonomyId={setEnrichmentTaxonomyId}
          model={enrichmentModel}
          setModel={setEnrichmentModel}
        />
      </div>

      <div className="flex justify-between gap-3 mt-4">
        <Button variant="ghost" onClick={onBack}>
          Back
        </Button>
        <div className="flex gap-3">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={onAdd}
            disabled={
              !name.trim() ||
              selectedUrls.size === 0 ||
              adding ||
              (enrichmentEnabled && !enrichmentTaxonomyId)
            }
          >
            {adding && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
            Add {selectedUrls.size} Page{selectedUrls.size !== 1 ? 's' : ''}
          </Button>
        </div>
      </div>
    </div>
  )
}
