/**
 * Single source of truth for HTTP-method label and badge styling.
 *
 * Colors resolve through the `--cat-http-*` design tokens (defined in
 * `index.css`, mapped in `tailwind.config.js`), so they are theme-aware in
 * light and dark. Mirror of the `sourceType` / `fileType` pattern.
 *
 * Do not hardcode palette colors at call sites; extend these maps instead.
 */

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'

/** Text-only class per method, for inline labels (e.g. the API reference TOC). */
const METHOD_TEXT_CLASSES: Record<string, string> = {
  GET: 'text-cat-http-get',
  POST: 'text-cat-http-post',
  PUT: 'text-cat-http-put',
  DELETE: 'text-cat-http-delete',
  PATCH: 'text-cat-http-patch',
}

/** Text + tinted border classes per method, for outline Badge components. */
const METHOD_BADGE_CLASSES: Record<string, string> = {
  GET: 'text-cat-http-get border-cat-http-get/50',
  POST: 'text-cat-http-post border-cat-http-post/50',
  PUT: 'text-cat-http-put border-cat-http-put/50',
  DELETE: 'text-cat-http-delete border-cat-http-delete/50',
  PATCH: 'text-cat-http-patch border-cat-http-patch/50',
}

const FALLBACK_TEXT_CLASS = 'text-muted-foreground'
const FALLBACK_BADGE_CLASS = 'text-muted-foreground border-border'

/**
 * Returns the theme-aware Tailwind text class for the given HTTP method.
 * Unknown, null, or undefined methods fall back to muted foreground.
 */
export function getHttpMethodClass(method: string | null | undefined): string {
  if (!method) return FALLBACK_TEXT_CLASS
  return METHOD_TEXT_CLASSES[method.toUpperCase()] ?? FALLBACK_TEXT_CLASS
}

/**
 * Returns theme-aware Tailwind text and border classes for the given HTTP
 * method, for use with an outline-variant Badge. Unknown, null, or undefined
 * methods fall back to muted foreground with the default border.
 */
export function getHttpMethodBadgeClass(method: string | null | undefined): string {
  if (!method) return FALLBACK_BADGE_CLASS
  return METHOD_BADGE_CLASSES[method.toUpperCase()] ?? FALLBACK_BADGE_CLASS
}
