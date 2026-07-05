/**
 * API Client for Agentbase Backend
 *
 * This file re-exports from the modular api/ directory for backward compatibility.
 * All existing imports will continue to work unchanged.
 *
 * For new code, consider importing directly from specific modules:
 *   import { sourcesApi } from './api/sources'
 *   import type { Source } from './api/types/sources'
 */

export * from './api/index';
