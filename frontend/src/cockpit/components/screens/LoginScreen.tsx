"use client";

import React, { useState } from 'react';
import { UserProfile } from '../../types';

export interface LoginScreenProps {
  onLogin?: (user: UserProfile) => void;
  onExploreDemo?: () => void;
  next?: string;
  initialMode?: 'signin' | 'signup';
}

export const LoginScreen: React.FC<LoginScreenProps> = ({
  onLogin,
  onExploreDemo,
  next = '/dashboard',
  initialMode = 'signin',
}) => {
  const [mode, setMode] = useState<'signin' | 'signup'>(initialMode);

  // Sign In state
  const [email, setEmail] = useState('admin');
  const [password, setPassword] = useState('admin123');
  const [rememberMe, setRememberMe] = useState(true);
  const [showPassword, setShowPassword] = useState(false);

  // Sign Up state
  const [fullName, setFullName] = useState('');
  const [signupUsername, setSignupUsername] = useState('');
  const [signupEmail, setSignupEmail] = useState('');
  const [signupPassword, setSignupPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showSignupPassword, setShowSignupPassword] = useState(false);
  const [agreeTerms, setAgreeTerms] = useState(true);

  // General state
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Forgot password modal state
  const [isForgotModalOpen, setIsForgotModalOpen] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotStatus, setForgotStatus] = useState<'idle' | 'sending' | 'sent'>('idle');

  const demoAccounts = [
    {
      name: 'System Administrator',
      role: 'Administrator · Supabase Auth',
      email: 'admin@cji.io',
      username: 'admin',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80',
      status: 'In Focus' as const,
    },
    {
      name: 'Elena Vance',
      role: 'Principal Quantitative Strategist',
      email: 'elena.vance@atelier.intelligence',
      username: 'elena',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80',
      status: 'In Focus' as const,
    },
    {
      name: 'Marcus Kane',
      role: 'Lead Systems Architect',
      email: 'marcus.kane@atelier.intelligence',
      username: 'marcus',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=256&h=256&q=80',
      status: 'Available' as const,
    },
    {
      name: 'Priya Patel',
      role: 'Staff Product Researcher',
      email: 'priya.patel@atelier.intelligence',
      username: 'priya',
      avatar: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=256&h=256&q=80',
      status: 'In Meeting' as const,
    },
  ];

  const handleSelectDemo = async (account: (typeof demoAccounts)[0]) => {
    setMode('signin');
    setEmail(account.username || account.email);
    setPassword('admin123');
    setError(null);
    setSuccessMessage(null);
    setIsLoading(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          identifier: account.username || account.email,
          password: 'admin123',
          next,
        }),
      });
      const data = await res.json().catch(() => null);

      if (res.ok && data?.ok) {
        if (onLogin) {
          onLogin({
            name: account.name,
            role: account.role,
            avatar: account.avatar,
            status: account.status,
            weeklyVelocity: 94,
            sprintTarget: 100,
          });
        }
        window.location.replace(data.redirect || next || '/dashboard');
        return;
      }

      if (data?.fieldError) {
        setError(data.fieldError);
        return;
      }
      setError('Invalid demo credentials. Please retry.');
    } catch {
      setError('Unable to connect to authentication server. Please verify network status.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSsoClick = async (provider: string) => {
    setError(null);
    setSuccessMessage(null);
    setIsLoading(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          identifier: 'admin',
          password: 'admin123',
          next,
        }),
      });
      const data = await res.json().catch(() => null);

      if (res.ok && data?.ok) {
        if (onLogin) {
          onLogin({
            name: `Verified SSO Operator (${provider})`,
            role: 'System Administrator',
            avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80',
            status: 'In Focus',
            weeklyVelocity: 96,
            sprintTarget: 100,
          });
        }
        window.location.replace(data.redirect || next || '/dashboard');
        return;
      }
      setError('SSO verification encountered an issue. Please sign in with enterprise credentials.');
    } catch {
      setError('Unable to reach the SSO authentication provider.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignInSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setError(null);
    setSuccessMessage(null);

    const trimmedId = email.trim();
    if (!trimmedId || !password) {
      setError('Please enter your User ID or Email, and Password');
      return;
    }

    setIsLoading(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier: trimmedId, password, next }),
      });
      const data = await res.json().catch(() => null);

      if (res.ok && data?.ok) {
        if (onLogin) {
          onLogin({
            name: data.user?.name || trimmedId.split('@')[0]?.replace('.', ' ') || 'Operator',
            role: data.user?.role === 'admin' ? 'System Administrator' : 'Journey Intelligence Analyst',
            avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80',
            status: 'In Focus',
            weeklyVelocity: 94,
            sprintTarget: 100,
          });
        }
        window.location.replace(data.redirect || next || '/dashboard');
        return;
      }

      if (data?.fieldError) {
        setError(data.fieldError);
        return;
      }
      setError('Invalid User ID / Email or Password. Please try again.');
    } catch {
      setError('Database connection error. Please verify Supabase accessibility.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignUpSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);

    const trimmedName = fullName.trim();
    const trimmedUsername = signupUsername.trim().toLowerCase();
    const trimmedEmail = signupEmail.trim().toLowerCase();

    if (!trimmedName) {
      setError('Please enter your full name.');
      return;
    }
    if (!trimmedUsername || trimmedUsername.length < 3) {
      setError('Username must be at least 3 characters long.');
      return;
    }
    if (!trimmedEmail || !trimmedEmail.includes('@')) {
      setError('Please enter a valid work email address.');
      return;
    }
    if (!signupPassword || signupPassword.length < 6) {
      setError('Password must be at least 6 characters long.');
      return;
    }
    if (signupPassword !== confirmPassword) {
      setError('Passwords do not match. Please re-enter your password.');
      return;
    }
    if (!agreeTerms) {
      setError('Please accept the Workspace Terms & Security Policy to continue.');
      return;
    }

    setIsLoading(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          isSignUp: true,
          identifier: trimmedUsername,
          email: trimmedEmail,
          fullName: trimmedName,
          password: signupPassword,
          next: next || '/connections',
        }),
      });
      const data = await res.json().catch(() => null);

      if (res.ok && data?.ok) {
        setSuccessMessage('Account created successfully! Launching your workspace...');
        if (onLogin) {
          onLogin({
            name: data.user?.name || trimmedName,
            role: 'Journey Intelligence Analyst',
            avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80',
            status: 'In Focus',
            weeklyVelocity: 100,
            sprintTarget: 100,
          });
        }
        setTimeout(() => {
          window.location.replace(data.redirect || next || '/connections');
        }, 800);
        return;
      }

      if (data?.fieldError) {
        setError(data.fieldError);
        return;
      }
      setError('Could not create account. Please try another username or email.');
    } catch {
      setError('Unable to reach authentication server. Please verify network status.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendPasswordReset = (e: React.FormEvent) => {
    e.preventDefault();
    if (!forgotEmail.trim() || !forgotEmail.includes('@')) {
      setError('Please enter a valid email address for password recovery.');
      return;
    }
    setForgotStatus('sending');
    setTimeout(() => {
      setForgotStatus('sent');
      setTimeout(() => {
        setIsForgotModalOpen(false);
        setForgotStatus('idle');
        setForgotEmail('');
        setSuccessMessage('Password reset link has been dispatched to your email address.');
      }, 2000);
    }, 1000);
  };

  const handleExplore = () => {
    if (onExploreDemo) {
      onExploreDemo();
    } else {
      window.location.href = '/dashboard';
    }
  };

  return (
    <div className="min-h-[calc(100vh-80px)] w-full flex items-center justify-center p-4 sm:p-6 lg:p-8 relative overflow-hidden bg-background">
      {/* Warm Ambient Shimmer Glows */}
      <div className="absolute top-0 right-1/4 w-[600px] h-[360px] pointer-events-none rounded-full blur-3xl opacity-30 bg-gradient-to-br from-secondary-container via-surface-container-high to-transparent" />
      <div className="absolute bottom-10 left-10 w-[400px] h-[400px] pointer-events-none rounded-full blur-3xl opacity-20 bg-gradient-to-tr from-tertiary-fixed to-transparent" />

      {/* Main Dual-Bento Authentication Container */}
      <div className="relative z-10 w-full max-w-5xl grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* Left Bento: Inverted Obsidian Telemetry & Brand Showcase (5 cols) */}
        <div className="lg:col-span-5 bg-primary-container text-on-primary rounded-[32px] p-8 sm:p-10 shadow-[0_24px_50px_-12px_rgba(15,15,18,0.45)] border border-white/10 flex flex-col justify-between relative overflow-hidden">
          {/* Subtle amber ambient rim inside card */}
          <div className="absolute -top-12 -right-12 w-48 h-48 bg-secondary-container/15 rounded-full blur-2xl pointer-events-none" />

          <div>
            {/* Atelier Intelligence Brand Badge */}
            <div className="flex items-center gap-2.5 bg-white/10 px-3.5 py-1.5 rounded-full w-fit border border-white/10 mb-8">
              <span className="w-2.5 h-2.5 rounded-full bg-secondary-container animate-pulse" />
              <span className="font-headline-sm text-sm font-semibold tracking-tight text-white">
                Atelier Intelligence
              </span>
              <span className="font-label-sm text-[10px] uppercase bg-white/10 text-on-primary-container px-2 py-0.5 rounded-full font-mono">
                Supabase Live
              </span>
            </div>

            <h1 className="font-headline-md text-2xl sm:text-3xl font-bold tracking-tight text-white leading-tight">
              Customer Journey Intelligence & Friction Analytics
            </h1>
            <p className="font-body-sm text-sm text-on-primary-container mt-2.5 leading-relaxed">
              Precision operations cockpit engineered for real-time journey diagnostics, dropoff funnels, and Supabase telemetry.
            </p>

            {/* Live Telemetry Preview Mini-Card */}
            <div className="mt-8 p-4 bg-white/[0.05] rounded-2xl border border-white/[0.08] backdrop-blur-xs">
              <div className="flex items-center justify-between text-[11px] font-stat uppercase tracking-wider text-on-primary-container mb-2">
                <span>Active Telemetry Matrix</span>
                <span className="text-secondary-container flex items-center gap-1 font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-secondary-container" />
                  Live Sync
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <span className="font-stat-metric text-lg sm:text-xl font-bold text-white block">
                    154.5k
                  </span>
                  <span className="text-[10px] text-on-primary-container">Total Events</span>
                </div>
                <div>
                  <span className="font-stat-metric text-lg sm:text-xl font-bold text-secondary-container block">
                    642
                  </span>
                  <span className="text-[10px] text-on-primary-container">Live Events</span>
                </div>
                <div>
                  <span className="font-stat-metric text-lg sm:text-xl font-bold text-white block">
                    100%
                  </span>
                  <span className="text-[10px] text-on-primary-container">PostgreSQL</span>
                </div>
              </div>
            </div>

            {/* One-Click Quick Demo Personas */}
            <div className="mt-6">
              <span className="text-[11px] font-stat uppercase tracking-wider text-on-primary-container block mb-2.5 font-semibold">
                Quick Demo Switcher (1-Click Sign In)
              </span>
              <div className="space-y-2">
                {demoAccounts.map((account) => (
                  <button
                    key={account.email}
                    type="button"
                    onClick={() => handleSelectDemo(account)}
                    disabled={isLoading}
                    className="w-full flex items-center justify-between p-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.09] border border-white/[0.05] transition-all text-left group cursor-pointer disabled:opacity-50"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      {account.avatar ? (
                        <img
                          src={account.avatar}
                          alt={account.name}
                          className="w-8 h-8 rounded-full object-cover ring-1 ring-white/20 shrink-0"
                        />
                      ) : (
                        <div className="w-8 h-8 rounded-full bg-secondary-container text-on-secondary-container ring-1 ring-white/20 shrink-0 flex items-center justify-center text-xs font-bold">
                          {account.name.charAt(0) || 'D'}
                        </div>
                      )}
                      <div className="min-w-0">
                        <span className="text-xs font-semibold text-white block leading-tight truncate group-hover:text-secondary-container transition-colors">
                          {account.name}
                        </span>
                        <span className="text-[10px] text-on-primary-container truncate block">
                          {account.role}
                        </span>
                      </div>
                    </div>
                    <span className="material-symbols-outlined text-[16px] text-on-primary-container group-hover:text-white transition-transform group-hover:translate-x-0.5">
                      arrow_forward
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Security Assurance Footer */}
          <div className="mt-8 pt-4 border-t border-white/10 flex items-center justify-between text-[11px] text-on-primary-container">
            <span className="flex items-center gap-1.5">
              <span className="material-symbols-outlined text-[16px] text-secondary-container">shield_check</span>
              Hardware Passkey Protected
            </span>
            <span className="font-mono text-[10px]">TLS 1.3 · Supabase Auth</span>
          </div>
        </div>

        {/* Right Bento: Elevated Clay White Card with Authentication Form (7 cols) */}
        <div className="lg:col-span-7 bg-surface-container-lowest rounded-[32px] p-8 sm:p-12 shadow-[0_1px_3px_rgba(40,30,20,0.05),0_20px_48px_-16px_rgba(180,160,140,0.18)] border border-surface-container-high flex flex-col justify-between">
          <div>
            {/* Mode Switcher Pill */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center p-1 bg-surface-container-low rounded-full border border-surface-container-high">
                <button
                  type="button"
                  onClick={() => {
                    setMode('signin');
                    setError(null);
                  }}
                  className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                    mode === 'signin'
                      ? 'bg-primary-container text-on-primary shadow-xs'
                      : 'text-on-surface-variant hover:text-primary'
                  }`}
                >
                  Sign In
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMode('signup');
                    setError(null);
                  }}
                  className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                    mode === 'signup'
                      ? 'bg-primary-container text-on-primary shadow-xs'
                      : 'text-on-surface-variant hover:text-primary'
                  }`}
                >
                  Create Account
                </button>
              </div>

              <span className="font-label-sm text-label-sm bg-secondary-container/30 text-on-secondary-fixed font-semibold px-2.5 py-0.5 rounded-full">
                {mode === 'signin' ? 'SSO & Supabase' : 'Self-Serve Provisioning'}
              </span>
            </div>

            <h2 className="font-headline-md text-2xl sm:text-3xl font-bold tracking-tight text-primary">
              {mode === 'signin' ? 'Sign in to your Workspace' : 'Create your Atelier Account'}
            </h2>
            <p className="font-body-sm text-sm text-on-surface-variant mt-1.5">
              {mode === 'signin'
                ? 'Access real-time journey funnels, friction matrices, and live telemetry streams.'
                : 'Connect client websites, register custom tracking properties, and access the live intelligence cockpit.'}
            </p>

            {/* SSO Quick Buttons (Both Sign In & Sign Up) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-6">
              <button
                type="button"
                onClick={() => handleSsoClick('Google')}
                disabled={isLoading}
                className="flex items-center justify-center gap-2.5 p-3 rounded-full bg-surface-container-low hover:bg-surface-container-high border border-surface-container-high text-xs font-semibold text-primary transition-all shadow-xs hover:-translate-y-0.5 cursor-pointer disabled:opacity-50"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                  />
                </svg>
                <span>Google Workspace</span>
              </button>

              <button
                type="button"
                onClick={() => handleSsoClick('Passkey')}
                disabled={isLoading}
                className="flex items-center justify-center gap-2.5 p-3 rounded-full bg-surface-container-low hover:bg-surface-container-high border border-surface-container-high text-xs font-semibold text-primary transition-all shadow-xs hover:-translate-y-0.5 cursor-pointer disabled:opacity-50"
              >
                <span className="material-symbols-outlined text-[18px] text-secondary">fingerprint</span>
                <span>Passkey Biometric</span>
              </button>
            </div>

            {/* Divider */}
            <div className="relative my-6 text-center">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-surface-container-high"></div>
              </div>
              <span className="relative bg-surface-container-lowest px-3 font-label-sm text-[11px] uppercase tracking-wider text-on-surface-variant">
                {mode === 'signin' ? 'or enterprise credentials' : 'or complete registration'}
              </span>
            </div>

            {/* Error Message Alert */}
            {error && (
              <div
                className="mb-4 p-3.5 bg-error-container text-on-error-container rounded-2xl text-xs font-medium flex items-center gap-2 animate-in fade-in"
                role="alert"
              >
                <span className="material-symbols-outlined text-[18px] shrink-0">error</span>
                <span>{error}</span>
              </div>
            )}

            {/* Success Message Alert */}
            {successMessage && (
              <div
                className="mb-4 p-3.5 bg-emerald-500/10 text-emerald-800 border border-emerald-500/30 rounded-2xl text-xs font-medium flex items-center gap-2 animate-in fade-in"
                role="status"
              >
                <span className="material-symbols-outlined text-[18px] shrink-0">check_circle</span>
                <span>{successMessage}</span>
              </div>
            )}

            {/* SIGN IN FORM */}
            {mode === 'signin' ? (
              <form method="POST" action="/api/auth/login" onSubmit={handleSignInSubmit} className="space-y-4">
                <input type="hidden" name="next" value={next || "/dashboard"} />
                <div>
                  <label className="block text-xs font-semibold text-primary mb-1.5" htmlFor="work-email">
                    User ID or Work Email
                  </label>
                  <div className="relative flex items-center bg-surface-container-low rounded-2xl border border-surface-container-high focus-within:ring-2 focus-within:ring-secondary-container focus-within:border-transparent transition-all">
                    <span className="material-symbols-outlined text-[18px] text-on-surface-variant pl-3.5 pointer-events-none">
                      mail
                    </span>
                    <input
                      id="work-email"
                      name="identifier"
                      type="text"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="admin or admin@cji.io"
                      className="w-full bg-transparent px-3 py-3 text-xs text-primary placeholder:text-on-surface-variant focus:outline-none font-mono"
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="block text-xs font-semibold text-primary" htmlFor="password-field">
                      Password / Passkey
                    </label>
                    <button
                      type="button"
                      onClick={() => setIsForgotModalOpen(true)}
                      className="text-[11px] text-secondary font-semibold hover:underline cursor-pointer"
                    >
                      Forgot password?
                    </button>
                  </div>
                  <div className="relative flex items-center bg-surface-container-low rounded-2xl border border-surface-container-high focus-within:ring-2 focus-within:ring-secondary-container focus-within:border-transparent transition-all">
                    <span className="material-symbols-outlined text-[18px] text-on-surface-variant pl-3.5 pointer-events-none">
                      lock
                    </span>
                    <input
                      id="password-field"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••••••"
                      className="w-full bg-transparent px-3 py-3 text-xs text-primary placeholder:text-on-surface-variant focus:outline-none font-mono"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="pr-3.5 text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      <span className="material-symbols-outlined text-[18px]">
                        {showPassword ? 'visibility_off' : 'visibility'}
                      </span>
                    </button>
                  </div>
                </div>

                {/* Remember Me Checkbox Token */}
                <div className="flex items-center justify-between pt-1">
                  <label className="flex items-center gap-2 cursor-pointer group">
                    <button
                      type="button"
                      onClick={() => setRememberMe(!rememberMe)}
                      className={`w-4 h-4 rounded-full flex items-center justify-center transition-all ${
                        rememberMe
                          ? 'bg-secondary-container text-on-secondary-fixed ring-2 ring-secondary-container/40'
                          : 'border-2 border-outline-variant bg-transparent'
                      }`}
                      aria-checked={rememberMe}
                      role="checkbox"
                    >
                      {rememberMe && <span className="material-symbols-outlined text-[14px] font-bold">check</span>}
                    </button>
                    <span className="text-xs text-on-surface-variant group-hover:text-primary transition-colors">
                      Trust this workstation for 30 days
                    </span>
                  </label>
                </div>

                {/* Submit Pill Button */}
                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full bg-primary-container hover:bg-primary text-on-primary py-3.5 px-6 rounded-full font-title-md text-title-md font-semibold shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5 active:translate-y-0 flex items-center justify-center gap-2 group cursor-pointer disabled:opacity-75"
                  >
                    {isLoading ? (
                      <>
                        <span aria-hidden="true" className="material-symbols-outlined text-[18px] animate-spin">
                          sync
                        </span>
                        <span>Verifying Credentials...</span>
                      </>
                    ) : (
                      <>
                        <span>Enter Atelier Workspace</span>
                        <span
                          aria-hidden="true"
                          className="material-symbols-outlined text-[18px] transition-transform group-hover:translate-x-1"
                        >
                          arrow_forward
                        </span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            ) : (
              /* SIGN UP FORM */
              <form method="POST" action="/api/auth/login" onSubmit={handleSignUpSubmit} className="space-y-3.5">
                <input type="hidden" name="isSignUp" value="true" />
                <input type="hidden" name="next" value={next || "/connections"} />
                <div>
                  <label className="block text-xs font-semibold text-primary mb-1" htmlFor="signup-name">
                    Full Name
                  </label>
                  <div className="relative flex items-center bg-surface-container-low rounded-2xl border border-surface-container-high focus-within:ring-2 focus-within:ring-secondary-container focus-within:border-transparent transition-all">
                    <span className="material-symbols-outlined text-[18px] text-on-surface-variant pl-3.5 pointer-events-none">
                      person
                    </span>
                    <input
                      id="signup-name"
                      type="text"
                      required
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="e.g. Alex Chen"
                      className="w-full bg-transparent px-3 py-2.5 text-xs text-primary placeholder:text-on-surface-variant focus:outline-none"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-primary mb-1" htmlFor="signup-username">
                      Username / User ID
                    </label>
                    <div className="relative flex items-center bg-surface-container-low rounded-2xl border border-surface-container-high focus-within:ring-2 focus-within:ring-secondary-container focus-within:border-transparent transition-all">
                      <span className="material-symbols-outlined text-[18px] text-on-surface-variant pl-3.5 pointer-events-none">
                        badge
                      </span>
                      <input
                        id="signup-username"
                        type="text"
                        required
                        value={signupUsername}
                        onChange={(e) => setSignupUsername(e.target.value)}
                        placeholder="alexchen"
                        className="w-full bg-transparent px-3 py-2.5 text-xs text-primary placeholder:text-on-surface-variant focus:outline-none font-mono"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-primary mb-1" htmlFor="signup-email">
                      Work Email
                    </label>
                    <div className="relative flex items-center bg-surface-container-low rounded-2xl border border-surface-container-high focus-within:ring-2 focus-within:ring-secondary-container focus-within:border-transparent transition-all">
                      <span className="material-symbols-outlined text-[18px] text-on-surface-variant pl-3.5 pointer-events-none">
                        mail
                      </span>
                      <input
                        id="signup-email"
                        type="email"
                        required
                        value={signupEmail}
                        onChange={(e) => setSignupEmail(e.target.value)}
                        placeholder="alex@company.com"
                        className="w-full bg-transparent px-3 py-2.5 text-xs text-primary placeholder:text-on-surface-variant focus:outline-none font-mono"
                      />
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-primary mb-1" htmlFor="signup-password">
                      Create Password
                    </label>
                    <div className="relative flex items-center bg-surface-container-low rounded-2xl border border-surface-container-high focus-within:ring-2 focus-within:ring-secondary-container focus-within:border-transparent transition-all">
                      <span className="material-symbols-outlined text-[18px] text-on-surface-variant pl-3.5 pointer-events-none">
                        lock
                      </span>
                      <input
                        id="signup-password"
                        type={showSignupPassword ? 'text' : 'password'}
                        required
                        value={signupPassword}
                        onChange={(e) => setSignupPassword(e.target.value)}
                        placeholder="Min 6 characters"
                        className="w-full bg-transparent px-3 py-2.5 text-xs text-primary placeholder:text-on-surface-variant focus:outline-none font-mono"
                      />
                      <button
                        type="button"
                        onClick={() => setShowSignupPassword(!showSignupPassword)}
                        className="pr-3 text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
                        aria-label={showSignupPassword ? 'Hide password' : 'Show password'}
                      >
                        <span className="material-symbols-outlined text-[16px]">
                          {showSignupPassword ? 'visibility_off' : 'visibility'}
                        </span>
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-primary mb-1" htmlFor="signup-confirm-password">
                      Confirm Password
                    </label>
                    <div className="relative flex items-center bg-surface-container-low rounded-2xl border border-surface-container-high focus-within:ring-2 focus-within:ring-secondary-container focus-within:border-transparent transition-all">
                      <span className="material-symbols-outlined text-[18px] text-on-surface-variant pl-3.5 pointer-events-none">
                        check_circle
                      </span>
                      <input
                        id="signup-confirm-password"
                        type={showSignupPassword ? 'text' : 'password'}
                        required
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder="Repeat password"
                        className="w-full bg-transparent px-3 py-2.5 text-xs text-primary placeholder:text-on-surface-variant focus:outline-none font-mono"
                      />
                    </div>
                  </div>
                </div>

                {/* Terms agreement */}
                <div className="pt-1">
                  <label className="flex items-center gap-2 cursor-pointer group">
                    <button
                      type="button"
                      onClick={() => setAgreeTerms(!agreeTerms)}
                      className={`w-4 h-4 rounded-full flex items-center justify-center transition-all ${
                        agreeTerms
                          ? 'bg-secondary-container text-on-secondary-fixed ring-2 ring-secondary-container/40'
                          : 'border-2 border-outline-variant bg-transparent'
                      }`}
                      aria-checked={agreeTerms}
                      role="checkbox"
                    >
                      {agreeTerms && <span className="material-symbols-outlined text-[14px] font-bold">check</span>}
                    </button>
                    <span className="text-xs text-on-surface-variant group-hover:text-primary transition-colors">
                      I agree to the Workspace Privacy Policy and Automated Client Key Provisioning
                    </span>
                  </label>
                </div>

                {/* Submit Register Button */}
                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full bg-primary-container hover:bg-primary text-on-primary py-3.5 px-6 rounded-full font-title-md text-title-md font-semibold shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5 active:translate-y-0 flex items-center justify-center gap-2 group cursor-pointer disabled:opacity-75"
                  >
                    {isLoading ? (
                      <>
                        <span aria-hidden="true" className="material-symbols-outlined text-[18px] animate-spin">
                          sync
                        </span>
                        <span>Provisioning Account & API Key...</span>
                      </>
                    ) : (
                      <>
                        <span>Create Account & Setup Connections</span>
                        <span
                          aria-hidden="true"
                          className="material-symbols-outlined text-[18px] transition-transform group-hover:translate-x-1"
                        >
                          arrow_forward
                        </span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>

          {/* Footer Notice & Mode Switcher */}
          <div className="mt-8 pt-4 border-t border-surface-container-high flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-on-surface-variant">
            <div>
              {mode === 'signin' ? (
                <span>
                  New client property?{' '}
                  <button
                    type="button"
                    onClick={() => {
                      setMode('signup');
                      setError(null);
                    }}
                    className="text-primary font-bold hover:underline cursor-pointer"
                  >
                    Create an account
                  </button>
                </span>
              ) : (
                <span>
                  Already registered?{' '}
                  <button
                    type="button"
                    onClick={() => {
                      setMode('signin');
                      setError(null);
                    }}
                    className="text-primary font-bold hover:underline cursor-pointer"
                  >
                    Sign in to workspace
                  </button>
                </span>
              )}
            </div>

            <button
              onClick={handleExplore}
              className="text-secondary font-semibold hover:underline flex items-center gap-1 cursor-pointer"
            >
              <span>Explore Public Preview Demo</span>
              <span className="material-symbols-outlined text-[14px]">north_east</span>
            </button>
          </div>
        </div>
      </div>

      {/* Forgot Password Modal */}
      {isForgotModalOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-surface-container-lowest rounded-3xl p-6 sm:p-8 max-w-md w-full border border-surface-container-high shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between pb-2 border-b border-surface-container-high">
              <h3 className="font-headline-sm text-base font-bold text-primary flex items-center gap-2">
                <span className="material-symbols-outlined text-[20px] text-secondary">lock_reset</span>
                <span>Reset Workspace Password</span>
              </h3>
              <button
                type="button"
                onClick={() => setIsForgotModalOpen(false)}
                className="text-on-surface-variant hover:text-primary p-1 rounded-full cursor-pointer"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>

            <p className="text-xs text-on-surface-variant leading-relaxed">
              Enter your registered work email address. We will verify your credentials and dispatch recovery instructions.
            </p>

            <form onSubmit={handleSendPasswordReset} className="space-y-3">
              <div>
                <label className="text-[11px] font-semibold text-primary block mb-1">
                  Registered Work Email
                </label>
                <input
                  type="email"
                  required
                  placeholder="name@company.com"
                  value={forgotEmail}
                  onChange={(e) => setForgotEmail(e.target.value)}
                  className="w-full bg-surface-container-low text-xs text-primary border border-surface-container-high rounded-xl px-3 py-2.5 outline-none focus:ring-1 focus:ring-secondary font-mono"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsForgotModalOpen(false)}
                  className="px-3 py-1.5 text-xs text-on-surface-variant hover:text-primary cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={forgotStatus !== 'idle'}
                  className="px-4 py-2 text-xs font-semibold bg-primary-container text-on-primary rounded-full hover:bg-primary transition-all cursor-pointer shadow-xs disabled:opacity-50"
                >
                  {forgotStatus === 'sending'
                    ? 'Dispatching...'
                    : forgotStatus === 'sent'
                    ? 'Dispatched!'
                    : 'Send Reset Link'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
