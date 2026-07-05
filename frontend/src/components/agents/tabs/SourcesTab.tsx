import { useState } from 'react'
import { ChevronDown, ChevronRight, Loader2, RefreshCw } from 'lucide-react'
import { cn } from '../../../lib/utils'
import { Source } from '../../../services/api'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { TabsContent } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { AgentFormData } from '../types'
import { LibraryPicker } from '../components/LibraryPicker'
import type { LibraryLoadStatus } from '../hooks/useAgentFormData'

interface SourcesTabProps {
  formData: AgentFormData
  onFormChange: (data: Partial<AgentFormData>) => void
  sources: Source[]
  onToggleSource: (sourceId: string) => void
  onToggleLibrary: (libraryId: string) => void
  /** Load state of the agent's current library bindings (edit flow). */
  libraryLoadStatus: LibraryLoadStatus
  onRetryLibraryLoad: () => void
}

export function SourcesTab({
  formData,
  onFormChange,
  sources,
  onToggleSource,
  onToggleLibrary,
  libraryLoadStatus,
  onRetryLibraryLoad,
}: SourcesTabProps) {
  const [sourcesExpanded, setSourcesExpanded] = useState(false)

  return (
    <TabsContent value="knowledge" className="space-y-4 py-4">
      {/* RAG toggle + top-k */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Switch
            id="use_rag"
            checked={formData.use_rag}
            onCheckedChange={checked => onFormChange({ use_rag: checked })}
          />
          <Label htmlFor="use_rag">Enable RAG (Knowledge Retrieval)</Label>
        </div>
        {formData.use_rag && (
          <div className="flex items-center gap-2">
            <Label htmlFor="rag_top_k" className="text-sm">Docs per search:</Label>
            <Select
              value={String(formData.rag_top_k)}
              onValueChange={value => onFormChange({ rag_top_k: parseInt(value) })}
            >
              <SelectTrigger className="w-20">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[3, 5, 10, 15].map(n => (
                  <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      {formData.use_rag && (
        <>
          {/* PRIMARY: Library bindings */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>
                Libraries
                {formData.library_ids.length > 0 && (
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    {formData.library_ids.length} bound
                  </span>
                )}
              </Label>
            </div>
            <p className="text-xs text-muted-foreground">
              Libraries are the primary knowledge source for RAG retrieval.
              Bind one or more curated libraries to this agent.
            </p>
            {libraryLoadStatus === 'error' ? (
              <div className="py-6 text-center border rounded-md space-y-2">
                <p className="text-sm text-destructive">
                  Failed to load this agent's library bindings. Library changes
                  will not be saved until they load.
                </p>
                <Button variant="ghost" size="sm" onClick={onRetryLibraryLoad}>
                  <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                  Retry
                </Button>
              </div>
            ) : libraryLoadStatus === 'loading' ? (
              <div className="flex items-center justify-center py-8 border rounded-md">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <LibraryPicker
                selectedIds={formData.library_ids}
                onToggle={onToggleLibrary}
              />
            )}
          </div>

          {/* SECONDARY: Individual source bindings (collapsible) */}
          <div className="border rounded-md">
            <Button
              type="button"
              variant="ghost"
              className="w-full flex items-center justify-between px-3 py-2.5 h-auto text-sm font-medium rounded-md"
              onClick={() => setSourcesExpanded(prev => !prev)}
              aria-expanded={sourcesExpanded}
            >
              <span>
                Advanced: Individual Sources
                {formData.source_ids.length > 0 && (
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    {formData.source_ids.length} selected
                  </span>
                )}
              </span>
              {sourcesExpanded
                ? <ChevronDown className="w-4 h-4 text-muted-foreground" />
                : <ChevronRight className="w-4 h-4 text-muted-foreground" />
              }
            </Button>

            {sourcesExpanded && (
              <div className="px-3 pb-3 space-y-2 border-t">
                <p className="text-xs text-muted-foreground pt-2">
                  Bind individual indexed sources directly. Use this when you need
                  granular control outside of a library.
                </p>
                {sources.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4 text-center">
                    No indexed sources available. Index some documents first.
                  </p>
                ) : (
                  <div className="space-y-1 max-h-48 overflow-y-auto border rounded-md p-2">
                    {sources.map(source => {
                      const selected = formData.source_ids.includes(source.id)
                      return (
                        <div
                          key={source.id}
                          role="checkbox"
                          aria-checked={selected}
                          tabIndex={0}
                          onClick={() => onToggleSource(source.id)}
                          onKeyDown={e => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault()
                              onToggleSource(source.id)
                            }
                          }}
                          className={cn(
                            'flex items-center gap-3 p-2 rounded-md cursor-pointer hover:bg-muted outline-none focus-visible:bg-muted',
                            selected && 'bg-muted'
                          )}
                        >
                          {/* Checkbox is presentation-only; the row owns the interaction */}
                          <Checkbox
                            checked={selected}
                            className="pointer-events-none"
                            tabIndex={-1}
                            aria-hidden="true"
                          />
                          <div className="flex-1">
                            <p className="text-sm font-medium">{source.name}</p>
                            <p className="text-xs text-muted-foreground">
                              {source.chunk_count} chunks
                            </p>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  {formData.source_ids.length} source(s) selected
                </p>
              </div>
            )}
          </div>
        </>
      )}
    </TabsContent>
  )
}
