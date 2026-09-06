import { useState, useEffect, useCallback } from 'react'
import {
  Sparkles, Download, FileText, ChevronDown, ChevronRight,
  Copy, Check, Loader2, Puzzle, Terminal,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ErrorBanner } from '@/components/ErrorBanner'
import MarkdownRenderer from '@/components/MarkdownRenderer'
import { skillsApi, type SkillSummary, type SkillDetail } from '@/services/api/skills'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Small inline command block with a copy button. */
function CommandLine({ command }: { command: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(command)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div className="flex items-center gap-2 bg-muted rounded-md px-3 py-2 font-mono text-xs">
      <Terminal className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
      <code className="flex-1 overflow-x-auto whitespace-pre">{command}</code>
      <Button variant="ghost" size="icon" className="h-6 w-6 flex-shrink-0" onClick={copy} aria-label="Copy command">
        {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
      </Button>
    </div>
  )
}

function InstallInstructions({ slug }: { slug: string }) {
  return (
    <Tabs defaultValue="personal" className="w-full">
      <TabsList className="mb-2">
        <TabsTrigger value="personal">All projects</TabsTrigger>
        <TabsTrigger value="project">This project only</TabsTrigger>
      </TabsList>
      <TabsContent value="personal" className="space-y-2">
        <p className="text-sm text-muted-foreground">
          Install into your personal skills directory so it's available in every Claude Code session:
        </p>
        <CommandLine command={`unzip ~/Downloads/${slug}.zip -d ~/.claude/skills/`} />
      </TabsContent>
      <TabsContent value="project" className="space-y-2">
        <p className="text-sm text-muted-foreground">
          Install into a repository so it ships with the project (run from the repo root):
        </p>
        <CommandLine command={`unzip ~/Downloads/${slug}.zip -d .claude/skills/`} />
      </TabsContent>
    </Tabs>
  )
}

function SkillCard({ skill }: { skill: SkillSummary }) {
  const [filesOpen, setFilesOpen] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [detail, setDetail] = useState<SkillDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  const togglePreview = async () => {
    const next = !previewOpen
    setPreviewOpen(next)
    if (next && !detail && !loadingDetail) {
      setLoadingDetail(true)
      try {
        setDetail(await skillsApi.get(skill.slug))
      } catch {
        // Preview is best-effort; the download still works.
      } finally {
        setLoadingDetail(false)
      }
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <CardTitle className="flex items-center gap-2 text-base">
              <Puzzle className="w-5 h-5 text-primary flex-shrink-0" />
              {skill.name}
            </CardTitle>
            <div className="flex flex-wrap gap-2 mt-2">
              <Badge variant="secondary" className="text-xs">{skill.file_count} files</Badge>
              <Badge variant="secondary" className="text-xs">{formatBytes(skill.size_bytes)}</Badge>
            </div>
          </div>
          {/* Native download via anchor — proxied through nginx, no auth header needed. */}
          <Button asChild className="flex-shrink-0">
            <a href={skillsApi.archiveUrl(skill.slug)} download={`${skill.slug}.zip`}>
              <Download className="w-4 h-4 mr-2" />
              Download (.zip)
            </a>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-foreground/90">{skill.description}</p>

        <div>
          <h4 className="text-sm font-medium text-foreground mb-2">Install</h4>
          <InstallInstructions slug={skill.slug} />
          <p className="text-xs text-muted-foreground mt-2">
            The skill loads on the next Claude Code session. It drives Agentbase's MCP
            tools, so connect this instance as an MCP server (see the MCP Server section on
            the Quickstart page) to give the skill something to work with.
          </p>
        </div>

        {/* Files */}
        <Collapsible open={filesOpen} onOpenChange={setFilesOpen}>
          <CollapsibleTrigger className="flex items-center gap-1.5 text-sm font-medium text-foreground hover:text-primary transition-colors">
            {filesOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            Files ({skill.file_count})
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2">
            <ul className="space-y-1 pl-1">
              {skill.files.map((f) => (
                <li key={f} className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
                  <FileText className="w-3.5 h-3.5 flex-shrink-0" />
                  {f}
                </li>
              ))}
            </ul>
          </CollapsibleContent>
        </Collapsible>

        {/* SKILL.md preview */}
        <Collapsible open={previewOpen} onOpenChange={togglePreview}>
          <CollapsibleTrigger className="flex items-center gap-1.5 text-sm font-medium text-foreground hover:text-primary transition-colors">
            {previewOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            Preview SKILL.md
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2">
            {loadingDetail ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading…
              </div>
            ) : detail ? (
              <div className="rounded-lg border border-border p-4 max-h-96 overflow-y-auto">
                <MarkdownRenderer content={detail.readme} />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground py-2">Preview unavailable — download to view.</p>
            )}
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  )
}

export default function SkillsPage() {
  const [skills, setSkills] = useState<SkillSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { skills } = await skillsApi.list()
      setSkills(skills)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load skills')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-foreground mb-2 flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-primary" />
            Agent Skills
          </h1>
          <p className="text-muted-foreground">
            Installable Claude Code skills that teach an agent how to research, ingest, and
            curate knowledge in Agentbase through its MCP tools. Download a skill, drop it
            into your <code className="text-xs bg-muted px-1 rounded">.claude/skills/</code>{' '}
            directory, and Claude Code picks it up automatically.
          </p>
        </div>

        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        {loading ? (
          <div className="flex items-center gap-2 text-muted-foreground py-12 justify-center">
            <Loader2 className="w-5 h-5 animate-spin" /> Loading skills…
          </div>
        ) : skills.length === 0 && !error ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">No skills found</CardTitle>
              <CardDescription>
                This instance has no skills bundled under <code>.claude/skills/</code>.
              </CardDescription>
            </CardHeader>
          </Card>
        ) : (
          <div className="grid gap-4">
            {skills.map((skill) => (
              <SkillCard key={skill.slug} skill={skill} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
