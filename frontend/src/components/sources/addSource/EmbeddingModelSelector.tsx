import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { EmbeddingConfig } from '../../../services/api'

interface EmbeddingModelSelectorProps {
  embeddingConfig: EmbeddingConfig | null
  useCustomEmbedding: boolean
  onUseCustomChange: (value: boolean) => void
  selectedProvider: string
  onProviderChange: (value: string) => void
  selectedModel: string
  onModelChange: (value: string) => void
  /** Compact mode for inline display */
  compact?: boolean
  /** ID prefix for form elements */
  idPrefix?: string
}

export default function EmbeddingModelSelector({
  embeddingConfig,
  useCustomEmbedding,
  onUseCustomChange,
  selectedProvider,
  onProviderChange,
  selectedModel,
  onModelChange,
  compact = false,
  idPrefix = 'embed',
}: EmbeddingModelSelectorProps) {
  const handleProviderChange = (value: string) => {
    onProviderChange(value)
    // Reset model when provider changes
    const firstModel = embeddingConfig?.available_models.find(
      (m) => m.provider === value
    )
    if (firstModel) {
      onModelChange(firstModel.model)
    }
  }

  if (compact) {
    return (
      <div className="p-3 border rounded-lg space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-sm">Embedding Model</Label>
          <div className="flex items-center gap-2">
            <Switch
              checked={useCustomEmbedding}
              onCheckedChange={onUseCustomChange}
            />
            <span className="text-xs text-muted-foreground">
              {useCustomEmbedding ? 'Custom' : 'Default'}
            </span>
          </div>
        </div>
        {!useCustomEmbedding && embeddingConfig && (
          <p className="text-xs text-muted-foreground">
            Using {embeddingConfig.default_provider}/{embeddingConfig.default_model}
          </p>
        )}
        {useCustomEmbedding && embeddingConfig && (
          <div className="grid grid-cols-2 gap-2">
            <Select value={selectedProvider} onValueChange={handleProviderChange}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Provider" />
              </SelectTrigger>
              <SelectContent>
                {[...new Set(embeddingConfig.available_models.map((m) => m.provider))].map(
                  (provider) => (
                    <SelectItem key={provider} value={provider}>
                      {provider}
                    </SelectItem>
                  )
                )}
              </SelectContent>
            </Select>
            <Select value={selectedModel} onValueChange={onModelChange}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Model" />
              </SelectTrigger>
              <SelectContent>
                {embeddingConfig.available_models
                  .filter((m) => m.provider === selectedProvider)
                  .map((model) => (
                    <SelectItem key={model.model} value={model.model}>
                      {model.model} ({model.dimensions}d)
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-3 pt-4 border-t">
      <Label>Embedding Model</Label>
      <div className="flex items-center gap-2">
        <Switch
          checked={useCustomEmbedding}
          onCheckedChange={onUseCustomChange}
        />
        <span className="text-sm text-muted-foreground">
          {useCustomEmbedding
            ? 'Custom embedding model'
            : `Use default (${embeddingConfig?.default_provider || 'loading...'}/${embeddingConfig?.default_model || ''})`}
        </span>
      </div>

      {useCustomEmbedding && embeddingConfig && (
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label htmlFor={`${idPrefix}-provider`} className="text-xs">
              Provider
            </Label>
            <Select value={selectedProvider} onValueChange={handleProviderChange}>
              <SelectTrigger id={`${idPrefix}-provider`}>
                <SelectValue placeholder="Select provider" />
              </SelectTrigger>
              <SelectContent>
                {[...new Set(embeddingConfig.available_models.map((m) => m.provider))].map(
                  (provider) => (
                    <SelectItem key={provider} value={provider}>
                      {provider}
                    </SelectItem>
                  )
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor={`${idPrefix}-model`} className="text-xs">
              Model
            </Label>
            <Select value={selectedModel} onValueChange={onModelChange}>
              <SelectTrigger id={`${idPrefix}-model`}>
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent>
                {embeddingConfig.available_models
                  .filter((m) => m.provider === selectedProvider)
                  .map((model) => (
                    <SelectItem key={model.model} value={model.model}>
                      {model.model}{' '}
                      <span className="text-muted-foreground text-xs">
                        ({model.dimensions}d)
                      </span>
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}
    </div>
  )
}
