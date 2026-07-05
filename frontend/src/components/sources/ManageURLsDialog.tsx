import { useState, useEffect } from 'react'
import { Globe, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import { sourcesApi, Source } from '../../services/api'
import { Button } from '@/components/ui/button'
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

interface ManageURLsDialogProps {
  source: Source | null
  onClose: () => void
  onUpdated: (source: Source) => void
  onError: (error: string) => void
}

export default function ManageURLsDialog({
  source,
  onClose,
  onUpdated,
  onError,
}: ManageURLsDialogProps) {
  const [urlsToRemove, setUrlsToRemove] = useState<Set<string>>(new Set())
  const [removing, setRemoving] = useState(false)

  useEffect(() => {
    if (source) {
      setUrlsToRemove(new Set())
    }
  }, [source])

  const handleRemove = async () => {
    if (!source || urlsToRemove.size === 0) return

    try {
      setRemoving(true)
      const updated = await sourcesApi.removeUrls(source.id, Array.from(urlsToRemove))
      onUpdated(updated)
      onClose()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to remove URLs')
    } finally {
      setRemoving(false)
    }
  }

  const urls = source?.selected_urls || []

  return (
    <Dialog open={!!source} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Manage URLs</DialogTitle>
          <DialogDescription>
            Select URLs to remove from this source. Removing URLs will delete their
            vectors from the source.
          </DialogDescription>
        </DialogHeader>
        <div className="flex-1 min-h-0 py-4">
          {urls.length > 0 ? (
            <>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-muted-foreground">
                  {urlsToRemove.size} of {urls.length} URLs selected for removal
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto p-0 text-xs"
                    onClick={() => setUrlsToRemove(new Set(urls))}
                  >
                    Select All
                  </Button>
                  <span className="text-muted-foreground/50">|</span>
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto p-0 text-xs"
                    onClick={() => setUrlsToRemove(new Set())}
                  >
                    Deselect All
                  </Button>
                </div>
              </div>
              <ScrollArea className="h-64 border rounded-lg p-2">
                <div className="space-y-1">
                  {urls.map((url) => (
                    <div
                      key={url}
                      className={cn(
                        'flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/50',
                        urlsToRemove.has(url) && 'bg-destructive/20'
                      )}
                    >
                      <Checkbox
                        checked={urlsToRemove.has(url)}
                        onCheckedChange={(checked) => {
                          setUrlsToRemove((prev) => {
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
            </>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              No URLs in this source
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleRemove}
            disabled={urlsToRemove.size === 0 || removing}
          >
            {removing && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
            Remove {urlsToRemove.size} URL{urlsToRemove.size !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
