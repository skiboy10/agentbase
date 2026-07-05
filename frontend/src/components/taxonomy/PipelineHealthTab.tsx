import { CoverageCard, StaleDocsList, SuggestionsQueue } from '../sources/pipeline'

interface PipelineHealthTabProps {
  taxonomyId: string
}

export function PipelineHealthTab({ taxonomyId }: PipelineHealthTabProps) {
  return (
    <div className="mt-4 space-y-6">
      <CoverageCard taxonomyId={taxonomyId} />
      <StaleDocsList taxonomyId={taxonomyId} />
      <SuggestionsQueue taxonomyId={taxonomyId} />
    </div>
  )
}
