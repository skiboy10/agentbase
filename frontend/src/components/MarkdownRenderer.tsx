import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { Check, Copy } from 'lucide-react'
import { cn } from '../lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

interface MarkdownRendererProps {
  content: string
  className?: string
}

interface CodeBlockProps {
  language: string
  code: string
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

function CodeBlock({ language, code }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Map common language aliases
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

  const normalizedLanguage = language ? (languageMap[language.toLowerCase()] || language.toLowerCase()) : ''
  const hasLanguage = normalizedLanguage && normalizedLanguage !== 'text'

  return (
    <div className="relative group my-3 rounded-lg border border-border overflow-hidden">
      {/* Copy button (and language badge if specified) */}
      <div className="absolute right-2 top-2 flex items-center gap-2 z-10">
        {language && (
          <Badge variant="secondary" className="text-xs">
            {language}
          </Badge>
        )}
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={handleCopy}
          title="Copy code"
        >
          {copied ? (
            <Check className="w-4 h-4 text-green-500" />
          ) : (
            <Copy className="w-4 h-4" />
          )}
        </Button>
      </div>

      {hasLanguage ? (
        <SyntaxHighlighter
          language={normalizedLanguage}
          style={simpleTheme}
          customStyle={{
            margin: 0,
            borderRadius: 0,
            padding: '1rem',
            paddingTop: '2.5rem',
            background: 'hsl(var(--muted))',
          }}
          showLineNumbers={code.split('\n').length > 5}
          lineNumberStyle={{
            minWidth: '2.5em',
            paddingRight: '1em',
            color: 'hsl(var(--muted-foreground))',
            userSelect: 'none',
          }}
        >
          {code}
        </SyntaxHighlighter>
      ) : (
        // Plain code block - no syntax highlighting
        <pre className="m-0 p-4 pt-10 bg-muted text-foreground text-sm font-mono leading-relaxed whitespace-pre-wrap overflow-auto">
          {code}
        </pre>
      )}
    </div>
  )
}

export default function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div className={cn('markdown-content', className)}>
    <ReactMarkdown
      components={{
        // Code blocks
        code({ node: _node, className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || '')
          const isInline = !match && !String(children).includes('\n')

          if (isInline) {
            return (
              <code
                className="bg-muted text-primary px-1.5 py-0.5 rounded text-sm font-mono"
                {...props}
              >
                {children}
              </code>
            )
          }

          const language = match ? match[1] : ''
          const code = String(children).replace(/\n$/, '')

          return <CodeBlock language={language} code={code} />
        },

        // Paragraphs
        p({ children }) {
          return <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>
        },

        // Headers
        h1({ children }) {
          return <h1 className="text-2xl font-bold mb-4 mt-6 first:mt-0 text-foreground">{children}</h1>
        },
        h2({ children }) {
          return <h2 className="text-xl font-bold mb-3 mt-5 first:mt-0 text-foreground">{children}</h2>
        },
        h3({ children }) {
          return <h3 className="text-lg font-semibold mb-2 mt-4 first:mt-0 text-foreground">{children}</h3>
        },
        h4({ children }) {
          return <h4 className="text-base font-semibold mb-2 mt-3 first:mt-0 text-foreground">{children}</h4>
        },

        // Lists
        ul({ children }) {
          return <ul className="list-disc list-inside mb-3 space-y-1 ml-2">{children}</ul>
        },
        ol({ children }) {
          return <ol className="list-decimal list-inside mb-3 space-y-1 ml-2">{children}</ol>
        },
        li({ children }) {
          return <li className="leading-relaxed">{children}</li>
        },

        // Blockquotes
        blockquote({ children }) {
          return (
            <blockquote className="border-l-4 border-primary pl-4 py-1 my-3 bg-muted/50 rounded-r italic text-muted-foreground">
              {children}
            </blockquote>
          )
        },

        // Links
        a({ href, children }) {
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:text-primary/80 underline underline-offset-2"
            >
              {children}
            </a>
          )
        },

        // Strong/Bold
        strong({ children }) {
          return <strong className="font-semibold text-foreground">{children}</strong>
        },

        // Emphasis/Italic
        em({ children }) {
          return <em className="italic">{children}</em>
        },

        // Horizontal rule
        hr() {
          return <hr className="my-6 border-border" />
        },

        // Tables
        table({ children }) {
          return (
            <div className="overflow-x-auto my-4">
              <table className="min-w-full divide-y divide-border border border-border rounded-lg">
                {children}
              </table>
            </div>
          )
        },
        thead({ children }) {
          return <thead className="bg-muted">{children}</thead>
        },
        tbody({ children }) {
          return <tbody className="divide-y divide-border">{children}</tbody>
        },
        tr({ children }) {
          return <tr>{children}</tr>
        },
        th({ children }) {
          return (
            <th className="px-4 py-2 text-left text-sm font-semibold text-foreground">
              {children}
            </th>
          )
        },
        td({ children }) {
          return <td className="px-4 py-2 text-sm text-muted-foreground">{children}</td>
        },

        // Pre (wrapper for code blocks - handled by code component)
        pre({ children }) {
          return <>{children}</>
        },
      }}
    >
      {content}
    </ReactMarkdown>
    </div>
  )
}
