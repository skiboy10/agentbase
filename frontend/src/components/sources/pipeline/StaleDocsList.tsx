import { useState, useEffect, useCallback } from 'react'
import { Loader2, Clock, AlertCircle } from 'lucide-react'
import { taxonomyApi } from '../../../services/api/taxonomy'
import type { StaleDocSummary } from '../../../services/api/types/taxonomy'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

interface StaleDocsListProps {
  taxonomyId: string
}

export function StaleDocsList({ taxonomyId }: StaleDocsListProps) {
  const [docs, setDocs] = useState<StaleDocSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchStale = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await taxonomyApi.listStale(taxonomyId)
      setDocs(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load stale documents')
    } finally {
      setLoading(false)
    }
  }, [taxonomyId])

  useEffect(() => { fetchStale() }, [fetchStale])

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-400" />
            <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              Stale Documents
            </CardTitle>
          </div>
          {!loading && !error && (
            <Badge variant={docs.length > 0 ? 'destructive' : 'secondary'}>
              {docs.length}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          Documents classified against an older taxonomy version
        </p>
      </CardHeader>

      <CardContent className="pt-0">
        {loading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        )}

        {error && (
          <div className="py-4 text-center">
            <p className="text-sm text-destructive mb-3">{error}</p>
            <Button variant="outline" size="sm" onClick={fetchStale}>
              Retry
            </Button>
          </div>
        )}

        {!loading && !error && docs.length === 0 && (
          <div className="py-8 text-center">
            <Clock className="w-8 h-8 text-muted-foreground/30 mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">No stale documents</p>
            <p className="text-xs text-muted-foreground/60 mt-1">
              All documents are classified against the current taxonomy version
            </p>
          </div>
        )}

        {!loading && !error && docs.length > 0 && (
          <ScrollArea className="h-72">
            <div className="space-y-2 pr-3">
              {docs.map((doc) => (
                <div
                  key={doc.id}
                  className="flex items-start justify-between gap-3 py-2 border-b border-border/50 last:border-0"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {doc.title ?? doc.file_id}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5 text-xs text-muted-foreground">
                      <span className="truncate max-w-[140px]">
                        source: {doc.source_id.slice(0, 8)}…
                      </span>
                      {doc.classification_taxonomy_version != null && (
                        <Badge variant="outline" className="text-xs h-4 px-1">
                          v{doc.classification_taxonomy_version}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <span className="text-xs text-muted-foreground shrink-0 mt-0.5">
                    {formatDate(doc.updated_at)}
                  </span>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  )
}
