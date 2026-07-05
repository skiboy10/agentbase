import { useState, useEffect, useCallback } from 'react'
import { AlertTriangle, ArrowLeft, Check, Gavel, Loader2, X } from 'lucide-react'
import { evaluationApi } from '../../services/api/evaluation'
import type { EvalResult, EvalRunDetail } from '../../services/api/types/evaluation'
import { useToast } from '@/hooks/use-toast'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ResultDrilldownDialog } from './ResultDrilldownDialog'
import { RunStatusChip } from './statusChip'

/** Format a 0-1 rate as a percentage label; em dash when unscored. */
export function formatRate(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? '—' : `${Math.round(rate * 100)}%`
}

/** Format a millisecond latency; em dash when absent. */
export function formatMs(ms: number | null | undefined): string {
  return ms === null || ms === undefined ? '—' : `${Math.round(ms)} ms`
}

/** Lower = worse. Failed answers first, then poor retrieval, then weak judge scores. */
function worstFirstKey(r: EvalResult): number {
  const rr = r.retrieval_metrics ? r.retrieval_metrics.reciprocal_rank : 1
  const judge = r.judge_scores
    ? (r.judge_scores.relevance + r.judge_scores.accuracy + r.judge_scores.groundedness) / 3
    : 1
  return (r.passed === false ? 0 : 4) + rr + judge
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border px-3 py-2.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-semibold text-foreground tabular-nums">{value}</p>
    </div>
  )
}

/** Boolean cell: icon + text label, status color never carries meaning alone. */
function FoundCell({ found }: { found: boolean | null }) {
  if (found === null) return <span className="text-muted-foreground">—</span>
  return found ? (
    <span className="flex items-center gap-1 text-status-success text-xs">
      <Check className="w-3.5 h-3.5" /> yes
    </span>
  ) : (
    <span className="flex items-center gap-1 text-status-error text-xs">
      <X className="w-3.5 h-3.5" /> no
    </span>
  )
}

interface RunReportCardProps {
  runId: string
  /** Bump to force a refetch (e.g., after a run-completed event). */
  refreshToken?: number
  onBack: () => void
  onError: (msg: string) => void
}

/**
 * Report card for one scorecard run: aggregate metric tiles, stale-question
 * warning, re-judge action for partial runs, and a worst-first per-question
 * table that drills down into retrieved docs and judged answers.
 */
export function RunReportCard({ runId, refreshToken, onBack, onError }: RunReportCardProps) {
  const { toast } = useToast()
  const [detail, setDetail] = useState<EvalRunDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [rejudging, setRejudging] = useState(false)
  const [drilldown, setDrilldown] = useState<EvalResult | null>(null)

  const fetchDetail = useCallback(async () => {
    try {
      setLoading(true)
      setDetail(await evaluationApi.getRun(runId))
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load scorecard run')
    } finally {
      setLoading(false)
    }
  }, [runId, onError])

  useEffect(() => { fetchDetail() }, [fetchDetail, refreshToken])

  const handleRejudge = async () => {
    try {
      setRejudging(true)
      await evaluationApi.rejudgeRun(runId)
      toast({
        title: 'Re-judge started',
        description: 'Unjudged answers are being re-scored in the background.',
      })
    } catch (err) {
      toast({
        title: 'Failed to start re-judge',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      })
    } finally {
      setRejudging(false)
    }
  }

  if (loading && !detail) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!detail) return null

  const m = detail.metrics_summary
  const sorted = [...detail.results].sort((a, b) => worstFirstKey(a) - worstFirstKey(b))
  const isAnswerRun = detail.run_type === 'answer'

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Button
            variant="ghost"
            size="sm"
            className="-ml-2 mb-1 text-muted-foreground hover:text-foreground"
            onClick={onBack}
          >
            <ArrowLeft className="w-4 h-4 mr-1.5" />
            Scorecards
          </Button>
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-lg font-semibold text-foreground truncate">{detail.target_label}</h2>
            <RunStatusChip status={detail.status} />
            <Badge variant="outline" className="text-xs text-muted-foreground">{detail.run_type}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {detail.question_set_name}
            {detail.started_at && ` · started ${new Date(detail.started_at).toLocaleString()}`}
          </p>
        </div>
        {detail.status === 'partial' && (
          <Button size="sm" variant="outline" onClick={handleRejudge} disabled={rejudging}>
            {rejudging ? (
              <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
            ) : (
              <Gavel className="w-4 h-4 mr-1.5" />
            )}
            Re-judge
          </Button>
        )}
      </div>

      {m && m.stale_questions > 0 && (
        <Alert>
          <AlertTriangle className="w-4 h-4 text-status-warning" />
          <AlertTitle>Stale questions excluded</AlertTitle>
          <AlertDescription>
            {m.stale_questions} question{m.stale_questions !== 1 ? 's' : ''} expected documents that
            no longer exist and {m.stale_questions !== 1 ? 'were' : 'was'} excluded from this run.
            Review them in the question set.
          </AlertDescription>
        </Alert>
      )}

      {m && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
          {m.scored_retrieval_count > 0 && (
            <>
              <MetricTile label="Found@5" value={formatRate(m.found_at_5_rate)} />
              <MetricTile label="Found@10" value={formatRate(m.found_at_10_rate)} />
              <MetricTile label="MRR" value={m.mrr !== null ? m.mrr.toFixed(2) : '—'} />
            </>
          )}
          {m.judged_count > 0 && (
            <MetricTile label="Passed" value={`${m.passed_count}/${m.judged_count}`} />
          )}
          {m.avg_judge_scores && (
            <>
              <MetricTile label="Relevance" value={m.avg_judge_scores.relevance.toFixed(2)} />
              <MetricTile label="Accuracy" value={m.avg_judge_scores.accuracy.toFixed(2)} />
              <MetricTile label="Groundedness" value={m.avg_judge_scores.groundedness.toFixed(2)} />
            </>
          )}
          <MetricTile label="Latency p50" value={formatMs(m.latency_p50_ms)} />
          <MetricTile label="Latency p95" value={formatMs(m.latency_p95_ms)} />
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Question</TableHead>
                <TableHead className="w-20">Found@5</TableHead>
                <TableHead className="w-20">Found@10</TableHead>
                <TableHead className="w-20 text-right">Best rank</TableHead>
                {isAnswerRun && <TableHead className="w-28">Judge R/A/G</TableHead>}
                {isAnswerRun && <TableHead className="w-20">Passed</TableHead>}
                <TableHead className="w-20 text-right">Latency</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.length === 0 && (
                <TableRow>
                  <TableCell colSpan={isAnswerRun ? 7 : 5} className="text-center text-muted-foreground py-8">
                    No results yet — the run may still be executing.
                  </TableCell>
                </TableRow>
              )}
              {sorted.map(r => (
                <TableRow
                  key={r.id}
                  className="cursor-pointer"
                  onClick={() => setDrilldown(r)}
                >
                  <TableCell className="max-w-0">
                    <span className="block truncate text-sm" title={r.question_text}>
                      {r.question_text}
                    </span>
                  </TableCell>
                  <TableCell><FoundCell found={r.retrieval_metrics?.found_at_5 ?? null} /></TableCell>
                  <TableCell><FoundCell found={r.retrieval_metrics?.found_at_10 ?? null} /></TableCell>
                  <TableCell className="text-right text-muted-foreground tabular-nums">
                    {r.retrieval_metrics ? r.retrieval_metrics.best_rank ?? '—' : '—'}
                  </TableCell>
                  {isAnswerRun && (
                    <TableCell className="text-xs text-muted-foreground tabular-nums">
                      {r.judge_scores
                        ? `${r.judge_scores.relevance.toFixed(1)} / ${r.judge_scores.accuracy.toFixed(1)} / ${r.judge_scores.groundedness.toFixed(1)}`
                        : 'unjudged'}
                    </TableCell>
                  )}
                  {isAnswerRun && (
                    <TableCell><FoundCell found={r.passed} /></TableCell>
                  )}
                  <TableCell className="text-right text-muted-foreground text-xs tabular-nums">
                    {r.latency_ms !== null ? `${r.latency_ms} ms` : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <ResultDrilldownDialog result={drilldown} onOpenChange={open => !open && setDrilldown(null)} />
    </div>
  )
}
