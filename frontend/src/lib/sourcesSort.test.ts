/**
 * Unit tests for sourcesSort comparator utilities.
 */
import { describe, it, expect } from 'vitest'
import {
  compareSourcesBy,
  sortSources,
  parseSortKey,
  DEFAULT_SORT,
  SORT_OPTIONS,
  type SourceSortKey,
} from './sourcesSort'
import type { Source } from '../services/api/types/sources'

/** Minimal Source factory — only fills fields relevant to sorting */
function makeSource(overrides: Partial<Source> & Pick<Source, 'id' | 'name'>): Source {
  return {
    description: null,
    source_type: 'web',
    source_path: '',
    project_id: null,
    status: 'indexed',
    last_indexed: null,
    document_count: 0,
    chunk_count: 0,
    error_message: null,
    progress: 0,
    progress_total: 0,
    progress_message: null,
    progress_updated_at: null,
    created_at: '2024-01-01T00:00:00Z',
    selected_urls: null,
    selected_files: null,
    collection_name: null,
    embedding_provider: null,
    embedding_model: null,
    embedding_dimensions: null,
    assigned_projects: [],
    owner_project: null,
    bound_agents: [],
    enrichment_enabled: false,
    enrichment_taxonomy_id: null,
    enrichment_model: null,
    youtube_backfill_mode: null,
    youtube_recent_count: null,
    watch_enabled: false,
    watch_extensions: null,
    watch_mode: null,
    watch_poll_interval_seconds: null,
    watch_debounce_seconds: null,
    watch_max_file_size_mb: null,
    watch_status: 'stopped',
    watch_last_heartbeat_at: null,
    watch_last_error: null,
    freshness_policy: null,
    stale_after_days: null,
    refresh_interval_days: null,
    next_refresh_at: null,
    parent_source_id: null,
    path_prefix: null,
    path_excludes: null,
    sub_source_count: 0,
    ...overrides,
  }
}

const alpha = makeSource({ id: '1', name: 'Alpha', chunk_count: 10, document_count: 5, status: 'indexed', created_at: '2024-01-01T00:00:00Z', last_indexed: '2024-06-01T00:00:00Z' })
const beta  = makeSource({ id: '2', name: 'Beta',  chunk_count: 30, document_count: 2, status: 'error',   created_at: '2024-03-01T00:00:00Z', last_indexed: '2024-07-01T00:00:00Z' })
const gamma = makeSource({ id: '3', name: 'Gamma', chunk_count: 20, document_count: 8, status: 'pending', created_at: '2024-02-01T00:00:00Z', last_indexed: null })

const sources = [alpha, beta, gamma]

describe('DEFAULT_SORT', () => {
  it('is name_asc', () => {
    expect(DEFAULT_SORT).toBe('name_asc')
  })
})

describe('SORT_OPTIONS', () => {
  it('contains all expected keys', () => {
    const keys = SORT_OPTIONS.map((o) => o.value)
    expect(keys).toContain('name_asc')
    expect(keys).toContain('name_desc')
    expect(keys).toContain('last_indexed_desc')
    expect(keys).toContain('chunk_count_desc')
    expect(keys).toContain('document_count_desc')
    expect(keys).toContain('status_asc')
    expect(keys).toContain('created_desc')
  })
})

describe('compareSourcesBy', () => {
  it('name_asc: alpha < beta < gamma', () => {
    expect(compareSourcesBy(alpha, beta, 'name_asc')).toBeLessThan(0)
    expect(compareSourcesBy(beta, gamma, 'name_asc')).toBeLessThan(0)
    expect(compareSourcesBy(gamma, alpha, 'name_asc')).toBeGreaterThan(0)
    expect(compareSourcesBy(alpha, alpha, 'name_asc')).toBe(0)
  })

  it('name_desc: gamma < beta < alpha', () => {
    expect(compareSourcesBy(gamma, beta, 'name_desc')).toBeLessThan(0)
    expect(compareSourcesBy(beta, alpha, 'name_desc')).toBeLessThan(0)
  })

  it('last_indexed_desc: beta (2024-07) first, gamma (null) last', () => {
    expect(compareSourcesBy(beta, alpha, 'last_indexed_desc')).toBeLessThan(0)
    expect(compareSourcesBy(alpha, gamma, 'last_indexed_desc')).toBeLessThan(0)
    expect(compareSourcesBy(gamma, beta, 'last_indexed_desc')).toBeGreaterThan(0)
  })

  it('last_indexed_desc: two nulls tie-break by name ascending', () => {
    const a = makeSource({ id: 'a', name: 'A', last_indexed: null })
    const b = makeSource({ id: 'b', name: 'B', last_indexed: null })
    expect(compareSourcesBy(a, b, 'last_indexed_desc')).toBeLessThan(0)
    expect(compareSourcesBy(b, a, 'last_indexed_desc')).toBeGreaterThan(0)
  })

  it('chunk_count_desc: beta (30) first, alpha (10) last', () => {
    expect(compareSourcesBy(beta, gamma, 'chunk_count_desc')).toBeLessThan(0)
    expect(compareSourcesBy(gamma, alpha, 'chunk_count_desc')).toBeLessThan(0)
  })

  it('document_count_desc: gamma (8) first, beta (2) last', () => {
    expect(compareSourcesBy(gamma, alpha, 'document_count_desc')).toBeLessThan(0)
    expect(compareSourcesBy(alpha, beta, 'document_count_desc')).toBeLessThan(0)
  })

  it('status_asc: error < pending < indexed', () => {
    expect(compareSourcesBy(beta, gamma, 'status_asc')).toBeLessThan(0)   // error < pending
    expect(compareSourcesBy(gamma, alpha, 'status_asc')).toBeLessThan(0)  // pending < indexed
    expect(compareSourcesBy(alpha, beta, 'status_asc')).toBeGreaterThan(0) // indexed > error
  })

  it('status_asc: identical source compares as 0', () => {
    expect(compareSourcesBy(alpha, alpha, 'status_asc')).toBe(0)
  })

  it('status_asc: same status tie-breaks by name ascending', () => {
    const zed = makeSource({ id: 'z', name: 'Zed', status: 'indexed' })
    const ant = makeSource({ id: 'x', name: 'Ant', status: 'indexed' })
    expect(compareSourcesBy(ant, zed, 'status_asc')).toBeLessThan(0)
    expect(compareSourcesBy(zed, ant, 'status_asc')).toBeGreaterThan(0)
  })

  it('chunk_count_desc: equal counts tie-break by name ascending', () => {
    const zed = makeSource({ id: 'z', name: 'Zed', chunk_count: 5 })
    const ant = makeSource({ id: 'x', name: 'Ant', chunk_count: 5 })
    expect(compareSourcesBy(ant, zed, 'chunk_count_desc')).toBeLessThan(0)
    expect(compareSourcesBy(zed, ant, 'chunk_count_desc')).toBeGreaterThan(0)
  })

  it('document_count_desc: equal counts tie-break by name ascending', () => {
    const zed = makeSource({ id: 'z', name: 'Zed', document_count: 5 })
    const ant = makeSource({ id: 'x', name: 'Ant', document_count: 5 })
    expect(compareSourcesBy(ant, zed, 'document_count_desc')).toBeLessThan(0)
  })

  it('created_desc: equal timestamps tie-break by name ascending', () => {
    const zed = makeSource({ id: 'z', name: 'Zed', created_at: '2024-05-01T00:00:00Z' })
    const ant = makeSource({ id: 'x', name: 'Ant', created_at: '2024-05-01T00:00:00Z' })
    expect(compareSourcesBy(ant, zed, 'created_desc')).toBeLessThan(0)
  })

  it('created_desc: beta (2024-03) first, alpha (2024-01) last', () => {
    expect(compareSourcesBy(beta, gamma, 'created_desc')).toBeLessThan(0)  // 2024-03 > 2024-02
    expect(compareSourcesBy(gamma, alpha, 'created_desc')).toBeLessThan(0) // 2024-02 > 2024-01
  })
})

describe('sortSources', () => {
  it('returns a new array (does not mutate input)', () => {
    const input = [beta, alpha, gamma]
    const result = sortSources(input, 'name_asc')
    expect(result).not.toBe(input)
    expect(input[0]).toBe(beta) // original untouched
  })

  it('name_asc produces alphabetical order', () => {
    const sorted = sortSources(sources, 'name_asc')
    expect(sorted.map((s) => s.name)).toEqual(['Alpha', 'Beta', 'Gamma'])
  })

  it('name_desc produces reverse alphabetical order', () => {
    const sorted = sortSources(sources, 'name_desc')
    expect(sorted.map((s) => s.name)).toEqual(['Gamma', 'Beta', 'Alpha'])
  })

  it('chunk_count_desc orders by chunk count descending', () => {
    const sorted = sortSources(sources, 'chunk_count_desc')
    expect(sorted.map((s) => s.chunk_count)).toEqual([30, 20, 10])
  })

  it('document_count_desc orders by document count descending', () => {
    const sorted = sortSources(sources, 'document_count_desc')
    expect(sorted.map((s) => s.document_count)).toEqual([8, 5, 2])
  })

  it('status_asc puts error first', () => {
    const sorted = sortSources(sources, 'status_asc')
    expect(sorted[0].status).toBe('error')
  })

  it('last_indexed_desc puts most-recently indexed first, never-indexed last', () => {
    const sorted = sortSources(sources, 'last_indexed_desc')
    expect(sorted[0].last_indexed).toBe('2024-07-01T00:00:00Z')
    expect(sorted[sorted.length - 1].last_indexed).toBeNull()
  })

  it('created_desc puts newest first', () => {
    const sorted = sortSources(sources, 'created_desc')
    expect(sorted[0].created_at).toBe('2024-03-01T00:00:00Z')
    expect(sorted[sorted.length - 1].created_at).toBe('2024-01-01T00:00:00Z')
  })

  it('handles empty array', () => {
    expect(sortSources([], 'name_asc')).toEqual([])
  })

  it('handles single-item array', () => {
    const result = sortSources([alpha], 'name_desc')
    expect(result).toHaveLength(1)
    expect(result[0]).toBe(alpha)
  })

  it('unknown key falls back to name ascending (deterministic)', () => {
    const input = [gamma, beta, alpha]
    const result = sortSources(input, 'unknown_key' as SourceSortKey)
    expect(result.map((s) => s.name)).toEqual(['Alpha', 'Beta', 'Gamma'])
  })

  it('status_asc with all-equal statuses yields stable name-ascending order', () => {
    const a = makeSource({ id: '1', name: 'Charlie', status: 'indexed' })
    const b = makeSource({ id: '2', name: 'Alpha', status: 'indexed' })
    const c = makeSource({ id: '3', name: 'Bravo', status: 'indexed' })
    const sorted = sortSources([a, b, c], 'status_asc')
    expect(sorted.map((s) => s.name)).toEqual(['Alpha', 'Bravo', 'Charlie'])
  })
})

describe('parseSortKey', () => {
  it('returns valid keys unchanged', () => {
    for (const { value } of SORT_OPTIONS) {
      expect(parseSortKey(value)).toBe(value)
    }
  })

  it('falls back to DEFAULT_SORT for unknown values', () => {
    expect(parseSortKey('bogus')).toBe(DEFAULT_SORT)
    expect(parseSortKey('NAME_ASC')).toBe(DEFAULT_SORT) // case-sensitive
    expect(parseSortKey('')).toBe(DEFAULT_SORT)
  })

  it('falls back to DEFAULT_SORT for null (param absent)', () => {
    expect(parseSortKey(null)).toBe(DEFAULT_SORT)
  })
})
