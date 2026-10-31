import type { ReactNode } from "react";

import { Shell } from "@/components/Shell";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

/** Second layer of the authentication boundary (OD-131): no session, no protected page. */
export default async function ProtectedLayout({ children }: { readonly children: ReactNode }) {
  const session = await requireSession();
  return (
    <Shell label={session.label} role={session.role}>
      {children}
    </Shell>
  );
}
