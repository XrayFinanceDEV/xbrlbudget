import { parseFinalReportModelV2, type EditorialNote, type FinalReportModelV2 } from "./final-report-v2";

export interface EditorialGenerationWarning { note_id: string; message: string }
export interface EditorialSession {
  report: FinalReportModelV2;
  revision: number;
  archived_notes: EditorialNote[];
  generation_warnings: EditorialGenerationWarning[];
}

export interface EditorialNoteReference { id: string; plan_hash: string; revision: number }
export interface EditorialNoteUpdate {
  id: string;
  text: string;
  revision: number;
  from_note?: EditorialNoteReference;
}

const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
const hash = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
const datetime = (value: unknown): value is string => typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?$/.test(value) && !Number.isNaN(Date.parse(value));
const note = (value: unknown): value is EditorialNote => object(value)
  && Object.keys(value).length === 9
  && ["id", "content_ids", "text", "provenance", "updated_at", "source_hash", "plan_hash", "revision", "freshness"].every((key) => Object.hasOwn(value, key))
  && typeof value.id === "string" && Array.isArray(value.content_ids) && value.content_ids.every((id) => typeof id === "string")
  && typeof value.text === "string" && value.text.trim().length > 0 && ["ai", "user", "automatic"].includes(String(value.provenance))
  && datetime(value.updated_at) && hash(value.source_hash) && hash(value.plan_hash)
  && typeof value.revision === "number" && Number.isInteger(value.revision) && value.revision >= 0 && ["fresh", "stale", "missing"].includes(String(value.freshness));

/** Client boundary for the editorial endpoint; no unvalidated v1 response enters its cache. */
export function parseEditorialSession(value: unknown): EditorialSession {
  if (!object(value) || Object.keys(value).length !== 4
    || !["report", "revision", "archived_notes", "generation_warnings"].every((key) => Object.hasOwn(value, key))
    || typeof value.revision !== "number" || !Number.isInteger(value.revision) || value.revision < 0
    || !Array.isArray(value.archived_notes) || !value.archived_notes.every(note)
    || !Array.isArray(value.generation_warnings)
    || !value.generation_warnings.every((warning) => object(warning) && Object.keys(warning).length === 2 && typeof warning.note_id === "string" && typeof warning.message === "string")) {
    throw new Error("Unsupported or invalid EditorialSession payload");
  }
  return { report: parseFinalReportModelV2(value.report), revision: value.revision, archived_notes: value.archived_notes, generation_warnings: value.generation_warnings };
}
