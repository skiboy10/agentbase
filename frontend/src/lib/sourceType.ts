import {
  Globe,
  FolderOpen,
  FileText,
  Play,
  Database,
  type LucideIcon,
} from 'lucide-react'

/**
 * Single source of truth for how a source type is presented in the UI.
 *
 * Colors resolve through the `--source-type-*` design tokens (defined in
 * `index.css`, mapped in `tailwind.config.js`), so they are theme-aware in
 * light and dark. The chip pattern is a tinted background (the token at 15%
 * alpha) paired with the solid accent as the icon/text color.
 *
 * Read this file to learn — for both humans and agents — exactly what icon and
 * color any source type renders with. Do not hardcode palette colors at call
 * sites; extend this map instead.
 */
export type SourceType = 'url' | 'directory' | 'file' | 'youtube' | 'collection'

export interface SourceTypeMeta {
  label: string
  icon: LucideIcon
  /** Saturated accent for the icon/text (token-driven, theme-aware). */
  text: string
  /** Tinted background for an icon chip; pairs with `text`. */
  bg: string
}

const META: Record<SourceType, SourceTypeMeta> = {
  url: { label: 'URL', icon: Globe, text: 'text-source-type-url', bg: 'bg-source-type-url/15' },
  directory: { label: 'Directory', icon: FolderOpen, text: 'text-source-type-directory', bg: 'bg-source-type-directory/15' },
  file: { label: 'File', icon: FileText, text: 'text-source-type-file', bg: 'bg-source-type-file/15' },
  youtube: { label: 'YouTube', icon: Play, text: 'text-source-type-youtube', bg: 'bg-source-type-youtube/15' },
  collection: { label: 'Collection', icon: Database, text: 'text-source-type-collection', bg: 'bg-source-type-collection/15' },
}

const FALLBACK: SourceTypeMeta = {
  label: 'Source',
  icon: FileText,
  text: 'text-muted-foreground',
  bg: 'bg-muted',
}

export function getSourceTypeMeta(type: string | null | undefined): SourceTypeMeta {
  if (!type) return FALLBACK
  return META[type as SourceType] ?? FALLBACK
}

/**
 * Logical "kind" used by the Sources page type filter.
 *
 * This is a filtering concern distinct from the raw `source_type`: a directory
 * *root* and its *sub-source* views both carry `source_type === 'directory'`,
 * but users filter them separately. Raw types are also relabelled to the
 * user-facing filter vocabulary (url → Scrape, file → Uploaded). Adopted
 * `collection` sources match no kind and are intentionally excluded from the
 * filter chips (they still appear when no type filter is active).
 */
export type SourceKind = 'directory' | 'sub-source' | 'scrape' | 'uploaded' | 'youtube'

/** Display order + label for the type filter chips. */
export const SOURCE_KINDS: { kind: SourceKind; label: string }[] = [
  { kind: 'directory', label: 'Directory' },
  { kind: 'sub-source', label: 'Sub-source' },
  { kind: 'scrape', label: 'Scrape' },
  { kind: 'uploaded', label: 'Uploaded' },
  { kind: 'youtube', label: 'YouTube' },
]

/**
 * Classify a source into its filter kind, or `null` if it matches none of the
 * filterable kinds (e.g. adopted `collection` sources). Sub-sources are detected
 * first because they share `source_type === 'directory'` with their root.
 */
export function getSourceKind(
  source: { source_type: string; parent_source_id?: string | null }
): SourceKind | null {
  if (source.parent_source_id) return 'sub-source'
  switch (source.source_type) {
    case 'directory':
      return 'directory'
    case 'url':
      return 'scrape'
    case 'file':
      return 'uploaded'
    case 'youtube':
      return 'youtube'
    default:
      return null
  }
}
