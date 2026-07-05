import { useState, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, ArrowUpCircle, FlaskConical, GitCompareArrows, Loader2, Plus, Trash2 } from 'lucide-react'
import { agentsApi } from '../../services/api/agents'
import type { Agent } from '../../services/api/types/agents'
import { evaluationApi } from '../../services/api/evaluation'
import type { Experiment, OverrideKey, QuestionSet } from '../../services/api/types/evaluation'
import { OVERRIDE_KEYS } from '../../services/api/types/evaluation'
import { useStudioEvents } from '../../hooks/useStudioEvents'
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
import { ComparisonVerdict } from './ComparisonVerdict'
import { CompareDialog, PromoteDialog } from './ExperimentActionDialogs'
import { ExperimentFormDialog } from './ExperimentFormDialog'
import { ExperimentStatusChip } from './statusChip'

/** Compact label for one override chip; long prompt text collapses to a marker. */
function overrideChipLabel(key: OverrideKey, value: unknown): string {
  if (key === 'system_prompt') return 'system_prompt: edited'
  return `${key}: ${String(value)}`
}

interface ExperimentsTabProps {
  libraryId: string
  onError: (msg: string) => void
}

/**
 * Pipeline experiments for the selected library: create (agent + overrides),
 * compare against a baseline over a question set, promote the winner into the
 * agent's live config, delete. The open comparison lives in URL params
 * (`experiment`, `baseline_run`, `experiment_run`) so verdicts are shareable.
 */
export function ExperimentsTab({ libraryId, onError }: ExperimentsTabProps) {
  const { toast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const openExperimentId = searchParams.get('experiment')
  const baselineRunId = searchParams.get('baseline_run')
  const experimentRunId = searchParams.get('experiment_run')

  const [experiments, setExperiments] = useState<Experiment[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [sets, setSets] = useState<QuestionSet[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshToken, setRefreshToken] = useState(0)

  const [showCreate, setShowCreate] = useState(false)
  const [compareTarget, setCompareTarget] = useState<Experiment | null>(null)
  const [promoteTarget, setPromoteTarget] = useState<Experiment | null>(null)
  const [promoting, setPromoting] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Experiment | null>(null)
  const [deleting, setDeleting] = useState(false)

  const agentName = useCallback(
    (agentId: string | null) => agents.find(a => a.id === agentId)?.name ?? 'unknown agent',
    [agents]
  )

  const setComparisonParams = useCallback(
    (values: { experiment: string; baseline_run: string; experiment_run: string } | null) => {
      setSearchParams(
        prev => {
          const params = new URLSearchParams(prev)
          for (const key of ['experiment', 'baseline_run', 'experiment_run'] as const) {
            if (values) params.set(key, values[key])
            else params.delete(key)
          }
          return params
        },
        { replace: true }
      )
    },
    [setSearchParams]
  )

  useEffect(() => {
    agentsApi
      .list()
      .then(setAgents)
      .catch(err => onError(err instanceof Error ? err.message : 'Failed to load agents'))
  }, [onError])

  const fetchData = useCallback(async (opts?: { silent?: boolean }) => {
    try {
      if (!opts?.silent) setLoading(true)
      const [experimentList, setList] = await Promise.all([
        evaluationApi.listExperiments({ library_id: libraryId }),
        evaluationApi.listQuestionSets(libraryId),
      ])
      setExperiments(experimentList)
      setSets(setList)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load experiments')
    } finally {
      if (!opts?.silent) setLoading(false)
    }
  }, [libraryId, onError])

  useEffect(() => { fetchData() }, [fetchData])

  // Comparison runs execute in background jobs; promote can also arrive via MCP
  useStudioEvents({
    onRunCompleted: payload => {
      const runId =
        typeof payload.id === 'string'
          ? payload.id
          : typeof payload.run_id === 'string'
            ? payload.run_id
            : null
      if (runId && (runId === baselineRunId || runId === experimentRunId)) {
        setRefreshToken(t => t + 1)
      }
    },
    onExperimentPromoted: payload => {
      fetchData({ silent: true })
      const experiment = experiments.find(e => e.id === payload.experiment_id)
      toast({
        title: 'Experiment promoted',
        description: `${experiment?.name ?? 'An experiment'} is now the live agent config.`,
      })
    },
  })

  const handleCompareStart = async (questionSetId: string) => {
    if (!compareTarget) return
    try {
      const res = await evaluationApi.compareExperiment(compareTarget.id, questionSetId)
      toast({
        title: 'Comparison started',
        description: 'Baseline and experiment scorecards run in the background.',
      })
      setComparisonParams({
        experiment: compareTarget.id,
        baseline_run: res.baseline_run_id,
        experiment_run: res.experiment_run_id,
      })
      setCompareTarget(null)
    } catch (err) {
      toast({
        title: 'Failed to start comparison',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      })
    }
  }

  const handlePromote = async () => {
    if (!promoteTarget) return
    try {
      setPromoting(true)
      await evaluationApi.promoteExperiment(promoteTarget.id)
      toast({
        title: 'Experiment promoted',
        description: `"${promoteTarget.name}" was written into ${agentName(promoteTarget.agent_id)}'s live config.`,
      })
      setPromoteTarget(null)
      await fetchData({ silent: true })
    } catch (err) {
      toast({
        title: 'Failed to promote experiment',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      })
    } finally {
      setPromoting(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      setDeleting(true)
      await evaluationApi.deleteExperiment(deleteTarget.id)
      setExperiments(prev => prev.filter(e => e.id !== deleteTarget.id))
      toast({ title: 'Experiment deleted', description: `"${deleteTarget.name}" has been removed.` })
      setDeleteTarget(null)
    } catch (err) {
      toast({
        title: 'Failed to delete experiment',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      })
    } finally {
      setDeleting(false)
    }
  }

  const openExperiment = useMemo(
    () => experiments.find(e => e.id === openExperimentId) ?? null,
    [experiments, openExperimentId]
  )

  if (openExperimentId && baselineRunId && experimentRunId) {
    return (
      <ComparisonVerdict
        experimentId={openExperimentId}
        experimentName={openExperiment?.name ?? 'Experiment'}
        baselineRunId={baselineRunId}
        experimentRunId={experimentRunId}
        refreshToken={refreshToken}
        onBack={() => { setComparisonParams(null); fetchData({ silent: true }) }}
        onError={onError}
      />
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {experiments.length} experiment{experiments.length !== 1 ? 's' : ''}
        </p>
        <Button size="sm" onClick={() => setShowCreate(true)}>
          <Plus className="w-4 h-4 mr-1.5" />
          New Experiment
        </Button>
      </div>

      {experiments.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground/60">
          <FlaskConical className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">No experiments for this library yet.</p>
          <p className="text-xs mt-1">
            Clone an agent's pipeline config with overrides, compare against its baseline, promote the winner.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {experiments.map(experiment => (
            <Card key={experiment.id}>
              <CardContent className="py-3 px-4">
                <div className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm text-foreground truncate">{experiment.name}</span>
                      <ExperimentStatusChip status={experiment.status} />
                      {OVERRIDE_KEYS.filter(key => experiment.overrides[key] !== undefined).map(key => (
                        <Badge key={key} variant="outline" className="text-xs text-muted-foreground shrink-0">
                          {overrideChipLabel(key, experiment.overrides[key])}
                        </Badge>
                      ))}
                    </div>
                    <p className="text-xs text-muted-foreground/70 mt-0.5 truncate">
                      on {agentName(experiment.agent_id)}
                      {experiment.description && ` — ${experiment.description}`}
                      {experiment.status === 'error' && experiment.error_message && (
                        <span className="text-status-error"> — {experiment.error_message}</span>
                      )}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button variant="outline" size="sm" onClick={() => setCompareTarget(experiment)}>
                      <GitCompareArrows className="w-4 h-4 mr-1.5" />
                      Compare
                    </Button>
                    {experiment.status === 'ready' && (
                      <Button variant="outline" size="sm" onClick={() => setPromoteTarget(experiment)}>
                        <ArrowUpCircle className="w-4 h-4 mr-1.5" />
                        Promote
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-muted-foreground hover:text-destructive"
                      aria-label={`Delete experiment ${experiment.name}`}
                      onClick={() => setDeleteTarget(experiment)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create */}
      <ExperimentFormDialog
        open={showCreate}
        onOpenChange={setShowCreate}
        agents={agents}
        libraryId={libraryId}
        onSubmit={async values => {
          await evaluationApi.createExperiment({ library_id: libraryId, ...values })
          toast({ title: 'Experiment created', description: 'Ready to compare — no reindex needed.' })
          await fetchData({ silent: true })
        }}
      />

      {/* Compare: pick the question set both runs share */}
      <CompareDialog
        experiment={compareTarget}
        sets={sets}
        onClose={() => setCompareTarget(null)}
        onStart={handleCompareStart}
      />

      {/* Promote: list exactly which agent fields change */}
      <PromoteDialog
        experiment={promoteTarget}
        agentName={agentName(promoteTarget?.agent_id ?? null)}
        promoting={promoting}
        onClose={() => setPromoteTarget(null)}
        onConfirm={handlePromote}
      />

      {/* Delete confirmation */}
      <Dialog open={!!deleteTarget} onOpenChange={open => !open && setDeleteTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-status-warning" />
              Delete Experiment
            </DialogTitle>
            <DialogDescription>
              Delete <strong>{deleteTarget?.name}</strong>? Its scorecard runs stay in history.
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
