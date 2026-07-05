import { useState, useEffect } from 'react'
import { Cloud, Check, X, Eye, EyeOff, RefreshCw, Loader2, ChevronDown, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { providersApi, Provider, ModelAssignment, EmbeddingModel } from '../services/api'
import { PageHeader, ErrorBanner } from '@/components'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

// Export for use by other components - returns only enabled models
// Uses the disabled_models from the Provider object (persisted in database)
export function getEnabledModelsForProvider(provider: Provider): string[] {
  const disabledSet = new Set(provider.disabled_models || [])
  return provider.available_models.filter((m) => !disabledSet.has(m))
}

export default function ProvidersPage() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [assignments, setAssignments] = useState<ModelAssignment[]>([])
  const [embeddingModels, setEmbeddingModels] = useState<EmbeddingModel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showApiKey, setShowApiKey] = useState<Record<string, boolean>>({})
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({})
  const [baseUrls, setBaseUrls] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [testing, setTesting] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; message: string }>>({})
  const [disabledModels, setDisabledModels] = useState<Record<string, string[]>>({})
  const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean>>({})
  const [deleteConfirmProvider, setDeleteConfirmProvider] = useState<string | null>(null)

  const toggleProviderExpanded = (providerName: string) => {
    setExpandedProviders((prev) => ({ ...prev, [providerName]: !prev[providerName] }))
  }

  const fetchData = async () => {
    try {
      setLoading(true)
      setError(null)
      const [providerData, assignmentData, embeddingModelData] = await Promise.all([
        providersApi.list(),
        providersApi.getAssignments(),
        providersApi.listEmbeddingModels(),
      ])
      setProviders(providerData)
      setAssignments(assignmentData)
      setEmbeddingModels(embeddingModelData)

      // Initialize base URLs from providers
      const urls: Record<string, string> = {}
      providerData.forEach((p) => {
        if (p.base_url) {
          urls[p.name] = p.base_url
        }
      })
      setBaseUrls(urls)

      // Initialize disabled models from API response
      const initialized: Record<string, string[]> = {}
      providerData.forEach((p) => {
        // Filter to only keep disabled models that still exist in backend
        initialized[p.name] = (p.disabled_models || []).filter((m) => p.available_models.includes(m))
      })
      setDisabledModels(initialized)

      // Initialize expanded state: configured providers start expanded
      const expanded: Record<string, boolean> = {}
      providerData.forEach((p) => {
        expanded[p.name] = p.is_configured
      })
      setExpandedProviders(expanded)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load providers')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    fetchData()
    return () => controller.abort()
  }, [])

  const toggleModelEnabled = async (providerName: string, modelName: string) => {
    const providerDisabled = disabledModels[providerName] || []
    const isDisabled = providerDisabled.includes(modelName)
    const updated = isDisabled
      ? providerDisabled.filter((m) => m !== modelName) // Enable: remove from disabled list
      : [...providerDisabled, modelName] // Disable: add to disabled list

    // Optimistically update UI
    setDisabledModels((prev) => ({ ...prev, [providerName]: updated }))

    // Persist to backend
    try {
      await providersApi.update(providerName, { disabled_models: updated })
    } catch (err) {
      // Revert on error
      setDisabledModels((prev) => ({ ...prev, [providerName]: providerDisabled }))
      setError(err instanceof Error ? err.message : 'Failed to update model settings')
    }
  }

  const isModelEnabled = (providerName: string, modelName: string): boolean => {
    const providerDisabled = disabledModels[providerName] || []
    return !providerDisabled.includes(modelName)
  }

  const toggleShowApiKey = (provider: string) => {
    setShowApiKey((prev) => ({ ...prev, [provider]: !prev[provider] }))
  }

  const handleSaveConfig = async (providerName: string) => {
    try {
      setSaving(providerName)
      setError(null)

      const config: { api_key?: string; base_url?: string } = {}
      if (apiKeys[providerName]) {
        config.api_key = apiKeys[providerName]
      }
      if (baseUrls[providerName]) {
        config.base_url = baseUrls[providerName]
      }

      await providersApi.update(providerName, config)
      await fetchData() // Refresh to get updated status
      setApiKeys((prev) => ({ ...prev, [providerName]: '' })) // Clear input after save
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save configuration')
    } finally {
      setSaving(null)
    }
  }

  const handleDeleteConfig = async (providerName: string) => {
    try {
      setDeleting(providerName)
      setError(null)
      await providersApi.delete(providerName)
      await fetchData() // Refresh to get updated status
      setTestResults((prev) => {
        const updated = { ...prev }
        delete updated[providerName]
        return updated
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete configuration')
    } finally {
      setDeleting(null)
      setDeleteConfirmProvider(null)
    }
  }

  const handleTestConnection = async (providerName: string) => {
    try {
      setTesting(providerName)
      setTestResults((prev) => ({ ...prev, [providerName]: { success: false, message: 'Testing...' } }))

      const result = await providersApi.test(providerName)
      setTestResults((prev) => ({
        ...prev,
        [providerName]: {
          success: result.healthy,
          message: result.message + (result.model_count ? ` (${result.model_count} models)` : ''),
        },
      }))
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [providerName]: {
          success: false,
          message: err instanceof Error ? err.message : 'Test failed',
        },
      }))
    } finally {
      setTesting(null)
    }
  }

  const handleAssignModel = async (taskType: string, provider: string, model: string) => {
    try {
      await providersApi.assignModel({ task_type: taskType, provider, model })
      const updatedAssignments = await providersApi.getAssignments()
      setAssignments(updatedAssignments)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to assign model')
    }
  }

  const getProviderDescription = (name: string) => {
    const descriptions: Record<string, string> = {
      ollama: 'Run local LLM models. No API key required.',
      openai: 'GPT-4, GPT-3.5-turbo, and embedding models.',
      anthropic: 'Claude models with large context windows.',
      grok: "xAI's Grok models.",
      google: 'Gemini models from Google AI.',
    }
    return descriptions[name] || ''
  }

  const getCurrentAssignment = (taskType: string) => {
    return assignments.find((a) => a.task_type === taskType)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </div>
    )
  }

  return (
    <div className="p-6">
      <div className="max-w-4xl mx-auto">
        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        <PageHeader
          title="LLM Providers"
          description="Connect LLM providers and configure which models are available for agents"
        />

        <div className="grid gap-4">
          {providers.map((provider) => (
            <Collapsible
              key={provider.name}
              open={expandedProviders[provider.name]}
              onOpenChange={() => toggleProviderExpanded(provider.name)}
            >
              <Card>
                <CollapsibleTrigger asChild>
                  <div className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/50 transition-colors rounded-t-lg">
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          'w-10 h-10 rounded-lg flex items-center justify-center',
                          provider.is_configured ? 'bg-status-success/15' : 'bg-muted'
                        )}
                      >
                        <Cloud className="w-5 h-5 text-foreground" />
                      </div>
                      <div>
                        <h3 className="text-lg font-semibold text-foreground">
                          {provider.display_name}
                        </h3>
                        <p className="text-sm text-muted-foreground">{getProviderDescription(provider.name)}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge variant={provider.is_configured ? 'default' : 'secondary'}>
                        {provider.is_configured ? (
                          <span className="flex items-center gap-1">
                            <Check className="w-3 h-3" />
                            Configured
                          </span>
                        ) : (
                          <span className="flex items-center gap-1">
                            <X className="w-3 h-3" />
                            Not configured
                          </span>
                        )}
                      </Badge>
                      {provider.is_configured && (
                        <span className="text-xs text-muted-foreground">
                          {provider.available_models.length} models
                        </span>
                      )}
                      <ChevronDown
                        className={cn(
                          'w-5 h-5 text-muted-foreground transition-transform',
                          expandedProviders[provider.name] && 'rotate-180'
                        )}
                      />
                    </div>
                  </div>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <CardContent className="pt-0 pb-4">
                    {/* Test Result */}
                    {testResults[provider.name] && (
                      <div
                        className={cn(
                          'mb-4 p-2 rounded-lg text-sm',
                          testResults[provider.name].success
                            ? 'bg-status-success/15 text-status-success-foreground'
                            : 'bg-destructive/30 text-destructive'
                        )}
                      >
                        {testResults[provider.name].message}
                      </div>
                    )}

                    {provider.requires_api_key ? (
                      <div className="mb-4 space-y-2">
                        <Label>API Key</Label>
                        <div className="flex gap-2">
                          <div className="relative flex-1">
                            <Input
                              type={showApiKey[provider.name] ? 'text' : 'password'}
                              value={apiKeys[provider.name] || ''}
                              onChange={(e) =>
                                setApiKeys((prev) => ({
                                  ...prev,
                                  [provider.name]: e.target.value,
                                }))
                              }
                              placeholder={provider.is_configured ? '••••••••' : 'Enter API key'}
                              className="pr-10"
                            />
                            <button
                              type="button"
                              onClick={() => toggleShowApiKey(provider.name)}
                              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                            >
                              {showApiKey[provider.name] ? (
                                <EyeOff className="w-4 h-4" />
                              ) : (
                                <Eye className="w-4 h-4" />
                              )}
                            </button>
                          </div>
                          <Button
                            onClick={() => handleSaveConfig(provider.name)}
                            disabled={saving === provider.name || !apiKeys[provider.name]}
                          >
                            {saving === provider.name ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              'Save'
                            )}
                          </Button>
                          <Button
                            variant="secondary"
                            size="icon"
                            onClick={() => handleTestConnection(provider.name)}
                            disabled={testing === provider.name}
                          >
                            {testing === provider.name ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <RefreshCw className="w-4 h-4" />
                            )}
                          </Button>
                          {provider.is_configured && (
                            <Button
                              variant="destructive"
                              size="icon"
                              onClick={(e) => {
                                e.stopPropagation()
                                setDeleteConfirmProvider(provider.name)
                              }}
                              disabled={deleting === provider.name}
                            >
                              {deleting === provider.name ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <Trash2 className="w-4 h-4" />
                              )}
                            </Button>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="mb-4 space-y-2">
                        <Label>Base URL</Label>
                        <div className="flex gap-2">
                          <Input
                            type="text"
                            value={baseUrls[provider.name] || 'http://localhost:11434'}
                            onChange={(e) =>
                              setBaseUrls((prev) => ({
                                ...prev,
                                [provider.name]: e.target.value,
                              }))
                            }
                            className="flex-1"
                          />
                          <Button
                            onClick={() => handleSaveConfig(provider.name)}
                            disabled={saving === provider.name}
                          >
                            {saving === provider.name ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              'Save'
                            )}
                          </Button>
                          <Button
                            variant="secondary"
                            size="icon"
                            onClick={() => handleTestConnection(provider.name)}
                            disabled={testing === provider.name}
                          >
                            {testing === provider.name ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <RefreshCw className="w-4 h-4" />
                            )}
                          </Button>
                        </div>
                      </div>
                    )}

                    <div className="space-y-2">
                      <Label>Available Models</Label>
                      <p className="text-xs text-muted-foreground mb-2">
                        Click models to enable/disable them in selection menus
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {provider.available_models.length > 0 ? (
                          provider.available_models.map((model) => {
                            const enabled = isModelEnabled(provider.name, model)
                            return (
                              <Badge
                                key={model}
                                variant={enabled ? 'default' : 'outline'}
                                className={cn(
                                  'cursor-pointer transition-all select-none',
                                  enabled
                                    ? 'bg-emerald-600 hover:bg-emerald-700 text-white border-emerald-600'
                                    : 'bg-transparent hover:bg-muted/50 text-muted-foreground border-muted-foreground/30 opacity-60'
                                )}
                                onClick={() => toggleModelEnabled(provider.name, model)}
                              >
                                {model}
                              </Badge>
                            )
                          })
                        ) : (
                          <span className="text-muted-foreground text-sm">
                            {provider.is_configured ? 'Fetching models...' : 'Configure provider to see models'}
                          </span>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </CollapsibleContent>
              </Card>
            </Collapsible>
          ))}
        </div>

        {/* Default Model & Embedder Section */}
        <div className="mt-8">
          <Card>
            <CardHeader>
              <CardTitle>Defaults</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="default-model">Default Model</Label>
                  <select
                    id="default-model"
                    value={
                      getCurrentAssignment('knowledge')
                        ? `${getCurrentAssignment('knowledge')?.provider}||${getCurrentAssignment('knowledge')?.model}`
                        : ''
                    }
                    onChange={(e) => {
                      const [provider, ...modelParts] = e.target.value.split('||')
                      const model = modelParts.join('||')
                      if (provider && model) {
                        handleAssignModel('knowledge', provider, model)
                      }
                    }}
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    <option value="">Select model...</option>
                    {providers
                      .filter((p) => p.is_configured && p.available_models.length > 0)
                      .map((provider) => {
                        const providerDisabled = disabledModels[provider.name] || []
                        const filteredModels = provider.available_models.filter((m) => !providerDisabled.includes(m))
                        if (filteredModels.length === 0) return null
                        return (
                          <optgroup key={provider.name} label={provider.display_name}>
                            {filteredModels.map((model) => (
                              <option key={`${provider.name}||${model}`} value={`${provider.name}||${model}`}>
                                {model}
                              </option>
                            ))}
                          </optgroup>
                        )
                      })}
                  </select>
                  <p className="text-xs text-muted-foreground">
                    Used for chat and agent conversations
                  </p>
                  {getCurrentAssignment('knowledge') && (
                    <p className="text-xs text-primary">
                      Current: {getCurrentAssignment('knowledge')?.provider}/{getCurrentAssignment('knowledge')?.model}
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="default-embedder">Default Embedder</Label>
                  <select
                    id="default-embedder"
                    value={
                      getCurrentAssignment('embedding')
                        ? `${getCurrentAssignment('embedding')?.provider}||${getCurrentAssignment('embedding')?.model}`
                        : ''
                    }
                    onChange={(e) => {
                      const [provider, ...modelParts] = e.target.value.split('||')
                      const model = modelParts.join('||')
                      if (provider && model) {
                        handleAssignModel('embedding', provider, model)
                      }
                    }}
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    <option value="">Select embedding model...</option>
                    {embeddingModels.map((model) => (
                      <option key={`${model.provider}||${model.id}`} value={`${model.provider}||${model.id}`}>
                        {model.name} ({model.provider}) - {model.dimensions}d
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground">
                    Used for library indexing and semantic search
                  </p>
                  {getCurrentAssignment('embedding') && (
                    <p className="text-xs text-primary">
                      Current: {getCurrentAssignment('embedding')?.provider}/{getCurrentAssignment('embedding')?.model}
                    </p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteConfirmProvider} onOpenChange={() => setDeleteConfirmProvider(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Provider Configuration</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete the configuration for{' '}
              <strong>
                {deleteConfirmProvider && providers.find((p) => p.name === deleteConfirmProvider)?.display_name}
              </strong>
              ? This will remove the API key and all settings for this provider.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteConfirmProvider && handleDeleteConfig(deleteConfirmProvider)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
