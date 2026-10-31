/**
 * Role checks for the UI only (Spec 14, OD-151): they decide whether an action is enabled and which explanation is
 * shown. The API enforces every role again; a stale or edited page cannot do more than its token allows.
 */
import type { Role } from "./session-core";

const RANK: Readonly<Record<Role, number>> = { viewer: 0, operator: 1, admin: 2 };

export function atLeast(role: Role, needed: Role): boolean {
  return RANK[role] >= RANK[needed];
}

export function roleHint(needed: Role): string {
  return `Requires the ${needed} role. Your token cannot do this; ask an administrator for a token with this role.`;
}
