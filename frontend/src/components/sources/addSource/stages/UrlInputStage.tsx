import { Loader2, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { DialogFooter } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import EmbeddingModelSelector from '../EmbeddingModelSelector'
import { UseEmbeddingConfigResult } from '../hooks/useEmbeddingConfig'
import { ScanMode } from '../types'

interface UrlInputStageProps {
  scanMode: ScanMode
  onScanModeChange: (mode: ScanMode) => void
  scanUrl: string
  onScanUrlChange: (url: string) => void
  scanDepth: number
  onScanDepthChange: (depth: number) => void
  pathScope: string
  onPathScopeChange: (scope: string) => void
  sitemapUrl: string
  onSitemapUrlChange: (url: string) => void
  pathFilter: string
  onPathFilterChange: (filter: string) => void
  scanning: boolean
  onScan: () => void
  onClose: () => void
  embedding: UseEmbeddingConfigResult
}

export function UrlInputStage({
  scanMode,
  onScanModeChange,
  scanUrl,
  onScanUrlChange,
  scanDepth,
  onScanDepthChange,
  pathScope,
  onPathScopeChange,
  sitemapUrl,
  onSitemapUrlChange,
  pathFilter,
  onPathFilterChange,
  scanning,
  onScan,
  onClose,
  embedding,
}: UrlInputStageProps) {
  const canScan = scanMode === 'sitemap' ? sitemapUrl.trim() : scanUrl.trim()

  return (
    <div className="space-y-4 py-4">
      <Tabs
        value={scanMode}
        onValueChange={(value) => onScanModeChange(value as ScanMode)}
      >
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="auto" className="text-xs">
            Auto-Discover
          </TabsTrigger>
          <TabsTrigger value="crawl" className="text-xs">
            Crawl Links
          </TabsTrigger>
          <TabsTrigger value="sitemap" className="text-xs">
            Manual Sitemap
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {scanMode === 'auto' && (
        <>
          <div className="space-y-2">
            <Label htmlFor="website-url">Website URL</Label>
            <Input
              id="website-url"
              type="url"
              value={scanUrl}
              onChange={(e) => onScanUrlChange(e.target.value)}
              placeholder="https://docs.example.com"
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Enter any URL - sitemap will be auto-discovered from robots.txt or
              common locations
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="path-filter">Path Filter (optional)</Label>
            <Input
              id="path-filter"
              type="text"
              value={pathFilter}
              onChange={(e) => onPathFilterChange(e.target.value)}
              placeholder="/docs/api/"
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Filter to only include URLs containing this path
            </p>
          </div>
        </>
      )}

      {scanMode === 'crawl' && (
        <>
          <div className="space-y-2">
            <Label htmlFor="crawl-url">URL to Scan</Label>
            <Input
              id="crawl-url"
              type="url"
              value={scanUrl}
              onChange={(e) => onScanUrlChange(e.target.value)}
              placeholder="https://docs.example.com"
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Crawl mode follows actual links on pages. Use for sites without
              sitemaps.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="scan-depth">Scan Depth</Label>
            <Select
              value={String(scanDepth)}
              onValueChange={(value) => onScanDepthChange(Number(value))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">1 level (direct links only)</SelectItem>
                <SelectItem value="2">2 levels (recommended)</SelectItem>
                <SelectItem value="3">3 levels (thorough)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="path-scope">Path Scope (optional)</Label>
            <Input
              id="path-scope"
              type="text"
              value={pathScope}
              onChange={(e) => onPathScopeChange(e.target.value)}
              placeholder="/guide"
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Broader path to include (e.g., "/guide" to crawl all pages under
              /guide/*)
            </p>
          </div>
        </>
      )}

      {scanMode === 'sitemap' && (
        <>
          <div className="space-y-2">
            <Label htmlFor="sitemap-url">Sitemap URL</Label>
            <Input
              id="sitemap-url"
              type="url"
              value={sitemapUrl}
              onChange={(e) => onSitemapUrlChange(e.target.value)}
              placeholder="https://example.com/sitemap.xml"
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Enter the exact sitemap URL if auto-discovery doesn't work
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="sitemap-path-filter">Path Filter (optional)</Label>
            <Input
              id="sitemap-path-filter"
              type="text"
              value={pathFilter}
              onChange={(e) => onPathFilterChange(e.target.value)}
              placeholder="/docs/guide/"
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Filter URLs containing this path
            </p>
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
        idPrefix="url-embed"
      />

      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={onScan} disabled={!canScan || scanning}>
          {scanning ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
              {scanMode === 'auto' ? 'Discovering...' : 'Scanning...'}
            </>
          ) : (
            <>
              <Search className="w-4 h-4 mr-2" />
              {scanMode === 'auto'
                ? 'Discover & Scan'
                : scanMode === 'sitemap'
                  ? 'Load Sitemap'
                  : 'Scan URL'}
            </>
          )}
        </Button>
      </DialogFooter>
    </div>
  )
}
