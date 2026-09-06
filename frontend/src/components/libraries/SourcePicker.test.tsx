/**
 * SourcePicker embedding-lock: mismatched rows are aria-disabled with a hint.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@/test/utils'
import userEvent from '@testing-library/user-event'
import type { Source } from '../../services/api/types/sources'
import { sourcesApi } from '../../services/api/sources'
import { SourcePicker, sourceEmbeddingMismatch } from './SourcePicker'

vi.mock('../../services/api/sources', () => ({
  sourcesApi: {
    listSources: vi.fn(),
  },
}))

const matchingSource = {
  id: 'source-1',
  name: 'React Documentation',
  source_type: 'url',
  status: 'indexed',
  chunk_count: 200,
  embedding_provider: 'ollama',
  embedding_model: 'mxbai-embed-large',
} as Source

const inheritingSource = {
  id: 'source-2',
  name: 'API Reference',
  source_type: 'file',
  status: 'pending',
  chunk_count: 0,
  embedding_provider: null,
  embedding_model: null,
} as Source

const mismatchSource = {
  id: 'source-3',
  name: 'Product Documentation',
  source_type: 'url',
  status: 'indexed',
  chunk_count: 10,
  embedding_provider: 'openai',
  embedding_model: 'text-embedding-3-small',
} as Source

describe('sourceEmbeddingMismatch', () => {
  it('is false when the library is unlocked', () => {
    expect(
      sourceEmbeddingMismatch(
        { embedding_provider: 'openai', embedding_model: 'text-embedding-3-small' },
        null,
        null,
      ),
    ).toBe(false)
  })

  it('is false when the source has no embedding (inherits the library model)', () => {
    expect(
      sourceEmbeddingMismatch(
        { embedding_provider: null, embedding_model: null },
        'openai',
        'text-embedding-3-small',
      ),
    ).toBe(false)
  })

  it('is false when provider and model match', () => {
    expect(
      sourceEmbeddingMismatch(
        { embedding_provider: 'openai', embedding_model: 'text-embedding-3-small' },
        'openai',
        'text-embedding-3-small',
      ),
    ).toBe(false)
  })

  it('is true when provider or model differ', () => {
    expect(
      sourceEmbeddingMismatch(
        { embedding_provider: 'ollama', embedding_model: 'nomic-embed-text' },
        'openai',
        'text-embedding-3-small',
      ),
    ).toBe(true)
  })
})

describe('SourcePicker', () => {
  beforeEach(() => {
    vi.mocked(sourcesApi.listSources).mockResolvedValue([
      matchingSource,
      inheritingSource,
      mismatchSource,
    ])
  })

  it('does not disable on embedding when the library is unlocked', async () => {
    render(
      <SourcePicker boundSourceIds={new Set()} value="" onChange={vi.fn()} />,
    )

    const mismatched = await screen.findByRole('option', { name: /Product Documentation/ })
    expect(mismatched).not.toHaveAttribute('aria-disabled', 'true')
  })

  it('disables mismatched sources when the library is locked and leaves matches enabled', async () => {
    const onChange = vi.fn()
    render(
      <SourcePicker
        boundSourceIds={new Set()}
        value=""
        onChange={onChange}
        embeddingProvider="ollama"
        embeddingModel="mxbai-embed-large"
      />,
    )

    const matching = await screen.findByRole('option', { name: /React Documentation/ })
    const inheriting = screen.getByRole('option', { name: /API Reference/ })
    const mismatched = screen.getByRole('option', { name: /Product Documentation/ })

    expect(matching).not.toHaveAttribute('aria-disabled', 'true')
    expect(inheriting).not.toHaveAttribute('aria-disabled', 'true')
    expect(mismatched).toHaveAttribute('aria-disabled', 'true')
    expect(mismatched).toHaveTextContent(/does not match this library/)

    const user = userEvent.setup()
    await user.click(mismatched)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('keeps already-bound sources disabled even when embeddings match', async () => {
    render(
      <SourcePicker
        boundSourceIds={new Set(['source-1'])}
        value=""
        onChange={vi.fn()}
        embeddingProvider="ollama"
        embeddingModel="mxbai-embed-large"
      />,
    )

    const bound = await screen.findByRole('option', { name: /React Documentation/ })
    expect(bound).toHaveAttribute('aria-disabled', 'true')
    expect(bound).toHaveTextContent(/already in library/)
  })
})
