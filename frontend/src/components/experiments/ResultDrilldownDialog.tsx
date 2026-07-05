import { Check, X } from 'lucide-react'
import type { EvalResult, RetrievedDoc } from '../../services/api/types/evaluation'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface ResultDrilldownDialogProps {
  /** Result to inspect; null keeps the dialog closed. */
  result: EvalResult | null
  onOpenChange: (open: boolean) => void
}

/** True when this retrieved doc satisfies the question's expectation. */
function isExpectedMatch(result: EvalResult, doc: RetrievedDoc, rank: number): boolean {
  if (result.expected_document_ids?.length) {
    return doc.document_id !== null && result.expected_document_ids.includes(doc.document_id)
  }
  // Fallback: without expected ids in the payload, highlight the best-rank hit
  return result.retrieval_metrics?.best_rank === rank
}

/**
 * Per-question drill-down: the question + expected criteria, retrieved docs in
 * rank order (expected matches highlighted with a labeled badge — never color
 * alone), and the judged answer + rationale when present.
 */
export function ResultDrilldownDialog({ result, onOpenChange }: ResultDrilldownDialogProps) {
  return (
    <Dialog open={!!result} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        {result && (
          <>
            <DialogHeader>
              <DialogTitle className="text-base pr-6">{result.question_text}</DialogTitle>
              {result.expected_criteria && (
                <DialogDescription>Expects: {result.expected_criteria}</DialogDescription>
              )}
            </DialogHeader>

            <div className="space-y-5">
              {/* Outcome summary */}
              <div className="flex items-center gap-2 flex-wrap text-sm">
                {result.passed !== null && (
                  result.passed ? (
                    <span className="flex items-center gap-1 text-status-success">
                      <Check className="w-4 h-4" /> passed
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-status-error">
                      <X className="w-4 h-4" /> failed
                    </span>
                  )
                )}
                {result.retrieval_metrics && (
                  <Badge variant="outline" className="text-xs text-muted-foreground">
                    best rank: {result.retrieval_metrics.best_rank ?? 'not found'}
                  </Badge>
                )}
                {result.latency_ms !== null && (
                  <Badge variant="outline" className="text-xs text-muted-foreground">
                    {result.latency_ms} ms
                  </Badge>
                )}
              </div>

              {/* Retrieved documents in rank order */}
              {result.retrieved && result.retrieved.length > 0 && (
                <section>
                  <h4 className="text-sm font-medium text-foreground mb-2">Retrieved documents</h4>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-12">Rank</TableHead>
                        <TableHead>Document</TableHead>
                        <TableHead className="w-20 text-right">Score</TableHead>
                        <TableHead className="w-24" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {result.retrieved.map((doc, i) => {
                        const rank = i + 1
                        const match = isExpectedMatch(result, doc, rank)
                        return (
                          <TableRow key={`${doc.document_id}-${rank}`} className={match ? 'bg-status-success/5' : undefined}>
                            <TableCell className="text-muted-foreground">{rank}</TableCell>
                            <TableCell className="max-w-0">
                              <span className="block truncate text-sm" title={doc.title ?? doc.document_id ?? undefined}>
                                {doc.title ?? doc.document_id ?? '(unresolved document)'}
                              </span>
                            </TableCell>
                            <TableCell className="text-right text-muted-foreground text-xs">
                              {doc.score !== null ? doc.score.toFixed(3) : '—'}
                            </TableCell>
                            <TableCell>
                              {match && (
                                <Badge variant="outline" className="text-xs text-status-success border-status-success/40">
                                  expected
                                </Badge>
                              )}
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </section>
              )}

              {/* Answer + judge verdict (answer runs only) */}
              {result.answer_text && (
                <section>
                  <h4 className="text-sm font-medium text-foreground mb-2">Answer</h4>
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap rounded-md border border-border bg-muted/30 p-3">
                    {result.answer_text}
                  </p>
                </section>
              )}

              {result.judge_scores && (
                <section>
                  <h4 className="text-sm font-medium text-foreground mb-2">Judge scores</h4>
                  <div className="flex items-center gap-2 flex-wrap">
                    {(['relevance', 'accuracy', 'groundedness'] as const).map(dim => (
                      <Badge key={dim} variant="outline" className="text-xs text-muted-foreground">
                        {dim}: {result.judge_scores![dim].toFixed(2)}
                      </Badge>
                    ))}
                  </div>
                  {result.judge_rationale && (
                    <p className="text-sm text-muted-foreground mt-2">{result.judge_rationale}</p>
                  )}
                </section>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
