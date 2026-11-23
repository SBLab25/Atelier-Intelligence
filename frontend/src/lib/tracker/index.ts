"use client";

import { useEffect } from "react";
import type { CJIConfig, CJIEventType, CJITrackerInstance } from "./types";

export * from "./types";

/**
 * Initialize CJI Client Tracker on the page.
 * Attaches window.CJI_CONFIG and dynamically injects the tracker script if not yet loaded.
 */
export function initCJITracker(config: CJIConfig, scriptUrl?: string): CJITrackerInstance | null {
  if (typeof window === "undefined") {
    return null;
  }

  window.CJI_CONFIG = {
    ...window.CJI_CONFIG,
    ...config,
  };

  if (window.CJITracker) {
    return window.CJITracker;
  }

  const existingScript = document.querySelector('script[data-cji-tracker="true"]');
  if (!existingScript) {
    const script = document.createElement("script");
    const base = config.collector_url.replace(/\/collect\/batch$/, "");
    script.src = scriptUrl || `${base}/tracker.js`;
    script.defer = true;
    script.setAttribute("data-cji-tracker", "true");
    document.head.appendChild(script);
  }

  return window.CJITracker || null;
}

/**
 * React Hook for zero-config Customer Journey Intelligence tracking in Next.js & React apps.
 */
export function useCJITracker(config?: Partial<CJIConfig>): void {
  useEffect(() => {
    if (typeof window === "undefined") return;

    if (config?.api_key && config.collector_url && config.journey_name) {
      initCJITracker(config as CJIConfig);
    } else if (window.CJI_CONFIG) {
      initCJITracker(window.CJI_CONFIG);
    }
  }, [config]);
}

/**
 * Dispatch a custom telemetry event to the active CJI journey pipeline.
 */
export function trackEvent(
  type: CJIEventType,
  metadata: Record<string, unknown> = {},
  targetElement?: HTMLElement | null
): void {
  if (typeof window !== "undefined" && window.CJITracker) {
    window.CJITracker.track(type, metadata, targetElement);
  }
}

/**
 * Transition the active session to a custom journey step.
 */
export function trackStep(stepName: string): void {
  if (typeof window !== "undefined" && window.CJITracker) {
    window.CJITracker.trackStep(stepName);
  }
}

/**
 * Identify a user and associate custom profile traits with the current telemetry stream.
 */
export function identifyUser(userId: string, traits: Record<string, unknown> = {}): void {
  if (typeof window !== "undefined" && window.CJITracker) {
    window.CJITracker.identify(userId, traits);
  }
}

/**
 * Manually trigger an immediate flush of all queued telemetry events.
 */
export function flushEvents(): void {
  if (typeof window !== "undefined" && window.CJITracker) {
    window.CJITracker.flush();
  }
}
