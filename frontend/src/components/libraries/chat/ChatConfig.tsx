import { useState, useEffect } from 'react'
import { Settings2 } from 'lucide-react'
import { providersApi } from '../../../services/api/providers'
import type { Provider } from '../../../services/api/types/common'
import type { LibraryChatConfig } from './types'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { HelpTooltip } from '@/components/HelpTooltip'

interface ChatConfigProps {
  config: LibraryChatConfig
  onChange: (c: LibraryChatConfig) => void
  disabled: boolean
}

export default function ChatConfig({ config, onChange, disabled }: ChatConfigProps) {
  const [open, setOpen] = useState(false)
  const [providers, setProviders] = useState<Provider[]>([])

  useEffect(() => {
    let cancelled = false
    providersApi.list().then((list) => {
      if (cancelled) return
      const active = list.filter((p) => p.is_active && p.is_configured)
      setProviders(active)
      // Auto-select first provider/model if config is empty (runs once on mount)
      if (!config.provider && active.length > 0) {
        const first = active[0]
        const availableModels = first.available_models.filter(
          (m) => !first.disabled_models.includes(m)
        )
        onChange({
          ...config,
          provider: first.name,
          model: availableModels[0] ?? '',
        })
      }
    }).catch(() => {
      // Silently fail — providers list stays empty
    })
    return () => { cancelled = true }
  // Intentionally runs once on mount — config/onChange captured from initial render
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectedProvider = providers.find((p) => p.name === config.provider)
  const availableModels = selectedProvider
    ? selectedProvider.available_models.filter(
        (m) => !selectedProvider.disabled_models.includes(m)
      )
    : []

  const handleProviderChange = (providerName: string) => {
    const provider = providers.find((p) => p.name === providerName)
    if (!provider) return
    const models = provider.available_models.filter(
      (m) => !provider.disabled_models.includes(m)
    )
    onChange({ ...config, provider: providerName, model: models[0] ?? '' })
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          disabled={disabled}
          className="flex items-center gap-2 text-muted-foreground hover:text-foreground h-8 px-2"
        >
          <Settings2 className="w-3.5 h-3.5" />
          <span className="text-xs font-medium">Config</span>
          {config.provider && config.model && (
            <span className="text-xs text-muted-foreground/70 font-mono">
              {config.provider}/{config.model}
            </span>
          )}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-2 p-4 rounded-lg border border-border bg-muted/20 grid grid-cols-2 gap-4 sm:grid-cols-3">
          {/* Provider */}
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Provider</Label>
            <Select
              value={config.provider}
              onValueChange={handleProviderChange}
              disabled={disabled || providers.length === 0}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Select provider" />
              </SelectTrigger>
              <SelectContent>
                {providers.map((p) => (
                  <SelectItem key={p.name} value={p.name} className="text-xs">
                    {p.display_name || p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Model */}
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Model</Label>
            <Select
              value={config.model}
              onValueChange={(v) => onChange({ ...config, model: v })}
              disabled={disabled || availableModels.length === 0}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent>
                {availableModels.map((m) => (
                  <SelectItem key={m} value={m} className="text-xs font-mono">
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Documents per search */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-1">
              <Label className="text-xs text-muted-foreground">Docs per search</Label>
              <HelpTooltip helpKey="libraries.topK" side="top" className="text-muted-foreground/70" />
            </div>
            <Select
              value={String(config.top_k)}
              onValueChange={(v) => onChange({ ...config, top_k: Number(v) })}
              disabled={disabled}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[3, 5, 10, 15, 20].map((n) => (
                  <SelectItem key={n} value={String(n)} className="text-xs">
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Search Mode */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-1">
              <Label className="text-xs text-muted-foreground">Search Mode</Label>
              <HelpTooltip helpKey={`libraries.searchMode.${config.search_mode}`} side="top" className="text-muted-foreground/70" />
            </div>
            <Select
              value={config.search_mode}
              onValueChange={(v) =>
                onChange({
                  ...config,
                  search_mode: v as LibraryChatConfig['search_mode'],
                })
              }
              disabled={disabled}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="hybrid" className="text-xs">Hybrid</SelectItem>
                <SelectItem value="vector" className="text-xs">Vector</SelectItem>
                <SelectItem value="deep" className="text-xs">Deep</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Reranking */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-1">
              <Label className="text-xs text-muted-foreground">Reranking</Label>
              <HelpTooltip helpKey="libraries.reranking" side="top" className="text-muted-foreground/70" />
            </div>
            <div className="flex items-center h-8">
              <Switch
                checked={config.rerank}
                onCheckedChange={(checked) => onChange({ ...config, rerank: checked })}
                disabled={disabled}
              />
            </div>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
