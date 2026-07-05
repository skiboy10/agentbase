import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, Radio, RefreshCw, Loader2 } from 'lucide-react'
import type { Source } from '../services/api/types/sources'
import { EditSourceDialog } from '../components/sources'
import { AutomationSummary, AutomationsTable } from '../components/automations'
import { useAutomations } from '../hooks/useAutomations'
import type { Automation } from '../lib/automations'
import { PageHeader, ErrorBanner, EmptyState } from '@/components'
import { TooltipProvider } from '@/components/ui/tooltip'

interface ConfigureTarget {
  source: Source
  focusWatcher: boolean
}

export default function AutomationsPage() {
  const {
    automations,
    summary,
    watcherStatuses,
    loading,
    error,
    pendingIds,
    togglePause,
    runNow,
    refetch,
  } = useAutomations()

  const navigate = useNavigate()
  const [configure, setConfigure] = useState<ConfigureTarget | null>(null)
  const [dialogError, setDialogError] = useState<string | null>(null)

  const watchers = automations.filter((a) => a.kind === 'watcher')
  const refreshes = automations.filter((a) => a.kind === 'refresh')

  const handleConfigure = (automation: Automation) => {
    setConfigure({ source: automation.source, focusWatcher: automation.kind === 'watcher' })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </div>
    )
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        <ErrorBanner error={error || dialogError} onDismiss={() => setDialogError(null)} />

        <PageHeader
          title="Automations"
          description="Every folder watcher and auto-refresh schedule in one place — pause, resume, or run them on demand"
        />

        <AutomationSummary summary={summary} />

        {automations.length === 0 ? (
          <EmptyState
            icon={<Activity className="w-8 h-8" />}
            title="No automations yet"
            description="Enable a folder watcher on a directory source, or set a source to refresh automatically, and it will appear here."
            action={{ label: 'Go to Sources', onClick: () => navigate('/sources') }}
          />
        ) : (
          <TooltipProvider delayDuration={300}>
            <AutomationsTable
              title="Folder Watchers"
              icon={Radio}
              automations={watchers}
              watcherStatuses={watcherStatuses}
              pendingIds={pendingIds}
              onTogglePause={togglePause}
              onRunNow={runNow}
              onConfigure={handleConfigure}
            />
            <AutomationsTable
              title="Auto-Refresh"
              icon={RefreshCw}
              automations={refreshes}
              watcherStatuses={watcherStatuses}
              pendingIds={pendingIds}
              onTogglePause={togglePause}
              onRunNow={runNow}
              onConfigure={handleConfigure}
            />
          </TooltipProvider>
        )}

        <EditSourceDialog
          source={configure?.source ?? null}
          initialFocus={configure?.focusWatcher ? 'watcher' : undefined}
          onClose={() => setConfigure(null)}
          onSaved={() => {
            setConfigure(null)
            void refetch()
          }}
          onError={setDialogError}
        />
      </div>
    </div>
  )
}
