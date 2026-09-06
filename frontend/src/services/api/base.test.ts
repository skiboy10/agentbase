/**
 * Tests for FastAPI error-body parsing in apiFetch.
 *
 * Object `detail` (409 EMBEDDING_MISMATCH) used to stringify as "[object Object]".
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/mocks/server'
import { apiFetch, ApiError, apiErrorFromBody } from './base'

const mismatchPayload = {
  error_code: 'EMBEDDING_MISMATCH',
  detail:
    'Source embedding model (ollama/nomic-embed-text) does not match library embedding model (openai/text-embedding-3-small). A library locks its embedding model to the first source bound to it; all subsequent sources must match.',
  library: {
    id: 'lib-1',
    embedding_provider: 'openai',
    embedding_model: 'text-embedding-3-small',
  },
  source: {
    id: 'src-1',
    embedding_provider: 'ollama',
    embedding_model: 'nomic-embed-text',
  },
  suggested_action:
    "Create a new source configured with embedding model 'openai/text-embedding-3-small' and bind that to this library, OR bind this source to a library whose embedding model matches 'ollama/nomic-embed-text'.",
}

describe('apiErrorFromBody', () => {
  it('uses a string detail as the message', () => {
    const err = apiErrorFromBody(404, { detail: 'Library not found' })
    expect(err).toBeInstanceOf(ApiError)
    expect(err.message).toBe('Library not found')
    expect(err.status).toBe(404)
  })

  it('parses EMBEDDING_MISMATCH object detail into a human message + payload', () => {
    const err = apiErrorFromBody(409, { detail: mismatchPayload })
    expect(err).toBeInstanceOf(ApiError)
    expect(err.message).toBe(mismatchPayload.detail)
    expect(err.message).not.toBe('[object Object]')
    expect(err.status).toBe(409)
    expect(err.errorCode).toBe('EMBEDDING_MISMATCH')
    expect(err.suggestedAction).toBe(mismatchPayload.suggested_action)
    expect(err.body).toEqual(mismatchPayload)
  })

  it('falls back to HTTP status when object detail has no string detail field', () => {
    const err = apiErrorFromBody(409, { detail: { error_code: 'EMBEDDING_MISMATCH' } })
    expect(err.message).toBe('HTTP 409')
    expect(err.message).not.toBe('[object Object]')
    expect(err.errorCode).toBe('EMBEDDING_MISMATCH')
  })

  it('does not stringify array (422) details as [object Object]', () => {
    const err = apiErrorFromBody(422, {
      detail: [{ loc: ['body', 'source_id'], msg: 'field required', type: 'missing' }],
    })
    expect(err.message).toBe('HTTP 422')
    expect(err.message).not.toContain('[object Object]')
  })
})

describe('apiFetch error handling', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => undefined,
      removeItem: () => undefined,
      clear: () => undefined,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('throws ApiError with human detail on 409 EMBEDDING_MISMATCH', async () => {
    server.use(
      http.post('/api/libraries/:id/sources', () =>
        HttpResponse.json({ detail: mismatchPayload }, { status: 409 }),
      ),
    )

    const err = await apiFetch('/api/libraries/lib-1/sources', {
      method: 'POST',
      body: JSON.stringify({ source_id: 'src-1' }),
    }).catch((e: unknown) => e)

    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).message).toBe(mismatchPayload.detail)
    expect((err as ApiError).suggestedAction).toBe(mismatchPayload.suggested_action)
    expect((err as ApiError).status).toBe(409)
  })

  it('dispatches auth:unauthorized and throws Authentication required on 401', async () => {
    const dispatch = vi.spyOn(window, 'dispatchEvent')
    server.use(
      http.get('/api/protected', () =>
        HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }),
      ),
    )

    await expect(apiFetch('/api/protected')).rejects.toThrow('Authentication required')
    expect(dispatch).toHaveBeenCalled()
    const event = dispatch.mock.calls.find(
      ([arg]) => arg instanceof CustomEvent && arg.type === 'auth:unauthorized',
    )?.[0] as CustomEvent | undefined
    expect(event?.type).toBe('auth:unauthorized')
    dispatch.mockRestore()
  })

  it('does not dispatch AuthGate when suppressAuth is set', async () => {
    const dispatch = vi.spyOn(window, 'dispatchEvent')
    server.use(
      http.get('/api/protected', () =>
        HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }),
      ),
    )

    await expect(apiFetch('/api/protected', { suppressAuth: true })).rejects.toThrow(
      'Authentication required',
    )
    const authEvents = dispatch.mock.calls.filter(
      ([arg]) => arg instanceof CustomEvent && arg.type === 'auth:unauthorized',
    )
    expect(authEvents).toHaveLength(0)
    dispatch.mockRestore()
  })
})
