/**
 * Prompt types
 */

export interface Prompt {
  id: string;
  project_id: string | null;
  name: string;
  description: string | null;
  task_type: string;
  system_prompt: string;
  rag_context_template: string | null;
  use_rag: boolean;
  is_default: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface PromptCreate {
  name: string;
  task_type: string;
  system_prompt: string;
  project_id?: string;
  description?: string;
  rag_context_template?: string;
  use_rag?: boolean;
  is_default?: boolean;
}

export interface PromptUpdate {
  name?: string;
  description?: string;
  system_prompt?: string;
  rag_context_template?: string;
  use_rag?: boolean;
  is_default?: boolean;
  increment_version?: boolean;
}

export interface PromptDuplicate {
  new_name: string;
  target_project_id?: string;
}

export interface GeneratePromptRequest {
  purpose: string;
  knowledge_sources?: string[];
  context_type: 'agent' | 'project';
}

export interface GeneratePromptResponse {
  system_prompt: string;
}
