import { useState, useEffect, useCallback } from 'react'
import { configApi, EmbeddingConfig } from '../../../../services/api'

export interface UseEmbeddingConfigResult {
  embeddingConfig: EmbeddingConfig | null
  useCustomEmbedding: boolean
  setUseCustomEmbedding: (value: boolean) => void
  selectedProvider: string
  setSelectedProvider: (value: string) => void
  selectedModel: string
  setSelectedModel: (value: string) => void
  reset: () => void
  getEmbeddingParams: () => { provider?: string; model?: string }
}

export function useEmbeddingConfig(isOpen: boolean): UseEmbeddingConfigResult {
  const [embeddingConfig, setEmbeddingConfig] = useState<EmbeddingConfig | null>(null)
  const [useCustomEmbedding, setUseCustomEmbedding] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState('')
  const [selectedModel, setSelectedModel] = useState('')

  // Fetch embedding config when dialog opens
  useEffect(() => {
    if (isOpen) {
      configApi.getEmbeddingConfig()
        .then((config) => {
          setEmbeddingConfig(config)
          // Set default selections when config loads
          if (config.available_models.length > 0) {
            const defaultModel = config.available_models.find(
              m => m.provider === config.default_provider && m.model === config.default_model
            ) || config.available_models[0]
            setSelectedProvider(defaultModel.provider)
            setSelectedModel(defaultModel.model)
          }
        })
        .catch(console.error)
    }
  }, [isOpen])

  const reset = useCallback(() => {
    setUseCustomEmbedding(false)
    setSelectedProvider('')
    setSelectedModel('')
  }, [])

  const getEmbeddingParams = useCallback(() => {
    if (useCustomEmbedding) {
      return {
        provider: selectedProvider,
        model: selectedModel,
      }
    }
    return {}
  }, [useCustomEmbedding, selectedProvider, selectedModel])

  return {
    embeddingConfig,
    useCustomEmbedding,
    setUseCustomEmbedding,
    selectedProvider,
    setSelectedProvider,
    selectedModel,
    setSelectedModel,
    reset,
    getEmbeddingParams,
  }
}
