/**
 * Shared API utilities for Agentbase frontend
 */

// Use relative URL by default so nginx proxy works for remote access
// Set VITE_API_URL explicitly only for local dev with vite proxy
export const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// localStorage key for platform API key
const API_KEY_STORAGE_KEY = 'agentbase_api_key';

/**
 * Get the stored API key from localStorage
 */
export function getStoredApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE_KEY);
}

/**
 * Store an API key in localStorage for subsequent requests
 */
export function setStoredApiKey(key: string): void {
  localStorage.setItem(API_KEY_STORAGE_KEY, key);
}

/**
 * Clear the stored API key from localStorage
 */
export function clearStoredApiKey(): void {
  localStorage.removeItem(API_KEY_STORAGE_KEY);
}

/**
 * HTTP error with the FastAPI body attached.
 *
 * FastAPI string details stay a human message. Object details (e.g. 409
 * EMBEDDING_MISMATCH) put the inner dict on `body` so callers can read
 * `error_code` / `suggested_action` without stringifying `[object Object]`.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  readonly errorCode: string | undefined;
  readonly suggestedAction: string | undefined;

  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    const payload =
      body && typeof body === 'object' ? (body as Record<string, unknown>) : undefined;
    this.errorCode =
      typeof payload?.error_code === 'string' ? payload.error_code : undefined;
    this.suggestedAction =
      typeof payload?.suggested_action === 'string' ? payload.suggested_action : undefined;
  }
}

/**
 * Turn a FastAPI `{ detail }` body into an Error whose message is always a string.
 *
 * - `detail` string → that string
 * - `detail` object with a string `detail` field (incl. EMBEDDING_MISMATCH) → that field
 * - otherwise → `HTTP {status}` (never `[object Object]`)
 */
export function apiErrorFromBody(status: number, error: unknown): ApiError {
  const fallback = `HTTP ${status}`;
  if (!error || typeof error !== 'object') {
    return new ApiError(fallback, status, error);
  }

  const detail = (error as { detail?: unknown }).detail;

  if (typeof detail === 'string' && detail) {
    return new ApiError(detail, status, error);
  }

  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const payload = detail as Record<string, unknown>;
    const human = typeof payload.detail === 'string' ? payload.detail : undefined;
    return new ApiError(human || fallback, status, payload);
  }

  return new ApiError(fallback, status, error);
}

/**
 * Generic fetch wrapper with error handling and auth header injection
 */
interface ApiFetchOptions extends RequestInit {
  /** When true, 401 errors won't trigger the AuthGate dialog */
  suppressAuth?: boolean;
}

export async function apiFetch<T>(
  endpoint: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { suppressAuth, ...fetchOptions } = options;
  const url = `${API_BASE_URL}${endpoint}`;

  // Build headers with auth injection
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  // Inject API key from localStorage if present
  const apiKey = getStoredApiKey();
  if (apiKey) {
    headers['Authorization'] = `Bearer ${apiKey}`;
  }

  const response = await fetch(url, {
    ...fetchOptions,
    headers: {
      ...headers,
      ...(fetchOptions.headers as Record<string, string>),
    },
  });

  if (!response.ok) {
    // On 401, dispatch event for AuthGate to handle (unless suppressed)
    if (response.status === 401) {
      if (!suppressAuth) {
        window.dispatchEvent(new CustomEvent('auth:unauthorized'));
      }
      throw new Error('Authentication required');
    }
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw apiErrorFromBody(response.status, error);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return null as T;
  }

  return response.json();
}

/**
 * SSE event data structure
 */
interface SSEEvent {
  type: string;
  data: unknown;
}

/**
 * Generic SSE stream handler that consolidates duplicate streaming logic
 * @param url - The SSE endpoint URL
 * @param options - Fetch options (method, body, headers)
 * @param eventHandler - Callback for each parsed SSE event
 * @returns Abort function to cancel the stream
 */
export function createSSEStream(
  url: string,
  options: RequestInit,
  eventHandler: (event: SSEEvent) => void
): () => void {
  const controller = new AbortController();

  fetch(url, {
    ...options,
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE events
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        let eventType = '';
        let eventData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7);
          } else if (line.startsWith('data: ')) {
            eventData = line.slice(6);
          } else if (line === '' && eventType && eventData) {
            // Empty line signals end of event
            try {
              const parsed = JSON.parse(eventData);
              eventHandler({ type: eventType, data: parsed });
            } catch (e) {
              console.error('Failed to parse SSE event:', e);
            }
            eventType = '';
            eventData = '';
          }
        }
      }
    })
    .catch((error) => {
      if (error.name !== 'AbortError') {
        eventHandler({ type: 'error', data: { error: error.message, code: 500 } });
      }
    });

  // Return abort function
  return () => controller.abort();
}
