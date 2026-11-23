"use client";

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Activity,
  Radio,
  Zap,
  AlertCircle,
  Clock,
  Filter,
  RefreshCw,
  Play,
  Pause,
  Download,
  Flame,
  CheckCircle2,
  Layers
} from 'lucide-react';
import { Task, TimeLog } from '../../types';

export interface TelemetryStreamEvent {
  event_id: string;
  timestamp: string;
  journey_id?: string | null;
  step_id?: string | null;
  event_type: string | null;
  user_id?: string | null;
  session_id?: string | null;
  duration_ms?: number | null;
  url?: string | null;
}

export interface StepDwellStat {
  step_id: string;
  avg_dwell_ms: number;
  unique_users: number;
  avg_rage_clicks: number;
  error_rate_pct: number;
  abandon_rate_pct: number;
}

export interface TimeOperationsScreenProps {
  tasks?: Task[];
  activeTaskId?: string;
  onSelectTask?: (taskId: string) => void;
  timeLogs?: TimeLog[];
  onLogTime?: (taskId: string, durationSeconds: number) => void;
  onDeleteLog?: (logId: string) => void;
}

export const TimeOperationsScreen: React.FC<TimeOperationsScreenProps> = () => {
  const [isStreaming, setIsStreaming] = useState<boolean>(true);
  const [streamStatus, setStreamStatus] = useState<'connected' | 'polling' | 'disconnected'>('connected');
  const [selectedJourney, setSelectedJourney] = useState<string>('all');
  const [selectedEventType, setSelectedEventType] = useState<string>('all');
  const [events, setEvents] = useState<TelemetryStreamEvent[]>([]);
  const [stepDwells, setStepDwells] = useState<StepDwellStat[]>([]);
  const [totalWindowEvents, setTotalWindowEvents] = useState<number>(0);
  const [availableJourneys, setAvailableJourneys] = useState<string[]>(['all']);
  const [lastHeartbeat, setLastHeartbeat] = useState<string>('Just now');
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  const eventSourceRef = useRef<EventSource | null>(null);

  // Initial load of telemetry & dwell metrics
  const fetchSnapshot = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const journeyParam = selectedJourney !== 'all' ? `&journey_id=${encodeURIComponent(selectedJourney)}` : '';
      const res = await fetch(`/api/analytics?minutes=60${journeyParam}`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.events)) {
          setEvents((prev) => {
            const combined = [...data.events, ...prev];
            const seen = new Set<string>();
            return combined.filter((e) => {
              if (seen.has(e.event_id)) return false;
              seen.add(e.event_id);
              return true;
            }).slice(0, 100);
          });
        }
        if (data.metrics?.steps && Array.isArray(data.metrics.steps)) {
          setStepDwells(data.metrics.steps);
        }
        if (data.totalEventsInWindow !== undefined) {
          setTotalWindowEvents(data.totalEventsInWindow);
        }
        if (Array.isArray(data.availableJourneys)) {
          setAvailableJourneys(['all', ...data.availableJourneys.filter((j: string) => j !== 'all')]);
        }
        setLastHeartbeat(new Date().toLocaleTimeString());
      }
    } catch (err) {
      console.warn('Analytics snapshot error:', err);
    } finally {
      setIsRefreshing(false);
    }
  }, [selectedJourney]);

  // Connect SSE Stream
  useEffect(() => {
    fetchSnapshot();

    if (!isStreaming) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      setStreamStatus('disconnected');
      return;
    }

    const sseUrl = new URL('/api/analytics/stream', window.location.origin);
    if (selectedJourney && selectedJourney !== 'all') {
      sseUrl.searchParams.set('journey_id', selectedJourney);
    }
    if (selectedEventType && selectedEventType !== 'all') {
      sseUrl.searchParams.set('event_type', selectedEventType);
    }

    const es = new EventSource(sseUrl.toString());
    eventSourceRef.current = es;

    es.onopen = () => {
      setStreamStatus('connected');
    };

    es.addEventListener('telemetry', (e: MessageEvent) => {
      try {
        const newEvent: TelemetryStreamEvent = JSON.parse(e.data);
        setEvents((prev) => [newEvent, ...prev.slice(0, 99)]);
        setTotalWindowEvents((count) => count + 1);
        setLastHeartbeat(new Date().toLocaleTimeString());
      } catch {
        // ignore parse error
      }
    });

    es.onerror = () => {
      setStreamStatus('polling');
      es.close();
      eventSourceRef.current = null;
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [isStreaming, selectedJourney, selectedEventType, fetchSnapshot]);

  // Fallback Polling when SSE is not actively streaming
  useEffect(() => {
    if (streamStatus !== 'polling' || !isStreaming) return;

    const interval = setInterval(() => {
      fetchSnapshot();
    }, 5000);

    return () => clearInterval(interval);
  }, [streamStatus, isStreaming, fetchSnapshot]);

  // Filtered view
  const filteredEvents = events.filter((ev) => {
    if (selectedJourney !== 'all' && ev.journey_id && ev.journey_id !== selectedJourney) {
      return false;
    }
    if (selectedEventType !== 'all' && ev.event_type !== selectedEventType) {
      return false;
    }
    return true;
  });

  // Calculate dwell summaries
  const totalRageClicks = events.filter((e) => e.event_type === 'rage_click').length;
  const totalErrors = events.filter((e) => e.event_type === 'error').length;
  const avgDwellSeconds =
    stepDwells.length > 0
      ? (stepDwells.reduce((acc, s) => acc + (s.avg_dwell_ms || 0), 0) / stepDwells.length / 1000).toFixed(1)
      : '0.0';

  const handleExportEvents = () => {
    const jsonStr = JSON.stringify(filteredEvents, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cji_telemetry_stream_${new Date().toISOString().slice(0, 19)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getBadgeStyle = (eventType: string | null) => {
    switch (eventType) {
      case 'rage_click':
        return 'bg-red-500/15 text-red-700 border-red-500/30';
      case 'error':
        return 'bg-amber-500/15 text-amber-800 border-amber-500/30';
      case 'abandon':
        return 'bg-orange-500/15 text-orange-800 border-orange-500/30';
      case 'step_complete':
        return 'bg-emerald-500/15 text-emerald-800 border-emerald-500/30';
      default:
        return 'bg-blue-500/15 text-blue-800 border-blue-500/30';
    }
  };

  return (
    <div className="space-y-6">
      {/* Screen Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 bg-white rounded-[28px] border border-[#ECE7E1] shadow-[0_12px_28px_-8px_rgba(180,160,140,0.14)]">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-stat text-[11px] uppercase tracking-wider text-[#6E6B68] bg-[#F3EFEA] px-2.5 py-0.5 rounded-full flex items-center gap-1.5">
              <Radio className={`w-3 h-3 ${isStreaming ? 'text-emerald-600 animate-pulse' : 'text-slate-400'}`} />
              Telemetry Operations
            </span>
            <span
              className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                streamStatus === 'connected'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : streamStatus === 'polling'
                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                  : 'bg-slate-100 text-slate-600 border-slate-200'
              }`}
            >
              {streamStatus === 'connected'
                ? 'SSE Live Stream Connected'
                : streamStatus === 'polling'
                ? 'Polling Fallback (5s)'
                : 'Stream Paused'}
            </span>
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-[#1E1E22]">
            Realtime Telemetry & Dwell Operations
          </h2>
          <p className="text-xs text-[#6E6B68] mt-0.5">
            Live ingestion pulse, customer dwell latency distributions, and active friction event ledger.
          </p>
        </div>

        {/* Global Controls & Metric Pills */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="bg-[#FAF8F5] border border-[#E8E3DC] px-3.5 py-2 rounded-2xl text-right min-w-[100px]">
            <span className="text-[10px] font-stat uppercase text-[#6E6B68] block">
              Events In Window
            </span>
            <span className="font-stat text-lg font-bold text-[#1E1E22] tabular-nums">
              {totalWindowEvents.toLocaleString()}
            </span>
          </div>

          <div className="bg-[#FAF8F5] border border-[#E8E3DC] px-3.5 py-2 rounded-2xl text-right min-w-[90px]">
            <span className="text-[10px] font-stat uppercase text-[#6E6B68] block">
              Avg Dwell
            </span>
            <span className="font-stat text-lg font-bold text-[#1E1E22] tabular-nums">
              {avgDwellSeconds}s
            </span>
          </div>

          <div className="bg-[#FAF8F5] border border-[#E8E3DC] px-3.5 py-2 rounded-2xl text-right min-w-[80px]">
            <span className="text-[10px] font-stat uppercase text-[#6E6B68] block">
              Rage Clicks
            </span>
            <span className="font-stat text-lg font-bold text-red-600 tabular-nums">
              {totalRageClicks}
            </span>
          </div>

          <div className="flex items-center gap-1.5 ml-1">
            <button
              onClick={() => setIsStreaming((prev) => !prev)}
              className={`p-2.5 rounded-2xl border transition-all cursor-pointer ${
                isStreaming
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                  : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
              }`}
              title={isStreaming ? 'Pause Realtime Stream' : 'Resume Realtime Stream'}
            >
              {isStreaming ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
            </button>

            <button
              onClick={fetchSnapshot}
              disabled={isRefreshing}
              className="p-2.5 rounded-2xl border border-[#E8E3DC] bg-white hover:bg-[#FAF8F5] text-slate-700 transition-all cursor-pointer disabled:opacity-50"
              title="Manual Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      {/* Main Grid: Live Ingestion Stream (8 cols) & Step Dwell Diagnostics (4 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Live Event Stream Terminal (8 cols) */}
        <div className="lg:col-span-8 bg-white rounded-[28px] border border-[#ECE7E1] p-6 shadow-[0_12px_28px_-8px_rgba(180,160,140,0.14)] space-y-4">
          {/* Stream Toolbar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#ECE7E1]">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-primary" />
              <h3 className="text-sm font-bold text-[#1E1E22]">Live Event Stream</h3>
              <span className="text-[11px] font-mono text-[#6E6B68]">
                ({filteredEvents.length} buffer)
              </span>
            </div>

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Journey filter */}
              <div className="flex items-center gap-1 bg-[#FAF8F5] border border-[#E8E3DC] rounded-xl px-2 py-1 text-xs">
                <Layers className="w-3.5 h-3.5 text-[#6E6B68]" />
                <select
                  value={selectedJourney}
                  onChange={(e) => setSelectedJourney(e.target.value)}
                  className="bg-transparent text-xs text-[#1E1E22] font-semibold focus:outline-none cursor-pointer"
                >
                  {availableJourneys.map((j) => (
                    <option key={j} value={j}>
                      {j === 'all' ? 'All Journeys' : j}
                    </option>
                  ))}
                </select>
              </div>

              {/* Event Type filter */}
              <div className="flex items-center gap-1 bg-[#FAF8F5] border border-[#E8E3DC] rounded-xl px-2 py-1 text-xs">
                <Filter className="w-3.5 h-3.5 text-[#6E6B68]" />
                <select
                  value={selectedEventType}
                  onChange={(e) => setSelectedEventType(e.target.value)}
                  className="bg-transparent text-xs text-[#1E1E22] font-semibold focus:outline-none cursor-pointer"
                >
                  <option value="all">All Event Types</option>
                  <option value="page_view">page_view</option>
                  <option value="click">click</option>
                  <option value="rage_click">rage_click</option>
                  <option value="error">error</option>
                  <option value="abandon">abandon</option>
                  <option value="step_complete">step_complete</option>
                </select>
              </div>

              {/* Export JSON */}
              <button
                onClick={handleExportEvents}
                className="flex items-center gap-1 bg-[#FAF8F5] hover:bg-[#F3EFEA] border border-[#E8E3DC] rounded-xl px-2.5 py-1 text-xs font-semibold text-[#1E1E22] transition-colors cursor-pointer"
              >
                <Download className="w-3.5 h-3.5 text-[#6E6B68]" />
                <span>Export</span>
              </button>
            </div>
          </div>

          {/* Event Stream List */}
          <div className="space-y-2 max-h-[560px] overflow-y-auto pr-1">
            {filteredEvents.length === 0 ? (
              <div className="text-center py-16 bg-[#FAF8F5] rounded-2xl border border-dashed border-[#E8E3DC]">
                <Activity className="w-8 h-8 text-[#A8A49E] mx-auto mb-2 animate-pulse" />
                <p className="text-xs font-semibold text-[#1E1E22]">Awaiting incoming telemetry events...</p>
                <p className="text-[11px] text-[#6E6B68] mt-1">
                  Events sent to the collector will stream here live via SSE.
                </p>
              </div>
            ) : (
              filteredEvents.map((ev, idx) => (
                <div
                  key={`${ev.event_id}-${idx}`}
                  className="p-3 bg-[#FAF8F5] hover:bg-white rounded-2xl border border-[#ECE7E1] hover:border-[#D5D0C9] transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-2.5"
                >
                  <div className="flex items-start sm:items-center gap-3 min-w-0">
                    <span
                      className={`text-[10px] font-bold uppercase font-mono px-2 py-0.5 rounded-lg border whitespace-nowrap ${getBadgeStyle(
                        ev.event_type
                      )}`}
                    >
                      {ev.event_type || 'event'}
                    </span>

                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-xs font-bold text-[#1E1E22]">
                          {ev.step_id || 'unassigned_step'}
                        </span>
                        {ev.journey_id && (
                          <span className="text-[10px] font-medium text-[#6E6B68] bg-[#F3EFEA] px-1.5 py-0.2 rounded-md">
                            {ev.journey_id}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 mt-0.5 text-[11px] font-mono text-[#6E6B68] truncate">
                        <span>User: {ev.user_id ? String(ev.user_id).slice(0, 12) : 'anon'}</span>
                        <span>•</span>
                        <span>Session: {ev.session_id ? String(ev.session_id).slice(0, 10) : 'n/a'}</span>
                        {ev.url && (
                          <>
                            <span>•</span>
                            <span className="truncate max-w-[180px]">{ev.url}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 sm:text-right shrink-0">
                    {ev.duration_ms !== null && ev.duration_ms !== undefined && ev.duration_ms > 0 && (
                      <div className="text-right">
                        <span className="text-[10px] font-mono text-[#6E6B68] block">Dwell</span>
                        <span className="text-xs font-bold font-mono text-[#1E1E22]">
                          {(ev.duration_ms / 1000).toFixed(1)}s
                        </span>
                      </div>
                    )}
                    <span className="text-[10px] font-mono text-[#A8A49E]">
                      {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : 'now'}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="pt-2 border-t border-[#ECE7E1] flex items-center justify-between text-[11px] text-[#6E6B68]">
            <span>Collector SSE Protocol (Keepalive: 15s)</span>
            <span className="font-mono text-[10px]">Heartbeat: {lastHeartbeat}</span>
          </div>
        </div>

        {/* Right Column: Step Dwell & Latency Breakdown (4 cols) */}
        <div className="lg:col-span-4 space-y-6">
          {/* Step Dwell Times Card */}
          <div className="bg-white rounded-[28px] border border-[#ECE7E1] p-6 shadow-[0_12px_28px_-8px_rgba(180,160,140,0.14)] space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-primary" />
                <h3 className="text-sm font-bold text-[#1E1E22]">Step Dwell Latency</h3>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200">
                Live Stats
              </span>
            </div>

            <p className="text-xs text-[#6E6B68]">
              Average time spent by visitors on each funnel stage before progressing or abandoning.
            </p>

            <div className="space-y-3 pt-1">
              {stepDwells.length === 0 ? (
                <div className="text-center py-8 text-xs text-[#6E6B68]">
                  No step dwell metrics available for the current window.
                </div>
              ) : (
                stepDwells.map((s) => {
                  const dwellSec = (s.avg_dwell_ms / 1000).toFixed(1);
                  const isHighDwell = s.avg_dwell_ms > 45000;
                  return (
                    <div
                      key={s.step_id}
                      className="p-3 bg-[#FAF8F5] rounded-2xl border border-[#ECE7E1] space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-[#1E1E22] truncate max-w-[180px]">
                          {s.step_id}
                        </span>
                        <span
                          className={`font-mono font-bold text-xs ${
                            isHighDwell ? 'text-amber-700' : 'text-[#1E1E22]'
                          }`}
                        >
                          {dwellSec}s avg
                        </span>
                      </div>

                      {/* Mini bar indicator */}
                      <div className="w-full bg-[#E8E3DC] h-1.5 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            isHighDwell ? 'bg-amber-500' : 'bg-primary'
                          }`}
                          style={{
                            width: `${Math.min(100, Math.max(8, (s.avg_dwell_ms / 60000) * 100))}%`,
                          }}
                        />
                      </div>

                      <div className="flex items-center justify-between text-[10px] text-[#6E6B68] pt-0.5">
                        <span>{s.unique_users.toLocaleString()} users</span>
                        <span>Dropoff: {s.abandon_rate_pct.toFixed(0)}%</span>
                        {s.avg_rage_clicks > 0 && (
                          <span className="text-red-600 font-semibold flex items-center gap-0.5">
                            <Flame className="w-2.5 h-2.5" />
                            {s.avg_rage_clicks} rage
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Friction & Rage Radar */}
          <div className="bg-white rounded-[28px] border border-[#ECE7E1] p-6 shadow-[0_12px_28px_-8px_rgba(180,160,140,0.14)] space-y-4">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-600" />
              <h3 className="text-sm font-bold text-[#1E1E22]">Active Friction Radar</h3>
            </div>

            <div className="space-y-2.5">
              <div className="p-3 bg-red-50/60 rounded-2xl border border-red-100 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <Flame className="w-4 h-4 text-red-600" />
                  <div>
                    <span className="text-xs font-bold text-red-900 block">Rage Click Incidents</span>
                    <span className="text-[10px] text-red-700">Rapid clicks within &lt;500ms</span>
                  </div>
                </div>
                <span className="text-base font-bold font-mono text-red-700">{totalRageClicks}</span>
              </div>

              <div className="p-3 bg-amber-50/60 rounded-2xl border border-amber-100 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <AlertCircle className="w-4 h-4 text-amber-600" />
                  <div>
                    <span className="text-xs font-bold text-amber-900 block">Logged Errors</span>
                    <span className="text-[10px] text-amber-700">Client script & API failures</span>
                  </div>
                </div>
                <span className="text-base font-bold font-mono text-amber-700">{totalErrors}</span>
              </div>

              <div className="p-3 bg-emerald-50/60 rounded-2xl border border-emerald-100 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <div>
                    <span className="text-xs font-bold text-emerald-900 block">Pipeline Health</span>
                    <span className="text-[10px] text-emerald-700">Ingestion collector status</span>
                  </div>
                </div>
                <span className="text-xs font-bold text-emerald-800">Operational</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
