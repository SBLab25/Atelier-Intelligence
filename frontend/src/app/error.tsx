"use client";

import Link from "next/link";

export default function RootError({
  error,
  reset,
}: {
  readonly error: Error & { digest?: string };
  readonly reset: () => void;
}) {
  return (
    <main className="min-h-screen w-full flex items-center justify-center p-4 bg-background">
      <div className="w-full max-w-md bg-surface-container-lowest rounded-[32px] p-8 sm:p-10 shadow-lg border border-surface-container-high text-center">
        <div className="w-12 h-12 mx-auto mb-4 rounded-2xl bg-amber-500/10 flex items-center justify-center text-amber-600">
          <span className="material-symbols-outlined text-2xl">warning</span>
        </div>
        <h1 className="text-xl font-bold text-primary mb-2">Something went wrong</h1>
        <p className="text-sm text-on-surface-variant mb-6">
          {error?.message || "An unexpected error occurred while loading this view."}
        </p>
        <div className="flex gap-3 justify-center">
          <button
            type="button"
            onClick={() => reset()}
            className="px-5 py-2.5 bg-primary-container text-on-primary text-sm font-semibold rounded-full hover:bg-primary transition cursor-pointer"
          >
            Try again
          </button>
          <Link
            href="/login"
            className="px-5 py-2.5 bg-surface-container-high text-on-surface text-sm font-semibold rounded-full hover:bg-surface-container transition"
          >
            Back to Sign in
          </Link>
        </div>
      </div>
    </main>
  );
}

