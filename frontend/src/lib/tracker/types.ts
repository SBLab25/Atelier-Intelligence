/**
 * CJI Official Client Telemetry SDK - Type Definitions
 */

export type CJIEventType =
  | "page_view"
  | "click"
  | "form_submit"
  | "error"
  | "rage_click"
  | "abandon"
  | "step_complete"
  | "identify";

export interface CJIConfig {
  /** Collector API endpoint (e.g. "https://api.yourdomain.com/collect/batch") */
  collector_url: string;
  /** Active Journey API key (e.g. "cji_live_...") */
  api_key: string;
  /** Primary journey name (e.g. "checkout_funnel") */
  journey_name: string;
  /** Optional mapping of step identifiers to URL path regexes */
  step_map?: Record<string, string>;
  /** Event batch size before triggering auto-flush (default: 20) */
  batch_size?: number;
  /** Periodic flush interval in milliseconds (default: 5000) */
  flush_interval?: number;
  /** Whether to capture window runtime and promise errors (default: true) */
  auto_capture_errors?: boolean;
  /** Whether to capture rapid multi-clicks as rage clicks (default: true) */
  auto_capture_rage_clicks?: boolean;
}

export interface TrackerEvent {
  event_id: string;
  timestamp: string;
  session_id: string;
  user_id: string;
  journey_name: string;
  step_id: string;
  event_type: CJIEventType;
  url: string;
  element_selectors: string | null;
  metadata: Record<string, unknown>;
}

export interface CJITrackerInstance {
  track: (type: CJIEventType, metadata?: Record<string, unknown>, targetElement?: HTMLElement | null) => void;
  trackStep: (stepName: string) => void;
  identify: (userId: string, traits?: Record<string, unknown>) => void;
  flush: () => void;
  getSessionId: () => string;
  getUserId: () => string;
  getCurrentStep: () => string;
  getDwellMs: () => number;
  getQueueLength: () => number;
}

declare global {
  interface Window {
    CJI_CONFIG?: CJIConfig;
    CJITracker?: CJITrackerInstance;
  }
}
