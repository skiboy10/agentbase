import { FileSearch } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { SearchResult } from '../../services/api/types/sources'

interface SearchResultCardProps {
  result: SearchResult
  rank: number
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen).trimEnd() + '...'
}

function formatScore(score: number): string {
  return `${Math.round(score * 100)}%`
}

function extractClassificationTags(
  meta: Record<string, unknown>
): { label: string; value: string }[] {
  const tags: { label: string; value: string }[] = []

  // Only show classification badges when a dedicated `classification` object exists.
  // Falling back to all root metadata fields would expose noisy internal fields
  // (file paths, chunk IDs, embedding vectors, etc.) as visible badges.
  const classification = meta.classification
  if (!classification || typeof classification !== 'object' || Array.isArray(classification)) {
    return tags
  }

  for (const [key, val] of Object.entries(classification as Record<string, unknown>)) {
    if (val && typeof val === 'string') {
      tags.push({ label: key, value: val })
    } else if (Array.isArray(val)) {
      for (const item of val) {
        if (typeof item === 'string') {
          tags.push({ label: key, value: item })
        }
      }
    }
  }

  return tags
}

export default function SearchResultCard({ result, rank }: SearchResultCardProps) {
  const meta = result.metadata
  const classificationTags = extractClassificationTags(meta)

  return (
    <Card className="border-border/60">
      <CardContent className="pt-4">
        <div className="flex items-start gap-3">
          {/* Rank indicator */}
          <div className="flex-shrink-0 w-7 h-7 rounded-full bg-muted flex items-center justify-center text-xs font-mono text-muted-foreground">
            {rank}
          </div>

          <div className="flex-1 min-w-0">
            {/* Content preview */}
            <p className="text-sm text-foreground leading-relaxed">
              {truncate(result.content, 220)}
            </p>

            {/* Source + score row */}
            <div className="flex items-center gap-3 mt-2">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground min-w-0">
                <FileSearch className="w-3 h-3 flex-shrink-0" />
                <span className="truncate font-mono">{result.source}</span>
              </div>
              <Badge
                variant="outline"
                className="text-xs font-mono text-emerald-400 border-emerald-400/50 flex-shrink-0"
              >
                {formatScore(result.score)}
              </Badge>
            </div>

            {/* Classification tags */}
            {classificationTags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {classificationTags.map((tag, i) => (
                  <Badge key={i} variant="secondary" className="text-xs">
                    {tag.value}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
