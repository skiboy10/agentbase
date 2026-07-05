import { Link } from 'react-router-dom'
import {
  Database, Bot, Cloud, Tags, Library, Search,
  ArrowRight, Layers, FileText, BookOpen, Zap
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { help } from '@/content/help'
import type { LucideIcon } from 'lucide-react'

// Presentation mappings — colors and icons live here, content comes from help.ts
type HelpDomain = 'sources' | 'libraries' | 'agents' | 'providers' | 'taxonomy'

const objectMeta: { key: HelpDomain; icon: LucideIcon; color: string }[] = [
  { key: 'sources', icon: Database, color: 'text-blue-500' },
  { key: 'libraries', icon: Library, color: 'text-violet-500' },
  { key: 'agents', icon: Bot, color: 'text-emerald-500' },
  { key: 'providers', icon: Cloud, color: 'text-sky-500' },
  { key: 'taxonomy', icon: Tags, color: 'text-rose-500' },
]

const objects = objectMeta.map((meta) => {
  const entry = (help[meta.key] as { page: { label: string; detail: string; example?: string; keyConcept?: string } }).page
  return {
    icon: meta.icon,
    name: entry.label,
    color: meta.color,
    description: entry.detail,
    examples: entry.example ?? '',
    key: entry.keyConcept ?? '',
  }
})

const flow = [
  { step: '1', label: 'Add a Provider', desc: help.workflow.steps[0].description, icon: Cloud, to: '/providers' },
  { step: '2', label: 'Create a Source', desc: 'Point to URLs, files, or a local directory', icon: Database, to: '/sources' },
  { step: '3', label: 'Index the Source', desc: 'Extract text, chunk, and embed into vectors', icon: Zap, to: '/sources' },
  { step: '4', label: 'Create a Library', desc: help.workflow.steps[3].description, icon: Library, to: '/libraries' },
  { step: '5', label: 'Create an Agent', desc: 'Pick a model, write a prompt, bind libraries', icon: Bot, to: '/agents' },
  { step: '6', label: 'Query the Agent', desc: help.workflow.steps[4].description, icon: Search, to: '/agents' },
]

export default function QuickstartPage() {
  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-foreground mb-2">Quickstart Guide</h1>
          <p className="text-muted-foreground">
            {help.quickstart.page.detail}
          </p>
        </div>

        {/* How it works flow */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Layers className="w-5 h-5 text-primary" />
              Getting Started
            </CardTitle>
            <CardDescription>The typical workflow from zero to a working agent</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3">
              {flow.map((item) => (
                <Link
                  key={item.step}
                  to={item.to}
                  aria-label={`${item.label} — open ${item.to.slice(1)}`}
                  className="group flex items-start gap-4 rounded-lg -mx-2 px-2 py-1.5 transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-none"
                >
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center text-sm font-semibold">
                    {item.step}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <item.icon className="w-4 h-4 text-muted-foreground" />
                      <span className="font-medium text-foreground">{item.label}</span>
                    </div>
                    <p className="text-sm text-muted-foreground mt-0.5">{item.desc}</p>
                  </div>
                  <ArrowRight className="w-4 h-4 text-muted-foreground/40 flex-shrink-0 mt-2 transition-all group-hover:text-primary group-hover:translate-x-0.5" />
                </Link>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Object reference */}
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-foreground mb-1">Object Reference</h2>
          <p className="text-sm text-muted-foreground">What each object does and how they connect</p>
        </div>

        <div className="grid gap-4 mb-8">
          {objects.map((obj) => (
            <Card key={obj.name}>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <obj.icon className={`w-5 h-5 ${obj.color}`} />
                  {obj.name}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-foreground/90">{obj.description}</p>
                <div className="flex flex-col gap-2">
                  <div className="bg-muted rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="secondary" className="text-xs">Example</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{obj.examples}</p>
                  </div>
                  <div className="bg-primary/5 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge className="text-xs">Key concept</Badge>
                    </div>
                    <p className="text-sm text-foreground/80">{obj.key}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Relationships */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-primary" />
              How Objects Relate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4 text-sm">
              <div className="bg-muted rounded-lg p-4 font-mono text-xs leading-relaxed">
                <pre className="whitespace-pre-wrap">
{`Provider          (supplies models to)
  └─► Agent        (bound to)
        └─► Library   (groups)
              └─► Sources   (indexed into)
                    └─► Qdrant Collections   (contain)
                          └─► Chunks (with vector embeddings)

Taxonomy
  └─► Terms (organized by facet)
        └─► Applied to chunks via enrichment`}
                </pre>
              </div>

              <div className="grid gap-3 mt-4">
                <div className="flex items-start gap-3">
                  <ArrowRight className="w-4 h-4 text-primary mt-0.5 flex-shrink-0" />
                  <p className="text-foreground/90">
                    <strong>Sources → Libraries:</strong> A library groups many sources, and a source
                    can be bound to multiple libraries (embedding settings must match). When you search
                    a library, all its sources are queried together.
                  </p>
                </div>
                <div className="flex items-start gap-3">
                  <ArrowRight className="w-4 h-4 text-primary mt-0.5 flex-shrink-0" />
                  <p className="text-foreground/90">
                    <strong>Libraries → Agents:</strong> Bind one or more libraries to an agent.
                    When the agent receives a query, it automatically searches bound libraries for
                    relevant context and includes it in the LLM prompt.
                  </p>
                </div>
                <div className="flex items-start gap-3">
                  <ArrowRight className="w-4 h-4 text-primary mt-0.5 flex-shrink-0" />
                  <p className="text-foreground/90">
                    <strong>Providers → Agents:</strong> Each agent uses a model from a configured provider.
                    The same provider can also supply embedding models used during source indexing.
                  </p>
                </div>
                <div className="flex items-start gap-3">
                  <ArrowRight className="w-4 h-4 text-primary mt-0.5 flex-shrink-0" />
                  <p className="text-foreground/90">
                    <strong>Taxonomies → Sources:</strong> Enrichment classifies each chunk in a source
                    against taxonomy terms, adding structured metadata that improves search relevance.
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Access methods */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-primary" />
              Ways to Interact
            </CardTitle>
            <CardDescription>Agentbase exposes three interfaces</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="bg-muted rounded-lg p-4">
                <h4 className="font-medium text-foreground mb-1">Web UI</h4>
                <p className="text-sm text-muted-foreground">
                  This interface. Manage sources, libraries, agents, and test queries visually.
                </p>
              </div>
              <div className="bg-muted rounded-lg p-4">
                <h4 className="font-medium text-foreground mb-1">REST API</h4>
                <p className="text-sm text-muted-foreground">
                  Full API at <code className="text-xs bg-background px-1 rounded">/api/*</code>. See the API Reference page for endpoints.
                </p>
              </div>
              <div className="bg-muted rounded-lg p-4">
                <h4 className="font-medium text-foreground mb-1">MCP Server</h4>
                <p className="text-sm text-muted-foreground">
                  84 tools covering everything in this UI. Connect from Claude, Cursor, or any MCP client.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
