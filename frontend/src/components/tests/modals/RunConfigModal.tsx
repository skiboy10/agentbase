import { useMemo } from 'react'
import { Play } from 'lucide-react'
import { Provider } from '../../../services/api'
import { getEnabledModelsForProvider } from '../../../pages/ProvidersPage'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface RunConfig {
  provider: string
  model: string
  evaluatorProvider: string
  evaluatorModel: string
}

interface RunConfigModalProps {
  open: boolean
  providers: Provider[]
  selectedProvider: Provider | undefined
  runConfig: RunConfig
  setRunConfig: (updater: (prev: RunConfig) => RunConfig) => void
  onClose: () => void
  onRun: () => void
}

export default function RunConfigModal({
  open,
  providers,
  selectedProvider,
  runConfig,
  setRunConfig,
  onClose,
  onRun,
}: RunConfigModalProps) {
  // Get enabled models for the selected provider
  const enabledModels = useMemo(() => {
    if (!selectedProvider) return []
    return getEnabledModelsForProvider(selectedProvider)
  }, [selectedProvider])

  // Get enabled models for the evaluator provider
  const evaluatorProvider = useMemo(
    () => providers.find(p => p.name === runConfig.evaluatorProvider),
    [providers, runConfig.evaluatorProvider]
  )
  const evaluatorModels = useMemo(() => {
    if (!evaluatorProvider) return []
    return getEnabledModelsForProvider(evaluatorProvider)
  }, [evaluatorProvider])

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Run Tests</DialogTitle>
          <DialogDescription>
            Select a model to run the test suite against.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>Provider</Label>
            <Select
              value={runConfig.provider}
              onValueChange={value => {
                const prov = providers.find(p => p.name === value)
                const provEnabledModels = prov
                  ? getEnabledModelsForProvider(prov)
                  : []
                setRunConfig(prev => ({
                  ...prev,
                  provider: value,
                  model: provEnabledModels[0] || '',
                }))
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select provider" />
              </SelectTrigger>
              <SelectContent>
                {providers.map(p => (
                  <SelectItem key={p.name} value={p.name}>{p.display_name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Model</Label>
            <Select
              value={runConfig.model}
              onValueChange={value => setRunConfig(prev => ({ ...prev, model: value }))}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent>
                {enabledModels.map(m => (
                  <SelectItem key={m} value={m}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="pt-4 border-t space-y-4">
            <div>
              <Label className="text-sm font-medium">Evaluator Override (optional)</Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Use a different model to judge responses. Defaults to the generating model.
              </p>
            </div>
            <div className="space-y-2">
              <Label>Evaluator Provider</Label>
              <Select
                value={runConfig.evaluatorProvider || '__same__'}
                onValueChange={value => {
                  if (value === '__same__') {
                    setRunConfig(prev => ({ ...prev, evaluatorProvider: '', evaluatorModel: '' }))
                  } else {
                    const prov = providers.find(p => p.name === value)
                    const models = prov ? getEnabledModelsForProvider(prov) : []
                    setRunConfig(prev => ({
                      ...prev,
                      evaluatorProvider: value,
                      evaluatorModel: models[0] || '',
                    }))
                  }
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Same as generating model" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__same__">Same as generating model</SelectItem>
                  {providers.map(p => (
                    <SelectItem key={p.name} value={p.name}>{p.display_name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {runConfig.evaluatorProvider && evaluatorModels.length > 0 && (
              <div className="space-y-2">
                <Label>Evaluator Model</Label>
                <Select
                  value={runConfig.evaluatorModel}
                  onValueChange={value => setRunConfig(prev => ({ ...prev, evaluatorModel: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    {evaluatorModels.map(m => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            onClick={onRun}
            disabled={!runConfig.provider || !runConfig.model}
          >
            <Play className="w-4 h-4 mr-2" />
            Run Tests
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
