import { useState, useRef, useCallback, useMemo } from 'react'

export interface ListItem {
  id: string
}

export interface UseListSelectionOptions<T extends ListItem> {
  items: T[]
  getItemId?: (item: T) => string
}

export interface UseListSelectionReturn {
  selectedIds: Set<string>
  setSelectedIds: React.Dispatch<React.SetStateAction<Set<string>>>
  toggleSelection: (id: string, shiftKey?: boolean) => void
  toggleSelectAll: () => void
  clearSelection: () => void
  isSelected: (id: string) => boolean
  isAllSelected: boolean
  isIndeterminate: boolean
  selectedCount: number
}

/**
 * Reusable hook for list selection with shift-click range support.
 *
 * Usage:
 * ```tsx
 * const { selectedIds, toggleSelection, toggleSelectAll } = useListSelection({ items })
 *
 * // In your list item click handler:
 * onClick={(e) => toggleSelection(item.id, e.shiftKey)}
 * ```
 */
export function useListSelection<T extends ListItem>({
  items,
  getItemId = (item) => item.id,
}: UseListSelectionOptions<T>): UseListSelectionReturn {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const lastSelectedId = useRef<string | null>(null)

  const itemIds = useMemo(() => items.map(getItemId), [items, getItemId])

  const toggleSelection = useCallback((id: string, shiftKey = false) => {
    setSelectedIds(prev => {
      const next = new Set(prev)

      // Shift-click range selection
      if (shiftKey && lastSelectedId.current && lastSelectedId.current !== id) {
        const lastIndex = itemIds.indexOf(lastSelectedId.current)
        const currentIndex = itemIds.indexOf(id)

        if (lastIndex !== -1 && currentIndex !== -1) {
          const start = Math.min(lastIndex, currentIndex)
          const end = Math.max(lastIndex, currentIndex)

          // Select all items in range
          for (let i = start; i <= end; i++) {
            next.add(itemIds[i])
          }
          return next
        }
      }

      // Normal toggle
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }

      // Track last selected for shift-click
      lastSelectedId.current = id
      return next
    })
  }, [itemIds])

  const toggleSelectAll = useCallback(() => {
    setSelectedIds(prev => {
      if (prev.size === items.length && items.length > 0) {
        return new Set()
      }
      return new Set(itemIds)
    })
  }, [items.length, itemIds])

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set())
    lastSelectedId.current = null
  }, [])

  const isSelected = useCallback((id: string) => selectedIds.has(id), [selectedIds])

  const isAllSelected = selectedIds.size === items.length && items.length > 0
  const isIndeterminate = selectedIds.size > 0 && selectedIds.size < items.length
  const selectedCount = selectedIds.size

  return {
    selectedIds,
    setSelectedIds,
    toggleSelection,
    toggleSelectAll,
    clearSelection,
    isSelected,
    isAllSelected,
    isIndeterminate,
    selectedCount,
  }
}
