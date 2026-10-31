"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { signOut } from "@/app/actions";
import type { Role } from "@/lib/session-core";
/** Atelier header: brand, signed-in token and a confirmed sign-out. */
export function AtelierNavbar({ label, role }: { readonly label: string; readonly role: Role }) {
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!confirming) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setConfirming(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirming]);

  return (
    <>
      <header className="sticky top-0 left-0 right-0 z-50 bg-surface/85 backdrop-blur-xl border-b border-surface-container-high/60">
        <div className="h-20 w-full px-gutter md:px-margin-desktop flex items-center justify-between gap-space-lg">
          <Link
            href="/"
            aria-label="Customer Journey Intelligence home"
            className="flex items-center gap-space-sm bg-surface-container-lowest px-space-md py-space-sm rounded-full shadow-[0_1px_2px_rgba(40,30,20,0.04)] no-underline"
          >
            <span className="w-2.5 h-2.5 rounded-full bg-secondary-container animate-pulse" aria-hidden="true" />
            <span className="font-headline-sm text-headline-sm tracking-tight text-primary">CJI</span>
            <span className="font-label-sm text-label-sm uppercase bg-surface-container-high text-on-surface-variant px-space-xs py-0.5 rounded-full">
              Atelier
            </span>
          </Link>

          <div className="flex items-center gap-space-sm flex-shrink-0">
            <span className="hidden sm:flex items-center gap-2 bg-surface-container-lowest rounded-full pl-1 pr-4 py-1 text-xs text-on-surface-variant shadow-[0_1px_2px_rgba(40,30,20,0.04)]">
              <span className="w-8 h-8 rounded-full bg-primary text-on-primary flex items-center justify-center" aria-hidden="true">
                <span className="material-symbols-outlined text-[18px]">person</span>
              </span>
              <span>
                Signed in as <strong className="text-primary">{label}</strong> ({role})
              </span>
            </span>
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="flex items-center gap-1.5 bg-primary-container hover:bg-primary text-on-primary text-xs font-semibold px-4 py-2.5 rounded-full shadow-sm transition-all cursor-pointer border-0"
            >
              <span className="material-symbols-outlined text-[16px]" aria-hidden="true">logout</span>
              <span>Sign out</span>
            </button>
          </div>
        </div>
      </header>

      {confirming ? (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="signout-title"
            className="w-full max-w-md bg-surface-container-lowest rounded-[32px] p-6 sm:p-8 shadow-[0_24px_50px_-12px_rgba(0,0,0,0.3)] border border-surface-container-high"
          >
            <div className="flex items-center gap-2 mb-4">
              <span className="w-9 h-9 rounded-full bg-secondary-container/20 flex items-center justify-center text-secondary" aria-hidden="true">
                <span className="material-symbols-outlined text-[20px]">logout</span>
              </span>
              <div>
                <span className="font-label-sm text-[10px] uppercase tracking-wider text-on-surface-variant block">Session control</span>
                <h2 id="signout-title" className="font-title-md text-base font-bold text-primary m-0">Confirm sign out</h2>
              </div>
            </div>
            <p className="text-xs text-on-surface-variant mb-4 leading-relaxed">
              This ends your session as <strong>{label}</strong>. The API token is removed from the server session and you will need to enter it again.
            </p>
            <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-surface-container-high">
              <button
                type="button"
                autoFocus
                onClick={() => setConfirming(false)}
                className="px-4 py-2 rounded-full text-xs font-medium text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors cursor-pointer bg-transparent border-0"
              >
                Stay signed in
              </button>
              <form action={signOut} className="m-0">
                <button
                  type="submit"
                  className="px-5 py-2.5 rounded-full text-xs font-semibold bg-primary-container hover:bg-primary text-on-primary shadow-sm transition-all flex items-center gap-1.5 cursor-pointer border-0"
                >
                  <span className="material-symbols-outlined text-[16px]" aria-hidden="true">logout</span>
                  <span>Sign out</span>
                </button>
              </form>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
