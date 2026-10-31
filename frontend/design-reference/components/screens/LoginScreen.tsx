import React, { useState } from 'react';
import { validateEmail, validatePassword } from '../../utils/auth';
import { UserProfile } from '../../types';

interface LoginScreenProps {
  onLogin: (user: UserProfile) => void;
  onExploreDemo: () => void;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({ onLogin, onExploreDemo }) => {
  const [email, setEmail] = useState('elena.vance@atelier.intelligence');
  const [password, setPassword] = useState('••••••••••••');
  const [rememberMe, setRememberMe] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const demoAccounts: { name: string; role: string; email: string; avatar: string; status: 'In Focus' | 'Available' | 'In Meeting' }[] = [
    {
      name: 'Elena Vance',
      role: 'Principal Quantitative Strategist',
      email: 'elena.vance@atelier.intelligence',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80',
      status: 'In Focus',
    },
    {
      name: 'Marcus Kane',
      role: 'Lead Systems Architect',
      email: 'marcus.kane@atelier.intelligence',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=256&h=256&q=80',
      status: 'Available',
    },
    {
      name: 'Priya Patel',
      role: 'Staff Product Researcher',
      email: 'priya.patel@atelier.intelligence',
      avatar: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=256&h=256&q=80',
      status: 'In Meeting',
    },
  ];

  const handleSelectDemo = (account: typeof demoAccounts[0]) => {
    setEmail(account.email);
    setPassword('atelier-passkey-2026');
    setError(null);
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      onLogin({
        name: account.name,
        role: account.role,
        avatar: account.avatar,
        status: account.status,
        weeklyVelocity: 94,
        sprintTarget: 100,
      });
    }, 400);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!validateEmail(email)) {
      setError('Please enter a valid work email address');
      return;
    }

    const pwCheck = validatePassword(password);
    if (!pwCheck.valid) {
      setError(pwCheck.reason || 'Invalid password');
      return;
    }

    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      const matched = demoAccounts.find((a) => a.email.toLowerCase() === email.toLowerCase());
      onLogin({
        name: matched ? matched.name : email.split('@')[0].replace('.', ' '),
        role: matched ? matched.role : 'Quantitative Analyst',
        avatar: matched ? matched.avatar : 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&h=256&q=80',
        status: matched ? matched.status : 'In Focus',
        weeklyVelocity: 88,
        sprintTarget: 100,
      });
    }, 600);
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
              <span className="font-label-sm text-[10px] uppercase bg-white/10 text-on-primary-container px-2 py-0.5 rounded-full">
                v2.4
              </span>
            </div>

            <h1 className="font-headline-md text-2xl sm:text-3xl font-bold tracking-tight text-white leading-tight">
              Tactile Intelligence & Quantitative Sprints
            </h1>
            <p className="font-body-sm text-sm text-on-primary-container mt-2.5 leading-relaxed">
              Precision operations cockpit engineered for high-velocity teams, live telemetry diagnostics, and tactile bento telemetry.
            </p>

            {/* Live Telemetry Preview Mini-Card */}
            <div className="mt-8 p-4 bg-white/[0.05] rounded-2xl border border-white/[0.08] backdrop-blur-xs">
              <div className="flex items-center justify-between text-[11px] font-stat uppercase tracking-wider text-on-primary-container mb-2">
                <span>Active Sprint Telemetry</span>
                <span className="text-secondary-container flex items-center gap-1 font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-secondary-container" />
                  Live Sync
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <span className="font-stat-metric text-lg sm:text-xl font-bold text-white block">
                    142.8k
                  </span>
                  <span className="text-[10px] text-on-primary-container">Sessions</span>
                </div>
                <div>
                  <span className="font-stat-metric text-lg sm:text-xl font-bold text-secondary-container block">
                    3.8/10
                  </span>
                  <span className="text-[10px] text-on-primary-container">Friction</span>
                </div>
                <div>
                  <span className="font-stat-metric text-lg sm:text-xl font-bold text-white block">
                    94.2%
                  </span>
                  <span className="text-[10px] text-on-primary-container">Accuracy</span>
                </div>
              </div>
            </div>

            {/* One-Click Quick Demo Personas */}
            <div className="mt-6">
              <span className="text-[11px] font-stat uppercase tracking-wider text-on-primary-container block mb-2.5">
                Quick Demo Switcher (1-Click Sign In)
              </span>
              <div className="space-y-2">
                {demoAccounts.map((account) => (
                  <button
                    key={account.email}
                    type="button"
                    onClick={() => handleSelectDemo(account)}
                    className="w-full flex items-center justify-between p-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.09] border border-white/[0.05] transition-all text-left group"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <img
                        src={account.avatar}
                        alt={account.name}
                        className="w-8 h-8 rounded-full object-cover ring-1 ring-white/20 shrink-0"
                      />
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
            <span className="font-mono text-[10px]">TLS 1.3 · AES-256</span>
          </div>
        </div>

        {/* Right Bento: Elevated Clay White Card with Authentication Form (7 cols) */}
        <div className="lg:col-span-7 bg-surface-container-lowest rounded-[32px] p-8 sm:p-12 shadow-[0_1px_3px_rgba(40,30,20,0.05),0_20px_48px_-16px_rgba(180,160,140,0.18)] border border-surface-container-high flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="font-label-md text-label-md text-on-surface-variant font-medium">
                Workspace Authentication
              </span>
              <span className="font-label-sm text-label-sm bg-secondary-container/30 text-on-secondary-fixed font-semibold px-2.5 py-0.5 rounded-full">
                SSO Enabled
              </span>
            </div>

            <h2 className="font-headline-md text-2xl sm:text-3xl font-bold tracking-tight text-primary">
              Sign in to your Workspace
            </h2>
            <p className="font-body-sm text-sm text-on-surface-variant mt-1.5">
              Access your team telemetry, bento velocity boards, and real-time sprint pipelines.
            </p>

            {/* SSO Quick Buttons */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-6">
              <button
                type="button"
                onClick={() => handleSelectDemo(demoAccounts[0])}
                className="flex items-center justify-center gap-2.5 p-3 rounded-full bg-surface-container-low hover:bg-surface-container-high border border-surface-container-high text-xs font-semibold text-primary transition-all shadow-xs hover:-translate-y-0.5"
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
                onClick={() => handleSelectDemo(demoAccounts[0])}
                className="flex items-center justify-center gap-2.5 p-3 rounded-full bg-surface-container-low hover:bg-surface-container-high border border-surface-container-high text-xs font-semibold text-primary transition-all shadow-xs hover:-translate-y-0.5"
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
                or enterprise credentials
              </span>
            </div>

            {/* Error Message */}
            {error && (
              <div className="mb-4 p-3 bg-error-container text-on-error-container rounded-2xl text-xs font-medium flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px]">error</span>
                <span>{error}</span>
              </div>
            )}

            {/* Credentials Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-primary mb-1.5" htmlFor="work-email">
                  Work Email Address
                </label>
                <div className="relative flex items-center bg-surface-container-low rounded-2xl border border-surface-container-high focus-within:ring-2 focus-within:ring-secondary-container focus-within:border-transparent transition-all">
                  <span className="material-symbols-outlined text-[18px] text-on-surface-variant pl-3.5 pointer-events-none">
                    mail
                  </span>
                  <input
                    id="work-email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@atelier.intelligence"
                    className="w-full bg-transparent px-3 py-3 text-xs text-primary placeholder:text-on-surface-variant focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-semibold text-primary" htmlFor="password-field">
                    Password / Token
                  </label>
                  <button
                    type="button"
                    onClick={() => alert('Password reset link sent to your administrator.')}
                    className="text-[11px] text-secondary font-semibold hover:underline"
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
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your security token"
                    className="w-full bg-transparent px-3 py-3 text-xs text-primary placeholder:text-on-surface-variant focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="pr-3.5 text-on-surface-variant hover:text-primary transition-colors"
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
                  className="w-full bg-primary-container hover:bg-primary text-on-primary py-3.5 px-6 rounded-full font-title-md text-title-md font-semibold shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5 active:translate-y-0 flex items-center justify-center gap-2 group disabled:opacity-75"
                >
                  {isLoading ? (
                    <>
                      <span className="material-symbols-outlined text-[18px] animate-spin">sync</span>
                      <span>Verifying Credentials...</span>
                    </>
                  ) : (
                    <>
                      <span>Enter Atelier Workspace</span>
                      <span className="material-symbols-outlined text-[18px] transition-transform group-hover:translate-x-1">
                        arrow_forward
                      </span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>

          {/* Footer Notice */}
          <div className="mt-8 pt-4 border-t border-surface-container-high flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-on-surface-variant">
            <span>New operator onboarding? Contact sysadmin</span>
            <button
              onClick={onExploreDemo}
              className="text-secondary font-semibold hover:underline flex items-center gap-1"
            >
              <span>Explore Public Preview Demo</span>
              <span className="material-symbols-outlined text-[14px]">north_east</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
