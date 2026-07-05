import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import type { LibrarySearchResult } from '../../../services/api/types/library'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'

const PREVIEW_LENGTH = 300
const EXCLUDED_META_KEYS = ['source', 'document_type', 'chunk_index', 'content_hash', 'file_id', 'source_id']

function ScoreBar({ score, rerankScore }: { score: number; rerankScore?: number | null }) {
  const pct = Math.round(score * 100)
  const color = pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-muted-foreground/40'

  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <div className="w-14 h-1.5 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted-foreground font-mono">
        {pct}%
        {rerankScore != null && (
          <span className="text-emerald-400"> → {Math.round(rerankScore * 100)}%</span>
        )}
      </span>
    </div>
  )
}

interface ResultCardProps {
  result: LibrarySearchResult
  rank: number
}

export default function ResultCard({ result, rank }: ResultCardProps) {
  const [expanded, setExpanded] = useState(false)
  const needsTruncation = result.content.length > PREVIEW_LENGTH

  const displayContent = expanded
    ? result.content
    : result.content.slice(0, PREVIEW_LENGTH) + (needsTruncation ? '...' : '')

  const metaEntries = Object.entries(result.metadata)
    .filter(([k]) => !EXCLUDED_META_KEYS.includes(k))
    .filter(([, v]) => v != null && v !== '' && !(Array.isArray(v) && v.length === 0))
    .slice(0, 5)

  return (
    <Card className="border-border/60">
      <CardContent className="py-3 px-4">
        {/* Header: rank + source + score */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 min-w-0">
            <Badge variant="outline" className="text-xs font-mono shrink-0">
              #{rank}
            </Badge>
            <span className="text-xs text-muted-foreground truncate" title={result.source}>
              {result.document_path || result.source}
            </span>
            {!!result.metadata?.document_type && (
              <Badge variant="secondary" className="text-xs shrink-0">
                {String(result.metadata.document_type)}
              </Badge>
            )}
          </div>
          <ScoreBar score={result.score} rerankScore={result.rerank_score} />
        </div>

        <Separator className="mb-2 opacity-30" />

        {/* Content */}
        <p className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
          {displayContent}
        </p>

        {needsTruncation && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs text-muted-foreground mt-1"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? (
              <>
                <ChevronUp className="w-3 h-3 mr-1" />
                Show less
              </>
            ) : (
              <>
                <ChevronDown className="w-3 h-3 mr-1" />
                Show more
              </>
            )}
          </Button>
        )}

        {/* Metadata tags */}
        {metaEntries.length > 0 && (
          <div className="flex items-center gap-1.5 mt-2 flex-wrap">
            {metaEntries.map(([k, v]) => (
              <Badge
                key={k}
                variant="outline"
                className="text-[10px] py-0 h-4 text-muted-foreground/70 border-border/50"
              >
                {k}: {Array.isArray(v) ? v.join(', ') : String(v)}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
