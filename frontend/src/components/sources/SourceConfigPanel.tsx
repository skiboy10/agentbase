import { Sparkles, Eye } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { Source } from '../../services/api/types/sources'

interface SourceConfigPanelProps {
  source: Source
}

export default function SourceConfigPanel({ source }: SourceConfigPanelProps) {
  const hasEnrichment = source.enrichment_enabled
  const hasWatcher = source.watch_enabled

  if (!hasEnrichment && !hasWatcher) {
    return (
      <p className="text-xs text-muted-foreground italic">No pipeline configuration</p>
    )
  }

  return (
    <div className="space-y-4">
      {hasEnrichment && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Sparkles className="w-3.5 h-3.5 text-violet-400" />
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Enrichment
            </span>
            <Badge
              variant="outline"
              className="text-xs text-violet-400 border-violet-400/50 h-5"
            >
              Enabled
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 pl-5 text-xs">
            {source.enrichment_taxonomy_id && (
              <>
                <span className="text-muted-foreground">Taxonomy</span>
                <span className="font-mono text-foreground/80 truncate">
                  {source.enrichment_taxonomy_id}
                </span>
              </>
            )}
            {source.enrichment_model && (
              <>
                <span className="text-muted-foreground">Model</span>
                <span className="font-mono text-foreground/80 truncate">
                  {source.enrichment_model}
                </span>
              </>
            )}
          </div>
        </div>
      )}

      {hasWatcher && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Eye className="w-3.5 h-3.5 text-sky-400" />
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Watcher
            </span>
            <Badge
              variant="outline"
              className="text-xs text-sky-400 border-sky-400/50 h-5"
            >
              Enabled
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 pl-5 text-xs">
            {source.watch_mode && (
              <>
                <span className="text-muted-foreground">Mode</span>
                <span className="text-foreground/80 capitalize">{source.watch_mode}</span>
              </>
            )}
            {source.watch_poll_interval_seconds != null && (
              <>
                <span className="text-muted-foreground">Poll interval</span>
                <span className="text-foreground/80">{source.watch_poll_interval_seconds}s</span>
              </>
            )}
            {source.watch_debounce_seconds != null && (
              <>
                <span className="text-muted-foreground">Debounce</span>
                <span className="text-foreground/80">{source.watch_debounce_seconds}s</span>
              </>
            )}
            {source.watch_max_file_size_mb != null && (
              <>
                <span className="text-muted-foreground">Max file size</span>
                <span className="text-foreground/80">{source.watch_max_file_size_mb} MB</span>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
