import { useState, useEffect, useCallback } from 'react'
import { MessageSquare, Plus, Trash2, Loader2, Copy, Pencil, Star, Globe, FileText } from 'lucide-react'
import { cn } from '../lib/utils'
import { promptsApi, Prompt, PromptCreate, PromptUpdate } from '../services/api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useToast } from '@/hooks/use-toast'

// Task type icon component
function TaskTypeIcon({ taskType }: { taskType: string }) {
  switch (taskType) {
    case 'knowledge':
      return <FileText className="w-5 h-5 text-blue-400" />
    default:
      return <MessageSquare className="w-5 h-5 text-purple-400" />
  }
}

export default function PromptStudioPage() {
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Modal states
  const [showAddModal, setShowAddModal] = useState(false)
  const [editPrompt, setEditPrompt] = useState<Prompt | null>(null)
  const [deletePrompt, setDeletePrompt] = useState<Prompt | null>(null)

  // Form state
  const [formData, setFormData] = useState<PromptCreate>({
    name: '',
    task_type: 'knowledge',
    system_prompt: '',
    description: '',
    rag_context_template: '',
    use_rag: true,
    is_default: false,
  })
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const { toast } = useToast()

  // Preview tab state
  const [previewTab, setPreviewTab] = useState<'system' | 'rag'>('system')

  const fetchPrompts = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await promptsApi.list()
      setPrompts(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load prompts')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchPrompts()
  }, [fetchPrompts])

  const resetForm = () => {
    setFormData({
      name: '',
      task_type: 'knowledge',
      system_prompt: '',
      description: '',
      rag_context_template: '',
      use_rag: true,
      is_default: false,
    })
  }

  const handleOpenAdd = () => {
    resetForm()
    setShowAddModal(true)
  }

  const handleOpenEdit = (prompt: Prompt) => {
    setFormData({
      name: prompt.name,
      task_type: prompt.task_type,
      system_prompt: prompt.system_prompt,
      description: prompt.description || '',
      rag_context_template: prompt.rag_context_template || '',
      use_rag: prompt.use_rag,
      is_default: prompt.is_default,
    })
    setEditPrompt(prompt)
  }

  const handleCreate = async () => {
    if (!formData.name.trim() || !formData.system_prompt.trim()) return

    try {
      setSaving(true)
      setError(null)
      const created = await promptsApi.create({
        ...formData,
      })
      setPrompts(prev => [created, ...prev])
      setShowAddModal(false)
      resetForm()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create prompt')
    } finally {
      setSaving(false)
    }
  }

  const handleUpdate = async () => {
    if (!editPrompt || !formData.name.trim() || !formData.system_prompt.trim()) return

    try {
      setSaving(true)
      setError(null)
      const updateData: PromptUpdate = {
        name: formData.name,
        description: formData.description || undefined,
        system_prompt: formData.system_prompt,
        rag_context_template: formData.rag_context_template || undefined,
        use_rag: formData.use_rag,
        is_default: formData.is_default,
        increment_version: true,
      }
      const updated = await promptsApi.update(editPrompt.id, updateData)
      setPrompts(prev => prev.map(p => p.id === updated.id ? updated : p))
      setEditPrompt(null)
      resetForm()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update prompt')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deletePrompt) return

    const promptName = deletePrompt.name
    try {
      setDeleting(true)
      await promptsApi.delete(deletePrompt.id)
      setPrompts(prev => prev.filter(p => p.id !== deletePrompt.id))
      setDeletePrompt(null)
      toast({ title: 'Prompt deleted', description: `"${promptName}" has been removed.` })
    } catch (err) {
      // Keep the confirmation dialog open so the user can retry or cancel
      toast({
        title: 'Failed to delete prompt',
        description: err instanceof Error ? err.message : 'An unexpected error occurred.',
        variant: 'destructive',
      })
    } finally {
      setDeleting(false)
    }
  }

  const handleDuplicate = async (prompt: Prompt) => {
    try {
      setError(null)
      const duplicated = await promptsApi.duplicate(prompt.id, {
        new_name: `${prompt.name} (Copy)`,
      })
      setPrompts(prev => [duplicated, ...prev])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to duplicate prompt')
    }
  }

  const handleSetDefault = async (prompt: Prompt) => {
    try {
      setError(null)
      const updated = await promptsApi.update(prompt.id, { is_default: true })
      // Update local state - unset other defaults for same task type
      setPrompts(prev => prev.map(p => {
        if (p.id === updated.id) return updated
        if (p.task_type === prompt.task_type && p.project_id === prompt.project_id && p.is_default) {
          return { ...p, is_default: false }
        }
        return p
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set default')
    }
  }

  // Group prompts by task type
  const promptsByType = prompts.reduce((acc, prompt) => {
    if (!acc[prompt.task_type]) acc[prompt.task_type] = []
    acc[prompt.task_type].push(prompt)
    return acc
  }, {} as Record<string, Prompt[]>)

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
        {error && (
          <div className="mb-4 p-4 bg-destructive/20 border border-destructive rounded-lg text-destructive-foreground">
            {error}
            <Button
              variant="link"
              className="ml-4 text-destructive hover:text-destructive-foreground"
              onClick={() => setError(null)}
            >
              Dismiss
            </Button>
          </div>
        )}

        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-foreground mb-2">Prompt Studio</h1>
            <p className="text-muted-foreground">
              Author and refine the system prompts that shape agent behavior
            </p>
          </div>
          <Button onClick={handleOpenAdd}>
            <Plus className="w-5 h-5 mr-2" />
            New Prompt
          </Button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-4 mb-8">
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-foreground">
                {prompts.length}
              </div>
              <div className="text-sm text-muted-foreground">Total Prompts</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-foreground">
                {prompts.filter(p => p.is_default).length}
              </div>
              <div className="text-sm text-muted-foreground">Default Prompts</div>
            </CardContent>
          </Card>
        </div>

        {/* Prompts List grouped by task type */}
        {Object.keys(promptsByType).length === 0 ? (
          <div className="text-center py-12">
            <MessageSquare className="w-16 h-16 text-muted-foreground/50 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-muted-foreground mb-2">
              No prompts yet
            </h3>
            <p className="text-muted-foreground/70 mb-4">
              Create your first prompt to customize agent behavior
            </p>
            <Button onClick={handleOpenAdd}>
              Create Prompt
            </Button>
          </div>
        ) : (
          <div className="space-y-8">
            {Object.entries(promptsByType).map(([taskType, typePrompts]) => (
              <div key={taskType}>
                <div className="flex items-center gap-2 mb-4">
                  <TaskTypeIcon taskType={taskType} />
                  <h2 className="text-lg font-semibold text-foreground capitalize">{taskType}</h2>
                  <Badge variant="secondary" className="ml-2">{typePrompts.length}</Badge>
                </div>
                <div className="space-y-3">
                  {typePrompts.map(prompt => (
                    <Card key={prompt.id} className={cn(
                      prompt.is_default && 'border-primary/50'
                    )}>
                      <CardContent className="pt-4">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <h3 className="font-semibold text-foreground">{prompt.name}</h3>
                              {prompt.is_default && (
                                <Badge variant="default" className="text-xs">
                                  <Star className="w-3 h-3 mr-1" />
                                  Default
                                </Badge>
                              )}
                              {!prompt.project_id && (
                                <Badge variant="outline" className="text-xs">
                                  <Globe className="w-3 h-3 mr-1" />
                                  Global
                                </Badge>
                              )}
                              <Badge variant="secondary" className="text-xs">
                                v{prompt.version}
                              </Badge>
                            </div>
                            {prompt.description && (
                              <p className="text-sm text-muted-foreground mb-2">
                                {prompt.description}
                              </p>
                            )}
                            <p className="text-sm text-muted-foreground/70 line-clamp-2 font-mono">
                              {prompt.system_prompt.substring(0, 150)}...
                            </p>
                            <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground/70">
                              <span>RAG: {prompt.use_rag ? 'Enabled' : 'Disabled'}</span>
                              <span>Updated: {new Date(prompt.updated_at).toLocaleDateString()}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 ml-4">
                            {!prompt.is_default && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleSetDefault(prompt)}
                                title="Set as default"
                              >
                                <Star className="w-4 h-4" />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDuplicate(prompt)}
                              title="Duplicate"
                            >
                              <Copy className="w-4 h-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleOpenEdit(prompt)}
                              title="Edit"
                            >
                              <Pencil className="w-4 h-4" />
                            </Button>
                            {prompt.id.startsWith('default-') ? (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span
                                    tabIndex={0}
                                    role="button"
                                    aria-disabled="true"
                                    aria-label="Delete (unavailable for built-in prompts)"
                                  >
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      disabled
                                      className="text-muted-foreground pointer-events-none"
                                      tabIndex={-1}
                                    >
                                      <Trash2 className="w-4 h-4" />
                                    </Button>
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>
                                  Built-in prompts can&apos;t be deleted. Duplicate it to customize.
                                </TooltipContent>
                              </Tooltip>
                            ) : (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setDeletePrompt(prompt)}
                                className="text-destructive hover:text-destructive"
                                title="Delete"
                              >
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Add/Edit Prompt Modal */}
        <Dialog open={showAddModal || !!editPrompt} onOpenChange={(open) => {
          if (!open) {
            setShowAddModal(false)
            setEditPrompt(null)
            resetForm()
          }
        }}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{editPrompt ? 'Edit Prompt' : 'Create New Prompt'}</DialogTitle>
              <DialogDescription>
                {editPrompt
                  ? 'Update the prompt configuration. Changes will increment the version number.'
                  : 'Create a new system prompt for agent tasks.'}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Name</Label>
                  <Input
                    id="name"
                    value={formData.name}
                    onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="e.g., Documentation Expert"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="task_type">Task Type</Label>
                  <Select
                    value={formData.task_type}
                    onValueChange={value => setFormData(prev => ({ ...prev, task_type: value }))}
                    disabled={!!editPrompt}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="knowledge">Knowledge</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description (optional)</Label>
                <Input
                  id="description"
                  value={formData.description}
                  onChange={e => setFormData(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Brief description of this prompt's purpose"
                />
              </div>

              <Tabs value={previewTab} onValueChange={v => setPreviewTab(v as 'system' | 'rag')}>
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="system">System Prompt</TabsTrigger>
                  <TabsTrigger value="rag">Context Template</TabsTrigger>
                </TabsList>

                <TabsContent value="system" className="space-y-2">
                  <Label htmlFor="system_prompt">System Prompt</Label>
                  <Textarea
                    id="system_prompt"
                    value={formData.system_prompt}
                    onChange={e => setFormData(prev => ({ ...prev, system_prompt: e.target.value }))}
                    placeholder="You are a knowledgeable assistant..."
                    rows={12}
                    className="font-mono text-sm"
                  />
                  <p className="text-xs text-muted-foreground">
                    The base system prompt sent to the LLM. Define the assistant's role, capabilities, and guidelines.
                  </p>
                </TabsContent>

                <TabsContent value="rag" className="space-y-2">
                  <Label htmlFor="rag_context_template">Context Template (optional)</Label>
                  <Textarea
                    id="rag_context_template"
                    value={formData.rag_context_template}
                    onChange={e => setFormData(prev => ({ ...prev, rag_context_template: e.target.value }))}
                    placeholder="## Relevant Documentation&#10;&#10;{context}&#10;&#10;Use this documentation to answer the question."
                    rows={8}
                    className="font-mono text-sm"
                  />
                  <p className="text-xs text-muted-foreground">
                    Template for injecting RAG context. Use <code className="bg-muted px-1 rounded">{'{context}'}</code> as placeholder for retrieved documents.
                    Leave empty to use the default template.
                  </p>
                </TabsContent>
              </Tabs>

              <div className="flex items-center justify-between pt-4 border-t">
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-2">
                    <Switch
                      id="use_rag"
                      checked={formData.use_rag}
                      onCheckedChange={checked => setFormData(prev => ({ ...prev, use_rag: checked }))}
                    />
                    <Label htmlFor="use_rag" className="text-sm">Enable RAG</Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch
                      id="is_default"
                      checked={formData.is_default}
                      onCheckedChange={checked => setFormData(prev => ({ ...prev, is_default: checked }))}
                    />
                    <Label htmlFor="is_default" className="text-sm">Set as Default</Label>
                  </div>
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button variant="ghost" onClick={() => {
                setShowAddModal(false)
                setEditPrompt(null)
                resetForm()
              }}>
                Cancel
              </Button>
              <Button
                onClick={editPrompt ? handleUpdate : handleCreate}
                disabled={!formData.name.trim() || !formData.system_prompt.trim() || saving}
              >
                {saving && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
                {editPrompt ? 'Save Changes' : 'Create Prompt'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Delete Confirmation Modal */}
        <Dialog open={!!deletePrompt} onOpenChange={(open) => !open && !deleting && setDeletePrompt(null)}>
          <DialogContent
            className="max-w-md"
            onInteractOutside={(e) => deleting && e.preventDefault()}
            onEscapeKeyDown={(e) => deleting && e.preventDefault()}
          >
            <DialogHeader>
              <DialogTitle>Delete Prompt</DialogTitle>
              <DialogDescription>
                Are you sure you want to delete "{deletePrompt?.name}"? This action cannot be undone.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setDeletePrompt(null)} disabled={deleting}>
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
      </div>
    </div>
  )
}
