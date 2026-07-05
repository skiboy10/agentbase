/**
 * Source types
 */

/** Inline type — Projects deprecated from UI but still in API responses */
interface ProjectInfo {
  id: string;
  name: string;
}

export interface AgentInfo {
  id: string;
  name: string;
}

export interface FileInfo {
  path: string;
  original_name: string;
  size_bytes: number;
}

export interface Source {
  id: string;
  name: string;
  description: string | null;
  source_type: string;
  source_path: string;
  project_id: string | null;
  status: string;
  last_indexed: string | null;
  document_count: number;
  chunk_count: number;
  error_message: string | null;
  progress: number;
  progress_total: number;
  progress_message: string | null;
  progress_updated_at: string | null;
  created_at: string;
  selected_urls: string[] | null;
  selected_files: FileInfo[] | null;
  // Qdrant collection name
  collection_name: string | null;
  // Embedding configuration used for this source
  embedding_provider: string | null;
  embedding_model: string | null;
  embedding_dimensions: number | null;
  // Project assignment info
  assigned_projects: ProjectInfo[];
  owner_project: ProjectInfo | null;
  // Agents that use this source
  bound_agents: AgentInfo[];
  // Enrichment pipeline config
  enrichment_enabled: boolean;
  enrichment_taxonomy_id: string | null;
  enrichment_model: string | null;
  // YouTube source config (source_type="youtube")
  youtube_backfill_mode: string | null;
  youtube_recent_count: number | null;
  // Directory watcher config
  watch_enabled: boolean;
  watch_extensions: string[] | null;
  watch_mode: string | null;
  watch_poll_interval_seconds: number | null;
  watch_debounce_seconds: number | null;
  watch_max_file_size_mb: number | null;
  // Watcher runtime state (from backend hardening — Phase 1)
  watch_status: string;
  watch_last_heartbeat_at: string | null;
  watch_last_error: string | null;
  // Freshness / auto-refresh schedule
  freshness_policy: string | null; // "none" | "automatic" | "manual"
  stale_after_days: number | null;
  refresh_interval_days: number | null;
  next_refresh_at: string | null;
  // Sub-source model: when parent_source_id is set, this Source is a
  // filtered view over the parent root (no own collection / watcher).
  parent_source_id: string | null;
  path_prefix: string | null;
  path_excludes: string[] | null;
  sub_source_count: number;
}

export interface SourceCreate {
  name: string;
  source_type: string;
  source_path: string;
  project_id?: string;
  selected_urls?: string[];
  // Optional embedding override
  embedding_provider?: string;
  embedding_model?: string;
  // Enrichment pipeline config
  enrichment_enabled?: boolean;
  enrichment_taxonomy_id?: string;
  enrichment_model?: string;
  // YouTube source config (source_type="youtube")
  youtube_backfill_mode?: string;
  youtube_recent_count?: number;
  // Directory watcher config
  watch_enabled?: boolean;
  watch_extensions?: string[];
  watch_mode?: string;
  watch_poll_interval_seconds?: number;
  watch_debounce_seconds?: number;
  watch_max_file_size_mb?: number;
  // Sub-source model
  parent_source_id?: string;
  path_prefix?: string;
  path_excludes?: string[];
}

export interface SourceUpdate {
  name?: string;
  description?: string;
  // Directory watcher config (all optional for partial updates)
  watch_enabled?: boolean;
  watch_extensions?: string[];
  watch_mode?: string;
  watch_poll_interval_seconds?: number;
  watch_debounce_seconds?: number;
  watch_max_file_size_mb?: number;
  // Enrichment config (null clears the field)
  enrichment_enabled?: boolean;
  enrichment_taxonomy_id?: string | null;
  enrichment_model?: string | null;
  // YouTube source config (depth editable post-creation)
  youtube_backfill_mode?: string;
  youtube_recent_count?: number;
  // Freshness / auto-refresh schedule
  freshness_policy?: string; // "none" | "automatic" | "manual"
  stale_after_days?: number;
  refresh_interval_days?: number;
  // Sub-source / path overlay
  path_prefix?: string;
  path_excludes?: string[];
}

export interface WatcherEvent {
  id: string;
  source_id: string;
  timestamp: string;
  event_type: string; // created|modified|deleted|started|stopped|recovery|error|degraded
  file_path: string | null;
  severity: string; // info|warn|error
  message: string | null;
}

export interface WatcherStatus {
  source_id: string;
  path: string;
  running: boolean;
  mode: string;
  last_event_time: string | null;
  event_count: number;
  started_at: string | null;
}

export interface SourceAssignment {
  id: string;
  source_id: string;
  source_name: string;
  source_type: string;
  status: string;
  document_count: number;
  chunk_count: number;
  is_global: boolean;
  assigned_at: string | null;
}

export interface RefreshSourceRequest {
  mode: 'full' | 'selective';
  urls?: string[];
}

export interface RefreshResponse {
  status: string;
  source_id: string;
  message: string;
  mode: string;
  url_count?: number;
}

export interface IndexingStatus {
  source_id: string;
  status: string;
  progress: number;
  progress_total: number;
  progress_message: string | null;
  progress_updated_at: string | null;
  document_count: number;
  chunk_count: number;
  error_message: string | null;
}

export interface IndexingLog {
  id: string;
  source_id: string;
  url: string;
  status: string; // pending, scraping, scraped, embedding, done, failed, skipped
  error_message: string | null;
  scrape_duration_ms: number | null;
  embed_duration_ms: number | null;
  content_length: number | null;
  chunk_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface IndexingLogsResponse {
  logs: IndexingLog[];
  summary: {
    total: number;
    done: number;
    failed: number;
    skipped: number;
    pending: number;
    in_progress: number;
  };
}

export interface RetryResponse {
  status: string;
  source_id: string;
  message: string;
  retry_count?: number;
}

export interface AdoptCollectionRequest {
  name: string;
  collection_name: string;
  description?: string;
  project_id?: string;
  embedding_provider: string;
  embedding_model: string;
  embedding_dimensions: number;
  // Optional enrichment. Adoption doesn't index, so callers must POST
  // /api/sources/{id}/re-enrich after create when this is enabled.
  enrichment_enabled?: boolean;
  enrichment_taxonomy_id?: string | null;
  enrichment_model?: string | null;
}

export interface QdrantCollectionInfo {
  name: string;
  vectors_count: number;
  points_count: number;
  vector_size: number | null;
  distance: string | null;
  is_linked: boolean;
  linked_source_id: string | null;
  linked_source_name: string | null;
}

export interface CollectionsResponse {
  collections: QdrantCollectionInfo[];
}

export interface SiteTreeNode {
  url: string;
  title: string;
  path: string;
  children: SiteTreeNode[];
}

export interface ScanUrlResponse {
  tree: SiteTreeNode;
  sitemap_url: string | null;
}

export interface SearchResult {
  content: string;
  source: string;
  score: number;
  metadata: Record<string, unknown>;
}
