import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Loader2, RotateCw } from 'lucide-react'
import { taxonomyApi } from '../services/api/taxonomy'
import type { Taxonomy } from '../services/api/types/taxonomy'
import { TaxonomyDetail } from '../components/taxonomy'
import { Button } from '@/components/ui/button'

export default function TaxonomyDetailPage() {
  const { taxonomyId } = useParams<{ taxonomyId: string }>()
  const navigate = useNavigate()

  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Bumped by the Retry button to re-run the fetch effect
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!taxonomyId) {
      setTaxonomy(null)
      setLoading(false)
      return
    }
    // Guard against a slow response landing after unmount or after
    // taxonomyId changes (a stale fetch would clobber the newer state).
    let active = true
    setLoading(true)
    setError(null)
    taxonomyApi
      .get(taxonomyId)
      .then(data => {
        if (active) setTaxonomy(data)
      })
      .catch(err => {
        if (active) {
          setTaxonomy(null)
          setError(err instanceof Error ? err.message : 'Failed to load taxonomy')
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [taxonomyId, attempt])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-7 h-7 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // Error state persists until a retry succeeds — never falls through to
  // a misleading "not found" message.
  if (error) {
    return (
      <div className="p-6">
        <div className="max-w-4xl mx-auto">
          <Button
            variant="ghost"
            size="sm"
            className="mb-4 -ml-2 text-muted-foreground hover:text-foreground"
            onClick={() => navigate('/taxonomy')}
          >
            <ArrowLeft className="w-4 h-4 mr-1.5" />
            All Taxonomies
          </Button>
          <div className="p-4 bg-destructive/20 border border-destructive rounded-lg text-destructive-foreground">
            {error}
            <Button
              variant="link"
              className="ml-4 text-destructive hover:text-destructive-foreground"
              onClick={() => setAttempt(a => a + 1)}
            >
              <RotateCw className="w-3.5 h-3.5 mr-1.5" />
              Retry
            </Button>
          </div>
        </div>
      </div>
    )
  }

  // Fetch completed successfully but no taxonomy (or no id in the URL)
  if (!taxonomy) {
    return (
      <div className="p-6">
        <div className="max-w-4xl mx-auto">
          <Button
            variant="ghost"
            size="sm"
            className="mb-4 -ml-2 text-muted-foreground hover:text-foreground"
            onClick={() => navigate('/taxonomy')}
          >
            <ArrowLeft className="w-4 h-4 mr-1.5" />
            All Taxonomies
          </Button>
          <div className="mt-6 text-center text-muted-foreground">
            Taxonomy not found.
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        <TaxonomyDetail
          taxonomy={taxonomy}
          onBack={() => navigate('/taxonomy')}
        />
      </div>
    </div>
  )
}
