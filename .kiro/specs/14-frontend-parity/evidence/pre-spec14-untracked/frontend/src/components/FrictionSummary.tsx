import type { Friction } from "@/lib/api/loaders";

import { EmptyState } from "./States";

/**
 * Friction scores exactly as the API returns them (Spec 13, OD-140): no recomputation, re-thresholding or
 * re-sorting; `is_critical` and `critical_steps` come from the backend.
 */
export function FrictionSummary({ friction }: { readonly friction: Friction }) {
  if (friction.scores.length === 0) {
    return <EmptyState>No friction scores for this window: the journey has no step metrics yet.</EmptyState>;
  }
  return (
    <div className="stack">
      <p>
        Critical steps (score at or above {friction.threshold}):{" "}
        {friction.critical_steps.length > 0 ? (
          <strong>{friction.critical_steps.join(", ")}</strong>
        ) : (
          <span>none</span>
        )}
      </p>
      <div className="table-wrap">
        <table>
          <caption>Friction score per step (threshold {friction.threshold})</caption>
          <thead>
            <tr>
              <th scope="col">Step</th>
              <th scope="col">Score</th>
              <th scope="col">Critical</th>
              <th scope="col">Signals</th>
              <th scope="col">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {friction.scores.map((score) => (
              <tr key={score.step_id}>
                <th scope="row">{score.step_id}</th>
                <td>{score.score}</td>
                <td>{score.is_critical ? <strong>Yes</strong> : "No"}</td>
                <td>{score.signals.length > 0 ? score.signals.join(", ") : "—"}</td>
                <td>{score.confidence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
