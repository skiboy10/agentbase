import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import AuthGate from './components/AuthGate'
import { ErrorBoundary } from './components/ErrorBoundary'
import ProvidersPage from './pages/ProvidersPage'
import SourcesPage from './pages/SourcesPage'
import AutomationsPage from './pages/AutomationsPage'
import LibrariesPage from './pages/LibrariesPage'
import LibraryDetailPage from './pages/LibraryDetailPage'
import AgentbasePage from './pages/AgentbasePage'
import SettingsPage from './pages/SettingsPage'
import APIReferencePage from './pages/APIReferencePage'
import ExperimentsPage from './pages/ExperimentsPage'
import APIKeysPage from './pages/APIKeysPage'
import TaxonomyPage from './pages/TaxonomyPage'
import TaxonomyDetailPage from './pages/TaxonomyDetailPage'
import AgentQueryPage from './pages/AgentQueryPage'
import PromptStudioPage from './pages/PromptStudioPage'
import QuickstartPage from './pages/QuickstartPage'
import { Toaster } from './components/ui/toaster'

function App() {
  return (
    <ErrorBoundary>
    <AuthGate>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/sources" replace />} />
            <Route path="providers" element={<ProvidersPage />} />
            <Route path="sources" element={<SourcesPage />} />
            <Route path="automations" element={<AutomationsPage />} />
            <Route path="libraries" element={<LibrariesPage />} />
            <Route path="libraries/:libraryId" element={<LibraryDetailPage />} />
            <Route path="agents" element={<AgentbasePage />} />
            <Route path="agents/:agentId/query" element={<AgentQueryPage />} />
            <Route path="prompt-studio" element={<PromptStudioPage />} />
            <Route path="taxonomy" element={<TaxonomyPage />} />
            <Route path="taxonomy/:taxonomyId" element={<TaxonomyDetailPage />} />
            <Route path="experiments" element={<ExperimentsPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="api-reference" element={<APIReferencePage />} />
            <Route path="keys" element={<APIKeysPage />} />
            <Route path="quickstart" element={<QuickstartPage />} />
            {/* Backward compat redirects */}
            <Route path="knowledge" element={<Navigate to="/sources" replace />} />
            <Route path="knowledge-bases" element={<Navigate to="/libraries" replace />} />
            <Route path="knowledge-bases/:kbId" element={<Navigate to="/libraries" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster />
    </AuthGate>
    </ErrorBoundary>
  )
}

export default App
