import { SiteTreeNode } from '../services/api/types/sources'

/**
 * Format a date string as relative time (e.g., "5m ago").
 * Also returns staleness info for progress tracking.
 */
export function formatTimeAgo(dateStr: string | null): {
  text: string
  isStale: boolean
  secondsAgo: number
} {
  if (!dateStr) return { text: 'Never', isStale: true, secondsAgo: Infinity }

  const date = new Date(dateStr)
  const now = new Date()
  const secondsAgo = Math.floor((now.getTime() - date.getTime()) / 1000)

  // Consider stale if no update in 30+ seconds
  const isStale = secondsAgo > 30

  if (secondsAgo < 5) return { text: 'Just now', isStale, secondsAgo }
  if (secondsAgo < 60) return { text: `${secondsAgo}s ago`, isStale, secondsAgo }
  if (secondsAgo < 3600) return { text: `${Math.floor(secondsAgo / 60)}m ago`, isStale, secondsAgo }
  if (secondsAgo < 86400) return { text: `${Math.floor(secondsAgo / 3600)}h ago`, isStale, secondsAgo }
  return { text: `${Math.floor(secondsAgo / 86400)}d ago`, isStale, secondsAgo }
}

/**
 * Flatten a site tree into a list of URLs.
 */
export function flattenTree(node: SiteTreeNode): string[] {
  const urls = [node.url]
  if (node.children) {
    for (const child of node.children) {
      urls.push(...flattenTree(child))
    }
  }
  return urls
}

/**
 * Format a date string for display.
 */
export function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  return new Date(dateStr).toLocaleString()
}

/**
 * Format duration in milliseconds to human-readable string.
 */
export function formatDuration(ms: number | null): string {
  if (ms === null) return '-'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}
