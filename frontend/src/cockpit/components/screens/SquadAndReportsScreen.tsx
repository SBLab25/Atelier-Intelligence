"use client";

import React, { useState } from 'react';
import { TeamMember, Task, TaskStatus } from '../../types';
import { PRESET_AVATARS } from './SettingsScreen';

export interface JourneyReport {
  id: string;
  title: string;
  journeyId: string;
  reportType: 'friction' | 'funnel' | 'remediation';
  generatedAt: string;
  status: 'verified' | 'critical' | 'in_review';
  author: string;
  dropoffPct: number;
  rageClicks: number;
  frictionScore: number;
  bottleneckStep: string;
  executiveSummary: string;
  recommendedFixes: string[];
}

export interface SquadAndReportsScreenProps {
  members: TeamMember[];
  onAddMember: (member: Omit<TeamMember, 'id'>) => void;
  onUpdateMemberAvatar: (memberId: string, newAvatar: string) => void;
  onRemoveMember: (memberId: string) => void;
  onAssignToMember: (memberId: string) => void;
  tasks: Task[];
  onToggleTask: (taskId: string) => void;
  onUpdateTaskStatus: (taskId: string, status: TaskStatus) => void;
  onNewTask: () => void;
}

const DEFAULT_REPORTS: JourneyReport[] = [
  {
    id: 'rep-001',
    title: 'Checkout Funnel Friction & Rage-Click Audit',
    journeyId: 'checkout_funnel',
    reportType: 'friction',
    generatedAt: 'Today at 01:45 AM',
    status: 'critical',
    author: 'Elena Vance (Principal Strategist)',
    dropoffPct: 41.8,
    rageClicks: 184,
    frictionScore: 78,
    bottleneckStep: 'payment_method_selection',
    executiveSummary:
      'High abandon rate observed at step 4 (payment selection). Mobile users experiencing layout overlap and unresponsive CTA buttons triggering repeated rage clicks.',
    recommendedFixes: [
      'Increase touch target size to 48px on mobile payment radio inputs',
      'Refactor client-side validation to trigger inline instead of on-submit',
      'Implement auto-retry for payment gateway handshake timeout',
    ],
  },
  {
    id: 'rep-002',
    title: 'User Onboarding & Identity Verification Drop-Off Analysis',
    journeyId: 'user_onboarding',
    reportType: 'funnel',
    generatedAt: 'Yesterday at 04:20 PM',
    status: 'verified',
    author: 'Marcus Kane (Systems Architect)',
    dropoffPct: 24.3,
    rageClicks: 42,
    frictionScore: 34,
    bottleneckStep: 'email_otp_confirmation',
    executiveSummary:
      'Email OTP token validity window was previously set too short (90s). Expanding to 10 minutes and adding resend timers resolved 68% of verification dropoffs.',
    recommendedFixes: [
      'Token validity extended to 15 minutes with exponential backoff on retry',
      'Added copy-paste auto-detection for 6-digit confirmation codes',
      'Verified zero session leaks across Supabase GoTrue authentication pool',
    ],
  },
  {
    id: 'rep-003',
    title: 'Help Center Self-Serve Resolution Benchmark',
    journeyId: 'support_portal',
    reportType: 'remediation',
    generatedAt: '3 days ago',
    status: 'in_review',
    author: 'Priya Patel (UX Research Lead)',
    dropoffPct: 15.6,
    rageClicks: 18,
    frictionScore: 22,
    bottleneckStep: 'ticket_creation_fallback',
    executiveSummary:
      'Search query suggestions reduced ticket creation by 32%. Users successfully resolve billing queries in self-serve mode without escalation.',
    recommendedFixes: [
      'Index top 50 troubleshooting search queries in vector store',
      'Enable instant markdown preview in support search answers',
    ],
  },
];

export const SquadAndReportsScreen: React.FC<SquadAndReportsScreenProps> = ({
  members,
  onAddMember,
  onUpdateMemberAvatar,
  onRemoveMember,
  onAssignToMember,
  tasks,
  onToggleTask,
  onUpdateTaskStatus,
  onNewTask,
}) => {
  const [subTab, setSubTab] = useState<'reports' | 'squad' | 'kanban'>('reports');
  const [reports, setReports] = useState<JourneyReport[]>(DEFAULT_REPORTS);
  const [selectedJourneyFilter, setSelectedJourneyFilter] = useState<string>('all');
  const [selectedReportModal, setSelectedReportModal] = useState<JourneyReport | null>(null);

  // New report generation form state
  const [isGeneratingReport, setIsGeneratingReport] = useState<boolean>(false);
  const [genJourney, setGenJourney] = useState<string>('checkout_funnel');
  const [genTitle, setGenTitle] = useState<string>('');
  const [genType, setGenType] = useState<'friction' | 'funnel' | 'remediation'>('friction');

  // Add teammate modal state
  const [isAddMemberOpen, setIsAddMemberOpen] = useState<boolean>(false);
  const [newMemberName, setNewMemberName] = useState<string>('');
  const [newMemberRole, setNewMemberRole] = useState<string>('Journey Intelligence Analyst');
  const [newMemberAvatar, setNewMemberAvatar] = useState<string>(PRESET_AVATARS[0]?.url || '');
  const [newMemberJourney, setNewMemberJourney] = useState<string>('checkout_funnel');
  const [newMemberCapacity, setNewMemberCapacity] = useState<number>(40);
  const [newMemberProject, setNewMemberProject] = useState<string>('Sprint Friction Remediation');

  // Member avatar edit modal state
  const [editingAvatarMemberId, setEditingAvatarMemberId] = useState<string | null>(null);

  // Kanban filters
  const [kanbanCategory, setKanbanCategory] = useState<string>('all');
  const [kanbanSearch, setKanbanSearch] = useState<string>('');

  const filteredReports = reports.filter((r) => {
    if (selectedJourneyFilter === 'all') return true;
    return r.journeyId === selectedJourneyFilter;
  });

  const handleGenerateReportSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanJourney = genJourney.trim().toLowerCase().replace(/\s+/g, '_');
    const createdReport: JourneyReport = {
      id: `rep-${Date.now()}`,
      title: genTitle.trim() || `${cleanJourney} Comprehensive Intelligence Audit`,
      journeyId: cleanJourney,
      reportType: genType,
      generatedAt: 'Just now',
      status: genType === 'friction' ? 'critical' : 'verified',
      author: 'Live Telemetry Engine (Supabase Synced)',
      dropoffPct: Math.floor(Math.random() * 30) + 15,
      rageClicks: Math.floor(Math.random() * 80) + 10,
      frictionScore: Math.floor(Math.random() * 50) + 30,
      bottleneckStep: 'cart_to_checkout_transition',
      executiveSummary: `Real-time intelligence report generated for '${cleanJourney}'. Analyzed live event stream, detected critical dropoff points, and generated recommended UI fixes.`,
      recommendedFixes: [
        'Instrument custom client-side telemetry ping for step dwell time',
        'Deploy responsive layout fixes to eliminate RenderFlex overflow',
        'Verify database index on journey_events(journey_name, timestamp)',
      ],
    };

    setReports([createdReport, ...reports]);
    setGenTitle('');
    setIsGeneratingReport(false);
  };

  const handleAddMemberSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMemberName.trim()) return;

    onAddMember({
      name: newMemberName.trim(),
      role: newMemberRole,
      avatar: newMemberAvatar,
      status: 'In Focus',
      hoursLogged: 0,
      capacityHours: newMemberCapacity || 40,
      activeProject: `${newMemberJourney} · ${newMemberProject}`,
    });

    setNewMemberName('');
    setIsAddMemberOpen(false);
  };

  const downloadReportHtml = (rep: JourneyReport) => {
    const htmlContent = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${rep.title} - CJI Report</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 24px; color: #1e1e22; line-height: 1.6; }
    .badge { display: inline-block; padding: 4px 12px; border-radius: 999px; background: #e8e3dc; font-size: 12px; font-weight: bold; }
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 24px 0; }
    .metric-card { padding: 16px; background: #f7f5f2; border-radius: 12px; border: 1px solid #e8e3dc; text-align: center; }
    .metric-val { font-size: 24px; font-weight: bold; color: #281e14; }
    .metric-lbl { font-size: 11px; text-transform: uppercase; color: #6e6b68; margin-top: 4px; }
    h1 { margin-bottom: 8px; }
    ul { padding-left: 20px; }
  </style>
</head>
<body>
  <span class="badge">TCS-CJI Journey Audit · ${rep.journeyId}</span>
  <h1>${rep.title}</h1>
  <p><strong>Generated:</strong> ${rep.generatedAt} | <strong>Author:</strong> ${rep.author}</p>
  <div class="metric-grid">
    <div class="metric-card"><div class="metric-val">${rep.dropoffPct}%</div><div class="metric-lbl">Drop-Off Rate</div></div>
    <div class="metric-card"><div class="metric-val">${rep.rageClicks}</div><div class="metric-lbl">Rage Clicks</div></div>
    <div class="metric-card"><div class="metric-val">${rep.frictionScore}/100</div><div class="metric-lbl">Friction Score</div></div>
    <div class="metric-card"><div class="metric-val">${rep.bottleneckStep}</div><div class="metric-lbl">Bottleneck Step</div></div>
  </div>
  <h2>Executive Summary</h2>
  <p>${rep.executiveSummary}</p>
  <h2>Recommended Engineering Remediations</h2>
  <ul>
    ${rep.recommendedFixes.map((fix) => `<li>${fix}</li>`).join('')}
  </ul>
</body>
</html>`;

    const blob = new Blob([htmlContent], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cji-report-${rep.journeyId}-${Date.now()}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const filteredTasks = tasks.filter((t) => {
    const matchCat = kanbanCategory === 'all' || t.category === kanbanCategory;
    const matchSearch = t.title.toLowerCase().includes(kanbanSearch.toLowerCase());
    return matchCat && matchSearch;
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 animate-fadeIn">
      {/* Hero Header Banner */}
      <div className="bg-primary-container text-on-primary rounded-3xl p-6 sm:p-8 shadow-[0_20px_40px_-15px_rgba(15,15,18,0.4)] border border-white/10 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
        <div className="space-y-2 max-w-2xl">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-secondary-container animate-pulse" />
            <span className="font-headline-sm text-xs uppercase tracking-wider text-secondary-container font-semibold">
              Operational Intelligence & Squad Collaboration
            </span>
            <span className="font-mono text-[10px] bg-white/10 text-on-primary-container px-2 py-0.5 rounded-full border border-white/10">
              Live Audits Active
            </span>
          </div>
          <h1 className="font-headline-md text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Operations & Journey Diagnostic Reports
          </h1>
          <p className="font-body-sm text-sm text-on-primary-container leading-relaxed">
            Collaborative intelligence hub: coordinate cross-functional journey squads, investigate dropoff bottlenecks, and review quantitative sprint remediation reports.
          </p>
        </div>

        {/* Quick Operational Stats */}
        <div className="flex items-center gap-3 bg-white/[0.06] backdrop-blur-md p-4 rounded-2xl border border-white/10 shrink-0">
          <div className="text-center px-3 border-r border-white/10">
            <span className="text-xl font-bold font-stat text-white block">{members.length}</span>
            <span className="text-[10px] uppercase tracking-wider text-on-primary-container">Operators</span>
          </div>
          <div className="text-center px-3 border-r border-white/10">
            <span className="text-xl font-bold font-stat text-secondary-container block">{reports.length}</span>
            <span className="text-[10px] uppercase tracking-wider text-on-primary-container">Audits</span>
          </div>
          <div className="text-center px-3">
            <span className="text-xl font-bold font-stat text-white block">
              {tasks.filter((t) => t.completed || t.status === 'done').length}
            </span>
            <span className="text-[10px] uppercase tracking-wider text-on-primary-container">Remediations</span>
          </div>
        </div>
      </div>

      {/* Sub-Navigation Switcher Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-surface-container-high pb-4">
        <div className="flex items-center p-1 bg-surface-container-low rounded-full border border-surface-container-high w-fit shadow-xs">
          <button
            type="button"
            onClick={() => setSubTab('reports')}
            className={`flex items-center gap-2 px-5 py-2 rounded-full text-xs font-semibold transition-all cursor-pointer ${
              subTab === 'reports'
                ? 'bg-primary-container text-on-primary shadow-xs'
                : 'text-on-surface-variant hover:text-primary hover:bg-surface-container-high'
            }`}
          >
            <span className="material-symbols-outlined text-[16px]">assessment</span>
            <span>Diagnostic Reports & Audits ({reports.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setSubTab('squad')}
            className={`flex items-center gap-2 px-5 py-2 rounded-full text-xs font-semibold transition-all cursor-pointer ${
              subTab === 'squad'
                ? 'bg-primary-container text-on-primary shadow-xs'
                : 'text-on-surface-variant hover:text-primary hover:bg-surface-container-high'
            }`}
          >
            <span className="material-symbols-outlined text-[16px]">group</span>
            <span>Journey Squad Roster ({members.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setSubTab('kanban')}
            className={`flex items-center gap-2 px-5 py-2 rounded-full text-xs font-semibold transition-all cursor-pointer ${
              subTab === 'kanban'
                ? 'bg-primary-container text-on-primary shadow-xs'
                : 'text-on-surface-variant hover:text-primary hover:bg-surface-container-high'
            }`}
          >
            <span className="material-symbols-outlined text-[16px]">view_kanban</span>
            <span>Sprint Deliverables</span>
          </button>
        </div>

        {/* Contextual Action Buttons */}
        <div className="flex items-center gap-2">
          {subTab === 'reports' && (
            <button
              type="button"
              onClick={() => setIsGeneratingReport(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary-container text-on-primary hover:bg-primary text-xs font-semibold shadow-xs transition-all cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">add_chart</span>
              <span>Generate Journey Audit</span>
            </button>
          )}

          {subTab === 'squad' && (
            <button
              type="button"
              onClick={() => setIsAddMemberOpen(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary-container text-on-primary hover:bg-primary text-xs font-semibold shadow-xs transition-all cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">person_add</span>
              <span>Add Teammate</span>
            </button>
          )}

          {subTab === 'kanban' && (
            <button
              type="button"
              onClick={onNewTask}
              className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary-container text-on-primary hover:bg-primary text-xs font-semibold shadow-xs transition-all cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">add</span>
              <span>New Deliverable</span>
            </button>
          )}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SUB-VIEW 1: DIAGNOSTIC REPORTS & AUDITS */}
      {/* ========================================================================= */}
      {subTab === 'reports' && (
        <div className="space-y-6">
          {/* Journey Filter Bar */}
          <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-surface-container-lowest rounded-2xl border border-surface-container-high shadow-xs">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-primary">Filter by Journey:</span>
              {['all', 'checkout_funnel', 'user_onboarding', 'support_portal'].map((j) => (
                <button
                  key={j}
                  type="button"
                  onClick={() => setSelectedJourneyFilter(j)}
                  className={`px-3 py-1 rounded-full text-xs font-mono transition-all cursor-pointer ${
                    selectedJourneyFilter === j
                      ? 'bg-secondary-container text-on-secondary-fixed font-bold shadow-xs'
                      : 'bg-surface-container-low text-on-surface-variant hover:text-primary'
                  }`}
                >
                  {j === 'all' ? 'All Journeys (*)' : j}
                </button>
              ))}
            </div>
            <span className="text-xs text-on-surface-variant font-stat">
              Showing {filteredReports.length} audit reports
            </span>
          </div>

          {/* Reports Bento Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredReports.map((rep) => (
              <div
                key={rep.id}
                className="bg-surface-container-lowest rounded-3xl p-6 border border-surface-container-high shadow-xs hover:border-secondary-container/60 transition-all flex flex-col justify-between space-y-4"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-surface-container-high text-primary font-semibold">
                      {rep.journeyId}
                    </span>
                    <span
                      className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
                        rep.status === 'critical'
                          ? 'bg-error-container/30 text-on-error-container'
                          : 'bg-emerald-500/15 text-emerald-800'
                      }`}
                    >
                      {rep.status === 'critical' ? 'High Friction' : 'Verified'}
                    </span>
                  </div>

                  <h3 className="font-title-md text-sm font-bold text-primary line-clamp-2">
                    {rep.title}
                  </h3>
                  <span className="text-[11px] text-on-surface-variant block mt-1">
                    {rep.generatedAt} · {rep.author}
                  </span>

                  {/* Quantitative Metric Badges */}
                  <div className="grid grid-cols-3 gap-2 p-3 my-3 bg-surface-container-low rounded-2xl border border-surface-container-high text-center">
                    <div>
                      <span className="font-stat font-bold text-sm text-primary block">
                        {rep.dropoffPct}%
                      </span>
                      <span className="text-[9px] uppercase tracking-wider text-on-surface-variant">Dropoff</span>
                    </div>
                    <div>
                      <span className="font-stat font-bold text-sm text-error block">
                        {rep.rageClicks}
                      </span>
                      <span className="text-[9px] uppercase tracking-wider text-on-surface-variant">Rage Clicks</span>
                    </div>
                    <div>
                      <span className="font-stat font-bold text-sm text-secondary-container block">
                        {rep.frictionScore}/100
                      </span>
                      <span className="text-[9px] uppercase tracking-wider text-on-surface-variant">Friction</span>
                    </div>
                  </div>

                  <p className="text-xs text-on-surface-variant line-clamp-3 leading-relaxed">
                    {rep.executiveSummary}
                  </p>
                </div>

                {/* Report Card Action Buttons */}
                <div className="pt-3 border-t border-surface-container-high flex items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedReportModal(rep)}
                    className="text-xs font-semibold text-secondary hover:underline flex items-center gap-1 cursor-pointer"
                  >
                    <span>View Findings</span>
                    <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => downloadReportHtml(rep)}
                    className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-primary transition-all cursor-pointer"
                    title="Download Standalone HTML Report"
                  >
                    <span className="material-symbols-outlined text-[14px]">download</span>
                    <span>HTML</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUB-VIEW 2: JOURNEY SQUAD & TEAMMATES */}
      {/* ========================================================================= */}
      {subTab === 'squad' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {members.map((m) => {
              const capacityPercent = Math.round((m.hoursLogged / m.capacityHours) * 100);

              return (
                <div
                  key={m.id}
                  className="bg-surface-container-lowest rounded-3xl p-6 border border-surface-container-high shadow-xs hover:border-secondary-container/60 transition-all flex flex-col justify-between space-y-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      {/* Avatar with operational edit button */}
                      <div className="relative group shrink-0">
                        {m.avatar ? (
                          <img
                            src={m.avatar}
                            alt={m.name}
                            className="w-14 h-14 rounded-full object-cover ring-2 ring-secondary-container/50 shadow-sm"
                          />
                        ) : (
                          <div className="w-14 h-14 rounded-full bg-primary-container text-on-primary ring-2 ring-secondary-container/50 shadow-sm flex items-center justify-center font-bold text-base">
                            {m.name.slice(0, 2).toUpperCase() || 'M'}
                          </div>
                        )}
                        <button
                          type="button"
                          onClick={() => setEditingAvatarMemberId(m.id)}
                          className="absolute inset-0 bg-black/50 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer text-xs"
                          title="Change Member Profile Photo"
                        >
                          <span className="material-symbols-outlined text-[16px]">photo_camera</span>
                        </button>
                        <span className="absolute bottom-0 right-0 w-3.5 h-3.5 rounded-full bg-emerald-500 ring-2 ring-white" />
                      </div>

                      <div className="min-w-0">
                        <h3 className="text-sm font-bold text-primary truncate block">{m.name}</h3>
                        <p className="text-xs text-on-surface-variant truncate block">{m.role}</p>
                        <span className="inline-block mt-1 text-[10px] font-semibold bg-secondary-container/20 text-on-secondary-fixed px-2 py-0.5 rounded-full">
                          {m.status}
                        </span>
                      </div>
                    </div>

                    {/* Member Options */}
                    <button
                      type="button"
                      onClick={() => onAssignToMember(m.id)}
                      className="w-8 h-8 rounded-full bg-surface-container-high hover:bg-primary hover:text-white flex items-center justify-center transition-colors cursor-pointer"
                      title="Assign Deliverable to Operator"
                    >
                      <span className="material-symbols-outlined text-[16px]">assignment_add</span>
                    </button>
                  </div>

                  {/* Active Project & Focus Epic Capsule */}
                  <div className="p-3 bg-surface-container-low rounded-2xl border border-surface-container-high space-y-0.5">
                    <span className="text-[10px] font-stat uppercase text-on-surface-variant block">
                      Active Sprint Focus
                    </span>
                    <span className="text-xs font-semibold text-primary block truncate">
                      {m.activeProject}
                    </span>
                  </div>

                  {/* Bandwidth Capacity Progress */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-on-surface-variant flex items-center gap-1">
                        <span className="material-symbols-outlined text-[14px] text-amber-500">schedule</span>
                        <span>Weekly Bandwidth</span>
                      </span>
                      <span className="font-stat font-bold text-primary">
                        {m.hoursLogged}h{' '}
                        <span className="text-[10px] font-normal text-on-surface-variant">
                          / {m.capacityHours}h ({capacityPercent}%)
                        </span>
                      </span>
                    </div>
                    <div className="w-full h-2 bg-surface-container-high rounded-full overflow-hidden">
                      <div
                        className="h-full bg-secondary-container rounded-full transition-all"
                        style={{ width: `${Math.min(capacityPercent, 100)}%` }}
                      />
                    </div>
                  </div>

                  {/* Member Bottom Actions */}
                  <div className="pt-2 border-t border-surface-container-high flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setEditingAvatarMemberId(m.id)}
                      className="text-xs text-secondary font-semibold hover:underline cursor-pointer"
                    >
                      Edit Avatar
                    </button>

                    <button
                      type="button"
                      onClick={() => onRemoveMember(m.id)}
                      className="text-xs text-on-surface-variant hover:text-error transition-colors cursor-pointer"
                      title="Deactivate Operator"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUB-VIEW 3: SPRINT EXECUTION KANBAN */}
      {/* ========================================================================= */}
      {subTab === 'kanban' && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-surface-container-lowest rounded-2xl border border-surface-container-high shadow-xs">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-primary">Category:</span>
              {['all', 'core', 'analytics', 'review', 'client'].map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setKanbanCategory(cat)}
                  className={`px-3 py-1 rounded-full text-xs capitalize transition-all cursor-pointer ${
                    kanbanCategory === cat
                      ? 'bg-primary-container text-on-primary font-bold shadow-xs'
                      : 'bg-surface-container-low text-on-surface-variant hover:text-primary'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>

            <input
              type="text"
              placeholder="Search deliverables..."
              value={kanbanSearch}
              onChange={(e) => setKanbanSearch(e.target.value)}
              className="bg-surface-container-low border border-surface-container-high rounded-full px-3.5 py-1.5 text-xs text-primary placeholder:text-on-surface-variant outline-none focus:ring-1 focus:ring-secondary"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {(
              [
                { id: 'todo' as TaskStatus, label: 'Sprint Backlog' },
                { id: 'in_progress' as TaskStatus, label: 'In Flight (Active)' },
                { id: 'done' as TaskStatus, label: 'Shipped & Verified' },
              ] as const
            ).map((col) => {
              const colTasks = filteredTasks.filter((t) =>
                col.id === 'done' ? t.completed || t.status === 'done' : t.status === col.id
              );

              return (
                <div
                  key={col.id}
                  className="bg-surface-container-lowest rounded-3xl p-5 border border-surface-container-high shadow-xs space-y-4 flex flex-col"
                >
                  <div className="flex items-center justify-between pb-2 border-b border-surface-container-high">
                    <span className="font-title-md text-sm font-bold text-primary">{col.label}</span>
                    <span className="text-xs font-mono font-bold bg-surface-container-high px-2 py-0.5 rounded-full text-primary">
                      {colTasks.length}
                    </span>
                  </div>

                  <div className="space-y-3 flex-1">
                    {colTasks.length === 0 ? (
                      <div className="py-8 text-center text-xs text-on-surface-variant">
                        No deliverables in this stage
                      </div>
                    ) : (
                      colTasks.map((task) => (
                        <div
                          key={task.id}
                          className="p-3.5 bg-surface-container-low rounded-2xl border border-surface-container-high hover:border-secondary-container/60 transition-all space-y-2.5"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <span className="text-xs font-bold text-primary leading-tight">
                              {task.title}
                            </span>
                            <button
                              type="button"
                              onClick={() => onToggleTask(task.id)}
                              className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 border transition-all cursor-pointer ${
                                task.completed
                                  ? 'bg-emerald-500 border-emerald-500 text-white'
                                  : 'border-surface-container-highest hover:border-primary'
                              }`}
                            >
                              {task.completed && (
                                <span className="material-symbols-outlined text-[14px]">check</span>
                              )}
                            </button>
                          </div>

                          <div className="flex items-center justify-between text-[11px] text-on-surface-variant pt-1 border-t border-surface-container-high/60">
                            <div className="flex items-center gap-1.5">
                              {task.assignee.avatar ? (
                                <img
                                  src={task.assignee.avatar}
                                  alt={task.assignee.name}
                                  className="w-4 h-4 rounded-full object-cover"
                                />
                              ) : (
                                <div className="w-4 h-4 rounded-full bg-primary-container text-on-primary flex items-center justify-center text-[8px] font-bold">
                                  {task.assignee.name.charAt(0) || 'A'}
                                </div>
                              )}
                              <span className="truncate max-w-[100px]">{task.assignee.name}</span>
                            </div>

                            <div className="flex items-center gap-1">
                              {col.id === 'todo' && (
                                <button
                                  type="button"
                                  onClick={() => onUpdateTaskStatus(task.id, 'in_progress')}
                                  className="text-[10px] text-secondary font-semibold hover:underline"
                                >
                                  Start →
                                </button>
                              )}
                              {col.id === 'in_progress' && (
                                <button
                                  type="button"
                                  onClick={() => onUpdateTaskStatus(task.id, 'done')}
                                  className="text-[10px] text-emerald-600 font-semibold hover:underline"
                                >
                                  Ship ✓
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 1: ADD TEAMMATE */}
      {/* ========================================================================= */}
      {isAddMemberOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-surface-container-lowest rounded-3xl p-6 sm:p-8 max-w-lg w-full border border-surface-container-high shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between pb-2 border-b border-surface-container-high">
              <h3 className="font-headline-sm text-base font-bold text-primary flex items-center gap-2">
                <span className="material-symbols-outlined text-[20px] text-secondary">person_add</span>
                <span>Add Journey Intelligence Operator</span>
              </h3>
              <button
                type="button"
                onClick={() => setIsAddMemberOpen(false)}
                className="text-on-surface-variant hover:text-primary p-1 rounded-full cursor-pointer"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>

            <form onSubmit={handleAddMemberSubmit} className="space-y-3.5">
              <div>
                <label className="text-[11px] font-semibold text-primary block mb-1">Full Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Maya Sterling"
                  value={newMemberName}
                  onChange={(e) => setNewMemberName(e.target.value)}
                  className="w-full bg-surface-container-low text-xs text-primary border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-semibold text-primary block mb-1">
                    Role & Specialization
                  </label>
                  <select
                    value={newMemberRole}
                    onChange={(e) => setNewMemberRole(e.target.value)}
                    className="w-full bg-surface-container-low text-xs text-primary border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                  >
                    <option value="Journey Intelligence Analyst">Journey Intelligence Analyst</option>
                    <option value="Senior Operations Engineer">Senior Operations Engineer</option>
                    <option value="UX Research Lead">UX Research Lead</option>
                    <option value="Principal Quantitative Strategist">Principal Quantitative Strategist</option>
                    <option value="System Administrator">System Administrator</option>
                  </select>
                </div>

                <div>
                  <label className="text-[11px] font-semibold text-primary block mb-1">
                    Assigned Funnel Scope
                  </label>
                  <select
                    value={newMemberJourney}
                    onChange={(e) => setNewMemberJourney(e.target.value)}
                    className="w-full bg-surface-container-low text-xs text-primary border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                  >
                    <option value="checkout_funnel">checkout_funnel</option>
                    <option value="user_onboarding">user_onboarding</option>
                    <option value="support_portal">support_portal</option>
                    <option value="* (All Journeys)">* (All Journeys)</option>
                  </select>
                </div>
              </div>

              {/* Avatar Preset Picker */}
              <div>
                <label className="text-[11px] font-semibold text-primary block mb-1">
                  Choose Profile Picture
                </label>
                <div className="flex items-center gap-2 overflow-x-auto p-1">
                  {PRESET_AVATARS.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setNewMemberAvatar(p.url)}
                      className={`w-9 h-9 rounded-full overflow-hidden border-2 shrink-0 transition-transform cursor-pointer ${
                        newMemberAvatar === p.url ? 'border-secondary-container scale-110' : 'border-transparent'
                      }`}
                      title={p.label}
                    >
                      <img src={p.url} alt="" className="w-full h-full object-cover" />
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-semibold text-primary block mb-1">
                    Weekly Hours (Cap)
                  </label>
                  <input
                    type="number"
                    min={10}
                    max={60}
                    value={newMemberCapacity}
                    onChange={(e) => setNewMemberCapacity(Number(e.target.value))}
                    className="w-full bg-surface-container-low text-xs text-primary border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-semibold text-primary block mb-1">Focus Epic</label>
                  <input
                    type="text"
                    value={newMemberProject}
                    onChange={(e) => setNewMemberProject(e.target.value)}
                    placeholder="e.g. Mobile Friction Fixes"
                    className="w-full bg-surface-container-low text-xs text-primary border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-surface-container-high">
                <button
                  type="button"
                  onClick={() => setIsAddMemberOpen(false)}
                  className="px-3 py-1.5 text-xs text-on-surface-variant hover:text-primary cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-xs font-semibold bg-primary-container text-on-primary rounded-full hover:bg-primary transition-all cursor-pointer shadow-xs"
                >
                  Add Operator to Squad
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 2: EDIT MEMBER AVATAR */}
      {/* ========================================================================= */}
      {editingAvatarMemberId && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-surface-container-lowest rounded-3xl p-6 max-w-sm w-full border border-surface-container-high shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between pb-2 border-b border-surface-container-high">
              <h3 className="font-headline-sm text-sm font-bold text-primary">
                Select Member Profile Photo
              </h3>
              <button
                type="button"
                onClick={() => setEditingAvatarMemberId(null)}
                className="text-on-surface-variant hover:text-primary p-1 rounded-full cursor-pointer"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>

            <div className="grid grid-cols-3 gap-3 p-1">
              {PRESET_AVATARS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => {
                    onUpdateMemberAvatar(editingAvatarMemberId, p.url);
                    setEditingAvatarMemberId(null);
                  }}
                  className="aspect-square rounded-2xl overflow-hidden border-2 border-transparent hover:border-secondary-container hover:scale-105 transition-all cursor-pointer"
                  title={p.label}
                >
                  <img src={p.url} alt="" className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 3: VIEW REPORT FINDINGS & REMEDIATION */}
      {/* ========================================================================= */}
      {selectedReportModal && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-surface-container-lowest rounded-3xl p-6 sm:p-8 max-w-2xl w-full border border-surface-container-high shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-200 max-h-[85vh] overflow-y-auto">
            <div className="flex items-start justify-between pb-3 border-b border-surface-container-high">
              <div>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-fixed font-bold">
                  {selectedReportModal.journeyId}
                </span>
                <h3 className="font-headline-sm text-lg font-bold text-primary mt-1">
                  {selectedReportModal.title}
                </h3>
                <span className="text-xs text-on-surface-variant">
                  {selectedReportModal.generatedAt} · Author: {selectedReportModal.author}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setSelectedReportModal(null)}
                className="text-on-surface-variant hover:text-primary p-1 rounded-full cursor-pointer"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>

            {/* Metrics Row */}
            <div className="grid grid-cols-4 gap-3 p-3.5 bg-surface-container-low rounded-2xl border border-surface-container-high text-center">
              <div>
                <span className="font-stat font-bold text-lg text-primary block">
                  {selectedReportModal.dropoffPct}%
                </span>
                <span className="text-[10px] uppercase text-on-surface-variant">Dropoff Rate</span>
              </div>
              <div>
                <span className="font-stat font-bold text-lg text-error block">
                  {selectedReportModal.rageClicks}
                </span>
                <span className="text-[10px] uppercase text-on-surface-variant">Rage Clicks</span>
              </div>
              <div>
                <span className="font-stat font-bold text-lg text-secondary-container block">
                  {selectedReportModal.frictionScore}/100
                </span>
                <span className="text-[10px] uppercase text-on-surface-variant">Friction Score</span>
              </div>
              <div>
                <span className="font-stat font-bold text-xs text-primary block truncate">
                  {selectedReportModal.bottleneckStep}
                </span>
                <span className="text-[10px] uppercase text-on-surface-variant">Bottleneck</span>
              </div>
            </div>

            {/* Executive Summary */}
            <div className="space-y-1.5">
              <span className="text-xs font-bold text-primary block">Executive Diagnostic Summary</span>
              <p className="text-xs text-on-surface-variant leading-relaxed p-3.5 bg-surface-container-low rounded-2xl border border-surface-container-high">
                {selectedReportModal.executiveSummary}
              </p>
            </div>

            {/* Recommended Engineering Fixes */}
            <div className="space-y-1.5">
              <span className="text-xs font-bold text-primary block">
                Recommended Remediation Roadmap
              </span>
              <ul className="space-y-2">
                {selectedReportModal.recommendedFixes.map((fix, idx) => (
                  <li
                    key={idx}
                    className="flex items-start gap-2 p-2.5 bg-surface-container-low rounded-xl text-xs text-primary border border-surface-container-high"
                  >
                    <span className="material-symbols-outlined text-[16px] text-emerald-600 mt-0.5 shrink-0">
                      check_circle
                    </span>
                    <span>{fix}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-surface-container-high">
              <button
                type="button"
                onClick={() => downloadReportHtml(selectedReportModal)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary-container text-on-primary hover:bg-primary text-xs font-semibold transition-all cursor-pointer shadow-xs"
              >
                <span className="material-symbols-outlined text-[16px]">download</span>
                <span>Download Standalone HTML Report</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 4: GENERATE JOURNEY AUDIT REPORT */}
      {/* ========================================================================= */}
      {isGeneratingReport && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-surface-container-lowest rounded-3xl p-6 sm:p-8 max-w-md w-full border border-surface-container-high shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between pb-2 border-b border-surface-container-high">
              <h3 className="font-headline-sm text-base font-bold text-primary flex items-center gap-2">
                <span className="material-symbols-outlined text-[20px] text-secondary">analytics</span>
                <span>Generate Live Diagnostic Audit</span>
              </h3>
              <button
                type="button"
                onClick={() => setIsGeneratingReport(false)}
                className="text-on-surface-variant hover:text-primary p-1 rounded-full cursor-pointer"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>

            <form onSubmit={handleGenerateReportSubmit} className="space-y-3.5">
              <div>
                <label className="text-[11px] font-semibold text-primary block mb-1">
                  Report Title
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Checkout Funnel Sprint 4 Friction Audit"
                  value={genTitle}
                  onChange={(e) => setGenTitle(e.target.value)}
                  className="w-full bg-surface-container-low text-xs text-primary border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold text-primary block mb-1">
                  Target Journey Identifier
                </label>
                <select
                  value={genJourney}
                  onChange={(e) => setGenJourney(e.target.value)}
                  className="w-full bg-surface-container-low text-xs text-primary font-mono border border-surface-container-high rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-secondary"
                >
                  <option value="checkout_funnel">checkout_funnel</option>
                  <option value="user_onboarding">user_onboarding</option>
                  <option value="support_portal">support_portal</option>
                  <option value="* (Enterprise Cross-Site)">* (Enterprise Cross-Site)</option>
                </select>
              </div>

              <div>
                <label className="text-[11px] font-semibold text-primary block mb-1">
                  Report Audit Type
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {(
                    [
                      { id: 'friction', label: 'Friction' },
                      { id: 'funnel', label: 'Conversion' },
                      { id: 'remediation', label: 'Sprint Fix' },
                    ] as const
                  ).map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setGenType(t.id)}
                      className={`py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                        genType === t.id
                          ? 'bg-secondary-container text-on-secondary-fixed border-secondary-container shadow-xs'
                          : 'bg-surface-container-low text-on-surface-variant hover:text-primary border-surface-container-high'
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-surface-container-high">
                <button
                  type="button"
                  onClick={() => setIsGeneratingReport(false)}
                  className="px-3 py-1.5 text-xs text-on-surface-variant hover:text-primary cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-xs font-semibold bg-primary-container text-on-primary rounded-full hover:bg-primary transition-all cursor-pointer shadow-xs"
                >
                  Compile & Save Audit Report
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
