import { cn } from '../../../lib/utils'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { TabsContent } from '@/components/ui/tabs'
import { AgentFormData } from '../types'

export interface SkillInfo {
  skill_id: string
  name: string
  description?: string
  status: string
}

interface SkillsTabProps {
  formData: AgentFormData
  availableSkills: SkillInfo[]
  onToggleSkill: (skill: SkillInfo) => void
  isSkillSelected: (skillId: string) => boolean
}

export function SkillsTab({
  formData,
  availableSkills,
  onToggleSkill,
  isSkillSelected,
}: SkillsTabProps) {
  return (
    <TabsContent value="skills" className="space-y-4 py-4">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Label>Available Skills</Label>
          <span className="text-sm text-muted-foreground">
            {formData.skills.length} configured
          </span>
        </div>

        {availableSkills.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No skills available. Skills are configured externally.
          </p>
        ) : (
          <div className="space-y-2 max-h-64 overflow-y-auto border rounded-md p-2">
            {availableSkills.map(skill => (
              <label
                key={skill.skill_id}
                htmlFor={`skill-${skill.skill_id}`}
                className={cn(
                  'flex items-start gap-3 p-3 rounded-md cursor-pointer hover:bg-muted transition-colors',
                  isSkillSelected(skill.skill_id) && 'bg-muted'
                )}
              >
                <Checkbox
                  id={`skill-${skill.skill_id}`}
                  checked={isSkillSelected(skill.skill_id)}
                  onCheckedChange={() => onToggleSkill(skill)}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-medium">{skill.name}</p>
                    <Badge
                      variant={skill.status === 'active' ? 'default' : 'secondary'}
                      className="text-xs"
                    >
                      {skill.status}
                    </Badge>
                  </div>
                  {skill.description && (
                    <p className="text-xs text-muted-foreground mt-1">
                      {skill.description}
                    </p>
                  )}
                </div>
              </label>
            ))}
          </div>
        )}

        <p className="text-xs text-muted-foreground">
          Skills give your agent additional capabilities beyond knowledge retrieval.
        </p>
      </div>
    </TabsContent>
  )
}
