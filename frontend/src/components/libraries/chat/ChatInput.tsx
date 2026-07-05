import { Send, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

interface ChatInputProps {
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  disabled: boolean
  placeholder?: string
}

export default function ChatInput({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder = 'Ask a question about this library...',
}: ChatInputProps) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      if (!disabled && value.trim()) {
        onSubmit()
      }
    }
  }

  return (
    <div className="border-t border-border pt-3">
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        aria-label="Chat message input"
        disabled={disabled}
        rows={3}
        className="resize-none text-sm mb-2"
      />
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          Press{' '}
          <kbd className="font-mono bg-muted px-1 py-0.5 rounded text-[11px]">
            {/Mac|iPhone|iPad/.test(navigator.userAgent) ? 'Cmd' : 'Ctrl'}
          </kbd>
          {' + '}
          <kbd className="font-mono bg-muted px-1 py-0.5 rounded text-[11px]">
            Enter
          </kbd>{' '}
          to send
        </p>
        <Button
          onClick={onSubmit}
          disabled={disabled || !value.trim()}
          size="sm"
        >
          {disabled ? (
            <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
          ) : (
            <Send className="w-4 h-4 mr-1.5" />
          )}
          {disabled ? 'Thinking...' : 'Send'}
        </Button>
      </div>
    </div>
  )
}
