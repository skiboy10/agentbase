import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { TabsContent } from '@/components/ui/tabs'
import { AgentFormData } from '../types'

interface AccessTabProps {
  formData: AgentFormData
  onFormChange: (data: Partial<AgentFormData>) => void
}

export function AccessTab({ formData, onFormChange }: AccessTabProps) {
  return (
    <TabsContent value="api" className="space-y-4 py-4">
      {/* External API Access */}
      <div className="space-y-3 p-4 border rounded-lg">
        <div className="flex items-center gap-2">
          <Switch
            id="is_public"
            checked={formData.is_public}
            onCheckedChange={checked => onFormChange({ is_public: checked })}
          />
          <Label htmlFor="is_public">Enable External API Access</Label>
        </div>
        <p className="text-sm text-muted-foreground">
          When enabled, this agent can be accessed via MCP or API using an API key.
          Generate an API key after creating the agent.
        </p>
      </div>

      {formData.is_public && (
        <div className="bg-muted p-4 rounded-md space-y-2 ml-6">
          <p className="text-sm font-medium">Access Methods:</p>
          <code className="text-xs bg-background p-2 rounded block">
            MCP: /mcp (Streamable HTTP)
          </code>
          <p className="text-xs text-muted-foreground">
            Include header: X-API-Key: your_api_key
          </p>
        </div>
      )}
    </TabsContent>
  )
}
