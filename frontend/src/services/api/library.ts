/**
 * Libraries API
 */

import { apiFetch } from './base';
import type {
  Library,
  LibraryCreate,
  LibraryUpdate,
  LibraryDocument,
  LibraryDocumentPage,
  LibraryDocumentListParams,
  LibrarySource,
  LibrarySearchResult,
  LibrarySearchParams,
  DeepSearchParams,
  DeepSearchResponse,
  LibraryChatRequest,
  LibraryChatResponse,
} from './types/library';

export const libraryApi = {
  // List all libraries
  list: () =>
    apiFetch<Library[]>('/api/libraries'),

  // Get a single library
  get: (id: string) =>
    apiFetch<Library>(`/api/libraries/${id}`),

  // Create a new library
  create: (data: LibraryCreate) =>
    apiFetch<Library>('/api/libraries', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Update a library
  update: (id: string, data: LibraryUpdate) =>
    apiFetch<Library>(`/api/libraries/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Delete a library
  delete: (id: string) =>
    apiFetch<void>(`/api/libraries/${id}`, {
      method: 'DELETE',
    }),

  // List sources attached to a library
  listSources: (libraryId: string) =>
    apiFetch<LibrarySource[]>(`/api/libraries/${libraryId}/sources`),

  // Add a source to a library. Returns binding status; when the source is
  // already indexed, a re-index job is queued so chunks fan into the new
  // library's collection.
  addSource: (libraryId: string, sourceIdOrBody: string | { source_id: string }) => {
    const body =
      typeof sourceIdOrBody === 'string'
        ? { source_id: sourceIdOrBody }
        : sourceIdOrBody;
    return apiFetch<{ bound: boolean; already_bound: boolean; reindex_queued: boolean }>(
      `/api/libraries/${libraryId}/sources`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    );
  },

  // Remove a source from a library
  removeSource: (libraryId: string, sourceId: string) =>
    apiFetch<void>(`/api/libraries/${libraryId}/sources/${sourceId}`, {
      method: 'DELETE',
    }),

  // Recalculate stats for a library
  recalculateStats: (libraryId: string) =>
    apiFetch<Library>(`/api/libraries/${libraryId}/recalculate-stats`, {
      method: 'POST',
    }),

  // Alias used by SettingsTab
  recalcStats: (libraryId: string) =>
    apiFetch<Library>(`/api/libraries/${libraryId}/recalculate-stats`, {
      method: 'POST',
    }),

  // Delete alias used by SettingsTab
  deleteLibrary: (libraryId: string) =>
    apiFetch<void>(`/api/libraries/${libraryId}`, {
      method: 'DELETE',
    }),

  // List documents in a library with optional filters
  listDocuments: (libraryId: string, paramsOrLimit?: LibraryDocumentListParams | number, offsetLegacy = 0) => {
    let qs: string;
    if (typeof paramsOrLimit === 'object' && paramsOrLimit !== null) {
      const p = paramsOrLimit;
      const parts: string[] = [];
      if (p.limit !== undefined) parts.push(`limit=${p.limit}`);
      if (p.offset !== undefined) parts.push(`offset=${p.offset}`);
      if (p.search) parts.push(`search=${encodeURIComponent(p.search)}`);
      if (p.file_type) parts.push(`file_type=${encodeURIComponent(p.file_type)}`);
      if (p.document_type) parts.push(`document_type=${encodeURIComponent(p.document_type)}`);
      if (p.source_id) parts.push(`source_id=${encodeURIComponent(p.source_id)}`);
      qs = parts.join('&');
    } else {
      const limit = typeof paramsOrLimit === 'number' ? paramsOrLimit : 50;
      qs = `limit=${limit}&offset=${offsetLegacy}`;
    }
    return apiFetch<LibraryDocumentPage>(`/api/libraries/${libraryId}/documents?${qs}`);
  },

  // Get a single document
  getDocument: (libraryId: string, docId: string) =>
    apiFetch<LibraryDocument>(`/api/libraries/${libraryId}/documents/${docId}`),

  // Get the full text of a document
  getDocumentText: (libraryId: string, docId: string) =>
    apiFetch<{ full_text: string }>(
      `/api/libraries/${libraryId}/documents/${docId}/text`
    ),

  // Delete a document from a library
  deleteDocument: (libraryId: string, docId: string) =>
    apiFetch<void>(`/api/libraries/${libraryId}/documents/${docId}`, {
      method: 'DELETE',
    }),

  // Search within a library (uses sources search endpoint with knowledge_base_id)
  search: (_libraryId: string, params: LibrarySearchParams) =>
    apiFetch<LibrarySearchResult[]>('/api/sources/search', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  // Deep search with LLM query decomposition
  deepSearch: (params: DeepSearchParams) =>
    apiFetch<DeepSearchResponse>('/api/sources/deep-search', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  // Chat with a library's knowledge base
  chat: (libraryId: string, data: LibraryChatRequest) =>
    apiFetch<LibraryChatResponse>(`/api/libraries/${libraryId}/chat`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
