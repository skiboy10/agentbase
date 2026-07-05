import { useState, useEffect } from 'react'
import { Moon, Sun, Monitor, Sidebar, Database, Loader2, Check, RotateCcw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components'
import { Switch } from '@/components/ui/switch'

type Theme = 'dark' | 'light' | 'system'

interface AppSettings {
  theme: Theme
  sidebarCollapsed: boolean
}

const defaultSettings: AppSettings = {
  theme: 'dark',
  sidebarCollapsed: false,
}

function loadSettings(): AppSettings {
  try {
    const stored = localStorage.getItem('appSettings')
    if (stored) {
      return { ...defaultSettings, ...JSON.parse(stored) }
    }
    // Migrate legacy sidebar setting
    const sidebarCollapsed = localStorage.getItem('sidebarCollapsed') === 'true'
    return { ...defaultSettings, sidebarCollapsed }
  } catch {
    return defaultSettings
  }
}

function saveSettings(settings: AppSettings) {
  localStorage.setItem('appSettings', JSON.stringify(settings))
  // Keep legacy key in sync for Layout.tsx
  localStorage.setItem('sidebarCollapsed', String(settings.sidebarCollapsed))
}

function applyTheme(theme: Theme) {
  const root = document.documentElement
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches

  if (theme === 'light' || (theme === 'system' && !systemDark)) {
    root.classList.remove('dark')
  } else {
    root.classList.add('dark')
  }
}

interface BackendConfig {
  chunk_size: number
  chunk_overlap: number
  retrieval_top_k: number
  max_upload_size_mb: number
  allowed_file_extensions: string
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings>(loadSettings)
  const [backendConfig, setBackendConfig] = useState<BackendConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    applyTheme(settings.theme)
  }, [settings.theme])

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        // Display-only defaults — these values are set via backend environment variables
        setBackendConfig({
          chunk_size: 1000,
          chunk_overlap: 200,
          retrieval_top_k: 5,
          max_upload_size_mb: 50,
          allowed_file_extensions: '.pdf',
        })
      } catch (err) {
        console.error('Failed to load config:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchConfig()
  }, [])

  const updateSetting = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
    const newSettings = { ...settings, [key]: value }
    setSettings(newSettings)
    saveSettings(newSettings)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const resetToDefaults = () => {
    setSettings(defaultSettings)
    saveSettings(defaultSettings)
    applyTheme(defaultSettings.theme)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto">
        <PageHeader
          title="Settings"
          description="Platform configuration for embeddings, retrieval, and context management"
          extra={saved ? (
            <div className="flex items-center gap-2 text-status-success-foreground text-sm">
              <Check className="w-4 h-4" />
              Saved
            </div>
          ) : undefined}
        />

        {/* Appearance Section */}
        <section className="mb-8">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sun className="w-5 h-5 text-primary" />
                Appearance
              </CardTitle>
              <CardDescription>
                Choose your preferred color scheme
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex gap-3">
                <Button
                  variant={settings.theme === 'dark' ? 'default' : 'outline'}
                  className="flex-1"
                  onClick={() => updateSetting('theme', 'dark')}
                >
                  <Moon className="w-4 h-4 mr-2" />
                  Dark
                </Button>
                <Button
                  variant={settings.theme === 'light' ? 'default' : 'outline'}
                  className="flex-1"
                  onClick={() => updateSetting('theme', 'light')}
                >
                  <Sun className="w-4 h-4 mr-2" />
                  Light
                </Button>
                <Button
                  variant={settings.theme === 'system' ? 'default' : 'outline'}
                  className="flex-1"
                  onClick={() => updateSetting('theme', 'system')}
                >
                  <Monitor className="w-4 h-4 mr-2" />
                  System
                </Button>
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Interface Section */}
        <section className="mb-8">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sidebar className="w-5 h-5 text-primary" />
                Interface
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-foreground">
                    Sidebar Default State
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Start with sidebar collapsed
                  </p>
                </div>
                <Switch
                  checked={settings.sidebarCollapsed}
                  onCheckedChange={(checked) => updateSetting('sidebarCollapsed', checked)}
                />
              </div>
            </CardContent>
          </Card>
        </section>

        {/* RAG Settings Section */}
        <section className="mb-8">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="w-5 h-5 text-primary" />
                Library Settings
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 text-muted-foreground animate-spin" />
                </div>
              ) : backendConfig ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-4">
                    <div className="bg-muted rounded-lg p-4">
                      <div className="text-2xl font-bold text-foreground">
                        {backendConfig.chunk_size}
                      </div>
                      <div className="text-sm text-muted-foreground">Chunk Size</div>
                      <div className="text-xs text-muted-foreground/70 mt-1">Characters per chunk</div>
                    </div>
                    <div className="bg-muted rounded-lg p-4">
                      <div className="text-2xl font-bold text-foreground">
                        {backendConfig.chunk_overlap}
                      </div>
                      <div className="text-sm text-muted-foreground">Chunk Overlap</div>
                      <div className="text-xs text-muted-foreground/70 mt-1">Character overlap</div>
                    </div>
                    <div className="bg-muted rounded-lg p-4">
                      <div className="text-2xl font-bold text-foreground">
                        {backendConfig.retrieval_top_k}
                      </div>
                      <div className="text-sm text-muted-foreground">Documents per search</div>
                      <div className="text-xs text-muted-foreground/70 mt-1">Retrieved passages per query</div>
                    </div>
                  </div>
                  <div className="pt-4 border-t border-border">
                    <h4 className="text-sm font-medium text-foreground mb-3">File Upload</h4>
                    <div className="flex gap-4">
                      <div className="bg-muted rounded-lg px-4 py-2">
                        <span className="text-muted-foreground text-sm">Max Size: </span>
                        <span className="text-foreground font-medium">{backendConfig.max_upload_size_mb} MB</span>
                      </div>
                      <div className="bg-muted rounded-lg px-4 py-2">
                        <span className="text-muted-foreground text-sm">Allowed: </span>
                        <span className="text-foreground font-medium">{backendConfig.allowed_file_extensions}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-muted-foreground">Failed to load RAG settings</p>
              )}
            </CardContent>
          </Card>
        </section>

        {/* Reset Section */}
        <section className="mb-8">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-foreground">Reset Settings</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Restore all client-side settings to their defaults
                  </p>
                </div>
                <Button variant="secondary" onClick={resetToDefaults}>
                  <RotateCcw className="w-4 h-4 mr-2" />
                  Reset to Defaults
                </Button>
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Version Info */}
        <div className="text-center text-sm text-muted-foreground">
          <p>Agentbase v0.3.0</p>
          <p className="text-xs mt-1">
            Backend settings are configured via environment variables
          </p>
        </div>
      </div>
    </div>
  )
}
