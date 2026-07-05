export interface APIKey {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  rate_limit_rpm: number | null;
  expires_at: string | null;
  last_used_at: string | null;
  is_active: boolean;
  created_at: string;
}

export interface APIKeyCreate {
  name: string;
  scopes: string[];
  rate_limit_rpm?: number;
  expires_at?: string;
}

export interface APIKeyCreateResponse extends APIKey {
  api_key: string;
  message: string;
}
