import { useState, useEffect, useCallback } from 'react'
import {
  Search,
  FileText,
  Trash2,
  Eye,
  Loader2,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
} from 'lucide-react'
import { libraryApi } from '../../services/api/library'
import { getFileTypeBadgeClass } from '@/lib/fileType'
import type { LibraryDocument, LibrarySource } from '../../services/api/types/library'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'

const PAGE_SIZE = 25

interface DocumentsTabProps {
  kbId: string
  sources: LibrarySource[]
  onError: (msg: string) => void
}

function formatDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function FileTypeBadge({ type }: { type: string | null }) {
  if (!type) return null
  const classes = getFileTypeBadgeClass(type)
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono border ${classes}`}>
      {type.toLowerCase()}
    </span>
  )
}

export default function DocumentsTab({ kbId, sources, onError }: DocumentsTabProps) {
  const [documents, setDocuments] = useState<LibraryDocument[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)

  // Filters
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [fileTypeFilter, setFileTypeFilter] = useState('all')
  const [docTypeFilter, setDocTypeFilter] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('all')

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350)
    return () => clearTimeout(t)
  }, [search])

  // Reset offset when filters change
  useEffect(() => {
    setOffset(0)
  }, [debouncedSearch, fileTypeFilter, docTypeFilter, sourceFilter])

  const fetchDocuments = useCallback(async () => {
    try {
      setLoading(true)
      const params = {
        offset,
        limit: PAGE_SIZE,
        search: debouncedSearch || undefined,
        file_type: fileTypeFilter !== 'all' ? fileTypeFilter : undefined,
        document_type: docTypeFilter !== 'all' ? docTypeFilter : undefined,
        source_id: sourceFilter !== 'all' ? sourceFilter : undefined,
      }
      const result = await libraryApi.listDocuments(kbId, params)
      setDocuments(result.documents)
      setTotal(result.total)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load documents')
    } finally {
      setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- onError is a stable prop callback; caller should memoize if needed
  }, [kbId, offset, debouncedSearch, fileTypeFilter, docTypeFilter, sourceFilter])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  // Full-text viewer
  const [viewDoc, setViewDoc] = useState<LibraryDocument | null>(null)
  const [viewText, setViewText] = useState<string | null>(null)
  const [viewLoading, setViewLoading] = useState(false)

  const openFullText = async (doc: LibraryDocument) => {
    setViewDoc(doc)
    setViewText(null)
    setViewLoading(true)
    try {
      const result = await libraryApi.getDocumentText(kbId, doc.id)
      setViewText(result.full_text)
    } catch (_err) {
      setViewText('Failed to load document text.')
    } finally {
      setViewLoading(false)
    }
  }

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState<LibraryDocument | null>(null)
  const [deleting, setDeleting] = useState(false)

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      setDeleting(true)
      await libraryApi.deleteDocument(kbId, deleteTarget.id)
      setDocuments(prev => prev.filter(d => d.id !== deleteTarget.id))
      setTotal(prev => prev - 1)
      setDeleteTarget(null)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to delete document')
    } finally {
      setDeleting(false)
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            placeholder="Search titles..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-8 h-8 text-sm"
          />
        </div>

        <Select value={fileTypeFilter} onValueChange={setFileTypeFilter}>
          <SelectTrigger className="h-8 w-[130px] text-sm">
            <SelectValue placeholder="File type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All file types</SelectItem>
            <SelectItem value="pdf">PDF</SelectItem>
            <SelectItem value="docx">DOCX</SelectItem>
            <SelectItem value="txt">TXT</SelectItem>
            <SelectItem value="md">Markdown</SelectItem>
            <SelectItem value="html">HTML</SelectItem>
            <SelectItem value="url">URL</SelectItem>
          </SelectContent>
        </Select>

        <Select value={docTypeFilter} onValueChange={setDocTypeFilter}>
          <SelectTrigger className="h-8 w-[140px] text-sm">
            <SelectValue placeholder="Doc type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All doc types</SelectItem>
            <SelectItem value="article">Article</SelectItem>
            <SelectItem value="reference">Reference</SelectItem>
            <SelectItem value="guide">Guide</SelectItem>
            <SelectItem value="note">Note</SelectItem>
          </SelectContent>
        </Select>

        {sources.length > 0 && (
          <Select value={sourceFilter} onValueChange={setSourceFilter}>
            <SelectTrigger className="h-8 w-[160px] text-sm">
              <SelectValue placeholder="Source" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sources</SelectItem>
              {sources.map(s => (
                <SelectItem key={s.id} value={s.id}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <span className="ml-auto text-xs text-muted-foreground shrink-0">
          {loading ? '...' : `${total} document${total !== 1 ? 's' : ''}`}
        </span>
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-[1fr_120px_100px_90px_80px_90px] gap-2 px-3 text-xs font-medium text-muted-foreground/60 uppercase tracking-wide border-b border-border/50 pb-1.5">
        <span>Title</span>
        <span>Source</span>
        <span>File Type</span>
        <span>Doc Type</span>
        <span className="text-right">Chunks</span>
        <span>Actions</span>
      </div>

      {/* Document rows */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : documents.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground/60">
          <FileText className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">No documents found.</p>
          {(debouncedSearch || fileTypeFilter !== 'all' || docTypeFilter !== 'all' || sourceFilter !== 'all') && (
            <p className="text-xs mt-1">Try adjusting your filters.</p>
          )}
        </div>
      ) : (
        <div className="space-y-0.5">
          {documents.map(doc => (
            <div
              key={doc.id}
              className="grid grid-cols-[1fr_120px_100px_90px_80px_90px] gap-2 items-center px-3 py-2 rounded hover:bg-muted/30 transition-colors group"
            >
              {/* Title + tags */}
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{doc.title}</p>
                {(doc.tags?.length ?? 0) > 0 && (
                  <div className="flex items-center gap-1 mt-0.5 flex-wrap">
                    {doc.tags!.map((tag, i) => (
                      <Badge
                        key={i}
                        variant="outline"
                        className="text-[10px] py-0 px-1 h-4 text-muted-foreground border-border/50"
                      >
                        {tag.value}
                      </Badge>
                    ))}
                  </div>
                )}
                <p className="text-[11px] text-muted-foreground/50 mt-0.5">
                  {formatDate(doc.indexed_at)}
                </p>
              </div>

              {/* Source */}
              <p className="text-xs text-muted-foreground truncate" title={doc.source_name ?? undefined}>
                {doc.source_name}
              </p>

              {/* File type */}
              <div>
                <FileTypeBadge type={doc.file_type} />
              </div>

              {/* Doc type */}
              <div>
                {doc.document_type ? (
                  <Badge variant="secondary" className="text-xs">
                    {doc.document_type}
                  </Badge>
                ) : (
                  <span className="text-xs text-muted-foreground/40">—</span>
                )}
              </div>

              {/* Chunks */}
              <p className="text-sm text-right text-muted-foreground">{doc.chunk_count}</p>

              {/* Actions */}
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => openFullText(doc)}
                  title="View full text"
                >
                  <Eye className="w-3.5 h-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                  onClick={() => setDeleteTarget(doc)}
                  title="Delete document"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2 border-t border-border/50">
          <span className="text-xs text-muted-foreground">
            Page {currentPage} of {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              disabled={offset === 0}
              onClick={() => setOffset(prev => Math.max(0, prev - PAGE_SIZE))}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(prev => prev + PAGE_SIZE)}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Full-text viewer */}
      <Dialog
        open={!!viewDoc}
        onOpenChange={open => { if (!open) { setViewDoc(null); setViewText(null) } }}
      >
        <DialogContent className="max-w-3xl max-h-[80vh] flex flex-col">
          <DialogHeader className="shrink-0">
            <DialogTitle className="flex items-center gap-2 text-base">
              <FileText className="w-4 h-4 text-muted-foreground" />
              {viewDoc?.title}
            </DialogTitle>
            <DialogDescription className="flex items-center gap-2 text-xs">
              <span>{viewDoc?.source_name}</span>
              {viewDoc?.file_type && (
                <>
                  <Separator orientation="vertical" className="h-3" />
                  <FileTypeBadge type={viewDoc.file_type} />
                </>
              )}
              {viewDoc?.chunk_count !== undefined && (
                <>
                  <Separator orientation="vertical" className="h-3" />
                  <span>{viewDoc.chunk_count} chunks</span>
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="flex-1 mt-2 border border-border/50 rounded">
            {viewLoading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : viewText ? (
              <pre className="p-4 text-xs text-foreground/90 font-mono whitespace-pre-wrap break-words leading-relaxed">
                {viewText}
              </pre>
            ) : (
              <div className="flex flex-col items-center gap-2 py-16 text-center">
                <AlertTriangle className="w-5 h-5 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  No stored text for this document.
                </p>
                <p className="text-xs text-muted-foreground/80 max-w-sm">
                  Its chunks are still searchable, but the full text was never
                  captured. Re-index the source to populate it.
                </p>
              </div>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={!!deleteTarget} onOpenChange={open => !open && setDeleteTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-400" />
              Delete Document
            </DialogTitle>
            <DialogDescription>
              Permanently delete <strong>{deleteTarget?.title}</strong>?
              This removes the document and all its chunks from the library. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
