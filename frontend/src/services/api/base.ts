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
    throw new Error(error.detail || `HTTP ${response.status}`);
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
