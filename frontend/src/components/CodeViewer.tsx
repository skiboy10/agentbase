import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { Check, Copy, FileCode } from 'lucide-react'
import { cn } from '../lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

interface CodeViewerProps {
  code: string
  language?: string
  filePath?: string
  showLineNumbers?: boolean
  className?: string
}

// Simple custom theme - clean, no aggressive token backgrounds
const simpleTheme: { [key: string]: React.CSSProperties } = {
  'code[class*="language-"]': {
    color: 'hsl(var(--foreground))',
    background: 'none',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: '0.875rem',
    textAlign: 'left',
    whiteSpace: 'pre',
    wordSpacing: 'normal',
    wordBreak: 'normal',
    wordWrap: 'normal',
    lineHeight: '1.6',
  },
  'pre[class*="language-"]': {
    color: 'hsl(var(--foreground))',
    background: 'hsl(var(--muted))',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: '0.875rem',
    textAlign: 'left',
    whiteSpace: 'pre',
    wordSpacing: 'normal',
    wordBreak: 'normal',
    wordWrap: 'normal',
    lineHeight: '1.6',
    padding: '1rem',
    margin: '0',
    overflow: 'auto',
  },
  'comment': { color: 'hsl(var(--muted-foreground))' },
  'prolog': { color: 'hsl(var(--muted-foreground))' },
  'doctype': { color: 'hsl(var(--muted-foreground))' },
  'cdata': { color: 'hsl(var(--muted-foreground))' },
  'punctuation': { color: 'hsl(var(--muted-foreground))' },
  'property': { color: '#e06c75' },
  'tag': { color: '#e06c75' },
  'boolean': { color: '#d19a66' },
  'number': { color: '#d19a66' },
  'constant': { color: '#d19a66' },
  'symbol': { color: '#d19a66' },
  'deleted': { color: '#e06c75' },
  'selector': { color: '#98c379' },
  'attr-name': { color: '#d19a66' },
  'string': { color: '#98c379' },
  'char': { color: '#98c379' },
  'builtin': { color: '#98c379' },
  'inserted': { color: '#98c379' },
  'operator': { color: 'hsl(var(--foreground))' },
  'entity': { color: '#61afef', cursor: 'help' },
  'url': { color: '#61afef' },
  'variable': { color: '#e06c75' },
  'atrule': { color: '#c678dd' },
  'attr-value': { color: '#98c379' },
  'function': { color: '#61afef' },
  'class-name': { color: '#e5c07b' },
  'keyword': { color: '#c678dd' },
  'regex': { color: '#56b6c2' },
  'important': { color: '#c678dd', fontWeight: 'bold' },
  'bold': { fontWeight: 'bold' },
  'italic': { fontStyle: 'italic' },
}

// Language alias mapping
const languageMap: Record<string, string> = {
  'ampscript': 'markup',
  'amp': 'markup',
  'ssjs': 'javascript',
  'js': 'javascript',
  'ts': 'typescript',
  'py': 'python',
  'sh': 'bash',
  'shell': 'bash',
  'yml': 'yaml',
}

export default function CodeViewer({
  code,
  language = 'python',
  filePath,
  showLineNumbers = true,
  className,
}: CodeViewerProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const normalizedLanguage = language
    ? (languageMap[language.toLowerCase()] || language.toLowerCase())
    : 'python'

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-muted/50">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <FileCode className="w-4 h-4" />
          {filePath && (
            <span className="font-mono text-xs truncate max-w-[300px]" title={filePath}>
              {filePath}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {language && (
            <Badge variant="secondary" className="text-xs">
              {language}
            </Badge>
          )}
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            onClick={handleCopy}
            title="Copy code"
            aria-label="Copy code"
          >
            {copied ? (
              <Check className="w-4 h-4 text-status-success" />
            ) : (
              <Copy className="w-4 h-4" />
            )}
          </Button>
        </div>
      </div>

      {/* Code */}
      <div className="flex-1 overflow-auto">
        <SyntaxHighlighter
          language={normalizedLanguage}
          style={simpleTheme}
          customStyle={{
            margin: 0,
            borderRadius: 0,
            padding: '1rem',
            background: 'hsl(var(--muted))',
            height: '100%',
            minHeight: '100%',
          }}
          showLineNumbers={showLineNumbers && code.split('\n').length > 1}
          lineNumberStyle={{
            minWidth: '3em',
            paddingRight: '1em',
            color: 'hsl(var(--muted-foreground))',
            userSelect: 'none',
          }}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    </div>
  )
}
