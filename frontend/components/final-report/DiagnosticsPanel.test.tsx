import * as React from "react";
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DiagnosticsPanel, DIAGNOSTICS_TITLE } from "./DiagnosticsPanel";
import { groupDiagnostics, sectionLabel, severityCounts, severityView } from "./DiagnosticsGrouping";
import type { Diagnostic } from "@/types/final-report";

/** Testo nudo: React escape gli apostrofi, e fra le classi il testo è quello che
 *  l'occhio (o lo screen reader) legge davvero. */
const plain = (html: string): string =>
  html.replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, "&").replace(/<[^>]*>/g, " ");

const ERROR: Diagnostic = {
  code: "adjustments_unconfirmed",
  severity: "error",
  section: "adjustments",
  message: "Le rettifiche economiche non sono state confermate.",
};
const WARNING: Diagnostic = {
  code: "legacy_assumption_provenance",
  severity: "warning",
  section: "assumptions",
  message: "Origine delle ipotesi non tracciata per i record storici.",
};
const INFO: Diagnostic = { code: "narrative_missing", severity: "info", section: "narrative", message: "Commento mancante." };

function panel(diagnostics: readonly Diagnostic[] | undefined): string {
  return renderToStaticMarkup(<DiagnosticsPanel diagnostics={diagnostics} />);
}

describe("raggruppamento", () => {
  it("prima gli errori, poi gli avvisi, poi le note", () => {
    const groups = groupDiagnostics([INFO, WARNING, ERROR]);
    expect(groups.map((group) => group.severity)).toEqual(["error", "warning", "info"]);
    expect(groups[0].count).toBe(1);
  });

  it("dentro una severità, le sezioni stanno nell'ordine in cui arrivano", () => {
    const groups = groupDiagnostics([
      { ...ERROR, section: "sources" },
      { ...ERROR, section: "forecast" },
      { ...ERROR, section: "sources" },
    ]);
    expect(groups[0].sections.map((section) => section.section)).toEqual(["sources", "forecast"]);
    expect(groups[0].sections[0].items).toHaveLength(2);
  });

  it("il riepilogo dichiara anche gli zeri", () => {
    const counts = severityCounts([WARNING]);
    expect(counts.map((row) => [row.severity, row.count])).toEqual([
      ["error", 0],
      ["warning", 1],
      ["info", 0],
    ]);
  });

  it("le sezioni del modello hanno un nome italiano, e il codice resta", () => {
    expect(sectionLabel("assumptions")).toBe("Ipotesi del budget");
    expect(sectionLabel("closing")).toBe("Chiusura infrannuale");
    expect(sectionLabel("magia")).toBe("magia");
    expect(groupDiagnostics([{ ...INFO, section: "magia" }])[0].sections[0].known).toBe(false);
  });

  it("una severità che non è delle tre non si fonde con «nota»", () => {
    const groups = groupDiagnostics([{ ...INFO, severity: "critico" as Diagnostic["severity"] }]);
    expect(groups).toHaveLength(1);
    expect(groups[0]).toMatchObject({ severity: "critico", known: false, count: 1 });
    expect(groups[0].view.label).toBe("Severità non dichiarata");
    expect(severityView("critico").description).toContain("critico");
  });
});

describe("il pannello", () => {
  it("ha un titolo, un riepilogo e i gruppi", () => {
    const html = panel([ERROR, WARNING, INFO]);
    expect(html).toContain(DIAGNOSTICS_TITLE);
    expect(html).toContain("<caption");
    expect(plain(html)).toContain("Errore");
    expect(plain(html)).toContain("Avviso");
    expect(plain(html)).toContain("Nota");
    expect(html).toContain("Le rettifiche economiche non sono state confermate.");
    expect(html).toContain("codice adjustments_unconfirmed, sezione adjustments");
    expect(html).toContain("<svg");
  });

  it("elenca per sezione con una lista nominata", () => {
    const html = panel([WARNING]);
    expect(html).toContain("Ipotesi del budget");
    expect(html).toContain('aria-label="Ipotesi del budget: segnalazioni"');
  });

  it("il nulla dichiarato e il nulla arrivato sono due frasi diverse", () => {
    expect(panel([])).toContain("Nessun rilievo dichiarato");
    const missing = panel(undefined);
    expect(missing).toContain("Il modello non dichiara la lista diagnostica");
    expect(missing).not.toContain("Nessun rilievo dichiarato");
  });

  it("i conti a tre righe ci sono anche quando non c'è nulla", () => {
    const html = panel(undefined);
    expect((html.match(/<tbody/g) ?? []).length).toBe(1);
    expect(html).toContain(">0<span");
  });

  it("una gravità non dichiarata si vede nel gruppo e nel riepilogo", () => {
    const html = panel([{ ...INFO, severity: "critico" as Diagnostic["severity"] }]);
    expect(plain(html)).toContain('gravità "critico" non è una delle tre');
    expect(plain(html)).toContain("Severità non dichiarata");
  });

  it("il livello dei titoli segue il contesto, senza saltarne uno", () => {
    const pagina = panel([ERROR]);
    expect(pagina).toContain("<h2");
    expect(pagina).toContain("<h3");
    expect(pagina).toContain("<h4");
    const annidato = renderToStaticMarkup(<DiagnosticsPanel diagnostics={[ERROR]} headingLevel={3} />);
    expect(annidato).not.toContain("<h2");
    expect(annidato).toContain("<h3");
    expect(annidato).toContain("<h4");
    expect(annidato).toContain("<h5");
  });
});
