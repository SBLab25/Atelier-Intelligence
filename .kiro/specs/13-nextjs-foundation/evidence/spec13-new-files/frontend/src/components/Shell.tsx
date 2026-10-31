import type { ReactNode } from "react";

import { signOut } from "@/app/actions";
import type { Role } from "@/lib/session-core";

import { Nav } from "./Nav";

export interface ShellProps {
  readonly label: string;
  readonly role: Role;
  readonly children: ReactNode;
}

/** Application shell: header with product name, main navigation, signed-in token and sign-out. */
export function Shell({ label, role, children }: ShellProps) {
  return (
    <>
      <header className="app-header">
        <p className="brand">
          <span aria-hidden="true">◆</span> CJI
        </p>
        <Nav />
        <div className="account">
          <span className="account-label">
            Signed in as <strong>{label}</strong> ({role})
          </span>
          <form action={signOut}>
            <button type="submit" className="button">
              Sign out
            </button>
          </form>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="content">
        {children}
      </main>
      <footer className="app-footer">
        <p>Data from the CJI API (/api/v1). The Streamlit dashboard stays available for comparison.</p>
      </footer>
    </>
  );
}
