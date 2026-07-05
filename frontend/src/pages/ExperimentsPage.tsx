import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Library as LibraryIcon, Loader2 } from 'lucide-react'
import { libraryApi } from '../services/api/library'
import type { Library } from '../services/api/types/library'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ErrorBanner, PageHeader } from '../components'
import { ExperimentsTab, QuestionSetsTab, ScorecardsTab } from '../components/experiments'

const TABS = ['question-sets', 'scorecards', 'experiments'] as const
type TabValue = (typeof TABS)[number]

function parseTab(raw: string | null): TabValue {
  return TABS.includes(raw as TabValue) ? (raw as TabValue) : 'question-sets'
}

export default function ExperimentsPage() {
  // Library + tab state live in the URL so views are shareable and survive
  // refresh / back-forward navigation (docs/recipes/url-filter-persistence.md)
  const [searchParams, setSearchParams] = useSearchParams()
  const libraryId = searchParams.get('library_id') ?? ''
  const tab = parseTab(searchParams.get('tab'))

  const [libraries, setLibraries] = useState<Library[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const setParam = useCallback(
    (key: string, value: string | null) => {
      setSearchParams(
        prev => {
          const params = new URLSearchParams(prev)
          if (value) params.set(key, value)
          else params.delete(key)
          return params
        },
        { replace: true }
      )
    },
    [setSearchParams]
  )

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    libraryApi
      .list()
      .then(data => { if (!cancelled) setLibraries(data) })
      .catch(err => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load libraries')
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const selectedLibrary = libraries.find(lib => lib.id === libraryId) ?? null

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto">
        <PageHeader
          title="Experiments"
          description="Evaluate and tune retrieval quality. Build golden question sets per library, then score libraries, agents, and experiments against them."
        />

        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        {/* Library selector */}
        <div className="flex items-center gap-3 mb-6">
          <LibraryIcon className="w-4 h-4 text-muted-foreground shrink-0" />
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading libraries...
            </div>
          ) : (
            <Select
              value={libraryId || undefined}
              onValueChange={value => setParam('library_id', value)}
            >
              <SelectTrigger className="w-72" aria-label="Select library">
                <SelectValue placeholder="Select a library..." />
              </SelectTrigger>
              <SelectContent>
                {libraries.map(lib => (
                  <SelectItem key={lib.id} value={lib.id}>
                    {lib.name}
                  </SelectItem>
                ))}
                {libraries.length === 0 && (
                  <div className="px-3 py-2 text-sm text-muted-foreground">
                    No libraries yet — create one on the Libraries page
                  </div>
                )}
              </SelectContent>
            </Select>
          )}
        </div>

        <Tabs value={tab} onValueChange={value => setParam('tab', value === 'question-sets' ? null : value)}>
          <TabsList className="mb-4">
            <TabsTrigger value="question-sets">Question Sets</TabsTrigger>
            <TabsTrigger value="scorecards">Scorecards</TabsTrigger>
            <TabsTrigger value="experiments">Experiments</TabsTrigger>
          </TabsList>

          <TabsContent value="question-sets">
            {selectedLibrary ? (
              <QuestionSetsTab libraryId={selectedLibrary.id} onError={setError} />
            ) : (
              !loading && (
                <Card>
                  <CardContent className="py-12 text-center text-muted-foreground">
                    <LibraryIcon className="w-10 h-10 mx-auto mb-3 opacity-40" />
                    <p className="text-sm">Select a library to manage its question sets.</p>
                  </CardContent>
                </Card>
              )
            )}
          </TabsContent>

          <TabsContent value="scorecards">
            {selectedLibrary ? (
              <ScorecardsTab
                libraryId={selectedLibrary.id}
                libraryName={selectedLibrary.name}
                onError={setError}
              />
            ) : (
              !loading && (
                <Card>
                  <CardContent className="py-12 text-center text-muted-foreground">
                    <LibraryIcon className="w-10 h-10 mx-auto mb-3 opacity-40" />
                    <p className="text-sm">Select a library to run scorecards against its question sets.</p>
                  </CardContent>
                </Card>
              )
            )}
          </TabsContent>

          <TabsContent value="experiments">
            {selectedLibrary ? (
              <ExperimentsTab libraryId={selectedLibrary.id} onError={setError} />
            ) : (
              !loading && (
                <Card>
                  <CardContent className="py-12 text-center text-muted-foreground">
                    <LibraryIcon className="w-10 h-10 mx-auto mb-3 opacity-40" />
                    <p className="text-sm">Select a library to run pipeline experiments.</p>
                  </CardContent>
                </Card>
              )
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
