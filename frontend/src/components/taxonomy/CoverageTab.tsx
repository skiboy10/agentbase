import { useState, useEffect, useCallback } from 'react'
import { Loader2, BarChart3, RefreshCw, AlertCircle } from 'lucide-react'
import { taxonomyApi } from '../../services/api/taxonomy'
import type { TaxonomyCoverage } from '../../services/api/types/taxonomy'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { HelpTooltip } from '@/components/HelpTooltip'

function pct(n: number) {
  return `${Math.round(n)}%`
}

interface CoverageTabProps {
  taxonomyId: string
}

export function CoverageTab({ taxonomyId }: CoverageTabProps) {
  const [report, setReport] = useState<TaxonomyCoverage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [staleCount, setStaleCount] = useState<number>(0)

  const fetchCoverage = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [data, stale] = await Promise.all([
        taxonomyApi.getCoverage(taxonomyId),
        taxonomyApi.countStale(taxonomyId).catch(() => ({ count: 0 })),
      ])
      setReport(data)
      setStaleCount(stale.count)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load coverage')
    } finally {
      setLoading(false)
    }
  }, [taxonomyId])

  useEffect(() => { fetchCoverage() }, [fetchCoverage])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="py-6 text-center">
        <p className="text-sm text-destructive">{error}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={fetchCoverage}>
          Retry
        </Button>
      </div>
    )
  }

  if (!report) return null

  // Flatten term_usage for top terms chart
  const allTerms: Array<{ facet: string; value: string; count: number }> = []
  if (report.term_usage) {
    for (const [facet, terms] of Object.entries(report.term_usage)) {
      for (const term of terms) {
        allTerms.push({ facet, value: term.value, count: term.count })
      }
    }
  }
  allTerms.sort((a, b) => b.count - a.count)
  const topTerms = allTerms.slice(0, 20)
  const maxTermDocs = topTerms.length > 0 ? topTerms[0].count : 1

  return (
    <div className="mt-4 space-y-6">
      {/* Overall coverage */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Overall Coverage
            <HelpTooltip helpKey="taxonomy.coverage" side="right" />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-end gap-3 mb-3">
            <span className="text-4xl font-bold text-foreground">
              {pct(report.coverage_percent)}
            </span>
            <span className="text-sm text-muted-foreground mb-1">
              {report.classified_documents.toLocaleString()} / {report.total_documents.toLocaleString()} documents classified
            </span>
          </div>
          <Progress value={report.coverage_percent} className="h-3" />
        </CardContent>
      </Card>

      {/* Per-facet coverage */}
      {report.facet_coverage && Object.keys(report.facet_coverage).length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              Coverage by Facet
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {Object.entries(report.facet_coverage).map(([facetName, facetData]) => (
                <div key={facetName}>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm font-medium text-foreground capitalize">{facetName}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {facetData.covered} / {facetData.total}
                      </span>
                      <span className="text-sm font-semibold text-foreground w-10 text-right">
                        {pct(facetData.percent)}
                      </span>
                    </div>
                  </div>
                  <Progress value={facetData.percent} className="h-2" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Top terms by document count */}
      {topTerms.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-muted-foreground" />
              <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                Top Terms by Document Count
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2.5">
              {topTerms.map((term, i) => (
                <div key={`${term.facet}-${term.value}-${i}`} className="flex items-center gap-3">
                  <Badge
                    variant="outline"
                    className="text-xs shrink-0 w-24 justify-center"
                  >
                    {term.facet}
                  </Badge>
                  <span className="text-sm text-foreground w-32 truncate shrink-0">
                    {term.value}
                  </span>
                  <div className="flex-1 flex items-center gap-2">
                    <div
                      className="h-2 rounded-full bg-primary/60 transition-all"
                      style={{ width: `${(term.count / maxTermDocs) * 100}%` }}
                    />
                    <span className="text-xs text-muted-foreground shrink-0">
                      {term.count.toLocaleString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stale documents */}
      <Card>
        <CardContent className="py-4">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-medium text-foreground">Stale documents</span>
                  <HelpTooltip helpKey="taxonomy.staleDocs" side="right" />
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Documents classified with an older taxonomy version
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <Badge variant={staleCount > 0 ? 'destructive' : 'secondary'} className="text-sm">
                {staleCount}
              </Badge>
              <Button
                size="sm"
                variant="outline"
                disabled={staleCount === 0}
                onClick={fetchCoverage}
              >
                <RefreshCw className="w-4 h-4 mr-1.5" />
                Refresh
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
