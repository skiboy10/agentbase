import { useState } from 'react'
import { Copy, Check, AlertTriangle } from 'lucide-react'
import { Provider } from '../../../services/api'
import { getEnabledModelsForProvider } from '../../../pages/ProvidersPage'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { TabsContent } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { AgentFormData } from '../types'
import { PromptGenerator } from '../components'

interface BasicTabProps {
  isEdit: boolean
  agentId?: string
  providers: Provider[]
  formData: AgentFormData
  onFormChange: (data: Partial<AgentFormData>) => void
  enabledModels: string[]
  promptPurpose: string
  onPurposeChange: (purpose: string) => void
  onGeneratePrompt: () => void
  generatingPrompt: boolean
  generateError: string | null
}

export function BasicTab({
  isEdit,
  agentId,
  providers,
  formData,
  onFormChange,
  enabledModels,
  promptPurpose,
  onPurposeChange,
  onGeneratePrompt,
  generatingPrompt,
  generateError,
}: BasicTabProps) {
  const [copied, setCopied] = useState(false)

  const handleCopyId = () => {
    if (!agentId) return
    navigator.clipboard.writeText(agentId)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // A saved model can disappear from the provider's list (e.g. an Ollama
  // model that was removed or never pulled). Warn without blocking the save —
  // the backend runs the authoritative preflight. When the provider's list is
  // empty the provider may just be unreachable, so we can't know either way.
  const modelUnavailable =
    formData.model_name !== '' &&
    enabledModels.length > 0 &&
    !enabledModels.includes(formData.model_name)

  return (
    <TabsContent value="basic" className="space-y-4 py-4">
      {/* Agent ID - only shown when editing */}
      {isEdit && agentId && (
        <div className="flex items-center gap-2 px-3 py-2 bg-muted/50 rounded-md">
          <span className="text-xs text-muted-foreground">Agent ID:</span>
          <code className="text-xs font-mono text-muted-foreground flex-1 truncate">{agentId}</code>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 shrink-0"
            onClick={handleCopyId}
          >
            {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
          </Button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            value={formData.name}
            onChange={e => onFormChange({ name: e.target.value })}
            placeholder="e.g., Documentation Assistant"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="temperature">Temperature</Label>
          <Select
            value={String(formData.temperature)}
            onValueChange={value => onFormChange({ temperature: parseFloat(value) })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1].map(temp => (
                <SelectItem key={temp} value={String(temp)}>
                  {temp.toFixed(1)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="description">Description (optional)</Label>
        <Input
          id="description"
          value={formData.description}
          onChange={e => onFormChange({ description: e.target.value })}
          placeholder="Brief description of this agent's purpose"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Provider</Label>
          <Select
            value={formData.model_provider}
            onValueChange={value => {
              const provider = providers.find(p => p.name === value)
              const providerEnabledModels = provider
                ? getEnabledModelsForProvider(provider)
                : []
              onFormChange({
                model_provider: value,
                model_name: providerEnabledModels[0] || '',
              })
            }}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {providers.map(provider => (
                <SelectItem key={provider.name} value={provider.name}>
                  {provider.display_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Model</Label>
          <Select
            value={formData.model_name}
            onValueChange={value => onFormChange({ model_name: value })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {/* Keep the saved-but-unavailable model selectable so the
                  trigger doesn't render blank and the user can see what the
                  agent is currently configured with */}
              {modelUnavailable && (
                <SelectItem value={formData.model_name}>
                  {formData.model_name} (not available)
                </SelectItem>
              )}
              {enabledModels.map(model => (
                <SelectItem key={model} value={model}>
                  {model}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {modelUnavailable && (
            <p className="flex items-start gap-1.5 text-xs text-status-warning">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-px" />
              <span>
                '{formData.model_name}' is not in this provider's current model
                list. Queries will fail until the model is available — pick
                another model or make it available on the provider.
              </span>
            </p>
          )}
        </div>
      </div>

      <PromptGenerator
        purpose={promptPurpose}
        onPurposeChange={onPurposeChange}
        onGenerate={onGeneratePrompt}
        generating={generatingPrompt}
        error={generateError}
      />

      <div className="space-y-2">
        <Label htmlFor="system_prompt">System Prompt</Label>
        <Textarea
          id="system_prompt"
          value={formData.system_prompt}
          onChange={e => onFormChange({ system_prompt: e.target.value })}
          placeholder="You are a helpful assistant..."
          rows={8}
          className="font-mono text-sm"
        />
        <p className="text-xs text-muted-foreground">
          Define the agent's behavior, capabilities, and guidelines
        </p>
      </div>
    </TabsContent>
  )
}
