import { useState, useEffect, useCallback } from 'react'
import { Loader2, BarChart3 } from 'lucide-react'
import { taxonomyApi } from '../../../services/api/taxonomy'
import type { TaxonomyCoverage } from '../../../services/api/types/taxonomy'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

function pct(n: number) {
  return `${Math.round(n)}%`
}

interface CoverageCardProps {
  taxonomyId: string
}

export function CoverageCard({ taxonomyId }: CoverageCardProps) {
  const [report, setReport] = useState<TaxonomyCoverage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchCoverage = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await taxonomyApi.getCoverage(taxonomyId)
      setReport(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load coverage')
    } finally {
      setLoading(false)
    }
  }, [taxonomyId])

  useEffect(() => { fetchCoverage() }, [fetchCoverage])

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-10">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-6 text-center">
          <p className="text-sm text-destructive mb-3">{error}</p>
          <Button variant="outline" size="sm" onClick={fetchCoverage}>
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }

  if (!report) return null

  const facetEntries = report.facet_coverage ? Object.entries(report.facet_coverage) : []

  return (
    <div className="space-y-4">
      {/* Overall stat */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Overall Coverage
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
          {report.unclassified_documents > 0 && (
            <p className="text-xs text-muted-foreground mt-2">
              {report.unclassified_documents.toLocaleString()} unclassified
            </p>
          )}
        </CardContent>
      </Card>

      {/* Per-facet breakdown */}
      {facetEntries.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-muted-foreground" />
              <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                Coverage by Facet
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground border-b border-border">
                  <th className="text-left pb-2 font-medium">Facet</th>
                  <th className="text-right pb-2 font-medium">Covered</th>
                  <th className="text-right pb-2 font-medium">Total</th>
                  <th className="text-right pb-2 font-medium w-16">%</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {facetEntries.map(([facetName, facetData]) => (
                  <tr key={facetName}>
                    <td className="py-2.5">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs capitalize">
                          {facetName}
                        </Badge>
                      </div>
                    </td>
                    <td className="py-2.5 text-right text-foreground">
                      {facetData.covered.toLocaleString()}
                    </td>
                    <td className="py-2.5 text-right text-muted-foreground">
                      {facetData.total.toLocaleString()}
                    </td>
                    <td className="py-2.5 text-right font-semibold text-foreground">
                      {pct(facetData.percent)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
