import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { Agent, Provider } from '../../../services/api'
import { agentsApi } from '../../../services/api/agents'
import { getEnabledModelsForProvider } from '../../../pages/ProvidersPage'
import { AgentFormData, DEFAULT_SYSTEM_PROMPT } from '../types'

/**
 * Load state of the agent's bound libraries (edit flow).
 * 'error' means the baseline is unknown — library sync MUST be skipped on save,
 * otherwise the delta would be computed against an empty form value and
 * unbind every library the agent has.
 */
export type LibraryLoadStatus = 'loading' | 'loaded' | 'error'

interface UseAgentFormDataProps {
  open: boolean
  editAgent: Agent | null
  providers: Provider[]
}

export function useAgentFormData({ open, editAgent, providers }: UseAgentFormDataProps) {
  const [activeTab, setActiveTab] = useState('basic')
  // 'loaded' by default: a new agent has a known-empty bindings baseline
  const [libraryLoadStatus, setLibraryLoadStatus] = useState<LibraryLoadStatus>('loaded')
  const [formData, setFormData] = useState<AgentFormData>({
    name: '',
    description: '',
    system_prompt: DEFAULT_SYSTEM_PROMPT,
    model_provider: providers[0]?.name || 'ollama',
    model_name: providers[0]?.available_models[0] || '',
    temperature: 0.7,
    use_rag: true,
    rag_top_k: 5,
    source_ids: [],
    library_ids: [],
    skills: [],
    is_public: false,
  })

  /**
   * Guards form initialization: only re-init when the dialog opens or the edit
   * target changes. Without this, a background providers refresh mid-edit
   * (new array reference) would reset formData and discard unsaved edits.
   */
  const initKeyRef = useRef<string | null>(null)
  /** Cancels the in-flight library fetch — set on every load, called on close/unmount. */
  const cancelLibraryLoadRef = useRef<(() => void) | null>(null)

  const loadLibraries = useCallback((agentId: string) => {
    cancelLibraryLoadRef.current?.()
    let cancelled = false
    cancelLibraryLoadRef.current = () => {
      cancelled = true
    }
    setLibraryLoadStatus('loading')
    agentsApi
      .listLibraries(agentId)
      .then(libs => {
        if (cancelled) return
        setFormData(prev => ({
          ...prev,
          library_ids: libs.map(l => l.id),
        }))
        setLibraryLoadStatus('loaded')
      })
      .catch(() => {
        // Baseline unknown — surfaced in the Knowledge tab; sync is skipped on save
        if (!cancelled) setLibraryLoadStatus('error')
      })
  }, [])

  useEffect(() => {
    if (!open) {
      initKeyRef.current = null
      cancelLibraryLoadRef.current?.()
      return
    }

    const initKey = editAgent ? editAgent.id : '__new__'
    if (initKeyRef.current === initKey) return
    initKeyRef.current = initKey

    if (editAgent) {
      setFormData({
        name: editAgent.name,
        description: editAgent.description || '',
        system_prompt: editAgent.system_prompt,
        model_provider: editAgent.model_provider,
        model_name: editAgent.model_name,
        temperature: editAgent.temperature,
        use_rag: editAgent.use_rag,
        rag_top_k: editAgent.rag_top_k,
        source_ids: editAgent.source_ids || [],
        library_ids: [],
        skills: editAgent.skills || [],
        is_public: editAgent.is_public,
      })
      loadLibraries(editAgent.id)
    } else {
      const defaultProvider = providers[0]
      const defaultEnabledModels = defaultProvider
        ? getEnabledModelsForProvider(defaultProvider)
        : []
      setFormData({
        name: '',
        description: '',
        system_prompt: DEFAULT_SYSTEM_PROMPT,
        model_provider: defaultProvider?.name || 'ollama',
        model_name: defaultEnabledModels[0] || '',
        temperature: 0.7,
        use_rag: true,
        rag_top_k: 5,
        source_ids: [],
        library_ids: [],
        skills: [],
        is_public: false,
      })
      setLibraryLoadStatus('loaded')
    }
    setActiveTab('basic')
  }, [open, editAgent, providers, loadLibraries])

  // Cancel any in-flight library fetch on unmount
  useEffect(() => {
    return () => {
      cancelLibraryLoadRef.current?.()
    }
  }, [])

  const retryLibraryLoad = useCallback(() => {
    if (editAgent) loadLibraries(editAgent.id)
  }, [editAgent, loadLibraries])

  const toggleSource = (sourceId: string) => {
    setFormData(prev => ({
      ...prev,
      source_ids: prev.source_ids.includes(sourceId)
        ? prev.source_ids.filter(id => id !== sourceId)
        : [...prev.source_ids, sourceId],
    }))
  }

  const toggleLibrary = (libraryId: string) => {
    setFormData(prev => ({
      ...prev,
      library_ids: prev.library_ids.includes(libraryId)
        ? prev.library_ids.filter(id => id !== libraryId)
        : [...prev.library_ids, libraryId],
    }))
  }

  const toggleSkill = (skill: { skill_id: string }) => {
    setFormData(prev => {
      const existingIndex = prev.skills.findIndex(s => s.name === skill.skill_id)
      if (existingIndex >= 0) {
        return {
          ...prev,
          skills: prev.skills.filter((_, i) => i !== existingIndex)
        }
      } else {
        return {
          ...prev,
          skills: [
            ...prev.skills,
            {
              type: 'builtin',
              name: skill.skill_id,
              config: {},
              enabled: true,
            }
          ]
        }
      }
    })
  }

  const isSkillSelected = (skillId: string) =>
    formData.skills.some(s => s.name === skillId)

  const selectedProvider = providers.find(p => p.name === formData.model_provider)

  const enabledModels = useMemo(() => {
    if (!selectedProvider) return []
    return getEnabledModelsForProvider(selectedProvider)
  }, [selectedProvider])

  return {
    activeTab,
    setActiveTab,
    formData,
    setFormData,
    toggleSource,
    toggleLibrary,
    toggleSkill,
    isSkillSelected,
    selectedProvider,
    enabledModels,
    libraryLoadStatus,
    retryLibraryLoad,
  }
}
