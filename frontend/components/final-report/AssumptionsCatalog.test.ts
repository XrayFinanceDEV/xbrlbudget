import { describe, it, expect } from "vitest";
import {
  CANONICAL_SECTION_KEYS,
  assumptionRowState,
  hasNestedTable,
  isDeadField,
  layoutSections,
  nestedTablesOf,
  readFinalReport,
  rowCells,
  sectionColumns,
  sectionTitle,
} from "./AssumptionsCatalog";
import type { AssumptionSection, AssumptionValue } from "@/types/final-report";
import infrannuale from "../../../tests/fixtures/final_report/infrannuale.json";

/** Una riga di ipotesi con i default del caso semplice. */
function row(field: string, values: AssumptionValue["values"], over: Partial<AssumptionValue> = {}): AssumptionValue {
  return { field, label: field, values, provenance: "user", active: true, ...over };
}

function section(key: AssumptionSection["key"], title: string, assumptions: AssumptionValue[]): AssumptionSection {
  return { key, title, assumptions };
}

describe("ordine canonico delle sezioni", () => {
  it("sono sette, nell'ordine del catalogo", () => {
    expect(CANONICAL_SECTION_KEYS).toEqual([
      "scenario",
      "fatturato",
      "costi",
      "altre-voci-ce",
      "circolante",
      "pregresso-nuovo",
      "imposte",
    ]);
  });

  it("l'ordine del payload non comanda nulla", () => {
    const shuffled = [
      section("imposte", "Imposte", [row("tax_rate", ["27.9"])]),
      section("fatturato", "Fatturato", [row("revenue_growth_pct", ["5"])]),
      section("scenario", "Scenario", []),
    ];
    const layout = layoutSections(shuffled);
    expect(layout.sections.map((item) => item.key)).toEqual([...CANONICAL_SECTION_KEYS]);
    expect(layout.sections[0].assumptions).toEqual([]);
    expect(layout.sections[1].assumptions.map((item) => item.field)).toEqual(["revenue_growth_pct"]);
  });

  it("una sezione che arriva due volte non scarta la prima", () => {
    const layout = layoutSections([
      section("fatturato", "Fatturato", [row("revenue_growth_pct", ["5"])]),
      section("fatturato", "Fatturato", [row("other_revenue_growth_pct", ["1"])]),
    ]);
    expect(layout.duplicates).toEqual(["fatturato"]);
    expect(layout.sections[1].assumptions.map((item) => item.field)).toEqual([
      "revenue_growth_pct",
      "other_revenue_growth_pct",
    ]);
  });

  it("una sezione che non è del catalogo si dichiara, non si elimina", () => {
    const stranger = { key: "magia", title: "Sezione magica", assumptions: [row("foo", ["1"])] };
    const layout = layoutSections([stranger as unknown as AssumptionSection]);
    expect(layout.unknown).toHaveLength(1);
    expect(layout.unknown[0].key).toBe("magia");
    expect(layout.missing).toEqual([...CANONICAL_SECTION_KEYS]);
  });

  it("il titolo del payload vince, quello del catalogo è il ripiego", () => {
    expect(sectionTitle("pregresso-nuovo", "Pregresso e nuovo")).toBe("Pregresso e nuovo");
    expect(sectionTitle("pregresso-nuovo", "  ")).toBe("Pregresso e nuovo");
    expect(sectionTitle("circolante")).toBe("Capitale circolante");
  });
});

describe("allineamento ai valori per anno", () => {
  it("un valore per anno, nell'ordine degli anni", () => {
    const columns = sectionColumns([row("a", ["1", null, true])], [2027, 2028, 2029]);
    expect(columns.map((column) => column.year)).toEqual([2027, 2028, 2029]);
    expect(rowCells(["1", null, true], columns).map((cell) => cell.value)).toEqual(["1", null, true]);
    expect(rowCells(["1", null, true], columns).every((cell) => !cell.absent)).toBe(true);
  });

  it("più valori che anni: una colonna in più dichiarata, nessun valore perso", () => {
    const values = ["1", "2", "3", "4"];
    const columns = sectionColumns([row("a", values)], [2027, 2028]);
    expect(columns.map((column) => column.label)).toEqual(["2027", "2028", "Anno non dichiarato (3)", "Anno non dichiarato (4)"]);
    const cells = rowCells(values, columns);
    expect(cells).toHaveLength(4);
    expect(cells[2]).toEqual({ value: "3", absent: false });
    expect(cells[3].value).toBe("4");
    expect(columns[2].extra).toBe(true);
  });

  it("meno valori che anni: la cella manca e lo dice, non è uno zero", () => {
    const columns = sectionColumns([row("a", ["1"])], [2027, 2028]);
    expect(rowCells(["1"], columns)[1]).toMatchObject({ value: null, absent: true });
  });

  it("le colonne della sezione sono quelle della riga più lunga", () => {
    const columns = sectionColumns([row("a", ["1"]), row("b", ["1", "2", "3"])], [2027, 2028]);
    expect(columns.map((column) => column.label)).toEqual(["2027", "2028", "Anno non dichiarato (3)"]);
    expect(columns[2].extra).toBe(true);
  });
});

describe("stato dichiarativo di una riga", () => {
  it("un campo inerte non è un pilota attivo", () => {
    expect(isDeadField("investments")).toBe(true);
    expect(isDeadField("revenue_growth_pct")).toBe(false);
    expect(assumptionRowState(row("investments", ["1"]))).toMatchObject({ level: "warning" });
  });

  it("`ignored` e `active: false` si dicono in due frasi diverse", () => {
    expect(assumptionRowState(row("tax_rate", ["27.9"], { provenance: "ignored", active: false }))).toMatchObject({
      text: "Non usato nel percorso corrente.",
    });
    expect(assumptionRowState(row("tax_rate", ["27.9"], { active: false }))).toMatchObject({
      text: "Riga non attiva in questo scenario.",
    });
  });

  it("una riga valorizzata senza anomalie non ha stato da dichiarare", () => {
    expect(assumptionRowState(row("revenue_growth_pct", ["5"]))).toBeNull();
  });
});

describe("tabelle nidificate", () => {
  it("le sei chiavi note, in ordine canonico", () => {
    const assumption = row("financing_loans", [null], {
      financing_loans: [],
      sp_overrides: [{ field: "sp09_disponibilita_liquide", value: "10" }],
    });
    expect(nestedTablesOf(assumption).map((table) => table.kind)).toEqual(["financing_loans", "sp_overrides"]);
    expect(hasNestedTable(assumption)).toBe(true);
    expect(hasNestedTable(row("tax_rate", ["27.9"]))).toBe(false);
  });

  it("una chiave a null non è una tabella", () => {
    const assumption = row("pregresso", [null], { pregresso: null });
    expect(nestedTablesOf(assumption)).toEqual([]);
    expect(hasNestedTable(assumption)).toBe(false);
  });
});

describe("schema del payload", () => {
  it("un modello v1 a posto passa", () => {
    expect(readFinalReport(infrannuale, "Ipotesi").ok).toBe(true);
  });

  it("una versione diversa è «sconosciuta», e lo dice", () => {
    const future = { ...structuredClone(infrannuale), schema_version: 2 };
    const verdict = readFinalReport(future, "Ipotesi");
    expect(verdict.ok).toBe(false);
    if (!verdict.ok) {
      expect(verdict.kind).toBe("unknown");
      expect(verdict.message).toContain("2");
    }
  });

  it("un payload che non c'è è malformato, non un documento vuoto", () => {
    for (const payload of [null, undefined, {}, "bilancio"]) {
      const verdict = readFinalReport(payload, "Diagnostica");
      expect(verdict.ok).toBe(false);
      if (!verdict.ok) expect(verdict.kind).toBe("malformed");
    }
  });

  it("un v1 che non rispetta il contratto è malformato", () => {
    const broken = { ...structuredClone(infrannuale), assumption_sections: [] };
    expect(readFinalReport(broken, "Ipotesi").ok).toBe(false);
  });
});
