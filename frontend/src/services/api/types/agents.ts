/**
 * Agent types
 */

export interface SkillConfig {
  type: string;
  name: string;
  config: Record<string, unknown>;
  enabled: boolean;
}

export interface AgentLibrarySummary {
  id: string;
  name: string;
  description: string | null;
  status: string;
  collection_name: string;
  source_count: number;
  document_count: number;
  chunk_count: number;
}

export interface AgentLibraryBindResponse {
  status: 'bound' | 'already_bound';
  agent_id: string;
  library: AgentLibrarySummary;
}

export interface AgentLibraryUnbindResponse {
  status: 'unbound';
  agent_id: string;
  library_id: string;
}

export interface Agent {
  id: string;
  agent_id: string | null;
  name: string;
  description: string | null;
  system_prompt: string;
  model_provider: string;
  model_name: string;
  temperature: number;
  use_rag: boolean;
  rag_top_k: number;
  skills: SkillConfig[];
  is_public: boolean;
  has_api_key: boolean;
  source_ids: string[];
  /** Libraries bound via AgentLibrary */
  library_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface AgentCreate {
  name: string;
  system_prompt: string;
  model_provider: string;
  model_name: string;
  description?: string;
  temperature?: number;
  use_rag?: boolean;
  rag_top_k?: number;
  skills?: SkillConfig[];
  is_public?: boolean;
  source_ids?: string[];
}

export interface AgentUpdate {
  name?: string;
  description?: string;
  system_prompt?: string;
  model_provider?: string;
  model_name?: string;
  temperature?: number;
  use_rag?: boolean;
  rag_top_k?: number;
  skills?: SkillConfig[];
  is_public?: boolean;
  source_ids?: string[];
}

export interface AgentDuplicate {
  new_name: string;
}

// Agent query types
export interface AgentQueryRequest {
  query: string;
  session_id?: string;
  filters?: Record<string, string[]>;
}

export interface AgentQuerySourceItem {
  source_id: string;
  source_name: string;
  url: string;
  title: string;
  score: number;
  preview: string;
}

export interface AgentQueryResponse {
  answer: string;
  sources: AgentQuerySourceItem[];
  query: string;
  model: string;
  agent_id: string;
}
