/**
 * Taxonomy API
 */

import { apiFetch } from './base';
import type {
  Taxonomy,
  TaxonomyCreate,
  TaxonomyUpdate,
  TaxonomyTerm,
  TaxonomyTermCreate,
  TaxonomyTermUpdate,
  TaxonomySuggestion,
  TaxonomyCoverage,
  StaleDocSummary,
} from './types/taxonomy';

export const taxonomyApi = {
  // Taxonomy CRUD
  list: (projectId?: string) => {
    const params = projectId ? `?project_id=${projectId}` : '';
    return apiFetch<Taxonomy[]>(`/api/taxonomies/${params}`);
  },

  get: (id: string) => apiFetch<Taxonomy>(`/api/taxonomies/${id}`),

  create: (data: TaxonomyCreate) =>
    apiFetch<Taxonomy>('/api/taxonomies/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: TaxonomyUpdate) =>
    apiFetch<Taxonomy>(`/api/taxonomies/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    apiFetch<null>(`/api/taxonomies/${id}`, { method: 'DELETE' }),

  // Term management
  listTerms: (taxonomyId: string, facet?: string) => {
    const params = facet ? `?facet=${facet}` : '';
    return apiFetch<TaxonomyTerm[]>(`/api/taxonomies/${taxonomyId}/terms${params}`);
  },

  addTerm: (taxonomyId: string, data: TaxonomyTermCreate) =>
    apiFetch<TaxonomyTerm>(`/api/taxonomies/${taxonomyId}/terms`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateTerm: (taxonomyId: string, termId: string, data: TaxonomyTermUpdate) =>
    apiFetch<TaxonomyTerm>(`/api/taxonomies/${taxonomyId}/terms/${termId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteTerm: (taxonomyId: string, termId: string) =>
    apiFetch<null>(`/api/taxonomies/${taxonomyId}/terms/${termId}`, { method: 'DELETE' }),

  // Coverage analytics
  getCoverage: (taxonomyId: string, sourceId?: string) => {
    const params = sourceId ? `?source_id=${sourceId}` : '';
    return apiFetch<TaxonomyCoverage>(`/api/taxonomies/${taxonomyId}/coverage${params}`);
  },

  // Stale classification
  listStale: (taxonomyId: string, sourceId?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (sourceId) params.set('source_id', sourceId);
    if (limit) params.set('limit', String(limit));
    const qs = params.toString() ? `?${params.toString()}` : '';
    return apiFetch<StaleDocSummary[]>(`/api/taxonomies/${taxonomyId}/stale${qs}`);
  },

  countStale: (taxonomyId: string, sourceId?: string) => {
    const params = sourceId ? `?source_id=${sourceId}` : '';
    return apiFetch<{ count: number }>(`/api/taxonomies/${taxonomyId}/stale/count${params}`);
  },

  // Suggestions
  listSuggestions: (taxonomyId: string, status?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (limit) params.set('limit', String(limit));
    const qs = params.toString() ? `?${params.toString()}` : '';
    return apiFetch<TaxonomySuggestion[]>(`/api/taxonomies/${taxonomyId}/suggestions${qs}`);
  },

  approveSuggestion: (taxonomyId: string, suggestionId: string) =>
    apiFetch<TaxonomyTerm>(`/api/taxonomies/${taxonomyId}/suggestions/${suggestionId}/approve`, {
      method: 'POST',
    }),

  rejectSuggestion: (taxonomyId: string, suggestionId: string) =>
    apiFetch<TaxonomySuggestion>(`/api/taxonomies/${taxonomyId}/suggestions/${suggestionId}/reject`, {
      method: 'POST',
    }),

  mergeSuggestion: (taxonomyId: string, suggestionId: string, mergeIntoValue: string) =>
    apiFetch<TaxonomySuggestion>(`/api/taxonomies/${taxonomyId}/suggestions/${suggestionId}/merge`, {
      method: 'POST',
      body: JSON.stringify({ merge_into_value: mergeIntoValue }),
    }),

  // Bulk import
  importFromJson: (taxonomyId: string, data: Record<string, unknown>) =>
    apiFetch<Taxonomy>(`/api/taxonomies/${taxonomyId}/import`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
