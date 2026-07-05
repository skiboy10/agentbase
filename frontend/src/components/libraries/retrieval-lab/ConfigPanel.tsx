import { X } from 'lucide-react'
import type { LibrarySource } from '../../../services/api/types/library'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { HelpTooltip } from '@/components/HelpTooltip'

export type SearchMode = 'hybrid' | 'vector' | 'deep'

export interface SearchConfig {
  mode: SearchMode
  vectorWeight: number
  topK: number
  rerank: boolean
  sourceFilter: string
}

interface ConfigPanelProps {
  label: string
  config: SearchConfig
  onChange: (config: SearchConfig) => void
  onRemove?: () => void
  sources: LibrarySource[]
  canRemove: boolean
}

export default function ConfigPanel({
  label,
  config,
  onChange,
  onRemove,
  sources,
  canRemove,
}: ConfigPanelProps) {
  const update = (patch: Partial<SearchConfig>) =>
    onChange({ ...config, ...patch })

  return (
    <div className="rounded-lg border border-border/60 bg-muted/20 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">{label}</h3>
        {canRemove && onRemove && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
            onClick={onRemove}
          >
            <X className="w-3.5 h-3.5" />
          </Button>
        )}
      </div>

      {/* Search Mode */}
      <div className="space-y-1">
        <div className="flex items-center gap-1">
          <Label className="text-xs text-muted-foreground">Search Mode</Label>
          <HelpTooltip helpKey={`libraries.searchMode.${config.mode}`} side="right" className="text-muted-foreground/70" />
        </div>
        <Select
          value={config.mode}
          onValueChange={(v) => update({ mode: v as SearchMode })}
        >
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="hybrid">Hybrid</SelectItem>
            <SelectItem value="vector">Vector Only</SelectItem>
            <SelectItem value="deep">Deep Search</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Vector Weight (Hybrid only) */}
      {config.mode === 'hybrid' && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1">
              <Label className="text-xs text-muted-foreground">Vector Weight</Label>
              <HelpTooltip helpKey="libraries.vectorWeight" side="right" className="text-muted-foreground/70" />
            </div>
            <span className="text-xs font-mono text-muted-foreground">
              {config.vectorWeight.toFixed(1)}
            </span>
          </div>
          <Slider
            value={config.vectorWeight}
            onValueChange={(v) => update({ vectorWeight: v })}
            min={0}
            max={1}
            step={0.1}
          />
          <div className="flex justify-between text-[10px] text-muted-foreground/60">
            <span>Keyword</span>
            <span>Semantic</span>
          </div>
        </div>
      )}

      {/* Documents per search */}
      <div className="space-y-1">
        <div className="flex items-center gap-1">
          <Label className="text-xs text-muted-foreground">Docs per search</Label>
          <HelpTooltip helpKey="libraries.topK" side="right" className="text-muted-foreground/70" />
        </div>
        <Select
          value={String(config.topK)}
          onValueChange={(v) => update({ topK: parseInt(v, 10) })}
        >
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="5">5</SelectItem>
            <SelectItem value="10">10</SelectItem>
            <SelectItem value="20">20</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Reranking */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <Label className="text-xs text-muted-foreground">Reranking</Label>
          <HelpTooltip helpKey="libraries.reranking" side="right" className="text-muted-foreground/70" />
        </div>
        <Switch
          checked={config.rerank}
          onCheckedChange={(v) => update({ rerank: v })}
        />
      </div>

      {/* Source Filter */}
      {sources.length > 0 && (
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Source</Label>
          <Select
            value={config.sourceFilter}
            onValueChange={(v) => update({ sourceFilter: v })}
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sources</SelectItem>
              {sources.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  )
}
