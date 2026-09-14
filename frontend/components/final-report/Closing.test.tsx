import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import bilancio from "../../../tests/fixtures/final_report/bilancio.json";
import infrannuale from "../../../tests/fixtures/final_report/infrannuale.json";
import startup from "../../../tests/fixtures/final_report/startup.json";
import type { ClosingValue, FinalReportModel, InfrannualClosing } from "@/types/final-report";
import { ReportClosing } from "./Closing";

const eur = (body: string): string => `${body}\u00A0€`;
const INFRANNUALE = infrannuale as unknown as Extract<FinalReportModel, { practice: { workflow_type: "infrannuale" } }>;
const BILANCIO = bilancio as unknown as FinalReportModel;
const STARTUP = startup as unknown as FinalReportModel;

const chi = (closing: InfrannualClosing | null | undefined, workflow: FinalReportModel["practice"]["workflow_type"]) =>
  renderToStaticMarkup(<ReportClosing workflow={workflow} closing={closing} />);

describe("ReportClosing (dall'infrannuale alla chiusura)", () => {
  it("infrannuale: le cinque colonne del percorso verso la chiusura, valori cosi com'è", () => {
    const html = chi(INFRANNUALE.infrannual_closing, "infrannuale");
    for (const heading of [
      "Voce",
      "Progressivo osservato",
      "Comparabile",
      "Proiezione automatica",
      "Override utente",
      "Chiusura usata",
    ]) {
      expect(html).toContain(`>${heading}<`);
    }
    expect(html).toContain("alla data del 30/09/2026");
    expect(html).toContain("Ricavi");
    expect(html).toContain("ce01_ricavi_vendite");
    expect(html).toContain(eur("900,00")); // osservato, com'è stato letto
    expect(html).toContain(eur("1.200,00")); // chiusura usata, com'è persistita
  });

  it("null e zero non si confondono: «—» sulle colonne mancanti, 0,00 sullo zero vero", () => {
    const closing = structuredClone(INFRANNUALE.infrannual_closing) as InfrannualClosing;
    const row: ClosingValue = {
      code: "ce05_materie",
      label: "Costi per materie",
      observed: null,
      comparable: "0.00",
      automatic: null,
      override: "-20.50",
      closing_used: "1500.00",
    };
    closing.values = [...closing.values, row];
    const html = chi(closing, "infrannuale");
    const start = html.indexOf("Costi per materie");
    const riga = html.slice(start, html.indexOf("</tr>", start));
    expect(riga).toContain("—"); // observed assente
    expect(riga).toContain(eur("0,00")); // comparable: zero, non assenza
    expect(riga).toContain(eur("-20,50")); // override negativo col suo segno
    expect(riga).toContain(eur("1.500,00")); // chiusura usata, mai rianualizzata dal progressivo
  });

  it("osservato e stimato restano distinti: la cella «chiusura usata» riporta il valore del modello", () => {
    const closing = structuredClone(INFRANNUALE.infrannual_closing) as InfrannualClosing;
    closing.values = [{
      code: "ce01_ricavi_vendite",
      label: "Ricavi",
      observed: "900.00",
      comparable: "800.00",
      automatic: "1200.00",
      override: "1440.00",
      closing_used: "1440.00",
    }];
    const html = chi(closing, "infrannuale");
    expect(html).toContain(eur("900,00"));
    expect(html).toContain(eur("800,00"));
    expect(html).toContain(eur("1.200,00"));
    expect(html).toContain('data-testid="chiusura-usata-ce01_ricavi_vendite"');
    expect(html).toContain(eur("1.440,00"));
  });

  it("alert extra-contabili: tutti e sette i segnali, attivi o meno, in testo", () => {
    const html = chi(INFRANNUALE.infrannual_closing, "infrannuale");
    for (const area of ["Retribuzioni", "Fornitori", "Banche", "INPS", "INAIL", "Cartelle di riscossione", "IVA"]) {
      expect(html).toContain(area);
    }
    expect(html).toContain("Segnale attivo");
    expect(html).toContain("Nessun segnale");
    expect(html.match(/Segnale attivo/g)?.length).toBe(1);
    expect(html.match(/Nessun segnale/g)?.length).toBe(6);
  });

  it("bilancio e startup: la sezione dichiara di non applicabile, senza numeri in scena", () => {
    for (const workflow of ["bilancio", "startup"] as const) {
      const html = chi(undefined, workflow);
      expect(html).toContain("Sezione non applicabile");
      expect(html).toContain("data-testid=\"chiusura-non-applicabile\"");
      expect(html).not.toContain("€");
      expect(html).not.toContain("<table");
    }
  });

  it("infrannuale senza chiusura nel documento: assenza dichiarata, non tabella vuota", () => {
    const html = chi(null, "infrannuale");
    expect(html).toContain("senza dati di chiusura");
    expect(html).not.toContain("<table");
  });

  it("tabella semantica: caption per le voci e per i segnali, th di riga e di colonna", () => {
    const html = chi(INFRANNUALE.infrannual_closing, "infrannuale");
    expect(html).toContain("Chiusura infrannuale: progressivo osservato");
    expect(html).toContain("Segnali extra-contabili");
    expect(html).toContain('<th scope="col"');
    expect(html).toContain('<th scope="row"');
    expect(html).toContain('aria-labelledby="final-report-closing-title"');
  });

  it("nessun calcolo: il testo guida promette solo il confronto fra colonne", () => {
    const html = chi(INFRANNUALE.infrannual_closing, "infrannuale");
    // La legenda tratta—assenza è nel testo, non affidata al CSS.
    expect(html).toContain("indica un valore non");
    // Nessun totale di colonna: le righe restano quelle del modello, una per voce.
    expect(html.match(/data-testid="chiusura-usata-/g)?.length).toBe(
      INFRANNUALE.infrannual_closing.values.length,
    );
  });
});
