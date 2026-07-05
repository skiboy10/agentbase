import { useState, useEffect, useMemo } from 'react'
import { Loader2 } from 'lucide-react'
import { providersApi } from '../../services/api/providers'
import type { Provider } from '../../services/api/types/common'
import type { Agent } from '../../services/api/types/agents'
import type { ExperimentOverrides } from '../../services/api/types/evaluation'
import { getEnabledModelsForProvider } from '../../pages/ProvidersPage'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
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
import { Textarea } from '@/components/ui/textarea'

export interface ExperimentFormValues {
  agent_id: string
  name: string
  description?: string
  overrides: ExperimentOverrides
}

interface ExperimentFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  agents: Agent[]
  /** Library the experiment is scoped to — the agent list is filtered to its bound agents. */
  libraryId: string
  /** Submit handler — resolves on success, throws on failure (dialog shows error). */
  onSubmit: (values: ExperimentFormValues) => Promise<void>
}

/** One override row: an include switch gating its field. Only toggled-on fields ship. */
function OverrideRow({
  label,
  included,
  onIncludedChange,
  children,
}: {
  label: string
  included: boolean
  onIncludedChange: (on: boolean) => void
  children: React.ReactNode
}) {
  return (
    <div className="rounded-md border border-border p-3 space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-sm">{label}</Label>
        <Switch
          checked={included}
          onCheckedChange={onIncludedChange}
          aria-label={`Override ${label}`}
        />
      </div>
      {included && children}
    </div>
  )
}

/**
 * Create-experiment form: pick the agent to experiment on, then toggle on the
 * config fields to override. Untouched fields keep the agent's live values.
 */
export function ExperimentFormDialog({
  open, onOpenChange, agents, libraryId, onSubmit,
}: ExperimentFormDialogProps) {
  const [providers, setProviders] = useState<Provider[]>([])
  const [agentId, setAgentId] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Override include-toggles + values
  const [includeTemperature, setIncludeTemperature] = useState(false)
  const [temperature, setTemperature] = useState(0.7)
  const [includeModel, setIncludeModel] = useState(false)
  const [modelProvider, setModelProvider] = useState('')
  const [modelName, setModelName] = useState('')
  const [includeTopK, setIncludeTopK] = useState(false)
  const [topK, setTopK] = useState(5)
  const [includePrompt, setIncludePrompt] = useState(false)
  const [systemPrompt, setSystemPrompt] = useState('')

  const agent = agents.find(a => a.id === agentId) ?? null

  // Scoring an unrelated agent against this library's question sets produces
  // meaningless numbers — offer only bound agents. When none are bound (e.g.
  // a new library), fall back to all agents with a warning so the flow still works.
  const boundAgents = useMemo(
    () => agents.filter(a => a.library_ids?.includes(libraryId)),
    [agents, libraryId]
  )
  const noneBound = boundAgents.length === 0
  const agentOptions = noneBound ? agents : boundAgents

  // Reset the form on every open
  useEffect(() => {
    if (!open) return
    setAgentId('')
    setName('')
    setDescription('')
    setError(null)
    setIncludeTemperature(false)
    setIncludeModel(false)
    setIncludeTopK(false)
    setIncludePrompt(false)
  }, [open])

  useEffect(() => {
    if (!open) return
    providersApi
      .list()
      .then(setProviders)
      .catch(() => setProviders([])) // selects degrade to empty; agent values still shown
  }, [open])

  // Seed override values from the chosen agent's live config for editing
  useEffect(() => {
    if (!agent) return
    setTemperature(agent.temperature)
    setModelProvider(agent.model_provider)
    setModelName(agent.model_name)
    setTopK(agent.rag_top_k)
    setSystemPrompt(agent.system_prompt)
  }, [agent])

  const enabledModels = useMemo(() => {
    const provider = providers.find(p => p.name === modelProvider)
    return provider ? getEnabledModelsForProvider(provider) : []
  }, [providers, modelProvider])

  const overrideCount = [includeTemperature, includeModel, includeTopK, includePrompt]
    .filter(Boolean).length
  const canSubmit = !!agentId && !!name.trim() && overrideCount > 0

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSaving(true)
    setError(null)
    // Keys = Agent column names verbatim (model_provider/model_name, not provider/model)
    const overrides: ExperimentOverrides = {}
    if (includeTemperature) overrides.temperature = temperature
    if (includeModel) {
      overrides.model_provider = modelProvider
      overrides.model_name = modelName
    }
    if (includeTopK) overrides.rag_top_k = topK
    if (includePrompt) overrides.system_prompt = systemPrompt
    try {
      await onSubmit({
        agent_id: agentId,
        name: name.trim(),
        description: description.trim() || undefined,
        overrides,
      })
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create experiment')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New Pipeline Experiment</DialogTitle>
          <DialogDescription>
            Try config changes against an agent without touching its live setup.
            Toggle on only the fields to override.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="space-y-1.5">
            <Label htmlFor="experiment-name">Name</Label>
            <Input
              id="experiment-name"
              placeholder="e.g., Lower temperature, wider retrieval"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="experiment-description">Description</Label>
            <Textarea
              id="experiment-description"
              rows={2}
              placeholder="What this experiment tests (optional)"
              value={description}
              onChange={e => setDescription(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label>Agent</Label>
            <Select value={agentId || undefined} onValueChange={setAgentId}>
              <SelectTrigger aria-label="Select agent">
                <SelectValue placeholder="Select the agent to experiment on..." />
              </SelectTrigger>
              <SelectContent>
                {agentOptions.map(a => (
                  <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
                ))}
                {agentOptions.length === 0 && (
                  <div className="px-3 py-2 text-sm text-muted-foreground">
                    No agents yet — create one on the Agents page
                  </div>
                )}
              </SelectContent>
            </Select>
            {noneBound && agents.length > 0 && (
              <p className="text-xs text-muted-foreground">
                No agents are bound to this library — results against its question
                sets may not be meaningful. Bind one on the Agents page.
              </p>
            )}
          </div>

          {agent && (
            <div className="space-y-2.5">
              <p className="text-xs text-muted-foreground">
                Overrides ({overrideCount} selected — at least one required)
              </p>

              <OverrideRow
                label="Temperature"
                included={includeTemperature}
                onIncludedChange={setIncludeTemperature}
              >
                <div className="flex items-center gap-3">
                  <Slider
                    value={temperature}
                    onValueChange={setTemperature}
                    min={0}
                    max={2}
                    step={0.05}
                    aria-label="Temperature override"
                  />
                  <span className="text-sm tabular-nums w-12 text-right">{temperature.toFixed(2)}</span>
                </div>
              </OverrideRow>

              <OverrideRow label="Model" included={includeModel} onIncludedChange={setIncludeModel}>
                <div className="grid grid-cols-2 gap-2">
                  <Select
                    value={modelProvider || undefined}
                    onValueChange={value => {
                      const provider = providers.find(p => p.name === value)
                      const models = provider ? getEnabledModelsForProvider(provider) : []
                      setModelProvider(value)
                      setModelName(models[0] || '')
                    }}
                  >
                    <SelectTrigger aria-label="Provider override">
                      <SelectValue placeholder="Provider" />
                    </SelectTrigger>
                    <SelectContent>
                      {providers.map(p => (
                        <SelectItem key={p.name} value={p.name}>{p.display_name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select value={modelName || undefined} onValueChange={setModelName}>
                    <SelectTrigger aria-label="Model override">
                      <SelectValue placeholder="Model" />
                    </SelectTrigger>
                    <SelectContent>
                      {enabledModels.map(m => (
                        <SelectItem key={m} value={m}>{m}</SelectItem>
                      ))}
                      {enabledModels.length === 0 && modelName && (
                        <SelectItem value={modelName}>{modelName}</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>
              </OverrideRow>

              <OverrideRow label="RAG top-k" included={includeTopK} onIncludedChange={setIncludeTopK}>
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={topK}
                  onChange={e => setTopK(Math.max(1, parseInt(e.target.value, 10) || 1))}
                  aria-label="RAG top-k override"
                  className="w-28"
                />
              </OverrideRow>

              <OverrideRow
                label="System prompt"
                included={includePrompt}
                onIncludedChange={setIncludePrompt}
              >
                <Textarea
                  rows={6}
                  value={systemPrompt}
                  onChange={e => setSystemPrompt(e.target.value)}
                  className="font-mono text-sm"
                  aria-label="System prompt override"
                />
              </OverrideRow>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={saving || !canSubmit}>
            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Create Experiment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
