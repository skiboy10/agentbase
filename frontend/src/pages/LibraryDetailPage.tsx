import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Loader2,
  Database,
  FileText,
  Layers,
  Cpu,
  MessageSquare,
} from 'lucide-react'
import { libraryApi } from '../services/api/library'
import type { Library, LibrarySource } from '../services/api/types/library'
import { useVisiblePolling } from '../hooks/useVisiblePolling'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ErrorBanner, HelpTooltip } from '../components'
import { SourcesTab, DocumentsTab, RetrievalLabTab, SettingsTab, ChatTab, EditableDescription } from '../components/libraries'

export default function LibraryDetailPage() {
  const { libraryId } = useParams<{ libraryId: string }>()
  const navigate = useNavigate()

  const [kb, setKb] = useState<Library | null>(null)
  const [sources, setSources] = useState<LibrarySource[]>([])
  const [sourcesLoaded, setSourcesLoaded] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchKB = useCallback(async (opts?: { silent?: boolean }) => {
    if (!libraryId) return
    try {
      // Background polling must not flip the page into its loading/error/not-found
      // screens — doing so unmounts the tabs (incl. an open Settings form, chat,
      // retrieval lab) and wipes their in-progress state.
      if (!opts?.silent) {
        setLoading(true)
        setError(null)
      }
      // Fetch library first — if this 401s, don't bother with sources
      const kbData = await libraryApi.get(libraryId)
      setKb(kbData)
      // Clear any stale error after a successful load (incl. a recovered silent poll)
      setError(null)
      setSourcesLoaded(false)
      // Sources fetch is non-critical — don't let it block the page
      try {
        const sourcesData = await libraryApi.listSources(libraryId)
        setSources(sourcesData)
        setSourcesLoaded(true)
      } catch {
        // Sources will load empty — tabs still render
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load library'
      // Don't set error for auth issues — AuthGate handles those.
      // Don't surface transient poll failures over an already-rendered page.
      if (!opts?.silent && msg !== 'Authentication required') {
        setError(msg)
      }
    } finally {
      if (!opts?.silent) setLoading(false)
    }
  }, [libraryId])

  useEffect(() => {
    fetchKB()
  }, [fetchKB])

  // Stable reference — an inline arrow would change every render and, since
  // useVisiblePolling depends on it, reset the interval (and re-poll) constantly.
  const pollKB = useCallback(() => fetchKB({ silent: true }), [fetchKB])

  useVisiblePolling(pollKB, {
    intervalMs: 15000,
    enabled: !!libraryId,
  })

  const handleKbUpdated = useCallback((updated: Library) => setKb(updated), [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-7 h-7 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!kb) {
    return (
      <div className="p-6">
        <div className="max-w-5xl mx-auto">
          <ErrorBanner error={error} onDismiss={() => setError(null)} />
          <Button variant="ghost" size="sm" onClick={() => navigate('/libraries')}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          {!error && (
            <div className="mt-6 text-center text-muted-foreground">
              Library not found.
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto">
        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        {/* Back button */}
        <Button
          variant="ghost"
          size="sm"
          className="mb-4 -ml-2 text-muted-foreground hover:text-foreground"
          onClick={() => navigate('/libraries')}
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Libraries
        </Button>

        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-2xl font-bold text-foreground truncate">{kb.name}</h1>
              <Badge
                variant={
                  kb.status === 'active' || kb.status === 'indexed'
                    ? 'default'
                    : kb.status === 'error'
                    ? 'destructive'
                    : 'secondary'
                }
                className="shrink-0"
              >
                {kb.status}
              </Badge>
            </div>
            <EditableDescription kb={kb} onUpdated={handleKbUpdated} />
            {kb.embedding_provider && kb.embedding_model && (
              <div className="flex items-center gap-1.5 mt-2">
                <Badge
                  variant="outline"
                  className="text-xs font-mono text-emerald-400 border-emerald-400/40"
                >
                  <Cpu className="w-3 h-3 mr-1" />
                  {kb.embedding_provider}/{kb.embedding_model}
                  {kb.embedding_dimensions && (
                    <span className="ml-1 text-muted-foreground/70">
                      ({kb.embedding_dimensions}d)
                    </span>
                  )}
                </Badge>
              </div>
            )}
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-muted/30 border border-border/50">
            <Database className="w-5 h-5 text-muted-foreground/60 shrink-0" />
            <div>
              <p className="text-xl font-bold text-foreground leading-none">
                {sourcesLoaded ? sources.length : kb.source_count}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">Sources</p>
            </div>
          </div>
          <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-muted/30 border border-border/50">
            <FileText className="w-5 h-5 text-muted-foreground/60 shrink-0" />
            <div>
              <p className="text-xl font-bold text-foreground leading-none">
                {kb.document_count.toLocaleString()}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">Documents</p>
            </div>
          </div>
          <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-muted/30 border border-border/50">
            <Layers className="w-5 h-5 text-muted-foreground/60 shrink-0" />
            <div>
              <p className="text-xl font-bold text-foreground leading-none">
                {kb.chunk_count.toLocaleString()}
              </p>
              <div className="flex items-center gap-1 mt-0.5">
                <p className="text-xs text-muted-foreground">Chunks</p>
                <HelpTooltip helpKey="libraries.chunks" side="bottom" className="text-muted-foreground/60" />
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="documents">
          <TabsList className="mb-4">
            <TabsTrigger value="sources">Sources</TabsTrigger>
            <TabsTrigger value="documents">Documents</TabsTrigger>
            <TabsTrigger value="retrieval-lab">Retrieval Lab</TabsTrigger>
            <TabsTrigger value="chat">
              <MessageSquare className="w-3.5 h-3.5 mr-1.5" />
              Chat
            </TabsTrigger>
            <TabsTrigger value="settings">Settings</TabsTrigger>
          </TabsList>

          <TabsContent value="sources">
            <SourcesTab kbId={kb.id} onError={setError} onSourcesChanged={fetchKB} />
          </TabsContent>

          <TabsContent value="documents">
            <DocumentsTab kbId={kb.id} sources={sources} onError={setError} />
          </TabsContent>

          <TabsContent value="retrieval-lab">
            <RetrievalLabTab kbId={kb.id} sources={sources} onError={setError} />
          </TabsContent>

          <TabsContent value="chat">
            <ChatTab kbId={kb.id} />
          </TabsContent>

          <TabsContent value="settings">
            <SettingsTab kb={kb} onKbUpdated={handleKbUpdated} onError={setError} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
