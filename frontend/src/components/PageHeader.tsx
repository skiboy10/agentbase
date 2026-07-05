import { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { HelpTooltip } from './HelpTooltip'

/**
 * Page header with title, description, and optional action button
 */
export interface PageHeaderProps {
  /** Page title */
  title: string
  /** Page description */
  description: string
  /** Optional action button configuration */
  action?: {
    label: string
    icon?: ReactNode
    onClick: () => void
  }
  /** Extra content rendered below the description (e.g., status badges, workflow hints) */
  extra?: ReactNode
  /** Help tooltip key from help.ts (e.g. 'sources.page') */
  helpKey?: string
}

export function PageHeader({ title, description, action, extra, helpKey }: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between mb-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground mb-2 flex items-center gap-2">
          {title}
          {helpKey && <HelpTooltip helpKey={helpKey} field="detail" />}
        </h1>
        <p className="text-muted-foreground">{description}</p>
        {extra && <div className="mt-2">{extra}</div>}
      </div>
      {action && (
        <Button onClick={action.onClick} className="shrink-0">
          {action.icon}
          {action.label}
        </Button>
      )}
    </div>
  )
}