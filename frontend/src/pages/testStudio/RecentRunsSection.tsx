import { BarChart3, CheckCircle2, XCircle, Clock } from 'lucide-react'
import { TestRun } from '../../services/api'
import { ScoreBadge, StatusBadge } from '../../components/tests/badges'
import { Card, CardContent } from '@/components/ui/card'

interface RecentRunsSectionProps {
  runs: TestRun[]
}

export default function RecentRunsSection({ runs }: RecentRunsSectionProps) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-foreground">Recent Runs</h2>
          <BarChart3 className="w-5 h-5 text-muted-foreground" />
        </div>
        {runs.length === 0 ? (
          <p className="text-center py-4 text-muted-foreground">No runs yet</p>
        ) : (
          <div className="space-y-2">
            {runs.map(run => (
              <div
                key={run.id}
                className="flex items-center gap-4 p-3 border rounded-lg"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{run.model}</span>
                    <StatusBadge status={run.status} />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {run.provider} - {new Date(run.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-4 text-sm">
                  <div className="flex items-center gap-1">
                    <CheckCircle2 className="w-4 h-4 text-green-500" />
                    <span>{run.passed_cases}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <XCircle className="w-4 h-4 text-red-500" />
                    <span>{run.failed_cases}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Clock className="w-4 h-4 text-muted-foreground" />
                    <span>{run.total_cases}</span>
                  </div>
                </div>
                {run.retrieval_score !== null && run.retrieval_score !== undefined && (
                  <div className="flex flex-col items-center">
                    <span className="text-xs text-muted-foreground mb-0.5">retrieval</span>
                    <ScoreBadge score={run.retrieval_score} />
                  </div>
                )}
                <ScoreBadge score={run.overall_score} />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
