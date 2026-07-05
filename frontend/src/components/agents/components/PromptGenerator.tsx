import { Loader2, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface PromptGeneratorProps {
  purpose: string
  onPurposeChange: (value: string) => void
  onGenerate: () => void
  generating: boolean
  error: string | null
}

export function PromptGenerator({
  purpose,
  onPurposeChange,
  onGenerate,
  generating,
  error,
}: PromptGeneratorProps) {
  return (
    <div className="space-y-3 p-4 bg-muted/30 rounded-lg border border-dashed">
      <div className="flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-primary" />
        <Label>AI Prompt Generator</Label>
      </div>
      <p className="text-xs text-muted-foreground">
        Describe your agent's purpose and we'll generate a tailored system prompt
      </p>
      <div className="flex gap-2">
        <Input
          value={purpose}
          onChange={e => onPurposeChange(e.target.value)}
          placeholder="e.g., Help users understand our API documentation"
          className="flex-1"
        />
        <Button
          type="button"
          variant="secondary"
          onClick={onGenerate}
          disabled={!purpose.trim() || generating}
        >
          {generating ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4" />
          )}
          <span className="ml-2">Generate</span>
        </Button>
      </div>
      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}
    </div>
  )
}
