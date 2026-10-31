"use server";

import { fieldError, problemState, type ActionState } from "@/lib/action-state";
import type { Ingestion, IngestionValidation } from "@/lib/api/loaders";
import { createIngestion, UPLOAD_TYPES, validateIngestion } from "@/lib/api/mutations";
import { isKey, newKey } from "@/lib/idempotency";
import { MAX_UPLOAD_BYTES } from "@/lib/upload";
import { requireSession } from "@/lib/session";

/**
 * Ingestion actions (Spec 14, OD-148): validate first (nothing is written), then write the validated file. The file
 * is forwarded to the API from the server; the browser never talks to the API.
 */
export interface Validated {
  readonly validation: IngestionValidation;
  /** Idempotency key for the write that confirms this validation. */
  readonly key: string;
}

const MAP_ENTRY = /^[^=\s]{1,64}=[a-z_]{2,20}$/;
const ROOT_KEY = /^[A-Za-z0-9_.-]{1,64}$/;
const SAFE_NAME = /^[^\x00-\x1f\x7f/\\:]{1,123}$/;

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

export async function validateAction(_previous: ActionState<Validated>, form: FormData): Promise<ActionState<Validated>> {
  await requireSession();
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) {
    return fieldError("Choose a file with events (.json, .ndjson, .jsonl or .csv).");
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return fieldError(`The file is larger than ${MAX_UPLOAD_BYTES / 1048576} MiB. Split it or use cji-ingest-json.`);
  }
  const extension = extensionOf(file.name);
  const mediaType = UPLOAD_TYPES[extension];
  if (!mediaType) {
    return fieldError("Only .json, .ndjson, .jsonl and .csv files can be validated here.");
  }
  const base = file.name.split(/[\\/]/).pop() ?? "";
  const stem = base.slice(0, base.length - extension.length);
  const filename = SAFE_NAME.test(stem) ? `${stem}${extension}` : `upload${extension}`;
  const rootKey = String(form.get("root_key") ?? "").trim();
  if (rootKey && !ROOT_KEY.test(rootKey)) {
    return fieldError("The root key may only contain letters, digits, dot, dash and underscore.");
  }
  const map = String(form.get("map") ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  if (map.length > 20 || map.some((entry) => !MAP_ENTRY.test(entry))) {
    return fieldError("Write one mapping per line as your_column=cji_column (at most 20).");
  }
  const result = await validateIngestion({ filename, mediaType, text: await file.text(), rootKey, map });
  if (!result.ok) {
    return problemState(result.problem);
  }
  return { status: "done", data: { validation: result.data, key: newKey() } };
}

export async function writeAction(_previous: ActionState<Ingestion>, form: FormData): Promise<ActionState<Ingestion>> {
  await requireSession();
  const key = form.get("key");
  const validationId = String(form.get("validation_id") ?? "");
  const mode = form.get("write_mode") === "replace" ? "replace" : "append";
  if (!isKey(key) || !/^[A-Za-z0-9_-]{24}$/.test(validationId)) {
    return fieldError("This form is out of date. Validate the file again.");
  }
  if (mode === "replace" && form.get("confirm_replace") !== "on") {
    return fieldError("Replacing deletes every stored event. Tick the confirmation box to continue.");
  }
  const result = await createIngestion(validationId, mode, key);
  if (!result.ok) {
    return problemState(result.problem);
  }
  return { status: "done", data: result.data };
}
