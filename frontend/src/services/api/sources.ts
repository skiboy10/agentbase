/**
 * Sources API
 */

import { apiFetch, API_BASE_URL, getStoredApiKey } from './base';
import type {
  Source,
  SourceCreate,
  SourceUpdate,
  RefreshSourceRequest,
  RefreshResponse,
  IndexingStatus,
  IndexingLogsResponse,
  RetryResponse,
  AdoptCollectionRequest,
  CollectionsResponse,
  ScanUrlResponse,
  WatcherEvent,
  WatcherStatus,
} from './types/sources';

async function uploadFormData<T>(url: string, formData: FormData): Promise<T> {
  const headers: Record<string, string> = {};
  const apiKey = getStoredApiKey();
  if (apiKey) {
    headers['Authorization'] = `Bearer ${apiKey}`;
  }

  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent('auth:unauthorized'));
      throw new Error('Authentication required');
    }
    const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export const sourcesApi = {
  // Auto-discover sitemap and scan (recommended for most sites)
  scanWithAutoDiscover: (url: string, pathFilter?: string) =>
    apiFetch<ScanUrlResponse>('/api/sources/scan-url', {
      method: 'POST',
      body: JSON.stringify({
        url,
        auto_discover_sitemap: true,
        path_filter: pathFilter || null,
      }),
    }),

  // Manual crawl mode (for sites without sitemaps)
  scanUrl: (url: string, maxDepth: number = 2, pathScope?: string) =>
    apiFetch<ScanUrlResponse>('/api/sources/scan-url', {
      method: 'POST',
      body: JSON.stringify({
        url,
        max_depth: maxDepth,
        path_scope: pathScope || null,
      }),
    }),

  // Explicit sitemap mode (if you know the sitemap URL)
  scanSitemap: (sitemapUrl: string, pathFilter?: string) =>
    apiFetch<ScanUrlResponse>('/api/sources/scan-url', {
      method: 'POST',
      body: JSON.stringify({
        url: '',  // Not used for sitemap mode
        sitemap_url: sitemapUrl,
        path_filter: pathFilter || null,
      }),
    }),

  listSources: (projectId?: string) =>
    apiFetch<Source[]>(
      `/api/sources${projectId ? `?project_id=${projectId}` : ''}`
    ),

  listGlobalSources: () =>
    apiFetch<Source[]>('/api/sources/global'),

  getSource: (id: string) =>
    apiFetch<Source>(`/api/sources/${id}`),

  addSource: (data: SourceCreate) =>
    apiFetch<Source>('/api/sources', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteSource: (id: string) =>
    apiFetch<null>(`/api/sources/${id}`, {
      method: 'DELETE',
    }),

  updateSource: (id: string, data: SourceUpdate) =>
    apiFetch<Source>(`/api/sources/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  addUrls: (id: string, urls: string[]) =>
    apiFetch<Source>(`/api/sources/${id}/urls`, {
      method: 'POST',
      body: JSON.stringify({ urls }),
    }),

  removeUrls: (id: string, urls: string[]) =>
    apiFetch<Source>(`/api/sources/${id}/urls`, {
      method: 'DELETE',
      body: JSON.stringify({ urls }),
    }),

  refreshSource: (id: string, request: RefreshSourceRequest) =>
    apiFetch<RefreshResponse>(`/api/sources/${id}/refresh`, {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  indexSource: (id: string) =>
    apiFetch<{ status: string; source_id: string; message: string }>(
      `/api/sources/${id}/index`,
      { method: 'POST' }
    ),

  reEnrich: (id: string) =>
    apiFetch<{ status: string; source_id: string; job_id: string }>(
      `/api/sources/${id}/re-enrich`,
      { method: 'POST' }
    ),

  getSourceStatus: (id: string) =>
    apiFetch<IndexingStatus>(`/api/sources/${id}/status`),

  getSourceLogs: (id: string, statusFilter?: string, limit: number = 500) =>
    apiFetch<IndexingLogsResponse>(
      `/api/sources/${id}/logs${statusFilter ? `?status_filter=${statusFilter}&limit=${limit}` : `?limit=${limit}`}`
    ),

  retryFailed: (id: string) =>
    apiFetch<RetryResponse>(
      `/api/sources/${id}/retry-failed`,
      { method: 'POST' }
    ),

  clearLogs: (id: string) =>
    apiFetch<null>(`/api/sources/${id}/logs`, {
      method: 'DELETE',
    }),

  search: (
    query: string,
    projectId?: string,
    topK: number = 5,
    filters?: Record<string, string | string[]>
  ) =>
    apiFetch<{ content: string; source: string; score: number; metadata: Record<string, unknown> }[]>(
      '/api/sources/search',
      {
        method: 'POST',
        body: JSON.stringify({
          query,
          project_id: projectId,
          top_k: topK,
          filters: filters && Object.keys(filters).length > 0 ? filters : undefined,
        }),
      }
    ),

  listCollections: (includeDetails: boolean = false) =>
    apiFetch<CollectionsResponse>(
      `/api/sources/collections${includeDetails ? '?include_details=true' : ''}`
    ),

  adoptCollection: (data: AdoptCollectionRequest) =>
    apiFetch<Source>('/api/sources/adopt', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  health: () =>
    apiFetch<{ qdrant: { healthy: boolean; message: string; url: string } }>('/api/sources/health'),

  // Upload single file (backward compatible)
  uploadFile: async (
    file: File,
    name: string,
    options?: {
      projectId?: string;
      embeddingProvider?: string;
      embeddingModel?: string;
    }
  ): Promise<Source> => {
    const formData = new FormData();
    formData.append('files', file);
    formData.append('name', name);
    if (options?.projectId) {
      formData.append('project_id', options.projectId);
    }
    if (options?.embeddingProvider) {
      formData.append('embedding_provider', options.embeddingProvider);
    }
    if (options?.embeddingModel) {
      formData.append('embedding_model', options.embeddingModel);
    }

    return uploadFormData<Source>(`${API_BASE_URL}/api/sources/upload`, formData);
  },

  // Upload multiple files
  uploadFiles: async (
    files: File[],
    name: string,
    options?: {
      projectId?: string;
      embeddingProvider?: string;
      embeddingModel?: string;
      enrichmentEnabled?: boolean;
      enrichmentTaxonomyId?: string;
      enrichmentModel?: string;
    }
  ): Promise<Source> => {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    formData.append('name', name);
    if (options?.projectId) {
      formData.append('project_id', options.projectId);
    }
    if (options?.embeddingProvider) {
      formData.append('embedding_provider', options.embeddingProvider);
    }
    if (options?.embeddingModel) {
      formData.append('embedding_model', options.embeddingModel);
    }
    if (options?.enrichmentEnabled) {
      formData.append('enrichment_enabled', 'true');
      if (options.enrichmentTaxonomyId) {
        formData.append('enrichment_taxonomy_id', options.enrichmentTaxonomyId);
      }
      if (options.enrichmentModel) {
        formData.append('enrichment_model', options.enrichmentModel);
      }
    }

    return uploadFormData<Source>(`${API_BASE_URL}/api/sources/upload`, formData);
  },

  // Add files to existing source
  addFiles: async (id: string, files: File[]): Promise<Source> => {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    return uploadFormData<Source>(`${API_BASE_URL}/api/sources/${id}/files`, formData);
  },

  // Remove files from source
  removeFiles: (id: string, filePaths: string[]) =>
    apiFetch<Source>(`/api/sources/${id}/files`, {
      method: 'DELETE',
      body: JSON.stringify({ file_paths: filePaths }),
    }),

  // Watcher controls
  startWatcher: (id: string) =>
    apiFetch<{ status: string; message: string }>(`/api/sources/watchers/${id}/start`, {
      method: 'POST',
    }),

  stopWatcher: (id: string) =>
    apiFetch<{ status: string; message: string }>(`/api/sources/watchers/${id}/stop`, {
      method: 'POST',
    }),

  syncWatcher: (id: string) =>
    apiFetch<{ status: string; message: string; new?: number; modified?: number; deleted?: number; unchanged?: number }>(`/api/sources/watchers/${id}/sync`, {
      method: 'POST',
    }),

  getWatcherStatus: (id: string) =>
    apiFetch<WatcherStatus>(`/api/sources/watchers/status/${id}`),

  listWatcherEvents: (id: string, params?: { limit?: number; before?: string }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.before) qs.set('before', params.before);
    const query = qs.toString();
    return apiFetch<WatcherEvent[]>(`/api/sources/${id}/watcher-events${query ? `?${query}` : ''}`);
  },
};
