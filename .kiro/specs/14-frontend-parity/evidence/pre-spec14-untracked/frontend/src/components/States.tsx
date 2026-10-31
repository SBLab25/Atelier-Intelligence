import type { ReactNode } from "react";

/** Placeholder while a region loads; announced politely to screen readers. */
export function Loading({ label }: { readonly label: string }) {
  return (
    <div className="loading" role="status" aria-live="polite" aria-busy="true">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

/** An explicit "nothing here" message (not an error). */
export function EmptyState({ children }: { readonly children: ReactNode }) {
  return (
    <p className="empty" role="status">
      {children}
    </p>
  );
}

const TONES: Readonly<Record<string, string>> = {
  ok: "good",
  completed: "good",
  approved: "good",
  running: "info",
  awaiting_approval: "warn",
  degraded: "warn",
  unavailable: "bad",
  failed: "bad",
};

/** Status as text with a colored marker; the text carries the meaning (not color alone). */
export function StatusBadge({ status }: { readonly status: string }) {
  const tone = TONES[status] ?? "neutral";
  return (
    <span className={`badge badge-${tone}`}>
      <span className="badge-dot" aria-hidden="true" />
      {status.replaceAll("_", " ")}
    </span>
  );
}

/** Formats an ISO timestamp as UTC text inside a <time> element. */
export function Timestamp({ value }: { readonly value: string | null | undefined }) {
  if (!value) {
    return <span>—</span>;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return <span>{value}</span>;
  }
  const text = `${date.toISOString().slice(0, 19).replace("T", " ")} UTC`;
  return <time dateTime={date.toISOString()}>{text}</time>;
}
