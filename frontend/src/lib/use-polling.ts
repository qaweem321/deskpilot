"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Load data now, again every `intervalMs` while the tab is visible, and whenever `load` or
 * `refreshKey` changes. Pass a stable `load` (useCallback), or it reloads on every render.
 */
export function usePolling<T>(load: () => Promise<T>, intervalMs: number, refreshKey = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    try {
      setData(await load());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load data.");
    }
  }, [load]);

  useEffect(() => {
    // Polling an external system: the state updates happen after the request, not during render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void run();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void run();
    }, intervalMs);
    return () => clearInterval(timer);
  }, [run, intervalMs, refreshKey]);

  return { data, error, reload: run };
}
