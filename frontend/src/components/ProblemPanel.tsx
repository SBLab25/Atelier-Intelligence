import Link from "next/link";
import type { ReactNode } from "react";

import type { Problem } from "@/lib/api/problem";

import { RetryButton } from "./RetryButton";

interface Described {
  readonly heading: string;
  readonly retry: boolean;
}

/** Heading and whether retrying can help, by status. Texts only; no decision about the data itself. */
export function describeProblem(problem: Problem): Described {
  switch (problem.status) {
    case 403:
      return { heading: "Not allowed for your token", retry: false };
    case 404:
      return { heading: "Not found", retry: false };
    case 400:
    case 422:
      return { heading: "The request was not accepted", retry: false };
    case 429:
      return { heading: "Too many requests", retry: true };
    default:
      return { heading: problem.title || "Something went wrong", retry: true };
  }
}

export interface ProblemPanelProps {
  readonly problem: Problem;
  /** What failed to load, e.g. "Friction summary". */
  readonly what: string;
  readonly back?: { readonly href: string; readonly label: string } | undefined;
  readonly children?: ReactNode;
}

/** A visible, persistent error with the API's code and request id, and a way to recover (Spec 13, OD-135). */
export function ProblemPanel({ problem, what, back, children }: ProblemPanelProps) {
  const { heading, retry } = describeProblem(problem);
  return (
    <section className="problem" role="alert">
      <h2 className="problem-heading">
        {what}: {heading}
      </h2>
      <p>{problem.detail || problem.title}</p>
      <dl className="problem-facts">
        <dt>Status</dt>
        <dd>{problem.status}</dd>
        <dt>Code</dt>
        <dd>
          <code>{problem.code}</code>
        </dd>
        {problem.requestId ? (
          <>
            <dt>Request id</dt>
            <dd>
              <code>{problem.requestId}</code>
            </dd>
          </>
        ) : null}
      </dl>
      {problem.retryAfterS ? <p>Try again in {problem.retryAfterS} seconds.</p> : null}
      {children}
      <div className="actions">
        {retry ? <RetryButton /> : null}
        {back ? <Link href={back.href}>{back.label}</Link> : null}
      </div>
    </section>
  );
}
