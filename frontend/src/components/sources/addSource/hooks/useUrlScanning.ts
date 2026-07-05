import { useState, useCallback } from 'react'
import {
  sourcesApi,
  Source,
  SourceCreate,
  SiteTreeNode,
  ScanUrlResponse,
} from '../../../../services/api'
import { flattenTree } from '../../../../utils/sourcesFormatters'
import { ScanMode, Stage } from '../types'
import { UseEmbeddingConfigResult } from './useEmbeddingConfig'

interface UseUrlScanningProps {
  embedding: UseEmbeddingConfigResult
  onSourceAdded: (source: Source) => void
  onError: (error: string) => void
  onClose: () => void
}

export function useUrlScanning({ embedding, onSourceAdded, onError, onClose }: UseUrlScanningProps) {
  // Stage state
  const [stage, setStage] = useState<Stage>('input')

  // Input stage state
  const [scanMode, setScanMode] = useState<ScanMode>('auto')
  const [scanUrl, setScanUrl] = useState('')
  const [scanDepth, setScanDepth] = useState(2)
  const [pathScope, setPathScope] = useState('')
  const [sitemapUrl, setSitemapUrl] = useState('')
  const [pathFilter, setPathFilter] = useState('')
  const [scanning, setScanning] = useState(false)

  // Select stage state
  const [name, setName] = useState('')
  const [siteTree, setSiteTree] = useState<SiteTreeNode | null>(null)
  const [discoveredSitemapUrl, setDiscoveredSitemapUrl] = useState<string | null>(null)
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set())
  const [expandedUrls, setExpandedUrls] = useState<Set<string>>(new Set())
  const [adding, setAdding] = useState(false)

  // Enrichment state (applied to created source)
  const [enrichmentEnabled, setEnrichmentEnabled] = useState(false)
  const [enrichmentTaxonomyId, setEnrichmentTaxonomyId] = useState('')
  const [enrichmentModel, setEnrichmentModel] = useState('')

  const handleScanUrl = useCallback(async () => {
    try {
      setScanning(true)
      setDiscoveredSitemapUrl(null)

      let response: ScanUrlResponse

      if (scanMode === 'auto') {
        if (!scanUrl.trim()) {
          onError('Please enter a URL')
          return
        }
        response = await sourcesApi.scanWithAutoDiscover(
          scanUrl.trim(),
          pathFilter.trim() || undefined
        )
        if (response.sitemap_url) {
          setDiscoveredSitemapUrl(response.sitemap_url)
        }
      } else if (scanMode === 'sitemap') {
        if (!sitemapUrl.trim()) {
          onError('Please enter a sitemap URL')
          return
        }
        response = await sourcesApi.scanSitemap(
          sitemapUrl.trim(),
          pathFilter.trim() || undefined
        )
        setDiscoveredSitemapUrl(response.sitemap_url)
      } else {
        if (!scanUrl.trim()) {
          onError('Please enter a URL to scan')
          return
        }
        response = await sourcesApi.scanUrl(
          scanUrl.trim(),
          scanDepth,
          pathScope.trim() || undefined
        )
      }

      const tree = response.tree
      setSiteTree(tree)
      setExpandedUrls(new Set([tree.url]))
      const allUrls = flattenTree(tree)
      setSelectedUrls(new Set(allUrls))
      setStage('select')
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to scan')
    } finally {
      setScanning(false)
    }
  }, [scanMode, scanUrl, sitemapUrl, scanDepth, pathScope, pathFilter, onError])

  const handleToggleUrl = useCallback((url: string) => {
    setSelectedUrls((prev) => {
      const next = new Set(prev)
      if (next.has(url)) {
        next.delete(url)
      } else {
        next.add(url)
      }
      return next
    })
  }, [])

  const handleExpandUrl = useCallback((url: string) => {
    setExpandedUrls((prev) => {
      const next = new Set(prev)
      if (next.has(url)) {
        next.delete(url)
      } else {
        next.add(url)
      }
      return next
    })
  }, [])

  const handleSelectAll = useCallback(() => {
    if (siteTree) {
      setSelectedUrls(new Set(flattenTree(siteTree)))
    }
  }, [siteTree])

  const handleDeselectAll = useCallback(() => {
    setSelectedUrls(new Set())
  }, [])

  const handleExpandAll = useCallback(() => {
    if (siteTree) {
      setExpandedUrls(new Set(flattenTree(siteTree)))
    }
  }, [siteTree])

  const handleCollapseAll = useCallback(() => {
    setExpandedUrls(new Set())
  }, [])

  const handleAddUrlSource = useCallback(async () => {
    if (!name.trim() || selectedUrls.size === 0) return

    try {
      setAdding(true)
      const embeddingParams = embedding.getEmbeddingParams()
      const createPayload: SourceCreate = {
        name: name.trim(),
        source_type: 'url',
        source_path: scanUrl || sitemapUrl,
        selected_urls: Array.from(selectedUrls),
        embedding_provider: embeddingParams.provider,
        embedding_model: embeddingParams.model,
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
      onError(err instanceof Error ? err.message : 'Failed to add URL source')
    } finally {
      setAdding(false)
    }
  }, [name, selectedUrls, scanUrl, sitemapUrl, embedding, enrichmentEnabled, enrichmentTaxonomyId, enrichmentModel, onSourceAdded, onClose, onError])

  const handleBack = useCallback(() => {
    setStage('input')
    setSiteTree(null)
    setSelectedUrls(new Set())
    setExpandedUrls(new Set())
  }, [])

  return {
    // Stage
    stage,
    // Input state
    scanMode,
    setScanMode,
    scanUrl,
    setScanUrl,
    scanDepth,
    setScanDepth,
    pathScope,
    setPathScope,
    sitemapUrl,
    setSitemapUrl,
    pathFilter,
    setPathFilter,
    scanning,
    // Select state
    name,
    setName,
    siteTree,
    discoveredSitemapUrl,
    selectedUrls,
    expandedUrls,
    adding,
    // Enrichment state
    enrichmentEnabled,
    setEnrichmentEnabled,
    enrichmentTaxonomyId,
    setEnrichmentTaxonomyId,
    enrichmentModel,
    setEnrichmentModel,
    // Actions
    handleScanUrl,
    handleToggleUrl,
    handleExpandUrl,
    handleSelectAll,
    handleDeselectAll,
    handleExpandAll,
    handleCollapseAll,
    handleAddUrlSource,
    handleBack,
  }
}
