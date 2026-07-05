import { useState, useEffect, useCallback } from 'react'
import { Bot, Plus, Loader2 } from 'lucide-react'
import { agentsApi, sourcesApi, providersApi, libraryApi, Agent, AgentUpdate, Source, Provider } from '../services/api'
import { useStudioEvents } from '../hooks/useStudioEvents'
import { useToast } from '@/hooks/use-toast'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import { ErrorBanner, PageHeader, StatsGrid, EmptyState, WorkflowHint } from '../components'
import { AgentCard, AgentFormDialog, ApiKeyDialog, AgentFormData, AgentSaveOptions } from '../components/agents'

export default function AgentbasePage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [sources, setSources] = useState<Source[]>([])
  const [providers, setProviders] = useState<Provider[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  // Modal states
  const [showAddModal, setShowAddModal] = useState(false)
  const [editAgent, setEditAgent] = useState<Agent | null>(null)
  const [deleteAgent, setDeleteAgent] = useState<Agent | null>(null)
  const [apiKeyAgent, setApiKeyAgent] = useState<Agent | null>(null)
  const [generatedApiKey, setGeneratedApiKey] = useState<string | null>(null)

  // Operation states
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [generatingKey, setGeneratingKey] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const [allAgentsData, sourcesData, providersData] = await Promise.all([
        agentsApi.list(),
        sourcesApi.listSources(),
        providersApi.list(),
      ])

      setAgents(allAgentsData)
      setSources(sourcesData.filter(s => s.status === 'indexed'))
      setProviders(providersData.filter(p => p.is_configured && p.is_active && p.available_models.length > 0))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  useStudioEvents({
    onAgentCreated: () => fetchData(),
    onAgentUpdated: () => fetchData(),
    onAgentDeleted: () => fetchData(),
  })

  const handleSaveAgent = async (formData: AgentFormData, options?: AgentSaveOptions) => {
    try {
      setSaving(true)
      setError(null)

      if (editAgent) {
        const updateData: AgentUpdate = {
          name: formData.name,
          description: formData.description || undefined,
          system_prompt: formData.system_prompt,
          model_provider: formData.model_provider,
          model_name: formData.model_name,
          temperature: formData.temperature,
          use_rag: formData.use_rag,
          rag_top_k: formData.rag_top_k,
          source_ids: formData.source_ids,
          skills: formData.skills,
          is_public: formData.is_public,
        }
        const updated = await agentsApi.update(editAgent.id, updateData)

        // Reconcile library bindings — skipped if the bindings baseline never
        // loaded in the form (delta would unbind everything from an empty value)
        if (!options?.skipLibrarySync) {
          await syncLibraryBindings(editAgent.id, formData.library_ids)
        }

        setAgents(prev => prev.map(a => a.id === updated.id ? updated : a))
        setEditAgent(null)
      } else {
        const created = await agentsApi.create({
          name: formData.name,
          description: formData.description || undefined,
          system_prompt: formData.system_prompt,
          model_provider: formData.model_provider,
          model_name: formData.model_name,
          temperature: formData.temperature,
          use_rag: formData.use_rag,
          rag_top_k: formData.rag_top_k,
          source_ids: formData.source_ids,
          skills: formData.skills,
          is_public: formData.is_public,
        })
        // Bind any selected libraries to the newly created agent.
        // A fresh agent has no bindings, so pass a known-empty baseline
        // (skips a pointless listLibraries round-trip).
        if (formData.library_ids.length > 0) {
          await syncLibraryBindings(created.id, formData.library_ids, [])
        }
        setAgents(prev => [created, ...prev])
        setShowAddModal(false)
      }
    } catch (err) {
      // Toast, not the page ErrorBanner — the form dialog stays open on
      // failure and would hide a banner behind it. Save rejections now
      // include the backend model preflight (#176), so the message must
      // be visible while the user can still fix the form.
      toast({
        title: 'Agent not saved',
        description: err instanceof Error ? err.message : 'Failed to save agent',
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }

  /**
   * Sync library bindings for an agent.
   *
   * Edit flows: fetches current bindings, then binds/unbinds the delta.
   * If that fetch fails, the sync is ABORTED (proceeding with an empty
   * baseline would silently drop unbinds and duplicate binds).
   *
   * Create flows: pass `knownBoundIds: []` — a fresh agent has no bindings,
   * so the fetch is skipped.
   *
   * Failures are surfaced as toasts (non-fatal — agent data itself was saved).
   */
  const syncLibraryBindings = async (
    agentId: string,
    desiredIds: string[],
    knownBoundIds?: string[]
  ) => {
    let boundIds: string[]
    if (knownBoundIds) {
      boundIds = knownBoundIds
    } else {
      try {
        const bound = await agentsApi.listLibraries(agentId)
        boundIds = bound.map(l => l.id)
      } catch {
        toast({
          title: 'Library bindings not updated',
          description:
            'Agent saved, but current library bindings could not be loaded. Library changes were skipped — reopen the agent and try again.',
          variant: 'destructive',
        })
        return
      }
    }

    const desired = new Set(desiredIds)
    const boundSet = new Set(boundIds)

    const toAdd = desiredIds.filter(id => !boundSet.has(id))
    const toRemove = boundIds.filter(id => !desired.has(id))
    if (toAdd.length === 0 && toRemove.length === 0) return

    // Map library ids to names for readable error toasts
    let nameById = new Map<string, string>()
    try {
      const libs = await libraryApi.list()
      nameById = new Map(libs.map(l => [l.id, l.name]))
    } catch {
      // fall back to raw ids in messages
    }
    const nameOf = (id: string) => nameById.get(id) ?? id

    const bindErrors: string[] = []

    await Promise.all([
      ...toAdd.map(id =>
        agentsApi.bindLibrary(agentId, id).catch(() => {
          bindErrors.push(`bind "${nameOf(id)}"`)
        })
      ),
      ...toRemove.map(id =>
        agentsApi.unbindLibrary(agentId, id).catch(() => {
          bindErrors.push(`unbind "${nameOf(id)}"`)
        })
      ),
    ])

    if (bindErrors.length > 0) {
      toast({
        title: 'Library binding issue',
        description: `Agent saved, but some library bindings failed: could not ${bindErrors.join(', ')}.`,
        variant: 'destructive',
      })
    }
  }

  const handleDelete = async () => {
    if (!deleteAgent) return
    try {
      setDeleting(true)
      await agentsApi.delete(deleteAgent.id)
      setAgents(prev => prev.filter(a => a.id !== deleteAgent.id))
      setDeleteAgent(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete agent')
    } finally {
      setDeleting(false)
    }
  }

  const handleDuplicate = async (agent: Agent) => {
    try {
      setError(null)
      const duplicated = await agentsApi.duplicate(agent.id, {
        new_name: `${agent.name} (Copy)`,
      })
      setAgents(prev => [duplicated, ...prev])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to duplicate agent')
    }
  }

  const handleGenerateApiKey = async () => {
    if (!apiKeyAgent) return
    try {
      setGeneratingKey(true)
      const result = await agentsApi.generateApiKey(apiKeyAgent.id)
      setGeneratedApiKey(result.api_key)
      setAgents(prev => prev.map(a => a.id === apiKeyAgent.id ? { ...a, has_api_key: true, is_public: true } : a))
      setApiKeyAgent(prev => prev ? { ...prev, has_api_key: true, is_public: true } : prev)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate API key')
    } finally {
      setGeneratingKey(false)
    }
  }

  const renderAgentCard = (agent: Agent) => (
    <AgentCard
      key={agent.id}
      agent={agent}
      onEdit={() => setEditAgent(agent)}
      onDuplicate={() => handleDuplicate(agent)}
      onDelete={() => setDeleteAgent(agent)}
      onManageApiKey={() => {
        setApiKeyAgent(agent)
        setGeneratedApiKey(null)
      }}
    />
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </div>
    )
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        <PageHeader
          title="Agents"
          description="Define agents with prompts, knowledge, and model settings — accessible via API and MCP"
          helpKey="agents.page"
          extra={<WorkflowHint />}
          action={{
            label: 'New Agent',
            icon: <Plus className="w-5 h-5 mr-2" />,
            onClick: () => setShowAddModal(true),
          }}
        />

        <StatsGrid
          stats={[
            { value: agents.length, label: 'Total Agents' },
            { value: agents.filter(a => a.is_public).length, label: 'Public Agents' },
          ]}
        />

        {agents.length === 0 ? (
          <EmptyState
            icon={<Bot className="w-16 h-16" />}
            title="No agents yet"
            description="Create your first agent to get started"
            action={{ label: 'Create Agent', onClick: () => setShowAddModal(true) }}
          />
        ) : (
          <div className="space-y-3">
            {agents.map((agent) => renderAgentCard(agent))}
          </div>
        )}

        {/* Add/Edit Agent Modal */}
        <AgentFormDialog
          open={showAddModal || !!editAgent}
          onOpenChange={(open) => {
            if (!open) {
              setShowAddModal(false)
              setEditAgent(null)
            }
          }}
          editAgent={editAgent}
          providers={providers}
          sources={sources}
          saving={saving}
          onSave={handleSaveAgent}
        />

        {/* Delete Confirmation Modal */}
        <Dialog open={!!deleteAgent} onOpenChange={(open) => !open && setDeleteAgent(null)}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Delete Agent</DialogTitle>
              <DialogDescription>
                Are you sure you want to delete "{deleteAgent?.name}"? This action cannot be undone.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setDeleteAgent(null)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={handleDelete}
                disabled={deleting}
              >
                {deleting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
                Delete
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* API Key Modal */}
        <ApiKeyDialog
          agent={apiKeyAgent}
          apiKey={generatedApiKey}
          open={!!apiKeyAgent}
          onOpenChange={(open) => {
            if (!open) {
              setApiKeyAgent(null)
              setGeneratedApiKey(null)
            }
          }}
          generatingKey={generatingKey}
          onGenerate={handleGenerateApiKey}
        />
      </div>
    </div>
  )
}
