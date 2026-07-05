import { useState, useEffect } from 'react'
import { Loader2 } from 'lucide-react'
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
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { Question } from '../../services/api/types/evaluation'

export interface QuestionFormValues {
  question_text: string
  expected_criteria?: string
  tags?: string[]
}

interface QuestionFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** When set, the dialog edits this question; otherwise it adds a new one. */
  question?: Question | null
  /** Submit handler — resolves on success, throws on failure (dialog shows error). */
  onSubmit: (values: QuestionFormValues) => Promise<void>
}

/** Add/edit form for a golden question. Used for both manual authoring and draft curation edits. */
export function QuestionFormDialog({ open, onOpenChange, question, onSubmit }: QuestionFormDialogProps) {
  const [questionText, setQuestionText] = useState('')
  const [expectedCriteria, setExpectedCriteria] = useState('')
  const [tagsInput, setTagsInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reset form whenever the dialog opens for a (possibly different) question
  useEffect(() => {
    if (!open) return
    setQuestionText(question?.question_text ?? '')
    setExpectedCriteria(question?.expected_criteria ?? '')
    setTagsInput(question?.tags?.join(', ') ?? '')
    setError(null)
  }, [open, question])

  const handleSubmit = async () => {
    if (!questionText.trim()) return
    setSaving(true)
    setError(null)
    try {
      const tags = tagsInput
        .split(',')
        .map(t => t.trim())
        .filter(Boolean)
      await onSubmit({
        question_text: questionText.trim(),
        expected_criteria: expectedCriteria.trim() || undefined,
        tags: tags.length ? tags : undefined,
      })
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save question')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{question ? 'Edit Question' : 'Add Question'}</DialogTitle>
          <DialogDescription>
            {question
              ? 'Update the question text, the facts a good answer must contain, or its tags.'
              : 'Manually authored questions are trusted and created active.'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="space-y-1.5">
            <Label htmlFor="question-text">Question</Label>
            <Textarea
              id="question-text"
              rows={3}
              placeholder="e.g., What are the stages of the ACME onboarding flow?"
              value={questionText}
              onChange={e => setQuestionText(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="expected-criteria">Expected criteria</Label>
            <Textarea
              id="expected-criteria"
              rows={3}
              placeholder="Facts a good answer must contain, e.g., mentions the three onboarding stages"
              value={expectedCriteria}
              onChange={e => setExpectedCriteria(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="question-tags">Tags</Label>
            <Input
              id="question-tags"
              placeholder="Comma-separated, e.g., onboarding, process"
              value={tagsInput}
              onChange={e => setTagsInput(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={saving || !questionText.trim()}>
            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            {question ? 'Save Changes' : 'Add Question'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
