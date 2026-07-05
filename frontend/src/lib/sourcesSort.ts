/**
 * Sort utilities for the Sources list.
 *
 * Sort keys are chosen based on fields that are always present on the Source
 * model. Sub-source-count (`sub_source_count`) and watcher-activity sorts are
 * omitted — sub_source_count is available but it only has meaning for parent
 * directory sources; watcher-activity timestamps are not carried on the list
 * response.
 */

import type { Source } from '../services/api/types/sources'

export type SourceSortKey =
  | 'name_asc'
  | 'name_desc'
  | 'last_indexed_desc'
  | 'chunk_count_desc'
  | 'document_count_desc'
  | 'status_asc'
  | 'created_desc'

export interface SortOption {
  value: SourceSortKey
  label: string
}

export const SORT_OPTIONS: SortOption[] = [
  { value: 'name_asc', label: 'Name A→Z' },
  { value: 'name_desc', label: 'Name Z→A' },
  { value: 'last_indexed_desc', label: 'Last indexed (newest)' },
  { value: 'chunk_count_desc', label: 'Chunks (high→low)' },
  { value: 'document_count_desc', label: 'Documents (high→low)' },
  { value: 'status_asc', label: 'Status (error first)' },
  { value: 'created_desc', label: 'Created (newest)' },
]

export const DEFAULT_SORT: SourceSortKey = 'name_asc'

const VALID_SORT_KEYS = new Set<string>(SORT_OPTIONS.map((o) => o.value))

/**
 * Parse a raw URL param value into a valid sort key.
 * Unknown/missing values fall back to DEFAULT_SORT so a hand-edited or
 * stale URL (e.g. ?sort=bogus) never leaves the Select control blank.
 */
export function parseSortKey(value: string | null): SourceSortKey {
  if (value !== null && VALID_SORT_KEYS.has(value)) return value as SourceSortKey
  return DEFAULT_SORT
}

/**
 * Status sort priority — lower index = sorts first.
 * Order: error → indexing → pending → indexed
 */
const STATUS_ORDER: Record<string, number> = {
  error: 0,
  indexing: 1,
  pending: 2,
  indexed: 3,
}

function statusRank(status: string): number {
  return STATUS_ORDER[status] ?? 99
}

/** Primary comparison for a sort key, without tie-breaking. */
function comparePrimary(a: Source, b: Source, key: SourceSortKey): number {
  switch (key) {
    case 'name_asc':
      return a.name.localeCompare(b.name)
    case 'name_desc':
      return b.name.localeCompare(a.name)
    case 'last_indexed_desc': {
      // Nulls (never indexed) sort last
      if (!a.last_indexed && !b.last_indexed) return 0
      if (!a.last_indexed) return 1
      if (!b.last_indexed) return -1
      return b.last_indexed.localeCompare(a.last_indexed)
    }
    case 'chunk_count_desc':
      return b.chunk_count - a.chunk_count
    case 'document_count_desc':
      return b.document_count - a.document_count
    case 'status_asc':
      return statusRank(a.status) - statusRank(b.status)
    case 'created_desc':
      return b.created_at.localeCompare(a.created_at)
    default:
      return 0
  }
}

/**
 * Compare two Source objects by the given sort key.
 * Returns a negative number, zero, or positive number, suitable for Array.sort().
 *
 * For non-name keys, ties on the primary comparison fall back to name
 * ascending so the order is deterministic and rows don't jump around
 * between renders or data refreshes.
 */
export function compareSourcesBy(a: Source, b: Source, key: SourceSortKey): number {
  const primary = comparePrimary(a, b, key)
  if (primary !== 0 || key === 'name_asc' || key === 'name_desc') return primary
  return a.name.localeCompare(b.name)
}

/**
 * Return a sorted copy of the sources array according to sortKey.
 * The original array is not mutated.
 */
export function sortSources(sources: Source[], key: SourceSortKey): Source[] {
  return [...sources].sort((a, b) => compareSourcesBy(a, b, key))
}
