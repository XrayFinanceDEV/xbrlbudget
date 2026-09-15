import { describe, expect, it } from "vitest";
import { acknowledgeReportDraft, editReportDraft, syncReportDrafts, type ReportDraftBuckets } from "./report-drafts";

describe("report drafts", () => {
  it("retains independent company/scenario/plan drafts on refetch and return", () => {
    const store: ReportDraftBuckets = {};
    editReportDraft(store, "company-a:budget-a:plan-1", "note", "Bozza A");
    syncReportDrafts(store, "company-a:budget-a:plan-1", [{ id: "note", text: "Testo server aggiornato" }]);
    syncReportDrafts(store, "company-b:budget-b:plan-1", [{ id: "note", text: "Testo B" }]);
    syncReportDrafts(store, "company-a:budget-a:plan-2", [{ id: "note", text: "Nuova pagina A" }]);
    expect(store["company-a:budget-a:plan-1"].values.note).toBe("Bozza A");
    expect(store["company-b:budget-b:plan-1"].values.note).toBe("Testo B");
    expect(store["company-a:budget-a:plan-2"].values.note).toBe("Nuova pagina A");
  });
  it("keeps edits made during a save and only acknowledges the submitted draft", () => {
    const store: ReportDraftBuckets = {};
    editReportDraft(store, "scope", "note", "Primo testo");
    editReportDraft(store, "scope", "note", "Modifica durante il salvataggio");
    acknowledgeReportDraft(store, "scope", "note", "Primo testo");
    expect(store.scope.dirty.note).toBe(true);
    acknowledgeReportDraft(store, "scope", "note", "Modifica durante il salvataggio");
    syncReportDrafts(store, "scope", [{ id: "note", text: "Testo confermato" }]);
    expect(store.scope.dirty.note).toBe(false);
    expect(store.scope.values.note).toBe("Testo confermato");
  });
});
