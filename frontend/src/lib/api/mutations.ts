import "server-only";

import { call } from "./client";
import { withApi, type Ingestion, type IngestionValidation, type Run } from "./loaders";
import type { Result } from "./problem";
import type { components } from "./schema";

/**
 * Write calls for Server Actions (Spec 14, OD-151). Each sends the Idempotency-Key the form was rendered with, so a
 * repeated submit replays the stored response instead of acting twice. The API checks every role again.
 */

export type StartRunRequest = components["schemas"]["StartRunRequest"];
export type Approval = components["schemas"]["Approval"];
export type WriteMode = components["schemas"]["IngestionRequest"]["write_mode"];

export const UPLOAD_TYPES: Readonly<Record<string, string>> = {
  ".json": "application/json",
  ".ndjson": "application/x-ndjson",
  ".jsonl": "application/x-ndjson",
  ".csv": "text/csv",
};

export interface Upload {
  readonly filename: string;
  readonly mediaType: string;
  readonly text: string;
  readonly rootKey?: string | undefined;
  readonly map: readonly string[];
}

export function startRun(body: StartRunRequest, key: string): Promise<Result<Run>> {
  return withApi(true, "POST /runs", ({ api, requestId }) =>
    call(requestId, () => api.POST("/api/v1/runs", { params: { header: { "Idempotency-Key": key } }, body })),
  );
}

export function approveRun(runId: string, key: string): Promise<Result<Approval>> {
  return withApi(true, "POST /runs/{id}/approval", ({ api, requestId }) =>
    call(requestId, () =>
      api.POST("/api/v1/runs/{run_id}/approval", {
        params: { path: { run_id: runId }, header: { "Idempotency-Key": key } },
        body: { comment: null },
      }),
    ),
  );
}

export function resumeRun(runId: string, key: string): Promise<Result<Run>> {
  return withApi(true, "POST /runs/{id}/resume", ({ api, requestId }) =>
    call(requestId, () =>
      api.POST("/api/v1/runs/{run_id}/resume", {
        params: { path: { run_id: runId }, header: { "Idempotency-Key": key } },
      }),
    ),
  );
}

export function validateIngestion(upload: Upload): Promise<Result<IngestionValidation>> {
  const query: { filename: string; root_key?: string; map?: string[] } = { filename: upload.filename };
  if (upload.rootKey) {
    query.root_key = upload.rootKey;
  }
  if (upload.map.length > 0) {
    query.map = [...upload.map];
  }
  return withApi(true, "POST /ingestions/validations", ({ api, requestId }) =>
    call(requestId, () =>
      api.POST("/api/v1/ingestions/validations", {
        params: { query },
        body: upload.text,
        bodySerializer: (text: string) => text,
        headers: { "Content-Type": upload.mediaType },
      }),
    ),
  );
}

export function createIngestion(validationId: string, writeMode: WriteMode, key: string): Promise<Result<Ingestion>> {
  return withApi(true, "POST /ingestions", ({ api, requestId }) =>
    call(requestId, () =>
      api.POST("/api/v1/ingestions", {
        params: { header: { "Idempotency-Key": key } },
        body: { validation_id: validationId, write_mode: writeMode },
      }),
    ),
  );
}
