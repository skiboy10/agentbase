import { ReactNode } from 'react'
import { Button } from '@/components/ui/button'

/**
 * Empty state display for when no items exist
 */
export interface EmptyStateProps {
  /** Icon to display (should be a lucide-react icon) */
  icon: ReactNode
  /** Title text */
  title: string
  /** Description text */
  description: string
  /** Optional action button */
  action?: {
    label: string
    onClick: () => void
  }
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="text-center py-12">
      <div className="w-16 h-16 text-muted-foreground/50 mx-auto mb-4 flex items-center justify-center">
        {icon}
      </div>
      <h3 className="text-xl font-semibold text-muted-foreground mb-2">{title}</h3>
      <p className="text-muted-foreground/70 mb-4">{description}</p>
      {action && <Button onClick={action.onClick}>{action.label}</Button>}
    </div>
  )
}