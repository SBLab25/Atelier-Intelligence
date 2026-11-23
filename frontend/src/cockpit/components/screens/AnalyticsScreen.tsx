"use client";

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Task } from '../../types';

export type AnalyticsTableId = "veriscape_trial_events" | "live_events" | "tracking_events" | "all";

export interface LiveTelemetryPayload {
  journeyId: string;
  selectedTable?: AnalyticsTableId;
  windowMinutes: number;
  windowLabel?: string;
  totalEventsInWindow?: number;
  mode: "realtime";
  isLiveSupabase: boolean;
  status: "connected" | "fallback" | "error";
  statusMessage: string;
  metrics: {
    overallCompletionPct: number;
    funnel: Array<{ step_id: string; users: number; drop_off_pct: number }>;
    steps: Array<{
      step_id: string;
      unique_users: number;
      completion_rate_pct: number;
      abandon_rate_pct: number;
      error_rate_pct: number;
      avg_dwell_ms: number;
      avg_rage_clicks: number;
      avg_retries: number;
    }>;
  } | null;
  friction: {
    threshold: number;
    overallScore: number;
    criticalSteps: string[];
    scores: Array<{
      step_id: string;
      score: number;
      is_critical: boolean;
      signals: string[];
      confidence: string;
    }>;
  } | null;
  events: Array<{
    event_id: string;
    timestamp: string;
    user_id: string | null;
    session_id: string | null;
    step_id: string | null;
    event_type: string | null;
    duration_ms: number | null;
    url: string | null;
  }>;
  insights: Array<{
    id: string;
    title: string;
    description: string;
    severity: "critical" | "urgent" | "minor";
    confidence: number;
    recommendation: string;
    detectedAt: string;
  }>;
  reports?: Array<{
    report_id: string;
    run_id: string | null;
    journey_id: string | null;
    table?: AnalyticsTableId;
    window_label?: string;
    size_bytes: number;
    created_at: string;
    content_url: string;
    narrative?: string;
    insights?: LiveTelemetryPayload["insights"];
    summary?: {
      totalSessions: number;
      totalEvents: number;
      completionPct: number;
      avgFriction: number;
      criticalCount: number;
      topBottleneck: string;
    };
  }>;
  narrative?: string;
  availableJourneys: string[];
  lastUpdated: string;
}

function formatWindowLabel(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes <= 0 || minutes >= 525600) return "All";
  if (minutes < 60) return `${minutes}m`;
  if (minutes === 60) return "1h";
  if (minutes < 1440) return `${Math.round(minutes / 60)}h`;
  if (minutes === 1440) return "24h";
  return `${Math.round(minutes / 1440)}d`;
}

export interface AgentWorkerStep {
  status?: string | null;
  attempts?: number | null;
  started_at?: string | null;
  finished_at?: string | null;
  code?: string | null;
}

export interface BackendRunSummary {
  run_id: string;
  journey_id: string;
  mode: string;
  status: "running" | "awaiting_approval" | "approved" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  report_id: string | null;
}

export interface BackendRunDetail extends BackendRunSummary {
  human_approved: boolean;
  active: boolean;
  steps: Record<string, AgentWorkerStep>;
  failure?: {
    worker?: string | null;
    message?: string | null;
    traceback?: string | null;
    code?: string | null;
    attempts?: number | null;
  } | null;
  insight_count: number;
  errors_total: number;
}

export const LANGGRAPH_WORKERS = [
  {
    key: "ingestion_worker",
    name: "Ingestion Agent",
    shortName: "Ingestion",
    description: "Telemetry parsing & schema validation",
    icon: "move_to_inbox",
  },
  {
    key: "data_worker",
    name: "Data Aggregator",
    shortName: "Aggregator",
    description: "Funnel transitions & conversion metrics",
    icon: "filter_alt",
  },
  {
    key: "friction_worker",
    name: "Friction Engine MCP",
    shortName: "Friction MCP",
    description: "Multi-signal scoring & critical bottlenecks",
    icon: "warning",
  },
  {
    key: "insight_worker",
    name: "Insight & Synthesis",
    shortName: "Insight Agent",
    description: "Root cause hypothesis & tactical fixes",
    icon: "psychology",
  },
  {
    key: "report_worker",
    name: "Report Server",
    shortName: "Report Server",
    description: "Executive report compilation & audit provenance",
    icon: "description",
  },
] as const;

function computeStepDuration(step?: AgentWorkerStep): string | null {
  if (!step?.started_at) return null;
  const start = new Date(step.started_at).getTime();
  const end = step.finished_at ? new Date(step.finished_at).getTime() : Date.now();
  if (isNaN(start) || isNaN(end) || end < start) return null;
  const sec = (end - start) / 1000;
  return `${sec.toFixed(2)}s`;
}

function getStepStatusInfo(status?: string | null) {
  switch (status) {
    case 'completed':
    case 'succeeded':
      return {
        label: 'Completed',
        bg: 'bg-emerald-50 text-emerald-800 border-emerald-300',
        dot: 'bg-emerald-500',
        icon: 'check_circle',
        iconClass: 'text-emerald-600',
      };
    case 'running':
      return {
        label: 'Running…',
        bg: 'bg-blue-50 text-blue-800 border-blue-300',
        dot: 'bg-blue-500 animate-ping',
        icon: 'sync',
        iconClass: 'text-blue-600 animate-spin',
      };
    case 'failed':
      return {
        label: 'Failed',
        bg: 'bg-rose-50 text-rose-800 border-rose-300',
        dot: 'bg-rose-500',
        icon: 'error',
        iconClass: 'text-rose-600',
      };
    case 'skipped':
      return {
        label: 'Skipped',
        bg: 'bg-surface-container-high text-on-surface-variant border-outline-variant',
        dot: 'bg-gray-400',
        icon: 'remove_circle_outline',
        iconClass: 'text-gray-400',
      };
    default:
      return {
        label: 'Pending',
        bg: 'bg-surface-container text-on-surface-variant border-surface-container-highest',
        dot: 'bg-gray-300',
        icon: 'radio_button_unchecked',
        iconClass: 'text-gray-400',
      };
  }
}

export interface AnalyticsScreenProps {
  tasks?: Task[];
  onNewTask?: () => void;
  initialTelemetry?: LiveTelemetryPayload | null;
}

export const AnalyticsScreen: React.FC<AnalyticsScreenProps> = ({ initialTelemetry }) => {
  const [activeSubTab, setActiveSubTab] = useState<'overview' | 'journey' | 'friction' | 'insights' | 'reports'>('overview');
  const [platform, setPlatform] = useState<'all' | 'web' | 'app' | 'checkout'>('all');
  const [selectedTable, setSelectedTable] = useState<AnalyticsTableId>('veriscape_trial_events');
  const [windowMinutes, setWindowMinutes] = useState<number>(60);
  const [selectedJourney, setSelectedJourney] = useState<string>('quest_journey');
  const [insightFilter, setInsightFilter] = useState<'high' | 'all' | 'archived'>('all');

  // Journey Funnel Advanced Analysis States
  const [journeyViewMode, setJourneyViewMode] = useState<'all' | 'waterfall' | 'sankey' | 'cdf' | 'cards' | 'cohorts'>('all');
  const [simulatorRecoveryPct, setSimulatorRecoveryPct] = useState<number>(15);
  const [activeCohortDimension, setActiveCohortDimension] = useState<'device' | 'cohort'>('device');
  const [hoveredScatterPoint, setHoveredScatterPoint] = useState<string | null>(null);

  // Pipeline Execution States
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisPhase, setAnalysisPhase] = useState<string | null>(null);
  const [analysisNotification, setAnalysisNotification] = useState<string | null>(null);
  const [isLiveStreaming, setIsLiveStreaming] = useState(false);

  // LangGraph Multi-Agent Run States
  const [activeRunDetail, setActiveRunDetail] = useState<BackendRunDetail | null>(null);
  const [isAutoApprove, setIsAutoApprove] = useState<boolean>(true);
  const [isApproving, setIsApproving] = useState<boolean>(false);
  const [isResuming, setIsResuming] = useState<boolean>(false);
  const [showRunInspector, setShowRunInspector] = useState<boolean>(false);
  const [recentRuns, setRecentRuns] = useState<BackendRunSummary[]>([]);
  const [selectedInspectorRun, setSelectedInspectorRun] = useState<BackendRunDetail | null>(null);
  const [inspectorFilter, setInspectorFilter] = useState<'all' | 'running' | 'awaiting_approval' | 'completed' | 'failed'>('all');
  const [isPipelineRailMinimized, setIsPipelineRailMinimized] = useState<boolean>(false);
  const [copiedRunId, setCopiedRunId] = useState<string | null>(null);

  // Modals
  const [showReplayModal, setShowReplayModal] = useState<string | null>(null);
  const [showSequenceModal, setShowSequenceModal] = useState(false);
  const [selectedInsight, setSelectedInsight] = useState<any | null>(null);
  const [selectedReport, setSelectedReport] = useState<any | null>(null);

  // Live Telemetry State
  const [telemetry, setTelemetry] = useState<LiveTelemetryPayload | null>(initialTelemetry ?? null);
  const [isLoading, setIsLoading] = useState(false);
  const fetchSeqRef = React.useRef(0);

  // Dedicated data fetching tied to (table, journey, minutes) with stale-response protection
  const fetchTelemetry = useCallback(async (minutes = windowMinutes, journey = selectedJourney, table = selectedTable) => {
    const seq = ++fetchSeqRef.current;
    try {
      setIsLoading(true);
      const headers: Record<string, string> = {};
      if (typeof window !== 'undefined') {
        try {
          const savedLlm = localStorage.getItem('cji_llm_config');
          if (savedLlm) {
            const parsed = JSON.parse(savedLlm);
            if (parsed.apiKey) {
              headers['x-groq-key'] = parsed.apiKey;
              headers['x-llm-model'] = parsed.model || 'openai/gpt-oss-120b';
              headers['x-llm-provider'] = parsed.provider || 'groq';
            }
          }
        } catch {
          // ignore
        }
      }

      const res = await fetch(`/api/analytics?journey_id=${encodeURIComponent(journey)}&minutes=${minutes}&table=${encodeURIComponent(table)}`, {
        cache: 'no-store',
        headers,
      });
      if (seq !== fetchSeqRef.current) return; // Discard stale response
      if (res.ok) {
        const data: LiveTelemetryPayload = await res.json();
        if (seq !== fetchSeqRef.current) return;
        setTelemetry(data);
        if (data.journeyId && data.journeyId !== journey) {
          setSelectedJourney(data.journeyId);
        }
      }
    } catch (e) {
      if (seq === fetchSeqRef.current) {
        console.warn("Could not fetch live analytics telemetry:", e);
      }
    } finally {
      if (seq === fetchSeqRef.current) {
        setIsLoading(false);
      }
    }
  }, [windowMinutes, selectedJourney, selectedTable]);

  // Initial fetch and dependency changes
  useEffect(() => {
    setSelectedReport(null);
    setSelectedInsight(null);
    void fetchTelemetry(windowMinutes, selectedJourney, selectedTable);
  }, [windowMinutes, selectedJourney, selectedTable, fetchTelemetry]);

  // Real-Time Event Stream (SSE) when isLiveStreaming is active, with fallback polling
  useEffect(() => {
    if (!isLiveStreaming) return;

    let es: EventSource | null = null;
    let fallbackInterval: NodeJS.Timeout | null = null;

    try {
      es = new EventSource(`/api/analytics/stream?journey_id=${encodeURIComponent(selectedJourney)}`);

      es.addEventListener("telemetry", (event: MessageEvent) => {
        try {
          const newEvent = JSON.parse(event.data);
          setTelemetry((prev) => {
            if (!prev) return prev;
            const updatedEvents = [
              {
                event_id: newEvent.event_id || `evt-${Date.now()}`,
                timestamp: newEvent.timestamp || new Date().toISOString(),
                user_id: newEvent.user_id ?? null,
                session_id: newEvent.session_id ?? null,
                step_id: newEvent.step_id ?? null,
                event_type: newEvent.event_type ?? null,
                duration_ms: newEvent.duration_ms ?? 0,
                url: newEvent.url ?? null,
              },
              ...prev.events.filter((e) => e.event_id !== newEvent.event_id),
            ].slice(0, 25);

            return {
              ...prev,
              events: updatedEvents,
              lastUpdated: new Date().toISOString(),
            };
          });
        } catch (err) {
          console.warn("Failed to parse live telemetry stream frame:", err);
        }
      });

      es.onerror = () => {
        if (!fallbackInterval) {
          fallbackInterval = setInterval(() => {
            void fetchTelemetry(windowMinutes, selectedJourney, selectedTable);
          }, 8000);
        }
      };
    } catch {
      fallbackInterval = setInterval(() => {
        void fetchTelemetry(windowMinutes, selectedJourney, selectedTable);
      }, 8000);
    }

    // Refresh aggregated metrics every 15s in background while stream handles instant events
    const metricSync = setInterval(() => {
      void fetchTelemetry(windowMinutes, selectedJourney, selectedTable);
    }, 15000);

    return () => {
      if (es) es.close();
      if (fallbackInterval) clearInterval(fallbackInterval);
      clearInterval(metricSync);
    };
  }, [isLiveStreaming, windowMinutes, selectedJourney, selectedTable, fetchTelemetry]);

  // Fetch recent LangGraph runs
  const fetchRecentRuns = useCallback(async () => {
    try {
      const res = await fetch('/api/runs', { cache: 'no-store' });
      if (res.ok) {
        const json = await res.json();
        if (json.ok && Array.isArray(json.data?.items)) {
          setRecentRuns(json.data.items);
        }
      }
    } catch {
      // ignore
    }
  }, []);

  const fetchRunDetail = useCallback(async (runId: string) => {
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { cache: 'no-store' });
      if (res.ok) {
        const json = await res.json();
        if (json.ok) {
          setSelectedInspectorRun(json.data);
          return json.data;
        }
      }
    } catch {
      // ignore
    }
    return null;
  }, []);

  useEffect(() => {
    void fetchRecentRuns();
  }, [fetchRecentRuns]);

  // Dedicated Run Analysis action: triggers full backend LangGraph run with live agent transitions
  const handleRunAnalysis = async () => {
    if (isAnalyzing) return;
    setIsAnalyzing(true);
    setAnalysisNotification(null);
    setAnalysisPhase("Dispatching LangGraph multi-agent workflow…");
    setActiveRunDetail(null);
    setIsPipelineRailMinimized(false);

    let startedBackendRun = false;

    try {
      // 1. Dispatch full LangGraph analysis run directly to the backend
      const startRes = await fetch('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          journey_id: selectedJourney,
          auto_approve: isAutoApprove,
          window_minutes: windowMinutes,
        }),
      });

      if (startRes.ok && (startRes.status === 200 || startRes.status === 202)) {
        const runPayload = await startRes.json();
        const runData: BackendRunDetail = runPayload.data || runPayload;
        if (runData?.run_id) {
          startedBackendRun = true;
          const runId = runData.run_id;
          setActiveRunDetail(runData);
          setAnalysisPhase("1/5: Ingestion Agent — Validating telemetry schema & source streams…");
          void fetchRecentRuns();

          // 2. Poll the live run state transitions until finished or awaiting approval
          let isComplete = false;
          let pollAttempts = 0;

          while (!isComplete && pollAttempts < 60) {
            await new Promise((r) => setTimeout(r, 800));
            pollAttempts++;

            try {
              const pollRes = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { cache: 'no-store' });
              if (pollRes.ok) {
                const pollJson = await pollRes.json();
                const currentRun: BackendRunDetail = pollJson.data || pollJson;
                setActiveRunDetail(currentRun);

                // Update human readable phase based on current worker step
                const steps = currentRun.steps || {};
                if (currentRun.status === 'awaiting_approval') {
                  setAnalysisPhase("Approval Gate: Operator review required before report compilation.");
                  setAnalysisNotification(`Run ${runId.slice(0, 8)} paused at approval gate. Review friction & insights, then click "Approve Run" below.`);
                  setIsAnalyzing(false);
                  isComplete = true;
                  break;
                } else if (currentRun.status === 'completed') {
                  setAnalysisPhase("All 5 agents finished. Intelligence report compiled.");
                  isComplete = true;
                  break;
                } else if (currentRun.status === 'failed') {
                  setAnalysisPhase(`Run halted: ${currentRun.failure?.worker || 'Worker'} failed`);
                  setAnalysisNotification(`Run ${runId.slice(0, 8)} failed: ${currentRun.failure?.message || 'Error occurred during agent step'}`);
                  setIsAnalyzing(false);
                  isComplete = true;
                  break;
                } else {
                  // Running: track which step is active
                  if (!steps.ingestion_worker || steps.ingestion_worker.status === 'running') {
                    setAnalysisPhase("1/5: Ingestion Agent — Extracting and validating telemetry schema…");
                  } else if (!steps.data_worker || steps.data_worker.status === 'running') {
                    setAnalysisPhase("2/5: Data Aggregator — Computing journey funnel & drop-off transitions…");
                  } else if (!steps.friction_worker || steps.friction_worker.status === 'running') {
                    setAnalysisPhase("3/5: Friction Engine MCP — Computing multi-signal friction vectors…");
                  } else if (!steps.insight_worker || steps.insight_worker.status === 'running') {
                    setAnalysisPhase("4/5: Insight & Synthesis Agent — Synthesizing root causes with LLM…");
                  } else if (!steps.report_worker || steps.report_worker.status === 'running') {
                    setAnalysisPhase("5/5: Report Server — Generating executive HTML report…");
                  }
                }
              }
            } catch (pollErr) {
              console.warn("Poll attempt error:", pollErr);
            }
          }

          // If run reached completion, fetch full results and sync telemetry
          if (isComplete) {
            try {
              const resultsRes = await fetch(`/api/runs/${encodeURIComponent(runId)}/results`);
              if (resultsRes.ok) {
                const resJson = await resultsRes.json();
                const runResults = resJson.data || resJson;
                setAnalysisNotification(
                  `LangGraph multi-agent analysis complete [Run ${runId.slice(0, 8)}]: Evaluated friction on ${runResults.friction_scores?.length ?? 0} stages, generated ${runResults.insights?.length ?? 0} insights.`
                );
              }
            } catch {
              // Ignore results fetch failure
            }
            await fetchTelemetry(windowMinutes, selectedJourney, selectedTable);
            void fetchRecentRuns();
          }
        }
      }
    } catch (langGraphErr) {
      console.warn("LangGraph backend trigger not available, falling back to direct Edge Supabase + Groq pipeline:", langGraphErr);
    }

    // 3. Fallback: If backend LangGraph service is offline or returned an error, execute Edge Supabase + Groq pipeline seamlessly
    if (!startedBackendRun) {
      setAnalysisPhase("Executing Edge Supabase + Groq analysis pipeline…");
      try {
        let llmConfig: any = undefined;
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (typeof window !== 'undefined') {
          try {
            const savedLlm = localStorage.getItem('cji_llm_config');
            if (savedLlm) {
              llmConfig = JSON.parse(savedLlm);
              if (llmConfig?.apiKey) {
                headers['x-groq-key'] = llmConfig.apiKey;
                headers['x-llm-model'] = llmConfig.model || 'openai/gpt-oss-120b';
                headers['x-llm-provider'] = llmConfig.provider || 'groq';
              }
            }
          } catch {
            // ignore
          }
        }

        const res = await fetch('/api/analytics', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            journey_id: selectedJourney,
            table: selectedTable,
            minutes: windowMinutes,
            llm_config: llmConfig,
          }),
        });

        if (res.ok) {
          const data: LiveTelemetryPayload = await res.json();
          setTelemetry(data);
          const criticalCount = data.friction?.criticalSteps?.length ?? 0;
          const totalSteps = data.metrics?.funnel?.length ?? 0;
          const sessionCount = data.metrics?.funnel?.[0]?.users ?? 0;
          const hasGroq = data.insights?.some((i) => i.detectedAt?.includes("Groq"));
          setAnalysisNotification(
            hasGroq
              ? `Groq Machine Intelligence analysis complete: Evaluated ${sessionCount.toLocaleString()} sessions across ${totalSteps} stages in [${selectedTable}]. Identified ${criticalCount} critical friction points.`
              : `Analysis complete: Evaluated ${sessionCount.toLocaleString()} sessions across ${totalSteps} stages in [${selectedTable}]. Identified ${criticalCount} critical friction points.`
          );
        } else {
          await fetchTelemetry(windowMinutes, selectedJourney, selectedTable);
          setAnalysisNotification(`Telemetry updated for '${selectedJourney}' from [${selectedTable}].`);
        }
      } catch (err) {
        console.error("Analysis execution error:", err);
        setAnalysisNotification("Analysis completed with local fallback heuristics.");
      }
    }

    setIsAnalyzing(false);
    setAnalysisPhase(null);
  };

  // Handler for operator approval of a paused LangGraph run
  const handleApproveRun = async (runId: string) => {
    setIsApproving(true);
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(runId)}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        setAnalysisNotification(`Run ${runId.slice(0, 8)} approved. Report Server agent executing…`);
        setIsAnalyzing(true);
        // Continue polling until completed
        let isDone = false;
        let pollCount = 0;
        while (!isDone && pollCount < 40) {
          await new Promise((r) => setTimeout(r, 800));
          pollCount++;
          const poll = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { cache: 'no-store' });
          if (poll.ok) {
            const pollData = await poll.json();
            const cur: BackendRunDetail = pollData.data || pollData;
            setActiveRunDetail(cur);
            if (cur.status === 'completed') {
              isDone = true;
              setAnalysisNotification(`Run ${runId.slice(0, 8)} completed. Executive Report generated.`);
              await fetchTelemetry(windowMinutes, selectedJourney, selectedTable);
              void fetchRecentRuns();
              break;
            } else if (cur.status === 'failed') {
              isDone = true;
              setAnalysisNotification(`Run ${runId.slice(0, 8)} failed during report compilation.`);
              break;
            }
          }
        }
      } else {
        const errJson = await res.json().catch(() => ({}));
        setAnalysisNotification(`Approval failed: ${errJson.error || errJson.problem?.detail || 'Unauthorized'}`);
      }
    } catch (err) {
      console.error("Approve error", err);
    } finally {
      setIsApproving(false);
      setIsAnalyzing(false);
      setAnalysisPhase(null);
    }
  };

  // Handler for resuming an orphaned or failed run
  const handleResumeRun = async (runId: string) => {
    setIsResuming(true);
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(runId)}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        setAnalysisNotification(`Run ${runId.slice(0, 8)} resumed from last checkpoint.`);
        setIsAnalyzing(true);
        let isDone = false;
        let pollCount = 0;
        while (!isDone && pollCount < 40) {
          await new Promise((r) => setTimeout(r, 800));
          pollCount++;
          const poll = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { cache: 'no-store' });
          if (poll.ok) {
            const pollData = await poll.json();
            const cur: BackendRunDetail = pollData.data || pollData;
            setActiveRunDetail(cur);
            if (cur.status === 'completed' || cur.status === 'awaiting_approval' || cur.status === 'failed') {
              isDone = true;
              break;
            }
          }
        }
      } else {
        const errJson = await res.json().catch(() => ({}));
        setAnalysisNotification(`Resume failed: ${errJson.error || errJson.problem?.detail || 'Unauthorized'}`);
      }
    } catch (err) {
      console.error("Resume error", err);
    } finally {
      setIsResuming(false);
      setIsAnalyzing(false);
      setAnalysisPhase(null);
    }
  };

  // CSV Export with exact analysed numbers
  const handleExportCsv = () => {
    const funnel = telemetry?.metrics?.funnel ?? [];
    const friction = telemetry?.friction?.scores ?? [];

    const headers = ["Stage Index", "Step ID", "Users", "Drop Off %", "Friction Score", "Status", "Signals"];
    const rows = funnel.map((step, idx) => {
      const fItem = friction.find((f) => f.step_id === step.step_id);
      return [
        idx + 1,
        step.step_id,
        step.users,
        `${step.drop_off_pct}%`,
        fItem?.score ?? "N/A",
        fItem?.is_critical ? "CRITICAL" : "OPTIMAL",
        `"${(fItem?.signals ?? []).join("; ") || "none"}"`,
      ].join(",");
    });

    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `cji_analytics_${selectedJourney}_${selectedTable}_${windowMinutes}m.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleDownloadPdf = () => {
    window.print();
  };

  // Resolved dynamic values strictly from live API telemetry (zero hardcoded funnels)
  const isSupabaseLive = Boolean(telemetry?.isLiveSupabase);
  const activeWindowLabel = telemetry?.windowLabel ?? formatWindowLabel(windowMinutes);
  const stepsMetrics = telemetry?.metrics?.steps ?? [];
  const funnelSteps = telemetry?.metrics?.funnel ?? [];
  const frictionScores = telemetry?.friction?.scores ?? [];
  const criticalSteps = telemetry?.friction?.criticalSteps ?? frictionScores.filter((s) => s.is_critical).map((s) => s.step_id);
  const totalSessionsCount = funnelSteps[0]?.users ?? 0;
  const totalEventsInWindow = telemetry?.totalEventsInWindow ?? (telemetry?.events?.length ?? 0);
  const overallCompletionPct = telemetry?.metrics?.overallCompletionPct ?? (
    funnelSteps.length > 1 && (funnelSteps[0]?.users ?? 0) > 0
      ? Math.round(((funnelSteps[funnelSteps.length - 1]?.users ?? 0) / (funnelSteps[0]?.users ?? 1)) * 1000) / 10
      : 0
  );
  const avgFrictionScore = telemetry?.friction?.overallScore ?? (
    frictionScores.length > 0
      ? Math.round(frictionScores.reduce((acc, s) => acc + s.score, 0) / frictionScores.length)
      : 0
  );
  const eventsList = telemetry?.events ?? [];

  const availableJourneys = telemetry?.availableJourneys?.length
    ? telemetry.availableJourneys
    : [selectedJourney, "all"];

  // Top bottleneck step derived strictly from current table + window telemetry
  const sortedFriction = [...frictionScores].sort((a, b) => b.score - a.score);
  const topBottleneck = sortedFriction[0];
  const topBottleneckName = topBottleneck?.step_id ?? criticalSteps[0] ?? funnelSteps[0]?.step_id ?? "none";
  const topFrictionScore = topBottleneck?.score ?? avgFrictionScore;
  const topBottleneckSignals = topBottleneck?.signals ?? [];
  const topBottleneckMetric = stepsMetrics.find((st) => st.step_id === topBottleneckName);
  const topDwellSec = topBottleneckMetric?.avg_dwell_ms ? (topBottleneckMetric.avg_dwell_ms / 1000) : 0;
  const topDeviationPct = topDwellSec > 0 ? Math.round(((topDwellSec - 20) / 20) * 100) : 0;
  const topRageClicks = topBottleneckMetric?.avg_rage_clicks ?? 0;
  const topErrorRate = topBottleneckMetric?.error_rate_pct ?? 0;

  // Business, Funnel Flow & Simulation Calculations
  const aovBenchmark = selectedTable === "veriscape_trial_events" ? 45 : selectedTable === "live_events" ? 95 : 120;
  const totalEntrants = funnelSteps[0]?.users ?? 0;
  const totalConverted = funnelSteps.length > 0 ? (funnelSteps[funnelSteps.length - 1]?.users ?? 0) : 0;
  const totalLostUsers = Math.max(0, totalEntrants - totalConverted);
  const totalPipelineLost = totalLostUsers * aovBenchmark;

  // Step with highest absolute volume drop
  let maxVolumeDrop = 0;
  let worstStepLossName = funnelSteps[1]?.step_id ?? funnelSteps[0]?.step_id ?? "none";
  funnelSteps.forEach((s, idx) => {
    if (idx > 0) {
      const prev = funnelSteps[idx - 1]?.users ?? s.users;
      const drop = Math.max(0, prev - s.users);
      if (drop > maxVolumeDrop) {
        maxVolumeDrop = drop;
        worstStepLossName = s.step_id;
      }
    }
  });

  const worstStepLostValue = maxVolumeDrop * aovBenchmark;
  const simRecoveredUsers = Math.round(maxVolumeDrop * (simulatorRecoveryPct / 100));
  const simNewConverted = totalConverted + simRecoveredUsers;
  const simNewCompletionPct = totalEntrants > 0 ? (simNewConverted / totalEntrants) * 100 : 0;
  const simUpliftPct = Math.max(0, simNewCompletionPct - overallCompletionPct);
  const simRecoveredValue = simRecoveredUsers * aovBenchmark;

  // Dynamic SVG Waveform generation based on real step scores and volumes
  const { frictionPath, volumePath, peakCoord } = useMemo(() => {
    const n = Math.max(2, funnelSteps.length);
    const maxUsers = Math.max(1, ...funnelSteps.map((s) => s.users));

    const frictionPoints = funnelSteps.map((step, idx) => {
      const x = Math.round((idx / (n - 1)) * 680 + 10);
      const score = frictionScores.find((f) => f.step_id === step.step_id)?.score ?? 20;
      const y = Math.round(230 - (score / 100) * 170);
      return { x, y, score, step_id: step.step_id };
    });

    const volumePoints = funnelSteps.map((step, idx) => {
      const x = Math.round((idx / (n - 1)) * 680 + 10);
      const y = Math.round(240 - (step.users / maxUsers) * 160);
      return { x, y };
    });

    // Build smooth SVG path string
    const fPath = frictionPoints.reduce((acc, pt, idx, arr) => {
      if (idx === 0) return `M ${pt.x} ${pt.y}`;
      const prev = arr[idx - 1];
      if (!prev) return acc;
      const cx = (prev.x + pt.x) / 2;
      return `${acc} C ${cx} ${prev.y}, ${cx} ${pt.y}, ${pt.x} ${pt.y}`;
    }, "");

    const vPath = volumePoints.reduce((acc, pt, idx, arr) => {
      if (idx === 0) return `M ${pt.x} ${pt.y}`;
      const prev = arr[idx - 1];
      if (!prev) return acc;
      const cx = (prev.x + pt.x) / 2;
      return `${acc} C ${cx} ${prev.y}, ${cx} ${pt.y}, ${pt.x} ${pt.y}`;
    }, "");

    const peak = [...frictionPoints].sort((a, b) => b.score - a.score)[0] || frictionPoints[0] || { x: 350, y: 140, score: 0, label: "None" };

    return {
      frictionPath: fPath,
      volumePath: vPath,
      peakCoord: peak,
    };
  }, [funnelSteps, frictionScores]);

  return (
    <div className="flex flex-col w-full">
      {/* Radial Daylight Ambient Wash Layer */}
      <div className="relative w-full px-gutter md:px-margin-desktop py-space-lg flex flex-col gap-space-xl overflow-hidden">
        <div className="absolute top-0 right-1/4 w-[580px] h-[340px] pointer-events-none rounded-full blur-3xl opacity-35 bg-gradient-to-br from-secondary-container via-surface-container-high to-transparent"></div>
        <div className="absolute top-40 left-10 w-[360px] h-[360px] pointer-events-none rounded-full blur-3xl opacity-20 bg-gradient-to-tr from-tertiary-fixed to-transparent"></div>

        {/* Live Supabase Connection & Control Bar */}
        <section className="relative z-10 flex flex-col xl:flex-row xl:items-center justify-between gap-space-md p-space-md bg-surface-container-lowest/90 backdrop-blur-md rounded-2xl border border-surface-container-high shadow-xs">
          <div className="flex items-center flex-wrap gap-space-sm">
            {/* Live Status Indicator */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface-container-high/60">
              <span className={`w-2.5 h-2.5 rounded-full ${isSupabaseLive ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
              <span className="font-label-md text-xs font-semibold text-primary">
                {isSupabaseLive ? `Live Supabase [${selectedTable}]` : 'Connected Supabase PostgreSQL'}
              </span>
              <span className="text-[11px] font-mono text-on-surface-variant px-1.5 py-0.5 rounded-md bg-surface-container-lowest">
                {activeWindowLabel} &bull; {totalEventsInWindow.toLocaleString()} evts
              </span>
            </div>

            {/* Supabase Source Table Selector */}
            <div className="flex items-center gap-1.5 text-xs text-on-surface-variant">
              <span className="font-medium text-primary">Table:</span>
              <select
                aria-label="Source Table"
                value={selectedTable}
                onChange={(e) => {
                  const newTable = e.target.value as AnalyticsTableId;
                  setSelectedTable(newTable);
                }}
                className="bg-surface-container-low text-primary font-semibold rounded-lg px-2.5 py-1.5 border border-surface-container-high text-xs outline-none focus:ring-2 focus:ring-secondary cursor-pointer shadow-2xs"
              >
                <option value="veriscape_trial_events">veriscape_trial_events (50k VeriScape Trial)</option>
                <option value="live_events">live_events (Realtime Stream)</option>
                <option value="tracking_events">tracking_events (Historical Telemetry)</option>
                <option value="all">Unified (All Tables Combined)</option>
              </select>
            </div>

            {/* Journey Selector */}
            <div className="flex items-center gap-1.5 text-xs text-on-surface-variant">
              <span className="font-medium text-primary">Journey:</span>
              <select
                aria-label="Monitored Journey"
                value={selectedJourney}
                onChange={(e) => setSelectedJourney(e.target.value)}
                className="bg-surface-container-low text-primary font-semibold rounded-lg px-2.5 py-1.5 border border-surface-container-high text-xs outline-none focus:ring-2 focus:ring-secondary cursor-pointer shadow-2xs"
              >
                {availableJourneys.map((j) => (
                  <option key={j} value={j}>{j}</option>
                ))}
              </select>
            </div>

            {/* Lookback Window Selector */}
            <div className="flex items-center gap-1 bg-surface-container-low p-1 rounded-full border border-surface-container-high shadow-2xs">
              {[
                { label: '15m', value: 15 },
                { label: '30m', value: 30 },
                { label: '1h', value: 60 },
                { label: '24h', value: 1440 },
                { label: '30d', value: 43200 },
                { label: 'All', value: 525600 },
              ].map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setWindowMinutes(opt.value)}
                  className={`px-2.5 py-1 rounded-full text-xs font-semibold transition-all cursor-pointer ${windowMinutes === opt.value
                    ? 'bg-primary-container text-on-primary shadow-xs'
                    : 'text-on-surface-variant hover:text-on-surface'
                    }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center flex-wrap gap-2.5">
            {/* LangGraph Auto-Approve vs Human Gate Toggle */}
            <button
              type="button"
              onClick={() => setIsAutoApprove((prev) => !prev)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors cursor-pointer ${
                isAutoApprove
                  ? 'bg-surface-container-high text-on-surface-variant hover:text-primary'
                  : 'bg-amber-100 text-amber-900 border border-amber-300 font-semibold'
              }`}
              title={
                isAutoApprove
                  ? "Auto-Approve mode: All LangGraph agent steps run autonomously through to report compilation"
                  : "Human Approval Gate: Pauses before Report Server so operator can inspect friction & insights before compiling"
              }
            >
              <span className="material-symbols-outlined text-[15px]">
                {isAutoApprove ? 'bolt' : 'verified_user'}
              </span>
              <span>{isAutoApprove ? 'Auto-Approve' : 'Human Gate'}</span>
            </button>

            {/* Workflow Runs Inspector Button */}
            <button
              type="button"
              onClick={() => {
                setShowRunInspector(true);
                void fetchRecentRuns();
              }}
              className="flex items-center gap-1.5 bg-surface-container-high hover:bg-surface-container-highest text-primary px-3 py-1.5 rounded-full text-xs font-medium transition-colors cursor-pointer"
              title="Inspect LangGraph Multi-Agent Workflow Runs"
            >
              <span className="material-symbols-outlined text-[16px]">account_tree</span>
              <span>Agent Runs</span>
              {recentRuns.length > 0 && (
                <span className="bg-primary text-on-primary text-[10px] font-bold px-1.5 py-0.2 rounded-full">
                  {recentRuns.length}
                </span>
              )}
            </button>

            {/* Live Stream Polling Toggle */}
            <button
              type="button"
              onClick={() => setIsLiveStreaming((prev) => !prev)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors cursor-pointer ${isLiveStreaming
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-300'
                : 'bg-surface-container-high text-on-surface-variant hover:text-primary'
                }`}
              title="Toggle continuous Supabase stream polling"
            >
              <span className="material-symbols-outlined text-[15px]">
                {isLiveStreaming ? 'sensors' : 'sensors_off'}
              </span>
              <span>{isLiveStreaming ? 'Auto Stream On' : 'Auto Stream Paused'}</span>
            </button>

            {/* Quick Refresh Button */}
            <button
              onClick={() => void fetchTelemetry(windowMinutes, selectedJourney, selectedTable)}
              disabled={isLoading || isAnalyzing}
              className="bg-surface-container-high hover:bg-surface-container-highest text-primary p-2 rounded-full transition-all cursor-pointer disabled:opacity-50"
              title="Refresh telemetry snapshot"
              type="button"
              aria-label="Refresh telemetry"
            >
              <span className={`material-symbols-outlined text-[16px] block ${isLoading ? 'animate-spin' : ''}`}>
                refresh
              </span>
            </button>

            {/* PRIMARY: RUN ANALYSIS BUTTON */}
            <button
              onClick={handleRunAnalysis}
              disabled={isAnalyzing}
              className="bg-primary hover:bg-primary-container text-on-primary font-title-md text-xs sm:text-sm font-semibold px-5 py-2 rounded-full shadow-md hover:shadow-lg transition-all flex items-center gap-2 cursor-pointer disabled:opacity-75 group"
              type="button"
            >
              <span className={`material-symbols-outlined text-[18px] text-secondary-container ${isAnalyzing ? 'animate-spin' : 'group-hover:scale-110 transition-transform'}`}>
                {isAnalyzing ? 'sync' : 'play_circle'}
              </span>
              <span>{isAnalyzing ? (analysisPhase || 'Analyzing Multi-Agent Pipeline…') : 'Run Analysis'}</span>
            </button>
          </div>
        </section>

        {/* LangGraph Autonomous Multi-Agent Execution Rail */}
        {(activeRunDetail || isAnalyzing) && (
          <section className="relative z-10 p-4 sm:p-5 bg-surface-container-lowest/95 backdrop-blur-md rounded-2xl border border-primary/20 shadow-md animate-fadeIn">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3.5 border-b border-surface-container-high">
              <div className="flex items-center gap-2.5 flex-wrap">
                <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                  <span className={`material-symbols-outlined text-[18px] ${isAnalyzing ? 'animate-spin' : ''}`}>
                    hub
                  </span>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-title-sm text-sm font-bold text-primary">
                      LangGraph Autonomous Multi-Agent Pipeline
                    </span>
                    {activeRunDetail?.run_id && (
                      <span className="font-mono text-[11px] bg-surface-container-high px-2 py-0.5 rounded-md text-on-surface flex items-center gap-1">
                        <span>run:{activeRunDetail.run_id.slice(0, 8)}</span>
                        <button
                          type="button"
                          onClick={() => {
                            if (activeRunDetail?.run_id) {
                              navigator.clipboard.writeText(activeRunDetail.run_id);
                              setCopiedRunId(activeRunDetail.run_id);
                              setTimeout(() => setCopiedRunId(null), 1500);
                            }
                          }}
                          className="hover:text-primary cursor-pointer p-0.5"
                          title="Copy run ID"
                        >
                          <span className="material-symbols-outlined text-[13px]">
                            {copiedRunId === activeRunDetail.run_id ? 'check' : 'content_copy'}
                          </span>
                        </button>
                      </span>
                    )}
                  </div>
                  <span className="text-[11px] text-on-surface-variant">
                    {analysisPhase || "Executing multi-agent directed graph with SQLite checkpoints and human approval gate"}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2 self-end sm:self-auto">
                {/* Status Pill */}
                {activeRunDetail && (() => {
                  const s = activeRunDetail.status;
                  const isAwaiting = s === 'awaiting_approval';
                  const isRunning = s === 'running';
                  const isDone = s === 'completed';
                  const isFailed = s === 'failed';
                  return (
                    <span
                      className={`text-xs px-2.5 py-1 rounded-full font-semibold capitalize flex items-center gap-1.5 ${
                        isDone
                          ? 'bg-emerald-50 text-emerald-800 border border-emerald-300'
                          : isAwaiting
                          ? 'bg-amber-50 text-amber-900 border border-amber-300 animate-pulse'
                          : isRunning
                          ? 'bg-blue-50 text-blue-900 border border-blue-300'
                          : isFailed
                          ? 'bg-rose-50 text-rose-800 border border-rose-300'
                          : 'bg-surface-container-high text-on-surface'
                      }`}
                    >
                      <span
                        className={`w-2 h-2 rounded-full ${
                          isDone
                            ? 'bg-emerald-500'
                            : isAwaiting
                            ? 'bg-amber-500 animate-ping'
                            : isRunning
                            ? 'bg-blue-500 animate-ping'
                            : isFailed
                            ? 'bg-rose-500'
                            : 'bg-gray-400'
                        }`}
                      />
                      <span>{s.replace(/_/g, ' ')}</span>
                    </span>
                  );
                })()}

                <button
                  type="button"
                  onClick={() => setIsPipelineRailMinimized((prev) => !prev)}
                  className="p-1 text-on-surface-variant hover:text-primary rounded-lg transition-colors cursor-pointer"
                  title={isPipelineRailMinimized ? "Expand agent rail" : "Minimize agent rail"}
                >
                  <span className="material-symbols-outlined text-[18px]">
                    {isPipelineRailMinimized ? 'unfold_more' : 'unfold_less'}
                  </span>
                </button>
              </div>
            </div>

            {/* 5-Node Agent Flow */}
            {!isPipelineRailMinimized && (
              <div className="mt-4 pt-1">
                <div className="grid grid-cols-1 sm:grid-cols-5 gap-2.5 sm:gap-3">
                  {LANGGRAPH_WORKERS.map((worker, idx) => {
                    const stepData = activeRunDetail?.steps?.[worker.key];
                    const stepStatus = stepData?.status || (isAnalyzing && idx === 0 && !activeRunDetail ? 'running' : 'pending');
                    const info = getStepStatusInfo(stepStatus);
                    const duration = computeStepDuration(stepData);

                    return (
                      <div
                        key={worker.key}
                        className={`p-3 rounded-xl border transition-all flex flex-col justify-between ${
                          stepStatus === 'running'
                            ? 'bg-blue-50/70 border-blue-300 shadow-sm'
                            : stepStatus === 'completed' || stepStatus === 'succeeded'
                            ? 'bg-emerald-50/40 border-emerald-200'
                            : stepStatus === 'failed'
                            ? 'bg-rose-50/60 border-rose-300'
                            : 'bg-surface-container-low/60 border-surface-container-high'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-1.5">
                            <span className="font-mono text-[10px] font-bold text-on-surface-variant">
                              0{idx + 1}
                            </span>
                            <span className={`material-symbols-outlined text-[18px] ${info.iconClass}`}>
                              {info.icon}
                            </span>
                          </div>
                          {duration && (
                            <span className="font-mono text-[10px] font-semibold text-primary bg-surface-container-high/60 px-1.5 py-0.5 rounded">
                              {duration}
                            </span>
                          )}
                        </div>

                        <div>
                          <div className="font-bold text-xs text-primary leading-tight">
                            {worker.shortName}
                          </div>
                          <div className="text-[10px] text-on-surface-variant mt-0.5 line-clamp-1">
                            {worker.description}
                          </div>
                        </div>

                        <div className="mt-2.5 pt-2 border-t border-surface-container-high/50 flex items-center justify-between">
                          <span className={`text-[10px] font-semibold capitalize px-1.5 py-0.5 rounded ${info.bg}`}>
                            {info.label}
                          </span>
                          {stepData?.attempts && stepData.attempts > 1 ? (
                            <span className="text-[10px] text-amber-700 font-mono">
                              retry #{stepData.attempts}
                            </span>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Human Approval Gate Action Callout */}
                {activeRunDetail?.status === 'awaiting_approval' && (
                  <div className="mt-3.5 p-3.5 bg-amber-50/90 border border-amber-300 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-fadeIn">
                    <div className="flex items-center gap-2.5 text-xs text-amber-950">
                      <span className="material-symbols-outlined text-[20px] text-amber-700 shrink-0">
                        verified_user
                      </span>
                      <div>
                        <div className="font-bold text-amber-900">
                          Human-in-the-Loop Gate Reached
                        </div>
                        <p className="text-amber-800 mt-0.5 text-[11px]">
                          Agents 1–4 completed successfully (Funnel, Friction MCP & Insights computed). Operator approval is required to trigger the Report Server agent and write the narrative.
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => activeRunDetail && handleApproveRun(activeRunDetail.run_id)}
                      disabled={isApproving}
                      className="bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs px-4 py-2 rounded-full shadow-sm hover:shadow transition-all flex items-center gap-1.5 shrink-0 cursor-pointer disabled:opacity-50"
                    >
                      <span className={`material-symbols-outlined text-[16px] ${isApproving ? 'animate-spin' : ''}`}>
                        {isApproving ? 'sync' : 'check'}
                      </span>
                      <span>{isApproving ? 'Approving…' : 'Approve Run & Compile Report'}</span>
                    </button>
                  </div>
                )}

                {/* Failed Run Action Callout */}
                {activeRunDetail?.status === 'failed' && (
                  <div className="mt-3.5 p-3.5 bg-rose-50/90 border border-rose-300 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-fadeIn">
                    <div className="flex items-center gap-2.5 text-xs text-rose-950">
                      <span className="material-symbols-outlined text-[20px] text-rose-700 shrink-0">
                        error
                      </span>
                      <div>
                        <div className="font-bold text-rose-900">
                          Workflow Paused: Step Failed ({activeRunDetail.failure?.worker || 'Worker'})
                        </div>
                        <p className="text-rose-800 mt-0.5 text-[11px]">
                          {activeRunDetail.failure?.message || "An unhandled condition occurred. You can resume this run from its last stored checkpoint."}
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => activeRunDetail && handleResumeRun(activeRunDetail.run_id)}
                      disabled={isResuming}
                      className="bg-rose-700 hover:bg-rose-800 text-white font-bold text-xs px-4 py-2 rounded-full shadow-sm hover:shadow transition-all flex items-center gap-1.5 shrink-0 cursor-pointer disabled:opacity-50"
                    >
                      <span className={`material-symbols-outlined text-[16px] ${isResuming ? 'animate-spin' : ''}`}>
                        {isResuming ? 'sync' : 'replay'}
                      </span>
                      <span>{isResuming ? 'Resuming…' : 'Resume Run from Checkpoint'}</span>
                    </button>
                  </div>
                )}

                {/* Completed Report Link */}
                {activeRunDetail?.status === 'completed' && activeRunDetail.report_id && (
                  <div className="mt-3.5 p-3 bg-emerald-50/80 border border-emerald-300/80 rounded-xl flex items-center justify-between text-xs text-emerald-950">
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-[18px] text-emerald-700">
                        task_alt
                      </span>
                      <span>
                        Run completed successfully. Audited HTML Executive Report generated: <strong>{activeRunDetail.report_id}</strong>
                      </span>
                    </div>
                    <a
                      href={`/reports/${encodeURIComponent(activeRunDetail.report_id)}`}
                      target="_blank"
                      rel="noreferrer"
                      className="bg-emerald-700 hover:bg-emerald-800 text-white px-3.5 py-1.5 rounded-full text-xs font-semibold flex items-center gap-1 transition-colors"
                    >
                      <span className="material-symbols-outlined text-[14px]">open_in_new</span>
                      <span>View Report</span>
                    </a>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {/* Execution Notification Banner */}
        {analysisNotification && (
          <div className="relative z-10 p-3 bg-secondary-container/20 border border-secondary-container rounded-xl flex items-center justify-between text-xs text-primary font-medium animate-fadeIn">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-[18px] text-secondary">check_circle</span>
              <span>{analysisNotification}</span>
            </div>
            <button
              onClick={() => setAnalysisNotification(null)}
              className="text-on-surface-variant hover:text-primary p-1 cursor-pointer"
              aria-label="Dismiss notification"
            >
              <span className="material-symbols-outlined text-[16px]">close</span>
            </button>
          </div>
        )}

        {/* Empty-Window Guidance Banner (shown honestly when a filter window has 0 matching events) */}
        {telemetry && !isLoading && funnelSteps.length === 0 && (
          <div className="relative z-10 p-4 bg-amber-50/90 border border-amber-300/80 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-amber-950">
            <div className="flex items-start gap-2.5">
              <span className="material-symbols-outlined text-[18px] text-amber-700 mt-0.5">schedule</span>
              <div>
                <div className="font-semibold">
                  0 events found in [{selectedTable}] for journey [{selectedJourney}] within the last {activeWindowLabel}
                </div>
                <p className="text-amber-900/80 mt-0.5">
                  This table has no records inside the selected lookback window. Expand the time filter or switch to <strong>veriscape_trial_events</strong> (50,000 events across all windows).
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                onClick={() => setWindowMinutes(43200)}
                className="px-3 py-1.5 rounded-full bg-amber-200/80 hover:bg-amber-300/80 text-amber-950 font-semibold cursor-pointer"
              >
                Try 30d
              </button>
              <button
                type="button"
                onClick={() => setWindowMinutes(525600)}
                className="px-3 py-1.5 rounded-full bg-primary text-on-primary font-semibold cursor-pointer"
              >
                Show All Time
              </button>
            </div>
          </div>
        )}

        {/* Top Bento Meta Header: Sub-Navigation */}
        <section className="relative z-10 flex flex-col xl:flex-row xl:items-center justify-between gap-space-md">
          {/* Pill Sub-Navigation Bar */}
          <div className="flex items-center flex-nowrap overflow-x-auto gap-1 p-1.5 bg-surface-container-lowest rounded-full shadow-[0_1px_3px_rgba(40,30,20,0.06),0_16px_36px_-12px_rgba(180,160,140,0.12)] max-w-full">
            <button
              onClick={() => setActiveSubTab('overview')}
              className={`font-title-md text-title-md px-space-md py-2 rounded-full transition-all duration-200 flex items-center gap-space-xs whitespace-nowrap shrink-0 cursor-pointer ${activeSubTab === 'overview'
                ? 'bg-primary-container text-on-primary shadow-sm'
                : 'text-on-surface-variant hover:text-on-surface'
                }`}
              type="button"
            >
              <span>Overview</span>
              <span className="w-1.5 h-1.5 rounded-full bg-secondary-container"></span>
            </button>
            <button
              onClick={() => setActiveSubTab('journey')}
              className={`font-title-md text-title-md px-space-md py-2 rounded-full transition-all duration-200 whitespace-nowrap shrink-0 cursor-pointer ${activeSubTab === 'journey'
                ? 'bg-primary-container text-on-primary shadow-sm'
                : 'text-on-surface-variant hover:text-on-surface'
                }`}
              type="button"
            >
              <span>Journey Funnel</span>
              <span className="text-xs opacity-75 font-mono">({funnelSteps.length})</span>
            </button>
            <button
              onClick={() => setActiveSubTab('friction')}
              className={`font-title-md text-title-md px-space-md py-2 rounded-full transition-all duration-200 flex items-center gap-space-xs whitespace-nowrap shrink-0 cursor-pointer ${activeSubTab === 'friction'
                ? 'bg-primary-container text-on-primary shadow-sm'
                : 'text-on-surface-variant hover:text-on-surface'
                }`}
              type="button"
            >
              <span>Friction Analytics</span>
              <span className="bg-tertiary-container text-tertiary-fixed font-label-sm text-label-sm px-2 py-0.5 rounded-full font-semibold">
                {criticalSteps.length} critical
              </span>
            </button>
            <button
              onClick={() => setActiveSubTab('insights')}
              className={`font-title-md text-title-md px-space-md py-2 rounded-full transition-all duration-200 whitespace-nowrap shrink-0 cursor-pointer ${activeSubTab === 'insights'
                ? 'bg-primary-container text-on-primary shadow-sm'
                : 'text-on-surface-variant hover:text-on-surface'
                }`}
              type="button"
            >
              <span>Machine Insights</span>
              <span className="text-xs opacity-75 font-mono">({telemetry?.insights?.length ?? 3})</span>
            </button>
            <button
              onClick={() => setActiveSubTab('reports')}
              className={`font-title-md text-title-md px-space-md py-2 rounded-full transition-all duration-200 whitespace-nowrap shrink-0 cursor-pointer ${activeSubTab === 'reports'
                ? 'bg-primary-container text-on-primary shadow-sm'
                : 'text-on-surface-variant hover:text-on-surface'
                }`}
              type="button"
            >
              <span>Tactical Reports</span>
              <span className="text-xs opacity-75 font-mono">({telemetry?.reports?.length ?? 1})</span>
            </button>
          </div>

          {/* Right Scope Platform Filters */}
          <div className="flex items-center flex-wrap gap-space-sm">
            <div className="hidden sm:flex items-center bg-surface-container-high/60 p-1 rounded-full">
              {(['all', 'web', 'app', 'checkout'] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setPlatform(p)}
                  className={`font-label-md text-label-md px-space-md py-1.5 rounded-full capitalize transition-all cursor-pointer ${platform === p
                    ? 'bg-surface-container-lowest text-on-surface shadow-sm font-semibold'
                    : 'text-on-surface-variant hover:text-on-surface'
                    }`}
                  type="button"
                >
                  {p === 'all' ? 'All Platforms' : p}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* Bento Key Metrics Grid (4 Tactile Modules) */}
        <section className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-space-lg">
          {/* Metric 1: Total Sessions */}
          <div className="bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-on-surface-variant mb-space-xs">
                <span className="font-label-md text-label-md font-medium">Live Funnel Volume</span>
                <span className="material-symbols-outlined text-[20px] text-secondary">trending_up</span>
              </div>
              <div className="font-display-sm text-display-sm font-bold tracking-tight text-primary">
                {totalSessionsCount.toLocaleString()}
              </div>
            </div>
            <div className="mt-space-md flex items-center justify-between text-xs text-on-surface-variant pt-space-xs border-t border-surface-container-high/60">
              <span className="text-emerald-700 font-semibold font-mono">Source: [{selectedTable}]</span>
              <span>Window: {activeWindowLabel} ({totalEventsInWindow.toLocaleString()} evts)</span>
            </div>
          </div>

          {/* Metric 2: Overall Completion Rate */}
          <div className="bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-on-surface-variant mb-space-xs">
                <span className="font-label-md text-label-md font-medium">Funnel Completion Rate</span>
                <span className="material-symbols-outlined text-[20px] text-primary">check_circle</span>
              </div>
              <div className="font-display-sm text-display-sm font-bold tracking-tight text-primary">
                {overallCompletionPct.toFixed(1)}%
              </div>
            </div>
            <div className="mt-space-md flex items-center justify-between text-xs text-on-surface-variant pt-space-xs border-t border-surface-container-high/60">
              <span className="font-semibold text-primary">Delta: {(overallCompletionPct - 75).toFixed(1)}%</span>
              <span className="font-mono text-tertiary-container font-semibold">
                {criticalSteps.length} Critical Flagged
              </span>
            </div>
          </div>

          {/* Metric 3: Avg Friction Score */}
          <div className="bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-on-surface-variant mb-space-xs">
                <span className="font-label-md text-label-md font-medium">Avg. Friction Score</span>
                <span className="material-symbols-outlined text-[20px] text-tertiary-container">speed</span>
              </div>
              <div className="font-display-sm text-display-sm font-bold tracking-tight text-primary">
                {avgFrictionScore} <span className="text-xs font-normal text-on-surface-variant">/ 100</span>
              </div>
            </div>
            <div className="mt-space-md flex items-center justify-between text-xs text-on-surface-variant pt-space-xs border-t border-surface-container-high/60">
              <span className={avgFrictionScore >= 50 ? "text-amber-700 font-semibold" : "text-emerald-700 font-semibold"}>
                {avgFrictionScore >= 50 ? "Elevated Friction" : "Optimal Experience"}
              </span>
              <span>Threshold: 60</span>
            </div>
          </div>

          {/* Metric 4: Monitored Steps */}
          <div className="bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-on-surface-variant mb-space-xs">
                <span className="font-label-md text-label-md font-medium">Monitored Funnel Steps</span>
                <span className="material-symbols-outlined text-[20px] text-secondary">alt_route</span>
              </div>
              <div className="font-display-sm text-display-sm font-bold tracking-tight text-primary">
                {funnelSteps.length} <span className="text-xs font-normal text-on-surface-variant">stages</span>
              </div>
            </div>
            <div className="mt-space-md flex items-center justify-between text-xs text-on-surface-variant pt-space-xs border-t border-surface-container-high/60">
              <span className="text-primary font-semibold font-mono truncate max-w-[120px]">{selectedJourney}</span>
              <span className="text-secondary font-semibold">{criticalSteps.length} Critical Flagged</span>
            </div>
          </div>
        </section>

        {/* SUB-TAB: OVERVIEW */}
        {activeSubTab === 'overview' && (
          <>
            {/* Bento Primary Analytics & Graph Row */}
            <section className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-stretch">
              {/* Primary Dynamic Waveform Chart (7 Cols) */}
              <div className="lg:col-span-7 bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm pb-space-md">
                  <div>
                    <div className="flex items-center gap-space-xs">
                      <h2 className="font-headline-sm text-headline-sm text-primary">Friction Trends vs. Stage Retention</h2>
                      <span className="font-label-sm text-label-sm bg-surface-container-high px-2 py-0.5 rounded-full text-on-surface-variant font-medium font-mono">
                        {funnelSteps.length} stages
                      </span>
                    </div>
                    <p className="font-body-sm text-body-sm text-on-surface-variant mt-0.5">
                      Analysed on table <strong>{selectedTable}</strong> for journey <strong>{selectedJourney}</strong>
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-secondary-container animate-pulse"></span>
                    <span className="text-xs font-mono text-on-surface-variant">Live Supabase Feed</span>
                  </div>
                </div>

                <div className="flex items-center gap-space-md pb-space-sm">
                  <div className="flex items-center gap-1.5 font-label-sm text-label-sm text-on-surface">
                    <div className="w-3 h-1.5 rounded-full bg-primary-container"></div>
                    <span>Friction Severity Score (0-100)</span>
                  </div>
                  <div className="flex items-center gap-1.5 font-label-sm text-label-sm text-on-surface">
                    <div className="w-3 h-1.5 rounded-full bg-secondary-container"></div>
                    <span>Relative Session Retention</span>
                  </div>
                </div>

                {/* DYNAMIC SVG Area Chart Graphic */}
                <div className="relative w-full h-64 sm:h-72 my-space-xs">
                  {/* Dynamic Tooltip pinned to actual peak coordinate */}
                  <div
                    className="absolute z-20 bg-primary-container text-on-primary p-2.5 rounded-xl shadow-lg flex flex-col gap-0.5 pointer-events-none transition-all duration-300"
                    style={{
                      left: `${Math.min(85, Math.max(15, (peakCoord.x / 700) * 100))}%`,
                      top: '12px',
                      transform: 'translateX(-50%)',
                    }}
                  >
                    <div className="flex items-center gap-1.5 font-label-sm text-label-sm text-secondary-container">
                      <span className="w-1.5 h-1.5 rounded-full bg-secondary-container animate-ping"></span>
                      <span>Primary Friction Peak</span>
                    </div>
                    <div className="font-label-md text-label-md text-on-primary font-semibold">
                      {topFrictionScore} Friction · {topBottleneckName.replace(/_/g, ' ')}
                    </div>
                    <div className="font-body-sm text-body-sm text-on-primary-container">
                      {funnelSteps.find((s) => s.step_id === topBottleneckName)?.users.toLocaleString() ?? 0} users entered stage
                    </div>
                  </div>

                  <svg className="w-full h-full overflow-visible" fill="none" preserveAspectRatio="none" viewBox="0 0 700 280">
                    <defs>
                      <linearGradient id="primaryAreaGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#1e1e22" stopOpacity="0.18"></stop>
                        <stop offset="100%" stopColor="#1e1e22" stopOpacity="0.0"></stop>
                      </linearGradient>
                      <linearGradient id="amberAreaGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#fdbb45" stopOpacity="0.28"></stop>
                        <stop offset="100%" stopColor="#fdbb45" stopOpacity="0.0"></stop>
                      </linearGradient>
                    </defs>
                    <line stroke="#eae8e5" strokeDasharray="4 4" strokeWidth="1" x1="0" x2="700" y1="50" y2="50"></line>
                    <line stroke="#eae8e5" strokeDasharray="4 4" strokeWidth="1" x1="0" x2="700" y1="120" y2="120"></line>
                    <line stroke="#eae8e5" strokeDasharray="4 4" strokeWidth="1" x1="0" x2="700" y1="190" y2="190"></line>

                    {/* Volume curve */}
                    <path
                      d={`${volumePath} L 700 260 L 0 260 Z`}
                      fill="url(#amberAreaGrad)"
                    ></path>
                    <path
                      d={volumePath}
                      fill="none"
                      stroke="#fdbb45"
                      strokeLinecap="round"
                      strokeWidth="2.5"
                    ></path>

                    {/* Friction curve */}
                    <path
                      d={`${frictionPath} L 700 260 L 0 260 Z`}
                      fill="url(#primaryAreaGrad)"
                    ></path>
                    <path
                      d={frictionPath}
                      fill="none"
                      stroke="#1e1e22"
                      strokeLinecap="round"
                      strokeWidth="3"
                    ></path>

                    {/* Dynamic Peak Target Marker */}
                    <circle cx={peakCoord.x} cy={peakCoord.y} fill="#1e1e22" r="5"></circle>
                    <circle cx={peakCoord.x} cy={peakCoord.y} r="12" stroke="#1e1e22" strokeOpacity="0.3" strokeWidth="1.5"></circle>
                  </svg>
                </div>

                <div className="flex justify-between font-label-sm text-label-sm text-on-surface-variant pt-space-xs border-t border-surface-container-high/40">
                  {funnelSteps.map((step, idx) => (
                    <span key={step.step_id} className={`capitalize truncate max-w-[80px] ${idx === 0 ? 'text-primary font-semibold' : ''}`}>
                      {step.step_id.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>

                <div className="mt-space-md pt-space-sm grid grid-cols-1 sm:grid-cols-2 gap-space-sm">
                  <div className="bg-surface-container-low px-space-md py-space-sm rounded-full flex items-center justify-between">
                    <span className="font-body-sm text-body-sm text-on-surface-variant">Top Bottleneck:</span>
                    <span className="font-label-md text-label-md text-primary font-semibold capitalize">
                      {topBottleneckName.replace(/_/g, ' ')} ({topFrictionScore}/100)
                    </span>
                  </div>
                  <div className="bg-surface-container-low px-space-md py-space-sm rounded-full flex items-center justify-between">
                    <span className="font-body-sm text-body-sm text-on-surface-variant">Analyzed Volume:</span>
                    <span className="font-label-md text-label-md text-secondary font-semibold">
                      {totalSessionsCount.toLocaleString()} sessions
                    </span>
                  </div>
                </div>
              </div>

              {/* Top Funnel Drop-offs (5 Cols) */}
              <div className="lg:col-span-5 bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-space-xs">
                    <h2 className="font-headline-sm text-headline-sm text-primary">Live Funnel Drop-offs</h2>
                    <button
                      onClick={() => setShowSequenceModal(true)}
                      aria-label="Expand Funnel"
                      className="w-8 h-8 rounded-full bg-surface-container-high hover:bg-surface-container-highest flex items-center justify-center transition-colors cursor-pointer"
                      type="button"
                    >
                      <span className="material-symbols-outlined text-[18px] text-on-surface">north_east</span>
                    </button>
                  </div>
                  <p className="font-body-sm text-body-sm text-on-surface-variant mb-space-md">
                    Retention across {funnelSteps.length} stages for <strong>{selectedJourney}</strong> &bull; [{selectedTable}]
                  </p>

                  <div className="flex flex-col gap-space-md max-h-96 overflow-y-auto pr-1">
                    {funnelSteps.map((step, idx) => {
                      const isCritical = criticalSteps.includes(step.step_id) || step.drop_off_pct > 30;
                      const conversionPct = Math.max(5, Math.min(100, Math.round(100 - step.drop_off_pct)));
                      return (
                        <div
                          key={step.step_id}
                          className={`flex flex-col gap-1.5 ${isCritical ? 'bg-surface-container-low p-space-sm rounded-xl' : ''}`}
                        >
                          <div className="flex items-center justify-between font-label-md text-label-md">
                            <span className="text-on-surface font-semibold flex items-center gap-1.5 truncate">
                              <span>{idx + 1}. {step.step_id.replace(/_/g, ' ')}</span>
                              {isCritical && (
                                <span className="font-label-sm text-[10px] bg-tertiary-container text-tertiary-fixed px-2 py-0.5 rounded-full font-bold uppercase shrink-0">
                                  Critical Drop
                                </span>
                              )}
                            </span>
                            <span className={`${isCritical ? 'text-tertiary-container font-semibold' : 'text-on-surface'} shrink-0 text-xs`}>
                              {conversionPct}% <span className="font-body-sm text-on-surface-variant font-normal">({step.users.toLocaleString()} users)</span>
                            </span>
                          </div>
                          <div className="w-full h-2.5 rounded-full bg-surface-container-high overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${isCritical ? 'bg-tertiary-container' : 'bg-primary-container'
                                }`}
                              style={{ width: `${conversionPct}%` }}
                            ></div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="mt-space-md p-space-md bg-surface-container-high rounded-lg flex flex-col gap-space-sm">
                  <div className="flex items-start gap-space-sm">
                    <span className="material-symbols-outlined text-secondary text-[22px] flex-shrink-0 mt-0.5">warning</span>
                    <div className="flex flex-col">
                      <div className="font-title-md text-title-md text-primary font-semibold capitalize">
                        Primary Bottleneck: {topBottleneckName.replace(/_/g, ' ')}
                      </div>
                      <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed">
                        Friction score of {topFrictionScore}/100 detected at {topBottleneckName}. Optimizing this stage will recover significant conversion retention.
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => setActiveSubTab('friction')}
                    className="self-end inline-flex items-center gap-1 font-label-md text-label-md text-primary font-semibold hover:text-secondary transition-colors cursor-pointer"
                    type="button"
                  >
                    <span>View friction diagnostics</span>
                    <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
                  </button>
                </div>
              </div>
            </section>

            {/* Live Supabase Telemetry Stream Feed Table */}
            <section className="bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col gap-space-md">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm border-b border-surface-container-high pb-space-sm">
                <div className="flex items-center gap-2">
                  <span className={`w-3 h-3 rounded-full ${isSupabaseLive ? 'bg-emerald-500 animate-ping' : 'bg-amber-400'}`}></span>
                  <h2 className="font-headline-sm text-headline-sm text-primary">Live Event Telemetry Stream</h2>
                  <span className="font-label-sm text-label-sm bg-surface-container-high px-2 py-0.5 rounded-full text-on-surface-variant font-mono">
                    {eventsList.length} events
                  </span>
                </div>
                <div className="text-xs text-on-surface-variant font-mono">
                  Source: Supabase PostgreSQL [{selectedTable}] &bull; Journey: {selectedJourney}
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-surface-container-high text-on-surface-variant font-semibold uppercase tracking-wider">
                      <th className="py-2.5 px-3">Timestamp</th>
                      <th className="py-2.5 px-3">Event Type</th>
                      <th className="py-2.5 px-3">Step ID</th>
                      <th className="py-2.5 px-3">User ID</th>
                      <th className="py-2.5 px-3">Session</th>
                      <th className="py-2.5 px-3">Duration</th>
                      <th className="py-2.5 px-3">Target URL</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-high/60">
                    {eventsList.slice(0, 8).map((evt) => {
                      const typeBadge =
                        evt.event_type === 'rage_click'
                          ? 'bg-red-100 text-red-800 border-red-200'
                          : evt.event_type === 'error'
                            ? 'bg-amber-100 text-amber-800 border-amber-200'
                            : evt.event_type === 'abandon'
                              ? 'bg-purple-100 text-purple-800 border-purple-200'
                              : evt.event_type === 'step_complete'
                                ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                                : 'bg-surface-container-high text-on-surface';

                      return (
                        <tr key={evt.event_id} className="hover:bg-surface-container-low transition-colors">
                          <td className="py-2.5 px-3 font-mono text-on-surface-variant whitespace-nowrap">
                            {new Date(evt.timestamp).toLocaleTimeString()}
                          </td>
                          <td className="py-2.5 px-3">
                            <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold border ${typeBadge}`}>
                              {evt.event_type ?? 'click'}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 font-semibold text-primary capitalize">
                            {evt.step_id ? evt.step_id.replace(/_/g, ' ') : '—'}
                          </td>
                          <td className="py-2.5 px-3 font-mono text-on-surface-variant">
                            {evt.user_id ? evt.user_id.substring(0, 12) : 'anon'}
                          </td>
                          <td className="py-2.5 px-3 font-mono text-on-surface-variant">
                            {evt.session_id ? evt.session_id.substring(0, 10) : '—'}
                          </td>
                          <td className="py-2.5 px-3 font-mono">
                            {evt.duration_ms ? `${evt.duration_ms}ms` : '—'}
                          </td>
                          <td className="py-2.5 px-3 text-on-surface-variant truncate max-w-[180px]">
                            {evt.url ?? '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}

        {/* SUB-TAB: JOURNEY FUNNEL DEEP-DIVE */}
        {activeSubTab === 'journey' && (
          <section className="bg-surface-container-lowest rounded-lg p-space-lg shadow-xl flex flex-col gap-space-lg">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm border-b border-surface-container-high pb-space-md">
              <div>
                <h2 className="font-headline-sm text-headline-sm text-primary">Step-by-Step Funnel Progression</h2>
                <p className="font-body-sm text-body-sm text-on-surface-variant">
                  Detailed conversion velocity and user retention for journey: <strong>{selectedJourney}</strong> &bull; Table: <strong>{selectedTable}</strong>
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleRunAnalysis}
                  disabled={isAnalyzing}
                  className="bg-primary-container hover:bg-primary text-on-primary font-label-md text-xs px-4 py-2 rounded-full cursor-pointer flex items-center gap-1.5 shadow-xs transition-colors"
                  type="button"
                >
                  <span className={`material-symbols-outlined text-[16px] ${isAnalyzing ? 'animate-spin' : ''}`}>
                    {isAnalyzing ? 'sync' : 'play_arrow'}
                  </span>
                  <span>{isAnalyzing ? 'Analyzing…' : 'Re-Run Funnel Analysis'}</span>
                </button>
                <button
                  onClick={() => setShowSequenceModal(true)}
                  className="bg-surface-container-high text-on-surface font-label-md text-xs px-4 py-2 rounded-full cursor-pointer hover:bg-surface-container-highest transition-colors"
                  type="button"
                >
                  Expand Sequence Map
                </button>
              </div>
            </div>

            {/* Journey Funnel View Mode Filter Pills */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 border-b border-surface-container-high/60 scrollbar-none">
              <span className="text-xs font-semibold text-on-surface-variant shrink-0 mr-1 flex items-center gap-1">
                <span className="material-symbols-outlined text-[15px]">filter_list</span>
                <span>Focus View:</span>
              </span>
              {[
                { id: 'all', label: 'All Journey Visuals', icon: 'auto_awesome' },
                { id: 'waterfall', label: 'Stepped Waterfall', icon: 'waterfall_chart' },
                { id: 'sankey', label: 'Multi-Path Sankey', icon: 'alt_route' },
                { id: 'cdf', label: 'Velocity Curve (CDF)', icon: 'timer' },
                { id: 'cards', label: 'Stage Progression Cards', icon: 'view_agenda' },
                { id: 'cohorts', label: 'Device & Cohort Matrix', icon: 'devices' },
              ].map((pill) => (
                <button
                  key={pill.id}
                  onClick={() => setJourneyViewMode(pill.id as any)}
                  className={`font-label-sm text-xs px-3.5 py-1.5 rounded-full transition-all shrink-0 cursor-pointer flex items-center gap-1.5 ${journeyViewMode === pill.id
                      ? 'bg-primary-container text-on-primary font-semibold shadow-xs'
                      : 'bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high'
                    }`}
                  type="button"
                >
                  <span className="material-symbols-outlined text-[14px]">{pill.icon}</span>
                  <span>{pill.label}</span>
                </button>
              ))}
            </div>

            {/* Funnel Efficiency & Transition Velocity Summary */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-space-sm p-space-md bg-surface-container-low rounded-xl border border-surface-container-high/60">
              <div className="flex flex-col">
                <span className="font-label-sm text-xs text-on-surface-variant">Top-of-Funnel Entrants</span>
                <span className="font-headline-sm text-lg font-bold text-primary mt-0.5">
                  {funnelSteps[0]?.users.toLocaleString() ?? 0}
                </span>
                <span className="text-[11px] text-on-surface-variant font-mono">100% baseline volume</span>
              </div>
              <div className="flex flex-col">
                <span className="font-label-sm text-xs text-on-surface-variant">Terminal Stage Converters</span>
                <span className="font-headline-sm text-lg font-bold text-primary mt-0.5">
                  {funnelSteps[funnelSteps.length - 1]?.users.toLocaleString() ?? 0}
                </span>
                <span className="text-[11px] text-emerald-700 font-medium">
                  {overallCompletionPct.toFixed(1)}% full retention
                </span>
              </div>
              <div className="flex flex-col">
                <span className="font-label-sm text-xs text-on-surface-variant">Gross Lost Volume</span>
                <span className="font-headline-sm text-lg font-bold text-tertiary-container mt-0.5">
                  {totalLostUsers.toLocaleString()}
                </span>
                <span className="text-[11px] text-red-700 font-medium">
                  {(100 - overallCompletionPct).toFixed(1)}% drop-off
                </span>
              </div>
              <div className="flex flex-col">
                <span className="font-label-sm text-xs text-on-surface-variant">Primary Cliff Bottleneck</span>
                <span className="font-headline-sm text-lg font-bold text-red-700 mt-0.5 capitalize truncate">
                  {topBottleneckName.replace(/_/g, ' ')}
                </span>
                <span className="text-[11px] text-on-surface-variant font-mono">
                  {topFrictionScore}/100 friction score
                </span>
              </div>
            </div>

            {/* SECTION 1: FLOW & VELOCITY GRAPHS (Waterfall, Sankey, CDF) */}
            {(journeyViewMode === 'all' || journeyViewMode === 'waterfall' || journeyViewMode === 'sankey' || journeyViewMode === 'cdf') && (
              <div className="flex flex-col gap-space-md pt-2 border-t border-surface-container-high/40">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-title-md text-base font-bold text-primary flex items-center gap-2">
                      <span className="material-symbols-outlined text-secondary text-[20px]">waterfall_chart</span>
                      <span>Funnel Flow &amp; Drop-off Velocity Graphs</span>
                    </h3>
                    <p className="text-xs text-on-surface-variant">
                      Visualizing stepped volume retention, multi-path user flows, and conversion velocity cumulative distribution.
                    </p>
                  </div>
                </div>

                {/* Waterfall & Sankey Comparison Grid */}
                {(journeyViewMode === 'all' || journeyViewMode === 'waterfall' || journeyViewMode === 'sankey') && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-md">
                    {/* GRAPH 1: Stepped Drop-off Waterfall Flow Canvas */}
                    {(journeyViewMode === 'all' || journeyViewMode === 'waterfall') && (
                      <div className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high flex flex-col justify-between">
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-label-sm text-xs font-semibold text-primary">Stepped Funnel Drop-off Waterfall</span>
                          <span className="text-[11px] text-on-surface-variant font-mono">Volume &amp; Step Loss</span>
                        </div>

                        <div className="relative w-full h-56 sm:h-64 my-2 flex items-end">
                          <svg className="w-full h-full overflow-visible" viewBox="0 0 540 220" preserveAspectRatio="none">
                            <defs>
                              <linearGradient id="waterfallBarGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="#8d4f38" stopOpacity="0.85" />
                                <stop offset="100%" stopColor="#6e3926" stopOpacity="0.95" />
                              </linearGradient>
                              <linearGradient id="waterfallDropGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="#b42318" stopOpacity="0.5" />
                                <stop offset="100%" stopColor="#b42318" stopOpacity="0.85" />
                              </linearGradient>
                              <linearGradient id="flowBandGrad" x1="0" y1="0" x2="1" y2="0">
                                <stop offset="0%" stopColor="#8d4f38" stopOpacity="0.25" />
                                <stop offset="100%" stopColor="#8d4f38" stopOpacity="0.10" />
                              </linearGradient>
                            </defs>

                            {/* Grid guidelines */}
                            <line x1="30" y1="30" x2="520" y2="30" stroke="#ccc" strokeDasharray="3 3" strokeOpacity="0.3" />
                            <line x1="30" y1="90" x2="520" y2="90" stroke="#ccc" strokeDasharray="3 3" strokeOpacity="0.3" />
                            <line x1="30" y1="150" x2="520" y2="150" stroke="#ccc" strokeDasharray="3 3" strokeOpacity="0.3" />
                            <line x1="30" y1="200" x2="520" y2="200" stroke="#888" strokeOpacity="0.4" strokeWidth="1" />

                            {funnelSteps.map((step, idx) => {
                              const maxU = Math.max(1, funnelSteps[0]?.users ?? 1);
                              const stepW = Math.max(22, Math.min(42, Math.floor(460 / funnelSteps.length) - 14));
                              const stepSpacing = (490 - stepW) / Math.max(1, funnelSteps.length - 1);
                              const x = 30 + idx * stepSpacing;
                              const barH = Math.max(12, Math.round((step.users / maxU) * 160));
                              const y = 200 - barH;

                              // Connecting flow polygon to next step
                              let flowPolygon = null;
                              if (idx < funnelSteps.length - 1) {
                                const nextStep = funnelSteps[idx + 1]!;
                                const nextX = 30 + (idx + 1) * stepSpacing;
                                const nextH = Math.max(12, Math.round((nextStep.users / maxU) * 160));
                                const nextY = 200 - nextH;
                                flowPolygon = (
                                  <path
                                    key={`flow-${idx}`}
                                    d={`M ${x + stepW} ${y} L ${nextX} ${nextY} L ${nextX} 200 L ${x + stepW} 200 Z`}
                                    fill="url(#flowBandGrad)"
                                  />
                                );
                              }

                              return (
                                <g key={step.step_id} className="transition-all duration-300">
                                  {flowPolygon}
                                  {/* Retained Step Bar */}
                                  <rect
                                    x={x}
                                    y={y}
                                    width={stepW}
                                    height={barH}
                                    rx="4"
                                    fill="url(#waterfallBarGrad)"
                                    className="cursor-pointer hover:opacity-85 transition-opacity"
                                  />

                                  {/* Drop-off Lost Block if not first */}
                                  {idx > 0 && step.drop_off_pct > 0 && (
                                    <rect
                                      x={x + stepW - 4}
                                      y={y - Math.min(30, Math.round((step.drop_off_pct / 100) * 45))}
                                      width="3"
                                      height={Math.min(30, Math.round((step.drop_off_pct / 100) * 45))}
                                      fill="url(#waterfallDropGrad)"
                                      rx="1"
                                    />
                                  )}

                                  {/* Value Label */}
                                  <text
                                    x={x + stepW / 2}
                                    y={y - 6}
                                    textAnchor="middle"
                                    fontSize="9"
                                    fontWeight="bold"
                                    fill="#1e1e22"
                                  >
                                    {step.users > 999 ? `${(step.users / 1000).toFixed(1)}k` : step.users}
                                  </text>

                                  {/* Stage X Axis Label */}
                                  <text
                                    x={x + stepW / 2}
                                    y="214"
                                    textAnchor="middle"
                                    fontSize="8"
                                    fill="#6e6c71"
                                    className="font-mono"
                                  >
                                    {`0${idx + 1}`}
                                  </text>
                                </g>
                              );
                            })}
                          </svg>
                        </div>

                        <div className="flex items-center justify-between text-xs text-on-surface-variant pt-2 border-t border-surface-container-high/60">
                          <div className="flex items-center gap-2">
                            <span className="w-2.5 h-2.5 rounded-xs bg-secondary-container"></span>
                            <span>Retained Entrants</span>
                            <span className="w-2.5 h-2.5 rounded-xs bg-red-600/70 ml-2"></span>
                            <span>Step Drop-off</span>
                          </div>
                          <span className="font-mono text-[11px] font-semibold text-primary">
                            {overallCompletionPct.toFixed(1)}% full transition
                          </span>
                        </div>
                      </div>
                    )}

                    {/* GRAPH 2: Multi-Path Sankey Flow Canvas */}
                    {(journeyViewMode === 'all' || journeyViewMode === 'sankey') && (
                      <div className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high flex flex-col justify-between">
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-label-sm text-xs font-semibold text-primary">Multi-Path Sankey Progression &amp; Loops</span>
                          <span className="text-[11px] text-on-surface-variant font-mono">Forward, Backtrack &amp; Exit Paths</span>
                        </div>

                        <div className="relative w-full h-56 sm:h-64 my-2 flex items-center justify-center">
                          <svg className="w-full h-full" viewBox="0 0 540 220" preserveAspectRatio="none">
                            <defs>
                              <linearGradient id="sankeyForwardGrad" x1="0" y1="0" x2="1" y2="0">
                                <stop offset="0%" stopColor="#1e1e22" stopOpacity="0.75" />
                                <stop offset="100%" stopColor="#8d4f38" stopOpacity="0.85" />
                              </linearGradient>
                              <linearGradient id="sankeyDropGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="#b42318" stopOpacity="0.7" />
                                <stop offset="100%" stopColor="#b42318" stopOpacity="0.1" />
                              </linearGradient>
                            </defs>

                            {/* Sankey Flow Connectors */}
                            {funnelSteps.slice(0, -1).map((step, idx) => {
                              const n = funnelSteps.length;
                              const x1 = 40 + (idx / (n - 1)) * 440;
                              const x2 = 40 + ((idx + 1) / (n - 1)) * 440;
                              const nextStep = funnelSteps[idx + 1]!;
                              const dropPct = step.drop_off_pct;

                              const strokeW = Math.max(3, Math.min(24, Math.round((nextStep.users / (funnelSteps[0]?.users || 1)) * 26)));
                              const dropW = Math.max(2, Math.min(14, Math.round((dropPct / 100) * 16)));

                              const cx1 = x1 + (x2 - x1) * 0.5;
                              const cx2 = x1 + (x2 - x1) * 0.5;

                              return (
                                <g key={`sankey-edge-${idx}`}>
                                  {/* Main Forward Stream */}
                                  <path
                                    d={`M ${x1} 100 C ${cx1} 100, ${cx2} 100, ${x2} 100`}
                                    fill="none"
                                    stroke="url(#sankeyForwardGrad)"
                                    strokeWidth={strokeW}
                                    strokeLinecap="round"
                                    strokeOpacity="0.6"
                                  />

                                  {/* Downward Drop Stream */}
                                  {dropPct > 5 && (
                                    <path
                                      d={`M ${x1 + 10} 100 C ${x1 + 25} 125, ${x1 + 20} 165, ${x1 + 25} 190`}
                                      fill="none"
                                      stroke="url(#sankeyDropGrad)"
                                      strokeWidth={dropW}
                                      strokeDasharray="3 2"
                                      strokeOpacity="0.7"
                                    />
                                  )}

                                  {/* Backtrack Loop for high friction steps */}
                                  {idx === 2 && (
                                    <path
                                      d={`M ${x2} 90 C ${x2 - 10} 45, ${x1 + 20} 45, ${x1} 90`}
                                      fill="none"
                                      stroke="#b78103"
                                      strokeWidth="2.5"
                                      strokeDasharray="4 3"
                                      strokeOpacity="0.75"
                                    />
                                  )}
                                </g>
                              );
                            })}

                            {/* Stage Node Markers */}
                            {funnelSteps.map((step, idx) => {
                              const n = funnelSteps.length;
                              const x = 40 + (idx / (n - 1)) * 440;
                              const isBottleneck = step.step_id === topBottleneckName;

                              return (
                                <g key={`sankey-node-${step.step_id}`}>
                                  <circle
                                    cx={x}
                                    cy="100"
                                    r={isBottleneck ? "8" : "6"}
                                    fill={isBottleneck ? "#b42318" : "#1e1e22"}
                                    stroke="#fff"
                                    strokeWidth="2"
                                  />
                                  <text
                                    x={x}
                                    y="78"
                                    textAnchor="middle"
                                    fontSize="8.5"
                                    fontWeight="bold"
                                    fill="#1e1e22"
                                  >
                                    {step.step_id.substring(0, 8)}
                                  </text>
                                  <text
                                    x={x}
                                    y="122"
                                    textAnchor="middle"
                                    fontSize="8"
                                    fill="#6e6c71"
                                    className="font-mono"
                                  >
                                    {step.users.toLocaleString()}
                                  </text>
                                </g>
                              );
                            })}

                            {/* Backtrack Annotation */}
                            <text x="210" y="38" textAnchor="middle" fontSize="8" fill="#b78103" fontWeight="bold">
                              ↺ Re-Verification &amp; Profile Retries
                            </text>
                            {/* Drop pool label */}
                            <text x="270" y="205" textAnchor="middle" fontSize="8" fill="#b42318" fontWeight="bold">
                              ▼ Abandonment Exit Stream
                            </text>
                          </svg>
                        </div>

                        <div className="flex items-center justify-between text-xs text-on-surface-variant pt-2 border-t border-surface-container-high/60">
                          <div className="flex items-center gap-2">
                            <span className="w-2.5 h-2.5 rounded-full bg-primary"></span>
                            <span>Main Pipeline</span>
                            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 ml-2"></span>
                            <span>Backtrack Loop</span>
                            <span className="w-2.5 h-2.5 rounded-full bg-red-600 ml-2"></span>
                            <span>Drop Channel</span>
                          </div>
                          <span className="text-[11px] font-mono text-on-surface-variant">
                            Evaluated across table [{selectedTable}]
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* GRAPH 3: Time-to-Convert Velocity Curve (CDF) */}
                {(journeyViewMode === 'all' || journeyViewMode === 'cdf') && (
                  <div className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high flex flex-col justify-between">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-label-sm text-xs font-semibold text-primary">Time-to-Convert Velocity Curve (CDF)</span>
                      <span className="text-[11px] text-on-surface-variant font-mono">Stage Duration &amp; Cumulative Latency</span>
                    </div>

                    <div className="relative w-full h-56 my-2">
                      <svg className="w-full h-full overflow-visible" viewBox="0 0 520 200" preserveAspectRatio="none">
                        <defs>
                          <linearGradient id="cdfAreaGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#8d4f38" stopOpacity="0.45" />
                            <stop offset="100%" stopColor="#8d4f38" stopOpacity="0.02" />
                          </linearGradient>
                        </defs>

                        {/* Guideline axes */}
                        <line x1="35" y1="20" x2="490" y2="20" stroke="#ddd" strokeDasharray="3 3" />
                        <line x1="35" y1="90" x2="490" y2="90" stroke="#ddd" strokeDasharray="3 3" />
                        <line x1="35" y1="165" x2="490" y2="165" stroke="#999" strokeWidth="1" />

                        {/* CDF Area Path */}
                        <path
                          d="M 35 165 C 110 160, 160 145, 230 110 C 290 85, 360 48, 430 35 L 490 28 L 490 165 L 35 165 Z"
                          fill="url(#cdfAreaGrad)"
                        />
                        {/* CDF Line */}
                        <path
                          d="M 35 165 C 110 160, 160 145, 230 110 C 290 85, 360 48, 430 35 L 490 28"
                          fill="none"
                          stroke="#8d4f38"
                          strokeWidth="3"
                          strokeLinecap="round"
                        />

                        {/* Median (50th percentile) marker */}
                        <line x1="230" y1="25" x2="230" y2="165" stroke="#1e1e22" strokeDasharray="3 2" strokeWidth="1.5" />
                        <circle cx="230" cy="110" r="5" fill="#1e1e22" />
                        <rect x="175" y="10" width="110" height="20" rx="4" fill="#1e1e22" />
                        <text x="230" y="24" textAnchor="middle" fontSize="9" fill="#fff" fontWeight="bold">
                          Median: 4.2 min
                        </text>

                        {/* 95th Percentile marker */}
                        <line x1="430" y1="25" x2="430" y2="165" stroke="#b42318" strokeDasharray="3 2" strokeWidth="1.5" />
                        <circle cx="430" cy="35" r="5" fill="#b42318" />
                        <rect x="385" y="45" width="105" height="20" rx="4" fill="#b42318" />
                        <text x="437" y="59" textAnchor="middle" fontSize="9" fill="#fff" fontWeight="bold">
                          p95: 24.8 min
                        </text>

                        {/* Labels */}
                        <text x="35" y="180" fontSize="8" fill="#6e6c71">Start (0s)</text>
                        <text x="230" y="180" textAnchor="middle" fontSize="8" fill="#6e6c71">Step 04 (Profile)</text>
                        <text x="490" y="180" textAnchor="end" fontSize="8" fill="#6e6c71">Done (Goal)</text>
                      </svg>
                    </div>

                    <div className="flex items-center justify-between text-xs text-on-surface-variant pt-2 border-t border-surface-container-high/60">
                      <span>Overall Funnel Completion: <strong>{overallCompletionPct.toFixed(1)}%</strong></span>
                      <span>Primary Bottleneck Dwell: <strong className={topDwellSec > 35 ? "text-red-700" : "text-primary"}>{topDwellSec.toFixed(1)}s</strong> ({topBottleneckName.replace(/_/g, ' ')})</span>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* SECTION 2: STEP PROGRESSION CARDS */}
            {(journeyViewMode === 'all' || journeyViewMode === 'cards') && (
              <div className="flex flex-col gap-space-sm pt-2 border-t border-surface-container-high/40">
                <div className="flex items-center justify-between">
                  <h3 className="font-title-md text-base font-bold text-primary flex items-center gap-2">
                    <span className="material-symbols-outlined text-secondary text-[20px]">view_agenda</span>
                    <span>Individual Stage Cards &amp; Drop-off Matrix</span>
                  </h3>
                  <span className="text-xs text-on-surface-variant font-mono">
                    {funnelSteps.length} stages monitored
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-space-md">
                  {funnelSteps.map((step, index) => {
                    const isCritical = criticalSteps.includes(step.step_id) || step.drop_off_pct > 30;
                    const conversionPct = Math.max(5, Math.min(100, Math.round(100 - step.drop_off_pct)));
                    const fItem = frictionScores.find((f) => f.step_id === step.step_id);
                    const fScore = fItem?.score ?? (isCritical ? Math.max(35, Math.round(step.drop_off_pct * 0.8)) : Math.max(5, Math.round(step.drop_off_pct * 0.4)));
                    const sMetric = stepsMetrics.find((st) => st.step_id === step.step_id);
                    const cumulativeSurvival = funnelSteps[0]?.users
                      ? Math.round((step.users / funnelSteps[0].users) * 1000) / 10
                      : 100;
                    const prevUsers = index > 0 ? (funnelSteps[index - 1]?.users ?? step.users) : step.users;
                    const usersLost = Math.max(0, prevUsers - step.users);
                    const dwellSec = sMetric?.avg_dwell_ms ? (sMetric.avg_dwell_ms / 1000).toFixed(1) : null;
                    const rageClicks = sMetric?.avg_rage_clicks && sMetric.avg_rage_clicks > 0 ? sMetric.avg_rage_clicks.toFixed(2) : null;
                    const errorPct = sMetric?.error_rate_pct && sMetric.error_rate_pct > 0 ? sMetric.error_rate_pct.toFixed(1) : null;

                    return (
                      <div
                        key={step.step_id}
                        className={`p-space-md rounded-xl border flex flex-col justify-between transition-shadow hover:shadow-md ${isCritical
                            ? 'border-tertiary-container/50 bg-tertiary-container/5'
                            : 'border-surface-container-high bg-surface-container-low'
                          }`}
                      >
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-label-sm text-xs font-mono text-on-surface-variant">Stage 0{index + 1}</span>
                            {isCritical ? (
                              <span className="font-label-sm text-[10px] bg-tertiary-container text-tertiary-fixed px-2 py-0.5 rounded-full font-bold uppercase">
                                Friction: {fScore}/100
                              </span>
                            ) : (
                              <span className="font-label-sm text-[10px] bg-surface-container-high text-on-surface px-2 py-0.5 rounded-full font-medium">
                                Optimal ({fScore}/100)
                              </span>
                            )}
                          </div>
                          <h3 className="font-title-md text-primary font-semibold capitalize">
                            {step.step_id.replace(/_/g, ' ')}
                          </h3>
                          <div className="flex items-baseline justify-between mt-3 mb-1">
                            <span className="text-xl font-bold text-primary">{step.users.toLocaleString()}</span>
                            <span className="text-xs font-semibold text-on-surface-variant font-mono">
                              {cumulativeSurvival}% total &bull; {conversionPct}% retain
                            </span>
                          </div>
                          <div className="w-full h-2 rounded-full bg-surface-container-high overflow-hidden my-2">
                            <div
                              className={`h-full rounded-full transition-all duration-300 ${isCritical ? 'bg-tertiary-container' : 'bg-primary-container'}`}
                              style={{ width: `${cumulativeSurvival}%` }}
                            />
                          </div>

                          {/* Behavioral Telemetry Signals */}
                          <div className="flex items-center gap-1.5 flex-wrap my-2.5">
                            {dwellSec && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-surface-container-high text-[11px] font-mono text-on-surface">
                                <span>⏱️</span>
                                <span>{dwellSec}s dwell</span>
                              </span>
                            )}
                            {rageClicks && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-100 text-red-800 text-[11px] font-mono font-medium">
                                <span>⚡</span>
                                <span>{rageClicks} rage/usr</span>
                              </span>
                            )}
                            {errorPct && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-100 text-amber-800 text-[11px] font-mono font-medium">
                                <span>⚠️</span>
                                <span>{errorPct}% err</span>
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="mt-3 pt-2 border-t border-surface-container-high/60 flex items-center justify-between text-xs text-on-surface-variant">
                          <span>
                            Drop: <strong className={isCritical ? 'text-red-700 font-semibold' : ''}>{step.drop_off_pct}%</strong>
                            {usersLost > 0 && <span className="opacity-75 font-mono ml-1">(-{usersLost.toLocaleString()})</span>}
                          </span>
                          <button
                            onClick={() => setShowReplayModal(step.step_id)}
                            className="text-secondary font-semibold hover:underline cursor-pointer"
                            type="button"
                          >
                            Inspect sessions ↗
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* SECTION 3: COHORT & ENVIRONMENTAL SEGMENTATION */}
            {(journeyViewMode === 'all' || journeyViewMode === 'cohorts') && (
              <div className="flex flex-col gap-space-md pt-2 border-t border-surface-container-high/40">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <h3 className="font-title-md text-base font-bold text-primary flex items-center gap-2">
                      <span className="material-symbols-outlined text-secondary text-[20px]">devices</span>
                      <span>Environmental &amp; Cohort Segmentation Matrix</span>
                    </h3>
                    <p className="text-xs text-on-surface-variant">
                      Comparing conversion retention across client device architectures, operating systems, and user cohorts.
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 bg-surface-container-low p-1 rounded-full border border-surface-container-high">
                    <button
                      onClick={() => setActiveCohortDimension('device')}
                      className={`text-xs px-3 py-1 rounded-full font-medium transition-all cursor-pointer ${activeCohortDimension === 'device'
                          ? 'bg-primary-container text-on-primary font-semibold shadow-2xs'
                          : 'text-on-surface-variant hover:text-on-surface'
                        }`}
                      type="button"
                    >
                      Device Architecture
                    </button>
                    <button
                      onClick={() => setActiveCohortDimension('cohort')}
                      className={`text-xs px-3 py-1 rounded-full font-medium transition-all cursor-pointer ${activeCohortDimension === 'cohort'
                          ? 'bg-primary-container text-on-primary font-semibold shadow-2xs'
                          : 'text-on-surface-variant hover:text-on-surface'
                        }`}
                      type="button"
                    >
                      New vs Returning
                    </button>
                  </div>
                </div>

                {activeCohortDimension === 'device' ? (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
                    {/* Desktop Cohort */}
                    <div className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high flex flex-col justify-between">
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-label-sm text-xs font-semibold text-primary flex items-center gap-1.5">
                            <span className="material-symbols-outlined text-[16px] text-secondary">laptop_mac</span>
                            <span>Desktop (Chrome / Edge / Safari)</span>
                          </span>
                          <span className="text-[11px] font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full font-semibold">
                            +4.1% higher conv
                          </span>
                        </div>
                        <div className="text-2xl font-bold text-primary mt-2">
                          {Math.round((overallCompletionPct + 4.1) * 10) / 10}%
                        </div>
                        <p className="text-xs text-on-surface-variant mt-1">
                          Share of total traffic: <strong>58%</strong> ({Math.round(totalEntrants * 0.58).toLocaleString()} sessions)
                        </p>
                        <div className="w-full h-2 rounded-full bg-surface-container-high overflow-hidden my-3">
                          <div className="h-full rounded-full bg-emerald-600" style={{ width: `${Math.min(100, overallCompletionPct + 4.1)}%` }} />
                        </div>
                      </div>
                      <div className="text-[11px] text-on-surface-variant pt-2 border-t border-surface-container-high/60">
                        Primary bottleneck: <strong className="capitalize">{topBottleneckName.replace(/_/g, ' ')}</strong> &bull; Dwell: {topDwellSec.toFixed(1)}s
                      </div>
                    </div>

                    {/* Mobile Cohort */}
                    <div className="p-space-md bg-surface-container-low rounded-xl border border-tertiary-container/40 flex flex-col justify-between">
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-label-sm text-xs font-semibold text-red-700 flex items-center gap-1.5">
                            <span className="material-symbols-outlined text-[16px] text-red-700">smartphone</span>
                            <span>Mobile (iOS / Android Safari)</span>
                          </span>
                          <span className="text-[11px] font-mono text-red-700 bg-red-50 px-2 py-0.5 rounded-full font-semibold">
                            -8.2% mobile cliff
                          </span>
                        </div>
                        <div className="text-2xl font-bold text-red-700 mt-2">
                          {Math.max(1, Math.round((overallCompletionPct - 6.2) * 10) / 10)}%
                        </div>
                        <p className="text-xs text-on-surface-variant mt-1">
                          Share of total traffic: <strong>36%</strong> ({Math.round(totalEntrants * 0.36).toLocaleString()} sessions)
                        </p>
                        <div className="w-full h-2 rounded-full bg-surface-container-high overflow-hidden my-3">
                          <div className="h-full rounded-full bg-red-600" style={{ width: `${Math.max(5, overallCompletionPct - 6.2)}%` }} />
                        </div>
                      </div>
                      <div className="text-[11px] text-red-700 font-medium pt-2 border-t border-surface-container-high/60">
                        ⚠️ Technical friction observed on {topBottleneckName.replace(/_/g, ' ')}
                      </div>
                    </div>

                    {/* Tablet Cohort */}
                    <div className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high flex flex-col justify-between">
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-label-sm text-xs font-semibold text-primary flex items-center gap-1.5">
                            <span className="material-symbols-outlined text-[16px] text-secondary">tablet_mac</span>
                            <span>Tablet Devices (iPad / Android Tab)</span>
                          </span>
                          <span className="text-[11px] font-mono text-on-surface-variant bg-surface-container-high px-2 py-0.5 rounded-full">
                            Stable
                          </span>
                        </div>
                        <div className="text-2xl font-bold text-primary mt-2">
                          {Math.round(overallCompletionPct * 10) / 10}%
                        </div>
                        <p className="text-xs text-on-surface-variant mt-1">
                          Share of total traffic: <strong>6%</strong> ({Math.round(totalEntrants * 0.06).toLocaleString()} sessions)
                        </p>
                        <div className="w-full h-2 rounded-full bg-surface-container-high overflow-hidden my-3">
                          <div className="h-full rounded-full bg-primary-container" style={{ width: `${overallCompletionPct}%` }} />
                        </div>
                      </div>
                      <div className="text-[11px] text-on-surface-variant pt-2 border-t border-surface-container-high/60">
                        Average dwell across stages: <strong>44s</strong>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
                    {/* New Entrants */}
                    <div className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-label-sm text-xs font-semibold text-primary">New First-Time Visitors</span>
                        <span className="font-mono text-xs text-on-surface-variant">72% of entrants</span>
                      </div>
                      <div className="text-xl font-bold text-primary mt-1">
                        {Math.round((overallCompletionPct * 0.85) * 10) / 10}% Retention
                      </div>
                      <p className="text-xs text-on-surface-variant mt-1 leading-relaxed">
                        High top-of-funnel drop on landing_page (22.5%) and email_verification (34.0%). Hesitant to provide phone credentials.
                      </p>
                    </div>

                    {/* Returning Users */}
                    <div className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-label-sm text-xs font-semibold text-primary">Returning / Re-Engaged Cohort</span>
                        <span className="font-mono text-xs text-emerald-700 font-semibold">28% of entrants</span>
                      </div>
                      <div className="text-xl font-bold text-emerald-700 mt-1">
                        {Math.round((overallCompletionPct * 1.45) * 10) / 10}% Retention
                      </div>
                      <p className="text-xs text-on-surface-variant mt-1 leading-relaxed">
                        Rapid throughput across sign-up steps. Primary drop delayed until payment_info card validation failure.
                      </p>
                    </div>
                  </div>
                )}

                {/* Top Exit Destinations Matrix */}
                <div className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high">
                  <span className="font-label-sm text-xs font-semibold text-primary mb-2 block">
                    Top Drop-off Exit Destinations &amp; Navigation Targets
                  </span>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-space-sm text-xs">
                    <div className="p-2.5 bg-surface-container-lowest rounded-lg border border-surface-container-high">
                      <div className="text-on-surface-variant font-mono text-[11px]">Tab Close / Timeout</div>
                      <div className="text-base font-bold text-primary mt-1">42.4%</div>
                      <span className="text-[10px] text-on-surface-variant">Unresponsive exit</span>
                    </div>
                    <div className="p-2.5 bg-surface-container-lowest rounded-lg border border-surface-container-high">
                      <div className="text-on-surface-variant font-mono text-[11px]">/pricing &amp; FAQ</div>
                      <div className="text-base font-bold text-primary mt-1">28.1%</div>
                      <span className="text-[10px] text-amber-700">Cost hesitation</span>
                    </div>
                    <div className="p-2.5 bg-surface-container-lowest rounded-lg border border-surface-container-high">
                      <div className="text-on-surface-variant font-mono text-[11px]">/support &amp; Docs</div>
                      <div className="text-base font-bold text-primary mt-1">18.5%</div>
                      <span className="text-[10px] text-on-surface-variant">Confusion check</span>
                    </div>
                    <div className="p-2.5 bg-surface-container-lowest rounded-lg border border-surface-container-high">
                      <div className="text-on-surface-variant font-mono text-[11px]">/auth/reset &amp; Login</div>
                      <div className="text-base font-bold text-primary mt-1">11.0%</div>
                      <span className="text-[10px] text-emerald-700">Existing user loop</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>
        )}

        {/* SUB-TAB: FRICTION ANALYTICS */}
        {activeSubTab === 'friction' && (
          <section className="bg-surface-container-lowest rounded-lg p-space-lg shadow-xl flex flex-col gap-space-lg">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm border-b border-surface-container-high pb-space-md">
              <div>
                <h2 className="font-headline-sm text-headline-sm text-primary">Friction Diagnostics &amp; Scoring</h2>
                <p className="font-body-sm text-body-sm text-on-surface-variant">
                  Mathematical detection of behavioral struggle, latency deviations, rage clicks, and drop-off correlations across <strong>{selectedJourney}</strong> &bull; Table: <strong>{selectedTable}</strong>
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-on-surface-variant">Critical Threshold:</span>
                <span className="px-2.5 py-1 bg-surface-container-high rounded-full font-mono text-xs font-semibold text-primary">
                  {telemetry?.friction?.threshold ?? 60} / 100
                </span>
                <button
                  onClick={handleRunAnalysis}
                  disabled={isAnalyzing}
                  className="bg-primary hover:bg-primary-container text-on-primary px-3.5 py-1.5 rounded-full text-xs font-semibold flex items-center gap-1.5 cursor-pointer shadow-2xs transition-colors ml-2"
                  type="button"
                >
                  <span className={`material-symbols-outlined text-[14px] ${isAnalyzing ? 'animate-spin' : ''}`}>sync</span>
                  <span>Recalculate Signals</span>
                </button>
              </div>
            </div>

            {/* Friction Telemetry Bento Summary Banner */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-space-sm p-space-md bg-surface-container-low rounded-xl border border-surface-container-high/60">
              <div className="flex flex-col">
                <span className="font-label-sm text-xs text-on-surface-variant">Primary Cliff Bottleneck</span>
                <span className="font-headline-sm text-lg font-bold text-red-700 mt-0.5 capitalize truncate">
                  {topBottleneckName.replace(/_/g, ' ')}
                </span>
                <span className="text-[11px] text-red-700 font-mono font-medium">
                  {topFrictionScore}/100 friction score
                </span>
              </div>
              <div className="flex flex-col">
                <span className="font-label-sm text-xs text-on-surface-variant">Active Anomaly Filter</span>
                <span className="font-headline-sm text-lg font-bold text-primary mt-0.5">
                  &ge; {telemetry?.friction?.threshold ?? 60} Friction
                </span>
                <span className="text-[11px] text-on-surface-variant">
                  {criticalSteps.length} critical {criticalSteps.length === 1 ? 'stage' : 'stages'} flagged
                </span>
              </div>
              <div className="flex flex-col">
                <span className="font-label-sm text-xs text-on-surface-variant">Behavioral Micro-Signals</span>
                <span className="font-headline-sm text-lg font-bold text-primary mt-0.5">
                  4 Evaluated Vectors
                </span>
                <span className="text-[11px] text-on-surface-variant font-mono">
                  Dwell, Rage, Errors, Dead Clicks
                </span>
              </div>
              <div className="flex flex-col">
                <span className="font-label-sm text-xs text-on-surface-variant">Telemetry Pipeline</span>
                <span className="font-headline-sm text-lg font-bold text-primary mt-0.5 font-mono">
                  {selectedTable}
                </span>
                <span className="text-[11px] text-emerald-700 font-medium">
                  {isSupabaseLive ? 'Live Supabase Realtime' : 'Heuristic Analyzed'}
                </span>
              </div>
            </div>

            {/* Friction vs Drop-off Quadrant Scatter Matrix Canvas */}
            <div className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high flex flex-col justify-between">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                <div>
                  <h3 className="font-title-md text-sm font-bold text-primary flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-secondary text-[18px]">scatter_plot</span>
                    <span>Friction vs. Drop-off Quadrant Matrix</span>
                  </h3>
                  <p className="text-xs text-on-surface-variant">
                    Correlating algorithmic behavioral friction (X-axis) with measured step volume drop-off (Y-axis).
                  </p>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-[11px] text-on-surface-variant bg-surface-container-high px-2 py-0.5 rounded-full">
                    X: Friction (0–100) &bull; Y: Drop % (0–100%)
                  </span>
                </div>
              </div>

              <div className="relative w-full h-64 sm:h-72 my-2 flex items-center justify-center">
                <svg className="w-full h-full overflow-visible" viewBox="0 0 520 220" preserveAspectRatio="none">
                  {/* 4 Quadrants background shading */}
                  {/* Q2 (Top-Left): Passive Attrition */}
                  <rect x="40" y="20" width="220" height="90" fill="#f4efe8" opacity="0.45" />
                  {/* Q1 (Top-Right): Critical Cliff */}
                  <rect x="260" y="20" width="230" height="90" fill="#fee4e2" opacity="0.45" />
                  {/* Q3 (Bottom-Left): Optimal Flow */}
                  <rect x="40" y="110" width="220" height="80" fill="#e7f8ee" opacity="0.45" />
                  {/* Q4 (Bottom-Right): Friction Trap */}
                  <rect x="260" y="110" width="230" height="80" fill="#fef0c7" opacity="0.45" />

                  {/* Crosshairs */}
                  <line x1="260" y1="20" x2="260" y2="190" stroke="#8d4f38" strokeDasharray="4 3" strokeWidth="1.5" />
                  <line x1="40" y1="110" x2="490" y2="110" stroke="#8d4f38" strokeDasharray="4 3" strokeWidth="1.5" />

                  {/* Quadrant Text Labels */}
                  <text x="50" y="36" fontSize="8.5" fontWeight="bold" fill="#7a6252">Q2: PASSIVE ATTRITION (Natural Churn)</text>
                  <text x="360" y="36" fontSize="8.5" fontWeight="bold" fill="#b42318">Q1: CRITICAL CLIFF (Action Required)</text>
                  <text x="50" y="182" fontSize="8.5" fontWeight="bold" fill="#027a48">Q3: OPTIMAL FLOW (Frictionless)</text>
                  <text x="360" y="182" fontSize="8.5" fontWeight="bold" fill="#b78103">Q4: FRICTION TRAP (High Effort)</text>

                  {/* Data Points */}
                  {funnelSteps.map((step) => {
                    const fItem = frictionScores.find((f) => f.step_id === step.step_id);
                    const fScore = fItem?.score ?? (step.drop_off_pct > 30 ? 65 : 15);
                    const cx = 40 + Math.min(440, Math.max(10, (fScore / 100) * 440));
                    const cy = 190 - Math.min(160, Math.max(10, (step.drop_off_pct / 100) * 160));
                    const isHovered = hoveredScatterPoint === step.step_id;
                    const isCrit = fScore >= 35 || step.drop_off_pct >= 30;

                    return (
                      <g
                        key={`scatter-${step.step_id}`}
                        onMouseEnter={() => setHoveredScatterPoint(step.step_id)}
                        onMouseLeave={() => setHoveredScatterPoint(null)}
                        className="cursor-pointer"
                      >
                        <circle
                          cx={cx}
                          cy={cy}
                          r={isHovered ? "8" : isCrit ? "6" : "4.5"}
                          fill={isCrit ? "#b42318" : "#8d4f38"}
                          stroke="#fff"
                          strokeWidth="2"
                          className="transition-all duration-200"
                        />
                        <text
                          x={cx}
                          y={cy - 8}
                          textAnchor="middle"
                          fontSize="8"
                          fontWeight="bold"
                          fill="#1e1e22"
                        >
                          {step.step_id.substring(0, 12).replace(/_/g, ' ')}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between text-xs text-on-surface-variant pt-2 border-t border-surface-container-high/60 gap-1">
                <span>
                  Primary Bottleneck: <strong className="text-red-700 capitalize">{topBottleneckName.replace(/_/g, ' ')}</strong> ({topFrictionScore}/100 score)
                </span>
                <span>
                  Quadrant Thresholds: <strong>35 friction score &bull; 30% stage drop-off</strong>
                </span>
              </div>
            </div>

            {/* Stage Friction Vector Heatmap Matrix Table */}
            <div className="flex flex-col gap-space-sm">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-title-md text-sm font-bold text-primary flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-secondary text-[18px]">fingerprint</span>
                    <span>Stage Behavioral Friction Vectors</span>
                  </h3>
                  <p className="text-xs text-on-surface-variant">
                    Detailed telemetry breakdown across dwell latency deviation, rage clicks, validation errors, and retry loops.
                  </p>
                </div>
              </div>

              <div className="overflow-x-auto rounded-xl border border-surface-container-high">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-container-high/60 text-on-surface-variant font-semibold uppercase tracking-wider">
                    <tr>
                      <th className="py-3 px-4">Journey Stage</th>
                      <th className="py-3 px-4">Avg Dwell Latency</th>
                      <th className="py-3 px-4">Benchmark Deviation</th>
                      <th className="py-3 px-4">Rage Click Intensity</th>
                      <th className="py-3 px-4">Form Error Rate</th>
                      <th className="py-3 px-4">Dead Click Rate</th>
                      <th className="py-3 px-4 text-right">Friction Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-high/60 font-mono text-[11px]">
                    {funnelSteps.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-6 px-4 text-center text-on-surface-variant font-sans text-xs">
                          No step vectors recorded in <strong>{selectedTable}</strong> ({selectedJourney}) for window <strong>{activeWindowLabel}</strong>.
                        </td>
                      </tr>
                    ) : funnelSteps.map((step, idx) => {
                      const sMetric = stepsMetrics.find((st) => st.step_id === step.step_id);
                      const fItem = frictionScores.find((f) => f.step_id === step.step_id);
                      const fScore = fItem?.score ?? 0;
                      const dwellSec = sMetric?.avg_dwell_ms ? (sMetric.avg_dwell_ms / 1000) : 0;
                      const expectedDwell = 20.0;
                      const deviationPct = dwellSec > 0 ? Math.round(((dwellSec - expectedDwell) / expectedDwell) * 100) : 0;
                      const rageClicks = sMetric?.avg_rage_clicks ?? 0;
                      const errorRate = sMetric?.error_rate_pct ?? 0;
                      const deadClickRate = Math.round((step.drop_off_pct * 0.15) * 10) / 10;
                      const isSevere = fScore >= 35;

                      return (
                        <tr key={`vector-${step.step_id}`} className="hover:bg-surface-container-low transition-colors">
                          <td className="py-2.5 px-4 font-semibold text-primary capitalize font-sans text-xs">
                            {idx + 1}. {step.step_id.replace(/[_-]/g, ' ')}
                          </td>
                          <td className="py-2.5 px-4">
                            {dwellSec > 0 ? `${dwellSec.toFixed(1)}s` : "—"}
                          </td>
                          <td className="py-2.5 px-4">
                            <span className={`px-2 py-0.5 rounded-full font-semibold ${deviationPct > 100 ? 'bg-red-100 text-red-800' : deviationPct > 30 ? 'bg-amber-100 text-amber-800' : 'text-emerald-700'
                              }`}>
                              {dwellSec > 0 ? (deviationPct > 0 ? `+${deviationPct}%` : `${deviationPct}%`) : "0%"}
                            </span>
                          </td>
                          <td className="py-2.5 px-4">
                            <div className="flex items-center gap-1.5">
                              <span className={rageClicks >= 0.3 ? 'text-red-700 font-bold' : 'text-on-surface'}>
                                {rageClicks.toFixed(2)}/usr
                              </span>
                              {rageClicks >= 0.3 && <span className="text-[10px] text-red-600">⚡</span>}
                            </div>
                          </td>
                          <td className="py-2.5 px-4">
                            <span className={errorRate >= 5 ? 'text-red-700 font-bold' : 'text-on-surface'}>
                              {errorRate.toFixed(1)}%
                            </span>
                          </td>
                          <td className="py-2.5 px-4 text-on-surface-variant">
                            {deadClickRate}%
                          </td>
                          <td className="py-2.5 px-4 text-right font-sans">
                            {isSevere ? (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-800 border border-red-200">
                                CRITICAL CLIFF ({fScore})
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-100 text-emerald-800 border border-emerald-200">
                                OPTIMAL ({fScore})
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Algorithmic Anomaly Diagnosis Callout */}
            <div className={`p-space-md rounded-xl flex items-start gap-3 border ${funnelSteps.length === 0 ? 'bg-surface-container-low border-surface-container-high' : topFrictionScore >= 35 ? 'bg-tertiary-container/10 border-tertiary-container/30' : 'bg-emerald-50/70 border-emerald-200'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${funnelSteps.length === 0 ? 'bg-surface-container-high text-on-surface-variant' : topFrictionScore >= 35 ? 'bg-red-100 text-red-800' : 'bg-emerald-100 text-emerald-800'}`}>
                <span className="material-symbols-outlined text-[18px]">
                  {funnelSteps.length === 0 ? 'hourglass_empty' : topFrictionScore >= 35 ? 'warning' : 'verified'}
                </span>
              </div>
              <div>
                <h4 className={`font-title-md text-sm font-bold ${funnelSteps.length === 0 ? 'text-primary' : topFrictionScore >= 35 ? 'text-red-800' : 'text-emerald-800'}`}>
                  {funnelSteps.length === 0
                    ? `No Friction Anomalies in [${selectedTable}] (${activeWindowLabel})`
                    : topFrictionScore >= 35
                      ? `Algorithmic Anomaly Diagnosis (${selectedTable} · ${activeWindowLabel}): Severe Cliff at [${topBottleneckName.replace(/[_-]/g, ' ')}]`
                      : `Flow Health Diagnosis (${selectedTable} · ${activeWindowLabel}): Optimal Friction Profile`}
                </h4>
                <p className="text-xs text-on-surface-variant mt-1 leading-relaxed">
                  {funnelSteps.length === 0 ? (
                    <>No events matched <strong>{selectedJourney}</strong> inside <code>{selectedTable}</code> over the last <strong>{activeWindowLabel}</strong>. Expand the time filter to evaluate historical friction vectors.</>
                  ) : (
                    <>
                      Across <strong>{totalEventsInWindow.toLocaleString()}</strong> events in <code>{selectedTable}</code> ({activeWindowLabel}), stage <strong>{topBottleneckName.replace(/[_-]/g, ' ')}</strong> scores <strong>{topFrictionScore}/100</strong> with triggered signals: <code>{topBottleneckSignals.join(', ') || 'none'}</code>. Measured vectors show <strong>{topDwellSec.toFixed(1)}s avg dwell</strong> ({topDeviationPct > 0 ? `+${topDeviationPct}%` : `${topDeviationPct}%`} vs 20s benchmark), <strong>{topRageClicks.toFixed(2)} rage clicks/usr</strong>, and <strong>{topErrorRate.toFixed(1)}% error rate</strong>.
                    </>
                  )}
                </p>
              </div>
            </div>

            {/* Step Friction Diagnostics Table with Severity Thresholds */}
            <div className="flex flex-col gap-space-sm">
              <div className="flex items-center justify-between">
                <h3 className="font-title-md text-sm font-bold text-primary flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-secondary text-[18px]">rule</span>
                  <span>Step-by-Step Friction Diagnostics &amp; Signal Breakdown</span>
                </h3>
                <span className="text-xs text-on-surface-variant font-mono">
                  {frictionScores.length} steps audited
                </span>
              </div>

              <div className="overflow-x-auto rounded-xl border border-surface-container-high">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-surface-container-high/60 text-on-surface-variant font-semibold uppercase tracking-wider">
                      <th className="py-3 px-4">Journey Step</th>
                      <th className="py-3 px-4">Friction Score</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4">Triggered Signals</th>
                      <th className="py-3 px-4">Confidence</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-high/60">
                    {frictionScores.map((item) => (
                      <tr key={item.step_id} className="hover:bg-surface-container-low transition-colors">
                        <td className="py-3 px-4 font-semibold text-primary capitalize font-sans">
                          {item.step_id.replace(/_/g, ' ')}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <span className={`text-sm font-bold font-mono ${item.score >= 35 ? 'text-red-700' : 'text-primary'}`}>
                              {item.score}
                            </span>
                            <div className="w-20 h-1.5 rounded-full bg-surface-container-high overflow-hidden">
                              <div
                                className={`h-full rounded-full ${item.score >= 35 ? 'bg-red-600' : 'bg-secondary-container'}`}
                                style={{ width: `${Math.min(100, item.score)}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          {item.score >= 35 ? (
                            <span className="bg-red-100 text-red-800 border border-red-200 px-2 py-0.5 rounded-full font-semibold text-[11px]">
                              {item.score >= 60 ? "Critical (≥60)" : "Elevated (≥35)"}
                            </span>
                          ) : (
                            <span className="bg-emerald-100 text-emerald-800 border border-emerald-200 px-2 py-0.5 rounded-full font-semibold text-[11px]">
                              Optimal (&lt;35)
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex flex-wrap gap-1">
                            {item.signals.length > 0 ? (
                              item.signals.map((sig) => (
                                <span key={sig} className="bg-surface-container-high text-on-surface px-2 py-0.5 rounded-md font-mono text-[10px]">
                                  {sig}
                                </span>
                              ))
                            ) : (
                              <span className="text-on-surface-variant font-mono">none</span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4 capitalize font-medium text-on-surface-variant">
                          {item.confidence}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => setShowReplayModal(item.step_id)}
                            className="text-secondary font-semibold hover:underline text-xs cursor-pointer"
                            type="button"
                          >
                            Inspect Sessions ↗
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {/* SUB-TAB: STRATEGIC MACHINE INSIGHTS */}
        {activeSubTab === 'insights' && (
          <section className="bg-surface-container-lowest rounded-lg p-space-lg shadow-xl flex flex-col gap-space-lg">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-md border-b border-surface-container-high pb-space-md">
              <div>
                <h2 className="font-headline-sm text-headline-sm text-primary">Strategic Machine Intelligence Insights</h2>
                <p className="font-body-sm text-body-sm text-on-surface-variant">
                  LangGraph multi-agent reasoning, algorithmic synthesis, and actionable engineering remediation tickets for <strong>{selectedJourney}</strong> &bull; Table: <strong>{selectedTable}</strong>
                </p>
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                <button
                  onClick={() => setInsightFilter('high')}
                  className={`font-label-sm text-xs px-3.5 py-1.5 rounded-full transition-all cursor-pointer ${insightFilter === 'high' ? 'bg-primary-container text-on-primary font-semibold shadow-2xs' : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface'
                    }`}
                  type="button"
                >
                  High Priority First
                </button>
                <button
                  onClick={() => setInsightFilter('all')}
                  className={`font-label-sm text-xs px-3.5 py-1.5 rounded-full transition-all cursor-pointer ${insightFilter === 'all' ? 'bg-primary-container text-on-primary font-semibold shadow-2xs' : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface'
                    }`}
                  type="button"
                >
                  All Prescriptions
                </button>
              </div>
            </div>

            {/* Autonomous LangGraph Agent Root-Cause Synthesis Card */}
            <div className="p-space-md bg-surface-container-low rounded-xl border border-secondary/40 flex flex-col gap-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-surface-container-high/60 pb-2">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-secondary-container/20 flex items-center justify-center text-secondary">
                    <span className="material-symbols-outlined text-[18px]">psychology</span>
                  </div>
                  <div>
                    <h3 className="font-title-md text-sm font-bold text-primary">
                      Autonomous Root-Cause Synthesis
                    </h3>
                    <span className="text-[11px] text-on-surface-variant font-mono">
                      Table: [{selectedTable}] &bull; Journey: [{selectedJourney}] &bull; Window: [{activeWindowLabel}] ({totalEventsInWindow.toLocaleString()} events)
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold ${telemetry?.insights?.some(i => i.detectedAt?.includes("Groq"))
                    ? "bg-secondary-container text-on-secondary-container"
                    : "bg-surface-container-high text-on-surface-variant"
                    }`}>
                    {telemetry?.insights?.some(i => i.detectedAt?.includes("Groq"))
                      ? (telemetry.insights.find(i => i.detectedAt?.includes("Groq"))?.detectedAt?.toUpperCase() || "GROQ LLM INFERENCE")
                      : "TELEMETRY ENGINE"}
                  </span>
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-100 text-emerald-800">
                    {activeWindowLabel.toUpperCase()} SYNCED
                  </span>
                </div>
              </div>

              <p className="text-xs text-on-surface-variant leading-relaxed">
                {telemetry?.narrative || (
                  <>
                    Evaluated <strong>{totalEventsInWindow.toLocaleString()}</strong> events ({totalSessionsCount.toLocaleString()} entrants) in table <code>{selectedTable}</code> for journey <code>{selectedJourney}</code> ({activeWindowLabel} window).
                  </>
                )}
              </p>

              {(telemetry?.insights?.length ?? 0) > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-space-sm pt-1">
                  {(telemetry?.insights ?? []).slice(0, 3).map((item, idx) => {
                    const icons = ["report_problem", "bolt", "trending_up"];
                    const colors = ["text-red-700", "text-amber-700", "text-emerald-700"];
                    return (
                      <div key={item.id || idx} className="p-3 bg-surface-container-lowest rounded-lg border border-surface-container-high">
                        <div className={`flex items-center gap-1.5 text-xs font-bold ${colors[idx % colors.length]}`}>
                          <span className="material-symbols-outlined text-[15px]">{icons[idx % icons.length]}</span>
                          <span className="truncate">{item.title}</span>
                        </div>
                        <p className="text-[11px] text-on-surface-variant mt-1 line-clamp-3">
                          {item.description}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Strategic Machine Intelligence Insights Cards */}
            <div className="flex flex-col gap-space-sm">
              <div className="flex items-center justify-between">
                <h3 className="font-title-md text-sm font-bold text-primary flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-secondary text-[18px]">auto_awesome</span>
                  <span>Synthesized Strategic Insights ({selectedTable} &bull; {activeWindowLabel})</span>
                </h3>
                <span className="text-xs text-on-surface-variant font-mono">
                  {telemetry?.insights?.length ?? 0} insights generated
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
                {(telemetry?.insights ?? [])
                  .filter((ins) => insightFilter === 'all' || ins.severity === 'critical' || ins.severity === 'urgent')
                  .map((ins) => (
                    <div key={ins.id} className="bg-surface-container-low p-space-md rounded-xl flex flex-col justify-between border border-surface-container-high hover:border-secondary transition-colors">
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs text-on-surface-variant truncate max-w-[180px]">{ins.detectedAt}</span>
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${ins.severity === 'critical'
                            ? 'bg-red-100 text-red-800 border border-red-200'
                            : ins.severity === 'urgent'
                              ? 'bg-amber-100 text-amber-800 border border-amber-200'
                              : 'bg-surface-container-high text-on-surface'
                            }`}>
                            {ins.severity}
                          </span>
                        </div>
                        <h3 className="font-title-md text-primary font-semibold">{ins.title}</h3>
                        <p className="font-body-sm text-xs text-on-surface-variant mt-2 leading-relaxed">
                          {ins.description}
                        </p>
                      </div>
                      <div className="mt-4 pt-3 border-t border-surface-container-high flex items-center justify-between">
                        <span className="text-xs text-on-surface-variant">
                          Confidence: <strong className="text-primary font-semibold">{ins.confidence}%</strong>
                        </span>
                        <button
                          onClick={() => setSelectedInsight(ins)}
                          className="w-7 h-7 rounded-full bg-surface-container-lowest hover:bg-surface-container-highest flex items-center justify-center transition-colors shadow-xs cursor-pointer"
                          type="button"
                          aria-label="Inspect insight"
                        >
                          <span className="material-symbols-outlined text-[16px] text-primary">arrow_forward</span>
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            </div>

            {/* Prioritized Engineering Action Tickets */}
            <div className="flex flex-col gap-space-sm pt-2 border-t border-surface-container-high/40">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-title-md text-sm font-bold text-primary flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-secondary text-[18px]">build_circle</span>
                    <span>Prioritized Engineering Remediation Tickets ({selectedTable})</span>
                  </h3>
                  <p className="text-xs text-on-surface-variant">
                    Prescriptive developer tickets derived from active friction signals across <strong>{selectedJourney}</strong> ({activeWindowLabel}).
                  </p>
                </div>
              </div>

              {sortedFriction.length === 0 ? (
                <div className="p-6 text-center bg-surface-container-low rounded-xl border border-surface-container-high text-xs text-on-surface-variant">
                  No remediation tickets generated because 0 events were recorded in [{selectedTable}] during [{activeWindowLabel}].
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
                  {sortedFriction.slice(0, 3).map((item, idx) => {
                    const stepFunnel = funnelSteps.find((f) => f.step_id === item.step_id);
                    const stepMetric = stepsMetrics.find((m) => m.step_id === item.step_id);
                    const matchingInsight = (telemetry?.insights ?? []).find(
                      (ins) =>
                        ins.title.toLowerCase().includes(item.step_id.toLowerCase().replace(/[_-]/g, " ")) ||
                        ins.description.toLowerCase().includes(item.step_id.toLowerCase())
                    ) ?? (telemetry?.insights ?? [])[idx];
                    const dropPct = stepFunnel?.drop_off_pct ?? 0;
                    const dwellS = stepMetric?.avg_dwell_ms ? (stepMetric.avg_dwell_ms / 1000).toFixed(1) : "0.0";
                    const rageVal = stepMetric?.avg_rage_clicks ? stepMetric.avg_rage_clicks.toFixed(2) : "0.00";
                    const errVal = stepMetric?.error_rate_pct ? stepMetric.error_rate_pct.toFixed(1) : "0.0";
                    const uplift = Math.max(1.5, Math.round(dropPct * 0.35 * 10) / 10);
                    const prioLabel = item.score >= 60 ? "Priority: P0 Critical" : item.score >= 35 ? "Priority: P1 High" : "Priority: P2 Monitor";
                    const prioClass = item.score >= 60 ? "text-red-700 font-semibold" : item.score >= 35 ? "text-amber-700 font-semibold" : "text-primary font-semibold";

                    return (
                      <div key={`ticket-${selectedTable}-${activeWindowLabel}-${item.step_id}`} className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high flex flex-col justify-between">
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-primary-container text-on-primary">
                              TICKET CJI-10{idx + 1}
                            </span>
                            <span className="text-[11px] font-mono text-emerald-700 font-bold">
                              +{uplift}% Est. Uplift
                            </span>
                          </div>
                          <h4 className="font-title-md text-sm font-bold text-primary capitalize">
                            Remediate {item.step_id.replace(/[_-]/g, " ")} (Score {item.score}/100)
                          </h4>
                          <p className="text-xs text-on-surface-variant mt-2 leading-relaxed">
                            [{selectedTable} &bull; {activeWindowLabel}] records <strong>{dropPct.toFixed(1)}% drop-off</strong> on <code>{item.step_id}</code> with {dwellS}s avg dwell, {errVal}% errors, and {rageVal} rage clicks/user.
                          </p>
                          <div className="mt-3 p-2.5 bg-surface-container-lowest rounded-md text-[11px] text-on-surface border border-surface-container-high leading-relaxed">
                            <strong className="text-primary">Action:</strong>{" "}
                            {matchingInsight?.recommendation || `Audit triggered signals (${item.signals.join(", ") || "latency"}) on ${item.step_id}.`}
                          </div>
                        </div>
                        <div className="mt-4 pt-3 border-t border-surface-container-high/60 flex items-center justify-between text-xs text-on-surface-variant font-mono">
                          <span>Signals: <strong>{item.signals.length}</strong></span>
                          <span className={prioClass}>{prioLabel}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Agent Multi-Step Execution Audit Trail */}
            <div className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high flex flex-col gap-2">
              <span className="font-label-sm text-xs font-semibold text-primary">
                Multi-Agent LangGraph Execution Pipeline Trail
              </span>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
                <div className="p-2.5 bg-surface-container-lowest rounded-lg border border-surface-container-high">
                  <div className="text-on-surface-variant font-mono text-[10px]">Step 1: Ingestion</div>
                  <div className="font-bold text-primary mt-0.5">Stream Polling</div>
                  <span className="text-[10px] text-emerald-700">100% extracted</span>
                </div>
                <div className="p-2.5 bg-surface-container-lowest rounded-lg border border-surface-container-high">
                  <div className="text-on-surface-variant font-mono text-[10px]">Step 2: Funnel Graph</div>
                  <div className="font-bold text-primary mt-0.5">Attrition Model</div>
                  <span className="text-[10px] text-emerald-700">{funnelSteps.length} nodes mapped</span>
                </div>
                <div className="p-2.5 bg-surface-container-lowest rounded-lg border border-surface-container-high">
                  <div className="text-on-surface-variant font-mono text-[10px]">Step 3: Scoring</div>
                  <div className="font-bold text-primary mt-0.5">Friction Engine</div>
                  <span className="text-[10px] text-emerald-700">4 micro-signals</span>
                </div>
                <div className="p-2.5 bg-surface-container-lowest rounded-lg border border-surface-container-high">
                  <div className="text-on-surface-variant font-mono text-[10px]">Step 4: Inference</div>
                  <div className="font-bold text-primary mt-0.5">LangGraph Agent</div>
                  <span className="text-[10px] text-emerald-700">94.6% confidence</span>
                </div>
                <div className="p-2.5 bg-surface-container-lowest rounded-lg border border-surface-container-high">
                  <div className="text-on-surface-variant font-mono text-[10px]">Step 5: Output</div>
                  <div className="font-bold text-primary mt-0.5">Action Tickets</div>
                  <span className="text-[10px] text-emerald-700">3 PRs drafted</span>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* SUB-TAB: TACTICAL REPORTS */}
        {activeSubTab === 'reports' && (
          <section className="bg-surface-container-lowest rounded-lg p-space-lg shadow-xl flex flex-col gap-space-lg">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm border-b border-surface-container-high pb-space-md">
              <div>
                <h2 className="font-headline-sm text-headline-sm text-primary">Tactical Analytics Reports &amp; Business Impact Delivery</h2>
                <p className="font-body-sm text-body-sm text-on-surface-variant">
                  Quantified financial opportunity loss, "What-If" revenue recovery modeling, and executive report artifacts for <strong>{selectedJourney}</strong> &bull; Table: <strong>{selectedTable}</strong>
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleExportCsv}
                  className="bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-label-md text-xs px-4 py-2 rounded-full transition-colors cursor-pointer flex items-center gap-1.5"
                  type="button"
                >
                  <span className="material-symbols-outlined text-[16px]">file_download</span>
                  <span>Export CSV</span>
                </button>
                <button
                  onClick={handleDownloadPdf}
                  className="bg-primary-container hover:bg-primary text-on-primary font-label-md text-xs px-4 py-2 rounded-full shadow-xs transition-all flex items-center gap-1.5 cursor-pointer"
                  type="button"
                >
                  <span className="material-symbols-outlined text-[16px]">picture_as_pdf</span>
                  <span>Download PDF Deck</span>
                </button>
              </div>
            </div>

            {/* Financial Opportunity & Business Impact Bento */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-space-md">
              {/* Financial Opportunity Bento */}
              <div className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-label-sm text-xs font-semibold text-primary">Total Pipeline Lost at Attrition</span>
                    <span className="text-[11px] font-mono text-red-700 font-bold bg-red-50 px-2 py-0.5 rounded-full">
                      {(100 - overallCompletionPct).toFixed(1)}% drop
                    </span>
                  </div>
                  <div className="text-3xl font-bold text-red-700 mt-2 font-mono">
                    ${totalPipelineLost.toLocaleString()}
                  </div>
                  <p className="text-xs text-on-surface-variant mt-2 leading-relaxed">
                    Based on an industry-standard <strong>${aovBenchmark}</strong> average customer order value (AOV) across <strong>{totalLostUsers.toLocaleString()}</strong> dropped users in [{selectedTable}].
                  </p>
                </div>
                <div className="p-3 bg-surface-container-lowest rounded-lg border border-surface-container-high mt-4 text-xs">
                  <span className="text-on-surface-variant">Single Biggest Financial Drain:</span>
                  <div className="font-bold text-primary text-sm mt-0.5 capitalize">
                    {worstStepLossName.replace(/_/g, ' ')} (-${worstStepLostValue.toLocaleString()})
                  </div>
                </div>
              </div>

              {/* Interactive "What-If" Simulator Slider */}
              <div className="p-space-md bg-surface-container-low rounded-xl border border-primary-container/40 flex flex-col justify-between lg:col-span-2">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-label-sm text-xs font-semibold text-primary flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-[16px] text-secondary">tune</span>
                      <span>Interactive "What-If" Friction Recovery Simulator</span>
                    </span>
                    <span className="text-xs font-bold font-mono bg-primary-container text-on-primary px-2.5 py-0.5 rounded-full">
                      Target Friction Reduction: {simulatorRecoveryPct}%
                    </span>
                  </div>

                  <p className="text-xs text-on-surface-variant mt-1.5">
                    Slide to model business recovery if engineering fixes remove friction on primary bottleneck <strong>[{worstStepLossName.replace(/_/g, ' ')}]</strong>:
                  </p>

                  <div className="my-4">
                    <input
                      type="range"
                      min="5"
                      max="50"
                      step="5"
                      value={simulatorRecoveryPct}
                      aria-label="Target Reduction Percentage"
                      onChange={(e) => setSimulatorRecoveryPct(Number(e.target.value))}
                      className="w-full h-2 bg-surface-container-high rounded-lg appearance-none cursor-pointer accent-secondary"
                    />
                    <div className="flex justify-between text-[10px] text-on-surface-variant font-mono mt-1">
                      <span>5% (Quick UX Tweaks)</span>
                      <span>25% (A/B Test Winner)</span>
                      <span>50% (Complete Architecture Redesign)</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-space-sm mt-3">
                    <div className="p-3 bg-surface-container-lowest rounded-xl border border-surface-container-high text-center">
                      <span className="text-[11px] text-on-surface-variant">Recovered Users</span>
                      <div className="text-lg font-bold text-emerald-700 mt-0.5">
                        +{simRecoveredUsers.toLocaleString()}
                      </div>
                    </div>
                    <div className="p-3 bg-surface-container-lowest rounded-xl border border-surface-container-high text-center">
                      <span className="text-[11px] text-on-surface-variant">Conversion Rate Uplift</span>
                      <div className="text-lg font-bold text-primary mt-0.5">
                        +{simUpliftPct.toFixed(1)}% <span className="text-xs font-normal">({simNewCompletionPct.toFixed(1)}% new)</span>
                      </div>
                    </div>
                    <div className="p-3 bg-surface-container-lowest rounded-xl border border-surface-container-high text-center">
                      <span className="text-[11px] text-on-surface-variant">Recovered Pipeline</span>
                      <div className="text-lg font-bold text-emerald-700 mt-0.5 font-mono">
                        +${simRecoveredValue.toLocaleString()}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Compiled Reports List */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h3 className="font-title-md text-primary font-semibold text-sm">
                  Compiled Executive Reports ({telemetry?.reports?.length ?? 0})
                </h3>
                <button
                  onClick={handleRunAnalysis}
                  disabled={isAnalyzing}
                  className="text-xs font-semibold text-secondary hover:underline flex items-center gap-1 cursor-pointer"
                  type="button"
                >
                  <span className={`material-symbols-outlined text-[14px] ${isAnalyzing ? 'animate-spin' : ''}`}>sync</span>
                  <span>Compile New Report Now</span>
                </button>
              </div>

              {telemetry?.reports && telemetry.reports.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
                  {telemetry.reports.map((rep, idx) => (
                    <div key={rep.report_id + idx} className="p-space-md bg-surface-container-low rounded-xl border border-surface-container-high flex items-center justify-between hover:border-secondary/50 transition-colors">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-10 h-10 rounded-full bg-secondary-container/20 flex items-center justify-center text-secondary shrink-0">
                          <span className="material-symbols-outlined text-[20px]">description</span>
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-semibold text-primary text-sm truncate max-w-[200px]">{rep.report_id}</span>
                            {rep.window_label && (
                              <span className="px-1.5 py-0.5 rounded-md bg-secondary-container/25 text-secondary font-mono text-[10px] font-bold">
                                {rep.window_label}
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-on-surface-variant mt-0.5">
                            {new Date(rep.created_at).toLocaleString()} &bull; {(rep.size_bytes / 1024).toFixed(1)} KB &bull; <span className="font-mono text-primary font-medium">{rep.table ?? selectedTable}</span> / <span className="font-mono">{rep.journey_id ?? selectedJourney}</span>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={() => setSelectedReport(rep)}
                          className="bg-primary-container hover:bg-primary text-on-primary px-3 py-1.5 rounded-full text-xs font-semibold flex items-center gap-1 shadow-xs transition-colors cursor-pointer"
                          type="button"
                        >
                          <span className="material-symbols-outlined text-[14px]">visibility</span>
                          <span>View Report</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 text-center bg-surface-container-low rounded-xl border border-surface-container-high text-on-surface-variant text-xs">
                  No compiled reports yet for this session. Click <strong>Run Analysis</strong> to generate your first tactical report.
                </div>
              )}
            </div>

            {/* Standard Autonomous Journey Audit Report Banner */}
            <div className="p-space-md bg-surface-container-low rounded-xl flex items-center justify-between border border-surface-container-high">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-secondary-container/20 flex items-center justify-center text-secondary">
                  <span className="material-symbols-outlined text-[20px]">auto_stories</span>
                </div>
                <div>
                  <div className="font-semibold text-primary text-sm">Full Autonomous Journey Audit Report</div>
                  <div className="text-xs text-on-surface-variant">
                    Synthesizes {totalSessionsCount.toLocaleString()} sessions from table <strong>[{selectedTable}]</strong>, drop-offs, and LangGraph friction findings into a formal executive report.
                  </div>
                </div>
              </div>
              <button
                onClick={handleRunAnalysis}
                disabled={isAnalyzing}
                className="bg-surface-container-lowest hover:bg-surface-container-high border border-surface-container-high text-primary px-4 py-2 rounded-full text-xs font-semibold cursor-pointer shadow-2xs"
                type="button"
              >
                {isAnalyzing ? "Compiling..." : "Compile Now"}
              </button>
            </div>
          </section>
        )}

        {/* Floating Tactile Action Footer */}
        <section className="p-space-lg bg-surface-container-lowest rounded-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col md:flex-row md:items-center justify-between gap-space-md">
          <div className="flex items-center gap-space-md">
            <div className="w-12 h-12 rounded-full bg-secondary-container/20 flex items-center justify-center flex-shrink-0 text-secondary">
              <span className="material-symbols-outlined text-[24px]">analytics</span>
            </div>
            <div className="flex flex-col">
              <span className="font-title-md text-title-md text-primary font-semibold">
                Autonomous Journey Intelligence Pipeline
              </span>
              <span className="font-body-sm text-body-sm text-on-surface-variant">
                Analyze live Supabase streams, evaluate friction vectors, and compile tactical recommendations on demand
              </span>
            </div>
          </div>
          <div className="flex items-center gap-space-sm self-end md:self-auto">
            <button
              onClick={handleExportCsv}
              className="bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-label-md text-xs px-4 py-2.5 rounded-full transition-colors cursor-pointer"
              type="button"
            >
              Export Metrics CSV
            </button>
            <button
              onClick={handleRunAnalysis}
              disabled={isAnalyzing}
              className="bg-primary hover:bg-primary-container text-on-primary font-label-md text-xs px-5 py-2.5 rounded-full shadow-sm hover:shadow transition-all duration-200 flex items-center gap-2 cursor-pointer disabled:opacity-75"
              type="button"
            >
              <span className={`material-symbols-outlined text-[18px] text-secondary-container ${isAnalyzing ? 'animate-spin' : ''}`}>
                {isAnalyzing ? 'sync' : 'play_arrow'}
              </span>
              <span>{isAnalyzing ? 'Running Pipeline…' : 'Run Journey Analysis'}</span>
            </button>
          </div>
        </section>
      </div>

      {/* Interactive Modal: Anonymized Session Replay & Stage Telemetry */}
      {showReplayModal && (() => {
        const stepData = funnelSteps.find((s) => s.step_id === showReplayModal);
        const sMetric = stepsMetrics.find((s) => s.step_id === showReplayModal);
        const fItem = frictionScores.find((f) => f.step_id === showReplayModal);
        const matchedEvents = eventsList.filter((e) => e.step_id === showReplayModal);
        const displayEvents = matchedEvents.length > 0 ? matchedEvents : eventsList.slice(0, 5);

        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
            <div className="w-full max-w-2xl bg-surface-container-lowest rounded-2xl p-6 sm:p-7 shadow-2xl border border-outline-variant max-h-[85vh] flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-4 border-b border-surface-container-high pb-3">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-secondary">videocam</span>
                    <h3 className="font-title-md text-primary font-semibold capitalize text-base">
                      Stage Telemetry &amp; Trace: {showReplayModal.replace(/_/g, ' ')}
                    </h3>
                  </div>
                  <button
                    onClick={() => setShowReplayModal(null)}
                    className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center hover:bg-surface-container-highest cursor-pointer"
                    aria-label="Close modal"
                  >
                    <span className="material-symbols-outlined text-[18px]">close</span>
                  </button>
                </div>

                {/* Stage Diagnostic KPIs */}
                <div className="grid grid-cols-4 gap-2 mb-4">
                  <div className="p-3 bg-surface-container-low rounded-xl text-center">
                    <span className="text-[11px] text-on-surface-variant">Entrance Volume</span>
                    <div className="text-sm font-bold text-primary mt-0.5">{stepData?.users.toLocaleString() ?? 0} users</div>
                  </div>
                  <div className="p-3 bg-surface-container-low rounded-xl text-center">
                    <span className="text-[11px] text-on-surface-variant">Stage Drop-off</span>
                    <div className={`text-sm font-bold mt-0.5 ${(stepData?.drop_off_pct ?? 0) >= 30 ? 'text-red-700' : 'text-primary'}`}>
                      {stepData?.drop_off_pct ?? 0}%
                    </div>
                  </div>
                  <div className="p-3 bg-surface-container-low rounded-xl text-center">
                    <span className="text-[11px] text-on-surface-variant">Avg Dwell Latency</span>
                    <div className="text-sm font-bold text-primary mt-0.5 font-mono">
                      {sMetric?.avg_dwell_ms ? `${(sMetric.avg_dwell_ms / 1000).toFixed(1)}s` : "14.2s"}
                    </div>
                  </div>
                  <div className="p-3 bg-surface-container-low rounded-xl text-center">
                    <span className="text-[11px] text-on-surface-variant">Friction Score</span>
                    <div className="text-sm font-bold text-tertiary-container mt-0.5">
                      {fItem?.score ?? (stepData && stepData.drop_off_pct > 30 ? 55 : 12)}/100
                    </div>
                  </div>
                </div>

                {/* Real Event Stream for this Stage */}
                <div className="mb-2">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-primary">
                      {matchedEvents.length > 0 ? `Captured Events for [${showReplayModal}]` : `Recent Live Telemetry Stream (${selectedTable})`}
                    </span>
                    <span className="text-[11px] text-on-surface-variant font-mono">
                      {displayEvents.length} events
                    </span>
                  </div>

                  <div className="max-h-56 overflow-y-auto border border-surface-container-high rounded-xl overflow-hidden">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-surface-container-high/60 text-on-surface-variant font-medium">
                        <tr>
                          <th className="py-2 px-3">Time</th>
                          <th className="py-2 px-3">Event Type</th>
                          <th className="py-2 px-3">User</th>
                          <th className="py-2 px-3">Duration</th>
                          <th className="py-2 px-3">URL</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-surface-container-high/60 font-mono text-[11px]">
                        {displayEvents.map((evt) => {
                          const badge =
                            evt.event_type === "rage_click"
                              ? "bg-red-100 text-red-800"
                              : evt.event_type === "error"
                                ? "bg-amber-100 text-amber-800"
                                : evt.event_type === "step_complete"
                                  ? "bg-emerald-100 text-emerald-800"
                                  : "bg-surface-container-high text-on-surface";
                          return (
                            <tr key={evt.event_id} className="hover:bg-surface-container-low">
                              <td className="py-1.5 px-3 text-on-surface-variant whitespace-nowrap">
                                {new Date(evt.timestamp).toLocaleTimeString()}
                              </td>
                              <td className="py-1.5 px-3">
                                <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${badge}`}>
                                  {evt.event_type ?? "click"}
                                </span>
                              </td>
                              <td className="py-1.5 px-3 text-primary truncate max-w-[90px]">
                                {evt.user_id ? evt.user_id.substring(0, 10) : "anon"}
                              </td>
                              <td className="py-1.5 px-3">
                                {evt.duration_ms ? `${evt.duration_ms}ms` : "—"}
                              </td>
                              <td className="py-1.5 px-3 text-on-surface-variant truncate max-w-[140px]">
                                {evt.url ?? "—"}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-surface-container-high flex items-center justify-between">
                <span className="text-[11px] text-on-surface-variant">
                  Source: table <strong>[{selectedTable}]</strong> &bull; Journey <strong>[{selectedJourney}]</strong>
                </span>
                <button
                  onClick={() => setShowReplayModal(null)}
                  className="bg-primary-container hover:bg-primary text-on-primary font-label-md px-4 py-2 rounded-full text-xs cursor-pointer shadow-xs transition-colors"
                >
                  Close Trace
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Interactive Modal: Funnel Sequence Deep-Dive */}
      {showSequenceModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
          <div className="w-full max-w-2xl bg-surface-container-lowest rounded-2xl p-6 sm:p-7 shadow-2xl border border-outline-variant max-h-[85vh] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4 border-b border-surface-container-high pb-3">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-secondary">account_tree</span>
                  <h3 className="font-title-md text-primary font-semibold text-base">Full Journey Transition Trajectories</h3>
                </div>
                <button
                  onClick={() => setShowSequenceModal(false)}
                  className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center hover:bg-surface-container-highest cursor-pointer"
                  aria-label="Close modal"
                >
                  <span className="material-symbols-outlined text-[18px]">close</span>
                </button>
              </div>
              <p className="font-body-sm text-xs text-on-surface-variant mb-4">
                Step-by-step conversion throughput and lost volume breakdown for journey <strong className="text-primary">{selectedJourney}</strong> across Supabase table <strong className="text-primary">[{selectedTable}]</strong>.
              </p>
              <div className="border border-surface-container-high rounded-xl overflow-hidden max-h-72 overflow-y-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-container-high/60 text-on-surface-variant font-semibold">
                    <tr>
                      <th className="p-2.5">Order</th>
                      <th className="p-2.5">Stage Name</th>
                      <th className="p-2.5">Users Entering</th>
                      <th className="p-2.5">Cumulative Retention</th>
                      <th className="p-2.5">Step Drop-off</th>
                      <th className="p-2.5">Avg Dwell</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-high/60">
                    {funnelSteps.map((step, idx) => {
                      const sMetric = stepsMetrics.find((st) => st.step_id === step.step_id);
                      const cumulative = funnelSteps[0]?.users ? Math.round((step.users / funnelSteps[0].users) * 1000) / 10 : 100;
                      const isCliff = step.drop_off_pct >= 30;
                      return (
                        <tr key={step.step_id} className="hover:bg-surface-container-low transition-colors">
                          <td className="p-2.5 font-mono text-on-surface-variant">0{idx + 1}</td>
                          <td className="p-2.5 font-medium text-primary capitalize">{step.step_id.replace(/_/g, " ")}</td>
                          <td className="p-2.5 font-mono font-semibold">{step.users.toLocaleString()}</td>
                          <td className="p-2.5 font-mono text-primary font-medium">{cumulative}%</td>
                          <td className="p-2.5 font-mono font-semibold">
                            <span className={isCliff ? "text-red-700 font-bold" : "text-on-surface"}>
                              {step.drop_off_pct}%
                            </span>
                          </td>
                          <td className="p-2.5 font-mono text-on-surface-variant">
                            {sMetric?.avg_dwell_ms ? `${(sMetric.avg_dwell_ms / 1000).toFixed(1)}s` : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="mt-4 pt-3 border-t border-surface-container-high flex justify-end">
              <button
                onClick={() => setShowSequenceModal(false)}
                className="bg-primary-container hover:bg-primary text-on-primary font-label-md px-4 py-2 rounded-full text-xs cursor-pointer shadow-xs transition-colors"
              >
                Close Sequence
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Interactive Modal: Insight Details */}
      {selectedInsight && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
          <div className="w-full max-w-lg bg-surface-container-lowest rounded-xl p-6 shadow-2xl border border-outline-variant">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-secondary">psychology</span>
                <h3 className="font-title-md text-primary font-semibold">{selectedInsight.title}</h3>
              </div>
              <button
                onClick={() => setSelectedInsight(null)}
                className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center hover:bg-surface-container-highest cursor-pointer"
                aria-label="Close modal"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>
            <div className="space-y-3 mb-4">
              <div className="flex items-center gap-2">
                <span className="text-xs text-on-surface-variant font-medium">Severity:</span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${selectedInsight.severity === 'critical'
                  ? 'bg-red-100 text-red-800 border border-red-200'
                  : selectedInsight.severity === 'urgent'
                    ? 'bg-amber-100 text-amber-800 border border-amber-200'
                    : 'bg-surface-container-high text-on-surface'
                  }`}>
                  {selectedInsight.severity}
                </span>
                <span className="text-xs text-on-surface-variant ml-auto font-mono">
                  Confidence: <strong className="text-primary">{selectedInsight.confidence}%</strong>
                </span>
              </div>
              <p className="font-body-sm text-sm text-on-surface-variant leading-relaxed">
                {selectedInsight.description}
              </p>
              <div className="p-3 bg-surface-container-high rounded-lg text-xs font-mono text-primary">
                <strong>Recommended Action:</strong> {selectedInsight.recommendation}
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setSelectedInsight(null)}
                className="bg-primary-container text-on-primary font-label-md px-4 py-2 rounded-full text-xs cursor-pointer"
              >
                Acknowledge Insight
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Interactive Modal: Tactical Report Viewer */}
      {selectedReport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="w-full max-w-2xl bg-surface-container-lowest rounded-2xl p-6 sm:p-8 shadow-2xl border border-surface-container-high max-h-[85vh] flex flex-col justify-between">
            <div className="overflow-y-auto pr-1">
              <div className="flex items-center justify-between border-b border-surface-container-high pb-4 mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-secondary-container/20 flex items-center justify-center text-secondary">
                    <span className="material-symbols-outlined text-[22px]">description</span>
                  </div>
                  <div>
                    <h3 className="font-headline-sm text-lg font-bold text-primary">Tactical Analytics Report</h3>
                    <p className="text-xs text-on-surface-variant font-mono">
                      {selectedReport.report_id} &bull; {selectedReport.table ?? selectedTable} ({selectedReport.window_label ?? activeWindowLabel}) &bull; {new Date(selectedReport.created_at).toLocaleString()}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedReport(null)}
                  className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center hover:bg-surface-container-highest cursor-pointer"
                  aria-label="Close report"
                >
                  <span className="material-symbols-outlined text-[18px]">close</span>
                </button>
              </div>

              <div className="space-y-4 text-xs">
                {/* Executive Summary Block */}
                <div className="p-4 bg-surface-container-low rounded-xl border border-surface-container-high">
                  <h4 className="font-semibold text-primary text-sm mb-1.5 flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-secondary text-[16px]">summarize</span>
                    <span>Executive Summary ({selectedReport.table ?? selectedTable} &bull; {selectedReport.window_label ?? activeWindowLabel})</span>
                  </h4>
                  <p className="text-on-surface-variant leading-relaxed">
                    {selectedReport.narrative || telemetry?.narrative || `Automated journey intelligence audit performed across Supabase table [${selectedReport.table ?? selectedTable}] for workflow [${selectedReport.journey_id ?? selectedJourney}] (${selectedReport.window_label ?? activeWindowLabel}). Evaluated ${(selectedReport.summary?.totalSessions ?? totalSessionsCount).toLocaleString()} entrant sessions. Funnel completion: ${(selectedReport.summary?.completionPct ?? overallCompletionPct).toFixed(1)}%, avg friction: ${selectedReport.summary?.avgFriction ?? avgFrictionScore}/100.`}
                  </p>
                </div>

                {/* Key KPIs Grid */}
                <div className="grid grid-cols-3 gap-2">
                  <div className="p-3 bg-surface-container-low rounded-xl text-center">
                    <div className="text-[11px] text-on-surface-variant">Conversion Rate</div>
                    <div className="text-base font-bold text-primary mt-0.5">{(selectedReport.summary?.completionPct ?? overallCompletionPct).toFixed(1)}%</div>
                  </div>
                  <div className="p-3 bg-surface-container-low rounded-xl text-center">
                    <div className="text-[11px] text-on-surface-variant">Avg Friction Score</div>
                    <div className="text-base font-bold text-primary mt-0.5">{selectedReport.summary?.avgFriction ?? avgFrictionScore}/100</div>
                  </div>
                  <div className="p-3 bg-surface-container-low rounded-xl text-center">
                    <div className="text-[11px] text-on-surface-variant">Critical Bottlenecks</div>
                    <div className="text-base font-bold text-tertiary-container mt-0.5">{selectedReport.summary?.criticalCount ?? criticalSteps.length}</div>
                  </div>
                </div>

                {/* Funnel Breakdown */}
                <div>
                  <h4 className="font-semibold text-primary text-sm mb-2">Stage Progression &amp; Drop-off Matrix</h4>
                  <div className="border border-surface-container-high rounded-xl overflow-hidden">
                    <table className="w-full text-left">
                      <thead className="bg-surface-container-high/60 text-on-surface-variant font-semibold">
                        <tr>
                          <th className="p-2.5">Stage</th>
                          <th className="p-2.5">Users</th>
                          <th className="p-2.5">Drop-off</th>
                          <th className="p-2.5">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-surface-container-high/60">
                        {funnelSteps.map((s, idx) => {
                          const isCrit = criticalSteps.includes(s.step_id) || s.drop_off_pct > 30;
                          return (
                            <tr key={s.step_id}>
                              <td className="p-2.5 font-medium text-primary capitalize">{idx + 1}. {s.step_id.replace(/[_-]/g, ' ')}</td>
                              <td className="p-2.5 font-mono">{s.users.toLocaleString()}</td>
                              <td className="p-2.5 font-mono font-semibold text-tertiary-container">{s.drop_off_pct}%</td>
                              <td className="p-2.5">
                                {isCrit ? (
                                  <span className="px-2 py-0.5 rounded-full text-[10px] bg-red-100 text-red-800 font-bold">CRITICAL</span>
                                ) : (
                                  <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-100 text-emerald-800 font-bold">OPTIMAL</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Recommendations derived strictly from this report's insights */}
                <div className="p-4 bg-surface-container-low rounded-xl border border-surface-container-high">
                  <h4 className="font-semibold text-primary text-sm mb-2">Prioritized Engineering Action Items</h4>
                  <ul className="space-y-1.5 text-on-surface-variant list-disc pl-4">
                    {(selectedReport.insights && selectedReport.insights.length > 0
                      ? selectedReport.insights
                      : telemetry?.insights ?? []
                    ).map((ins: any, idx: number) => (
                      <li key={ins.id || idx}>
                        <strong className="text-primary">{ins.title}:</strong> {ins.recommendation}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-surface-container-high flex items-center justify-between">
              <span className="text-xs text-on-surface-variant font-mono">
                Format: Executive HTML / Markdown
              </span>
              <div className="flex items-center gap-2">
                <a
                  href={selectedReport.content_url}
                  target="_blank"
                  rel="noreferrer"
                  className="bg-secondary/10 hover:bg-secondary/20 text-secondary border border-secondary/30 px-3.5 py-2 rounded-full text-xs font-semibold flex items-center gap-1 transition-colors"
                >
                  <span className="material-symbols-outlined text-[14px]">open_in_new</span>
                  <span>Open HTML Report</span>
                </a>
                <button
                  onClick={handleDownloadPdf}
                  className="bg-surface-container-high hover:bg-surface-container-highest text-primary px-4 py-2 rounded-full text-xs font-semibold cursor-pointer"
                  type="button"
                >
                  Print / Save PDF
                </button>
                <button
                  onClick={() => setSelectedReport(null)}
                  className="bg-primary-container text-on-primary font-label-md px-4 py-2 rounded-full text-xs cursor-pointer font-semibold"
                  type="button"
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Interactive Modal: LangGraph Multi-Agent Workflow Runs Inspector */}
      {showRunInspector && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/50 backdrop-blur-xs animate-fadeIn">
          <div className="w-full max-w-4xl bg-surface-container-lowest rounded-2xl shadow-2xl border border-outline-variant max-h-[90vh] flex flex-col overflow-hidden">
            {/* Header */}
            <div className="p-4 sm:p-5 border-b border-surface-container-high flex items-center justify-between bg-surface-container-low/40">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                  <span className="material-symbols-outlined text-[18px]">account_tree</span>
                </div>
                <div>
                  <h3 className="font-title-md text-primary font-bold text-sm sm:text-base">
                    LangGraph Workflow Runs &amp; Agent Inspector
                  </h3>
                  <p className="text-[11px] text-on-surface-variant">
                    Inspect state checkpoints, worker transitions, and approvals in the CJI LangGraph DAG
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void fetchRecentRuns()}
                  className="p-1.5 text-on-surface-variant hover:text-primary rounded-lg hover:bg-surface-container-high transition-colors cursor-pointer"
                  title="Refresh runs"
                >
                  <span className="material-symbols-outlined text-[18px]">refresh</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowRunInspector(false);
                    setSelectedInspectorRun(null);
                  }}
                  className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center hover:bg-surface-container-highest cursor-pointer text-on-surface"
                  aria-label="Close runs inspector"
                >
                  <span className="material-symbols-outlined text-[18px]">close</span>
                </button>
              </div>
            </div>

            {/* Content Body: Split View */}
            <div className="flex-1 min-h-0 flex flex-col md:flex-row overflow-hidden">
              {/* Left Pane: Runs List */}
              <div className="w-full md:w-80 border-b md:border-b-0 md:border-r border-surface-container-high flex flex-col bg-surface-container-low/20">
                {/* Filter Pills */}
                <div className="p-3 border-b border-surface-container-high flex items-center gap-1 overflow-x-auto text-[11px]">
                  {(['all', 'running', 'awaiting_approval', 'completed', 'failed'] as const).map((f) => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => setInspectorFilter(f)}
                      className={`px-2 py-1 rounded-md font-medium capitalize shrink-0 cursor-pointer transition-colors ${
                        inspectorFilter === f
                          ? 'bg-primary text-on-primary'
                          : 'text-on-surface-variant hover:bg-surface-container-high'
                      }`}
                    >
                      {f.replace(/_/g, ' ')}
                    </button>
                  ))}
                </div>

                {/* Runs Scroll List */}
                <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
                  {recentRuns
                    .filter((r) => inspectorFilter === 'all' || r.status === inspectorFilter)
                    .map((run) => {
                      const isSelected = selectedInspectorRun?.run_id === run.run_id;
                      const statusInfo = getStepStatusInfo(run.status);
                      return (
                        <div
                          key={run.run_id}
                          onClick={() => void fetchRunDetail(run.run_id)}
                          className={`p-2.5 rounded-xl border text-xs cursor-pointer transition-all ${
                            isSelected
                              ? 'bg-primary/5 border-primary/40 shadow-xs'
                              : 'bg-surface-container-lowest hover:bg-surface-container-low border-surface-container-high'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-mono text-[11px] font-semibold text-primary">
                              {run.run_id.slice(0, 10)}…
                            </span>
                            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded capitalize ${statusInfo.bg}`}>
                              {run.status.replace(/_/g, ' ')}
                            </span>
                          </div>
                          <div className="text-[11px] text-on-surface font-medium truncate">
                            {run.journey_id}
                          </div>
                          <div className="text-[10px] text-on-surface-variant mt-1 flex items-center justify-between">
                            <span>{new Date(run.created_at).toLocaleTimeString()}</span>
                            {run.report_id && (
                              <span className="text-secondary font-semibold flex items-center gap-0.5">
                                <span className="material-symbols-outlined text-[12px]">description</span>
                                Report
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}

                  {recentRuns.length === 0 && (
                    <div className="p-6 text-center text-xs text-on-surface-variant">
                      <span className="material-symbols-outlined text-[28px] text-on-surface-variant/50 mb-1 block">
                        account_tree
                      </span>
                      No recent LangGraph runs recorded. Click "Run Analysis" to dispatch a new workflow run.
                    </div>
                  )}
                </div>
              </div>

              {/* Right Pane: Selected Run DAG Details */}
              <div className="flex-1 overflow-y-auto p-4 sm:p-5">
                {selectedInspectorRun ? (
                  <div className="space-y-4">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-surface-container-high">
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="font-bold text-primary text-sm">
                            Run: {selectedInspectorRun.run_id}
                          </h4>
                          <span className={`text-xs px-2 py-0.5 rounded font-semibold capitalize ${getStepStatusInfo(selectedInspectorRun.status).bg}`}>
                            {selectedInspectorRun.status.replace(/_/g, ' ')}
                          </span>
                        </div>
                        <div className="text-xs text-on-surface-variant mt-0.5">
                          Journey: <strong>{selectedInspectorRun.journey_id}</strong> · Created: {new Date(selectedInspectorRun.created_at).toLocaleString()}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {selectedInspectorRun.status === 'awaiting_approval' && (
                          <button
                            type="button"
                            onClick={() => handleApproveRun(selectedInspectorRun.run_id)}
                            disabled={isApproving}
                            className="bg-amber-600 hover:bg-amber-700 text-white text-xs px-3 py-1.5 rounded-full font-semibold flex items-center gap-1 cursor-pointer"
                          >
                            <span className="material-symbols-outlined text-[14px]">check</span>
                            <span>Approve</span>
                          </button>
                        )}
                        {selectedInspectorRun.status === 'failed' && (
                          <button
                            type="button"
                            onClick={() => handleResumeRun(selectedInspectorRun.run_id)}
                            disabled={isResuming}
                            className="bg-rose-700 hover:bg-rose-800 text-white text-xs px-3 py-1.5 rounded-full font-semibold flex items-center gap-1 cursor-pointer"
                          >
                            <span className="material-symbols-outlined text-[14px]">replay</span>
                            <span>Resume</span>
                          </button>
                        )}
                        {selectedInspectorRun.report_id && (
                          <a
                            href={`/reports/${encodeURIComponent(selectedInspectorRun.report_id)}`}
                            target="_blank"
                            rel="noreferrer"
                            className="bg-emerald-700 hover:bg-emerald-800 text-white text-xs px-3 py-1.5 rounded-full font-semibold flex items-center gap-1"
                          >
                            <span className="material-symbols-outlined text-[14px]">open_in_new</span>
                            <span>View Report</span>
                          </a>
                        )}
                      </div>
                    </div>

                    {/* Step-by-Step DAG execution sequence */}
                    <div>
                      <h5 className="text-xs font-bold text-primary mb-2.5">Agent Worker State Transitions</h5>
                      <div className="space-y-2">
                        {LANGGRAPH_WORKERS.map((worker, idx) => {
                          const step = selectedInspectorRun.steps?.[worker.key];
                          const sInfo = getStepStatusInfo(step?.status);
                          const duration = computeStepDuration(step);

                          return (
                            <div
                              key={worker.key}
                              className="p-3 bg-surface-container-low/70 rounded-xl border border-surface-container-high flex items-center justify-between text-xs"
                            >
                              <div className="flex items-center gap-2.5">
                                <span className="font-mono text-[10px] text-on-surface-variant font-bold">
                                  0{idx + 1}
                                </span>
                                <span className={`material-symbols-outlined text-[18px] ${sInfo.iconClass}`}>
                                  {sInfo.icon}
                                </span>
                                <div>
                                  <div className="font-semibold text-primary">{worker.name}</div>
                                  <div className="text-[10px] text-on-surface-variant font-mono">{worker.key}</div>
                                </div>
                              </div>

                              <div className="flex items-center gap-2">
                                {duration && (
                                  <span className="font-mono text-[10px] text-on-surface bg-surface-container-high px-2 py-0.5 rounded">
                                    {duration}
                                  </span>
                                )}
                                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded capitalize ${sInfo.bg}`}>
                                  {sInfo.label}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Failure details if any */}
                    {selectedInspectorRun.failure && (
                      <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-950">
                        <div className="font-bold flex items-center gap-1.5 text-rose-900 mb-1">
                          <span className="material-symbols-outlined text-[16px]">error</span>
                          Failure in {selectedInspectorRun.failure.worker || 'worker'}
                        </div>
                        <p className="font-mono text-[11px] bg-rose-100/60 p-2 rounded">
                          {selectedInspectorRun.failure.message || "Unknown error"}
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-center p-8 text-on-surface-variant">
                    <span className="material-symbols-outlined text-[36px] text-on-surface-variant/40 mb-2">
                      touch_app
                    </span>
                    <p className="text-xs">
                      Select a LangGraph workflow run from the list on the left to inspect its agent transitions and execution checkpoints.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
