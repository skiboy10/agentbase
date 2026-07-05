/**
 * Library types
 */

export interface Library {
  id: string;
  name: string;
  description: string | null;
  project_id: string | null;
  collection_name: string;
  embedding_provider: string | null;
  embedding_model: string | null;
  embedding_dimensions: number | null;
  taxonomy_id: string | null;
  enrichment_model: string | null;
  source_count: number;
  document_count: number;
  chunk_count: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface LibraryCreate {
  name: string;
  description?: string;
  project_id?: string;
  embedding_provider?: string;
  embedding_model?: string;
  taxonomy_id?: string;
  enrichment_model?: string;
}

export interface LibraryUpdate {
  name?: string;
  description?: string | null;
  taxonomy_id?: string;
  enrichment_model?: string;
}

export interface LibraryDocument {
  id: string;
  library_id: string;
  source_id: string;
  document_id: string;
  title: string | null;
  file_path: string | null;
  url: string | null;
  file_type: string | null;
  full_text: string | null;
  text_length: number;
  content_hash: string | null;
  classification: Record<string, unknown> | null;
  document_type: string | null;
  chunk_count: number;
  status: string;
  indexed_at: string | null;
  created_at: string;
  // Optional enrichment fields returned by some API versions
  tags?: Array<{ value: string }>;
  source_name?: string | null;
}

export interface LibraryDocumentPage {
  documents: LibraryDocument[];
  total: number;
}

export interface LibrarySource {
  id: string;
  name: string;
  source_type: string;
  status: string;
  document_count: number;
  chunk_count: number;
  last_indexed: string | null;
  watch_enabled: boolean;
}

export interface LibrarySearchResult {
  content: string;
  score: number;
  source: string;
  metadata: Record<string, unknown>;
  rerank_score?: number | null;
  title?: string;
  source_name?: string;
  document_path?: string;
}

export interface LibrarySearchParams {
  query: string;
  source_ids?: string[];
  knowledge_base_id?: string;
  top_k?: number;
  hybrid?: boolean;
  vector_weight?: number;
  rerank?: boolean;
}

export interface DeepSearchParams {
  query: string;
  knowledge_base_id?: string;
  source_ids?: string[];
  top_k?: number;
  rerank?: boolean;
}

export interface DeepSearchResponse {
  results: LibrarySearchResult[];
  sub_queries: { query: string; strategy: string }[];
  stats: Record<string, unknown>;
}

export interface LibraryDocumentListParams {
  limit?: number;
  offset?: number;
  search?: string;
  file_type?: string;
  document_type?: string;
  source_id?: string;
}

export interface LibraryChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface LibraryChatConfig {
  provider: string;
  model: string;
  top_k: number;
  rerank: boolean;
  system_prompt?: string;
  search_mode: 'hybrid' | 'vector' | 'deep';
  vector_weight: number;
}

export interface LibraryChatSourceItem {
  source_id: string;
  source_name: string;
  url: string;
  title: string;
  score: number;
  preview: string;
}

export interface LibraryChatRequest {
  message: string;
  history: LibraryChatMessage[];
  config: LibraryChatConfig;
}

export interface LibraryChatResponse {
  answer: string;
  sources: LibraryChatSourceItem[];
  model: string;
}
