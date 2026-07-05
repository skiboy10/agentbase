import { useState, KeyboardEvent } from 'react'
import { Loader2, X } from 'lucide-react'
import { TestCase, TestCaseCreate } from '../../../services/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'

interface CaseFormModalProps {
  open: boolean
  editCase: TestCase | null
  form: TestCaseCreate
  setForm: (updater: (prev: TestCaseCreate) => TestCaseCreate) => void
  saving: boolean
  onClose: () => void
  onCreate: () => void
  onUpdate: () => void
}

export default function CaseFormModal({
  open,
  editCase,
  form,
  setForm,
  saving,
  onClose,
  onCreate,
  onUpdate,
}: CaseFormModalProps) {
  const [sourceInput, setSourceInput] = useState('')

  const handleSourceKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      const value = sourceInput.trim()
      if (value && !(form.expected_sources || []).includes(value)) {
        setForm(prev => ({
          ...prev,
          expected_sources: [...(prev.expected_sources || []), value],
        }))
      }
      setSourceInput('')
    }
  }

  const removeSource = (source: string) => {
    setForm(prev => ({
      ...prev,
      expected_sources: (prev.expected_sources || []).filter((s: string) => s !== source),
    }))
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{editCase ? 'Edit Test Case' : 'Add Test Case'}</DialogTitle>
          <DialogDescription>
            {editCase ? 'Update the test case details.' : 'Add a new test case with input and expected output.'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="case-name">Name</Label>
            <Input
              id="case-name"
              value={form.name}
              onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
              placeholder="e.g., Basic greeting test"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="case-input">Input</Label>
            <Textarea
              id="case-input"
              value={form.input_text}
              onChange={e => setForm(prev => ({ ...prev, input_text: e.target.value }))}
              placeholder="What question should be asked?"
              rows={3}
              className="font-mono text-sm"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="case-expected">Expected Output (optional)</Label>
            <Textarea
              id="case-expected"
              value={form.expected_output}
              onChange={e => setForm(prev => ({ ...prev, expected_output: e.target.value }))}
              placeholder="What should the response contain or be like?"
              rows={3}
              className="font-mono text-sm"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="case-criteria">Evaluation Criteria (optional)</Label>
            <Textarea
              id="case-criteria"
              value={form.evaluation_criteria}
              onChange={e => setForm(prev => ({ ...prev, evaluation_criteria: e.target.value }))}
              placeholder="What criteria should be used to evaluate the response?"
              rows={2}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="case-sources">Expected Sources (optional)</Label>
            <p className="text-xs text-muted-foreground">
              Source names that should appear in retrieval results. Press Enter to add.
            </p>
            {(form.expected_sources || []).length > 0 && (
              <div className="flex flex-wrap gap-1">
                {(form.expected_sources || []).map((source: string) => (
                  <Badge key={source} variant="secondary" className="gap-1">
                    {source}
                    <button
                      type="button"
                      onClick={() => removeSource(source)}
                      className="ml-1 hover:text-destructive"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
            <Input
              id="case-sources"
              value={sourceInput}
              onChange={e => setSourceInput(e.target.value)}
              onKeyDown={handleSourceKeyDown}
              placeholder="e.g., Company Policy 2024"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            onClick={editCase ? onUpdate : onCreate}
            disabled={!form.name.trim() || !form.input_text.trim() || saving}
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
            {editCase ? 'Save' : 'Add'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
