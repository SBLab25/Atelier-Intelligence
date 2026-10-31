"use client";

import { useActionState } from "react";

import { signIn, type SignInState } from "@/app/actions";
import { ProblemPanel } from "@/components/ProblemPanel";

const INITIAL: SignInState = { fieldError: null, problem: null };

export function LoginForm({ next }: { readonly next: string }) {
  const [state, action, pending] = useActionState(signIn, INITIAL);
  const errorId = "token-error";
  return (
    <form action={action} className="stack login-form" noValidate>
      <input type="hidden" name="next" value={next} />
      <div className="field">
        <label htmlFor="token">API token</label>
        <input
          id="token"
          name="token"
          type="password"
          autoComplete="off"
          spellCheck={false}
          required
          aria-invalid={state.fieldError ? true : undefined}
          aria-describedby={state.fieldError ? `${errorId} token-hint` : "token-hint"}
        />
        <p id="token-hint" className="hint">
          Issued by an operator with <code>cji-api-token create</code>. It stays on the server after you sign in.
        </p>
        {state.fieldError ? (
          <p id={errorId} className="field-error" role="alert">
            {state.fieldError}
          </p>
        ) : null}
      </div>
      {state.problem ? <ProblemPanel problem={state.problem} what="Sign-in" /> : null}
      <div>
        <button type="submit" className="button button-primary" disabled={pending} aria-busy={pending}>
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </div>
    </form>
  );
}
