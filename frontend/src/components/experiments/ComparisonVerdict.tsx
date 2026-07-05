import { useState, useEffect, useCallback } from 'react'
import { ArrowLeft, CircleSlash, Loader2, Minus, TrendingDown, TrendingUp } from 'lucide-react'
import { evaluationApi } from '../../services/api/evaluation'
import type {
  ComparisonQuestion,
  ComparisonQuestionSide,
  ComparisonQuestionVerdict,
  ComparisonReport,
  EvalResult,
  EvalRunDetail,
} from '../../services/api/types/evaluation'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
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

/** Icon + token + sort weight per verdict — color never carries meaning alone. */
const VERDICT_CONFIG: Record<
  ComparisonQuestionVerdict,
  { icon: typeof TrendingUp; className: string; order: number }
> = {
  regressed: { icon: TrendingDown, className: 'text-status-error', order: 0 },
  uncomparable: { icon: CircleSlash, className: 'text-status-warning', order: 1 },
  unchanged: { icon: Minus, className: 'text-muted-foreground', order: 2 },
  improved: { icon: TrendingUp, className: 'text-status-success', order: 3 },
}

/** Mean of the available judge dimensions; null when the side is unjudged. */
function judgeMean(side: ComparisonQuestionSide | null): number | null {
  const scores = side?.judge_scores
  if (!scores) return null
  const values = [scores.relevance, scores.accuracy, scores.groundedness].filter(
    (v): v is number => v !== null && v !== undefined
  )
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null
}

function VerdictLabel({ verdict }: { verdict: ComparisonQuestionVerdict }) {
  const config = VERDICT_CONFIG[verdict] ?? VERDICT_CONFIG.unchanged
  const Icon = config.icon
  return (
    <span className={`flex items-center gap-1 text-xs ${config.className}`}>
      <Icon className="w-3.5 h-3.5" /> {verdict}
    </span>
  )
}

/** Signed delta tile: "+" / "−" sign and status color together, em dash when unscored. */
function DeltaTile({
  label,
  delta,
  format,
  lowerIsBetter = false,
}: {
  label: string
  delta: number | null | undefined
  format: (n: number) => string
  lowerIsBetter?: boolean
}) {
  if (delta === null || delta === undefined) {
    return (
      <div className="rounded-md border border-border px-3 py-2.5">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-xl font-semibold text-muted-foreground">—</p>
      </div>
    )
  }
  const improved = lowerIsBetter ? delta < 0 : delta > 0
  const className =
    delta === 0
      ? 'text-foreground'
      : improved
        ? 'text-status-success'
        : 'text-status-error'
  const sign = delta > 0 ? '+' : delta < 0 ? '−' : '±'
  return (
    <div className="rounded-md border border-border px-3 py-2.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`text-xl font-semibold tabular-nums ${className}`}>
        {sign}{format(Math.abs(delta))}
      </p>
    </div>
  )
}

/** "baseline → experiment" cell for a per-question number; em dashes for missing sides. */
function TransitionCell({
  baseline,
  experiment,
  format,
}: {
  baseline: number | null | undefined
  experiment: number | null | undefined
  format: (n: number) => string
}) {
  const fmt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : format(v))
  return (
    <span className="tabular-nums text-sm text-muted-foreground">
      {fmt(baseline)} <span className="text-muted-foreground/50">→</span>{' '}
      <span className="text-foreground">{fmt(experiment)}</span>
    </span>
  )
}

const RUN_DONE_STATUSES = new Set(['completed', 'partial'])

interface ComparisonVerdictProps {
  experimentId: string
  experimentName: string
  baselineRunId: string
  experimentRunId: string
  /** Bump to refetch (e.g., on evaluation.run_completed SSE for either run). */
  refreshToken?: number
  onBack: () => void
  onError: (msg: string) => void
}

/**
 * Baseline-vs-experiment verdict view. Shows a "Comparing..." state while the
 * two scorecard runs execute, then the aggregate verdict banner, metric-delta
 * tiles, and a regressions-first per-question table with side drill-downs.
 */
export function ComparisonVerdict({
  experimentId,
  experimentName,
  baselineRunId,
  experimentRunId,
  refreshToken,
  onBack,
  onError,
}: ComparisonVerdictProps) {
  const [baselineRun, setBaselineRun] = useState<EvalRunDetail | null>(null)
  const [experimentRun, setExperimentRun] = useState<EvalRunDetail | null>(null)
  const [report, setReport] = useState<ComparisonReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [drilldown, setDrilldown] = useState<EvalResult | null>(null)

  const fetchAll = useCallback(async () => {
    try {
      const [baseline, experiment] = await Promise.all([
        evaluationApi.getRun(baselineRunId),
        evaluationApi.getRun(experimentRunId),
      ])
      setBaselineRun(baseline)
      setExperimentRun(experiment)
      if (RUN_DONE_STATUSES.has(baseline.status) && RUN_DONE_STATUSES.has(experiment.status)) {
        setReport(await evaluationApi.getComparison(experimentId, baselineRunId, experimentRunId))
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load comparison')
    } finally {
      setLoading(false)
    }
  }, [experimentId, baselineRunId, experimentRunId, onError])

  useEffect(() => { fetchAll() }, [fetchAll, refreshToken])

  const header = (
    <div className="min-w-0">
      <Button
        variant="ghost"
        size="sm"
        className="-ml-2 mb-1 text-muted-foreground hover:text-foreground"
        onClick={onBack}
      >
        <ArrowLeft className="w-4 h-4 mr-1.5" />
        Experiments
      </Button>
      <h2 className="text-lg font-semibold text-foreground truncate">
        {experimentName} <span className="text-muted-foreground font-normal">vs. baseline</span>
      </h2>
      {baselineRun && (
        <p className="text-sm text-muted-foreground">{baselineRun.question_set_name}</p>
      )}
    </div>
  )

  if (loading && !baselineRun) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const failedRun =
    baselineRun?.status === 'error' || experimentRun?.status === 'error'

  // Comparing state: one or both runs still executing
  if (!report) {
    return (
      <div className="space-y-5">
        {header}
        {failedRun ? (
          <Alert variant="destructive">
            <AlertTitle>Comparison run failed</AlertTitle>
            <AlertDescription>
              One of the scorecard runs hit an error — inspect it on the Scorecards tab,
              then start a new comparison.
            </AlertDescription>
          </Alert>
        ) : (
          <Card>
            <CardContent className="py-10 text-center space-y-3">
              <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                Comparing... both scorecard runs execute in the background.
              </p>
              <div className="flex items-center justify-center gap-4 text-sm text-muted-foreground">
                <span className="flex items-center gap-2">
                  baseline {baselineRun && <RunStatusChip status={baselineRun.status} />}
                </span>
                <span className="flex items-center gap-2">
                  experiment {experimentRun && <RunStatusChip status={experimentRun.status} />}
                </span>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    )
  }

  const counts = report.verdict_counts
  const deltas = report.metric_deltas
  const sorted = [...report.per_question].sort(
    (a, b) =>
      (VERDICT_CONFIG[a.verdict]?.order ?? 2) - (VERDICT_CONFIG[b.verdict]?.order ?? 2)
  )

  const openDrilldown = (q: ComparisonQuestion, side: 'baseline' | 'experiment') => {
    const run = side === 'baseline' ? baselineRun : experimentRun
    const result = run?.results.find(r => r.question_id === q.question_id) ?? null
    if (result) setDrilldown(result)
  }

  return (
    <div className="space-y-5">
      {header}

      {/* Aggregate verdict banner */}
      <Card>
        <CardContent className="py-4 px-4">
          <div className="flex items-center gap-5 flex-wrap text-sm font-medium">
            <span className="flex items-center gap-1.5 text-status-success">
              <TrendingUp className="w-4 h-4" /> {counts.improved} improved
            </span>
            <span className="text-muted-foreground/40">·</span>
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <Minus className="w-4 h-4" /> {counts.unchanged} unchanged
            </span>
            <span className="text-muted-foreground/40">·</span>
            <span className="flex items-center gap-1.5 text-status-error">
              <TrendingDown className="w-4 h-4" /> {counts.regressed} regressed
            </span>
          </div>
          {report.uncomparable > 0 && (
            <p className="text-xs text-muted-foreground mt-2">
              {report.uncomparable} question{report.uncomparable !== 1 ? 's' : ''} appeared in only
              one run and {report.uncomparable !== 1 ? 'were' : 'was'} excluded from the verdict.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Metric deltas (experiment − baseline) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
        <DeltaTile label="Δ Found@5" delta={deltas.found_at_5_rate} format={n => `${Math.round(n * 100)}%`} />
        <DeltaTile label="Δ Found@10" delta={deltas.found_at_10_rate} format={n => `${Math.round(n * 100)}%`} />
        <DeltaTile label="Δ MRR" delta={deltas.mrr} format={n => n.toFixed(2)} />
        <DeltaTile label="Δ Relevance" delta={deltas.avg_judge_scores?.relevance} format={n => n.toFixed(2)} />
        <DeltaTile label="Δ Accuracy" delta={deltas.avg_judge_scores?.accuracy} format={n => n.toFixed(2)} />
        <DeltaTile label="Δ Groundedness" delta={deltas.avg_judge_scores?.groundedness} format={n => n.toFixed(2)} />
        <DeltaTile
          label="Δ Latency p50"
          delta={deltas.latency_p50_ms}
          format={n => `${Math.round(n)} ms`}
          lowerIsBetter
        />
      </div>

      {/* Per-question verdicts, regressions first */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-28">Verdict</TableHead>
                <TableHead>Question</TableHead>
                <TableHead className="w-32">Judge mean</TableHead>
                <TableHead className="w-24">Best rank</TableHead>
                <TableHead className="w-36">Inspect</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                    No comparable questions between the two runs.
                  </TableCell>
                </TableRow>
              )}
              {sorted.map(q => (
                <TableRow key={q.question_id}>
                  <TableCell><VerdictLabel verdict={q.verdict} /></TableCell>
                  <TableCell className="max-w-0">
                    <span className="block truncate text-sm" title={q.question_text ?? undefined}>
                      {q.question_text}
                    </span>
                  </TableCell>
                  <TableCell>
                    <TransitionCell
                      baseline={judgeMean(q.baseline)}
                      experiment={judgeMean(q.experiment)}
                      format={n => n.toFixed(2)}
                    />
                  </TableCell>
                  <TableCell>
                    <TransitionCell
                      baseline={q.baseline?.retrieval_metrics?.best_rank}
                      experiment={q.experiment?.retrieval_metrics?.best_rank}
                      format={n => String(n)}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-xs text-muted-foreground"
                        onClick={() => openDrilldown(q, 'baseline')}
                      >
                        baseline
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-xs text-muted-foreground"
                        onClick={() => openDrilldown(q, 'experiment')}
                      >
                        experiment
                      </Button>
                    </div>
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
