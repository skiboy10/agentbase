import { useState, useEffect, useRef } from 'react'
import { MessageSquare, Trash2 } from 'lucide-react'
import { libraryApi } from '../../../services/api/library'
import type { ChatDisplayMessage, LibraryChatConfig } from './types'
import ChatConfig from './ChatConfig'
import ChatMessage from './ChatMessage'
import ChatInput from './ChatInput'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

interface ChatTabProps {
  kbId: string
}

const DEFAULT_CONFIG: LibraryChatConfig = {
  provider: '',
  model: '',
  top_k: 5,
  rerank: false,
  search_mode: 'hybrid',
  vector_weight: 0.7,
}

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export default function ChatTab({ kbId }: ChatTabProps) {  // sources prop removed — unused
  const [messages, setMessages] = useState<ChatDisplayMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [config, setConfig] = useState<LibraryChatConfig>(DEFAULT_CONFIG)

  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom whenever messages change
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || loading) return

    // Build history from current messages (exclude the new message being sent)
    const history = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }))

    // Optimistically append the user message
    const userMsgId = newId()
    const userMessage: ChatDisplayMessage = { id: userMsgId, role: 'user', content: text }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setLoading(true)
    setError(null)

    try {
      const response = await libraryApi.chat(kbId, {
        message: text,
        history,
        config,
      })

      const assistantMessage: ChatDisplayMessage = {
        id: newId(),
        role: 'assistant',
        content: response.answer,
        sources: response.sources,
        model: response.model,
      }
      setMessages((prev) => [...prev, assistantMessage])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Chat request failed. Please try again.')
      // Remove the specific optimistic user message by ID
      setMessages((prev) => prev.filter((m) => m.id !== userMsgId))
      setInput(text)
    } finally {
      setLoading(false)
    }
  }

  const handleClearChat = () => {
    setMessages([])
    setError(null)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-20rem)] min-h-[400px] max-h-[800px]">
      {/* Config bar */}
      <div className="flex items-center justify-between mb-2">
        <ChatConfig config={config} onChange={setConfig} disabled={loading} />
        {messages.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClearChat}
            disabled={loading}
            className="text-muted-foreground hover:text-foreground h-8 px-2 text-xs"
          >
            <Trash2 className="w-3.5 h-3.5 mr-1" />
            Clear
          </Button>
        )}
      </div>

      {/* Message area */}
      <div className="flex-1 overflow-y-auto py-2 space-y-4 pr-1">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center gap-3 text-muted-foreground">
            <MessageSquare className="w-10 h-10 opacity-30" />
            <div>
              <p className="text-sm font-medium">Ask anything about this library</p>
              <p className="text-xs mt-1 opacity-70">
                Questions are answered using the library's indexed knowledge
              </p>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))
        )}

        {/* Loading indicator */}
        {loading && (
          <div className="flex items-center gap-2 text-muted-foreground text-xs pl-1">
            <span className="flex gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:300ms]" />
            </span>
            Thinking...
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Error banner */}
      {error && (
        <Card className="mb-2 border-destructive/50 bg-destructive/5 shrink-0">
          <CardContent className="py-2 px-3 text-xs text-destructive">
            {error}
          </CardContent>
        </Card>
      )}

      {/* Input area */}
      <ChatInput
        value={input}
        onChange={setInput}
        onSubmit={handleSend}
        disabled={loading}
      />
    </div>
  )
}
