/**
 * Background job queue types (/api/jobs)
 */

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface Job {
  id: string;
  job_type: string;
  status: JobStatus;
  priority: number;
  payload: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  retry_count: number;
  max_retries: number;
  project_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}
