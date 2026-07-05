import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Bot,
  Send,
  ChevronDown,
  Loader2,
  MessageSquare,
  Zap,
  Database,
} from 'lucide-react'
import { agentsApi } from '../services/api/agents'
import type { Agent, AgentQueryResponse } from '../services/api/types/agents'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import MarkdownRenderer from '../components/MarkdownRenderer'

export default function AgentQueryPage() {
  const { agentId } = useParams<{ agentId: string }>()
  const navigate = useNavigate()

  const [agent, setAgent] = useState<Agent | null>(null)
  const [agentLoading, setAgentLoading] = useState(true)
  const [agentError, setAgentError] = useState<string | null>(null)

  const [query, setQuery] = useState('')
  const [response, setResponse] = useState<AgentQueryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sourcesOpen, setSourcesOpen] = useState(false)

  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Fetch agent details on mount
  useEffect(() => {
    if (!agentId) return
    setAgentLoading(true)
    agentsApi
      .get(agentId)
      .then((a) => {
        setAgent(a)
        setAgentError(null)
      })
      .catch((err) => {
        setAgentError(err instanceof Error ? err.message : 'Failed to load agent')
      })
      .finally(() => setAgentLoading(false))
  }, [agentId])

  // Auto-focus textarea once agent loads
  useEffect(() => {
    if (!agentLoading && textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [agentLoading])

  const handleSubmit = useCallback(async () => {
    if (!agentId || !query.trim() || loading) return

    setLoading(true)
    setError(null)
    setResponse(null)
    setSourcesOpen(false)

    try {
      const result = await agentsApi.query(agentId, { query: query.trim() })
      setResponse(result)
      // Auto-open sources if there are any
      if (result.sources && result.sources.length > 0) {
        setSourcesOpen(true)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Query failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [agentId, query, loading])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      handleSubmit()
    }
  }

  // Loading state for agent fetch
  if (agentLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </div>
    )
  }

  // Agent fetch error
  if (agentError || !agent) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <Button variant="ghost" size="sm" onClick={() => navigate('/agents')} className="mb-4">
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Agents
        </Button>
        <Card>
          <CardContent className="pt-6 text-center text-destructive">
            {agentError || 'Agent not found.'}
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto">
        {/* Back navigation */}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/agents')}
          className="mb-5 -ml-2 text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Agents
        </Button>

        {/* Agent header */}
        <div className="flex items-start gap-3 mb-6">
          <div className="p-2 rounded-lg bg-primary/10">
            <Bot className="w-6 h-6 text-primary" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold text-foreground">{agent.name}</h1>
              <MessageSquare className="w-4 h-4 text-muted-foreground" />
            </div>
            {agent.description && (
              <p className="text-sm text-muted-foreground mt-0.5">{agent.description}</p>
            )}
            <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Zap className="w-3 h-3" />
                {agent.model_provider}/{agent.model_name}
              </span>
              {agent.use_rag && (
                <span className="flex items-center gap-1">
                  <Database className="w-3 h-3" />
                  {agent.source_ids?.length || 0} source
                  {(agent.source_ids?.length || 0) !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          </div>
        </div>

        <Separator className="mb-6" />

        {/* Query input */}
        <div className="mb-4">
          <Textarea
            ref={textareaRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question..."
            disabled={loading}
            rows={4}
            className="resize-none text-base"
          />
          <div className="flex items-center justify-between mt-2">
            <p className="text-xs text-muted-foreground">
              Press <kbd className="font-mono bg-muted px-1 py-0.5 rounded text-[11px]">Cmd</kbd>
              {' + '}
              <kbd className="font-mono bg-muted px-1 py-0.5 rounded text-[11px]">Enter</kbd>
              {' to submit'}
            </p>
            <Button
              onClick={handleSubmit}
              disabled={loading || !query.trim()}
              size="sm"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Send className="w-4 h-4 mr-2" />
              )}
              {loading ? 'Asking...' : 'Ask'}
            </Button>
          </div>
        </div>

        {/* Error state */}
        {error && (
          <Card className="mb-4 border-destructive/50 bg-destructive/5">
            <CardContent className="pt-4 text-sm text-destructive">
              {error}
            </CardContent>
          </Card>
        )}

        {/* Response section */}
        {response && (
          <div className="mt-6 space-y-4">
            {/* Answer card */}
            <Card>
              <CardContent className="pt-5">
                <div className="prose-sm text-foreground leading-relaxed">
                  <MarkdownRenderer content={response.answer} />
                </div>

                {/* Model used indicator */}
                <div className="mt-4 pt-3 border-t border-border flex items-center justify-between">
                  <p className="text-xs text-muted-foreground">
                    Answered by <span className="font-medium">{response.model}</span>
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Sources section */}
            {response.sources && response.sources.length > 0 && (
              <Collapsible open={sourcesOpen} onOpenChange={setSourcesOpen}>
                <CollapsibleTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="flex items-center gap-2 text-muted-foreground hover:text-foreground w-full justify-start px-0"
                  >
                    <ChevronDown
                      className={`w-4 h-4 transition-transform duration-200 ${
                        sourcesOpen ? 'rotate-180' : ''
                      }`}
                    />
                    <span className="text-sm font-medium">
                      {response.sources.length} source
                      {response.sources.length !== 1 ? 's' : ''}
                    </span>
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="mt-2 space-y-2">
                    {response.sources.map((source, idx) => (
                      <Card key={`${source.source_id}-${idx}`} className="bg-muted/40">
                        <CardHeader className="py-3 px-4">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-foreground truncate">
                                {source.title || source.source_name}
                              </p>
                              {source.title && source.source_name && source.title !== source.source_name && (
                                <p className="text-xs text-muted-foreground truncate">
                                  {source.source_name}
                                </p>
                              )}
                            </div>
                            <Badge variant="secondary" className="shrink-0 text-xs tabular-nums">
                              {(source.score * 100).toFixed(0)}%
                            </Badge>
                          </div>
                        </CardHeader>
                        {source.preview && (
                          <CardContent className="pb-3 pt-0 px-4">
                            <p className="text-xs text-muted-foreground line-clamp-3 leading-relaxed">
                              {source.preview}
                            </p>
                            {source.url && (
                              <a
                                href={source.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs text-primary hover:underline mt-1.5 block truncate"
                              >
                                {source.url}
                              </a>
                            )}
                          </CardContent>
                        )}
                      </Card>
                    ))}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
