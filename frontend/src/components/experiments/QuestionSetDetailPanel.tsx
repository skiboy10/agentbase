import { useState, useEffect, useCallback } from 'react'
import {
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronRight,
  ListChecks,
  Loader2,
  Pencil,
  Plus,
  X,
} from 'lucide-react'
import { evaluationApi } from '../../services/api/evaluation'
import type { Question, QuestionSetDetail } from '../../services/api/types/evaluation'
import { useToast } from '@/hooks/use-toast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { QuestionFormDialog, type QuestionFormValues } from './QuestionFormDialog'
import { QuestionStatusChip } from './statusChip'

interface QuestionRowProps {
  question: Question
  actioning: boolean
  onApprove?: () => void
  onEdit: () => void
  onDelete: () => void
}

function QuestionRow({ question, actioning, onApprove, onEdit, onDelete }: QuestionRowProps) {
  return (
    <Card>
      <CardContent className="py-3 px-4">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <QuestionStatusChip status={question.status} />
              <Badge variant="outline" className="text-xs text-muted-foreground shrink-0">
                {question.origin}
              </Badge>
              {question.tags?.map(tag => (
                <Badge key={tag} variant="secondary" className="text-xs shrink-0">{tag}</Badge>
              ))}
            </div>
            <p className="text-sm text-foreground mt-1.5">{question.question_text}</p>
            {question.expected_criteria && (
              <p className="text-xs text-muted-foreground mt-1">
                Expects: {question.expected_criteria}
              </p>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {onApprove && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-status-success hover:text-status-success hover:bg-status-success/10"
                aria-label="Approve question"
                title="Approve (set active)"
                onClick={onApprove}
                disabled={actioning}
              >
                {actioning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
              aria-label="Edit question"
              title="Edit"
              onClick={onEdit}
              disabled={actioning}
            >
              <Pencil className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
              aria-label="Delete question"
              title="Delete (archives if it has eval results)"
              onClick={onDelete}
              disabled={actioning}
            >
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

interface QuestionSetDetailPanelProps {
  setId: string
  /** Bump to force a refetch (e.g., after a generation-complete event). */
  refreshToken?: number
  onBack: () => void
  onError: (msg: string) => void
  /** Called after any mutation so the parent list can refresh its counts. */
  onChanged?: () => void
}

/** Curation view for one question set: drafts first (the curation queue), then active, then retired. */
export function QuestionSetDetailPanel({
  setId, refreshToken, onBack, onError, onChanged,
}: QuestionSetDetailPanelProps) {
  const { toast } = useToast()
  const [detail, setDetail] = useState<QuestionSetDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [actioning, setActioning] = useState<string | null>(null)
  const [retiredOpen, setRetiredOpen] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Question | null>(null)

  const fetchDetail = useCallback(async () => {
    try {
      setLoading(true)
      setDetail(await evaluationApi.getQuestionSet(setId))
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load question set')
    } finally {
      setLoading(false)
    }
  }, [setId, onError])

  useEffect(() => { fetchDetail() }, [fetchDetail, refreshToken])

  const handleApprove = async (q: Question) => {
    setActioning(q.id)
    try {
      await evaluationApi.updateQuestion(q.id, { status: 'active' })
      toast({ title: 'Question approved', description: 'The draft is now active.' })
      await fetchDetail()
      onChanged?.()
    } catch (err) {
      toast({
        title: 'Failed to approve question',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      })
    } finally {
      setActioning(null)
    }
  }

  const handleDelete = async (q: Question) => {
    setActioning(q.id)
    try {
      const { outcome } = await evaluationApi.deleteQuestion(q.id)
      toast({
        title: outcome === 'archived' ? 'Question archived' : 'Question deleted',
        description: outcome === 'archived'
          ? 'It has eval results, so it was archived to preserve scorecard history.'
          : 'The question has been removed.',
      })
      await fetchDetail()
      onChanged?.()
    } catch (err) {
      toast({
        title: 'Failed to delete question',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      })
    } finally {
      setActioning(null)
    }
  }

  const handleFormSubmit = async (values: QuestionFormValues) => {
    if (editTarget) {
      await evaluationApi.updateQuestion(editTarget.id, values)
      toast({ title: 'Question updated' })
    } else {
      await evaluationApi.addQuestion(setId, values)
      toast({ title: 'Question added', description: 'Manual questions are created active.' })
    }
    await fetchDetail()
    onChanged?.()
  }

  if (loading && !detail) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!detail) return null

  const drafts = detail.questions.filter(q => q.status === 'draft')
  const active = detail.questions.filter(q => q.status === 'active')
  const retired = detail.questions.filter(q => q.status === 'archived' || q.status === 'stale')

  const rowProps = (q: Question) => ({
    question: q,
    actioning: actioning === q.id,
    onEdit: () => { setEditTarget(q); setFormOpen(true) },
    onDelete: () => handleDelete(q),
  })

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="min-w-0">
          <Button
            variant="ghost"
            size="sm"
            className="-ml-2 mb-1 text-muted-foreground hover:text-foreground"
            onClick={onBack}
          >
            <ArrowLeft className="w-4 h-4 mr-1.5" />
            Question Sets
          </Button>
          <h2 className="text-lg font-semibold text-foreground truncate">{detail.name}</h2>
          {detail.description && (
            <p className="text-sm text-muted-foreground">{detail.description}</p>
          )}
        </div>
        <Button size="sm" onClick={() => { setEditTarget(null); setFormOpen(true) }}>
          <Plus className="w-4 h-4 mr-1.5" />
          Add Question
        </Button>
      </div>

      {detail.questions.length === 0 && (
        <div className="text-center py-12 text-muted-foreground/60">
          <ListChecks className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">No questions yet.</p>
          <p className="text-xs mt-1">Add one manually or generate drafts from the library's documents.</p>
        </div>
      )}

      {drafts.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-medium text-foreground">
            Curation queue
            <span className="ml-2 text-xs text-muted-foreground">
              {drafts.length} draft{drafts.length !== 1 ? 's' : ''} awaiting review
            </span>
          </h3>
          {drafts.map(q => (
            <QuestionRow key={q.id} {...rowProps(q)} onApprove={() => handleApprove(q)} />
          ))}
        </section>
      )}

      {active.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-medium text-foreground">
            Active
            <span className="ml-2 text-xs text-muted-foreground">{active.length}</span>
          </h3>
          {active.map(q => <QuestionRow key={q.id} {...rowProps(q)} />)}
        </section>
      )}

      {retired.length > 0 && (
        <Collapsible open={retiredOpen} onOpenChange={setRetiredOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="-ml-2 text-muted-foreground hover:text-foreground">
              {retiredOpen ? <ChevronDown className="w-4 h-4 mr-1.5" /> : <ChevronRight className="w-4 h-4 mr-1.5" />}
              Archived &amp; stale ({retired.length})
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-2 mt-2">
            {retired.map(q => <QuestionRow key={q.id} {...rowProps(q)} />)}
          </CollapsibleContent>
        </Collapsible>
      )}

      <QuestionFormDialog
        open={formOpen}
        onOpenChange={open => { setFormOpen(open); if (!open) setEditTarget(null) }}
        question={editTarget}
        onSubmit={handleFormSubmit}
      />
    </div>
  )
}
