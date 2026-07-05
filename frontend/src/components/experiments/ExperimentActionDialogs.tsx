import { useState } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import type { Experiment, QuestionSet } from '../../services/api/types/evaluation'
import { OVERRIDE_KEYS } from '../../services/api/types/evaluation'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

/** Display value in the promote dialog; prompts truncate, everything else verbatim. */
function promoteValueLabel(value: unknown): string {
  const text = String(value)
  return text.length > 80 ? `${text.slice(0, 80)}...` : text
}

interface CompareDialogProps {
  /** Experiment to compare; null keeps the dialog closed. */
  experiment: Experiment | null
  sets: QuestionSet[]
  onClose: () => void
  /** Starts the comparison — resolves on success (parent closes + navigates). */
  onStart: (questionSetId: string) => Promise<void>
}

/** Question-set picker for a baseline-vs-experiment comparison. */
export function CompareDialog({ experiment, sets, onClose, onStart }: CompareDialogProps) {
  const [setId, setSetId] = useState('')
  const [starting, setStarting] = useState(false)

  const handleStart = async () => {
    if (!setId) return
    try {
      setStarting(true)
      await onStart(setId)
      setSetId('')
    } finally {
      setStarting(false)
    }
  }

  return (
    <Dialog open={!!experiment} onOpenChange={open => { if (!open) { setSetId(''); onClose() } }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Compare Against Baseline</DialogTitle>
          <DialogDescription>
            Runs two scorecards over the same question set — the agent's live config as
            baseline vs. <strong>{experiment?.name}</strong> — and diffs them per question.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5 py-2">
          <Label>Question set</Label>
          <Select value={setId || undefined} onValueChange={setSetId}>
            <SelectTrigger aria-label="Select question set">
              <SelectValue placeholder="Select a question set..." />
            </SelectTrigger>
            <SelectContent>
              {sets.map(set => (
                <SelectItem key={set.id} value={set.id}>{set.name}</SelectItem>
              ))}
              {sets.length === 0 && (
                <div className="px-3 py-2 text-sm text-muted-foreground">
                  No question sets for this library yet
                </div>
              )}
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={handleStart} disabled={starting || !setId}>
            {starting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Start Comparison
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface PromoteDialogProps {
  /** Experiment to promote; null keeps the dialog closed. */
  experiment: Experiment | null
  agentName: string
  promoting: boolean
  onClose: () => void
  onConfirm: () => void
}

/** Promote confirmation listing exactly which agent fields the overrides will change. */
export function PromoteDialog({ experiment, agentName, promoting, onClose, onConfirm }: PromoteDialogProps) {
  return (
    <Dialog open={!!experiment} onOpenChange={open => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-status-warning" />
            Promote Experiment
          </DialogTitle>
          <DialogDescription>
            Promoting <strong>{experiment?.name}</strong> updates these fields on agent{' '}
            <strong>{agentName}</strong>'s live config:
          </DialogDescription>
        </DialogHeader>
        <ul className="space-y-1.5 py-1 text-sm">
          {experiment &&
            OVERRIDE_KEYS.filter(key => experiment.overrides[key] !== undefined).map(key => (
              <li key={key} className="flex gap-2">
                <code className="text-xs bg-muted/50 rounded px-1.5 py-0.5 shrink-0">{key}</code>
                <span className="text-muted-foreground break-all">
                  {promoteValueLabel(experiment.overrides[key])}
                </span>
              </li>
            ))}
        </ul>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={onConfirm} disabled={promoting}>
            {promoting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Promote
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
