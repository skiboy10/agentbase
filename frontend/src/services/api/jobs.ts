/**
 * Jobs API — visibility into the background job queue.
 */

import { apiFetch } from './base';
import type { Job } from './types/jobs';

export const jobsApi = {
  // List jobs (newest first), optionally filtered by type/status
  list: (params?: { job_type?: string; status?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.job_type) query.set('job_type', params.job_type);
    if (params?.status) query.set('status', params.status);
    if (params?.limit) query.set('limit', String(params.limit));
    const qs = query.toString();
    // Trailing slash matches the backend route (avoids a 307 redirect)
    return apiFetch<Job[]>(`/api/jobs/${qs ? `?${qs}` : ''}`);
  },

  // Get a single job
  get: (id: string) => apiFetch<Job>(`/api/jobs/${id}`),
};
