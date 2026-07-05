import { useState } from 'react'
import { Loader2, Upload, FileText, X } from 'lucide-react'
import { cn } from '../../../lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { DialogFooter } from '@/components/ui/dialog'
import { sourcesApi, Source } from '../../../services/api'
import EmbeddingModelSelector from './EmbeddingModelSelector'
import EnrichmentSection from './EnrichmentSection'
import { UseEmbeddingConfigResult } from './hooks/useEmbeddingConfig'

interface FileSourceFormProps {
  embedding: UseEmbeddingConfigResult
  onSourceAdded: (source: Source) => void
  onError: (error: string) => void
  onClose: () => void
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

const MAX_FILE_SIZE_MB = 200
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

export default function FileSourceForm({
  embedding,
  onSourceAdded,
  onError,
  onClose,
}: FileSourceFormProps) {
  const [name, setName] = useState('')
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [enrichmentEnabled, setEnrichmentEnabled] = useState(false)
  const [enrichmentTaxonomyId, setEnrichmentTaxonomyId] = useState('')
  const [enrichmentModel, setEnrichmentModel] = useState('')

  const totalSize = uploadFiles.reduce((sum, f) => sum + f.size, 0)

  const handleFilesSelect = (newFiles: File[]) => {
    // Filter to only PDF files
    const pdfFiles = newFiles.filter(f => f.name.toLowerCase().endsWith('.pdf'))
    if (pdfFiles.length === 0) return

    // Validate file sizes client-side
    const oversized = pdfFiles.filter(f => f.size > MAX_FILE_SIZE_BYTES)
    if (oversized.length > 0) {
      const names = oversized.map(f => `${f.name} (${formatFileSize(f.size)})`).join(', ')
      onError(`File(s) exceed ${MAX_FILE_SIZE_MB}MB limit: ${names}`)
      // Still add the files that are within the limit
      const validFiles = pdfFiles.filter(f => f.size <= MAX_FILE_SIZE_BYTES)
      if (validFiles.length === 0) return
    }

    const validPdfFiles = pdfFiles.filter(f => f.size <= MAX_FILE_SIZE_BYTES)

    // Merge with existing, avoiding duplicates by name
    const existingNames = new Set(uploadFiles.map(f => f.name))
    const uniqueNewFiles = validPdfFiles.filter(f => !existingNames.has(f.name))

    const merged = [...uploadFiles, ...uniqueNewFiles]
    setUploadFiles(merged)

    // Auto-set name from first file if not already set
    if (!name && merged.length > 0) {
      if (merged.length === 1) {
        setName(merged[0].name.replace('.pdf', ''))
      } else {
        setName(`${merged.length} PDF Files`)
      }
    }
  }

  const handleRemoveFile = (index: number) => {
    setUploadFiles(prev => prev.filter((_, i) => i !== index))
  }

  const handleUploadFiles = async () => {
    if (uploadFiles.length === 0 || !name.trim()) return

    try {
      setUploading(true)
      const embeddingParams = embedding.getEmbeddingParams()
      const created = await sourcesApi.uploadFiles(uploadFiles, name.trim(), {
        embeddingProvider: embeddingParams.provider,
        embeddingModel: embeddingParams.model,
        enrichmentEnabled,
        enrichmentTaxonomyId: enrichmentEnabled ? enrichmentTaxonomyId : undefined,
        enrichmentModel: enrichmentEnabled ? enrichmentModel : undefined,
      })
      onSourceAdded(created)
      onClose()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to upload files')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-4 py-4">
      <div className="space-y-2">
        <Label htmlFor="file-source-name">Source Name</Label>
        <Input
          id="file-source-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g., Product Documentation"
        />
      </div>
      <div className="space-y-2">
        <Label>PDF Files</Label>
        <div
          className={cn(
            'relative border-2 border-dashed rounded-lg p-6 transition-colors cursor-pointer',
            uploadFiles.length > 0
              ? 'border-primary bg-primary/10'
              : 'border-muted-foreground/25 hover:border-muted-foreground/50 bg-muted/50'
          )}
          onClick={() => document.getElementById('file-upload')?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            e.stopPropagation()
          }}
          onDrop={(e) => {
            e.preventDefault()
            e.stopPropagation()
            const droppedFiles = Array.from(e.dataTransfer.files)
            handleFilesSelect(droppedFiles)
          }}
        >
          <input
            id="file-upload"
            type="file"
            accept=".pdf"
            multiple
            className="hidden"
            onChange={(e) => handleFilesSelect(Array.from(e.target.files || []))}
          />
          {uploadFiles.length > 0 ? (
            <div className="space-y-3" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <span>{uploadFiles.length} file(s) selected</span>
                <span>{formatFileSize(totalSize)} total</span>
              </div>
              <div className="max-h-40 overflow-y-auto space-y-2">
                {uploadFiles.map((file, index) => (
                  <div
                    key={`${file.name}-${index}`}
                    className="flex items-center justify-between bg-background rounded-md px-3 py-2"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="w-4 h-4 flex-shrink-0 text-primary" />
                      <span className="truncate text-sm">{file.name}</span>
                      <span className="text-xs text-muted-foreground flex-shrink-0">
                        ({formatFileSize(file.size)})
                      </span>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                      onClick={() => handleRemoveFile(index)}
                    >
                      <X className="w-4 h-4" />
                    </Button>
                  </div>
                ))}
              </div>
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={() => document.getElementById('file-upload')?.click()}
              >
                Add More Files
              </Button>
            </div>
          ) : (
            <div className="text-center">
              <Upload className="w-10 h-10 text-muted-foreground mx-auto mb-2" />
              <p className="text-foreground">Click to select or drag and drop</p>
              <p className="text-muted-foreground text-sm mt-1">
                PDF files only, max {MAX_FILE_SIZE_MB}MB each
              </p>
            </div>
          )}
        </div>
      </div>

      <EmbeddingModelSelector
        embeddingConfig={embedding.embeddingConfig}
        useCustomEmbedding={embedding.useCustomEmbedding}
        onUseCustomChange={embedding.setUseCustomEmbedding}
        selectedProvider={embedding.selectedProvider}
        onProviderChange={embedding.setSelectedProvider}
        selectedModel={embedding.selectedModel}
        onModelChange={embedding.setSelectedModel}
        idPrefix="file-embed"
      />

      <EnrichmentSection
        enrichmentEnabled={enrichmentEnabled}
        setEnrichmentEnabled={setEnrichmentEnabled}
        taxonomyId={enrichmentTaxonomyId}
        setTaxonomyId={setEnrichmentTaxonomyId}
        model={enrichmentModel}
        setModel={setEnrichmentModel}
      />

      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button
          onClick={handleUploadFiles}
          disabled={
            !name.trim() ||
            uploadFiles.length === 0 ||
            uploading ||
            (enrichmentEnabled && !enrichmentTaxonomyId)
          }
        >
          {uploading && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
          Upload & Index {uploadFiles.length > 1 ? `(${uploadFiles.length} files)` : ''}
        </Button>
      </DialogFooter>
    </div>
  )
}
