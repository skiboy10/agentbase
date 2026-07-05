import { useEffect } from 'react'
import { Loader2, Settings } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { AgentFormData, AgentFormDialogProps } from './types'
import { useAgentFormData, usePromptGenerator } from './hooks'
import { BasicTab, SourcesTab, SkillsTab, AccessTab } from './tabs'

export type { AgentFormData, AgentFormDialogProps }

export function AgentFormDialog({
  open,
  onOpenChange,
  editAgent,
  providers,
  sources,
  saving,
  onSave,
}: AgentFormDialogProps) {
  const {
    activeTab,
    setActiveTab,
    formData,
    setFormData,
    toggleSource,
    toggleLibrary,
    toggleSkill,
    isSkillSelected,
    enabledModels,
    libraryLoadStatus,
    retryLibraryLoad,
  } = useAgentFormData({ open, editAgent, providers })

  const promptGen = usePromptGenerator({
    sources,
    selectedSourceIds: formData.source_ids,
    onGenerated: (prompt) => setFormData(prev => ({ ...prev, system_prompt: prompt })),
  })

  useEffect(() => {
    if (open) {
      promptGen.reset()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- promptGen is a stable ref-like object
  }, [open])

  const handleFormChange = (data: Partial<AgentFormData>) => {
    setFormData(prev => ({ ...prev, ...data }))
  }

  const handleSubmit = async () => {
    if (!formData.name.trim() || !formData.system_prompt.trim()) return
    // If the bindings baseline never loaded, the save handler must not compute
    // a library delta — it would unbind everything from an empty form value.
    await onSave(formData, { skipLibrarySync: libraryLoadStatus !== 'loaded' })
  }

  const noProvidersConfigured = providers.length === 0

  // Derive knowledge tab label — show bound count if any
  const knowledgeLabel = formData.library_ids.length > 0
    ? `Knowledge (${formData.library_ids.length})`
    : 'Knowledge'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{editAgent ? 'Edit Agent' : 'Create New Agent'}</DialogTitle>
          <DialogDescription>
            {editAgent
              ? 'Update agent configuration'
              : 'Configure your agent with a prompt, sources, and model settings'}
          </DialogDescription>
        </DialogHeader>

        {noProvidersConfigured ? (
          <div className="py-8 text-center">
            <Settings className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">No Providers Configured</h3>
            <p className="text-muted-foreground mb-4">
              You need to configure at least one LLM provider before creating agents.
            </p>
            <Button asChild>
              <Link to="/providers">Configure Providers</Link>
            </Button>
          </div>
        ) : (
          <>
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="basic">Basic</TabsTrigger>
                <TabsTrigger value="knowledge">{knowledgeLabel}</TabsTrigger>
                <TabsTrigger value="skills">Skills</TabsTrigger>
                <TabsTrigger value="api">Access</TabsTrigger>
              </TabsList>

              <BasicTab
                isEdit={!!editAgent}
                agentId={editAgent?.id}
                providers={providers}
                formData={formData}
                onFormChange={handleFormChange}
                enabledModels={enabledModels}
                promptPurpose={promptGen.purpose}
                onPurposeChange={promptGen.setPurpose}
                onGeneratePrompt={promptGen.generate}
                generatingPrompt={promptGen.generating}
                generateError={promptGen.error}
              />

              <SourcesTab
                formData={formData}
                onFormChange={handleFormChange}
                sources={sources}
                onToggleSource={toggleSource}
                onToggleLibrary={toggleLibrary}
                libraryLoadStatus={libraryLoadStatus}
                onRetryLibraryLoad={retryLibraryLoad}
              />

              <SkillsTab
                formData={formData}
                availableSkills={[]}
                onToggleSkill={toggleSkill}
                isSkillSelected={isSkillSelected}
              />

              <AccessTab
                formData={formData}
                onFormChange={handleFormChange}
              />
            </Tabs>

            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={!formData.name.trim() || !formData.system_prompt.trim() || saving}
              >
                {saving && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
                {editAgent ? 'Save Changes' : 'Create Agent'}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
