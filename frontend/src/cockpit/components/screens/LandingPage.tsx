"use client";

import React, { useState } from 'react';
import { TimeTrackerDial } from '../bento/TimeTrackerDial';
import { InvertedFocusModule } from '../bento/InvertedFocusModule';
import { Task, UserProfile } from '../../types';

interface LandingPageProps {
  tasks: Task[];
  onToggleTask: (taskId: string) => void;
  onLaunchCockpit: () => void;
  onSignIn: () => void;
  onViewAnalytics: () => void;
  currentUser?: UserProfile;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  tasks,
  onToggleTask,
  onLaunchCockpit,
  onSignIn,
  onViewAnalytics,
}) => {
  const [selectedPlan, setSelectedPlan] = useState<'starter' | 'pro' | 'enterprise'>('pro');

  return (
    <div className="w-full flex flex-col bg-background selection:bg-secondary-container selection:text-on-secondary-container relative overflow-hidden">
      {/* Ambient Daylight Shimmer Background Washes */}
      <div className="absolute top-0 right-1/4 w-[680px] h-[400px] pointer-events-none rounded-full blur-3xl opacity-35 bg-gradient-to-br from-secondary-container via-surface-container-high to-transparent" />
      <div className="absolute top-80 left-10 w-[440px] h-[440px] pointer-events-none rounded-full blur-3xl opacity-20 bg-gradient-to-tr from-tertiary-fixed to-transparent" />
      <div className="absolute bottom-96 right-10 w-[500px] h-[500px] pointer-events-none rounded-full blur-3xl opacity-20 bg-gradient-to-bl from-secondary-fixed to-transparent" />

      {/* Floating Landing Header / Navigation */}
      <header className="sticky top-4 z-40 px-4 sm:px-6 lg:px-8 mb-8">
        <nav
          className="max-w-7xl mx-auto bg-surface-container-lowest/90 backdrop-blur-md border border-surface-container-high rounded-full p-2 pl-4 pr-3 flex items-center justify-between gap-3 shadow-[0_12px_32px_-8px_rgba(180,160,140,0.18)]"
          aria-label="Landing Navigation"
        >
          {/* Brand */}
          <div className="flex items-center gap-2.5">
            <div className="w-2.5 h-2.5 rounded-full bg-secondary-container animate-pulse" />
            <span className="font-headline-sm text-sm sm:text-base font-bold tracking-tight text-primary">
              Atelier Intelligence
            </span>
            <span className="font-label-sm text-[10px] uppercase bg-surface-container-high text-on-surface-variant px-2 py-0.5 rounded-full">
              v2.4
            </span>
          </div>

          {/* Center Links */}
          <div className="hidden md:flex items-center gap-1 bg-surface-container-low p-1 rounded-full border border-surface-container-high/60">
            <a href="#features" className="font-title-md text-xs px-3.5 py-1.5 rounded-full text-on-surface-variant hover:text-on-surface hover:bg-surface-container-lowest transition-all">
              Architecture
            </a>
            <a href="#telemetry" className="font-title-md text-xs px-3.5 py-1.5 rounded-full text-on-surface-variant hover:text-on-surface hover:bg-surface-container-lowest transition-all">
              Bento Telemetry
            </a>
            <a href="#pricing" className="font-title-md text-xs px-3.5 py-1.5 rounded-full text-on-surface-variant hover:text-on-surface hover:bg-surface-container-lowest transition-all">
              Pricing
            </a>
            <button
              onClick={onViewAnalytics}
              className="font-title-md text-xs px-3.5 py-1.5 rounded-full text-secondary hover:bg-surface-container-lowest transition-all font-semibold"
            >
              Live Analytics ↗
            </button>
          </div>

          {/* Right Action Buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={onSignIn}
              className="font-title-md text-xs text-on-surface-variant hover:text-on-surface px-3.5 py-2 rounded-full transition-colors font-medium"
            >
              Sign In
            </button>

            <button
              onClick={onLaunchCockpit}
              className="bg-secondary-container hover:bg-secondary-fixed text-on-secondary-fixed font-title-md text-xs px-4 sm:px-5 py-2 rounded-full font-semibold shadow-sm hover:shadow transition-all hover:-translate-y-0.5 active:translate-y-0 flex items-center gap-1.5 group"
            >
              <span>Launch Cockpit</span>
              <span className="material-symbols-outlined text-[16px] transition-transform group-hover:translate-x-0.5">
                arrow_forward
              </span>
            </button>
          </div>
        </nav>
      </header>

      {/* Hero Section */}
      <section className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-16 text-center flex flex-col items-center">
        {/* Release Pill Badge */}
        <div className="inline-flex items-center gap-2 bg-surface-container-lowest px-4 py-1.5 rounded-full shadow-[0_1px_3px_rgba(40,30,20,0.06),0_12px_24px_-8px_rgba(180,160,140,0.12)] border border-surface-container-high mb-6">
          <span className="w-2 h-2 rounded-full bg-secondary-container animate-ping" />
          <span className="font-label-sm text-xs font-semibold text-primary uppercase tracking-wider">
            Warm Bento Tactile System
          </span>
          <span className="text-on-surface-variant">•</span>
          <span className="font-body-sm text-xs text-on-surface-variant">
            Engineered for Quantitative Operators
          </span>
        </div>

        {/* Display Headline */}
        <h1 className="font-headline-lg text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-primary max-w-4xl leading-[1.15]">
          Tactile intelligence for modern engineering & quantitative workflows
        </h1>

        {/* Subtitle */}
        <p className="font-body-lg text-base sm:text-lg text-on-surface-variant max-w-2xl mt-4 leading-relaxed font-normal">
          Drawing direct inspiration from high-craft product management and precision analytics. Reject sterile corporate gray in favor of a warm, human, clay-and-sand palette with obsidian focal points.
        </p>

        {/* Hero CTAs */}
        <div className="flex flex-wrap items-center justify-center gap-3.5 mt-8">
          <button
            onClick={onLaunchCockpit}
            className="bg-primary-container hover:bg-primary text-on-primary font-title-md text-sm px-7 py-3.5 rounded-full font-semibold shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5 active:translate-y-0 flex items-center gap-2 group"
          >
            <span>Enter Intelligence Cockpit</span>
            <span className="material-symbols-outlined text-[18px] transition-transform group-hover:translate-x-1">
              arrow_forward
            </span>
          </button>

          <button
            onClick={onViewAnalytics}
            className="bg-surface-container-lowest hover:bg-surface-container-high text-primary font-title-md text-sm px-6 py-3.5 rounded-full font-semibold border border-surface-container-high shadow-xs transition-all flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-[18px] text-secondary">insights</span>
            <span>Explore Live Analytics</span>
          </button>
        </div>

        {/* Quantitative Metrics Bar */}
        <div className="w-full max-w-4xl grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 mt-12 p-3 bg-surface-container-lowest/80 backdrop-blur-sm rounded-3xl border border-surface-container-high shadow-[0_1px_3px_rgba(40,30,20,0.04),0_16px_36px_-12px_rgba(180,160,140,0.1)] text-left">
          <div className="p-3 bg-surface-container-low rounded-2xl">
            <span className="font-label-sm text-[10px] uppercase tracking-wider text-on-surface-variant block">
              Active Telemetry
            </span>
            <span className="font-stat-metric text-2xl font-bold text-primary block mt-0.5">
              142,850
            </span>
            <span className="text-[10px] text-secondary font-medium">+12.4% this sprint</span>
          </div>

          <div className="p-3 bg-surface-container-low rounded-2xl">
            <span className="font-label-sm text-[10px] uppercase tracking-wider text-on-surface-variant block">
              Avg Friction Score
            </span>
            <span className="font-stat-metric text-2xl font-bold text-primary block mt-0.5">
              3.8 <span className="text-xs font-normal text-on-surface-variant">/ 10</span>
            </span>
            <span className="text-[10px] text-secondary font-medium">Optimal threshold</span>
          </div>

          <div className="p-3 bg-surface-container-low rounded-2xl">
            <span className="font-label-sm text-[10px] uppercase tracking-wider text-on-surface-variant block">
              Milestone Accuracy
            </span>
            <span className="font-stat-metric text-2xl font-bold text-secondary block mt-0.5">
              94.2%
            </span>
            <span className="text-[10px] text-on-surface-variant">Zero-drift delivery</span>
          </div>

          <div className="p-3 bg-surface-container-low rounded-2xl">
            <span className="font-label-sm text-[10px] uppercase tracking-wider text-on-surface-variant block">
              Resolution Speed
            </span>
            <span className="font-stat-metric text-2xl font-bold text-primary block mt-0.5">
              1.8 <span className="text-xs font-normal text-on-surface-variant">days</span>
            </span>
            <span className="text-[10px] text-secondary font-medium">-0.4d latency</span>
          </div>
        </div>
      </section>

      {/* Flagship Interactive Bento Preview Section */}
      <section id="telemetry" className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="text-center mb-8">
          <span className="font-label-sm text-xs font-semibold uppercase tracking-widest text-secondary bg-secondary-container/20 px-3 py-1 rounded-full">
            Live Tactile Modules
          </span>
          <h2 className="font-headline-md text-3xl sm:text-4xl font-bold text-primary tracking-tight mt-2">
            The Bento Box Modular Architecture
          </h2>
          <p className="font-body-sm text-sm text-on-surface-variant max-w-xl mx-auto mt-1">
            Every module is tactile, extruded, and deeply tangible. Click the dials and toggles below to interact with live components.
          </p>
        </div>

        {/* 12-Column Responsive Bento Grid */}
        <div className="grid grid-cols-1 md:grid-cols-6 lg:grid-cols-12 gap-5 sm:gap-6">
          {/* Module 1: Flagship Circular Time Tracker Dial (4 cols) */}
          <div className="md:col-span-3 lg:col-span-4 flex flex-col">
            <TimeTrackerDial
              tasks={tasks}
              activeTaskId={tasks[0]?.id || 't-1'}
              onSelectTask={() => {}}
              onLogTime={() => {}}
              onExpandView={onLaunchCockpit}
            />
          </div>

          {/* Module 2: Inverted Dark Bento Focus Module (4 cols) */}
          <div className="md:col-span-3 lg:col-span-4 flex flex-col">
            <InvertedFocusModule
              tasks={tasks}
              onToggleTask={onToggleTask}
              onExpandView={onLaunchCockpit}
            />
          </div>

          {/* Module 3: Mini Friction Preview Bento (4 cols) */}
          <div className="md:col-span-6 lg:col-span-4 bg-surface-container-lowest rounded-[28px] p-6 shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] border border-surface-container-high flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="font-label-sm text-[10px] uppercase tracking-wider text-on-surface-variant">
                  Platform Diagnostics
                </span>
                <span className="font-label-sm text-[10px] bg-secondary-container/30 text-on-secondary-fixed font-semibold px-2 py-0.5 rounded-full">
                  Real-time
                </span>
              </div>
              <h3 className="font-headline-sm text-base font-semibold text-primary">
                Cohort Latency Gauges
              </h3>
              <p className="font-body-sm text-xs text-on-surface-variant mt-0.5">
                Micro-dial telemetry across runtime devices
              </p>

              {/* 3 Radial Gauges */}
              <div className="grid grid-cols-3 gap-2 mt-4">
                <div className="bg-surface-container-low p-2 rounded-2xl text-center">
                  <div className="relative w-12 h-12 mx-auto flex items-center justify-center">
                    <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                      <path className="text-surface-container-high" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeWidth="3" />
                      <path className="text-secondary-container" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeDasharray="72, 100" strokeLinecap="round" strokeWidth="3" />
                    </svg>
                    <span className="absolute font-stat text-xs font-bold text-primary">72%</span>
                  </div>
                  <span className="text-[10px] font-medium text-primary block mt-1">WebKit</span>
                </div>

                <div className="bg-surface-container-low p-2 rounded-2xl text-center">
                  <div className="relative w-12 h-12 mx-auto flex items-center justify-center">
                    <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                      <path className="text-surface-container-high" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeWidth="3" />
                      <path className="text-primary-container" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeDasharray="28, 100" strokeLinecap="round" strokeWidth="3" />
                    </svg>
                    <span className="absolute font-stat text-xs font-bold text-primary">28%</span>
                  </div>
                  <span className="text-[10px] font-medium text-primary block mt-1">Chrome</span>
                </div>

                <div className="bg-surface-container-low p-2 rounded-2xl text-center">
                  <div className="relative w-12 h-12 mx-auto flex items-center justify-center">
                    <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                      <path className="text-surface-container-high" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeWidth="3" />
                      <path className="text-secondary" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeDasharray="14, 100" strokeLinecap="round" strokeWidth="3" />
                    </svg>
                    <span className="absolute font-stat text-xs font-bold text-primary">14%</span>
                  </div>
                  <span className="text-[10px] font-medium text-primary block mt-1">Native</span>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-surface-container-high flex items-center justify-between text-xs">
              <span className="text-on-surface-variant text-[11px]">DOM Hydration: 380ms</span>
              <button
                onClick={onViewAnalytics}
                className="text-secondary font-semibold hover:underline flex items-center gap-1 text-[11px]"
              >
                <span>Full Telemetry</span>
                <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Philosophy & Architecture Section */}
      <section id="features" className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="text-center mb-12">
          <span className="font-label-sm text-xs font-semibold uppercase tracking-widest text-on-surface-variant bg-surface-container-high px-3 py-1 rounded-full">
            Tactile Design System
          </span>
          <h2 className="font-headline-md text-3xl sm:text-4xl font-bold text-primary tracking-tight mt-2">
            Engineered for Precision & Ergonomic Ease
          </h2>
          <p className="font-body-sm text-sm text-on-surface-variant max-w-xl mx-auto mt-1">
            Built upon three pillars of Organic Tactile Modernism.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Card 1 */}
          <div className="bg-surface-container-lowest rounded-[28px] p-8 border border-surface-container-high shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-2xl bg-secondary-container/20 flex items-center justify-center text-secondary mb-5">
                <span className="material-symbols-outlined text-[24px]">wb_sunny</span>
              </div>
              <h3 className="font-headline-sm text-lg font-bold text-primary">
                Approachable Sophistication
              </h3>
              <p className="font-body-sm text-sm text-on-surface-variant mt-2 leading-relaxed">
                Warm neutral foundations (soft bone white, brushed clay, sunlit sand) create inviting domestic comfort while maintaining elite mathematical rigor.
              </p>
            </div>
            <div className="mt-6 pt-3 border-t border-surface-container-high text-xs text-on-surface-variant font-stat">
              Palette: #FAF8F5 · #F3EFEA · #FFF9E6
            </div>
          </div>

          {/* Card 2 */}
          <div className="bg-surface-container-lowest rounded-[28px] p-8 border border-surface-container-high shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-2xl bg-primary-container text-white flex items-center justify-center mb-5">
                <span className="material-symbols-outlined text-[24px]">touch_app</span>
              </div>
              <h3 className="font-headline-sm text-lg font-bold text-primary">
                Tactile Physical Clarity
              </h3>
              <p className="font-body-sm text-sm text-on-surface-variant mt-2 leading-relaxed">
                Components feel extruded through delicate perimeter ambient rims, continuous 9999px pillular ergonomics, and micro-dials with tick marks.
              </p>
            </div>
            <div className="mt-6 pt-3 border-t border-surface-container-high text-xs text-on-surface-variant font-stat">
              Clay substrate: 0 16px 36px -12px
            </div>
          </div>

          {/* Card 3 */}
          <div className="bg-surface-container-lowest rounded-[28px] p-8 border border-surface-container-high shadow-[0_1px_3px_rgba(40,30,20,0.05),0_16px_36px_-12px_rgba(180,160,140,0.12)] flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-2xl bg-secondary-container text-on-secondary-fixed flex items-center justify-center mb-5">
                <span className="material-symbols-outlined text-[24px]">balance</span>
              </div>
              <h3 className="font-headline-sm text-lg font-bold text-primary">
                Dynamic Equilibrium
              </h3>
              <p className="font-body-sm text-sm text-on-surface-variant mt-2 leading-relaxed">
                Ultra-high contrast deep-charcoal focus pills interact harmoniously with soft champagne backdrop cards, punctuated by radiant Amber Gold and Coral status sparks.
              </p>
            </div>
            <div className="mt-6 pt-3 border-t border-surface-container-high text-xs text-on-surface-variant font-stat">
              Anchors: #1E1E22 · #F4B33E · #F06A42
            </div>
          </div>
        </div>
      </section>

      {/* Pricing / Workspace Tiers Bento Grid */}
      <section id="pricing" className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="text-center mb-12">
          <span className="font-label-sm text-xs font-semibold uppercase tracking-widest text-secondary bg-secondary-container/20 px-3 py-1 rounded-full">
            Transparent Telemetry
          </span>
          <h2 className="font-headline-md text-3xl sm:text-4xl font-bold text-primary tracking-tight mt-2">
            Scale With Your Sprint Velocity
          </h2>
          <p className="font-body-sm text-sm text-on-surface-variant max-w-xl mx-auto mt-1">
            Choose the workspace plan that fits your quantitative operations.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
          {/* Tier 1: Starter */}
          <div
            onClick={() => setSelectedPlan('starter')}
            className={`cursor-pointer rounded-[32px] p-8 flex flex-col justify-between transition-all ${
              selectedPlan === 'starter'
                ? 'bg-surface-container-lowest ring-2 ring-primary shadow-lg'
                : 'bg-surface-container-lowest border border-surface-container-high hover:border-outline-variant'
            }`}
          >
            <div>
              <div className="flex items-center justify-between mb-4">
                <span className="font-label-sm text-xs uppercase tracking-wider text-on-surface-variant">
                  Team Operator
                </span>
                <span className="font-label-sm text-[10px] bg-surface-container-high px-2 py-0.5 rounded-full">
                  Up to 5 Seats
                </span>
              </div>
              <div className="flex items-baseline gap-1 my-3">
                <span className="font-stat-metric text-4xl font-bold text-primary">$0</span>
                <span className="font-body-sm text-xs text-on-surface-variant">/ month</span>
              </div>
              <p className="font-body-sm text-xs text-on-surface-variant leading-relaxed">
                Essential bento modular cockpit for exploratory engineering and sprint velocity tracking.
              </p>

              <ul className="mt-6 space-y-3 text-xs text-on-surface">
                <li className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px] text-secondary">check</span>
                  <span>14-day telemetry retention</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px] text-secondary">check</span>
                  <span>Circular time tracking dial</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px] text-secondary">check</span>
                  <span>Standard sprint kanban board</span>
                </li>
              </ul>
            </div>

            <button
              onClick={onLaunchCockpit}
              className="mt-8 w-full py-3 rounded-full text-xs font-semibold bg-surface-container-high hover:bg-surface-container-highest text-primary transition-colors"
            >
              Get Started Free
            </button>
          </div>

          {/* Tier 2: Quantitative Pro (Featured Bento) */}
          <div
            onClick={() => setSelectedPlan('pro')}
            className="cursor-pointer bg-primary-container text-on-primary rounded-[32px] p-8 shadow-[0_24px_50px_-12px_rgba(15,15,18,0.45)] border border-white/10 flex flex-col justify-between relative overflow-hidden"
          >
            {/* Ambient amber glow */}
            <div className="absolute top-0 right-0 w-44 h-44 bg-secondary-container/15 rounded-full blur-2xl pointer-events-none" />

            <div>
              <div className="flex items-center justify-between mb-4">
                <span className="font-label-sm text-xs uppercase tracking-wider text-secondary-container font-semibold">
                  Quantitative Pro
                </span>
                <span className="font-label-sm text-[10px] bg-secondary-container text-on-secondary-fixed px-2.5 py-0.5 rounded-full font-bold uppercase">
                  Most Popular
                </span>
              </div>
              <div className="flex items-baseline gap-1 my-3">
                <span className="font-stat-metric text-4xl font-bold text-white">$49</span>
                <span className="font-body-sm text-xs text-on-primary-container">/ seat / month</span>
              </div>
              <p className="font-body-sm text-xs text-on-primary-container leading-relaxed">
                Full-spectrum telemetry diagnostics, live rage-click correlation, and machine heuristics.
              </p>

              <ul className="mt-6 space-y-3 text-xs text-white">
                <li className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px] text-secondary-container">check_circle</span>
                  <span>90-day granular waveform telemetry</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px] text-secondary-container">check_circle</span>
                  <span>Real-time rage click vector mapping</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px] text-secondary-container">check_circle</span>
                  <span>Automated cognitive insight feed</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px] text-secondary-container">check_circle</span>
                  <span>Unlimited bento workspace boards</span>
                </li>
              </ul>
            </div>

            <button
              onClick={onLaunchCockpit}
              className="mt-8 w-full py-3.5 rounded-full text-xs font-semibold bg-secondary-container hover:bg-secondary-fixed text-on-secondary-fixed shadow-md transition-all hover:-translate-y-0.5"
            >
              Start 14-Day Free Trial
            </button>
          </div>

          {/* Tier 3: Enterprise Atelier */}
          <div
            onClick={() => setSelectedPlan('enterprise')}
            className={`cursor-pointer rounded-[32px] p-8 flex flex-col justify-between transition-all ${
              selectedPlan === 'enterprise'
                ? 'bg-surface-container-lowest ring-2 ring-primary shadow-lg'
                : 'bg-surface-container-lowest border border-surface-container-high hover:border-outline-variant'
            }`}
          >
            <div>
              <div className="flex items-center justify-between mb-4">
                <span className="font-label-sm text-xs uppercase tracking-wider text-on-surface-variant">
                  Atelier Enterprise
                </span>
                <span className="font-label-sm text-[10px] bg-surface-container-high px-2 py-0.5 rounded-full">
                  Dedicated Cloud
                </span>
              </div>
              <div className="flex items-baseline gap-1 my-3">
                <span className="font-headline-md text-3xl font-bold text-primary">Custom</span>
              </div>
              <p className="font-body-sm text-xs text-on-surface-variant leading-relaxed">
                For quantitative enterprises requiring custom telemetry pipelines, hardware passkeys, and on-premise SLA.
              </p>

              <ul className="mt-6 space-y-3 text-xs text-on-surface">
                <li className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px] text-secondary">check</span>
                  <span>Infinite historical session replay</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px] text-secondary">check</span>
                  <span>Zero-Trust passkey SAML & Okta SSO</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px] text-secondary">check</span>
                  <span>Dedicated quantitative solutions architect</span>
                </li>
              </ul>
            </div>

            <button
              onClick={onSignIn}
              className="mt-8 w-full py-3 rounded-full text-xs font-semibold bg-primary-container hover:bg-primary text-on-primary transition-colors"
            >
              Contact Atelier Sales
            </button>
          </div>
        </div>
      </section>

      {/* Sunlit Final CTA Shimmer Card */}
      <section className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="relative rounded-[36px] overflow-hidden border border-surface-container-high bg-white p-8 sm:p-14 text-center shadow-[0_20px_48px_-16px_rgba(180,160,140,0.22)]">
          {/* Sunlit highlight glow wash */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: 'radial-gradient(ellipse at 80% 0%, rgba(254, 237, 188, 0.55) 0%, rgba(250, 248, 245, 0) 70%)',
            }}
          />

          <div className="relative z-10 max-w-2xl mx-auto flex flex-col items-center">
            <div className="w-12 h-12 rounded-full bg-secondary-container/30 flex items-center justify-center text-secondary mb-4">
              <span className="material-symbols-outlined text-[24px]">rocket_launch</span>
            </div>

            <h2 className="font-headline-lg text-3xl sm:text-4xl font-bold tracking-tight text-primary">
              Ready to elevate your sprint velocity?
            </h2>
            <p className="font-body-lg text-sm sm:text-base text-on-surface-variant mt-3 leading-relaxed">
              Step into the Atelier Intelligence cockpit now. Realize immediate friction reductions and quantitative precision across your entire product roadmap.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-3 mt-8">
              <button
                onClick={onLaunchCockpit}
                className="bg-primary-container hover:bg-primary text-on-primary font-title-md text-sm px-8 py-3.5 rounded-full font-semibold shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5 flex items-center gap-2 group"
              >
                <span>Launch Cockpit Now</span>
                <span className="material-symbols-outlined text-[18px] transition-transform group-hover:translate-x-1">
                  arrow_forward
                </span>
              </button>

              <button
                onClick={onSignIn}
                className="bg-surface-container-lowest hover:bg-surface-container-high text-primary font-title-md text-sm px-6 py-3.5 rounded-full font-semibold border border-surface-container-high transition-colors"
              >
                Sign In to Workspace
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Tactile Footer */}
      <footer className="w-full bg-surface-container-low py-space-xl border-t border-surface-container-high/60 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row items-center justify-between gap-space-md text-xs text-on-surface-variant">
          <div className="flex items-center gap-space-sm">
            <div className="w-2.5 h-2.5 rounded-full bg-secondary-container" />
            <span className="font-headline-sm text-sm font-bold text-primary">Atelier Intelligence Core</span>
            <span className="font-label-sm text-[10px] bg-surface-container-high px-2 py-0.5 rounded-full">v2.4</span>
          </div>

          <div className="flex items-center gap-4">
            <button onClick={onLaunchCockpit} className="hover:text-primary transition-colors">
              Cockpit
            </button>
            <button onClick={onViewAnalytics} className="hover:text-primary transition-colors">
              Telemetry
            </button>
            <button onClick={onSignIn} className="hover:text-primary transition-colors">
              Sign In
            </button>
          </div>

          <div className="font-body-sm text-[11px]">
            © 2025 Atelier Architecture. Tactile Bento Modular System.
          </div>
        </div>
      </footer>
    </div>
  );
};
