/**
 * Prompts API
 */

import { apiFetch } from './base';
import type {
  Prompt,
  PromptCreate,
  PromptUpdate,
  PromptDuplicate,
  GeneratePromptRequest,
  GeneratePromptResponse,
} from './types/prompts';

export const promptsApi = {
  list: (projectId?: string, taskType?: string, includeGlobal: boolean = true) => {
    const params = new URLSearchParams();
    if (projectId) params.append('project_id', projectId);
    if (taskType) params.append('task_type', taskType);
    params.append('include_global', String(includeGlobal));
    return apiFetch<Prompt[]>(`/api/prompts/prompts?${params.toString()}`);
  },

  get: (id: string) => apiFetch<Prompt>(`/api/prompts/prompts/${id}`),

  getDefault: (taskType: string, projectId?: string) => {
    const params = projectId ? `?project_id=${projectId}` : '';
    return apiFetch<Prompt>(`/api/prompts/prompts/default/${taskType}${params}`);
  },

  getTaskTypes: (projectId?: string) => {
    const params = projectId ? `?project_id=${projectId}` : '';
    return apiFetch<{ task_types: string[] }>(`/api/prompts/prompts/task-types${params}`);
  },

  create: (data: PromptCreate) =>
    apiFetch<Prompt>('/api/prompts/prompts', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: PromptUpdate) =>
    apiFetch<Prompt>(`/api/prompts/prompts/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    apiFetch<{ status: string; id: string }>(`/api/prompts/prompts/${id}`, {
      method: 'DELETE',
    }),

  duplicate: (id: string, data: PromptDuplicate) =>
    apiFetch<Prompt>(`/api/prompts/prompts/${id}/duplicate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

export const promptGeneratorApi = {
  generate: async (request: GeneratePromptRequest): Promise<GeneratePromptResponse> => {
    // Prompt generation requires a backend endpoint - placeholder for future implementation
    return {
      system_prompt: `You are a helpful AI assistant focused on: ${request.purpose}`,
    };
  },
};
