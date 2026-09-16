import * as React from "react";
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  AssumptionsNestedTables,
  ceOverridesViewModel,
  financingLoansViewModel,
  nestedTableViewModel,
  pregressoViewModel,
  spIndexingViewModel,
  spOverridesViewModel,
  taxPlanViewModel,
  temporaryDifferencesViewModel,
} from "./AssumptionsTables";
import type { AssumptionValue } from "@/types/final-report";

function row(over: Partial<AssumptionValue>): AssumptionValue {
  return { field: "financing_loans", label: "Finanziamenti", values: [null, null], provenance: "user", active: true, ...over };
}

const YEARS = [2027, 2028, 2029];

describe("finanziamenti e prestiti", () => {
  it("una riga per contratto, con le sue sei cifre", () => {
    const model = financingLoansViewModel([
      {
        name: "Mutuo ipotecario",
        amount: "100000.00",
        opening_residual: "0.00",
        duration_years: 5,
        interest_rate: "3.25",
        grace_years: 0,
        balloon_pct: "0",
      },
    ]);
    expect(model.columns).toEqual([
      "Prestito",
      "Importo",
      "Residuo ad apertura",
      "Durata",
      "Tasso",
      "Preammortamento",
      "Quota finale",
    ]);
    expect(model.rows[0].map((cell) => cell.text)).toEqual([
      "Mutuo ipotecario",
      "100.000,00 €",
      "0,00 €",
      "5 anni",
      "3,25%",
      "nessun preammortamento",
      "0%",
    ]);
    // Lo zero della quota finale non è un'assenza.
    expect(model.rows[0][6].absent).toBe(false);
  });

  it("un prestito senza nome non sparisce, e un valore negativo si vede", () => {
    const model = financingLoansViewModel([
      {
        name: null,
        amount: "-25000.09",
        opening_residual: "25000.09",
        duration_years: 1,
        interest_rate: "0",
        grace_years: 1,
        balloon_pct: "100",
      },
    ]);
    expect(model.rows[0][0].text).toBe("Prestito 1 (senza nome)");
    expect(model.rows[0][1]).toMatchObject({ text: "-25.000,09 €", negative: true });
    expect(model.rows[0][5].text).toBe("1 anno");
  });

  it("il piano vuoto lo dichiara", () => {
    const model = financingLoansViewModel([]);
    expect(model.rows).toEqual([]);
    expect(model.note).toContain("Nessun prestito");
  });

  it("mostra durata assente e rimborsi senza perdere la quota oltre l'orizzonte", () => {
    const loan = { name: "Mutuo", amount: "100", opening_residual: "100", interest_rate: "3", grace_years: 0, balloon_pct: "0", repayments: ["25", "25"] };
    expect(financingLoansViewModel([loan]).rows[0][3].text).toBe("durata non dichiarata");
    const repayments = nestedTableViewModel({ kind: "financing_repayments", rows: [loan] }, [2027]);
    expect(repayments.rows.map((cells) => cells.map((cell) => cell.text))).toEqual([
      ["Mutuo", "2027", "25 €"],
      ["Mutuo", "Quota 2 (anno non dichiarato)", "25 €"],
    ]);
  });
});

describe("piano del pregresso", () => {
  it("le cinque posizioni, tutte in tabella — anche senza piano", () => {
    const model = pregressoViewModel({ crediti_commerciali: { opening: "100", amounts: ["50", "50"] } }, YEARS);
    expect(model.rows.map((cells) => cells[0].text)).toEqual([
      "Crediti commerciali",
      "Debiti fornitori",
      "Debiti tributari",
      "Debiti previdenziali",
      "Altri debiti",
    ]);
    expect(model.rows[1][1].text).toBe("nessun piano");
    expect(model.rows[1][1].srText).toContain("Nessun piano di rientro");
    // Tre colonne d'anno, due quote nel piano: la terza cella è assente, non zero.
    expect(model.rows[0].length).toBe(model.columns.length);
    expect(model.rows[0][3]).toMatchObject({ text: "50 €" });
    expect(model.rows[0][4]).toMatchObject({ text: "—", absent: true });
    expect(model.caption).toContain("1 posizione pianificata su 5");
  });

  it("uno stralcio dichiarato ha una riga sua", () => {
    const model = pregressoViewModel(
      { debiti_fornitori: { opening: "200", amounts: ["100", "100"], writeoff: ["0", "10"] } },
      [2027, 2028],
    );
    expect(model.rows.map((cells) => cells[0].text)).toContain("Debiti fornitori — stralcio");
    const stralcio = model.rows.find((cells) => cells[0].text.includes("stralcio"))!;
    expect(stralcio.map((cell) => cell.text)).toEqual(["Debiti fornitori — stralcio", "—", "0 €", "10 €"]);
  });

  it("la scelta di non incassare resta visibile nel pregresso", () => {
    const model = pregressoViewModel({ crediti_commerciali: { opening: "100", amounts: ["0"], non_incassato: true } }, YEARS);
    expect(model.rows.find((cells) => cells[0].text.includes("non incassato"))?.[1].text).toBe("sì");
  });

  it("più quote che anni: colonne aggiuntive, nessuna quota persa", () => {
    const model = pregressoViewModel(
      { altri_debiti: { opening: "10", amounts: ["5", "3", "2", "1"] } },
      [2027],
    );
    expect(model.columns.slice(2)).toEqual(["2027", "Quota 2 (anno non dichiarato)", "Quota 3 (anno non dichiarato)", "Quota 4 (anno non dichiarato)"]);
    expect(model.rows[4].map((cell) => cell.text)).toEqual(["Altri debiti", "10 €", "5 €", "3 €", "2 €", "1 €"]);
    for (const cells of model.rows) expect(cells.length).toBe(model.columns.length);
  });

  it("saldo, rateizzato e acconto hanno una tabella loro", () => {
    const model = taxPlanViewModel({
      opening: "120",
      amounts: ["50", "40"],
      saldo: "30",
      rateizzato: "90",
      acconto_pct: "100",
    });
    expect(model.rows.map((cells) => [cells[0].text, cells[1].text])).toEqual([
      ["Saldo dovuto", "30 €"],
      ["Rateizzato", "90 €"],
      ["Acconto", "100%"],
    ]);
  });

  it("nessun piano da nessuna parte è una frase, non una tabella vuota", () => {
    const model = pregressoViewModel({}, YEARS);
    expect(model.note).toContain("Nessuna posizione");
    expect(model.rows).toHaveLength(5);
  });
});

describe("differenze temporanee", () => {
  it("natura, scadenza e aliquota mancante", () => {
    const model = temporaryDifferencesViewModel([
      {
        name: "Fondo rischi",
        kind: "deductible",
        maturity: "short",
        opening_amount: "200",
        additions: "50",
        reversals: "-25",
        tax_rate: null,
      },
    ]);
    expect(model.rows[0].map((cell) => cell.text)).toEqual([
      "Fondo rischi",
      "Deducibile",
      "Breve",
      "200 €",
      "50 €",
      "-25 €",
      "—",
    ]);
    expect(model.rows[0][6].absent).toBe(true);
    expect(model.rows[0][5].negative).toBe(true);
  });
});

describe("override e indicizzazione", () => {
  it("il codice della voce resta in una colonna sua", () => {
    const ce = ceOverridesViewModel([{ field: "ce02_override", value: "120.00" }]);
    expect(ce.rows[0].map((cell) => cell.text)).toEqual(["2) Var. rimanenze di prodotti in c/lav., semilav. e finiti", "ce02_override", "120,00 €"]);
    const sp = spOverridesViewModel([{ field: "sp09_disponibilita_liquide", value: "-0.01" }]);
    expect(sp.rows[0][0].text).toBe("IV - Disponibilità liquide");
    expect(sp.rows[0][1].text).toBe("sp09_disponibilita_liquide");
    expect(sp.rows[0][2]).toMatchObject({ text: "-0,01 €", negative: true });
  });

  it("una voce che il catalogo non conosce si mostra col suo codice", () => {
    const sp = spOverridesViewModel([{ field: "sp99z_inventata", value: "1" }]);
    expect(sp.rows[0][0].text).toBe("sp99z_inventata");
  });

  it("il pilota dell'indicizzazione si legge", () => {
    const model = spIndexingViewModel([{ field: "sp16g", driver: "ricavi" }]);
    expect(model.rows[0].map((cell) => cell.text)).toEqual(["Altri debiti (entro)", "sp16g", "Ricavi"]);
  });
});

describe("dispatch per tipo di tabella", () => {
  it("tutte le tabelle nidificate del contratto hanno una resa", () => {
    const cases: Array<Parameters<typeof nestedTableViewModel>[0]> = [
      { kind: "financing_loans", rows: [] },
      { kind: "financing_repayments", rows: [] },
      { kind: "pregresso", plan: {} },
      { kind: "temporary_differences", rows: [] },
      { kind: "ce_overrides", rows: [] },
      { kind: "sp_overrides", rows: [] },
      { kind: "sp_indexing", rows: [] },
      { kind: "other_lenders", rows: [] },
      { kind: "other_lender_repayments", rows: [] },
    ];
    for (const item of cases) {
      const model = nestedTableViewModel(item, YEARS);
      expect(model.id).toBe(item.kind);
      expect(model.caption.length).toBeGreaterThan(0);
      expect(model.columns.length).toBeGreaterThan(0);
    }
  });

  it("gli altri finanziatori espongono residuo, tasso e quote per anno", () => {
    const lender = { name: "Socio", opening_residual: "90.125", interest_rate: "2.5", repayments: ["30.25"] };
    const summary = nestedTableViewModel({ kind: "other_lenders", rows: [lender] }, YEARS);
    const repayments = nestedTableViewModel({ kind: "other_lender_repayments", rows: [lender] }, YEARS);
    expect(summary.rows[0].map((cell) => cell.text)).toEqual(["Socio", "90,125 €", "2,5%"]);
    expect(repayments.rows[0].map((cell) => cell.text)).toEqual(["Socio", "2027", "30,25 €"]);
  });
});

describe("resa a schermo delle tabelle nidificate", () => {
  it("è una tabella con una didascalia, non un testo serializzato", () => {
    const html = renderToStaticMarkup(
      <AssumptionsNestedTables assumption={row({ pregresso: { crediti_commerciali: { opening: "100", amounts: ["50"] } } })} years={YEARS} />,
    );
    expect(html).toContain("<table");
    expect(html).toContain("<caption");
    expect(html).toContain('scope="row"');
    expect(html).toContain("Piano del pregresso");
    // Un `{ "opening": "100" }` in una cella è esattamente ciò che §6.4 vieta.
    expect(html).not.toContain('"opening"');
    expect(html).not.toContain("{&quot;");
  });

  it("una riga con due nidificate le rende tutte e due", () => {
    const html = renderToStaticMarkup(
      <AssumptionsNestedTables
        assumption={row({
          financing_loans: [
            {
              name: "Mutuo",
              amount: "1000",
              opening_residual: "1000",
              duration_years: 5,
              interest_rate: "3",
              grace_years: 0,
              balloon_pct: "0",
            },
          ],
          sp_overrides: [{ field: "sp09_disponibilita_liquide", value: "10" }],
        })}
        years={YEARS}
      />,
    );
    expect(html).toContain("Finanziamenti e prestiti");
    expect(html).toContain("Override dello stato patrimoniale");
  });
});
