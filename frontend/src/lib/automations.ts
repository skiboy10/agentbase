/**
 * Automations view-model.
 *
 * Agentbase runs two kinds of per-source background automation:
 *   - "watcher"  — a folder watcher that live-monitors a directory for changes
 *   - "refresh"  — an auto-refresh schedule that periodically re-indexes a source
 *                  (this is what drives recurring YouTube channel pulls, but also
 *                  applies to website/URL, directory, and file sources)
 *
 * These helpers derive a flat, display-ready list of automations from the raw
 * Source list returned by the API. Pure functions — no I/O — so they're trivial
 * to unit-test and safe to call on every render.
 */
import type { Source } from '../services/api/types/sources'
import type { StatusVariant } from './status'

export type AutomationKind = 'watcher' | 'refresh'

export type AutomationStatus =
  | 'running'      // watcher actively watching
  | 'starting'     // watcher enabled, supervisor will start it shortly
  | 'degraded'     // watcher running but reporting errors
  | 'path_missing' // watcher path no longer exists
  | 'error'        // watcher in an error state
  | 'scheduled'    // auto-refresh active, next_refresh_at is set
  | 'pending'      // auto-refresh active but next_refresh_at not yet assigned
  | 'refreshing'   // auto-refresh due / currently re-indexing
  | 'paused'       // user-paused (durable)
  | 'off'          // directory watcher that has never been enabled

export interface Automation {
  /** Stable unique row id (a source can host both kinds). */
  id: string
  kind: AutomationKind
  source: Source
  status: AutomationStatus
  variant: StatusVariant
  statusLabel: string
  /** Toggle state — is the automation currently active (vs paused/off)? */
  enabled: boolean
}

const STATUS_META: Record<AutomationStatus, { variant: StatusVariant; label: string }> = {
  running: { variant: 'success', label: 'Watching' },
  starting: { variant: 'neutral', label: 'Starting…' },
  degraded: { variant: 'warning', label: 'Watching with errors' },
  path_missing: { variant: 'error', label: 'Path missing' },
  error: { variant: 'error', label: 'Error' },
  scheduled: { variant: 'success', label: 'Scheduled' },
  pending: { variant: 'warning', label: 'Pending' },
  refreshing: { variant: 'info', label: 'Refreshing' },
  paused: { variant: 'neutral', label: 'Paused' },
  off: { variant: 'neutral', label: 'Off' },
}

function makeAutomation(
  kind: AutomationKind,
  source: Source,
  status: AutomationStatus,
  enabled: boolean,
): Automation {
  const meta = STATUS_META[status]
  return {
    id: `${kind}:${source.id}`,
    kind,
    source,
    status,
    variant: meta.variant,
    statusLabel: meta.label,
    enabled,
  }
}

function buildWatcher(source: Source): Automation {
  const enabled = source.watch_enabled
  if (!enabled) {
    // Distinguish a paused watcher (ran before) from one never set up.
    const status: AutomationStatus = source.watch_last_heartbeat_at ? 'paused' : 'off'
    return makeAutomation('watcher', source, status, false)
  }
  let status: AutomationStatus
  switch (source.watch_status) {
    case 'running':
      status = 'running'
      break
    case 'degraded':
      status = 'degraded'
      break
    case 'path_missing':
      status = 'path_missing'
      break
    case 'error':
      status = 'error'
      break
    default:
      // 'stopped' while enabled — the supervisor reconciler will start it.
      status = 'starting'
  }
  return makeAutomation('watcher', source, status, true)
}

function buildRefresh(source: Source): Automation {
  if (source.freshness_policy === 'manual') {
    return makeAutomation('refresh', source, 'paused', false)
  }
  // automatic
  if (source.status === 'indexing') {
    return makeAutomation('refresh', source, 'refreshing', true)
  }
  if (!source.next_refresh_at) {
    // Automatic policy is active but the scheduler hasn't assigned a time yet.
    return makeAutomation('refresh', source, 'pending', true)
  }
  const due = new Date(source.next_refresh_at).getTime() <= Date.now()
  const status: AutomationStatus = due ? 'refreshing' : 'scheduled'
  return makeAutomation('refresh', source, status, true)
}

/**
 * Derive the full list of automations from a source list.
 * A source may yield both a watcher and a refresh row — they pause independently.
 */
export function deriveAutomations(sources: Source[]): Automation[] {
  const out: Automation[] = []
  for (const source of sources) {
    // Folder watchers live only on root directory sources (sub-sources share
    // the parent's collection / watcher, so they have none of their own).
    // Only surface a watcher that is actually an automation: currently enabled,
    // or previously ran and is now paused (has a heartbeat). A directory whose
    // watcher was never enabled isn't an automation, so it stays off this page.
    if (
      source.source_type === 'directory' &&
      source.parent_source_id == null &&
      (source.watch_enabled || source.watch_last_heartbeat_at != null)
    ) {
      out.push(buildWatcher(source))
    }
    // Auto-refresh schedules: "automatic" = active, "manual" = paused.
    // "none"/null means no schedule, so it's not an automation.
    if (source.freshness_policy === 'automatic' || source.freshness_policy === 'manual') {
      out.push(buildRefresh(source))
    }
  }
  return out
}

const ATTENTION_STATUSES: AutomationStatus[] = ['degraded', 'path_missing', 'error']

export function needsAttention(automation: Automation): boolean {
  return ATTENTION_STATUSES.includes(automation.status)
}

export interface AutomationSummary {
  running: number
  paused: number
  needsAttention: number
}

export function summaryCounts(automations: Automation[]): AutomationSummary {
  let running = 0
  let paused = 0
  let attention = 0
  for (const a of automations) {
    if (needsAttention(a)) attention++
    else if (a.enabled) running++
    else paused++
  }
  return { running, paused, needsAttention: attention }
}

/**
 * Human-readable relative time for a *future* instant (e.g. next refresh).
 * Complements formatTimeAgo, which only handles the past.
 */
export function formatTimeUntil(dateStr: string | null): string {
  if (!dateStr) return 'unscheduled'
  const time = new Date(dateStr).getTime()
  if (isNaN(time)) return 'unscheduled'
  const secs = Math.floor((time - Date.now()) / 1000)
  if (secs <= 0) return 'due now'
  if (secs < 60) return `in ${secs}s`
  if (secs < 3600) return `in ${Math.floor(secs / 60)}m`
  if (secs < 86400) return `in ${Math.floor(secs / 3600)}h`
  return `in ${Math.floor(secs / 86400)}d`
}
