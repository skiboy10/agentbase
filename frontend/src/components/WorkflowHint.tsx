import { Link, useLocation } from 'react-router-dom'
import { Cloud, Database, Tags, Library, Bot, ArrowRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { help } from '@/content/help'
import type { LucideIcon } from 'lucide-react'

const stepIcons: Record<string, LucideIcon> = {
  providers: Cloud,
  sources: Database,
  taxonomy: Tags,
  libraries: Library,
  agents: Bot,
}

export interface WorkflowHintProps {
  /** Override auto-detected active step */
  activeStep?: string
  className?: string
}

export function WorkflowHint({ activeStep, className }: WorkflowHintProps) {
  const location = useLocation()
  const current = activeStep ?? location.pathname.split('/')[1] ?? ''

  return (
    <div className={cn('flex items-center gap-1 text-xs text-muted-foreground', className)}>
      {help.workflow.steps.map((step, i) => {
        const Icon = stepIcons[step.key]
        const isActive = current === step.key
        return (
          <span key={step.key} className="flex items-center gap-1">
            {i > 0 && <ArrowRight className="w-3 h-3 text-muted-foreground/40 shrink-0" />}
            <Link
              to={step.href}
              className={cn(
                'flex items-center gap-1 px-2 py-1 rounded transition-colors whitespace-nowrap',
                isActive
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'hover:text-foreground hover:bg-muted',
              )}
            >
              {Icon && <Icon className="w-3 h-3" />}
              <span>{step.label}</span>
            </Link>
          </span>
        )
      })}
    </div>
  )
}
