import { useState, useCallback } from 'react'
import { testsApi, TestSuite, TestCase, Provider, TestStreamCallbacks } from '../../services/api'
import { getEnabledModelsForProvider } from '../../pages/ProvidersPage'

interface RunProgress {
  current: number
  total: number
  currentCase: string
}

interface UseTestRunningOptions {
  selectedSuite: TestSuite | null
  testCases: TestCase[]
  providers: Provider[]
  onError: (error: string) => void
  onComplete: () => void
}

export function useTestRunning({
  selectedSuite,
  testCases,
  providers,
  onError,
  onComplete,
}: UseTestRunningOptions) {
  const [showRunModal, setShowRunModal] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [runProgress, setRunProgress] = useState<RunProgress>({ current: 0, total: 0, currentCase: '' })
  const [runConfig, setRunConfig] = useState({
    provider: '',
    model: '',
    evaluatorProvider: '',
    evaluatorModel: '',
  })

  const openRunModal = useCallback(() => {
    if (providers.length > 0) {
      const firstProvider = providers[0]
      const enabledModels = getEnabledModelsForProvider(firstProvider)
      if (enabledModels.length > 0) {
        setRunConfig(prev => ({
          ...prev,
          provider: firstProvider.name,
          model: enabledModels[0],
        }))
      }
    }
    setShowRunModal(true)
  }, [providers])

  const handleRunTests = useCallback(async () => {
    if (!selectedSuite || !runConfig.provider || !runConfig.model) return

    setShowRunModal(false)
    setIsRunning(true)
    setRunProgress({ current: 0, total: testCases.length, currentCase: '' })

    const callbacks: TestStreamCallbacks = {
      onStart: (data) => {
        setRunProgress(prev => ({ ...prev, total: data.total_cases }))
      },
      onCaseStart: (data) => {
        setRunProgress(prev => ({ ...prev, currentCase: data.case_name }))
      },
      onCaseComplete: () => {
        setRunProgress(prev => ({ ...prev, current: prev.current + 1 }))
      },
      onComplete: async () => {
        setIsRunning(false)
        setRunProgress({ current: 0, total: 0, currentCase: '' })
        onComplete()
      },
      onError: (data) => {
        setIsRunning(false)
        onError(data.message)
      },
    }

    testsApi.runTestsStream(
      selectedSuite.id,
      runConfig.provider,
      runConfig.model,
      callbacks,
      true,
      runConfig.evaluatorProvider || undefined,
      runConfig.evaluatorModel || undefined
    )
  }, [selectedSuite, testCases.length, runConfig, onComplete, onError])

  const selectedProvider = providers.find(p => p.name === runConfig.provider)

  return {
    showRunModal,
    setShowRunModal,
    isRunning,
    runProgress,
    runConfig,
    setRunConfig,
    selectedProvider,
    openRunModal,
    handleRunTests,
  }
}
