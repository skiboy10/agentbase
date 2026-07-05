import { Bot, Copy, Database, Globe, Key, MessageSquare, MoreHorizontal, Pencil, Puzzle, Trash2, Wrench, Zap } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Agent } from '../../services/api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export interface AgentCardProps {
  agent: Agent
  onEdit: () => void
  onDuplicate: () => void
  onDelete: () => void
  onManageApiKey: () => void
}

// Badge priority: Extension > API Key > Public > Global
// Show at most 2, collapse remainder into +N
function AgentBadges({ agent }: { agent: Agent }) {
  const badges: { key: string; variant: 'outline' | 'secondary' | 'default'; icon: React.ReactNode; label: string }[] = []

  const isExtension = !!agent.agent_id && agent.agent_id.includes('.')
  if (isExtension) {
    badges.push({ key: 'ext', variant: 'outline', icon: <Puzzle className="w-3 h-3 mr-1" />, label: 'Extension' })
  }
  if (agent.has_api_key) {
    badges.push({ key: 'api', variant: 'secondary', icon: <Key className="w-3 h-3 mr-1" />, label: 'API Key' })
  }
  if (agent.is_public) {
    badges.push({ key: 'pub', variant: 'default', icon: <Globe className="w-3 h-3 mr-1" />, label: 'Public' })
  }

  if (badges.length === 0) return null

  const visible = badges.slice(0, 2)
  const overflow = badges.length - 2

  return (
    <>
      {visible.map(b => (
        <Badge key={b.key} variant={b.variant} className="text-xs">
          {b.icon}
          {b.label}
        </Badge>
      ))}
      {overflow > 0 && (
        <Badge variant="secondary" className="text-xs">
          +{overflow}
        </Badge>
      )}
    </>
  )
}

export function AgentCard({
  agent,
  onEdit,
  onDuplicate,
  onDelete,
  onManageApiKey,
}: AgentCardProps) {
  const navigate = useNavigate()
  const hasSources = (agent.source_ids?.length || 0) > 0

  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <Bot className="w-5 h-5 text-primary" />
              <h3 className="font-semibold text-foreground">{agent.name}</h3>
              <AgentBadges agent={agent} />
            </div>
            {agent.description && (
              <p className="text-sm text-muted-foreground mb-2">
                {agent.description}
              </p>
            )}
            <div className="flex items-center gap-1 text-sm text-muted-foreground">
              <span className="flex items-center gap-1">
                <Zap className="w-3 h-3" />
                {agent.model_provider}/{agent.model_name}
              </span>
              {agent.use_rag && (
                <>
                  <span className="mx-1.5">&middot;</span>
                  <button
                    type="button"
                    onClick={() => navigate('/sources')}
                    className="flex items-center gap-1 hover:text-foreground transition-colors cursor-pointer rounded-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    title="View sources"
                  >
                    <Database className="w-3 h-3" />
                    {agent.source_ids?.length || 0} source{(agent.source_ids?.length || 0) !== 1 ? 's' : ''}
                  </button>
                </>
              )}
              {agent.skills && agent.skills.length > 0 && (
                <>
                  <span className="mx-1.5">&middot;</span>
                  <span className="flex items-center gap-1">
                    <Wrench className="w-3 h-3" />
                    {agent.skills.length} skill{agent.skills.length !== 1 ? 's' : ''}
                  </span>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 ml-4">
            {/* Actions dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" title="Actions">
                  <MoreHorizontal className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {hasSources && (
                  <DropdownMenuItem onClick={() => navigate(`/agents/${agent.id}/query`)}>
                    <MessageSquare className="w-4 h-4 mr-2" />
                    Query
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem onClick={onEdit}>
                  <Pencil className="w-4 h-4 mr-2" />
                  Edit
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onDuplicate}>
                  <Copy className="w-4 h-4 mr-2" />
                  Duplicate
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onManageApiKey}>
                  <Key className="w-4 h-4 mr-2" />
                  Manage API Key
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onDelete} className="text-destructive focus:text-destructive">
                  <Trash2 className="w-4 h-4 mr-2" />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
