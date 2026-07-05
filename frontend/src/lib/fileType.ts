/**
 * Single source of truth for document file-type badge styling.
 *
 * File types reuse the shared `--source-type-*` accent hues (a small
 * categorical palette) rather than introducing a parallel token family — the
 * hues already line up by color (pdf≈red, docx≈blue, md≈purple, html≈orange,
 * url≈cyan), and keeping the token surface small is easier for agents to reason
 * about. Each badge is a theme-aware tinted background + solid text + subtle
 * border. Do not hardcode palette colors at call sites; extend this map.
 */
const FILE_TYPE_BADGE: Record<string, string> = {
  pdf: 'bg-source-type-youtube/15 text-source-type-youtube border-source-type-youtube/30',
  docx: 'bg-source-type-url/15 text-source-type-url border-source-type-url/30',
  md: 'bg-source-type-directory/15 text-source-type-directory border-source-type-directory/30',
  html: 'bg-source-type-file/15 text-source-type-file border-source-type-file/30',
  url: 'bg-source-type-collection/15 text-source-type-collection border-source-type-collection/30',
  txt: 'bg-muted text-muted-foreground border-border',
}

const FALLBACK = 'bg-muted text-muted-foreground border-border'

export function getFileTypeBadgeClass(type: string | null | undefined): string {
  if (!type) return FALLBACK
  return FILE_TYPE_BADGE[type.toLowerCase()] ?? FALLBACK
}
