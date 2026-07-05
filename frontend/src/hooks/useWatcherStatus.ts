import { useState, useEffect, useRef, useCallback } from 'react';
import { sourcesApi } from '../services/api';
import type { Source, WatcherStatus } from '../services/api/types/sources';

const POLL_INTERVAL_MS = 15_000;

export function useWatcherStatus(sources: Source[]): Record<string, WatcherStatus | null> {
  const [statusMap, setStatusMap] = useState<Record<string, WatcherStatus | null>>({});
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Derive the stable set of source IDs that should be polled
  const pollableIds = sources
    .filter((s) => s.source_type === 'directory' && s.watch_enabled)
    .map((s) => s.id);
  const pollKey = pollableIds.join(',');

  const pollOnce = useCallback(async (ids: string[]) => {
    if (ids.length === 0) return;
    const results = await Promise.all(
      ids.map((id) => sourcesApi.getWatcherStatus(id).catch(() => null))
    );
    setStatusMap((prev) => {
      const next = { ...prev };
      ids.forEach((id, i) => {
        next[id] = results[i];
      });
      return next;
    });
  }, []);

  useEffect(() => {
    const ids = pollKey ? pollKey.split(',') : [];

    // Clear any previous interval
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (ids.length === 0) return;

    // Immediate first fetch, then poll
    pollOnce(ids);
    intervalRef.current = setInterval(() => pollOnce(ids), POLL_INTERVAL_MS);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [pollKey, pollOnce]);

  return statusMap;
}
