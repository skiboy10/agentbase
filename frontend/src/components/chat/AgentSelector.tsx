import { FC } from 'react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Bot } from 'lucide-react'
import type { Agent } from '@/services/api/types/agents'

interface AgentSelectorProps {
  agents: Agent[]
  selectedAgentId: string | null
  onSelectAgent: (agentId: string | null) => void
  disabled?: boolean
}

export const AgentSelector: FC<AgentSelectorProps> = ({
  agents,
  selectedAgentId,
  onSelectAgent,
  disabled = false,
}) => {
  const selectedAgent = agents.find(a => a.id === selectedAgentId)

  return (
    <Select
      value={selectedAgentId || 'none'}
      onValueChange={(value) => onSelectAgent(value === 'none' ? null : value)}
      disabled={disabled}
    >
      <SelectTrigger className="w-[140px] md:w-[200px] h-8 text-sm">
        <div className="flex items-center gap-2 truncate">
          <Bot className="h-4 w-4 flex-shrink-0" />
          <SelectValue placeholder="No Agent">
            {selectedAgent ? selectedAgent.name : 'No Agent'}
          </SelectValue>
        </div>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="none">
          <span className="text-muted-foreground">No Agent</span>
        </SelectItem>
        {agents.map((agent) => (
          <SelectItem key={agent.id} value={agent.id}>
            <div className="flex flex-col">
              <span>{agent.name}</span>
              {agent.description && (
                <span className="text-xs text-muted-foreground truncate max-w-[180px]">
                  {agent.description}
                </span>
              )}
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export default AgentSelector
