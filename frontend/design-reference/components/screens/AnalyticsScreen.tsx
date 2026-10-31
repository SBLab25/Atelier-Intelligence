import React, { useState } from 'react';
import { Task } from '../../types';

interface AnalyticsScreenProps {
  tasks?: Task[];
  onNewTask?: () => void;
}

export const AnalyticsScreen: React.FC<AnalyticsScreenProps> = ({ tasks, onNewTask }) => {
  const [activeSubTab, setActiveSubTab] = useState<'overview' | 'journey' | 'friction' | 'insights' | 'reports'>('overview');
  const [platform, setPlatform] = useState<'all' | 'web' | 'app' | 'checkout'>('all');
  const [timeframe, setTimeframe] = useState<'7D' | '30D' | '90D'>('30D');
  const [insightFilter, setInsightFilter] = useState<'high' | 'all' | 'archived'>('high');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showReplayModal, setShowReplayModal] = useState<string | null>(null);
  const [showSequenceModal, setShowSequenceModal] = useState(false);
  const [selectedInsight, setSelectedInsight] = useState<string | null>(null);

  const handleRunAnalysis = () => {
    setIsAnalyzing(true);
    setTimeout(() => {
      setIsAnalyzing(false);
    }, 1200);
  };

  return (
    <div className="flex flex-col w-full">
      {/* Radial Sunlit Daylight Shimmer & Floating Tactile Canvas Layer */}
      <div className="relative w-full px-gutter md:px-margin-desktop py-space-lg flex flex-col gap-space-xl overflow-hidden">
        {/* Ambient daylight glow wash in background corner */}
        <div className="absolute top-0 right-1/4 w-[580px] h-[340px] pointer-events-none rounded-full blur-3xl opacity-35 bg-gradient-to-br from-secondary-container via-surface-container-high to-transparent"></div>
        <div className="absolute top-40 left-10 w-[360px] h-[360px] pointer-events-none rounded-full blur-3xl opacity-20 bg-gradient-to-tr from-tertiary-fixed to-transparent"></div>

        {/* Top Bento Meta Header: Sub-Navigation + Global Scope Selectors */}
        <section className="relative z-10 flex flex-col xl:flex-row xl:items-center justify-between gap-space-md">
          {/* Left Pill Sub-Navigation Bar */}
          <div className="flex items-center flex-nowrap overflow-x-auto gap-1 p-1.5 bg-surface-container-lowest rounded-full shadow-[0_1px_3px_rgba(40,30,20,0.06),0_16px_36px_-12px_rgba(180,160,140,0.12)] max-w-full">
            <button
              onClick={() => setActiveSubTab('overview')}
              className={`font-title-md text-title-md px-space-md py-2 rounded-full transition-all duration-200 flex items-center gap-space-xs whitespace-nowrap shrink-0 ${
                activeSubTab === 'overview'
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
              className={`font-title-md text-title-md px-space-md py-2 rounded-full transition-all duration-200 whitespace-nowrap shrink-0 ${
                activeSubTab === 'journey'
                  ? 'bg-primary-container text-on-primary shadow-sm'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
              type="button"
            >
              Journey
            </button>
            <button
              onClick={() => setActiveSubTab('friction')}
              className={`font-title-md text-title-md px-space-md py-2 rounded-full transition-all duration-200 flex items-center gap-space-xs whitespace-nowrap shrink-0 ${
                activeSubTab === 'friction'
                  ? 'bg-primary-container text-on-primary shadow-sm'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
              type="button"
            >
              <span>Friction</span>
              <span className="bg-tertiary-container text-tertiary-fixed font-label-sm text-label-sm px-2 py-0.5 rounded-full font-semibold">
                2 live
              </span>
            </button>
            <button
              onClick={() => setActiveSubTab('insights')}
              className={`font-title-md text-title-md px-space-md py-2 rounded-full transition-all duration-200 whitespace-nowrap shrink-0 ${
                activeSubTab === 'insights'
                  ? 'bg-primary-container text-on-primary shadow-sm'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
              type="button"
            >
              Insights
            </button>
            <button
              onClick={() => setActiveSubTab('reports')}
              className={`font-title-md text-title-md px-space-md py-2 rounded-full transition-all duration-200 whitespace-nowrap shrink-0 ${
                activeSubTab === 'reports'
                  ? 'bg-primary-container text-on-primary shadow-sm'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
              type="button"
            >
              Reports
            </button>
          </div>

          {/* Right Scope & Execution Controls */}
          <div className="flex items-center flex-wrap gap-space-sm">
            {/* Date Range Tactile Capsule */}
            <div className="flex items-center gap-space-xs bg-surface-container-lowest px-space-md py-2 rounded-full shadow-[0_1px_3px_rgba(40,30,20,0.05)] cursor-pointer hover:bg-surface-container-low transition-colors">
              <span className="material-symbols-outlined text-[18px] text-on-surface-variant">calendar_today</span>
              <span className="font-label-md text-label-md text-on-surface">Oct 12 – Nov 11, 2024</span>
              <span className="material-symbols-outlined text-[16px] text-on-surface-variant">expand_more</span>
            </div>

            {/* Platform Switcher Pill */}
            <div className="hidden sm:flex items-center bg-surface-container-high/60 p-1 rounded-full">
              <button
                onClick={() => setPlatform('all')}
                className={`font-label-md text-label-md px-space-md py-1.5 rounded-full transition-all ${
                  platform === 'all'
                    ? 'bg-surface-container-lowest text-on-surface shadow-sm font-semibold'
                    : 'text-on-surface-variant hover:text-on-surface'
                }`}
                type="button"
              >
                All Platforms
              </button>
              <button
                onClick={() => setPlatform('web')}
                className={`font-label-md text-label-md px-space-md py-1.5 rounded-full transition-all ${
                  platform === 'web'
                    ? 'bg-surface-container-lowest text-on-surface shadow-sm font-semibold'
                    : 'text-on-surface-variant hover:text-on-surface'
                }`}
                type="button"
              >
                Web
              </button>
              <button
                onClick={() => setPlatform('app')}
                className={`font-label-md text-label-md px-space-md py-1.5 rounded-full transition-all ${
                  platform === 'app'
                    ? 'bg-surface-container-lowest text-on-surface shadow-sm font-semibold'
                    : 'text-on-surface-variant hover:text-on-surface'
                }`}
                type="button"
              >
                App
              </button>
              <button
                onClick={() => setPlatform('checkout')}
                className={`font-label-md text-label-md px-space-md py-1.5 rounded-full transition-all ${
                  platform === 'checkout'
                    ? 'bg-surface-container-lowest text-on-surface shadow-sm font-semibold'
                    : 'text-on-surface-variant hover:text-on-surface'
                }`}
                type="button"
              >
                Checkout
              </button>
            </div>

            {/* Run Analysis Pill Accent Button */}
            <button
              onClick={handleRunAnalysis}
              disabled={isAnalyzing}
              className="bg-secondary-container hover:bg-secondary-fixed text-on-secondary-fixed font-title-md text-title-md px-space-lg py-2 rounded-full shadow-sm hover:shadow transition-all duration-200 flex items-center gap-space-xs group disabled:opacity-75"
              type="button"
            >
              <span
                className={`material-symbols-outlined text-[18px] transition-transform ${
                  isAnalyzing ? 'animate-spin' : 'group-hover:rotate-45'
                }`}
              >
                {isAnalyzing ? 'sync' : 'query_stats'}
              </span>
              <span>{isAnalyzing ? 'Analyzing...' : 'Run Analysis'}</span>
            </button>
          </div>
        </section>

        {/* Bento Key Metrics Grid (4 Tactile Modules) */}
        <section className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-space-lg">
          {/* Metric 1: Total Sessions */}
          <div className="relative bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between group hover:-translate-y-0.5 transition-transform duration-200">
            <div className="flex items-center justify-between mb-space-sm">
              <span className="font-label-md text-label-md text-on-surface-variant">Total Sessions</span>
              <span className="inline-flex items-center gap-0.5 font-label-sm text-label-sm bg-surface-container-high text-on-surface px-2 py-0.5 rounded-full">
                <span className="material-symbols-outlined text-[14px] text-secondary">trending_up</span>
                +12.4%
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-space-md my-space-xs">
              <span className="font-stat-metric text-stat-metric text-primary tracking-tight">142,850</span>
              <span className="font-label-sm text-label-sm text-on-surface-variant">7.8k / day</span>
            </div>
            {/* Tactile Bar Sparkline */}
            <div className="pt-space-sm flex items-end gap-1.5 h-10 w-full">
              <div className="flex-1 bg-surface-container-high rounded-full h-[40%]"></div>
              <div className="flex-1 bg-surface-container-high rounded-full h-[65%]"></div>
              <div className="flex-1 bg-surface-container-high rounded-full h-[55%]"></div>
              <div className="flex-1 bg-surface-container-high rounded-full h-[80%]"></div>
              <div className="flex-1 bg-surface-container-high rounded-full h-[45%]"></div>
              <div className="flex-1 bg-secondary-container rounded-full h-[95%]"></div>
              <div className="flex-1 bg-primary-container rounded-full h-[70%]"></div>
            </div>
          </div>

          {/* Metric 2: Avg Friction Score */}
          <div className="relative bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between group hover:-translate-y-0.5 transition-transform duration-200">
            <div className="flex items-center justify-between mb-space-sm">
              <span className="font-label-md text-label-md text-on-surface-variant">Avg. Friction Score</span>
              <span className="inline-flex items-center gap-0.5 font-label-sm text-label-sm bg-surface-container-high text-secondary px-2 py-0.5 rounded-full">
                <span className="material-symbols-outlined text-[14px]">trending_down</span>
                -2.1%
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-space-md my-space-xs">
              <div className="flex items-baseline gap-1">
                <span className="font-stat-metric text-stat-metric text-primary tracking-tight">3.8</span>
                <span className="font-label-md text-label-md text-on-surface-variant">/ 10</span>
              </div>
              <span className="font-label-sm text-label-sm uppercase tracking-wider text-secondary-fixed-dim bg-on-secondary-fixed/5 px-2 py-0.5 rounded-full">
                Optimal Range
              </span>
            </div>
            {/* Status Progress Rail */}
            <div className="pt-space-sm flex flex-col gap-1.5 w-full">
              <div className="w-full h-2 rounded-full bg-surface-container-high overflow-hidden flex">
                <div className="h-full bg-secondary-container rounded-l-full" style={{ width: '38%' }}></div>
                <div className="h-full bg-surface-container-highest" style={{ width: '42%' }}></div>
                <div className="h-full bg-tertiary-container rounded-r-full" style={{ width: '20%' }}></div>
              </div>
              <div className="flex justify-between font-label-sm text-label-sm text-on-surface-variant">
                <span>Low (62%)</span>
                <span>Spike (18%)</span>
              </div>
            </div>
          </div>

          {/* Metric 3: Critical Journey Steps */}
          <div className="relative bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between group hover:-translate-y-0.5 transition-transform duration-200">
            <div className="flex items-center justify-between mb-space-sm">
              <span className="font-label-md text-label-md text-on-surface-variant">Monitored Funnel Steps</span>
              <span className="font-label-sm text-label-sm bg-surface-container-high text-on-surface-variant px-2 py-0.5 rounded-full">
                Stable
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-space-md my-space-xs">
              <div className="flex items-baseline gap-1.5">
                <span className="font-stat-metric text-stat-metric text-primary tracking-tight">12</span>
                <span className="font-label-md text-label-md text-on-surface-variant">/ 20 Steps</span>
              </div>
              <span className="font-label-sm text-label-sm text-on-tertiary-container bg-error-container/40 px-2 py-0.5 rounded-full font-semibold">
                2 Critical
              </span>
            </div>
            {/* Multi-segment Striped Rail */}
            <div className="pt-space-sm flex flex-col gap-1.5 w-full">
              <div className="w-full h-2 rounded-full bg-surface-container-high flex overflow-hidden">
                <div className="h-full bg-primary-container" style={{ width: '60%' }}></div>
                <div className="h-full bg-tertiary-container" style={{ width: '15%' }}></div>
                <div className="h-full bg-surface-container-highest" style={{ width: '25%' }}></div>
              </div>
              <div className="flex justify-between font-label-sm text-label-sm text-on-surface-variant">
                <span>Pass (10)</span>
                <span className="text-tertiary-container font-semibold">Flagged (2)</span>
              </div>
            </div>
          </div>

          {/* Metric 4: Total Synthesized Insights */}
          <div className="relative bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between group hover:-translate-y-0.5 transition-transform duration-200">
            <div className="flex items-center justify-between mb-space-sm">
              <span className="font-label-md text-label-md text-on-surface-variant">Intelligence Insights</span>
              <span className="font-label-sm text-label-sm bg-secondary-container text-on-secondary-fixed font-semibold px-2 py-0.5 rounded-full">
                +5 New
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-space-md my-space-xs">
              <span className="font-stat-metric text-stat-metric text-primary tracking-tight">86</span>
              <span className="font-label-sm text-label-sm text-on-surface-variant">3 Actionable</span>
            </div>
            {/* Synthesized user cohort cluster mini-preview */}
            <div className="pt-space-sm flex items-center justify-between">
              <div className="flex items-center -space-x-2">
                <div className="w-7 h-7 rounded-full bg-surface-container-high border-2 border-surface-container-lowest flex items-center justify-center text-primary font-label-sm text-label-sm font-semibold">
                  US
                </div>
                <div className="w-7 h-7 rounded-full bg-secondary-container border-2 border-surface-container-lowest flex items-center justify-center text-on-secondary-fixed font-label-sm text-label-sm font-semibold">
                  EU
                </div>
                <div className="w-7 h-7 rounded-full bg-primary-container border-2 border-surface-container-lowest flex items-center justify-center text-on-primary font-label-sm text-label-sm font-semibold">
                  AP
                </div>
                <div className="w-7 h-7 rounded-full bg-surface-container-highest border-2 border-surface-container-lowest flex items-center justify-center font-label-sm text-label-sm text-on-surface-variant">
                  +6
                </div>
              </div>
              <span className="font-label-sm text-label-sm text-on-surface-variant">4 Cohorts</span>
            </div>
          </div>
        </section>

        {/* Bento Primary Analytics & Graph Row (Asymmetric Split 7 / 5) */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-stretch">
          {/* Primary Wave Chart Card: Friction Trends vs. Rage Clicks (7 Cols) */}
          <div className="lg:col-span-7 bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between">
            {/* Card Header with Timeframe Toggles */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm pb-space-md">
              <div>
                <div className="flex items-center gap-space-xs">
                  <h2 className="font-headline-sm text-headline-sm text-primary">Friction Trends vs. Rage Clicks</h2>
                  <span className="font-label-sm text-label-sm bg-surface-container-high px-2 py-0.5 rounded-full text-on-surface-variant font-medium">
                    r = 0.88
                  </span>
                </div>
                <p className="font-body-sm text-body-sm text-on-surface-variant mt-0.5">
                  Correlation index across active user workflows
                </p>
              </div>
              <div className="flex items-center gap-1 bg-surface-container-low p-1 rounded-full self-start sm:self-auto">
                {(['7D', '30D', '90D'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTimeframe(t)}
                    className={`font-label-sm text-label-sm px-3 py-1 rounded-full transition-colors ${
                      timeframe === t
                        ? 'bg-primary-container text-on-primary shadow-sm font-medium'
                        : 'text-on-surface-variant hover:text-on-surface'
                    }`}
                    type="button"
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            {/* Legend Pill Indicators */}
            <div className="flex items-center gap-space-md pb-space-sm">
              <div className="flex items-center gap-1.5 font-label-sm text-label-sm text-on-surface">
                <div className="w-3 h-1.5 rounded-full bg-primary-container"></div>
                <span>Friction Severity Score</span>
              </div>
              <div className="flex items-center gap-1.5 font-label-sm text-label-sm text-on-surface">
                <div className="w-3 h-1.5 rounded-full bg-secondary-container"></div>
                <span>Rage Clicks Volume</span>
              </div>
            </div>

            {/* Smooth Area SVG Chart Visual with Peak Frustration Pin Tooltip */}
            <div className="relative w-full h-64 sm:h-72 my-space-xs">
              {/* Ambient Tooltip Pin Callout on Spike */}
              <div className="absolute top-8 left-[64%] -translate-x-1/2 z-20 bg-primary-container text-on-primary p-2.5 rounded-xl shadow-lg flex flex-col gap-0.5 pointer-events-none">
                <div className="flex items-center gap-1.5 font-label-sm text-label-sm text-secondary-container">
                  <span className="w-1.5 h-1.5 rounded-full bg-secondary-container animate-ping"></span>
                  <span>Nov 02 Spike Correlation</span>
                </div>
                <div className="font-label-md text-label-md text-on-primary font-semibold">
                  4.2 Friction · 318 Rage Clicks
                </div>
                <div className="font-body-sm text-body-sm text-on-primary-container">
                  Checkout Step 1 bottleneck
                </div>
              </div>

              {/* Inline Vector SVG Graphic Area Chart */}
              <svg className="w-full h-full overflow-visible" fill="none" preserveAspectRatio="none" viewBox="0 0 700 280">
                <defs>
                  <linearGradient id="primaryAreaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#1e1e22" stopOpacity="0.16"></stop>
                    <stop offset="100%" stopColor="#1e1e22" stopOpacity="0.0"></stop>
                  </linearGradient>
                  <linearGradient id="amberAreaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#fdbb45" stopOpacity="0.28"></stop>
                    <stop offset="100%" stopColor="#fdbb45" stopOpacity="0.0"></stop>
                  </linearGradient>
                </defs>

                {/* Subtle Gridlines */}
                <line stroke="#eae8e5" strokeDasharray="4 4" strokeWidth="1" x1="0" x2="700" y1="50" y2="50"></line>
                <line stroke="#eae8e5" strokeDasharray="4 4" strokeWidth="1" x1="0" x2="700" y1="120" y2="120"></line>
                <line stroke="#eae8e5" strokeDasharray="4 4" strokeWidth="1" x1="0" x2="700" y1="190" y2="190"></line>

                {/* Amber / Secondary Fill & Line: Rage Clicks */}
                <path
                  d="M 0 210 Q 70 200, 140 180 T 280 150 T 420 160 T 450 60 T 520 140 T 630 165 T 700 140 L 700 260 L 0 260 Z"
                  fill="url(#amberAreaGrad)"
                ></path>
                <path
                  d="M 0 210 Q 70 200, 140 180 T 280 150 T 420 160 T 450 60 T 520 140 T 630 165 T 700 140"
                  fill="none"
                  stroke="#fdbb45"
                  strokeLinecap="round"
                  strokeWidth="3"
                ></path>

                {/* Primary Fill & Line: Friction Score */}
                <path
                  d="M 0 170 Q 70 160, 140 140 T 280 120 T 420 115 T 450 45 T 520 110 T 630 130 T 700 120 L 700 260 L 0 260 Z"
                  fill="url(#primaryAreaGrad)"
                ></path>
                <path
                  d="M 0 170 Q 70 160, 140 140 T 280 120 T 420 115 T 450 45 T 520 110 T 630 130 T 700 120"
                  fill="none"
                  stroke="#1e1e22"
                  strokeLinecap="round"
                  strokeWidth="2.5"
                ></path>

                {/* Spike Marker Circle Rings */}
                <circle cx="450" cy="45" fill="#1e1e22" r="5"></circle>
                <circle cx="450" cy="45" r="11" stroke="#1e1e22" strokeOpacity="0.3" strokeWidth="1.5"></circle>
                <circle cx="450" cy="60" fill="#fdbb45" r="5"></circle>
                <circle cx="450" cy="60" r="11" stroke="#fdbb45" strokeOpacity="0.5" strokeWidth="1.5"></circle>
              </svg>
            </div>

            {/* Dynamic Timeline Labels */}
            <div className="flex justify-between font-label-sm text-label-sm text-on-surface-variant pt-space-xs border-t border-surface-container-high/40">
              <span>Oct 14</span>
              <span>Oct 21</span>
              <span>Oct 28</span>
              <span className="text-primary font-semibold">Nov 02 (Spike)</span>
              <span>Nov 08</span>
              <span>Nov 11</span>
            </div>

            {/* Bottom Tactile Highlights Strip */}
            <div className="mt-space-md pt-space-sm grid grid-cols-1 sm:grid-cols-2 gap-space-sm">
              <div className="bg-surface-container-low px-space-md py-space-sm rounded-full flex items-center justify-between">
                <span className="font-body-sm text-body-sm text-on-surface-variant">Peak Frustration Window:</span>
                <span className="font-label-md text-label-md text-primary font-semibold">Checkout Step 1 (+18%)</span>
              </div>
              <div className="bg-surface-container-low px-space-md py-space-sm rounded-full flex items-center justify-between">
                <span className="font-body-sm text-body-sm text-on-surface-variant">Mean Resolution Velocity:</span>
                <span className="font-label-md text-label-md text-secondary font-semibold">1.8 Days to Normal</span>
              </div>
            </div>
          </div>

          {/* Main Right Funnel Card: Top Funnel Drop-offs (5 Cols) */}
          <div className="lg:col-span-5 bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-space-xs">
                <h2 className="font-headline-sm text-headline-sm text-primary">Top Funnel Drop-offs</h2>
                <button
                  onClick={() => setShowSequenceModal(true)}
                  aria-label="Expand Funnel"
                  className="w-8 h-8 rounded-full bg-surface-container-high hover:bg-surface-container-highest flex items-center justify-center transition-colors"
                  type="button"
                >
                  <span className="material-symbols-outlined text-[18px] text-on-surface">north_east</span>
                </button>
              </div>
              <p className="font-body-sm text-body-sm text-on-surface-variant mb-space-md">
                Conversion retention across the core 4 checkout stages
              </p>

              {/* Funnel Stages Flow */}
              <div className="flex flex-col gap-space-md">
                {/* Stage 1 */}
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between font-label-md text-label-md">
                    <span className="text-on-surface font-semibold">1. Landing Page Entry</span>
                    <span className="text-on-surface font-semibold">
                      84% <span className="font-body-sm text-body-sm text-on-surface-variant font-normal">(120k users)</span>
                    </span>
                  </div>
                  <div className="w-full h-3 rounded-full bg-surface-container-high overflow-hidden">
                    <div className="h-full bg-primary-container rounded-full" style={{ width: '84%' }}></div>
                  </div>
                </div>

                {/* Stage 2 */}
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between font-label-md text-label-md">
                    <span className="text-on-surface font-semibold">2. Product Configurator</span>
                    <span className="text-on-surface font-semibold">
                      52% <span className="font-body-sm text-body-sm text-on-surface-variant font-normal">(62.4k users)</span>
                    </span>
                  </div>
                  <div className="w-full h-3 rounded-full bg-surface-container-high overflow-hidden">
                    <div className="h-full bg-primary-container rounded-full" style={{ width: '52%' }}></div>
                  </div>
                </div>

                {/* Stage 3 (Critical Drop Stage) */}
                <div className="flex flex-col gap-1.5 bg-surface-container-low p-space-sm rounded-xl">
                  <div className="flex items-center justify-between font-label-md text-label-md">
                    <span className="text-on-surface font-semibold flex items-center gap-1.5">
                      <span>3. Checkout (Step 1)</span>
                      <span className="font-label-sm text-label-sm bg-tertiary-container text-tertiary-fixed px-2 py-0.5 rounded-full font-bold uppercase">
                        Critical Drop
                      </span>
                    </span>
                    <span className="text-tertiary-container font-semibold">
                      21% <span className="font-body-sm text-body-sm text-on-surface-variant font-normal">(13.1k users)</span>
                    </span>
                  </div>
                  <div className="w-full h-3 rounded-full bg-surface-container-high overflow-hidden">
                    <div className="h-full bg-tertiary-container rounded-full" style={{ width: '21%' }}></div>
                  </div>
                </div>

                {/* Stage 4 */}
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between font-label-md text-label-md">
                    <span className="text-on-surface font-semibold">4. Payment Auth &amp; Completion</span>
                    <span className="text-on-surface font-semibold">
                      18% <span className="font-body-sm text-body-sm text-on-surface-variant font-normal">(11.2k users)</span>
                    </span>
                  </div>
                  <div className="w-full h-3 rounded-full bg-surface-container-high overflow-hidden">
                    <div className="h-full bg-secondary-container rounded-full" style={{ width: '18%' }}></div>
                  </div>
                </div>
              </div>
            </div>

            {/* In-card Contextual Warning Module */}
            <div className="mt-space-md p-space-md bg-surface-container-high rounded-lg flex flex-col gap-space-sm">
              <div className="flex items-start gap-space-sm">
                <span className="material-symbols-outlined text-secondary text-[22px] flex-shrink-0 mt-0.5">warning</span>
                <div className="flex flex-col">
                  <div className="font-title-md text-title-md text-primary font-semibold">Hidden Shipping Friction Trigger</div>
                  <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed">
                    67% of Step 1 dropouts occur immediately upon calculating dynamic parcel rates. Moving shipping estimate upfront is projected to recover +8.4% conversion.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowSequenceModal(true)}
                className="self-end inline-flex items-center gap-1 font-label-md text-label-md text-primary font-semibold hover:text-secondary transition-colors"
                type="button"
              >
                <span>View journey sequence</span>
                <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
              </button>
            </div>
          </div>
        </section>

        {/* Bento Deep-Dive: Friction Diagnostics & Journey Telemetry */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
          {/* Inverted Dark Bento Module: Friction Diagnostics Breakdown (5 Cols) */}
          <div className="lg:col-span-5 bg-primary-container text-on-primary rounded-lg p-space-lg shadow-xl flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-space-sm">
                <div className="flex items-center gap-space-xs">
                  <div className="w-2.5 h-2.5 rounded-full bg-secondary-container"></div>
                  <span className="font-label-md text-label-md text-on-primary-container uppercase tracking-wider">
                    Device Cohort Latency
                  </span>
                </div>
                <span className="font-label-sm text-label-sm text-on-primary bg-surface-container-high/15 px-2.5 py-1 rounded-full">
                  Real-time Telemetry
                </span>
              </div>
              <div className="my-space-md">
                <div className="font-headline-md text-headline-md text-on-primary">Platform Friction Index</div>
                <p className="font-body-sm text-body-sm text-on-primary-container mt-1">
                  Cross-referencing client runtimes with rendering bottlenecks
                </p>
              </div>

              {/* Micro-Dial / Radial Progress Row */}
              <div className="grid grid-cols-3 gap-space-sm py-space-sm">
                {/* Mobile WebKit Dial */}
                <div className="bg-surface-container-highest/10 p-space-sm rounded-xl flex flex-col items-center text-center">
                  <div className="relative w-14 h-14 flex items-center justify-center">
                    <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                      <path
                        className="text-surface-container-high/20"
                        d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="3"
                      ></path>
                      <path
                        className="text-secondary-container"
                        d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                        fill="none"
                        stroke="currentColor"
                        strokeDasharray="72, 100"
                        strokeLinecap="round"
                        strokeWidth="3"
                      ></path>
                    </svg>
                    <span className="absolute font-stat-metric text-stat-metric text-on-primary text-[15px]">72%</span>
                  </div>
                  <span className="font-label-sm text-label-sm text-on-primary mt-2">Mobile WebKit</span>
                  <span className="font-body-sm text-body-sm text-on-primary-container">4.8 Friction</span>
                </div>

                {/* Desktop Chrome Dial */}
                <div className="bg-surface-container-highest/10 p-space-sm rounded-xl flex flex-col items-center text-center">
                  <div className="relative w-14 h-14 flex items-center justify-center">
                    <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                      <path
                        className="text-surface-container-high/20"
                        d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="3"
                      ></path>
                      <path
                        className="text-on-primary"
                        d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                        fill="none"
                        stroke="currentColor"
                        strokeDasharray="28, 100"
                        strokeLinecap="round"
                        strokeWidth="3"
                      ></path>
                    </svg>
                    <span className="absolute font-stat-metric text-stat-metric text-on-primary text-[15px]">28%</span>
                  </div>
                  <span className="font-label-sm text-label-sm text-on-primary mt-2">Desktop Chrome</span>
                  <span className="font-body-sm text-body-sm text-on-primary-container">1.9 Friction</span>
                </div>

                {/* Native App Dial */}
                <div className="bg-surface-container-highest/10 p-space-sm rounded-xl flex flex-col items-center text-center">
                  <div className="relative w-14 h-14 flex items-center justify-center">
                    <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                      <path
                        className="text-surface-container-high/20"
                        d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="3"
                      ></path>
                      <path
                        className="text-secondary-fixed-dim"
                        d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                        fill="none"
                        stroke="currentColor"
                        strokeDasharray="14, 100"
                        strokeLinecap="round"
                        strokeWidth="3"
                      ></path>
                    </svg>
                    <span className="absolute font-stat-metric text-stat-metric text-on-primary text-[15px]">14%</span>
                  </div>
                  <span className="font-label-sm text-label-sm text-on-primary mt-2">Native App</span>
                  <span className="font-body-sm text-body-sm text-on-primary-container">0.9 Friction</span>
                </div>
              </div>
            </div>

            {/* Terminal Status Pill Output */}
            <div className="mt-space-md p-space-sm bg-surface-container-highest/5 rounded-full flex items-center justify-between">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-secondary-container text-[18px]">bolt</span>
                <span className="font-label-sm text-label-sm text-on-primary-container">DOM Hydration: 380ms (iOS 17.5)</span>
              </div>
              <span className="font-label-sm text-label-sm text-secondary-container font-mono">OK-104</span>
            </div>
          </div>

          {/* Tactile Journey Path Micro-Module (7 Cols) */}
          <div className="lg:col-span-7 bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-space-sm">
                <div>
                  <h2 className="font-headline-sm text-headline-sm text-primary">High-Friction Journey Trajectories</h2>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">Top multi-touch step sequences leading to abrupt user exit</p>
                </div>
                <button
                  onClick={() => setShowSequenceModal(true)}
                  className="font-label-sm text-label-sm bg-surface-container-high hover:bg-surface-container-highest text-on-surface px-3 py-1 rounded-full transition-colors"
                  type="button"
                >
                  Filter by Persona
                </button>
              </div>

              {/* Micro Journey Flow Sequence 1 */}
              <div className="space-y-space-md mt-space-md">
                <div className="p-space-md rounded-lg bg-surface-container-low flex flex-col gap-space-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-title-md text-title-md text-primary font-semibold">Path A: Cart Abandonment Loop</span>
                    <span className="font-label-sm text-label-sm bg-error-container text-on-error-container font-semibold px-2 py-0.5 rounded-full">
                      34.2k Sessions affected
                    </span>
                  </div>

                  {/* Flow Sequence Nodes */}
                  <div className="flex items-center flex-wrap gap-2 pt-1">
                    <div className="bg-surface-container-lowest px-space-sm py-1 rounded-full text-primary font-label-md text-label-md flex items-center gap-1 shadow-sm">
                      <span className="material-symbols-outlined text-[14px] text-on-surface-variant">shopping_cart</span>
                      <span>Review Bag</span>
                    </div>
                    <span className="material-symbols-outlined text-[16px] text-on-surface-variant">arrow_forward</span>
                    <div className="bg-surface-container-lowest px-space-sm py-1 rounded-full text-primary font-label-md text-label-md flex items-center gap-1 shadow-sm">
                      <span className="material-symbols-outlined text-[14px] text-on-surface-variant">pin_drop</span>
                      <span>Shipping Address</span>
                    </div>
                    <span className="material-symbols-outlined text-[16px] text-on-surface-variant">arrow_forward</span>
                    <div className="bg-tertiary-container text-tertiary-fixed px-space-sm py-1 rounded-full font-label-md text-label-md flex items-center gap-1 shadow-sm font-semibold">
                      <span className="material-symbols-outlined text-[14px]">error</span>
                      <span>Promo Auto-Validator</span>
                    </div>
                    <span className="material-symbols-outlined text-[16px] text-on-surface-variant">arrow_forward</span>
                    <div className="bg-surface-container-high text-on-surface-variant px-space-sm py-1 rounded-full font-label-md text-label-md">
                      Abrupt Drop (88%)
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-1 font-body-sm text-body-sm text-on-surface-variant">
                    <span>Mean latency: 4.8s at validator</span>
                    <button
                      onClick={() => setShowReplayModal('Path A (Cart Abandonment Loop)')}
                      className="text-secondary font-semibold hover:underline"
                    >
                      Replay 12 anonymized sessions ↗
                    </button>
                  </div>
                </div>

                {/* Micro Journey Flow Sequence 2 */}
                <div className="p-space-md rounded-lg bg-surface-container-low flex flex-col gap-space-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-title-md text-title-md text-primary font-semibold">Path B: Mobile Auth Loopback</span>
                    <span className="font-label-sm text-label-sm bg-surface-container-high text-on-surface font-semibold px-2 py-0.5 rounded-full">
                      18.6k Sessions affected
                    </span>
                  </div>

                  {/* Flow Sequence Nodes */}
                  <div className="flex items-center flex-wrap gap-2 pt-1">
                    <div className="bg-surface-container-lowest px-space-sm py-1 rounded-full text-primary font-label-md text-label-md flex items-center gap-1 shadow-sm">
                      <span className="material-symbols-outlined text-[14px] text-on-surface-variant">touch_app</span>
                      <span>1-Click Checkout</span>
                    </div>
                    <span className="material-symbols-outlined text-[16px] text-on-surface-variant">arrow_forward</span>
                    <div className="bg-secondary-container text-on-secondary-fixed px-space-sm py-1 rounded-full font-label-md text-label-md flex items-center gap-1 shadow-sm font-semibold">
                      <span className="material-symbols-outlined text-[14px]">lock_reset</span>
                      <span>Biometric Handshake</span>
                    </div>
                    <span className="material-symbols-outlined text-[16px] text-on-surface-variant">arrow_forward</span>
                    <div className="bg-surface-container-lowest px-space-sm py-1 rounded-full text-primary font-label-md text-label-md flex items-center gap-1 shadow-sm">
                      <span>Fallback Password</span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-1 font-body-sm text-body-sm text-on-surface-variant">
                    <span>Passkey fallback timeout triggered after 12s</span>
                    <button
                      onClick={() => setShowReplayModal('Path B (Mobile Auth Loopback)')}
                      className="text-secondary font-semibold hover:underline"
                    >
                      Replay 8 anonymized sessions ↗
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div className="pt-space-md flex items-center justify-between">
              <span className="font-label-sm text-label-sm text-on-surface-variant">Displaying 2 of 14 telemetry clusters</span>
              <button
                onClick={() => setShowSequenceModal(true)}
                className="font-label-md text-label-md text-primary font-semibold hover:text-secondary transition-colors"
                type="button"
              >
                Expand All Trajectories
              </button>
            </div>
          </div>
        </section>

        {/* Strategic Machine Intelligence Insights (Bento Expandable Feed) */}
        <section className="bg-surface-container-lowest rounded-lg p-space-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col gap-space-lg">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-md">
            <div>
              <div className="flex items-center gap-space-xs">
                <span className="w-2 h-2 rounded-full bg-secondary-container"></span>
                <h2 className="font-headline-sm text-headline-sm text-primary">Strategic Machine Intelligence Insights</h2>
              </div>
              <p className="font-body-sm text-body-sm text-on-surface-variant">
                Automated cognitive synthesis derived from current friction heuristics
              </p>
            </div>

            {/* Filter Chips Pill Group */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <button
                onClick={() => setInsightFilter('high')}
                className={`font-label-sm text-label-sm px-space-md py-1.5 rounded-full transition-all ${
                  insightFilter === 'high'
                    ? 'bg-primary-container text-on-primary shadow-sm'
                    : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface'
                }`}
                type="button"
              >
                High Priority First
              </button>
              <button
                onClick={() => setInsightFilter('all')}
                className={`font-label-sm text-label-sm px-space-md py-1.5 rounded-full transition-all ${
                  insightFilter === 'all'
                    ? 'bg-primary-container text-on-primary shadow-sm'
                    : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface'
                }`}
                type="button"
              >
                All Items
              </button>
              <button
                onClick={() => setInsightFilter('archived')}
                className={`font-label-sm text-label-sm px-space-md py-1.5 rounded-full transition-all ${
                  insightFilter === 'archived'
                    ? 'bg-primary-container text-on-primary shadow-sm'
                    : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface'
                }`}
                type="button"
              >
                Archive All
              </button>
            </div>
          </div>

          {/* Bento Cards Grid for 3 Machine Insights */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
            {/* Insight Card 1: Critical */}
            <div className="bg-surface-container-low p-space-md rounded-lg flex flex-col justify-between group hover:bg-surface-container transition-colors">
              <div>
                <div className="flex items-center justify-between mb-space-xs">
                  <span className="font-label-sm text-label-sm text-on-surface-variant">Detected 2h ago</span>
                  <span className="font-label-sm text-label-sm bg-tertiary-container text-tertiary-fixed px-2 py-0.5 rounded-full font-bold uppercase">
                    Critical
                  </span>
                </div>
                <h3 className="font-title-md text-title-md text-primary font-semibold mt-1">
                  Predictive Friction Spike: Checkout Redesign
                </h3>
                <p className="font-body-sm text-body-sm text-on-surface-variant mt-2 leading-relaxed">
                  New form layout introduces excessive viewport scrolling on devices with aspect ratio &lt; 19.5:9. Impacts 14% of mobile checkout traffic.
                </p>
              </div>
              <div className="mt-space-md pt-space-sm border-t border-surface-container-high flex items-center justify-between">
                <span className="font-label-sm text-label-sm text-on-surface-variant">
                  Confidence: <strong className="text-primary font-semibold">94%</strong>
                </span>
                <button
                  onClick={() => setSelectedInsight('Checkout Redesign Friction Analysis')}
                  className="w-8 h-8 rounded-full bg-surface-container-lowest hover:bg-surface-container-highest flex items-center justify-center transition-colors shadow-sm"
                  type="button"
                  aria-label="Inspect Insight 1"
                >
                  <span className="material-symbols-outlined text-[16px] text-primary">arrow_forward</span>
                </button>
              </div>
            </div>

            {/* Insight Card 2: Urgent */}
            <div className="bg-surface-container-low p-space-md rounded-lg flex flex-col justify-between group hover:bg-surface-container transition-colors">
              <div>
                <div className="flex items-center justify-between mb-space-xs">
                  <span className="font-label-sm text-label-sm text-on-surface-variant">Detected 5h ago</span>
                  <span className="font-label-sm text-label-sm bg-secondary-container text-on-secondary-fixed px-2 py-0.5 rounded-full font-bold uppercase">
                    Urgent
                  </span>
                </div>
                <h3 className="font-title-md text-title-md text-primary font-semibold mt-1">
                  API Latency Impacting Conversion
                </h3>
                <p className="font-body-sm text-body-sm text-on-surface-variant mt-2 leading-relaxed">
                  Response time from currency conversion endpoint degraded to 2.4s. Directly correlates with 68% of Rage Clicks registered in EU regions.
                </p>
              </div>
              <div className="mt-space-md pt-space-sm border-t border-surface-container-high flex items-center justify-between">
                <span className="font-label-sm text-label-sm text-on-surface-variant">
                  Confidence: <strong className="text-primary font-semibold">88%</strong>
                </span>
                <button
                  onClick={() => setSelectedInsight('API Latency Breakdown')}
                  className="w-8 h-8 rounded-full bg-surface-container-lowest hover:bg-surface-container-highest flex items-center justify-center transition-colors shadow-sm"
                  type="button"
                  aria-label="Inspect Insight 2"
                >
                  <span className="material-symbols-outlined text-[16px] text-primary">arrow_forward</span>
                </button>
              </div>
            </div>

            {/* Insight Card 3: Minor */}
            <div className="bg-surface-container-low p-space-md rounded-lg flex flex-col justify-between group hover:bg-surface-container transition-colors">
              <div>
                <div className="flex items-center justify-between mb-space-xs">
                  <span className="font-label-sm text-label-sm text-on-surface-variant">Detected 1d ago</span>
                  <span className="font-label-sm text-label-sm bg-surface-container-high text-on-surface-variant px-2 py-0.5 rounded-full font-semibold uppercase">
                    Minor
                  </span>
                </div>
                <h3 className="font-title-md text-title-md text-primary font-semibold mt-1">
                  New Persona Discovery: Casual Explorer
                </h3>
                <p className="font-body-sm text-body-sm text-on-surface-variant mt-2 leading-relaxed">
                  Cluster of 8,400 weekend visitors demonstrates zero checkout intent but high architectural search frequency. Potential audience for curated digest.
                </p>
              </div>
              <div className="mt-space-md pt-space-sm border-t border-surface-container-high flex items-center justify-between">
                <span className="font-label-sm text-label-sm text-on-surface-variant">
                  Confidence: <strong className="text-primary font-semibold">81%</strong>
                </span>
                <button
                  onClick={() => setSelectedInsight('Casual Explorer Persona Cluster')}
                  className="w-8 h-8 rounded-full bg-surface-container-lowest hover:bg-surface-container-highest flex items-center justify-center transition-colors shadow-sm"
                  type="button"
                  aria-label="Inspect Insight 3"
                >
                  <span className="material-symbols-outlined text-[16px] text-primary">arrow_forward</span>
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* Floating Tactile Action Bar / Footer Module */}
        <section className="p-space-lg bg-surface-container-lowest rounded-lg shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col md:flex-row md:items-center justify-between gap-space-md">
          <div className="flex items-center gap-space-md">
            <div className="w-12 h-12 rounded-full bg-secondary-container/20 flex items-center justify-center flex-shrink-0 text-secondary">
              <span className="material-symbols-outlined text-[24px]">description</span>
            </div>
            <div className="flex flex-col">
              <span className="font-title-md text-title-md text-primary font-semibold">
                Generate Full Tactical Analytics Report
              </span>
              <span className="font-body-sm text-body-sm text-on-surface-variant">
                Compiles 142k user sessions, funnel drops, and machine recommendations into an executive summary
              </span>
            </div>
          </div>
          <div className="flex items-center gap-space-sm self-end md:self-auto">
            <button
              onClick={() => alert('CSV schedule configured for Monday 9:00 AM.')}
              className="bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-label-md text-label-md px-space-lg py-2.5 rounded-full transition-colors"
              type="button"
            >
              Schedule CSV
            </button>
            <button
              onClick={() => alert('Compiling tactical report... PDF deck download initiated.')}
              className="bg-primary-container hover:bg-primary text-on-primary font-label-md text-label-md px-space-lg py-2.5 rounded-full shadow-sm hover:shadow transition-all duration-200 flex items-center gap-1.5"
              type="button"
            >
              <span className="material-symbols-outlined text-[18px]">download</span>
              <span>Download PDF Deck</span>
            </button>
          </div>
        </section>
      </div>

      {/* Interactive Modal: Anonymized Session Replay */}
      {showReplayModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
          <div className="w-full max-w-lg bg-surface-container-lowest rounded-xl p-6 shadow-2xl border border-outline-variant">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-secondary">videocam</span>
                <h3 className="font-title-md text-primary font-semibold">Telemetry Session Replay</h3>
              </div>
              <button
                onClick={() => setShowReplayModal(null)}
                className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center hover:bg-surface-container-highest"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>
            <p className="font-body-sm text-on-surface-variant mb-4">
              Viewing anonymized telemetry for <strong className="text-primary">{showReplayModal}</strong>. Captures multi-touch bottlenecks, input latencies, and exit triggers.
            </p>
            <div className="aspect-video bg-surface-container-highest rounded-lg flex flex-col items-center justify-center text-center p-4 border border-outline-variant/60">
              <span className="material-symbols-outlined text-[48px] text-secondary-container animate-pulse">
                play_circle
              </span>
              <span className="font-label-md text-primary mt-2">Simulating Telemetry Waveform</span>
              <span className="font-label-sm text-on-surface-variant">Step 3 promo validator timeout: 4.8s response lag</span>
            </div>
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setShowReplayModal(null)}
                className="bg-primary-container text-on-primary font-label-md px-4 py-2 rounded-full text-xs"
              >
                Close Replay
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Interactive Modal: Funnel Sequence Deep-Dive */}
      {showSequenceModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
          <div className="w-full max-w-xl bg-surface-container-lowest rounded-xl p-6 shadow-2xl border border-outline-variant">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-secondary">account_tree</span>
                <h3 className="font-title-md text-primary font-semibold">Full Journey Sequence Trajectories</h3>
              </div>
              <button
                onClick={() => setShowSequenceModal(false)}
                className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center hover:bg-surface-container-highest"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>
            <p className="font-body-sm text-on-surface-variant mb-4">
              Breakdown of all 14 active user flow clusters showing transition drop-off percentages.
            </p>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {[
                { title: 'Landing → Search → Direct PDP Checkout', drop: '14%', status: 'Optimal' },
                { title: 'Promo Code Application Loop', drop: '88%', status: 'Critical' },
                { title: 'Cross-Border Currency Conversion', drop: '68%', status: 'High' },
                { title: 'Social Sign-in OAuth Handoff', drop: '32%', status: 'Moderate' },
              ].map((flow, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-surface-container-low rounded-lg">
                  <span className="text-xs font-semibold text-primary">{flow.title}</span>
                  <div className="flex items-center gap-2">
                    <span className="font-label-sm text-xs font-bold text-tertiary-container">{flow.drop} Drop</span>
                    <span className="font-label-sm text-[10px] bg-surface-container-high px-2 py-0.5 rounded-full">
                      {flow.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setShowSequenceModal(false)}
                className="bg-primary-container text-on-primary font-label-md px-4 py-2 rounded-full text-xs"
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
                <h3 className="font-title-md text-primary font-semibold">{selectedInsight}</h3>
              </div>
              <button
                onClick={() => setSelectedInsight(null)}
                className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center hover:bg-surface-container-highest"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>
            <p className="font-body-sm text-on-surface-variant mb-4">
              Detailed machine heuristics indicate moving input validation client-side will prevent checkout abandonment and recover up to $24,000/week in lost basket value.
            </p>
            <div className="p-3 bg-surface-container-high rounded-lg text-xs font-mono text-primary mb-4">
              Action Plan: Deploy PR #409 · Zero-latency debounce validation
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setSelectedInsight(null)}
                className="bg-primary-container text-on-primary font-label-md px-4 py-2 rounded-full text-xs"
              >
                Acknowledge Insight
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
