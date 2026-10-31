"use client";

import { useActionState, useId, type ReactNode } from "react";

import { IDLE, type ActionState } from "@/lib/action-state";

import { ProblemPanel } from "./ProblemPanel";

export interface ActionFormProps {
  /** A Server Action taking (previous state, form data). */
  readonly action: (previous: ActionState<never>, form: FormData) => Promise<ActionState<never>>;
  /** Hidden fields (ids and the idempotency key rendered with the page). */
  readonly fields: Readonly<Record<string, string>>;
  readonly label: string;
  readonly pendingLabel: string;
  /** What the action is called in problem messages, e.g. "Approve run". */
  readonly what: string;
  /** When set, the button is disabled and this text explains why (e.g. the role needed). */
  readonly disabledReason?: string | null | undefined;
  readonly primary?: boolean | undefined;
  readonly children?: ReactNode;
}

/**
 * A form for one write action (Spec 14, OD-151). The button shows progress and cannot be pressed twice while the
 * request runs; a refusal or API problem stays next to the button. Roles below the needed one see the button
 * disabled with the reason (the API enforces the role as well).
 */
export function ActionForm({ action, fields, label, pendingLabel, what, disabledReason, primary, children }: ActionFormProps) {
  const [state, formAction, pending] = useActionState(action, IDLE);
  const reasonId = useId();
  const disabled = Boolean(disabledReason) || pending;
  return (
    <form action={formAction} className="action-form" aria-busy={pending}>
      {Object.entries(fields).map(([name, value]) => (
        <input key={name} type="hidden" name={name} value={value} />
      ))}
      {children}
      <div className="actions">
        <button
          type="submit"
          className={primary ? "button button-primary" : "button"}
          disabled={disabled}
          aria-describedby={disabledReason ? reasonId : undefined}
        >
          {pending ? pendingLabel : label}
        </button>
        {disabledReason ? (
          <p id={reasonId} className="hint">
            {disabledReason}
          </p>
        ) : null}
      </div>
      {state.status === "error" && state.fieldError ? (
        <p className="field-error" role="alert">
          {state.fieldError}
        </p>
      ) : null}
      {state.status === "error" && state.problem ? <ProblemPanel problem={state.problem} what={what} /> : null}
    </form>
  );
}
