/**
 * Tests for question-generation job helpers
 */
import { describe, it, expect } from 'vitest'
import type { Job } from '../../services/api/types/jobs'
import {
  latestGenerationJobForSet,
  parseGenerationCount,
  pendingGenerationSetIds,
  sameIdSet,
} from './generationJobs'

function job(overrides: Partial<Job>): Job {
  return {
    id: 'job-1',
    job_type: 'generate_questions',
    status: 'queued',
    priority: 0,
    payload: { question_set_id: 'set-1' },
    started_at: null,
    completed_at: null,
    error_message: null,
    retry_count: 0,
    max_retries: 3,
    project_id: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  }
}

describe('pendingGenerationSetIds', () => {
  it('includes sets with queued or running generation jobs', () => {
    const jobs = [
      job({ id: 'a', status: 'queued', payload: { question_set_id: 'set-1' } }),
      job({ id: 'b', status: 'running', payload: { question_set_id: 'set-2' } }),
    ]
    expect(pendingGenerationSetIds(jobs)).toEqual(new Set(['set-1', 'set-2']))
  })

  it('excludes finished jobs and other job types', () => {
    const jobs = [
      job({ id: 'a', status: 'completed' }),
      job({ id: 'b', status: 'failed' }),
      job({ id: 'c', status: 'cancelled' }),
      job({ id: 'd', job_type: 'index_source', status: 'running', payload: {} }),
      job({ id: 'e', status: 'running', payload: {} }), // no question_set_id
    ]
    expect(pendingGenerationSetIds(jobs).size).toBe(0)
  })
})

describe('latestGenerationJobForSet', () => {
  it('returns the first (newest) matching job', () => {
    const jobs = [
      job({ id: 'newest', status: 'failed' }),
      job({ id: 'older', status: 'completed' }),
    ]
    expect(latestGenerationJobForSet(jobs, 'set-1')?.id).toBe('newest')
  })

  it('returns null when the set has no generation jobs', () => {
    expect(latestGenerationJobForSet([job({})], 'set-9')).toBeNull()
  })
})

describe('parseGenerationCount', () => {
  it('accepts integers within 5-50', () => {
    expect(parseGenerationCount('5')).toBe(5)
    expect(parseGenerationCount('30')).toBe(30)
    expect(parseGenerationCount('50')).toBe(50)
    expect(parseGenerationCount(' 12 ')).toBe(12)
  })

  it('rejects out-of-range, non-integer, and empty input', () => {
    for (const raw of ['4', '51', '0', '-3', '3.5', 'abc', '', '  ']) {
      expect(parseGenerationCount(raw)).toBeNull()
    }
  })
})


describe('pendingGenerationSetIds — stuck older jobs', () => {
  it('only the newest job per set decides pending state', () => {
    // newest-first: the latest run completed; an older one is wedged 'running'
    const jobs = [
      job({ id: 'new', status: 'completed' }),
      job({ id: 'old-stuck', status: 'running' }),
    ]
    expect(pendingGenerationSetIds(jobs).has('set-1')).toBe(false)
  })

  it('newest queued job still reads as pending', () => {
    const jobs = [
      job({ id: 'new', status: 'queued' }),
      job({ id: 'old', status: 'completed' }),
    ]
    expect(pendingGenerationSetIds(jobs).has('set-1')).toBe(true)
  })
})

describe('sameIdSet', () => {
  it('true for equal contents regardless of insertion order', () => {
    expect(sameIdSet(new Set(['a', 'b']), new Set(['b', 'a']))).toBe(true)
    expect(sameIdSet(new Set(), new Set())).toBe(true)
  })

  it('false for differing size or members', () => {
    expect(sameIdSet(new Set(['a']), new Set(['a', 'b']))).toBe(false)
    expect(sameIdSet(new Set(['a']), new Set(['b']))).toBe(false)
  })
})
