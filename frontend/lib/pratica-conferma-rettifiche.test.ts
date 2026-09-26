import { describe, expect, it } from "vitest";
import type { RettificaEntry } from "@/types/api";
import { scartoQuadratura } from "@/lib/pratica-quadratura";
import { preparaConfermaRettifiche } from "@/lib/pratica-conferma-rettifiche";

const marker: RettificaEntry = {
  id: "confirm-2026-6", entry_type: "confirm", edited_field: "", edited_label: "Rettifiche confermate",
  edit_delta: 0, counterpart_field: "", counterpart_label: "", counterpart_delta: 0, created_at: "2026-09-24T00:00:00Z",
};

describe("conferma delle rettifiche", () => {
  it("chiude i 23 centesimi salvati anche se la conferma esiste già", () => {
    const prepared = preparaConfermaRettifiche({
      balance_sheet: {
        sp09_disponibilita_liquide: 2352463.09,
        sp16_debiti_breve: 2352463.32,
        sp16g_altri_debiti_breve: 50000,
      },
      income_statement: {},
      rettifiche_log: [marker],
    }, 2026, 6);
    expect(prepared.kind).toBe("save");
    if (prepared.kind !== "save") return;
    expect(prepared.closedAmount).toBe(0.23);
    expect(prepared.values?.sp16g_altri_debiti_breve).toBe(49999.77);
    expect(prepared.values?.sp16_debiti_breve).toBe(2352463.09);
    expect(scartoQuadratura(prepared.values!)).toBe(0);
    expect(prepared.log.filter((entry) => entry.entry_type === "confirm")).toHaveLength(1);
    expect(prepared.log.filter((entry) => entry.counterpart_field === "_correzione_import")).toHaveLength(1);
    expect(preparaConfermaRettifiche({
      balance_sheet: prepared.values!, income_statement: {}, rettifiche_log: prepared.log,
    }, 2026, 6)).toEqual({ kind: "already_confirmed" });
  });

  it("non chiude automaticamente uno scarto oltre due euro", () => {
    expect(preparaConfermaRettifiche({
      balance_sheet: { sp09_disponibilita_liquide: 97, sp16_debiti_breve: 100 },
      income_statement: {}, rettifiche_log: [marker],
    }, 2026, 6)).toEqual({ kind: "already_confirmed" });
  });
});
