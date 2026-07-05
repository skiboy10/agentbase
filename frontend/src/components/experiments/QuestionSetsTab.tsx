import { useState, useEffect, useCallback, useRef } from 'react'
import { AlertTriangle, ListChecks, Loader2, Plus, Sparkles, Trash2 } from 'lucide-react'
import { evaluationApi } from '../../services/api/evaluation'
import { jobsApi } from '../../services/api/jobs'
import type { QuestionSet } from '../../services/api/types/evaluation'
import { useStudioEvents } from '../../hooks/useStudioEvents'
import {
  GENERATION_COUNT_DEFAULT,
  GENERATION_COUNT_MAX,
  GENERATION_COUNT_MIN,
  GENERATION_JOB_TYPE,
  latestGenerationJobForSet,
  parseGenerationCount,
  pendingGenerationSetIds,
  sameIdSet,
} from './generationJobs'
import { useToast } from '@/hooks/use-toast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { QuestionSetDetailPanel } from './QuestionSetDetailPanel'

interface QuestionSetsTabProps {
  libraryId: string
  onError: (msg: string) => void
}

/** Per-status question counts shown as labeled badges on each set card. */
function statusCounts(set: QuestionSet) {
  return set.question_counts
}

/** Question set list for a library, with create/generate/delete and a curation detail panel. */
export function QuestionSetsTab({ libraryId, onError }: QuestionSetsTabProps) {
  const { toast } = useToast()
  const [sets, setSets] = useState<QuestionSet[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedSetId, setSelectedSetId] = useState<string | null>(null)
  const [refreshToken, setRefreshToken] = useState(0)

  // Create dialog
  const [showCreate, setShowCreate] = useState(false)
  const [createName, setCreateName] = useState('')
  const [createDescription, setCreateDescription] = useState('')
  const [creating, setCreating] = useState(false)

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState<QuestionSet | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Sets with a generation job queued/running — button stays pending until
  // the job finishes (survives page reloads via the /api/jobs fetch below)
  const [pendingSetIds, setPendingSetIds] = useState<Set<string>>(new Set())
  const pendingRef = useRef(pendingSetIds)
  pendingRef.current = pendingSetIds
  // Per-set draft-count input (raw string; empty = untouched default)
  const [countBySet, setCountBySet] = useState<Record<string, string>>({})

  const fetchSets = useCallback(async (opts?: { silent?: boolean }) => {
    try {
      if (!opts?.silent) setLoading(true)
      const list = await evaluationApi.listQuestionSets(libraryId)
      setSets(list)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load question sets')
    } finally {
      if (!opts?.silent) setLoading(false)
    }
  }, [libraryId, onError])

  useEffect(() => {
    setSelectedSetId(null)
    fetchSets()
  }, [fetchSets])

  const refreshAll = useCallback(() => {
    fetchSets({ silent: true })
    setRefreshToken(t => t + 1)
  }, [fetchSets])

  // Refs keep reconcilePending's identity stable regardless of how the parent
  // passes onError — an unstable callback chain here would re-arm the poll
  // interval every render and refire the mount effect (Antigravity finding).
  const refreshAllRef = useRef(refreshAll)
  refreshAllRef.current = refreshAll

  /**
   * Reconcile pending button state against the job queue. Runs on mount (so a
   * page reload mid-generation still shows the pending button) and on a slow
   * poll while anything is pending — the poll covers what SSE cannot: failed
   * jobs publish no event, and events can be missed during a disconnect.
   */
  const reconcilePending = useCallback(async (opts?: { announce?: boolean }) => {
    try {
      const jobs = await jobsApi.list({ job_type: GENERATION_JOB_TYPE, limit: 100 })
      const next = pendingGenerationSetIds(jobs)
      if (opts?.announce) {
        const finished = [...pendingRef.current].filter(id => !next.has(id))
        for (const setId of finished) {
          const latest = latestGenerationJobForSet(jobs, setId)
          if (latest?.status === 'failed' || latest?.status === 'cancelled') {
            toast({
              title: 'Question generation failed',
              description: latest.error_message ?? 'The generation job did not complete.',
              variant: 'destructive',
            })
          } else {
            toast({
              title: 'Draft questions ready for review',
              description: 'New drafts are waiting in the curation queue.',
            })
          }
        }
        if (finished.length > 0) refreshAllRef.current()
      }
      // Same contents -> keep the old Set identity so polls don't re-render.
      setPendingSetIds(prev => (sameIdSet(prev, next) ? prev : next))
    } catch {
      // Job queue visibility is best-effort; SSE remains the primary signal
    }
  }, [toast])

  useEffect(() => { reconcilePending() }, [reconcilePending])

  const hasPending = pendingSetIds.size > 0
  useEffect(() => {
    if (!hasPending) return
    const timer = setInterval(() => reconcilePending({ announce: true }), 5000)
    return () => clearInterval(timer)
  }, [hasPending, reconcilePending])

  // Generation completes in a background job — refresh and announce via SSE
  useStudioEvents({
    onQuestionsGenerated: payload => {
      const created = typeof payload.created === 'number' ? payload.created : 0
      const setId = typeof payload.question_set_id === 'string' ? payload.question_set_id : null
      toast({
        title: 'Draft questions ready for review',
        description: `${created} draft question${created !== 1 ? 's' : ''} added to the curation queue.`,
      })
      if (setId) {
        setPendingSetIds(prev => {
          if (!prev.has(setId)) return prev
          const next = new Set(prev)
          next.delete(setId)
          return next
        })
      }
      refreshAll()
    },
  })

  const handleCreate = async () => {
    if (!createName.trim()) return
    try {
      setCreating(true)
      await evaluationApi.createQuestionSet({
        library_id: libraryId,
        name: createName.trim(),
        description: createDescription.trim() || undefined,
      })
      setShowCreate(false)
      setCreateName('')
      setCreateDescription('')
      toast({ title: 'Question set created' })
      await fetchSets({ silent: true })
    } catch (err) {
      toast({
        title: 'Failed to create question set',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      })
    } finally {
      setCreating(false)
    }
  }

  /** Raw count input for a set ('' = untouched, shows the default). */
  const rawCountFor = (setId: string) => countBySet[setId] ?? String(GENERATION_COUNT_DEFAULT)

  const handleGenerate = async (setId: string) => {
    const count = parseGenerationCount(rawCountFor(setId))
    if (count === null) return // button is disabled; guard against stale clicks
    setPendingSetIds(prev => new Set(prev).add(setId))
    try {
      await evaluationApi.generateQuestions(setId, { count })
      toast({
        title: 'Generating draft questions',
        description: `About ${count} drafts will appear in the curation queue when ready.`,
      })
    } catch (err) {
      setPendingSetIds(prev => {
        const next = new Set(prev)
        next.delete(setId)
        return next
      })
      toast({
        title: 'Failed to start generation',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      })
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      setDeleting(true)
      await evaluationApi.deleteQuestionSet(deleteTarget.id)
      setSets(prev => prev.filter(s => s.id !== deleteTarget.id))
      if (selectedSetId === deleteTarget.id) setSelectedSetId(null)
      toast({ title: 'Question set deleted', description: `"${deleteTarget.name}" has been removed.` })
      setDeleteTarget(null)
    } catch (err) {
      toast({
        title: 'Failed to delete question set',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      })
    } finally {
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (selectedSetId) {
    return (
      <QuestionSetDetailPanel
        setId={selectedSetId}
        refreshToken={refreshToken}
        onBack={() => { setSelectedSetId(null); fetchSets({ silent: true }) }}
        onError={onError}
        onChanged={() => fetchSets({ silent: true })}
      />
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {sets.length} question set{sets.length !== 1 ? 's' : ''}
        </p>
        <Button size="sm" onClick={() => setShowCreate(true)}>
          <Plus className="w-4 h-4 mr-1.5" />
          New Question Set
        </Button>
      </div>

      {sets.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground/60">
          <ListChecks className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">No question sets for this library yet.</p>
          <p className="text-xs mt-1">Create one, then generate draft questions from its documents.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {sets.map(set => {
            const counts = statusCounts(set)
            const generating = pendingSetIds.has(set.id)
            const rawCount = rawCountFor(set.id)
            const countInvalid = parseGenerationCount(rawCount) === null
            return (
              <Card
                key={set.id}
                className="cursor-pointer hover:border-primary/40 transition-colors"
                onClick={() => setSelectedSetId(set.id)}
              >
                <CardContent className="py-3 px-4">
                  <div className="flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-sm text-foreground truncate">{set.name}</span>
                        {(['draft', 'active', 'archived', 'stale'] as const).map(status =>
                          counts[status] ? (
                            <Badge key={status} variant="outline" className="text-xs text-muted-foreground shrink-0">
                              {counts[status]} {status}
                            </Badge>
                          ) : null
                        )}
                      </div>
                      {set.description && (
                        <p className="text-xs text-muted-foreground/70 mt-0.5 truncate">{set.description}</p>
                      )}
                    </div>
                    <div className="flex items-start gap-1 shrink-0" onClick={e => e.stopPropagation()}>
                      <div className="flex flex-col items-end">
                        <div className="flex items-center gap-1.5">
                          <Input
                            type="number"
                            min={GENERATION_COUNT_MIN}
                            max={GENERATION_COUNT_MAX}
                            value={rawCount}
                            onChange={e => setCountBySet(prev => ({ ...prev, [set.id]: e.target.value }))}
                            disabled={generating}
                            aria-label={`Draft question count for ${set.name}`}
                            aria-invalid={countInvalid}
                            className="w-16 h-9"
                          />
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleGenerate(set.id)}
                            disabled={generating || countInvalid}
                          >
                            {generating ? (
                              <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                            ) : (
                              <Sparkles className="w-4 h-4 mr-1.5" />
                            )}
                            {generating ? 'Generating…' : 'Generate questions'}
                          </Button>
                        </div>
                        {countInvalid && (
                          <p className="text-xs font-medium text-destructive mt-1">
                            Count must be {GENERATION_COUNT_MIN}-{GENERATION_COUNT_MAX}
                          </p>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-muted-foreground hover:text-destructive"
                        aria-label={`Delete question set ${set.name}`}
                        onClick={() => setDeleteTarget(set)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* Create dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>New Question Set</DialogTitle>
            <DialogDescription>
              Question sets hold golden questions used to score retrieval and answer quality.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="set-name">Name</Label>
              <Input
                id="set-name"
                placeholder="e.g., Core onboarding questions"
                value={createName}
                onChange={e => setCreateName(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="set-description">Description</Label>
              <Textarea
                id="set-description"
                rows={2}
                placeholder="What this set covers (optional)"
                value={createDescription}
                onChange={e => setCreateDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={creating || !createName.trim()}>
              {creating && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={!!deleteTarget} onOpenChange={open => !open && setDeleteTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-status-warning" />
              Delete Question Set
            </DialogTitle>
            <DialogDescription>
              Delete <strong>{deleteTarget?.name}</strong> and all its questions?
              This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
