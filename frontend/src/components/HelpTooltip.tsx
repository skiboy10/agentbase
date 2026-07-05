import { HelpCircle } from 'lucide-react'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { getHelp } from '@/content/help'
import { cn } from '@/lib/utils'

export interface HelpTooltipProps {
  /** Dot-path key into help.ts, e.g. 'sources.page' */
  helpKey?: string
  /** Override tooltip text directly */
  text?: string
  /** Which field to display from help entry */
  field?: 'summary' | 'detail'
  /** Tooltip placement */
  side?: 'top' | 'right' | 'bottom' | 'left'
  /** Extra classes on the icon */
  className?: string
}

export function HelpTooltip({
  helpKey,
  text,
  field = 'summary',
  side = 'right',
  className,
}: HelpTooltipProps) {
  const content = text ?? (helpKey ? getHelp(helpKey)?.[field] : undefined)
  if (!content) return null

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label="Help"
          className="inline-flex items-center"
        >
          <HelpCircle
            className={cn(
              'w-4 h-4 text-muted-foreground hover:text-foreground cursor-help transition-colors',
              className
            )}
          />
        </button>
      </TooltipTrigger>
      <TooltipContent side={side} className="max-w-xs">
        <p className="text-sm">{content}</p>
      </TooltipContent>
    </Tooltip>
  )
}
