import { ReactNode } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { HelpTooltip } from '@/components/HelpTooltip'

/**
 * Individual stat configuration
 */
export interface Stat {
  /** Stat value (number or string) */
  value: string | number
  /** Stat label */
  label: string
  /** Optional icon to display */
  icon?: ReactNode
  /** Optional help tooltip key (dot-path into help.ts) */
  helpKey?: string
}

/**
 * Grid of stat cards for displaying key metrics
 */
export interface StatsGridProps {
  /** Array of stats to display */
  stats: Stat[]
  /** Number of columns (2, 3, or 4) */
  columns?: 2 | 3 | 4
}

export function StatsGrid({ stats, columns = 3 }: StatsGridProps) {
  const gridCols = {
    2: 'grid-cols-2',
    3: 'grid-cols-3',
    4: 'grid-cols-4',
  }

  return (
    <div className={`grid ${gridCols[columns]} gap-4 mb-8`}>
      {stats.map((stat, index) => (
        <Card key={index}>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2">
              {stat.icon}
              <div className="text-2xl font-bold text-foreground">{stat.value}</div>
            </div>
            <div className="flex items-center gap-1 text-sm text-muted-foreground">
              {stat.label}
              {stat.helpKey && <HelpTooltip helpKey={stat.helpKey} side="right" />}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}