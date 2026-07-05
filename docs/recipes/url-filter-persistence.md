# URL Filter State Persistence

For pages with filters, use URL search params as the single source of truth to ensure filters persist across navigation (browser back/forward, link clicks).

## Implementation

Use `useUrlFilters` hook pattern (see `extensions/.../frontend/hooks/useUrlFilters.ts` for reference):

```tsx
const { filters, updateFilter, clearFilters, hasActiveFilters } = useUrlFilters<MyFilters>(
  ['status', 'type', 'search', 'tags'],  // Filter keys to track
  { arrayKeys: ['tags'] }                 // Keys stored as comma-separated arrays
);

// In filter controls:
<select
  value={filters.status || ''}
  onChange={(e) => updateFilter('status', e.target.value || undefined)}
/>
```

## Why URL-Based

- Browser back/forward navigation works correctly
- Filters can be bookmarked/shared
- No state sync bugs between URL and React state
