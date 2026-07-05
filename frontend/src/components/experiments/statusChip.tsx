import { Badge } from '@/components/ui/badge'
import type {
  EvalRunStatus,
  ExperimentStatus,
  QuestionStatus,
} from '../../services/api/types/evaluation'

/**
 * Status chip styling for question lifecycle states.
 *
 * Colors resolve through design tokens (status-info/success/warning) — never
 * raw palette classes. Every chip pairs color with a visible text label so
 * status is never communicated by color alone (accessibility).
 */
const STATUS_CHIP_CLASSES: Record<QuestionStatus, string> = {
  draft: 'text-status-info border-status-info/40',
  active: 'text-status-success border-status-success/40',
  stale: 'text-status-warning border-status-warning/40',
  archived: 'text-muted-foreground border-border',
}

export function QuestionStatusChip({ status }: { status: QuestionStatus }) {
  return (
    <Badge
      variant="outline"
      className={`text-xs shrink-0 ${STATUS_CHIP_CLASSES[status] ?? 'text-muted-foreground border-border'}`}
    >
      {status}
    </Badge>
  )
}

/** Status chip styling for scorecard run states — same token-only rules as above. */
const RUN_STATUS_CHIP_CLASSES: Record<EvalRunStatus, string> = {
  pending: 'text-muted-foreground border-border',
  running: 'text-status-info border-status-info/40',
  completed: 'text-status-success border-status-success/40',
  partial: 'text-status-warning border-status-warning/40',
  error: 'text-status-error border-status-error/40',
}

export function RunStatusChip({ status }: { status: EvalRunStatus }) {
  return (
    <Badge
      variant="outline"
      className={`text-xs shrink-0 ${RUN_STATUS_CHIP_CLASSES[status] ?? 'text-muted-foreground border-border'}`}
    >
      {status}
    </Badge>
  )
}

/** Status chip styling for experiment states — same token-only rules as above. */
const EXPERIMENT_STATUS_CHIP_CLASSES: Record<ExperimentStatus, string> = {
  pending: 'text-muted-foreground border-border',
  indexing: 'text-status-info border-status-info/40',
  ready: 'text-status-success border-status-success/40',
  promoted: 'text-status-info border-status-info/40',
  error: 'text-status-error border-status-error/40',
}

export function ExperimentStatusChip({ status }: { status: ExperimentStatus }) {
  return (
    <Badge
      variant="outline"
      className={`text-xs shrink-0 ${EXPERIMENT_STATUS_CHIP_CLASSES[status] ?? 'text-muted-foreground border-border'}`}
    >
      {status}
    </Badge>
  )
}
