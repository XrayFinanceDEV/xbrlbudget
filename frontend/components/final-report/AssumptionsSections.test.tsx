import * as React from "react";
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { AssumptionsSections, AssumptionsSectionTable, AssumptionsSchemaNotice } from "./AssumptionsSections";
import { CANONICAL_SECTION_KEYS } from "./AssumptionsCatalog";
import type { AssumptionSection, AssumptionValue } from "@/types/final-report";
import infrannuale from "../../../tests/fixtures/final_report/infrannuale.json";

/** Il payload del renderer: un modello v1 con le sezioni che servono al caso. */
function reportWith(sections: AssumptionSection[]): unknown {
  const model = structuredClone(infrannuale) as Record<string, unknown>;
  model.assumption_sections = sections;
  return model;
}

function row(field: string, values: AssumptionValue["values"], over: Partial<AssumptionValue> = {}): AssumptionValue {
  return { field, label: field, values, provenance: "user", active: true, ...over };
}

function section(key: AssumptionSection["key"], assumptions: AssumptionValue[]): AssumptionSection {
  return { key, title: key, assumptions };
}

/** Le sette sezioni canoniche, vuote: è il caso dello scenario startup. */
function emptySections(): AssumptionSection[] {
  return CANONICAL_SECTION_KEYS.map((key) => section(key, []));
}

/** Solo la sezione che interessa, resa da sola (è il componente interno, tipizzato). */
function renderSection(assumptions: AssumptionValue[], years: number[] = [2027, 2028, 2029]): string {
  return renderToStaticMarkup(
    <AssumptionsSectionTable
      section={{ key: "circolante", title: "Capitale circolante", assumptions }}
      years={years}
      Heading="h3"
      idPrefix="ipotesi-budget"
    />,
  );
}

describe("le sette sezioni", () => {
  it("compaiono tutte, nell'ordine del catalogo", () => {
    const html = renderToStaticMarkup(<AssumptionsSections model={infrannuale} />);
    const positions = CANONICAL_SECTION_KEYS.map((key) => html.indexOf(`id="ipotesi-budget-${key}"`));
    expect(positions.every((position) => position >= 0)).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
  });

  it("una per una hanno il loro titolo, il loro ancoraggio e il loro livello di titolo", () => {
    const html = renderToStaticMarkup(<AssumptionsSections model={infrannuale} />);
    for (const key of CANONICAL_SECTION_KEYS) {
      expect(html).toContain(`id="ipotesi-budget-${key}"`);
      expect(html).toContain(`id="ipotesi-budget-${key}-title"`);
    }
    // Il blocco è un h2, le sezioni scendono di un livello: l'outlining del
    // documento deve reggere anche senza styles.
    expect(html).toContain("<h2");
    expect(html).toContain("<h3");
  });

  it("il modello del fixture reale si rende senza stati d'errore", () => {
    const html = renderToStaticMarkup(<AssumptionsSections model={infrannuale} />);
    expect(html).not.toContain("non supportato");
    expect(html).not.toContain("non leggibile");
    expect(html).toContain("Crescita ricavi");
    expect(html).toContain("Origine storica"); // `legacy_unknown` sul DSO del fixture
  });

  it("una sezione senza ipotesi lo dice, non sparisce", () => {
    const html = renderToStaticMarkup(<AssumptionsSections model={reportWith(emptySections())} />);
    expect(html).toContain("Nessuna ipotesi materializzata");
    expect((html.match(/Nessuna ipotesi materializzata/g) ?? []).length).toBe(7);
  });
});

describe("valori per anno", () => {
  it("una colonna per anno dell'orizzonte, con l'anno nell'intestazione", () => {
    const html = renderSection([row("dso_days", ["58", "55", "52"])]);
    for (const year of [2027, 2028, 2029]) expect(html).toContain(`>${year}</th>`);
    expect(html).toContain("58 giorni");
  });

  it("più valori che anni: la colonna in più si dichiara", () => {
    const html = renderSection([row("dso_days", ["58", "55", "52", "50"])]);
    expect(html).toContain("Anno non dichiarato (4)");
    expect(html).toContain("50 giorni");
  });

  it("meno valori che anni: le celle che mancano si dicono, non si azzerano", () => {
    const html = renderSection([row("dso_days", ["58"])]);
    expect(html.match(/nessun valore/g)?.length).toBe(2);
    expect(html).not.toContain("0 giorni");
  });

  it("null, zero, negativo e booleano restano quattro cose diverse", () => {
    const html = renderSection([
      row("dso_days", [null, "0", "-12.5", true]),
      row("previdenza_scales_with_personnel", [true, false, true, null], { label: "Previdenza scala con personale" }),
    ]);
    expect(html).toContain("—");
    expect(html).toContain("0 giorni");
    expect(html).toContain("-12,5 giorni");
    expect(html).toContain(">Sì<");
    expect(html).toContain(">No<");
    // L'assenza non è mai muta: ha una frase per chi ascolta.
    expect(html).toContain("nessun valore");
  });

  it("un booleano a false non è un valore mancante", () => {
    const html = renderSection([row("cash_sweep_enabled", [false, false, false])]);
    expect(html).toContain(">No<");
    expect(html).not.toContain("nessun valore");
  });
});

describe("origine e stato di ogni riga", () => {
  it("sei origini, sei parole diverse", () => {
    const html = renderSection([
      row("dso_days", ["1"], { provenance: "user" }),
      row("dio_days", ["2"], { provenance: "automatic" }),
      row("dpo_days", ["3"], { provenance: "default" }),
      row("receivables_long_growth_pct", ["4"], { provenance: "override" }),
      row("sp01_growth_pct", ["5"], { provenance: "ignored", active: false }),
      row("sp04_growth_pct", ["6"], { provenance: "legacy_unknown" }),
    ]);
    for (const label of ["Utente", "Automatico", "Default", "Override", "Ignorato", "Origine storica"]) {
      expect(html).toContain(label);
    }
    // Ogni badge ha anche un'icona: il significato non passa dal colore.
    expect((html.match(/<svg/g) ?? []).length).toBeGreaterThan(5);
    expect(html).toContain("non attivo nel percorso corrente");
    expect(html).toContain("Non usato nel percorso corrente.");
  });

  it("un campo inerte del wizard non si presenta come pilota attivo", () => {
    const html = renderSection([row("investments", ["1000"], { provenance: "ignored", active: false })]);
    expect(html).toContain("Campo inerte");
    expect(html).not.toContain("In uso nel piano");
  });

  it("una riga senza anomalie dice che è in uso", () => {
    const html = renderSection([row("dso_days", ["58", "55", "52"])]);
    expect(html).toContain("In uso nel piano");
  });
});

describe("tabelle nidificate dentro la sezione", () => {
  it("una riga nidificata rende la sua tabella e non un valore seriale", () => {
    const html = renderSection([
      row("financing_loans", [null, null, null], {
        label: "Finanziamenti",
        financing_loans: [
          {
            name: "Mutuo",
            amount: "100000.00",
            opening_residual: "0.00",
            duration_years: 5,
            interest_rate: "3.25",
            grace_years: 0,
            balloon_pct: "0",
          },
        ],
      }),
    ]);
    expect(html).toContain("Finanziamenti e prestiti");
    expect(html).toContain("100.000,00 €");
    expect(html).toContain("Dettaglio nella tabella sotto.");
    expect(html).not.toContain("{&quot;name&quot;");
  });
});

describe("schema sconosciuto o malformato", () => {
  it("una versione maggiore non si rende a metà", () => {
    const future = { ...structuredClone(infrannuale), schema_version: 9 };
    const html = renderToStaticMarkup(<AssumptionsSections model={future} />);
    expect(html).toContain("Schema del report non supportato");
    expect(html).toContain("9");
    expect(html).not.toContain("ipotesi-budget-circolante");
  });

  it("un payload v1 che non rispetta il contratto si dichiara malformato", () => {
    const html = renderToStaticMarkup(<AssumptionsSections model={{ schema_version: 1, company: {} }} />);
    expect(html).toContain("Schema del report non leggibile");
    expect(html).toContain("Nessuna ipotesi viene mostrata");
  });

  it("il modello manca del tutto", () => {
    const html = renderToStaticMarkup(<AssumptionsSections model={undefined} />);
    expect(html).toContain("Schema del report non leggibile");
    expect(html).toContain("nessun modello ricevuto");
  });

  it("l'avviso ha un ruolo, non solo un colore", () => {
    const html = renderToStaticMarkup(
      <AssumptionsSchemaNotice verdict={{ ok: false, kind: "unknown", message: "Schema versione 2" }} />,
    );
    expect(html).toContain('role="status"');
    expect(html).toContain("<svg");
  });
});

describe("accessibilità del blocco", () => {
  it("ogni tabella ha una didascalia e le intestazioni il loro scope", () => {
    const html = renderSection([row("dso_days", ["58", "55", "52"]), row("dpo_days", ["27.9"], { label: "DPO" })]);
    expect(html).toContain("<caption");
    expect(html).toContain('scope="col"');
    expect(html).toContain('scope="row"');
    expect(html).toContain("Ogni riga dichiara la propria origine.");
  });

  it("le sezioni sono `section` con un titolo referenziato", () => {
    const html = renderSection([row("dso_days", ["58", "55", "52"])]);
    expect(html).toContain('aria-labelledby="ipotesi-budget-circolante-title"');
  });

  it("un payload monco non produce una pagina bianca", () => {
    const html = renderToStaticMarkup(<AssumptionsSections model={reportWith(emptySections())} headingLevel={3} />);
    expect(html.length).toBeGreaterThan(200);
    expect(html).toContain("<h3");
  });
});
