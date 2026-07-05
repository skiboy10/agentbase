import { useState } from 'react'
import { ArrowLeft, Hash, Activity } from 'lucide-react'
import type { Taxonomy } from '../../services/api/types/taxonomy'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { TermsTab } from './TermsTab'
import { SuggestionsTab } from './SuggestionsTab'
import { CoverageTab } from './CoverageTab'
import { PipelineHealthTab } from './PipelineHealthTab'

interface TaxonomyDetailProps {
  taxonomy: Taxonomy
  onBack: () => void
}

export function TaxonomyDetail({ taxonomy, onBack }: TaxonomyDetailProps) {
  const [activeTab, setActiveTab] = useState('terms')

  return (
    <div>
      {/* Back + header */}
      <div className="mb-6">
        <Button
          variant="ghost"
          size="sm"
          className="mb-4 -ml-2 text-muted-foreground hover:text-foreground"
          onClick={onBack}
        >
          <ArrowLeft className="w-4 h-4 mr-1.5" />
          All Taxonomies
        </Button>

        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-bold text-foreground">{taxonomy.name}</h1>
              <Badge
                variant="outline"
                className="text-sm font-mono text-violet-400 border-violet-400/40"
              >
                v{taxonomy.version}
              </Badge>
              <Badge variant="secondary" className="gap-1">
                <Hash className="w-3 h-3" />
                {taxonomy.term_count} terms
              </Badge>
            </div>
            {taxonomy.description && (
              <p className="text-muted-foreground mt-1.5">{taxonomy.description}</p>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="terms">Terms</TabsTrigger>
          <TabsTrigger value="suggestions">Suggestions</TabsTrigger>
          <TabsTrigger value="coverage">Coverage</TabsTrigger>
          <TabsTrigger value="pipeline-health">
            <Activity className="w-3.5 h-3.5 mr-1.5" />
            Pipeline Health
          </TabsTrigger>
        </TabsList>

        <TabsContent value="terms">
          <TermsTab taxonomyId={taxonomy.id} />
        </TabsContent>

        <TabsContent value="suggestions">
          <SuggestionsTab taxonomyId={taxonomy.id} />
        </TabsContent>

        <TabsContent value="coverage">
          <CoverageTab taxonomyId={taxonomy.id} />
        </TabsContent>

        <TabsContent value="pipeline-health">
          <PipelineHealthTab taxonomyId={taxonomy.id} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
