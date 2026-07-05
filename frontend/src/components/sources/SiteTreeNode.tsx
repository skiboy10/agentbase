import { ChevronRight, ChevronDown, Globe } from 'lucide-react'
import { cn } from '../../lib/utils'
import { SiteTreeNode as SiteTreeNodeType } from '../../services/api'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'

interface SiteTreeNodeProps {
  node: SiteTreeNodeType
  selected: Set<string>
  expanded: Set<string>
  onToggle: (url: string) => void
  onExpand: (url: string) => void
  depth: number
}

export default function SiteTreeNode({
  node,
  selected,
  expanded,
  onToggle,
  onExpand,
  depth,
}: SiteTreeNodeProps) {
  const hasChildren = node.children && node.children.length > 0
  const isExpanded = expanded.has(node.url)
  const isSelected = selected.has(node.url)

  return (
    <div className="select-none">
      <div
        className={cn(
          'flex items-center gap-2 py-1.5 px-2 rounded hover:bg-muted/50 cursor-pointer',
          isSelected && 'bg-primary/20'
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        {hasChildren ? (
          <Button
            variant="ghost"
            size="icon"
            className="w-5 h-5"
            onClick={(e) => {
              e.stopPropagation()
              onExpand(node.url)
            }}
          >
            {isExpanded ? (
              <ChevronDown className="w-4 h-4" />
            ) : (
              <ChevronRight className="w-4 h-4" />
            )}
          </Button>
        ) : (
          <div className="w-5 h-5" />
        )}
        <Checkbox
          checked={isSelected}
          onCheckedChange={() => onToggle(node.url)}
        />
        <Globe className="w-4 h-4 text-muted-foreground flex-shrink-0" />
        <span className="text-sm text-foreground truncate flex-1" title={node.url}>
          {node.title || node.path || node.url}
        </span>
      </div>
      {hasChildren && isExpanded && (
        <div>
          {node.children.map((child) => (
            <SiteTreeNode
              key={child.url}
              node={child}
              selected={selected}
              expanded={expanded}
              onToggle={onToggle}
              onExpand={onExpand}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}
