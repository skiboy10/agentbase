import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
// Self-hosted fonts (offline-safe; no external CDN). Body: IBM Plex Sans, code: IBM Plex Mono.
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-sans/700.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import App from './App'
import './index.css'

// Apply persisted theme immediately to avoid flash
function initializeTheme() {
  try {
    const stored = localStorage.getItem('appSettings')
    const theme = stored ? JSON.parse(stored).theme : 'dark'
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches

    if (theme === 'light' || (theme === 'system' && !systemDark)) {
      document.documentElement.classList.remove('dark')
    } else {
      document.documentElement.classList.add('dark')
    }
  } catch {
    document.documentElement.classList.add('dark')
  }
}
initializeTheme()

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
