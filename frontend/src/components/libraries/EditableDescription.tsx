import { useState, useRef, useEffect, useCallback } from 'react'
import { Pencil, Check, X } from 'lucide-react'
import { libraryApi } from '../../services/api/library'
import type { Library } from '../../services/api/types/library'

interface EditableDescriptionProps {
  kb: Library
  onUpdated: (updated: Library) => void
}

/**
 * Inline-editable library description shown in the Library detail header.
 *
 * Behaviour:
 * - Pencil icon next to the text enters edit mode.
 * - Enter key saves; Esc cancels.
 * - Optimistic update: local state reflects the new value immediately while
 *   the PATCH request is in flight.  On error, the displayed value is reverted
 *   (unless a newer one arrived meanwhile), the draft is preserved so the user
 *   can retry, and an inline error message is displayed below the textarea.
 */
export default function EditableDescription({ kb, onUpdated }: EditableDescriptionProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(kb.description ?? '')
  const [saving, setSaving] = useState(false)
  const [inlineError, setInlineError] = useState<string | null>(null)

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const editBtnRef = useRef<HTMLButtonElement>(null)
  // Track the latest kb prop so the revert on PATCH failure uses fresh data.
  const latestKbRef = useRef(kb)
  useEffect(() => {
    latestKbRef.current = kb
  }, [kb])

  // Keep draft in sync when the parent refreshes the library (e.g. background poll).
  useEffect(() => {
    if (!editing) {
      setDraft(kb.description ?? '')
    }
  }, [kb.description, editing])

  // Focus and place cursor at the end of the textarea when entering edit mode.
  useEffect(() => {
    if (editing && textareaRef.current) {
      const el = textareaRef.current
      el.focus()
      el.selectionStart = el.selectionEnd = el.value.length
    }
  }, [editing])

  const exitEditing = useCallback(() => {
    setEditing(false)
    // Return focus to the pencil button so keyboard users don't lose their place.
    requestAnimationFrame(() => {
      editBtnRef.current?.focus()
    })
  }, [])

  const handleEdit = () => {
    setDraft(kb.description ?? '')
    setInlineError(null)
    setEditing(true)
  }

  const handleCancel = useCallback(() => {
    setDraft(latestKbRef.current.description ?? '')
    setInlineError(null)
    exitEditing()
  }, [exitEditing])

  const handleSave = useCallback(async () => {
    const trimmed = draft.trim()
    // Snapshot the current kb at save time to correctly scope the optimistic update.
    const kbAtSave = latestKbRef.current
    // No-op if nothing changed.
    const current = kbAtSave.description ?? ''
    if (trimmed === current) {
      exitEditing()
      return
    }

    // Optimistic update.
    const optimistic: Library = { ...kbAtSave, description: trimmed || null }
    onUpdated(optimistic)
    setSaving(true)
    setInlineError(null)

    try {
      const updated = await libraryApi.update(kbAtSave.id, {
        description: trimmed || null,
      })
      onUpdated(updated)
      exitEditing()
    } catch (err) {
      // Revert only the description field, and only if it still holds our
      // optimistic value — a background poll may have brought in a newer
      // description while the save was in flight; don't clobber it.
      const latest = latestKbRef.current
      if (latest.description === optimistic.description) {
        onUpdated({ ...latest, description: kbAtSave.description })
      }
      // Keep the draft intact so the user can retry without retyping.
      setInlineError(err instanceof Error ? err.message : 'Failed to save description')
    } finally {
      setSaving(false)
    }
  }, [draft, onUpdated, exitEditing])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSave()
    } else if (e.key === 'Escape') {
      handleCancel()
    }
  }

  if (editing) {
    return (
      <div className="mt-0.5">
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={saving}
          rows={2}
          placeholder="Add a short description…"
          aria-label="Library description"
          aria-invalid={!!inlineError}
          aria-describedby={inlineError ? 'library-description-error' : undefined}
          className={[
            'w-full resize-none rounded-md border bg-background px-2.5 py-1.5',
            'text-sm text-foreground placeholder:text-muted-foreground/50',
            'focus:outline-none focus:ring-1 focus:ring-ring',
            'disabled:opacity-60',
            inlineError ? 'border-destructive' : 'border-input',
          ].join(' ')}
        />
        {inlineError && (
          <p id="library-description-error" className="mt-1 text-xs text-destructive" role="alert">
            {inlineError}
          </p>
        )}
        <div className="mt-1.5 flex items-center gap-1.5">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            aria-label="Save description"
            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-60 focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <Check className="w-3 h-3" />
            Save
          </button>
          <button
            type="button"
            onClick={handleCancel}
            disabled={saving}
            aria-label="Cancel editing"
            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-60 focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <X className="w-3 h-3" />
            Cancel
          </button>
          <span className="text-xs text-muted-foreground/60">
            Enter to save · Esc to cancel
          </span>
        </div>
      </div>
    )
  }

  // Read mode.
  return (
    <div className="group/desc flex items-start gap-1.5 mt-0.5">
      {kb.description ? (
        <p className="text-muted-foreground text-sm">{kb.description}</p>
      ) : (
        <p className="text-muted-foreground/40 text-sm italic">No description</p>
      )}
      <button
        ref={editBtnRef}
        type="button"
        onClick={handleEdit}
        aria-label="Edit description"
        className={[
          'shrink-0 mt-px rounded p-0.5',
          'text-muted-foreground/30 hover:text-muted-foreground',
          'opacity-0 group-hover/desc:opacity-100 focus:opacity-100',
          'transition-opacity focus:outline-none focus:ring-1 focus:ring-ring',
        ].join(' ')}
      >
        <Pencil className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}
