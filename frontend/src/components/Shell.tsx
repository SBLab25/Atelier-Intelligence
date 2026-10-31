"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import type { Role } from "@/lib/session-core";
import { AtelierNavbar } from "./AtelierNavbar";

export interface ShellProps {
  readonly label: string;
  readonly role: Role;
  readonly children: ReactNode;
}

const NEW_FRONTEND_ROUTES = new Set([
  "/",
  "/dashboard",
  "/analytics",
  "/cockpit",
  "/team",
  "/projects",
  "/intelligence",
  "/time",
  "/connections",
]);

/** Application shell: for new Cockpit views, CockpitApp provides its own unified navigation. */
export function Shell({ label, role, children }: ShellProps) {
  const pathname = usePathname() ?? "/";
  const isNewFrontend = NEW_FRONTEND_ROUTES.has(pathname);

  if (isNewFrontend) {
    return (
      <main id="main" tabIndex={-1} className="w-full min-h-screen">
        {children}
      </main>
    );
  }

  return (
    <>
      <AtelierNavbar label={label} role={role} />
      <main id="main" tabIndex={-1} className="content">
        {children}
      </main>
    </>
  );
}
