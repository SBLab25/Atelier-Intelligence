import { ProblemPanel } from "@/components/ProblemPanel";
import { EmptyState, StatusBadge } from "@/components/States";
import type { Health, HealthDetails, Me } from "@/lib/api/loaders";
import type { Result } from "@/lib/api/problem";

export function HealthView({ result }: { readonly result: Result<Health> }) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="API health" />;
  }
  const health = result.data;
  return (
    <dl className="kv">
      <dt>Status</dt>
      <dd>
        <StatusBadge status={health.status} />
      </dd>
      <dt>API version</dt>
      <dd>{health.version}</dd>
      <dt>Data mode</dt>
      <dd>{health.mode}</dd>
    </dl>
  );
}

export function HealthDetailsView({ result }: { readonly result: Result<HealthDetails> }) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Component status" />;
  }
  const details = result.data;
  if (details.components.length === 0) {
    return <EmptyState>The API reported no components.</EmptyState>;
  }
  return (
    <div className="stack">
      <p>
        Overall: <StatusBadge status={details.status} />
      </p>
      <div className="table-wrap">
        <table>
          <caption>Backend components</caption>
          <thead>
            <tr>
              <th scope="col">Component</th>
              <th scope="col">Status</th>
              <th scope="col">Code</th>
            </tr>
          </thead>
          <tbody>
            {details.components.map((component) => (
              <tr key={component.name}>
                <th scope="row">{component.name}</th>
                <td>
                  <StatusBadge status={component.status} />
                </td>
                <td>{component.code ? <code>{component.code}</code> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function MeView({ result }: { readonly result: Result<Me> }) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Your token" />;
  }
  const me = result.data;
  return (
    <dl className="kv">
      <dt>Label</dt>
      <dd>{me.label}</dd>
      <dt>Token id</dt>
      <dd>
        <code>{me.token_id}</code>
      </dd>
      <dt>Role</dt>
      <dd>{me.role}</dd>
      <dt>Journeys</dt>
      <dd>{me.journeys.includes("*") ? "all journeys" : me.journeys.join(", ") || "none"}</dd>
    </dl>
  );
}
