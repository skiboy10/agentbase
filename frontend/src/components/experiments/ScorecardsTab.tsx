import { useState, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ClipboardCheck, Loader2, Play } from 'lucide-react'
import { agentsApi } from '../../services/api/agents'
import type { Agent } from '../../services/api/types/agents'
import { evaluationApi } from '../../services/api/evaluation'
import type {
  EvalRunSummary,
  EvalTargetType,
  QuestionSet,
} from '../../services/api/types/evaluation'
import { useStudioEvents } from '../../hooks/useStudioEvents'
import { useToast } from '@/hooks/use-toast'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { RunReportCard, formatMs, formatRate } from './RunReportCard'
import { RunStatusChip } from './statusChip'

interface ScorecardsTabProps {
  libraryId: string
  libraryName: string
  onError: (msg: string) => void
}

/**
 * Scorecards tab: pick a target (the page's library, or an agent), pick a
 * question set from this library, run a scorecard, and browse run history.
 * The open run lives in the `run` URL param so report cards are shareable.
 */
export function ScorecardsTab({ libraryId, libraryName, onError }: ScorecardsTabProps) {
  const { toast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const openRunId = searchParams.get('run')

  const [targetType, setTargetType] = useState<EvalTargetType>('library')
  const [agentId, setAgentId] = useState('')
  const [agents, setAgents] = useState<Agent[]>([])
  const [questionSetId, setQuestionSetId] = useState('')
  const [sets, setSets] = useState<QuestionSet[]>([])
  const [runs, setRuns] = useState<EvalRunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [refreshToken, setRefreshToken] = useState(0)

  const setRunParam = useCallback(
    (runId: string | null) => {
      setSearchParams(
        prev => {
          const params = new URLSearchParams(prev)
          if (runId) params.set('run', runId)
          else params.delete('run')
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
      const [setList, runList] = await Promise.all([
        evaluationApi.listQuestionSets(libraryId),
        evaluationApi.listRuns({ library_id: libraryId, limit: 50 }),
      ])
      setSets(setList)
      setRuns(runList)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load scorecards')
    } finally {
      if (!opts?.silent) setLoading(false)
    }
  }, [libraryId, onError])

  useEffect(() => {
    setQuestionSetId('')
    fetchData()
  }, [fetchData])

  // Runs are scoped to this library's question sets (covers agent runs too,
  // since every question set belongs to a library).
  const libraryRuns = useMemo(() => {
    const setIds = new Set(sets.map(s => s.id))
    return runs.filter(run => setIds.has(run.question_set_id))
  }, [runs, sets])

  // Scorecards execute in background jobs — refresh and announce via SSE
  useStudioEvents({
    onRunCompleted: payload => {
      const status = typeof payload.status === 'string' ? payload.status : 'completed'
      if (status === 'error') {
        toast({
          title: 'Scorecard failed',
          description: 'The run hit an error. Open it to inspect the details.',
          variant: 'destructive',
        })
      } else {
        toast({
          title: status === 'partial' ? 'Scorecard partially complete' : 'Scorecard complete',
          description:
            status === 'partial'
              ? 'Some answers could not be judged — open the run to re-judge them.'
              : 'The report card is ready.',
        })
      }
      fetchData({ silent: true })
      setRefreshToken(t => t + 1)
    },
  })

  const handleRun = async () => {
    const targetId = targetType === 'library' ? libraryId : agentId
    if (!targetId || !questionSetId) return
    try {
      setRunning(true)
      await evaluationApi.createRun({
        target_type: targetType,
        target_id: targetId,
        question_set_id: questionSetId,
      })
      toast({
        title: 'Scorecard running',
        description: 'The run executes in the background — results appear here when it completes.',
      })
      await fetchData({ silent: true })
    } catch (err) {
      toast({
        title: 'Failed to start scorecard',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      })
    } finally {
      setRunning(false)
    }
  }

  if (openRunId) {
    return (
      <RunReportCard
        runId={openRunId}
        refreshToken={refreshToken}
        onBack={() => { setRunParam(null); fetchData({ silent: true }) }}
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

  const canRun = !!questionSetId && (targetType === 'library' || !!agentId)

  return (
    <div className="space-y-5">
      {/* Run launcher */}
      <Card>
        <CardContent className="py-4 px-4">
          <div className="flex flex-wrap items-end gap-4">
            <div className="space-y-1.5">
              <Label>Target</Label>
              <div className="flex gap-1" role="radiogroup" aria-label="Scorecard target type">
                <Button
                  size="sm"
                  variant={targetType === 'library' ? 'default' : 'outline'}
                  role="radio"
                  aria-checked={targetType === 'library'}
                  onClick={() => setTargetType('library')}
                >
                  Library
                </Button>
                <Button
                  size="sm"
                  variant={targetType === 'agent' ? 'default' : 'outline'}
                  role="radio"
                  aria-checked={targetType === 'agent'}
                  onClick={() => setTargetType('agent')}
                >
                  Agent
                </Button>
              </div>
            </div>

            {targetType === 'library' ? (
              <div className="space-y-1.5">
                <Label>Library</Label>
                <p className="text-sm text-foreground h-9 flex items-center px-3 rounded-md border border-border bg-muted/30">
                  {libraryName}
                </p>
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label>Agent</Label>
                <Select value={agentId || undefined} onValueChange={setAgentId}>
                  <SelectTrigger className="w-56" aria-label="Select agent">
                    <SelectValue placeholder="Select an agent..." />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map(agent => (
                      <SelectItem key={agent.id} value={agent.id}>{agent.name}</SelectItem>
                    ))}
                    {agents.length === 0 && (
                      <div className="px-3 py-2 text-sm text-muted-foreground">
                        No agents yet — create one on the Agents page
                      </div>
                    )}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="space-y-1.5">
              <Label>Question set</Label>
              <Select value={questionSetId || undefined} onValueChange={setQuestionSetId}>
                <SelectTrigger className="w-64" aria-label="Select question set">
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

            <Button onClick={handleRun} disabled={!canRun || running}>
              {running ? (
                <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
              ) : (
                <Play className="w-4 h-4 mr-1.5" />
              )}
              Run scorecard
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Run history */}
      {libraryRuns.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground/60">
          <ClipboardCheck className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">No scorecard runs for this library yet.</p>
          <p className="text-xs mt-1">Pick a question set and run a baseline to start a quality history.</p>
        </div>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Target</TableHead>
                  <TableHead>Question set</TableHead>
                  <TableHead className="w-24">Status</TableHead>
                  <TableHead className="w-20 text-right">Found@5</TableHead>
                  <TableHead className="w-16 text-right">MRR</TableHead>
                  <TableHead className="w-20 text-right">Passed</TableHead>
                  <TableHead className="w-20 text-right">p50</TableHead>
                  <TableHead className="w-40">Started</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {libraryRuns.map(run => {
                  const m = run.metrics_summary
                  return (
                    <TableRow
                      key={run.id}
                      className="cursor-pointer"
                      onClick={() => setRunParam(run.id)}
                    >
                      <TableCell className="max-w-0">
                        <span className="block truncate text-sm font-medium" title={run.target_label}>
                          {run.target_label}
                        </span>
                        <span className="text-xs text-muted-foreground">{run.run_type}</span>
                      </TableCell>
                      <TableCell className="max-w-0">
                        <span className="block truncate text-sm text-muted-foreground" title={run.question_set_name}>
                          {run.question_set_name}
                        </span>
                      </TableCell>
                      <TableCell><RunStatusChip status={run.status} /></TableCell>
                      <TableCell className="text-right tabular-nums text-sm">
                        {formatRate(m?.found_at_5_rate)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-sm">
                        {m && m.mrr !== null ? m.mrr.toFixed(2) : '—'}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-sm">
                        {m && m.judged_count > 0 ? `${m.passed_count}/${m.judged_count}` : '—'}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs text-muted-foreground">
                        {formatMs(m?.latency_p50_ms)}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
