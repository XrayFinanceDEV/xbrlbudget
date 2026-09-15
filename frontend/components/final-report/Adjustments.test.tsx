import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import bilancio from "../../../tests/fixtures/final_report/bilancio.json";
import infrannuale from "../../../tests/fixtures/final_report/infrannuale.json";
import startup from "../../../tests/fixtures/final_report/startup.json";
import type { Adjustments as AdjustmentsModel, FinalReportModel } from "@/types/final-report";
import { ReportAdjustments } from "./Adjustments";

const eur = (body: string): string => `${body}\u00A0€`;
const INFRANNUALE = infrannuale as unknown as FinalReportModel;
const BILANCIO = bilancio as unknown as FinalReportModel;
const STARTUP = startup as unknown as FinalReportModel;

const render = (adjustments: AdjustmentsModel): string =>
  renderToStaticMarkup(<ReportAdjustments adjustments={adjustments} />);

describe("ReportAdjustments (rettifiche apportate)", () => {
  it("infrannuale: le due zampe con i loro delta firmati, motivazione assente dichiarata", () => {
    const html = render(INFRANNUALE.adjustments);
    expect(html).toContain("Giornale rettifiche confermato.");
    expect(html).toContain("Ricavi");
    expect(html).toContain("ce01_ricavi_vendite");
    expect(html).toContain("Cassa");
    expect(html).toContain("sp09_disponibilita_liquide");
    expect(html).toContain("+120,00\u00A0€");
    expect(html).toContain(eur("-120,00"));
    // explanation null: «—», non cella muta.
    expect(html).toContain("—");
    expect(html).toContain("02/09/2026 08:00Z");
  });

  it("giornale non confermato: lo stato lo dice il testo, non il colore", () => {
    const report = structuredClone(STARTUP) as FinalReportModel;
    const html = render(report.adjustments);
    expect(html).toContain("NON confermato");
    expect(STARTUP.practice.workflow_type).toBe("startup");
  });

  it("entries vuote: nessuna rettifica, ma l'effetto netto dichiarato c'è lo stesso", () => {
    const html = render(BILANCIO.adjustments);
    expect(html).toContain("Nessuna rettifica economica registrata");
    expect(html).toContain("Le voci di sola conferma non sono riportate");
    expect(html).toContain("Effetto netto dichiarato");
    expect(html).toContain(eur("0,00"));
  });

  it("entries assenti: il dettaglio manca ed è detto, il netto resta quello del modello", () => {
    const adjustments: AdjustmentsModel = { confirmed: true, net_effect: "250.09" };
    const html = render(adjustments);
    expect(html).toContain("Dettaglio delle rettifiche non disponibile");
    expect(html).toContain(eur("250,09"));
    expect(html).not.toContain("<table");
  });

  it("nessun ricalcolo: la somma delle zampe non sostituisce mai net_effect", () => {
    const adjustments: AdjustmentsModel = {
      confirmed: true,
      net_effect: "0.00",
      entries: [
        {
          id: "a1",
          edited_field: "ce01_ricavi_vendite",
          edited_label: "Ricavi",
          edit_delta: "100.00",
          counterpart_field: "sp09_disponibilita_liquide",
          counterpart_label: "Cassa",
          counterpart_delta: "-100.00",
          created_at: "2026-09-02T08:00:00Z",
        },
        {
          id: "a2",
          edited_field: "ce02_altri ricavi",
          edited_label: "Altri ricavi",
          edit_delta: "50.00",
          counterpart_field: "sp07_crediti",
          counterpart_label: "Altri crediti",
          counterpart_delta: "-50.00",
          created_at: "2026-09-02T08:00:00Z",
        },
      ],
    };
    const html = render(adjustments);
    // Le due zampe mostrano i loro +100 e +50...
    expect(html).toContain("+100,00\u00A0€");
    expect(html).toContain("+50,00\u00A0€");
    // ...ma il netto è «0,00»: il componente NON ha sommato 150.
    expect(html).not.toContain(eur("150,00"));
    expect(html).toContain(eur("0,00"));
  });

  it("tabella semantica: intestazioni per le due zampe e righe con th di testa", () => {
    const html = render(INFRANNUALE.adjustments);
    expect(html).toContain("<caption");
    for (const heading of [
      "Voce modificata",
      "Delta",
      "Contropartita",
      "Delta contropartita",
      "Motivazione",
      "Data",
    ]) {
      expect(html).toContain(`>${heading}<`);
    }
    expect(html).toContain('<th scope="col"');
    expect(html).toContain('<th scope="row"');
    expect(html).toContain("<tfoot");
    expect(html).toContain("Effetto netto sugli aggregati");
  });

  it("i tre workflow condividono la stessa resa: la sezione non cambia forma", () => {
    for (const report of [INFRANNUALE, BILANCIO, STARTUP]) {
      const html = render(report.adjustments);
      expect(html).toContain("Rettifiche apportate");
      expect(html).toContain('aria-labelledby="final-report-adjustments-title"');
    }
  });
});
