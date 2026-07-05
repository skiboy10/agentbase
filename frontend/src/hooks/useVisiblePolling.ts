import { useEffect, useRef } from 'react'

interface UseVisiblePollingOptions {
  intervalMs: number
  enabled?: boolean
}

/**
 * Runs `onPoll` immediately, then on interval while the page is visible.
 * Also triggers a refresh when the window regains focus.
 */
export function useVisiblePolling(
  onPoll: () => Promise<void> | void,
  { intervalMs, enabled = true }: UseVisiblePollingOptions
) {
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const isPollingRef = useRef(false)

  useEffect(() => {
    if (!enabled) return

    const pollOnce = async () => {
      if (isPollingRef.current) return
      isPollingRef.current = true
      try {
        await onPoll()
      } finally {
        isPollingRef.current = false
      }
    }

    const stop = () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
    }

    const startIfVisible = () => {
      stop()
      if (document.visibilityState !== 'visible') return
      void pollOnce()
      pollingRef.current = setInterval(() => {
        void pollOnce()
      }, intervalMs)
    }

    const handleVisibilityChange = () => {
      startIfVisible()
    }

    const handleFocus = () => {
      if (document.visibilityState === 'visible') {
        void pollOnce()
      }
    }

    startIfVisible()
    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('focus', handleFocus)

    return () => {
      stop()
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('focus', handleFocus)
    }
  }, [enabled, intervalMs, onPoll])
}
