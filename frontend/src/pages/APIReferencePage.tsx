import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Search, Copy, Check, ChevronRight, ChevronDown, Book, Loader2 } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { getHttpMethodClass, getHttpMethodBadgeClass } from '@/lib/httpMethod'

/**
 * Recursively extract plain text from a React node tree.
 * Handles strings, numbers, arrays, and React elements with children.
 * Used to build stable heading IDs for nodes containing inline code or bold.
 */
export function extractTextFromNode(node: React.ReactNode): string {
  if (node === null || node === undefined) return ''
  if (typeof node === 'string') return node
  if (typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractTextFromNode).join('')
  if (typeof node === 'object' && 'props' in (node as React.ReactElement)) {
    const el = node as React.ReactElement<{ children?: React.ReactNode }>
    return extractTextFromNode(el.props?.children)
  }
  return ''
}

/** Slugify plain heading text (shared by TOC builder and heading renderers). */
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
}

/**
 * Uniquify a slug against a seen-count map: first occurrence returns the base
 * slug, repeats return base-1, base-2, ... (GitHub anchor convention). The same
 * map must be used in document order so TOC ids match rendered heading ids.
 */
export function uniqueSlug(base: string, counts: Map<string, number>): string {
  const seen = counts.get(base) ?? 0
  counts.set(base, seen + 1)
  return seen === 0 ? base : `${base}-${seen}`
}

interface TocItem {
  id: string
  text: string
  level: number
  method?: string
}

interface CopyButtonProps {
  text: string
}

function CopyButton({ text }: CopyButtonProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [text])

  return (
    <Button
      variant="ghost"
      size="sm"
      aria-label="Copy code"
      className="absolute top-2 right-2 h-8 w-8 p-0 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
      onClick={handleCopy}
    >
      {copied ? (
        <Check className="h-4 w-4 text-status-success" />
      ) : (
        <Copy className="h-4 w-4" />
      )}
    </Button>
  )
}


export default function APIReferencePage() {
  const [content, setContent] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [activeSection, setActiveSection] = useState<string>('')
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set())
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  // Per-render-pass slug counts for the markdown heading renderers. Reset
  // immediately before ReactMarkdown renders so repeated headings (e.g.
  // multiple "### Response") get unique ids matching the TOC builder's output.
  const headingSlugCountsRef = useRef(new Map<string, number>())

  // Fetch API.md content
  useEffect(() => {
    const fetchContent = async () => {
      try {
        const response = await fetch('/api/docs/api-reference')
        if (!response.ok) {
          throw new Error('Failed to load API documentation')
        }
        const text = await response.text()
        setContent(text)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }

    fetchContent()
  }, [])

  // Parse table of contents from markdown headings, skipping fenced code blocks.
  // Slugs are uniquified in document order so they match the rendered heading ids.
  const tocItems = useMemo((): TocItem[] => {
    const items: TocItem[] = []
    const slugCounts = new Map<string, number>()
    let inFence = false

    for (const line of content.split('\n')) {
      // Track fenced code block boundaries (``` or ~~~)
      if (/^(`{3,}|~{3,})/.test(line)) {
        inFence = !inFence
        continue
      }
      if (inFence) continue

      const headingMatch = /^(#{1,3})\s+(.+)$/.exec(line)
      if (!headingMatch) continue

      const level = headingMatch[1].length
      const text = headingMatch[2].trim()
      const id = uniqueSlug(slugify(text), slugCounts)

      // Extract HTTP method if present (e.g., "GET /api/projects")
      const methodMatch = text.match(/^(GET|POST|PUT|DELETE|PATCH)\s+/)

      items.push({
        id,
        text,
        level,
        method: methodMatch ? methodMatch[1] : undefined,
      })
    }

    return items
  }, [content])

  // Filter TOC items based on search
  const filteredTocItems = useMemo(() => {
    if (!searchQuery) return tocItems
    const query = searchQuery.toLowerCase()
    return tocItems.filter(item =>
      item.text.toLowerCase().includes(query)
    )
  }, [tocItems, searchQuery])

  // Get section headers (level 2 headings)
  const sections = useMemo(() => {
    return tocItems.filter(item => item.level === 2)
  }, [tocItems])

  // Get children for a section
  const getSectionChildren = useCallback((sectionId: string) => {
    const sectionIndex = tocItems.findIndex(item => item.id === sectionId)
    if (sectionIndex === -1) return []

    const children: TocItem[] = []
    for (let i = sectionIndex + 1; i < tocItems.length; i++) {
      const item = tocItems[i]
      if (item.level <= 2) break
      children.push(item)
    }
    return children
  }, [tocItems])

  // Toggle section expansion
  const toggleSection = useCallback((sectionId: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      if (next.has(sectionId)) {
        next.delete(sectionId)
      } else {
        next.add(sectionId)
      }
      return next
    })
  }, [])

  // Scroll to section
  const scrollToSection = useCallback((id: string) => {
    const element = document.getElementById(id)
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' })
      setActiveSection(id)
    }
  }, [])

  // Track active section on scroll.
  // Must attach to the Radix ScrollArea viewport — the root element has
  // overflow:hidden and does not receive scroll events.
  // Depends on `loading` too: if content is refetched and the string is
  // identical, the ScrollArea remounts (loading toggled) without a content
  // change — the effect must re-run to re-attach the listener.
  useEffect(() => {
    if (loading) return
    let rafId: number | null = null

    const handleScroll = () => {
      if (rafId !== null) return
      rafId = requestAnimationFrame(() => {
        rafId = null
        const headings = document.querySelectorAll('h1[id], h2[id], h3[id]')
        let current = ''
        headings.forEach(heading => {
          const rect = heading.getBoundingClientRect()
          if (rect.top <= 100) {
            current = heading.id
          }
        })
        if (current) {
          setActiveSection(current)
        }
      })
    }

    // The Radix ScrollArea root has overflow:hidden; the actual scrolling
    // element is the inner viewport (data-radix-scroll-area-viewport).
    const root = scrollAreaRef.current
    const viewport = root?.querySelector('[data-radix-scroll-area-viewport]') as HTMLElement | null
    if (viewport) {
      viewport.addEventListener('scroll', handleScroll, { passive: true })
      return () => {
        viewport.removeEventListener('scroll', handleScroll)
        if (rafId !== null) cancelAnimationFrame(rafId)
      }
    }
  }, [content, loading])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-primary mx-auto mb-4" />
          <p className="text-muted-foreground">Loading API documentation...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Book className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-foreground mb-2">Failed to load documentation</h2>
          <p className="text-muted-foreground mb-4">{error}</p>
          <Button onClick={() => window.location.reload()}>
            Try Again
          </Button>
        </div>
      </div>
    )
  }

  // Reset heading slug counts for this render pass: the ReactMarkdown heading
  // components below execute in document order during this same render, so a
  // fresh map keeps their ids in sync with the TOC builder's uniquified slugs.
  headingSlugCountsRef.current = new Map()

  return (
    <div className="flex h-full">
      {/* Table of Contents Sidebar */}
      <div className="w-72 border-r border-border bg-card flex flex-col">
        <div className="p-4 border-b border-border">
          <h2 className="text-lg font-semibold text-foreground mb-3 flex items-center gap-2">
            <Book className="w-5 h-5 text-primary" />
            API Reference
          </h2>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search endpoints..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        <ScrollArea className="flex-1">
          <nav className="p-2">
            {searchQuery ? (
              // Flat filtered list when searching
              <div className="space-y-1">
                {filteredTocItems.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => scrollToSection(item.id)}
                    className={cn(
                      'w-full text-left px-3 py-2 rounded-md text-sm transition-colors',
                      'hover:bg-muted',
                      activeSection === item.id
                        ? 'bg-primary/10 text-primary font-medium'
                        : 'text-muted-foreground'
                    )}
                    style={{ paddingLeft: `${(item.level - 1) * 12 + 12}px` }}
                  >
                    <span className="flex items-center gap-2">
                      {item.method && (
                        <Badge
                          variant="outline"
                          className={cn('text-xs px-1.5 py-0', getHttpMethodBadgeClass(item.method))}
                        >
                          {item.method}
                        </Badge>
                      )}
                      <span className="truncate">{item.text.replace(/^(GET|POST|PUT|DELETE|PATCH)\s+/, '')}</span>
                    </span>
                  </button>
                ))}
                {filteredTocItems.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-4">
                    No matching endpoints
                  </p>
                )}
              </div>
            ) : (
              // Collapsible tree when not searching
              <div className="space-y-1">
                {sections.map((section) => {
                  const children = getSectionChildren(section.id)
                  const isExpanded = expandedSections.has(section.id)
                  const hasChildren = children.length > 0

                  return (
                    <div key={section.id}>
                      <button
                        onClick={() => {
                          if (hasChildren) {
                            toggleSection(section.id)
                          }
                          scrollToSection(section.id)
                        }}
                        className={cn(
                          'w-full text-left px-3 py-2 rounded-md text-sm transition-colors flex items-center gap-2',
                          'hover:bg-muted',
                          activeSection === section.id
                            ? 'bg-primary/10 text-primary font-medium'
                            : 'text-foreground'
                        )}
                      >
                        {hasChildren ? (
                          isExpanded ? (
                            <ChevronDown className="w-4 h-4 shrink-0" />
                          ) : (
                            <ChevronRight className="w-4 h-4 shrink-0" />
                          )
                        ) : (
                          <span className="w-4" />
                        )}
                        <span className="truncate">{section.text}</span>
                      </button>

                      {isExpanded && hasChildren && (
                        <div className="ml-4 space-y-1 mt-1">
                          {children.map((child) => (
                            <button
                              key={child.id}
                              onClick={() => scrollToSection(child.id)}
                              className={cn(
                                'w-full text-left px-3 py-1.5 rounded-md text-sm transition-colors',
                                'hover:bg-muted',
                                activeSection === child.id
                                  ? 'bg-primary/10 text-primary font-medium'
                                  : 'text-muted-foreground'
                              )}
                            >
                              <span className="flex items-center gap-2">
                                {child.method && (
                                  <span className={cn('text-xs font-mono font-semibold', getHttpMethodClass(child.method))}>
                                    {child.method}
                                  </span>
                                )}
                                <span className="truncate">
                                  {child.text.replace(/^(GET|POST|PUT|DELETE|PATCH)\s+/, '')}
                                </span>
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </nav>
        </ScrollArea>

      </div>

      {/* Main Content */}
      <ScrollArea ref={scrollAreaRef} className="flex-1" data-api-content>
        <div className="max-w-4xl mx-auto p-8">
          <ReactMarkdown
            components={{
              h1: ({ children, ...props }) => {
                const id = uniqueSlug(slugify(extractTextFromNode(children)), headingSlugCountsRef.current)
                return (
                  <h1
                    id={id}
                    className="text-3xl font-bold text-foreground mb-6 mt-8 first:mt-0 scroll-mt-4"
                    {...props}
                  >
                    {children}
                  </h1>
                )
              },
              h2: ({ children, ...props }) => {
                const id = uniqueSlug(slugify(extractTextFromNode(children)), headingSlugCountsRef.current)
                return (
                  <h2
                    id={id}
                    className="text-2xl font-semibold text-foreground mb-4 mt-8 pb-2 border-b border-border scroll-mt-4"
                    {...props}
                  >
                    {children}
                  </h2>
                )
              },
              h3: ({ children, ...props }) => {
                const text = extractTextFromNode(children)
                const id = uniqueSlug(slugify(text), headingSlugCountsRef.current)

                // Check if this is an endpoint heading
                const methodMatch = text.match(/^(GET|POST|PUT|DELETE|PATCH)\s+(.+)$/)

                if (methodMatch) {
                  const [, method, path] = methodMatch
                  return (
                    <h3
                      id={id}
                      className="flex items-center gap-3 text-lg font-semibold text-foreground mb-3 mt-6 scroll-mt-4"
                      {...props}
                    >
                      <Badge variant="outline" className={cn('font-mono', getHttpMethodBadgeClass(method))}>
                        {method}
                      </Badge>
                      <code className="text-base font-mono bg-muted px-2 py-1 rounded">
                        {path}
                      </code>
                    </h3>
                  )
                }

                return (
                  <h3
                    id={id}
                    className="text-lg font-semibold text-foreground mb-3 mt-6 scroll-mt-4"
                    {...props}
                  >
                    {children}
                  </h3>
                )
              },
              h4: ({ children, ...props }) => (
                <h4 className="text-base font-semibold text-foreground mb-2 mt-4" {...props}>
                  {children}
                </h4>
              ),
              p: ({ children, ...props }) => (
                <p className="text-muted-foreground mb-4 leading-relaxed" {...props}>
                  {children}
                </p>
              ),
              ul: ({ children, ...props }) => (
                <ul className="list-disc list-inside text-muted-foreground mb-4 space-y-1" {...props}>
                  {children}
                </ul>
              ),
              ol: ({ children, ...props }) => (
                <ol className="list-decimal list-inside text-muted-foreground mb-4 space-y-1" {...props}>
                  {children}
                </ol>
              ),
              li: ({ children, ...props }) => (
                <li className="text-muted-foreground" {...props}>
                  {children}
                </li>
              ),
              a: ({ href, children, ...props }) => (
                <a
                  href={href}
                  className="text-primary hover:underline"
                  target={href?.startsWith('http') ? '_blank' : undefined}
                  rel={href?.startsWith('http') ? 'noopener noreferrer' : undefined}
                  {...props}
                >
                  {children}
                </a>
              ),
              code: ({ className, children, ...props }) => {
                const match = /language-(\w+)/.exec(className || '')
                const isInline = !match

                if (isInline) {
                  return (
                    <code
                      className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono text-foreground"
                      {...props}
                    >
                      {children}
                    </code>
                  )
                }

                const codeString = String(children).replace(/\n$/, '')

                return (
                  <div className="relative group mb-4">
                    <CopyButton text={codeString} />
                    <SyntaxHighlighter
                      style={oneDark as { [key: string]: React.CSSProperties }}
                      language={match[1]}
                      PreTag="div"
                      customStyle={{
                        margin: 0,
                        borderRadius: '0.5rem',
                        fontSize: '0.875rem',
                      }}
                    >
                      {codeString}
                    </SyntaxHighlighter>
                  </div>
                )
              },
              pre: ({ children }) => <>{children}</>,
              table: ({ children }) => (
                <div className="mb-4">
                  <Table>{children}</Table>
                </div>
              ),
              thead: ({ children }) => <TableHeader>{children}</TableHeader>,
              tbody: ({ children }) => <TableBody>{children}</TableBody>,
              tr: ({ children }) => <TableRow>{children}</TableRow>,
              th: ({ children, style }) => (
                <TableHead className="font-semibold text-foreground" style={style}>
                  {children}
                </TableHead>
              ),
              td: ({ children, style }) => (
                <TableCell style={style}>{children}</TableCell>
              ),
              blockquote: ({ children, ...props }) => (
                <blockquote
                  className="border-l-4 border-primary pl-4 italic text-muted-foreground mb-4"
                  {...props}
                >
                  {children}
                </blockquote>
              ),
              hr: () => <hr className="my-8 border-border" />,
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      </ScrollArea>
    </div>
  )
}
