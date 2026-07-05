/**
 * Tests for automations view-model helpers — buildRefresh pending status
 * and formatTimeUntil guards.
 */
import { describe, it, expect } from 'vitest'
import { deriveAutomations, formatTimeUntil } from './automations'
import type { Source } from '../services/api/types/sources'

function makeSource(overrides: Partial<Source> = {}): Source {
  return {
    id: 'src-1',
    name: 'Test Source',
    source_type: 'url',
    source_path: 'https://example.com',
    status: 'indexed',
    freshness_policy: 'none',
    next_refresh_at: null,
    last_indexed: null,
    document_count: 0,
    chunk_count: 0,
    watch_enabled: false,
    watch_status: null,
    watch_last_heartbeat_at: null,
    watch_last_error: null,
    enrichment_enabled: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    parent_source_id: null,
    collection_name: null,
    description: null,
    stale_after_days: null,
    refresh_interval_days: null,
    is_stale: false,
    ...overrides,
  } as Source
}

describe('buildRefresh — pending status', () => {
  it('produces "scheduled" status when next_refresh_at is set in the future', () => {
    const future = new Date(Date.now() + 3_600_000).toISOString()
    const source = makeSource({ freshness_policy: 'automatic', next_refresh_at: future })
    const automations = deriveAutomations([source])
    const refresh = automations.find((a) => a.kind === 'refresh')
    expect(refresh?.status).toBe('scheduled')
    expect(refresh?.variant).toBe('success')
  })

  it('produces "pending" status when next_refresh_at is null and not indexing', () => {
    const source = makeSource({ freshness_policy: 'automatic', next_refresh_at: null, status: 'indexed' })
    const automations = deriveAutomations([source])
    const refresh = automations.find((a) => a.kind === 'refresh')
    expect(refresh?.status).toBe('pending')
    expect(refresh?.variant).toBe('warning')
    expect(refresh?.statusLabel).toBe('Pending')
  })

  it('produces "refreshing" status when source is indexing regardless of next_refresh_at', () => {
    const source = makeSource({ freshness_policy: 'automatic', next_refresh_at: null, status: 'indexing' })
    const automations = deriveAutomations([source])
    const refresh = automations.find((a) => a.kind === 'refresh')
    expect(refresh?.status).toBe('refreshing')
  })

  it('produces "refreshing" status when next_refresh_at is due', () => {
    const past = new Date(Date.now() - 1000).toISOString()
    const source = makeSource({ freshness_policy: 'automatic', next_refresh_at: past, status: 'indexed' })
    const automations = deriveAutomations([source])
    const refresh = automations.find((a) => a.kind === 'refresh')
    expect(refresh?.status).toBe('refreshing')
  })

  it('produces "paused" status for manual freshness_policy', () => {
    const source = makeSource({ freshness_policy: 'manual', next_refresh_at: null })
    const automations = deriveAutomations([source])
    const refresh = automations.find((a) => a.kind === 'refresh')
    expect(refresh?.status).toBe('paused')
    expect(refresh?.enabled).toBe(false)
  })
})

describe('formatTimeUntil', () => {
  it('returns "unscheduled" for null', () => {
    expect(formatTimeUntil(null)).toBe('unscheduled')
  })

  it('returns "unscheduled" for an unparseable date string', () => {
    expect(formatTimeUntil('not-a-date')).toBe('unscheduled')
  })

  it('returns "due now" for a past instant', () => {
    const past = new Date(Date.now() - 5000).toISOString()
    expect(formatTimeUntil(past)).toBe('due now')
  })

  it('formats a future instant in hours', () => {
    const future = new Date(Date.now() + 2 * 3_600_000 + 1000).toISOString()
    expect(formatTimeUntil(future)).toBe('in 2h')
  })
})
