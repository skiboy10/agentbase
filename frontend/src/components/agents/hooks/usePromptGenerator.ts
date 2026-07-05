import { useState } from 'react'
import { Source, promptGeneratorApi } from '../../../services/api'

interface UsePromptGeneratorProps {
  sources: Source[]
  selectedSourceIds: string[]
  onGenerated: (prompt: string) => void
}

export function usePromptGenerator({
  sources,
  selectedSourceIds,
  onGenerated,
}: UsePromptGeneratorProps) {
  const [purpose, setPurpose] = useState('')
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const generate = async () => {
    if (!purpose.trim()) return

    try {
      setGenerating(true)
      setError(null)

      const selectedSourceNames = selectedSourceIds
        .map(id => sources.find(s => s.id === id)?.name)
        .filter((name): name is string => !!name)

      const result = await promptGeneratorApi.generate({
        purpose,
        knowledge_sources: selectedSourceNames,
        context_type: 'agent',
      })

      onGenerated(result.system_prompt)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate prompt')
    } finally {
      setGenerating(false)
    }
  }

  const reset = () => {
    setPurpose('')
    setError(null)
  }

  return {
    purpose,
    setPurpose,
    generating,
    error,
    generate,
    reset,
  }
}
