import { Tags, Hash, MoreVertical, Eye, Pencil, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Taxonomy } from '../../services/api/types/taxonomy'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

interface TaxonomyCardProps {
  taxonomy: Taxonomy
  onViewDetails: (taxonomy: Taxonomy) => void
  onEdit: (taxonomy: Taxonomy) => void
  onDelete: (taxonomy: Taxonomy) => void
  isDeleting?: boolean
}

export function TaxonomyCard({
  taxonomy,
  onViewDetails,
  onEdit,
  onDelete,
  isDeleting = false,
}: TaxonomyCardProps) {
  return (
    <Card
      className={cn(
        'cursor-pointer transition-colors hover:bg-accent/30 border-border',
        isDeleting && 'opacity-50 pointer-events-none'
      )}
      onClick={() => onViewDetails(taxonomy)}
    >
      <CardContent className="pt-4">
        <div className="flex items-start justify-between gap-4">
          {/* Icon + main info */}
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-violet-900/60 flex items-center justify-center shrink-0 mt-0.5">
              <Tags className="w-4 h-4 text-violet-300" />
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-foreground truncate">{taxonomy.name}</h3>
              {taxonomy.description && (
                <p className="text-sm text-muted-foreground mt-0.5 line-clamp-2">
                  {taxonomy.description}
                </p>
              )}
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                <Badge variant="secondary" className="text-xs gap-1">
                  <Hash className="w-3 h-3" />
                  {taxonomy.term_count} terms
                </Badge>
                <Badge
                  variant="outline"
                  className="text-xs font-mono text-violet-400 border-violet-400/40"
                >
                  v{taxonomy.version}
                </Badge>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div
            className="shrink-0"
            onClick={(e) => e.stopPropagation()}
          >
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <MoreVertical className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onViewDetails(taxonomy)}>
                  <Eye className="w-4 h-4 mr-2" />
                  View Details
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => onEdit(taxonomy)}>
                  <Pencil className="w-4 h-4 mr-2" />
                  Edit
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => onDelete(taxonomy)}
                  className="text-destructive focus:text-destructive"
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
