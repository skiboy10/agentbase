import { Agent, Source, Provider, SkillConfig } from '../../services/api'

export interface AgentFormData {
  name: string
  description: string
  system_prompt: string
  model_provider: string
  model_name: string
  temperature: number
  use_rag: boolean
  rag_top_k: number
  source_ids: string[]
  library_ids: string[]
  skills: SkillConfig[]
  is_public: boolean
}

export interface AgentSaveOptions {
  /**
   * True when the agent's current library bindings could not be loaded.
   * The save handler must skip library sync — computing a delta against an
   * unloaded (empty) baseline would unbind everything.
   */
  skipLibrarySync?: boolean
}

export interface AgentFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editAgent: Agent | null
  providers: Provider[]
  sources: Source[]
  saving: boolean
  onSave: (data: AgentFormData, options?: AgentSaveOptions) => Promise<void>
}

export const DEFAULT_SYSTEM_PROMPT = `You are a helpful AI assistant with access to curated documentation.
Answer questions accurately using the provided context when available.
If you're unsure or the documentation doesn't cover a topic, say so clearly.`
