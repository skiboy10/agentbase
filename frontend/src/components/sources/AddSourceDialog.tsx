/**
 * Backward compatibility re-exports from modular addSource/ directory.
 *
 * The AddSourceDialog has been split into:
 * - addSource/index.tsx: Main dialog component
 * - addSource/hooks/useEmbeddingConfig.ts: Embedding config hook
 * - addSource/EmbeddingModelSelector.tsx: Reusable selector component
 * - addSource/DirectorySourceForm.tsx: Directory source form
 * - addSource/FileSourceForm.tsx: File upload form
 * - addSource/UrlSourceForm.tsx: URL scanning form (both stages)
 * - addSource/CollectionAdoptionForm.tsx: Collection adoption form
 *
 * Import from this file for backward compatibility,
 * or directly from components/sources/addSource/* for explicit imports.
 */

// Re-export the main component as default
export { default } from './addSource'

// Re-export all named exports
export * from './addSource'
