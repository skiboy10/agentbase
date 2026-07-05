import { useState } from 'react'
import {
  FolderOpen,
  FileText,
  Database,
  Loader2,
  AlertTriangle,
  RefreshCw,
  Trash2,
  MoreVertical,
  Pencil,
  ListChecks,
  Cpu,
  Bot,
  Sparkles,
  Eye,
  RotateCcw,
  FolderSync,
  Radio,
  AlertCircle,
  FolderX,
  Copy,
  Check,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { Source } from '../../services/api'
import { formatTimeAgo, formatDate } from '../../utils/sourcesFormatters'
import { getSourceTypeMeta } from '@/lib/sourceType'
import { watchStatusMeta } from '@/lib/status'
import IndexingLogsPanel from './IndexingLogsPanel'
import { HelpTooltip } from '@/components/HelpTooltip'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface SourceCardProps {
  source: Source
  isDeleting: boolean
  expandedLogs: boolean
  onToggleLogs: () => void
  onEdit: () => void
  onManageUrls: () => void
  onRefresh: () => void
  onIndex: () => void
  onDelete: () => void
  onRetryFailed: () => void
  onForceSync?: () => void
  onReEnrich?: () => void
}

export default function SourceCard({
  source,
  isDeleting,
  expandedLogs,
  onToggleLogs,
  onEdit,
  onManageUrls,
  onRefresh,
  onIndex,
  onDelete,
  onRetryFailed,
  onForceSync,
  onReEnrich,
}: SourceCardProps) {
  const isIndexing = source.status === 'indexing'
  const [copiedId, setCopiedId] = useState(false)

  const handleCopyId = async () => {
    try {
      await navigator.clipboard.writeText(source.id)
      setCopiedId(true)
      setTimeout(() => setCopiedId(false), 1500)
    } catch {
      // Clipboard access can be denied — ignore silently
    }
  }

  const typeMeta = getSourceTypeMeta(source.source_type)
  const TypeIcon = typeMeta.icon

  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-4">
            <div
              className={cn(
                'w-10 h-10 rounded-lg flex items-center justify-center',
                typeMeta.bg
              )}
            >
              <TypeIcon className={cn('w-5 h-5', typeMeta.text)} />
            </div>
            <div>
              <h3 className="font-semibold text-foreground">{source.name}</h3>
              {source.description && (
                <p className="text-sm text-muted-foreground">{source.description}</p>
              )}
              <p className="text-sm text-muted-foreground/70 font-mono">
                {source.source_path}
              </p>
              {source.source_type === 'youtube' && (
                <p className="text-xs text-muted-foreground/70">
                  {source.youtube_backfill_mode === 'all'
                    ? 'Full history'
                    : `Recent ${source.youtube_recent_count ?? 50} videos`}{' '}
                  · auto-refresh daily
                </p>
              )}
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={handleCopyId}
                      className="mt-1 inline-flex items-center gap-1 font-mono text-xs text-muted-foreground/60 hover:text-foreground transition-colors"
                    >
                      <span>ID: {source.id.slice(0, 8)}…</span>
                      {copiedId ? (
                        <Check className="w-3 h-3 text-status-success" />
                      ) : (
                        <Copy className="w-3 h-3" />
                      )}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {copiedId ? 'Copied!' : `Copy source ID: ${source.id}`}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
              {source.collection_name && (
                <p className="text-xs text-muted-foreground/50 font-mono mt-1">
                  <Database className="w-3 h-3 inline mr-1" />
                  {source.collection_name}
                </p>
              )}
              {/* Root / sub-source hierarchy chip */}
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                {source.parent_source_id ? (
                  <Badge
                    variant="outline"
                    className="text-xs text-cat-subsource border-cat-subsource/50"
                    title={`Sub-source view; filters parent's chunks by ${source.path_prefix ?? source.source_path}`}
                  >
                    Sub-source
                  </Badge>
                ) : source.sub_source_count && source.sub_source_count > 0 ? (
                  <Badge
                    variant="outline"
                    className="text-xs text-cat-root border-cat-root/50"
                  >
                    Root · {source.sub_source_count} sub-source{source.sub_source_count === 1 ? '' : 's'}
                  </Badge>
                ) : null}
              </div>
              {/* Project assignment badges */}
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                {source.owner_project ? (
                  <Badge variant="secondary" className="text-xs">
                    <FolderOpen className="w-3 h-3 mr-1" />
                    {source.owner_project.name}
                  </Badge>
                ) : source.assigned_projects && source.assigned_projects.length > 0 ? (
                  <>
                    <Badge
                      variant="outline"
                      className="text-xs text-cat-global border-cat-global/50"
                    >
                      Global
                    </Badge>
                    {source.assigned_projects.map((proj) => (
                      <Badge key={proj.id} variant="secondary" className="text-xs">
                        {proj.name}
                      </Badge>
                    ))}
                  </>
                ) : (
                  <Badge variant="outline" className="text-xs text-muted-foreground">
                    Global (unassigned)
                  </Badge>
                )}
              </div>
              {/* Agent bindings badges */}
              {source.bound_agents && source.bound_agents.length > 0 && (
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <span className="text-xs text-muted-foreground">Used by:</span>
                  {source.bound_agents.map((agent) => (
                    <Badge
                      key={agent.id}
                      variant="outline"
                      className="text-xs text-cat-agent border-cat-agent/50"
                    >
                      <Bot className="w-3 h-3 mr-1" />
                      {agent.name}
                    </Badge>
                  ))}
                </div>
              )}
              {/* Embedding model badge */}
              {source.embedding_provider && source.embedding_model && (
                <div className="flex items-center gap-1 mt-2">
                  <Badge variant="outline" className="text-xs font-mono text-cat-embedding border-cat-embedding/50">
                    <Cpu className="w-3 h-3 mr-1" />
                    {source.embedding_provider}/{source.embedding_model}
                    {source.embedding_dimensions && (
                      <span className="ml-1 text-muted-foreground">({source.embedding_dimensions}d)</span>
                    )}
                  </Badge>
                </div>
              )}
              {/* Enrichment + watcher badges */}
              {(source.enrichment_enabled || source.watch_enabled) && (
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  {source.enrichment_enabled && (
                    <Badge variant="outline" className="text-xs text-cat-enriched border-cat-enriched/50">
                      <Sparkles className="w-3 h-3 mr-1" />
                      Enriched
                    </Badge>
                  )}
                  {source.source_type === 'directory' && source.watch_enabled && (() => {
                    const wsMeta = watchStatusMeta(source.watch_status);
                    let icon = <Eye className="w-3 h-3 mr-1" />;
                    let label = wsMeta.label;

                    if (source.watch_status === 'running') {
                      icon = <Radio className="w-3 h-3 mr-1 animate-pulse" />;
                      const ago = source.watch_last_heartbeat_at
                        ? formatTimeAgo(source.watch_last_heartbeat_at).text
                        : 'unknown';
                      label = `Watching — last event ${ago}`;
                    } else if (source.watch_status === 'degraded') {
                      icon = <AlertCircle className="w-3 h-3 mr-1" />;
                      label = 'Watching with errors — click to view';
                    } else if (source.watch_status === 'path_missing') {
                      icon = <FolderX className="w-3 h-3 mr-1" />;
                    } else if (source.watch_status === 'error') {
                      icon = <AlertTriangle className="w-3 h-3 mr-1" />;
                      label = source.watch_last_error || wsMeta.label;
                    }

                    return (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              onClick={onEdit}
                              aria-label={label}
                              className="inline-flex items-center"
                            >
                              <Badge
                                variant="outline"
                                className={cn('text-xs cursor-pointer', wsMeta.colorClass)}
                              >
                                {icon}
                                Watching
                              </Badge>
                            </button>
                          </TooltipTrigger>
                          <TooltipContent>{label}</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    );
                  })()}
                </div>
              )}
              <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground/70">
                <span>{source.document_count} docs</span>
                <span className="inline-flex items-center gap-1">
                  {source.chunk_count} chunks
                  <HelpTooltip helpKey="sources.chunks" side="top" />
                </span>
                <span>Last indexed: {formatDate(source.last_indexed)}</span>
              </div>
              {/* Progress indicator during indexing */}
              {isIndexing && (() => {
                const lastUpdate = formatTimeAgo(source.progress_updated_at)
                const progressPercent =
                  source.progress_total > 0
                    ? Math.min(100, (source.progress / source.progress_total) * 100)
                    : 0
                return (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-sm mb-1">
                      <span className="text-status-warning">
                        {source.progress_message || 'Indexing...'}
                      </span>
                      {source.progress_total > 0 && (
                        <span className="text-muted-foreground">
                          {source.progress}/{source.progress_total}
                        </span>
                      )}
                    </div>
                    {source.progress_total > 0 && (
                      <Progress
                        value={progressPercent}
                        className={cn(
                          'h-2 mb-2',
                          lastUpdate.isStale && '[&>div]:bg-status-warning'
                        )}
                      />
                    )}
                    {/* Last update indicator */}
                    <div
                      className={cn(
                        'flex items-center gap-2 text-xs',
                        lastUpdate.isStale ? 'text-status-warning' : 'text-muted-foreground'
                      )}
                    >
                      {lastUpdate.isStale && <AlertTriangle className="w-3 h-3" />}
                      <span>Last update: {lastUpdate.text}</span>
                      {lastUpdate.isStale && lastUpdate.secondsAgo > 60 && (
                        <span className="text-status-warning">(process may be stalled)</span>
                      )}
                    </div>
                  </div>
                )
              })()}
              {source.error_message && source.status === 'error' && (
                <p className="mt-2 text-sm text-destructive">
                  Error: {source.error_message}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              variant={
                source.status === 'indexed'
                  ? 'default'
                  : source.status === 'error'
                    ? 'destructive'
                    : 'secondary'
              }
            >
              {source.status}
            </Badge>
            {/* View Logs button - only for URL sources */}
            {source.source_type === 'url' && (
              <Button
                variant={expandedLogs ? 'secondary' : 'ghost'}
                size="icon"
                onClick={onToggleLogs}
                title="View indexing logs"
              >
                <FileText className="w-4 h-4" />
              </Button>
            )}
            {/* Actions Dropdown Menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" disabled={isIndexing}>
                  <MoreVertical className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={onEdit}>
                  <Pencil className="w-4 h-4 mr-2" />
                  Edit Details
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleCopyId}>
                  <Copy className="w-4 h-4 mr-2" />
                  Copy Source ID
                </DropdownMenuItem>
                {source.source_type === 'url' && (
                  <DropdownMenuItem onClick={onManageUrls}>
                    <ListChecks className="w-4 h-4 mr-2" />
                    Manage URLs
                  </DropdownMenuItem>
                )}
                {source.source_type === 'directory' && (
                  <DropdownMenuItem onClick={onForceSync}>
                    <FolderSync className="w-4 h-4 mr-2 shrink-0" />
                    <div className="flex flex-col">
                      <span>Force Sync</span>
                      <span className="text-xs text-muted-foreground font-normal">{"Reconcile the watcher with what's on disk now"}</span>
                    </div>
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onRefresh}>
                  <RefreshCw className="w-4 h-4 mr-2 shrink-0" />
                  <div className="flex flex-col">
                    <span>Refresh Source</span>
                    <span className="text-xs text-muted-foreground font-normal">Re-fetch changed content from the original source</span>
                  </div>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onIndex}>
                  <RefreshCw className="w-4 h-4 mr-2 shrink-0" />
                  <div className="flex flex-col">
                    <span>Full Re-index</span>
                    <span className="text-xs text-muted-foreground font-normal">{"Rebuild this source's search index from scratch"}</span>
                  </div>
                </DropdownMenuItem>
                {source.enrichment_enabled && (
                  <DropdownMenuItem onClick={onReEnrich}>
                    <RotateCcw className="w-4 h-4 mr-2 shrink-0" />
                    <div className="flex flex-col">
                      <span>Re-enrich</span>
                      <span className="text-xs text-muted-foreground font-normal">Re-run classification and metadata extraction</span>
                    </div>
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={onDelete}
                  className="text-destructive focus:text-destructive"
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  Delete Source
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            {/* Loading indicator for indexing/deleting */}
            {(isIndexing || isDeleting) && (
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            )}
          </div>
        </div>
        {/* Logs Panel */}
        {expandedLogs && (
          <IndexingLogsPanel
            sourceId={source.id}
            isIndexing={isIndexing}
            onClose={onToggleLogs}
            onRetry={onRetryFailed}
          />
        )}
      </CardContent>
    </Card>
  )
}
