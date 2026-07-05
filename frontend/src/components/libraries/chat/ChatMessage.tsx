import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import type { ChatDisplayMessage } from './types'
import MarkdownRenderer from '../../MarkdownRenderer'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'

interface ChatMessageProps {
  message: ChatDisplayMessage
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-tr-sm px-4 py-2.5 bg-muted text-foreground text-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    )
  }

  // Assistant message
  return (
    <div className="flex flex-col gap-1.5 max-w-[90%]">
      <Card className="bg-background border-border/60">
        <CardContent className="pt-4 pb-3 px-4">
          <div className="prose-sm text-foreground leading-relaxed">
            <MarkdownRenderer content={message.content} />
          </div>
        </CardContent>
      </Card>

      {/* Sources attribution */}
      {message.sources && message.sources.length > 0 && (
        <Collapsible open={sourcesOpen} onOpenChange={setSourcesOpen}>
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground h-7 px-1 justify-start"
            >
              <ChevronDown
                className={`w-3.5 h-3.5 transition-transform duration-200 ${
                  sourcesOpen ? 'rotate-180' : ''
                }`}
              />
              <span className="text-xs">
                {message.sources.length} source{message.sources.length !== 1 ? 's' : ''}
              </span>
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-1.5 space-y-1.5">
              {message.sources.map((source, idx) => (
                <Card
                  key={`${source.source_id}-${idx}`}
                  className="bg-muted/40 border-border/50"
                >
                  <CardHeader className="py-2.5 px-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-foreground truncate">
                          {source.title || source.source_name}
                        </p>
                        {source.title && source.source_name && source.title !== source.source_name && (
                          <p className="text-xs text-muted-foreground truncate mt-0.5">
                            {source.source_name}
                          </p>
                        )}
                      </div>
                      <Badge variant="secondary" className="shrink-0 text-xs tabular-nums">
                        {((source.score || 0) * 100).toFixed(0)}%
                      </Badge>
                    </div>
                  </CardHeader>
                  {source.preview && (
                    <CardContent className="pb-2.5 pt-0 px-3">
                      <p className="text-xs text-muted-foreground line-clamp-3 leading-relaxed">
                        {source.preview}
                      </p>
                      {source.url && (
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-primary hover:underline mt-1 block truncate"
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

      {/* Model indicator */}
      {message.model && (
        <p className="text-[11px] text-muted-foreground/60 px-1">
          {message.model}
        </p>
      )}
    </div>
  )
}
