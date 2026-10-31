"use client";

import React, { useState } from 'react';
import { 
  Sparkles, 
  BrainCircuit, 
  ShieldCheck, 
  Zap, 
  CheckCircle2, 
  ChevronRight
} from 'lucide-react';
import { Task, TeamMember } from '../../types';
import { calculateSprintSimulation, prioritizeSignals, IntelligenceSignal } from '../../utils/intelligenceMetrics';

interface IntelligenceHubScreenProps {
  tasks?: Task[];
  teamMembers?: TeamMember[];
  onNavigateToProjects?: () => void;
  onNavigateToTime?: () => void;
}

export const IntelligenceHubScreen: React.FC<IntelligenceHubScreenProps> = () => {
  // Scenario Simulation Levers
  const [engineersCount, setEngineersCount] = useState<number>(4);
  const [velocityPerDay, setVelocityPerDay] = useState<number>(2.2);
  const [scopeCreep, setScopeCreep] = useState<number>(10);
  const [storyPoints] = useState<number>(85);

  // Active query in synthesizer
  const [synthesizerQuery, setSynthesizerQuery] = useState<string>('Forecast Q4 milestone delivery confidence');
  const [synthesizerResult, setSynthesizerResult] = useState<string | null>(
    'Synthesizer Analysis: Current sprint burn trajectory indicates a 94.2% likelihood of completing all 6 critical path milestones by Friday 4:00 PM. Blocker risk on API token integration is currently isolated.'
  );

  // Initial Signals
  const [signals] = useState<IntelligenceSignal[]>([
    {
      id: 'sig-1',
      category: 'risk',
      severity: 'critical',
      title: 'Cross-Sprint PR Review Bottleneck',
      metricLabel: 'Review Latency',
      metricValue: '4.2 hrs',
      confidence: 94,
      recommendation: 'Batch review approvals before 2:00 PM standup to unlock 2 blocked deliverables.',
      impactScore: 92,
    },
    {
      id: 'sig-2',
      category: 'velocity',
      severity: 'optimal',
      title: 'Design System Consolidation Velocity Surge',
      metricLabel: 'Throughput',
      metricValue: '+28.4%',
      confidence: 96,
      recommendation: 'Soren Lindqvist has cleared 3 tokens ahead of schedule. Surplus bandwidth can be allocated to client reviews.',
      impactScore: 84,
    },
    {
      id: 'sig-3',
      category: 'capacity',
      severity: 'warning',
      title: 'Quantitative Lead Bandwidth Concentration',
      metricLabel: 'Concentration',
      metricValue: '64% critical',
      confidence: 89,
      recommendation: 'Elena Vance is designated as sole reviewer on 4 high-priority milestones. Delegate PR checks to Marcus Kane.',
      impactScore: 78,
    },
    {
      id: 'sig-4',
      category: 'anomaly',
      severity: 'optimal',
      title: 'Automated Test Regressions Zero-State',
      metricLabel: 'Pass Rate',
      metricValue: '100.0%',
      confidence: 98,
      recommendation: 'Build and unit-test stability is currently at the 99th percentile across past 8 sprints.',
      impactScore: 70,
    },
  ]);

  const [appliedSignalIds, setAppliedSignalIds] = useState<string[]>([]);

  const handleApplyMitigation = (signalId: string) => {
    if (appliedSignalIds.includes(signalId)) {
      setAppliedSignalIds(appliedSignalIds.filter((id) => id !== signalId));
    } else {
      setAppliedSignalIds([...appliedSignalIds, signalId]);
    }
  };

  const simulation = calculateSprintSimulation({
    teamCapacityHours: engineersCount * 40,
    storyPointsEstimate: storyPoints,
    velocityPerEngineerDay: velocityPerDay,
    engineersCount,
    scopeCreepPercent: scopeCreep,
  });

  const sortedSignals = prioritizeSignals(signals);

  const handleRunPreset = (preset: string) => {
    setSynthesizerQuery(preset);
    if (preset.includes('Senior Engineer')) {
      setEngineersCount(5);
      setSynthesizerResult(
        'Scenario Injected: Adding 1 Senior Engineer scales daily output to 11.0 pts/day, reducing projected sprint cycle from 10.0 to 7.8 days (2.2 days ahead of deadline).'
      );
    } else if (preset.includes('bottleneck')) {
      setSynthesizerResult(
        'Bottleneck Identified: 2 deliverables in Sprint Backlog require API schema sign-off. Mitigating review lag restores completion confidence from 84% to 96%.'
      );
    } else {
      setSynthesizerResult(
        'Global Sprint Telemetry: Q4 milestone delivery confidence remains at 94.2%. Velocity delta is +24% ahead of the 120 pts historical benchmark.'
      );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="relative rounded-[32px] overflow-hidden border border-[#ECE7E1] bg-white p-6 sm:p-8 shadow-[0_16px_36px_-12px_rgba(180,160,140,0.15)]">
        <div 
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'radial-gradient(ellipse at 85% 0%, rgba(254, 237, 188, 0.45) 0%, rgba(250, 248, 245, 0) 70%)',
          }}
        />

        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div className="max-w-2xl">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="font-stat text-[11px] uppercase tracking-widest text-[#1E1E22] font-semibold bg-[#F4B33E]/20 text-[#1E1E22] px-2.5 py-1 rounded-full border border-[#F4B33E]/30 flex items-center gap-1.5">
                <BrainCircuit className="w-3.5 h-3.5 text-[#1E1E22]" />
                Analytics Intelligence Hub
              </span>
              <span className="inline-flex items-center gap-1 text-[11px] font-stat font-medium text-[#449E74] bg-[#449E74]/10 px-2.5 py-1 rounded-full">
                <ShieldCheck className="w-3 h-3" />
                Model Confidence: 96.4%
              </span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#1E1E22]">
              Predictive Sprints & Telemetry Modeling
            </h1>
            <p className="text-sm text-[#6E6B68] mt-1 leading-relaxed">
              Algorithmic anomaly detection, stochastic Monte Carlo simulations, and real-time team throughput forecasting.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-[#FAF8F5] border border-[#E8E3DC] px-4 py-2.5 rounded-2xl text-right">
              <span className="text-[10px] font-stat uppercase text-[#6E6B68] block">
                Signals Monitored
              </span>
              <span className="font-stat text-xl font-bold text-[#1E1E22] tabular-nums">
                {signals.length} <span className="text-xs font-normal text-[#449E74]">Active</span>
              </span>
            </div>

            <div className="bg-[#FAF8F5] border border-[#E8E3DC] px-4 py-2.5 rounded-2xl text-right">
              <span className="text-[10px] font-stat uppercase text-[#6E6B68] block">
                Mitigations Applied
              </span>
              <span className="font-stat text-xl font-bold text-[#F4B33E] tabular-nums">
                {appliedSignalIds.length} <span className="text-xs font-normal text-[#6E6B68]">/ {signals.length}</span>
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Flagship Bento Section 1: Scenario Simulation Cockpit */}
      <div className="bento-card p-6 sm:p-8 bg-white relative">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 pb-4 border-b border-[#E8E3DC]">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-stat uppercase tracking-wider text-[#6E6B68]">
                Dynamic Simulation Cockpit
              </span>
              <span className="text-xs font-stat bg-[#1E1E22] text-[#F4B33E] px-2 py-0.5 rounded-full font-semibold">
                Monte Carlo Engine
              </span>
            </div>
            <h2 className="text-xl font-bold text-[#1E1E22] tracking-tight mt-1">
              Sprint Velocity & Capacity Scenario Modeling
            </h2>
            <p className="text-xs text-[#6E6B68]">
              Adjust operational levers below to observe algorithmic impact on deadline variance and completion probability.
            </p>
          </div>

          {/* Quick Preset Buttons */}
          <div className="flex items-center gap-1.5 bg-[#F3EFEA] p-1 rounded-full border border-[#E8E3DC] self-start md:self-auto">
            <button
              onClick={() => {
                setEngineersCount(4);
                setVelocityPerDay(2.2);
                setScopeCreep(0);
              }}
              className="px-3 py-1 text-xs font-stat font-medium rounded-full hover:bg-white text-[#1E1E22] transition-colors"
            >
              Baseline
            </button>
            <button
              onClick={() => {
                setEngineersCount(5);
                setVelocityPerDay(2.4);
                setScopeCreep(15);
              }}
              className="px-3 py-1 text-xs font-stat font-medium rounded-full bg-[#1E1E22] text-white shadow-xs"
            >
              Surge Scale (+1 FTE)
            </button>
            <button
              onClick={() => {
                setEngineersCount(3);
                setVelocityPerDay(1.8);
                setScopeCreep(25);
              }}
              className="px-3 py-1 text-xs font-stat font-medium rounded-full hover:bg-white text-[#1E1E22] transition-colors"
            >
              Stress Test
            </button>
          </div>
        </div>

        {/* 2-Column Cockpit Grid: Controls on Left, Real-Time Model Telemetry on Right */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          {/* Controls Column (6 cols) */}
          <div className="lg:col-span-6 space-y-5">
            {/* Lever 1: Engineers Count */}
            <div>
              <div className="flex justify-between items-center text-xs mb-2">
                <span className="font-semibold text-[#1E1E22]">Active Engineering Operators</span>
                <span className="font-stat font-bold text-sm bg-[#F3EFEA] px-2.5 py-0.5 rounded-full text-[#1E1E22]">
                  {engineersCount} engineers ({engineersCount * 40}h capacity)
                </span>
              </div>
              <input
                type="range"
                min="2"
                max="8"
                step="1"
                value={engineersCount}
                onChange={(e) => setEngineersCount(Number(e.target.value))}
                className="w-full accent-[#F4B33E] cursor-pointer"
              />
              <div className="flex justify-between text-[10px] font-stat text-[#6E6B68] mt-1">
                <span>2 FTE</span>
                <span>4 FTE (Current)</span>
                <span>8 FTE</span>
              </div>
            </div>

            {/* Lever 2: Velocity Rate */}
            <div>
              <div className="flex justify-between items-center text-xs mb-2">
                <span className="font-semibold text-[#1E1E22]">Average Velocity Throughput</span>
                <span className="font-stat font-bold text-sm bg-[#F3EFEA] px-2.5 py-0.5 rounded-full text-[#1E1E22]">
                  {velocityPerDay.toFixed(1)} pts / engineer / day
                </span>
              </div>
              <input
                type="range"
                min="1.0"
                max="3.5"
                step="0.1"
                value={velocityPerDay}
                onChange={(e) => setVelocityPerDay(Number(e.target.value))}
                className="w-full accent-[#F4B33E] cursor-pointer"
              />
              <div className="flex justify-between text-[10px] font-stat text-[#6E6B68] mt-1">
                <span>1.0 pts/d</span>
                <span>2.2 pts/d (Sprint Avg)</span>
                <span>3.5 pts/d</span>
              </div>
            </div>

            {/* Lever 3: Scope Creep Factor */}
            <div>
              <div className="flex justify-between items-center text-xs mb-2">
                <span className="font-semibold text-[#1E1E22]">Anticipated Scope Growth</span>
                <span className="font-stat font-bold text-sm bg-[#F3EFEA] px-2.5 py-0.5 rounded-full text-[#F06A42]">
                  +{scopeCreep}% creep ({simulation.adjustedPoints} pts total)
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="40"
                step="5"
                value={scopeCreep}
                onChange={(e) => setScopeCreep(Number(e.target.value))}
                className="w-full accent-[#F06A42] cursor-pointer"
              />
              <div className="flex justify-between text-[10px] font-stat text-[#6E6B68] mt-1">
                <span>0% (Frozen Scope)</span>
                <span>+10% (Target)</span>
                <span>+40% (High Volatility)</span>
              </div>
            </div>
          </div>

          {/* Real-Time Quantitative Projection Readout (6 cols) */}
          <div className="lg:col-span-6 bg-[#FAF8F5] rounded-[28px] p-6 border border-[#E8E3DC] flex flex-col justify-between">
            <div className="flex items-center justify-between mb-4">
              <span className="text-[10px] font-stat uppercase tracking-wider text-[#6E6B68]">
                Stochastic Output Model
              </span>
              <span
                className={`text-[10px] font-stat font-semibold uppercase px-2.5 py-0.5 rounded-full ${
                  simulation.riskLevel === 'low'
                    ? 'bg-[#449E74]/15 text-[#449E74]'
                    : simulation.riskLevel === 'moderate'
                    ? 'bg-[#F4B33E]/20 text-[#1E1E22]'
                    : 'bg-[#F06A42]/15 text-[#F06A42]'
                }`}
              >
                {simulation.riskLevel} Risk Profile
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4 my-2">
              <div className="bg-white p-4 rounded-2xl border border-[#E8E3DC]/80 shadow-xs">
                <span className="text-[10px] font-stat uppercase text-[#6E6B68] block">
                  Projected Sprint Days
                </span>
                <div className="font-stat text-3xl sm:text-4xl font-bold text-[#1E1E22] mt-1 tabular-nums">
                  {simulation.projectedDays} <span className="text-xs font-normal text-[#6E6B68]">/ 10d</span>
                </div>
                <span className="text-[10px] text-[#449E74] font-medium block mt-1">
                  {simulation.projectedDays <= 10 ? 'Ahead of sprint schedule' : `+${(simulation.projectedDays - 10).toFixed(1)}d delivery lag`}
                </span>
              </div>

              <div className="bg-white p-4 rounded-2xl border border-[#E8E3DC]/80 shadow-xs">
                <span className="text-[10px] font-stat uppercase text-[#6E6B68] block">
                  Completion Probability
                </span>
                <div className="font-stat text-3xl sm:text-4xl font-bold text-[#F4B33E] mt-1 tabular-nums">
                  {simulation.completionProbability}%
                </div>
                <span className="text-[10px] text-[#6E6B68] font-medium block mt-1">
                  Confidence Index: {simulation.confidenceScore}%
                </span>
              </div>
            </div>

            {/* Gauge Track */}
            <div className="mt-4 pt-3 border-t border-[#E8E3DC]">
              <div className="flex justify-between items-center text-xs font-stat mb-1.5">
                <span className="text-[#6E6B68]">Sprint Delivery Margin</span>
                <span className="font-semibold text-[#1E1E22]">
                  {Math.round((engineersCount * velocityPerDay * 10))} pts capacity vs {simulation.adjustedPoints} pts load
                </span>
              </div>
              <div className="w-full h-2.5 rounded-full bg-[#E8E3DC] overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-[#F4B33E] to-[#449E74] rounded-full transition-all duration-300"
                  style={{ width: `${Math.min(100, simulation.completionProbability)}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Flagship Bento Section 2: Automated Intelligence Signals & Mitigations */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <span className="font-stat text-[11px] uppercase tracking-wider text-[#6E6B68] bg-[#F3EFEA] px-2 py-0.5 rounded-full">
              Automated Telemetry
            </span>
            <h3 className="text-lg font-bold text-[#1E1E22] tracking-tight mt-1">
              Active Intelligence Signals & Recommended Interventions
            </h3>
          </div>

          <span className="text-xs text-[#6E6B68]">
            Ranked by impact weighting
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {sortedSignals.map((sig) => {
            const isApplied = appliedSignalIds.includes(sig.id);

            return (
              <div
                key={sig.id}
                className={`bento-card p-6 bg-white flex flex-col justify-between transition-all ${
                  isApplied ? 'ring-2 ring-[#449E74] border-transparent' : ''
                }`}
              >
                <div>
                  {/* Category Pill and Severity */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span
                        className={`w-2.5 h-2.5 rounded-full ${
                          sig.severity === 'critical'
                            ? 'bg-[#F06A42]'
                            : sig.severity === 'warning'
                            ? 'bg-[#F4B33E]'
                            : 'bg-[#449E74]'
                        }`}
                      />
                      <span className="font-stat text-[10px] uppercase tracking-wider font-semibold bg-[#F3EFEA] text-[#1E1E22] px-2 py-0.5 rounded-full">
                        {sig.category} Signal
                      </span>
                    </div>

                    <div className="flex items-center gap-1 text-[11px] font-stat text-[#6E6B68]">
                      <span>Confidence:</span>
                      <strong className="text-[#1E1E22] font-bold">{sig.confidence}%</strong>
                    </div>
                  </div>

                  <h4 className="text-sm font-bold text-[#1E1E22] leading-snug">
                    {sig.title}
                  </h4>

                  {/* Highlight Metric Capsule */}
                  <div className="my-3 flex items-center justify-between p-3 rounded-2xl bg-[#FAF8F5] border border-[#E8E3DC]">
                    <span className="text-xs text-[#6E6B68] font-medium">
                      {sig.metricLabel}
                    </span>
                    <span className="font-stat text-lg font-bold text-[#1E1E22]">
                      {sig.metricValue}
                    </span>
                  </div>

                  {/* Recommendation Text */}
                  <p className="text-xs text-[#6E6B68] leading-relaxed">
                    {sig.recommendation}
                  </p>
                </div>

                {/* Mitigation Action Button */}
                <div className="mt-5 pt-3 border-t border-[#E8E3DC]/60 flex items-center justify-between">
                  <span className="text-[10px] font-stat uppercase text-[#6E6B68]">
                    Impact Score: <strong className="text-[#1E1E22]">{sig.impactScore}/100</strong>
                  </span>

                  <button
                    onClick={() => handleApplyMitigation(sig.id)}
                    className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all shadow-xs ${
                      isApplied
                        ? 'bg-[#449E74] text-white'
                        : 'bg-[#1E1E22] hover:bg-[#2E2E34] text-white'
                    }`}
                  >
                    {isApplied ? (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Mitigation Deployed</span>
                      </>
                    ) : (
                      <>
                        <Zap className="w-3.5 h-3.5 text-[#F4B33E]" />
                        <span>Execute Mitigation</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Flagship Bento Section 3: Metric Synthesizer & Natural Intelligence Bar */}
      <div className="bento-card p-6 bg-white">
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="w-4 h-4 text-[#F4B33E]" />
          <h3 className="text-base font-semibold text-[#1E1E22]">
            Metric Synthesizer & Telemetry Query Assistant
          </h3>
        </div>
        <p className="text-xs text-[#6E6B68] mb-4">
          Select or prompt instant query scenarios to evaluate real-time architectural telemetry.
        </p>

        {/* Preset Chips */}
        <div className="flex flex-wrap items-center gap-2 mb-4">
          {[
            'Forecast Q4 milestone delivery confidence',
            'Simulate adding 1 Senior Engineer (+1 FTE)',
            'Analyze PR review latency bottleneck',
          ].map((preset) => (
            <button
              key={preset}
              onClick={() => handleRunPreset(preset)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors flex items-center gap-1.5 ${
                synthesizerQuery === preset
                  ? 'bg-[#1E1E22] text-white border-[#1E1E22]'
                  : 'bg-[#FAF8F5] text-[#1E1E22] border-[#E8E3DC] hover:bg-[#F3EFEA]'
              }`}
            >
              <span>{preset}</span>
              <ChevronRight className="w-3 h-3 text-[#F4B33E]" />
            </button>
          ))}
        </div>

        {/* Synthesized Output Display */}
        {synthesizerResult && (
          <div className="p-4 rounded-2xl bg-[#FAF8F5] border border-[#E8E3DC] flex items-start gap-3">
            <div className="w-7 h-7 rounded-full bg-[#1E1E22] flex items-center justify-center text-[#F4B33E] shrink-0 mt-0.5">
              <BrainCircuit className="w-4 h-4" />
            </div>
            <div className="flex-1">
              <span className="text-[10px] font-stat uppercase tracking-wider text-[#6E6B68] font-bold block mb-1">
                Telemetry Synthesis Engine
              </span>
              <p className="text-xs text-[#1E1E22] leading-relaxed font-medium">
                {synthesizerResult}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
