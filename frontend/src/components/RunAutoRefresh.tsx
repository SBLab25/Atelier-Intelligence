"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export const REFRESH_MS = 5_000;
export const MAX_REFRESH_MS = 10 * 60_000;

/**
 * Refreshes the run page while the run is in progress (Spec 14, OD-151): every 5 s, for at most 10 minutes, paused
 * while the tab is hidden. The page decides when to render this component (running or approved runs).
 */
export function RunAutoRefresh() {
  const router = useRouter();
  const [stopped, setStopped] = useState(false);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => {
      if (Date.now() - started > MAX_REFRESH_MS) {
        window.clearInterval(timer);
        setStopped(true);
        return;
      }
      if (!document.hidden) {
        router.refresh();
      }
    }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [router]);
  return (
    <p className="hint" role="status" aria-live="polite">
      {stopped
        ? "Automatic updates stopped after 10 minutes. Reload the page to see the latest status."
        : "This page updates every 5 seconds while the run is in progress."}
    </p>
  );
}
