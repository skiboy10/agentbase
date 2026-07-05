import { Source } from '../../../services/api'
import { UseEmbeddingConfigResult } from './hooks/useEmbeddingConfig'
import { useUrlScanning } from './hooks/useUrlScanning'
import { UrlInputStage, UrlSelectStage } from './stages'

interface UrlSourceFormProps {
  embedding: UseEmbeddingConfigResult
  onSourceAdded: (source: Source) => void
  onError: (error: string) => void
  onClose: () => void
}

export default function UrlSourceForm({
  embedding,
  onSourceAdded,
  onError,
  onClose,
}: UrlSourceFormProps) {
  const scanning = useUrlScanning({
    embedding,
    onSourceAdded,
    onError,
    onClose,
  })

  if (scanning.stage === 'input') {
    return (
      <UrlInputStage
        scanMode={scanning.scanMode}
        onScanModeChange={scanning.setScanMode}
        scanUrl={scanning.scanUrl}
        onScanUrlChange={scanning.setScanUrl}
        scanDepth={scanning.scanDepth}
        onScanDepthChange={scanning.setScanDepth}
        pathScope={scanning.pathScope}
        onPathScopeChange={scanning.setPathScope}
        sitemapUrl={scanning.sitemapUrl}
        onSitemapUrlChange={scanning.setSitemapUrl}
        pathFilter={scanning.pathFilter}
        onPathFilterChange={scanning.setPathFilter}
        scanning={scanning.scanning}
        onScan={scanning.handleScanUrl}
        onClose={onClose}
        embedding={embedding}
      />
    )
  }

  return (
    <UrlSelectStage
      name={scanning.name}
      onNameChange={scanning.setName}
      siteTree={scanning.siteTree}
      discoveredSitemapUrl={scanning.discoveredSitemapUrl}
      selectedUrls={scanning.selectedUrls}
      expandedUrls={scanning.expandedUrls}
      adding={scanning.adding}
      onToggleUrl={scanning.handleToggleUrl}
      onExpandUrl={scanning.handleExpandUrl}
      onSelectAll={scanning.handleSelectAll}
      onDeselectAll={scanning.handleDeselectAll}
      onExpandAll={scanning.handleExpandAll}
      onCollapseAll={scanning.handleCollapseAll}
      onAdd={scanning.handleAddUrlSource}
      onBack={scanning.handleBack}
      onClose={onClose}
      embedding={embedding}
      enrichmentEnabled={scanning.enrichmentEnabled}
      setEnrichmentEnabled={scanning.setEnrichmentEnabled}
      enrichmentTaxonomyId={scanning.enrichmentTaxonomyId}
      setEnrichmentTaxonomyId={scanning.setEnrichmentTaxonomyId}
      enrichmentModel={scanning.enrichmentModel}
      setEnrichmentModel={scanning.setEnrichmentModel}
    />
  )
}
