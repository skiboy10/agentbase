import { Source, SiteTreeNode } from '../../../services/api'
import { UseEmbeddingConfigResult } from './hooks/useEmbeddingConfig'

export type ScanMode = 'auto' | 'crawl' | 'sitemap'
export type Stage = 'input' | 'select'

export interface UrlSourceFormProps {
  embedding: UseEmbeddingConfigResult
  onSourceAdded: (source: Source) => void
  onError: (error: string) => void
  onClose: () => void
}

export interface UrlScanningState {
  // Input stage state
  scanMode: ScanMode
  scanUrl: string
  scanDepth: number
  pathScope: string
  sitemapUrl: string
  pathFilter: string
  scanning: boolean
  // Select stage state
  name: string
  siteTree: SiteTreeNode | null
  discoveredSitemapUrl: string | null
  selectedUrls: Set<string>
  expandedUrls: Set<string>
  adding: boolean
}
