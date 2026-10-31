import { FixesTable, InsightCard, ProvenanceBadge, UsageSummary } from "@/components/Insights";
import { ProblemPanel } from "@/components/ProblemPanel";
import { EmptyState, Timestamp } from "@/components/States";
import type { RunResults } from "@/lib/api/loaders";
import type { Result } from "@/lib/api/problem";
import { count, fraction } from "@/lib/format";

/**
 * A run's results as stored by the workflow (Spec 14, OD-146, OD-147): narrative and insights with their provenance,
 * prioritized fixes in the run's order, friction scores, LLM usage, ingestion results and errors. Values are shown as
 * the API returns them; nothing is re-ranked or re-scored.
 */
export function RunResultsView({ result }: { readonly result: Result<RunResults> }) {
  if (!result.ok) {
    return <ProblemPanel problem={result.problem} what="Run results" />;
  }
  const r = result.data;
  return (
    <div className="stack">
      <section className="region" aria-labelledby="narrative-heading">
        <h2 id="narrative-heading">Executive narrative</h2>
        {r.narrative ? (
          <>
            <p>
              <ProvenanceBadge provenance={r.narrative_provenance} />
              {r.narrative_provenance.generated_at ? (
                <>
                  {" "}
                  · <Timestamp value={r.narrative_provenance.generated_at} />
                </>
              ) : null}
            </p>
            <blockquote className="narrative">{r.narrative}</blockquote>
          </>
        ) : (
          <EmptyState>No narrative yet: it is written by the report step after approval.</EmptyState>
        )}
      </section>

      <section className="region" aria-labelledby="insights-heading">
        <h2 id="insights-heading">Insights ({r.insights.length})</h2>
        {r.insights.length === 0 ? (
          <EmptyState>
            {r.status === "running" ? "Insights are not generated yet." : "No insights: the run found no critical step."}
          </EmptyState>
        ) : (
          r.insights.map((insight) => <InsightCard key={insight.insight_id} insight={insight} />)
        )}
      </section>

      <section className="region" aria-labelledby="fixes-heading">
        <h2 id="fixes-heading">Prioritized fixes</h2>
        {r.prioritized_fixes.length === 0 ? (
          <EmptyState>No prioritized fixes.</EmptyState>
        ) : (
          <FixesTable fixes={r.prioritized_fixes} />
        )}
      </section>

      <section className="region" aria-labelledby="run-friction-heading">
        <h2 id="run-friction-heading">Friction scores of this run</h2>
        {r.friction_scores.length === 0 ? (
          <EmptyState>No friction scores stored for this run.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table>
              <caption>Friction scores stored by this run (critical: {r.critical_steps.join(", ") || "none"})</caption>
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
                {r.friction_scores.map((score) => (
                  <tr key={score.step_id}>
                    <th scope="row">{score.step_id}</th>
                    <td>{score.score}</td>
                    <td>{score.is_critical ? <strong>Yes</strong> : "No"}</td>
                    <td>{score.signals && score.signals.length > 0 ? score.signals.join(", ") : "—"}</td>
                    <td>{fraction(score.confidence)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="region" aria-labelledby="usage-heading">
        <h2 id="usage-heading">Language model usage</h2>
        <UsageSummary usage={r.llm_usage} />
      </section>

      {r.ingestion_results.length > 0 || r.ingestion_pending_review.length > 0 ? (
        <section className="region" aria-labelledby="run-ingestion-heading">
          <h2 id="run-ingestion-heading">Ingestion in this run</h2>
          {r.ingestion_results.length > 0 ? (
            <div className="table-wrap">
              <table>
                <caption>Files ingested by this run</caption>
                <thead>
                  <tr>
                    <th scope="col">File</th>
                    <th scope="col">Detected source</th>
                    <th scope="col">Confidence</th>
                    <th scope="col">Written</th>
                    <th scope="col">Skipped</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {r.ingestion_results.map((item, index) => (
                    <tr key={`${item.file_name}-${index}`}>
                      <th scope="row">{item.file_name}</th>
                      <td>{item.detected_source ?? "—"}</td>
                      <td>{fraction(item.confidence)}</td>
                      <td>{count(item.records_written)}</td>
                      <td>{count(item.records_skipped)}</td>
                      <td>{item.status ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {r.ingestion_pending_review.length > 0 ? (
            <>
              <p className="notice">
                These files were not ingested: the schema detection confidence was below the threshold. Review them and
                ingest them on the Ingest page or with cji-ingest-json.
              </p>
              <ul>
                {r.ingestion_pending_review.map((item, index) => (
                  <li key={`${item.file_name}-${index}`}>
                    {item.file_name} (detected {item.detected_source ?? "unknown"}, confidence {fraction(item.confidence)})
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </section>
      ) : null}

      <section className="region" aria-labelledby="errors-heading">
        <h2 id="errors-heading">Errors recorded</h2>
        {r.errors.length === 0 ? (
          <EmptyState>No errors recorded.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table>
              <caption>Errors recorded by the workers (newest last)</caption>
              <thead>
                <tr>
                  <th scope="col">Worker</th>
                  <th scope="col">Message</th>
                  <th scope="col">Time</th>
                </tr>
              </thead>
              <tbody>
                {r.errors.map((error, index) => (
                  <tr key={index}>
                    <th scope="row">{error.worker}</th>
                    <td>{error.message}</td>
                    <td>
                      <Timestamp value={error.ts} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
