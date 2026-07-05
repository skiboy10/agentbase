/**
 * Agents API
 */

import { apiFetch } from './base';
import type {
  Agent,
  AgentCreate,
  AgentUpdate,
  AgentDuplicate,
  AgentQueryRequest,
  AgentQueryResponse,
  AgentLibrarySummary,
  AgentLibraryBindResponse,
  AgentLibraryUnbindResponse,
} from './types/agents';

export const agentsApi = {
  list: () => apiFetch<Agent[]>('/api/agents'),

  get: (id: string) => apiFetch<Agent>(`/api/agents/${id}`),

  create: (data: AgentCreate) =>
    apiFetch<Agent>('/api/agents', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: AgentUpdate) =>
    apiFetch<Agent>(`/api/agents/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    apiFetch<{ status: string; id: string }>(`/api/agents/${id}`, {
      method: 'DELETE',
    }),

  duplicate: (id: string, data: AgentDuplicate) =>
    apiFetch<Agent>(`/api/agents/${id}/duplicate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  generateApiKey: (id: string) =>
    apiFetch<{ api_key: string; message: string; is_public: boolean; has_api_key: boolean }>(`/api/agents/${id}/api-key`, {
      method: 'POST',
    }),

  // Agent query
  query: (id: string, data: AgentQueryRequest) =>
    apiFetch<AgentQueryResponse>(`/api/agents/${id}/query`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Library bindings
  listLibraries: (agentId: string) =>
    apiFetch<AgentLibrarySummary[]>(`/api/agents/${agentId}/libraries`),

  bindLibrary: (agentId: string, libraryId: string) =>
    apiFetch<AgentLibraryBindResponse>(`/api/agents/${agentId}/libraries/${libraryId}`, {
      method: 'POST',
    }),

  unbindLibrary: (agentId: string, libraryId: string) =>
    apiFetch<AgentLibraryUnbindResponse>(`/api/agents/${agentId}/libraries/${libraryId}`, {
      method: 'DELETE',
    }),
};
