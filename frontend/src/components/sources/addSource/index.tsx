import { useState, useCallback } from 'react'
import {
  FolderOpen,
  Link,
  Upload,
  Database,
  Play,
} from 'lucide-react'
import { cn } from '../../../lib/utils'
import { Source } from '../../../services/api'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useEmbeddingConfig } from './hooks/useEmbeddingConfig'
import DirectorySourceForm from './DirectorySourceForm'
import FileSourceForm from './FileSourceForm'
import UrlSourceForm from './UrlSourceForm'
import YoutubeSourceForm from './YoutubeSourceForm'
import CollectionAdoptionForm from './CollectionAdoptionForm'

export interface AddSourceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSourceAdded: (source: Source) => void
  onError: (error: string) => void
}

type SourceType = 'url' | 'directory' | 'file' | 'youtube' | 'collection'

export default function AddSourceDialog({
  open,
  onOpenChange,
  onSourceAdded,
  onError,
}: AddSourceDialogProps) {
  const [addType, setAddType] = useState<SourceType>('directory')

  // Shared embedding config
  const embedding = useEmbeddingConfig(open)

  const handleClose = useCallback(() => {
    embedding.reset()
    onOpenChange(false)
  }, [embedding, onOpenChange])

  const handleTypeChange = (value: string) => {
    setAddType(value as SourceType)
    embedding.reset()
  }

  // Determine dialog size
  const isUrlSelectStage = addType === 'url'
  const isDirectoryType = addType === 'directory'

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(o) : handleClose())}>
      <DialogContent
        className={cn(
          isUrlSelectStage
            ? 'max-w-2xl max-h-[90vh] flex flex-col'
            : isDirectoryType
              ? 'max-w-lg max-h-[90vh] overflow-y-auto'
              : 'max-w-md'
        )}
      >
        <DialogHeader>
          <DialogTitle>Add Source</DialogTitle>
        </DialogHeader>

        {/* Type Toggle */}
        <Tabs value={addType} onValueChange={handleTypeChange}>
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="directory" className="gap-2">
              <FolderOpen className="w-4 h-4" />
              Directory
            </TabsTrigger>
            <TabsTrigger value="url" className="gap-2">
              <Link className="w-4 h-4" />
              URL
            </TabsTrigger>
            <TabsTrigger value="file" className="gap-2">
              <Upload className="w-4 h-4" />
              PDF
            </TabsTrigger>
            <TabsTrigger value="youtube" className="gap-2">
              <Play className="w-4 h-4" />
              YouTube
            </TabsTrigger>
            <TabsTrigger value="collection" className="gap-2">
              <Database className="w-4 h-4" />
              Existing
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {/* Directory Form */}
        {addType === 'directory' && (
          <DirectorySourceForm
            embedding={embedding}
            onSourceAdded={onSourceAdded}
            onError={onError}
            onClose={handleClose}
          />
        )}

        {/* File Upload Form */}
        {addType === 'file' && (
          <FileSourceForm
            embedding={embedding}
            onSourceAdded={onSourceAdded}
            onError={onError}
            onClose={handleClose}
          />
        )}

        {/* URL Form */}
        {addType === 'url' && (
          <UrlSourceForm
            embedding={embedding}
            onSourceAdded={onSourceAdded}
            onError={onError}
            onClose={handleClose}
          />
        )}

        {/* YouTube Form */}
        {addType === 'youtube' && (
          <YoutubeSourceForm
            embedding={embedding}
            onSourceAdded={onSourceAdded}
            onError={onError}
            onClose={handleClose}
          />
        )}

        {/* Collection Adoption Form */}
        {addType === 'collection' && (
          <CollectionAdoptionForm
            onSourceAdded={onSourceAdded}
            onError={onError}
            onClose={handleClose}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

// Re-export subcomponents for direct use if needed
export { default as DirectorySourceForm } from './DirectorySourceForm'
export { default as FileSourceForm } from './FileSourceForm'
export { default as UrlSourceForm } from './UrlSourceForm'
export { default as YoutubeSourceForm } from './YoutubeSourceForm'
export { default as CollectionAdoptionForm } from './CollectionAdoptionForm'
export { default as EmbeddingModelSelector } from './EmbeddingModelSelector'
export { useEmbeddingConfig } from './hooks/useEmbeddingConfig'
