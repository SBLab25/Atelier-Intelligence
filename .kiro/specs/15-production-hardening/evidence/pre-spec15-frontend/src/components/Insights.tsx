import type { Provenance, RunResults } from "@/lib/api/loaders";
import { count, decimal, usd } from "@/lib/format";

import { Timestamp } from "./States";

/**
 * Where a text came from (Spec 14, OD-147): written by the language model (with model and provider), a fallback
 * template (with the gateway's reason), or not recorded (runs from before Spec 14).
 */
export function ProvenanceBadge({ provenance }: { readonly provenance: Provenance }) {
  if (provenance.source === "llm") {
    const parts = [provenance.model, provenance.provider].filter((p): p is string => Boolean(p));
    return (
      <span className="provenance provenance-llm">
        Written by the language model{parts.length > 0 ? ` (${parts.join(", ")})` : ""}
      </span>
    );
  }
  if (provenance.source === "fallback") {
    return (
      <span className="provenance provenance-fallback">
        Fallback text, not written by the language model{provenance.reason ? ` (reason: ${provenance.reason})` : ""}
      </span>
    );
  }
  return <span className="provenance provenance-unknown">Provenance not recorded (run created before Spec 14)</span>;
}

type RunInsight = RunResults["insights"][number];

export function InsightCard({ insight }: { readonly insight: RunInsight }) {
  const evidence = insight.evidence ?? [];
  return (
    <article className="insight" aria-labelledby={`insight-${insight.insight_id}`}>
      <h3 id={`insight-${insight.insight_id}`}>
        {insight.title} <span className="hint">({insight.step_id})</span>
      </h3>
      <p>
        <ProvenanceBadge provenance={insight.provenance} />
        {insight.provenance.generated_at ? (
          <>
            {" "}
            · <Timestamp value={insight.provenance.generated_at} />
          </>
        ) : null}
      </p>
      <dl className="kv">
        <dt>Root cause</dt>
        <dd>{insight.root_cause ?? "—"}</dd>
        <dt>Suggested fix</dt>
        <dd>{insight.suggested_fix ?? "—"}</dd>
        <dt>Category</dt>
        <dd>{insight.category ?? "—"}</dd>
        <dt>Effort</dt>
        <dd>{insight.fix_effort ?? "—"}</dd>
        <dt>Priority</dt>
        <dd>{insight.priority ?? "—"}</dd>
        <dt>Friction score</dt>
        <dd>{insight.score ?? "—"}</dd>
      </dl>
      {evidence.length > 0 ? (
        <>
          <h4>Evidence</h4>
          <ul>
            {evidence.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}
    </article>
  );
}

export function UsageSummary({ usage }: { readonly usage: RunResults["llm_usage"] }) {
  return (
    <dl className="kv">
      <dt>Language model calls</dt>
      <dd>{count(usage.calls)}</dd>
      <dt>Input tokens</dt>
      <dd>{count(usage.input_tokens)}</dd>
      <dt>Output tokens</dt>
      <dd>{count(usage.output_tokens)}</dd>
      <dt>Cost</dt>
      <dd>{usage.cost_usd > 0 ? usd(usage.cost_usd) : "not priced"}</dd>
    </dl>
  );
}

export function FixesTable({ fixes }: { readonly fixes: RunResults["prioritized_fixes"] }) {
  return (
    <div className="table-wrap">
      <table>
        <caption>Prioritized fixes, in the order the run ranked them</caption>
        <thead>
          <tr>
            <th scope="col">Step</th>
            <th scope="col">Fix</th>
            <th scope="col">Effort</th>
            <th scope="col">Priority</th>
            <th scope="col">Priority score</th>
          </tr>
        </thead>
        <tbody>
          {fixes.map((fix, index) => (
            <tr key={fix.insight_id ?? `${fix.step_id}-${index}`}>
              <th scope="row">{fix.step_id}</th>
              <td>{fix.suggested_fix ?? fix.title ?? "—"}</td>
              <td>{fix.fix_effort ?? "—"}</td>
              <td>{fix.priority ?? "—"}</td>
              <td>{decimal(fix.priority_score, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
