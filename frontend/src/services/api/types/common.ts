/**
 * Common/shared types used across multiple API modules
 */

export interface Provider {
  name: string;
  display_name: string;
  is_configured: boolean;
  is_active: boolean;
  is_healthy: boolean;
  available_models: string[];
  disabled_models: string[];
  base_url: string | null;
  requires_api_key: boolean;
}

export interface ModelAssignment {
  task_type: string;
  provider: string;
  model: string;
  is_global: boolean;
}

export interface EmbeddingModel {
  id: string;
  name: string;
  provider: string;
  dimensions: number;
  max_input_tokens: number;
}

export interface EmbeddingConfig {
  default_provider: string;
  default_model: string;
  available_models: Array<{
    provider: string;
    model: string;
    dimensions: number;
  }>;
}

export interface HealthStatus {
  status: string;
  version: string;
  providers: Record<string, boolean>;
}
