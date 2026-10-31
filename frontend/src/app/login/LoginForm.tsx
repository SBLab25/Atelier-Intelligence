"use client";

import { useState, useTransition } from "react";
import { signIn, type SignInState } from "@/app/actions";
import { ProblemPanel } from "@/components/ProblemPanel";

const INITIAL: SignInState = { fieldError: null, problem: null };

export function LoginForm({ next }: { readonly next: string }) {
  const [isSignUp, setIsSignUp] = useState(false);
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [state, setState] = useState<SignInState>(INITIAL);
  const [isPending, startTransition] = useTransition();

  const errorId = "auth-error";

  function handleQuickFill(user: "admin" | "operator") {
    if (user === "admin") {
      setIdentifier("admin");
      setPassword("admin123");
    } else {
      setIdentifier("operator");
      setPassword("operator123");
    }
    setState(INITIAL);
  }

  async function handleFormAction(formData: FormData) {
    setState(INITIAL);
    const result = await signIn(INITIAL, formData);
    if (result) {
      setState(result);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState(INITIAL);

    const form = event.currentTarget;
    const formData = new FormData(form);
    const idVal = String(formData.get("identifier") || identifier || "").trim();
    const passVal = String(formData.get("password") || password || "");
    const nextTarget = String(formData.get("next") || next || "/dashboard");

    if (!idVal) {
      setState({
        fieldError: "Please enter your User ID or Email.",
        problem: null,
      });
      return;
    }

    if (!passVal) {
      setState({
        fieldError: "Please enter your password.",
        problem: null,
      });
      return;
    }

    if (process.env.NODE_ENV === "test") {
      const result = await signIn(INITIAL, formData);
      if (result) {
        setState(result);
      }
      return;
    }

    startTransition(async () => {
      try {
        const response = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            identifier: idVal,
            password: passVal,
            isSignUp,
            fullName: isSignUp ? fullName : undefined,
            next: nextTarget,
          }),
        });

        const data = await response.json().catch(() => null);

        if (response.ok && data?.ok) {
          const destination = data.redirect || "/dashboard";
          window.location.href = destination;
          return;
        }

        if (data?.fieldError) {
          setState({ fieldError: data.fieldError, problem: null });
          return;
        }

        if (data?.problem) {
          setState({ fieldError: null, problem: data.problem });
          return;
        }

        setState({
          fieldError: "Authentication failed. Please verify your credentials.",
          problem: null,
        });
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setState({
          fieldError: `Connection error: ${msg}. Please check your network or Supabase status.`,
          problem: null,
        });
      }
    });
  }

  return (
    <div className="space-y-5">
      {/* Tab Switcher: Sign In vs Create Account */}
      <div className="flex border-b border-surface-container-high pb-2">
        <button
          type="button"
          onClick={() => {
            setIsSignUp(false);
            setState(INITIAL);
          }}
          className={`flex-1 py-1.5 text-xs font-semibold uppercase tracking-wider text-center transition-colors ${!isSignUp
              ? "text-primary border-b-2 border-primary -mb-2"
              : "text-on-surface-variant hover:text-on-surface"
            }`}
        >
          Sign In
        </button>
        <button
          type="button"
          onClick={() => {
            setIsSignUp(true);
            setState(INITIAL);
          }}
          className={`flex-1 py-1.5 text-xs font-semibold uppercase tracking-wider text-center transition-colors ${isSignUp
              ? "text-primary border-b-2 border-primary -mb-2"
              : "text-on-surface-variant hover:text-on-surface"
            }`}
        >
          Create Account
        </button>
      </div>

        <form onSubmit={handleSubmit} action={handleFormAction} className="space-y-4" noValidate>
          <input type="hidden" name="next" value={next} />
          <input type="hidden" name="isSignUp" value={isSignUp ? "true" : "false"} />

          {/* Full Name for Sign Up */}
          {isSignUp && (
            <div>
              <label
                htmlFor="fullName"
                className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant block mb-2"
              >
                Full Name
              </label>
              <input
                id="fullName"
                name="fullName"
                type="text"
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Elena Vance"
                className="w-full bg-surface-container-lowest border border-surface-container-high focus:border-primary focus:ring-1 focus:ring-primary rounded-xl px-4 py-3 text-sm text-on-surface placeholder:text-outline/60 outline-none transition-all"
              />
            </div>
          )}

          {/* User ID / Email */}
          <div>
            <label
              htmlFor="identifier"
              className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant block mb-2"
            >
              User ID or Email
            </label>
            <input
              id="identifier"
              name="identifier"
              type="text"
              autoComplete="username"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              aria-invalid={Boolean(state.fieldError)}
              aria-describedby={state.fieldError ? errorId : undefined}
              placeholder={isSignUp ? "e.g. elena or elena@cji.io" : "admin or admin@cji.io"}
              className="w-full bg-surface-container-lowest border border-surface-container-high focus:border-primary focus:ring-1 focus:ring-primary rounded-xl px-4 py-3 text-sm text-on-surface placeholder:text-outline/60 outline-none transition-all font-mono"
              required
            />
          </div>

          {/* Password */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label
                htmlFor="password"
                className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant block"
              >
                Password
              </label>
              <button
                type="button"
                onClick={() => setShowPassword((p) => !p)}
                className="text-xs text-secondary hover:underline cursor-pointer"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
            <div className="relative">
              <input
                id="password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete={isSignUp ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={Boolean(state.fieldError)}
                aria-describedby={state.fieldError ? errorId : undefined}
                placeholder="••••••••••••"
                className="w-full bg-surface-container-lowest border border-surface-container-high focus:border-primary focus:ring-1 focus:ring-primary rounded-xl px-4 py-3 text-sm text-on-surface placeholder:text-outline/60 outline-none transition-all font-mono"
                required
              />
            </div>
          </div>

          {/* Error notification */}
          {state.fieldError && (
            <p
              id={errorId}
              role="alert"
              className="text-xs font-medium text-error bg-error-container/20 border border-error/30 rounded-xl px-3 py-2.5 mt-2"
            >
              {state.fieldError}
            </p>
          )}

          {state.problem && (
            <div className="mt-2">
              <ProblemPanel what="Sign-in" problem={state.problem} />
            </div>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isPending}
            className="w-full bg-primary text-on-primary hover:bg-primary-hover font-semibold py-3 px-4 rounded-xl shadow-sm transition-all duration-150 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed mt-4"
          >
            {isPending ? (
              <span className="inline-block w-4 h-4 border-2 border-on-primary border-t-transparent rounded-full animate-spin" />
            ) : null}
            <span>{isSignUp ? "Create Supabase Account" : "Sign in with Supabase"}</span>
          </button>
        </form>

        {/* Quick Fill Demo Badges */}
        {!isSignUp && (
          <div className="bg-surface-container-low border border-surface-container-high rounded-2xl p-3.5 space-y-2">
            <div className="flex items-center justify-between text-xs text-on-surface-variant font-medium">
              <span>Quick Fill Credentials:</span>
              <span className="text-[10px] text-primary/80 font-mono">Supabase Auth</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => handleQuickFill("admin")}
                className="px-2.5 py-1.5 rounded-lg bg-surface-container-highest hover:bg-surface-container-high text-xs font-medium text-on-surface text-left transition-colors flex flex-col cursor-pointer border border-surface-container-high"
              >
                <span className="font-semibold text-primary">Admin</span>
                <span className="text-[10px] text-on-surface-variant font-mono">admin / admin123</span>
              </button>
              <button
                type="button"
                onClick={() => handleQuickFill("operator")}
                className="px-2.5 py-1.5 rounded-lg bg-surface-container-highest hover:bg-surface-container-high text-xs font-medium text-on-surface text-left transition-colors flex flex-col cursor-pointer border border-surface-container-high"
              >
                <span className="font-semibold text-primary">Operator</span>
                <span className="text-[10px] text-on-surface-variant font-mono">operator / operator123</span>
              </button>
            </div>
          </div>
        )}
    </div>
  );
}
