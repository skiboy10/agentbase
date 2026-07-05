/**
 * Taxonomy API types.
 *
 * Types for taxonomy management, term CRUD, coverage analytics,
 * suggestions, and stale classification detection.
 */

export interface Taxonomy {
  id: string;
  name: string;
  description: string | null;
  project_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  term_count?: number;
}

export interface TaxonomyCreate {
  name: string;
  description?: string;
  project_id?: string;
}

export interface TaxonomyUpdate {
  name?: string;
  description?: string;
}

export interface TaxonomyTerm {
  id: string;
  taxonomy_id: string;
  facet: string;
  value: string;
  parent_value: string | null;
  keywords: string[];
  sort_order: number;
  created_at: string;
}

export interface TaxonomyTermCreate {
  facet: string;
  value: string;
  parent_value?: string;
  keywords?: string[];
  sort_order?: number;
}

export interface TaxonomyTermUpdate {
  value?: string;
  parent_value?: string;
  keywords?: string[];
  sort_order?: number;
}

export interface TaxonomySuggestion {
  id: string;
  taxonomy_id: string;
  facet: string;
  suggested_value: string;
  frequency: number;
  sample_document_ids: string[] | null;
  status: 'pending' | 'approved' | 'rejected' | 'merged';
  merged_into: string | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface TaxonomyCoverage {
  total_documents: number;
  classified_documents: number;
  unclassified_documents: number;
  coverage_percent: number;
  facet_coverage: Record<string, { covered: number; total: number; percent: number }>;
  term_usage: Record<string, Array<{ value: string; count: number }>>;
}

export interface StaleDocSummary {
  id: string;
  source_id: string;
  file_id: string;
  title: string | null;
  classification: Record<string, unknown> | null;
  classification_taxonomy_version: number | null;
  updated_at: string;
}

export interface MergeRequest {
  merge_into_value: string;
}
