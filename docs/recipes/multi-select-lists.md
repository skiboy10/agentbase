# Multi-Select Lists

All multi-select lists in Agentbase must support standard selection behaviors.

## Behaviors

| Action | Behavior |
|--------|----------|
| Click | Toggle single item selection |
| Shift+Click | Select range from last clicked to current item |
| Select All | Toggle all items (header checkbox or button) |

## Implementation with useListSelection Hook

Use `useListSelection` hook from `frontend/src/hooks/useListSelection.ts`:

```tsx
const { selectedIds, toggleSelection, toggleSelectAll, isSelected } = useListSelection({ items })

// In list item click handler:
<div onClick={(e) => toggleSelection(item.id, e.shiftKey)}>
  <Checkbox checked={isSelected(item.id)} />
  {item.name}
</div>
```

## Controlled State (Props-Based Selection)

For controlled state, implement shift-click directly:

```tsx
const lastClickedId = useRef<string | null>(null)

const handleClick = (id: string, shiftKey: boolean) => {
  if (shiftKey && lastClickedId.current) {
    // Select range between lastClickedId and id
    const start = items.findIndex(i => i.id === lastClickedId.current)
    const end = items.findIndex(i => i.id === id)
    const range = items.slice(Math.min(start, end), Math.max(start, end) + 1)
    onSelectionChange([...new Set([...selected, ...range.map(i => i.id)])])
  } else {
    // Toggle single item
    onSelectionChange(selected.includes(id)
      ? selected.filter(s => s !== id)
      : [...selected, id])
    lastClickedId.current = id
  }
}
```

Add `select-none` class to prevent text selection during shift-click.
