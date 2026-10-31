"use client";

import React from 'react';
import { UserProfile } from '../../types';

interface SignOutModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirmSignOut: () => void;
  user: UserProfile;
}

export const SignOutModal: React.FC<SignOutModalProps> = ({
  isOpen,
  onClose,
  onConfirmSignOut,
  user,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-200">
      <div
        className="w-full max-w-md bg-surface-container-lowest rounded-[32px] p-6 sm:p-8 shadow-[0_24px_50px_-12px_rgba(0,0,0,0.3)] border border-surface-container-high text-left relative"
        role="dialog"
        aria-modal="true"
        aria-labelledby="signout-dialog-title"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-full bg-secondary-container/20 flex items-center justify-center text-secondary">
              <span className="material-symbols-outlined text-[20px]">logout</span>
            </div>
            <div>
              <span className="font-label-sm text-[10px] uppercase tracking-wider text-on-surface-variant block">
                Session Control
              </span>
              <h2 id="signout-dialog-title" className="font-title-md text-base font-bold text-primary">
                Confirm Sign Out
              </h2>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-on-surface-variant flex items-center justify-center transition-colors"
            aria-label="Close dialog"
          >
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>

        <p className="font-body-sm text-xs text-on-surface-variant mb-4 leading-relaxed">
          Are you sure you want to end your current session in the Atelier Intelligence cockpit?
        </p>

        {/* Current Operator Info */}
        <div className="p-3.5 bg-surface-container-low rounded-2xl border border-surface-container-high flex items-center gap-3 mb-4">
          {user.avatar ? (
            <img
              src={user.avatar}
              alt={user.name}
              className="w-10 h-10 rounded-full object-cover ring-2 ring-white shadow-xs"
            />
          ) : (
            <div className="w-10 h-10 rounded-full bg-primary-container text-on-primary ring-2 ring-white shadow-xs flex items-center justify-center font-bold text-sm">
              {user.name.slice(0, 2).toUpperCase() || 'OP'}
            </div>
          )}
          <div>
            <span className="text-xs font-bold text-primary block leading-tight">
              {user.name}
            </span>
            <span className="text-[11px] text-on-surface-variant block">
              {user.role}
            </span>
            <span className="inline-flex items-center gap-1 font-label-sm text-[9px] text-secondary font-medium mt-0.5">
              <span className="w-1 h-1 rounded-full bg-secondary"></span>
              Sprint 42 Telemetry Synchronized
            </span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-surface-container-high">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-full font-label-md text-xs font-medium text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors"
          >
            Stay in Workspace
          </button>

          <button
            type="button"
            onClick={onConfirmSignOut}
            className="px-5 py-2.5 rounded-full font-title-md text-xs font-semibold bg-tertiary-container hover:bg-tertiary text-on-tertiary shadow-sm transition-all hover:-translate-y-0.5 active:translate-y-0 flex items-center gap-1.5"
          >
            <span className="material-symbols-outlined text-[16px]">logout</span>
            <span>Sign Out</span>
          </button>
        </div>
      </div>
    </div>
  );
};
