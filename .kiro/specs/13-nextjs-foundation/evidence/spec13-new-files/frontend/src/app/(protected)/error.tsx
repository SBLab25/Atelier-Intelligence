"use client";

import Link from "next/link";

/**
 * Last-resort boundary for unexpected exceptions (API problems are rendered as values by the views). Production
 * builds pass only a digest, which matches the server log entry.
 */
export default function PageError({ error, retry }: { readonly error: unknown; readonly retry: () => void }) {
  const digest =
    typeof error === "object" && error !== null && "digest" in error && typeof error.digest === "string"
      ? error.digest
      : null;
  return (
    <section className="problem" role="alert">
      <h1 className="problem-heading">This page could not be shown</h1>
      <p>An unexpected error happened while rendering. Retry, or go back to the status page.</p>
      {digest ? (
        <p>
          Reference: <code>{digest}</code>
        </p>
      ) : null}
      <div className="actions">
        <button type="button" className="button" onClick={() => retry()}>
          Retry
        </button>
        <Link href="/">Status page</Link>
      </div>
    </section>
  );
}
