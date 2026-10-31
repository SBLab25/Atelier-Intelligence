import React from 'react';
import { UserProfile } from '../../types';

interface SignedOutScreenProps {
  onSignInAgain: () => void;
  onExploreCockpit: () => void;
  lastUser?: UserProfile;
}

export const SignedOutScreen: React.FC<SignedOutScreenProps> = ({
  onSignInAgain,
  onExploreCockpit,
  lastUser,
}) => {
  return (
    <div className="min-h-[calc(100vh-80px)] w-full flex items-center justify-center p-4 sm:p-6 lg:p-8 relative overflow-hidden bg-background">
      {/* Warm Ambient Shimmer Glows */}
      <div className="absolute top-0 right-1/3 w-[550px] h-[340px] pointer-events-none rounded-full blur-3xl opacity-30 bg-gradient-to-br from-secondary-container via-surface-container-high to-transparent" />
      <div className="absolute bottom-10 left-1/4 w-[380px] h-[380px] pointer-events-none rounded-full blur-3xl opacity-20 bg-gradient-to-tr from-secondary-fixed to-transparent" />

      {/* Main Signed Out Bento Canister */}
      <div className="relative z-10 w-full max-w-xl bg-surface-container-lowest rounded-[32px] p-8 sm:p-12 shadow-[0_1px_3px_rgba(40,30,20,0.05),0_20px_48px_-16px_rgba(180,160,140,0.18)] border border-surface-container-high text-center flex flex-col items-center">
        {/* Status Check Capsule with Sage Green */}
        <div className="w-16 h-16 rounded-full bg-surface-container-low flex items-center justify-center text-primary mb-6 shadow-sm border border-surface-container-high relative">
          <div className="w-10 h-10 rounded-full bg-secondary-container/20 flex items-center justify-center">
            <span className="material-symbols-outlined text-[26px] text-secondary">
              check_circle
            </span>
          </div>
          <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-secondary-container animate-ping" />
        </div>

        <div className="inline-flex items-center gap-2 bg-surface-container-high px-3 py-1 rounded-full text-on-surface-variant font-label-sm text-label-sm uppercase tracking-wider mb-2">
          <span>Session Concluded</span>
          <span className="w-1.5 h-1.5 rounded-full bg-secondary"></span>
          <span>Zero-Trust Safe</span>
        </div>

        <h1 className="font-headline-md text-2xl sm:text-3xl font-bold tracking-tight text-primary mt-1">
          You have safely signed out
        </h1>
        <p className="font-body-sm text-sm text-on-surface-variant mt-2 max-w-md leading-relaxed">
          Your workstation passkey tokens have been securely de-authenticated. All sprint telemetry and deliverables were saved to cloud records.
        </p>

        {/* Previous Operator Card Preview */}
        {lastUser && (
          <div className="my-6 p-4 w-full bg-surface-container-low rounded-2xl border border-surface-container-high flex items-center justify-between text-left">
            <div className="flex items-center gap-3">
              <img
                src={lastUser.avatar}
                alt={lastUser.name}
                className="w-10 h-10 rounded-full object-cover ring-2 ring-white shadow-xs"
              />
              <div>
                <span className="text-xs font-bold text-primary block leading-tight">
                  {lastUser.name}
                </span>
                <span className="text-[11px] text-on-surface-variant block">
                  {lastUser.role}
                </span>
              </div>
            </div>
            <span className="font-label-sm text-[10px] uppercase font-semibold bg-surface-container-high text-on-surface-variant px-2.5 py-1 rounded-full">
              Logged Out
            </span>
          </div>
        )}

        {/* Telemetry Summary Bento Grid */}
        <div className="w-full grid grid-cols-3 gap-2.5 my-2 p-3 bg-surface-container-low/70 rounded-2xl border border-surface-container-high">
          <div className="p-2.5 bg-surface-container-lowest rounded-xl text-center">
            <span className="font-label-sm text-[10px] uppercase text-on-surface-variant block">
              Session Time
            </span>
            <span className="font-stat-metric text-base font-bold text-primary block mt-0.5">
              02:35:14
            </span>
          </div>
          <div className="p-2.5 bg-surface-container-lowest rounded-xl text-center">
            <span className="font-label-sm text-[10px] uppercase text-on-surface-variant block">
              Deliverables
            </span>
            <span className="font-stat-metric text-base font-bold text-secondary block mt-0.5">
              4 Updated
            </span>
          </div>
          <div className="p-2.5 bg-surface-container-lowest rounded-xl text-center">
            <span className="font-label-sm text-[10px] uppercase text-on-surface-variant block">
              Sync Health
            </span>
            <span className="font-stat-metric text-base font-bold text-primary block mt-0.5">
              100% OK
            </span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="w-full flex flex-col sm:flex-row items-center justify-center gap-3 mt-8">
          <button
            onClick={onSignInAgain}
            className="w-full sm:w-auto bg-primary-container hover:bg-primary text-on-primary font-title-md text-title-md px-8 py-3 rounded-full font-semibold shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5 flex items-center justify-center gap-2 group"
          >
            <span>Sign Back In</span>
            <span className="material-symbols-outlined text-[18px] transition-transform group-hover:translate-x-1">
              login
            </span>
          </button>

          <button
            onClick={onExploreCockpit}
            className="w-full sm:w-auto bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-title-md text-title-md px-6 py-3 rounded-full font-semibold transition-colors"
          >
            Explore Public Demo
          </button>
        </div>

        {/* Security Timestamp */}
        <div className="mt-8 pt-4 border-t border-surface-container-high w-full flex items-center justify-between text-[11px] text-on-surface-variant">
          <span>Atelier Architecture SSO Guard</span>
          <span className="font-mono text-[10px]">Session Token Cleared</span>
        </div>
      </div>
    </div>
  );
};
