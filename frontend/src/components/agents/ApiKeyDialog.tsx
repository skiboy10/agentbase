import { Copy, Loader2 } from 'lucide-react'
import { Agent } from '../../services/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'

export interface ApiKeyDialogProps {
  agent: Agent | null
  apiKey: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  generatingKey: boolean
  onGenerate: () => void
}

export function ApiKeyDialog({
  agent,
  apiKey,
  open,
  onOpenChange,
  generatingKey,
  onGenerate,
}: ApiKeyDialogProps) {
  if (!agent) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>API Key Management</DialogTitle>
          <DialogDescription>
            {apiKey
              ? "Your new API key has been generated. Copy it now - it won't be shown again."
              : `Manage API key for "${agent.name}"`}
          </DialogDescription>
        </DialogHeader>

        {apiKey ? (
          <div className="space-y-4">
            <div className="bg-muted p-4 rounded-md">
              <code className="text-sm break-all">{apiKey}</code>
            </div>
            <Button
              className="w-full"
              onClick={() => navigator.clipboard.writeText(apiKey)}
            >
              <Copy className="w-4 h-4 mr-2" />
              Copy to Clipboard
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              {agent.has_api_key
                ? 'This agent has an active API key. You can generate a new one to replace it.'
                : 'Generate an API key to allow external applications to invoke this agent.'}
            </p>
            <Button
              className="w-full"
              onClick={onGenerate}
              disabled={generatingKey}
            >
              {generatingKey && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              {agent.has_api_key ? 'Refresh API Key' : 'Create API Key'}
            </Button>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
