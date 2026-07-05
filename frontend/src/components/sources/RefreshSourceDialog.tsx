import { useState, useEffect } from 'react'
import { Globe, RefreshCw } from 'lucide-react'
import { cn } from '../../lib/utils'
import { sourcesApi, Source } from '../../services/api'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface RefreshSourceDialogProps {
  source: Source | null
  onClose: () => void
  onRefreshStarted: (source: Source, urlCount: number, message: string) => void
  onError: (error: string) => void
}

export default function RefreshSourceDialog({
  source,
  onClose,
  onRefreshStarted,
  onError,
}: RefreshSourceDialogProps) {
  const [mode, setMode] = useState<'full' | 'selective'>('full')
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (source) {
      setMode('full')
      setSelectedUrls(new Set())
    }
  }, [source])

  const handleRefresh = async () => {
    if (!source) return

    try {
      const result = await sourcesApi.refreshSource(source.id, {
        mode,
        urls: mode === 'selective' ? Array.from(selectedUrls) : undefined,
      })
      onRefreshStarted(source, result.url_count || 0, result.message)
      onClose()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to refresh source')
    }
  }

  const urls = source?.selected_urls || []
  const isUrlSource = source?.source_type === 'url'

  return (
    <Dialog open={!!source} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className={cn(
          mode === 'selective' && isUrlSource
            ? 'max-w-2xl max-h-[80vh] flex flex-col'
            : 'max-w-md'
        )}
      >
        <DialogHeader>
          <DialogTitle>Refresh Source</DialogTitle>
          <DialogDescription>
            Re-fetch and re-index content from this source to capture updates.
          </DialogDescription>
        </DialogHeader>
        <div className="py-4 space-y-4 flex-1 min-h-0 flex flex-col">
          <div className="space-y-2">
            <Label>Refresh Mode</Label>
            <Select
              value={mode}
              onValueChange={(value) => setMode(value as 'full' | 'selective')}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="full">Full Refresh</SelectItem>
                {isUrlSource && <SelectItem value="selective">Selective Refresh</SelectItem>}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {mode === 'full'
                ? 'Clear all documents and re-index everything from scratch.'
                : 'Re-index only selected URLs. Useful for updating specific pages.'}
            </p>
          </div>

          {/* URL selection for selective mode */}
          {mode === 'selective' && isUrlSource && urls.length > 0 && (
            <div className="flex-1 min-h-0 space-y-2">
              <div className="flex items-center justify-between">
                <Label>Select URLs to refresh</Label>
                <div className="flex gap-2">
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto p-0 text-xs"
                    onClick={() => setSelectedUrls(new Set(urls))}
                  >
                    Select All
                  </Button>
                  <span className="text-muted-foreground/50">|</span>
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto p-0 text-xs"
                    onClick={() => setSelectedUrls(new Set())}
                  >
                    Deselect All
                  </Button>
                </div>
              </div>
              <ScrollArea className="h-48 border rounded-lg p-2">
                <div className="space-y-1">
                  {urls.map((url) => (
                    <div
                      key={url}
                      className={cn(
                        'flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/50',
                        selectedUrls.has(url) && 'bg-primary/20'
                      )}
                    >
                      <Checkbox
                        checked={selectedUrls.has(url)}
                        onCheckedChange={(checked) => {
                          setSelectedUrls((prev) => {
                            const next = new Set(prev)
                            if (checked) {
                              next.add(url)
                            } else {
                              next.delete(url)
                            }
                            return next
                          })
                        }}
                      />
                      <Globe className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                      <span
                        className="text-sm text-foreground truncate font-mono"
                        title={url}
                      >
                        {url}
                      </span>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleRefresh}
            disabled={mode === 'selective' && selectedUrls.size === 0}
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            {mode === 'full'
              ? 'Full Refresh'
              : `Refresh ${selectedUrls.size} URL${selectedUrls.size !== 1 ? 's' : ''}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
