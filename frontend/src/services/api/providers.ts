/**
 * Providers API
 */

import { apiFetch } from './base';
import type { Provider, ModelAssignment, EmbeddingModel } from './types/common';

export const providersApi = {
  list: () => apiFetch<Provider[]>('/api/providers'),

  get: (name: string) => apiFetch<Provider>(`/api/providers/${name}`),

  update: (name: string, data: { api_key?: string; base_url?: string; is_active?: boolean; disabled_models?: string[] }) =>
    apiFetch<{ status: string; provider: string }>(`/api/providers/${name}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (name: string) =>
    apiFetch<{ status: string; provider: string }>(`/api/providers/${name}`, {
      method: 'DELETE',
    }),

  test: (name: string) =>
    apiFetch<{ status: string; provider: string; healthy: boolean; message: string; model_count?: number }>(
      `/api/providers/${name}/test`,
      { method: 'POST' }
    ),

  listModels: () =>
    apiFetch<{ id: string; name: string; provider: string; context_window: number; capabilities: string[] }[]>(
      '/api/providers/models/available'
    ),

  listEmbeddingModels: () =>
    apiFetch<EmbeddingModel[]>('/api/providers/embedding-models/available'),

  getAssignments: (projectId?: string) =>
    apiFetch<ModelAssignment[]>(
      `/api/providers/models/assignments${projectId ? `?project_id=${projectId}` : ''}`
    ),

  assignModel: (data: { task_type: string; provider: string; model: string }, projectId?: string) =>
    apiFetch<{ status: string; task_type: string; provider: string; model: string }>(
      `/api/providers/models/assign${projectId ? `?project_id=${projectId}` : ''}`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    ),
};
