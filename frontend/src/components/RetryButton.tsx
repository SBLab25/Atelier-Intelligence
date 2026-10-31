"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

/** Re-runs the page's server loaders without a full reload (Spec 13, OD-135). */
export function RetryButton({ label = "Retry" }: { readonly label?: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <button
      type="button"
      className="button"
      onClick={() => startTransition(() => router.refresh())}
      disabled={pending}
      aria-busy={pending}
    >
      {pending ? "Retrying…" : label}
    </button>
  );
}
