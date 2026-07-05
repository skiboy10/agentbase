/**
 * Tests for shared status helpers — watchStatusMeta and statusClasses dot key.
 */
import { describe, it, expect } from 'vitest'
import { watchStatusMeta, statusClasses } from './status'

describe('statusClasses', () => {
  it('includes a dot class for every variant', () => {
    const variants = ['success', 'warning', 'info', 'error', 'neutral'] as const
    for (const variant of variants) {
      const classes = statusClasses(variant)
      expect(classes.dot, `dot missing for variant "${variant}"`).toBeTruthy()
      expect(classes.dot.startsWith('bg-'), `dot should start with bg- for "${variant}"`).toBe(true)
    }
  })

  it('uses design tokens, not raw palette classes', () => {
    const variants = ['success', 'warning', 'info', 'error', 'neutral'] as const
    for (const variant of variants) {
      const { dot } = statusClasses(variant)
      expect(dot).not.toMatch(/bg-(?:blue|green|red|yellow|orange|purple|pink|gray|zinc|slate)-\d+/)
    }
  })
})

describe('watchStatusMeta', () => {
  it('maps running → success variant', () => {
    const meta = watchStatusMeta('running')
    expect(meta.variant).toBe('success')
    expect(meta.label).toBe('Watching')
    expect(meta.colorClass).toContain('text-status-success')
  })

  it('maps degraded → warning variant', () => {
    const meta = watchStatusMeta('degraded')
    expect(meta.variant).toBe('warning')
    expect(meta.colorClass).toContain('text-status-warning')
  })

  it('maps path_missing → error variant', () => {
    const meta = watchStatusMeta('path_missing')
    expect(meta.variant).toBe('error')
    expect(meta.label).toBe('Path not found')
  })

  it('maps error → error variant', () => {
    const meta = watchStatusMeta('error')
    expect(meta.variant).toBe('error')
    expect(meta.label).toBe('Watcher error')
  })

  it('maps stopped → neutral variant', () => {
    const meta = watchStatusMeta('stopped')
    expect(meta.variant).toBe('neutral')
    expect(meta.label).toBe('Watcher stopped')
  })

  it('falls back to neutral for null', () => {
    const meta = watchStatusMeta(null)
    expect(meta.variant).toBe('neutral')
  })

  it('falls back to neutral for undefined', () => {
    const meta = watchStatusMeta(undefined)
    expect(meta.variant).toBe('neutral')
  })

  it('falls back to neutral for unknown status', () => {
    const meta = watchStatusMeta('unknown_status')
    expect(meta.variant).toBe('neutral')
  })
})
