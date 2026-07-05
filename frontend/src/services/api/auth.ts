import { apiFetch } from './base';
import type { APIKey, APIKeyCreate, APIKeyCreateResponse } from './types/auth';

export const authApi = {
  listKeys: () =>
    apiFetch<APIKey[]>('/api/auth/keys'),

  createKey: (data: APIKeyCreate) =>
    apiFetch<APIKeyCreateResponse>('/api/auth/keys', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  revokeKey: (id: string) =>
    apiFetch<{ status: string; id: string }>(`/api/auth/keys/${id}`, {
      method: 'DELETE',
    }),
};
