/**
 * Tests for page-level utility helpers:
 *   - extractTextFromNode (APIReferencePage): flattens React node trees to plain text
 *   - uniqueSlug (APIReferencePage): uniquifies repeated heading slugs in document order
 *   - formatDate (APIKeysPage): guards against malformed date strings
 */
import { describe, it, expect } from 'vitest'
import React from 'react'
import { extractTextFromNode, uniqueSlug } from './APIReferencePage'
import { formatDate } from './APIKeysPage'

// ---------------------------------------------------------------------------
// extractTextFromNode
// ---------------------------------------------------------------------------

describe('extractTextFromNode', () => {
  it('returns empty string for null', () => {
    expect(extractTextFromNode(null)).toBe('')
  })

  it('returns empty string for undefined', () => {
    expect(extractTextFromNode(undefined)).toBe('')
  })

  it('returns a plain string unchanged', () => {
    expect(extractTextFromNode('hello world')).toBe('hello world')
  })

  it('converts a number to string', () => {
    expect(extractTextFromNode(42)).toBe('42')
  })

  it('flattens an array of strings', () => {
    expect(extractTextFromNode(['foo', ' ', 'bar'])).toBe('foo bar')
  })

  it('extracts text from a React element with a string child', () => {
    const el = React.createElement('code', null, 'my-slug')
    expect(extractTextFromNode(el)).toBe('my-slug')
  })

  it('extracts text from nested React elements (bold inside heading)', () => {
    const bold = React.createElement('strong', null, 'bold')
    const el = React.createElement('span', null, 'Before ', bold, ' after')
    expect(extractTextFromNode(el)).toBe('Before bold after')
  })

  it('flattens deeply nested nodes', () => {
    const code = React.createElement('code', null, 'inner')
    const p = React.createElement('p', null, 'Prefix ', code)
    expect(extractTextFromNode(p)).toBe('Prefix inner')
  })

  it('produces the same slug as headings with inline code would', () => {
    // Simulates: ## Using `source_id`
    const code = React.createElement('code', null, 'source_id')
    const children = ['Using ', code]
    const text = extractTextFromNode(children)
    const slug = text.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-')
    // Should be "using-source_id", not "using-object-object"
    expect(slug).toBe('using-source_id')
    expect(slug).not.toContain('object')
  })
})

// ---------------------------------------------------------------------------
// uniqueSlug
// ---------------------------------------------------------------------------

describe('uniqueSlug', () => {
  it('returns the base slug for a first occurrence', () => {
    const counts = new Map<string, number>()
    expect(uniqueSlug('response', counts)).toBe('response')
  })

  it('appends -1, -2 for repeated slugs (GitHub anchor convention)', () => {
    const counts = new Map<string, number>()
    expect(uniqueSlug('response', counts)).toBe('response')
    expect(uniqueSlug('response', counts)).toBe('response-1')
    expect(uniqueSlug('response', counts)).toBe('response-2')
  })

  it('tracks different base slugs independently', () => {
    const counts = new Map<string, number>()
    expect(uniqueSlug('response', counts)).toBe('response')
    expect(uniqueSlug('request', counts)).toBe('request')
    expect(uniqueSlug('response', counts)).toBe('response-1')
    expect(uniqueSlug('request', counts)).toBe('request-1')
  })

  it('produces identical sequences for two consumers scanning the same document order', () => {
    // Simulates the TOC builder and the markdown renderer each walking
    // headings in document order with their own counts map — ids must match.
    const headings = ['Overview', 'Response', 'Response', 'Errors', 'Response']
    const slugifyLocal = (t: string) => t.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-')

    const tocCounts = new Map<string, number>()
    const tocIds = headings.map(h => uniqueSlug(slugifyLocal(h), tocCounts))

    const rendererCounts = new Map<string, number>()
    const renderedIds = headings.map(h => uniqueSlug(slugifyLocal(h), rendererCounts))

    expect(renderedIds).toEqual(tocIds)
    expect(tocIds).toEqual(['overview', 'response', 'response-1', 'errors', 'response-2'])
  })
})

// ---------------------------------------------------------------------------
// formatDate
// ---------------------------------------------------------------------------

describe('formatDate', () => {
  it('returns em dash for null', () => {
    expect(formatDate(null)).toBe('—')
  })

  it('returns the raw string for a malformed date (NaN guard)', () => {
    expect(formatDate('not-a-date')).toBe('not-a-date')
  })

  it('returns the raw string for an empty-ish invalid value', () => {
    expect(formatDate('0000-99-99')).toBe('0000-99-99')
  })

  it('returns a formatted date string for a valid ISO date', () => {
    const result = formatDate('2026-01-15T10:30:00Z')
    // Should include the year and not be the raw ISO string
    expect(result).toContain('2026')
    expect(result).not.toBe('2026-01-15T10:30:00Z')
  })

  it('does not throw for any string input', () => {
    const inputs = ['', 'garbage', '9999-12-31', '2026-06-10T00:00:00Z', null]
    for (const input of inputs) {
      expect(() => formatDate(input)).not.toThrow()
    }
  })
})
