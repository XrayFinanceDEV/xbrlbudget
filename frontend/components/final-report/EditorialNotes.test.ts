import { describe, expect, it } from "vitest";
import { eligibleForGeneration } from "./EditorialNotes";
import type { EditorialNote } from "@/types/final-report-v2";

const note = (id: string, provenance: EditorialNote["provenance"]): EditorialNote => ({ id, content_ids: ["content"], text: "Nota", provenance, updated_at: "2026-09-15T10:00:00Z", source_hash: "a".repeat(64), plan_hash: "b".repeat(64), revision: 1, freshness: "fresh" });
describe("eligibleForGeneration", () => {
  it("excludes user comments and a note made dirty after it was selected", () => {
    expect(eligibleForGeneration([note("ai", "ai"), note("user", "user"), note("automatic", "automatic")], { ai: true, user: true, automatic: true }, { automatic: true })).toEqual([note("ai", "ai")]);
  });
});
