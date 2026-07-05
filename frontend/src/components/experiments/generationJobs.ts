/**
 * Pure helpers for tracking question-generation background jobs.
 *
 * The Generate button stays pending while a `generate_questions` job for the
 * set is queued or running; jobs come newest-first from /api/jobs.
 */
import type { Job } from '../../services/api/types/jobs'

export const GENERATION_JOB_TYPE = 'generate_questions'

/** Generation count bounds/default — mirror the backend's validated range. */
export const GENERATION_COUNT_MIN = 5
export const GENERATION_COUNT_MAX = 50
export const GENERATION_COUNT_DEFAULT = 30

/** Parse a raw count input. Returns the integer, or null when invalid. */
export function parseGenerationCount(raw: string): number | null {
  if (!/^\d+$/.test(raw.trim())) return null
  const value = Number(raw.trim())
  if (value < GENERATION_COUNT_MIN || value > GENERATION_COUNT_MAX) return null
  return value
}

function generationSetId(job: Job): string | null {
  if (job.job_type !== GENERATION_JOB_TYPE) return null
  const setId = job.payload?.question_set_id
  return typeof setId === 'string' ? setId : null
}

/** Question-set ids whose MOST RECENT generation job is queued or running.

Only the newest job per set counts — an older job wedged in 'queued' or
'running' must not pin the button to pending after a later run completed. */
export function pendingGenerationSetIds(jobs: Job[]): Set<string> {
  const ids = new Set<string>()
  const seen = new Set<string>()
  for (const job of jobs) {  // newest-first from /api/jobs
    const setId = generationSetId(job)
    if (!setId || seen.has(setId)) continue
    seen.add(setId)
    if (job.status === 'queued' || job.status === 'running') {
      ids.add(setId)
    }
  }
  return ids
}

/** Value equality for two id sets (state must not churn on identical polls). */
export function sameIdSet(a: Set<string>, b: Set<string>): boolean {
  if (a.size !== b.size) return false
  for (const id of a) if (!b.has(id)) return false
  return true
}

/** Most recent generation job for a set (jobs are newest-first). */
export function latestGenerationJobForSet(jobs: Job[], setId: string): Job | null {
  return jobs.find(job => generationSetId(job) === setId) ?? null
}
