import { useState, useCallback } from 'react'
import { testsApi, TestSuite, TestCase, TestCaseCreate } from '../../services/api'

interface UseCaseManagementOptions {
  selectedSuite: TestSuite | null
  setTestCases: (updater: (prev: TestCase[]) => TestCase[]) => void
  onError: (error: string) => void
}

export function useCaseManagement({
  selectedSuite,
  setTestCases,
  onError,
}: UseCaseManagementOptions) {
  const [showAddModal, setShowAddModal] = useState(false)
  const [editCase, setEditCase] = useState<TestCase | null>(null)
  const [deleteCase, setDeleteCase] = useState<TestCase | null>(null)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const [form, setForm] = useState<TestCaseCreate>({
    suite_id: '',
    name: '',
    input_text: '',
    expected_output: '',
    evaluation_criteria: '',
    expected_sources: [],
  })

  const resetForm = useCallback(() => {
    setForm({
      suite_id: selectedSuite?.id || '',
      name: '',
      input_text: '',
      expected_output: '',
      evaluation_criteria: '',
      expected_sources: [],
    })
  }, [selectedSuite])

  const openAdd = useCallback(() => {
    resetForm()
    setShowAddModal(true)
  }, [resetForm])

  const openEdit = useCallback((tc: TestCase) => {
    setForm({
      suite_id: tc.suite_id,
      name: tc.name,
      input_text: tc.input_text,
      expected_output: tc.expected_output || '',
      evaluation_criteria: tc.evaluation_criteria || '',
      expected_sources: tc.expected_sources || [],
    })
    setEditCase(tc)
  }, [])

  const closeModal = useCallback(() => {
    setShowAddModal(false)
    setEditCase(null)
    resetForm()
  }, [resetForm])

  const handleCreate = useCallback(async () => {
    if (!form.name.trim() || !form.input_text.trim() || !selectedSuite) return
    try {
      setSaving(true)
      const created = await testsApi.createCase({
        ...form,
        suite_id: selectedSuite.id,
      })
      setTestCases(prev => [...prev, created])
      closeModal()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to create test case')
    } finally {
      setSaving(false)
    }
  }, [form, selectedSuite, setTestCases, closeModal, onError])

  const handleUpdate = useCallback(async () => {
    if (!editCase || !form.name.trim() || !form.input_text.trim()) return
    try {
      setSaving(true)
      const updated = await testsApi.updateCase(editCase.id, {
        name: form.name,
        input_text: form.input_text,
        expected_output: form.expected_output || undefined,
        evaluation_criteria: form.evaluation_criteria || undefined,
        expected_sources: form.expected_sources && form.expected_sources.length > 0 ? form.expected_sources : undefined,
      })
      setTestCases(prev => prev.map(c => c.id === updated.id ? updated : c))
      closeModal()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to update test case')
    } finally {
      setSaving(false)
    }
  }, [editCase, form, setTestCases, closeModal, onError])

  const handleDelete = useCallback(async () => {
    if (!deleteCase) return
    try {
      setDeleting(true)
      await testsApi.deleteCase(deleteCase.id)
      setTestCases(prev => prev.filter(c => c.id !== deleteCase.id))
      setDeleteCase(null)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to delete test case')
    } finally {
      setDeleting(false)
    }
  }, [deleteCase, setTestCases, onError])

  return {
    showAddModal,
    editCase,
    deleteCase,
    form,
    setForm,
    saving,
    deleting,
    openAdd,
    openEdit,
    closeModal,
    setDeleteCase,
    handleCreate,
    handleUpdate,
    handleDelete,
  }
}
