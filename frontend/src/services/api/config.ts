/**
 * Config and Health APIs
 */

import { apiFetch } from './base';
import type { EmbeddingConfig, HealthStatus } from './types/common';

export const configApi = {
  getEmbeddingConfig: () =>
    apiFetch<EmbeddingConfig>('/api/config/embedding'),
};

export const healthApi = {
  check: () => apiFetch<HealthStatus>('/health'),
};
