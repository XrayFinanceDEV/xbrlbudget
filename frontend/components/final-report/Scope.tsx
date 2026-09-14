/**
 * Sezione 1 — Copertina e perimetro (design §6.1) del report finale.
 *
 * Presentazione pura: nessun hook, nessuna chiamata API, nessun calcolo.
 * Consuma i sotto-blocchi del `FinalReportModel` che le servono (azienda,
 * pratica, data di generazione, stato) e rende il perimetro in modo diverso
 * per i tre workflow: lo scenario sorgente e l'anno di chiusura compaiono
 * solo nel percorso infrannuale; su startup l'assenza dello storico è
 * dichiarata, non taciuta.
 */

import { Card, CardContent } from "@/components/ui/card";
import type { CompanyIdentity, Practice, Readiness } from "@/types/final-report";
import { CircleCheck, TriangleAlert, CircleX } from "lucide-react";
import {
  formatDateItalian,
  formatDateTimeItalian,
  MISSING_VALUE,
  periodMonthsLabel,
  READINESS_LABELS,
  WORKFLOW_LABELS,
} from "./final-report-format";

export interface ReportScopeProps {
  company: CompanyIdentity;
  practice: Practice;
  generated_at: string;
  readiness: Readiness;
}

const STATO_ICONE = {
  ready: CircleCheck,
  draft: TriangleAlert,
  blocked: CircleX,
} as const;

function Rigga({ etichetta, valore }: { etichetta: string; valore: string }) {
  return (
    <tr>
      <th
        scope="row"
        className="border-b px-3 py-1.5 text-left align-top font-medium text-muted-foreground print:px-1"
      >
        {etichetta}
      </th>
      <td className="border-b px-3 py-1.5 text-left align-top text-foreground print:px-1">
        {valore}
      </td>
    </tr>
  );
}

export function ReportScope({ company, practice, generated_at, readiness }: ReportScopeProps) {
  const { workflow_type, budget_scenario, periods } = practice;
  const StatoIcon = STATO_ICONE[readiness.status];
  const annoStorico =
    periods.historical_year !== null
      ? String(periods.historical_year)
      : workflow_type === "startup"
        ? "Nessuno storico: il piano parte dai saldi di apertura"
        : MISSING_VALUE;

  return (
    <section aria-labelledby="final-report-scope-title">
      <Card>
        <CardContent className="py-4 print:py-2">
          <div className="mb-3 text-center print:mb-2">
            <h2
              id="final-report-scope-title"
              className="text-2xl font-bold text-foreground print:text-xl"
            >
              Report finale di analisi
            </h2>
            <p className="text-base font-semibold print:text-sm">{company.name}</p>
            <p className="text-sm text-muted-foreground print:text-xs">
              {WORKFLOW_LABELS[workflow_type]} · generato il {formatDateTimeItalian(generated_at)}
            </p>
          </div>

          <p className="mb-2 flex items-center gap-1.5 text-sm font-medium print:text-xs">
            <StatoIcon
              className="h-4 w-4 shrink-0"
              aria-hidden="true"
              data-testid={`stato-${readiness.status}`}
            />
            {/* Il stato si legge dal testo: l'icona è solo un rinforzo. */}
            Documento: {READINESS_LABELS[readiness.status]}
          </p>

          <table className="w-full text-sm print:text-xs">
            <caption className="sr-only">Perimetro del documento</caption>
            <tbody>
              <Rigga
                etichetta="Azienda"
                valore={
                  company.tax_id
                    ? `${company.name} · CF/PIVA ${company.tax_id}`
                    : `${company.name} · codice fiscale non dichiarato`
                }
              />
              <Rigga
                etichetta="Percorso"
                valore={
                  // Il periodo parziale appartiene allo scenario sorgente: la
                  // riga «Scenario sorgente» lo dichiara lí, qui non si
                  // attribuisce a quest'uno un `period_months` che non suo.
                  WORKFLOW_LABELS[workflow_type]
                }
              />
              <Rigga
                etichetta="Scenario budget"
                valore={`${budget_scenario.name} (#${budget_scenario.id}) · anno base ${budget_scenario.base_year}`}
              />
              {practice.workflow_type === "infrannuale" && (
                <Rigga
                  etichetta="Scenario sorgente"
                  valore={`${practice.source_scenario.name} (#${practice.source_scenario.id}) · anno base ${practice.source_scenario.base_year} · ${periodMonthsLabel(practice.source_scenario.period_months)}`}
                />
              )}
              {practice.workflow_type !== "infrannuale" && practice.source_scenario && (
                <Rigga
                  etichetta="Scenario sorgente"
                  valore={`${practice.source_scenario.name} (#${practice.source_scenario.id})`}
                />
              )}
              <Rigga etichetta="Anno storico di riferimento" valore={annoStorico} />
              {workflow_type === "infrannuale" && (
                <Rigga
                  etichetta="Anno di chiusura attesa"
                  valore={
                    periods.closing_year !== null
                      ? String(periods.closing_year)
                      : "Non dichiarato"
                  }
                />
              )}
              {workflow_type !== "infrannuale" && periods.closing_year !== null && (
                <Rigga
                  etichetta="Anno di chiusura attesa"
                  valore={String(periods.closing_year)}
                />
              )}
              <Rigga
                etichetta="Orizzonte di previsione"
                valore={`${periods.forecast_years.join(", ")} (${periods.forecast_years.length} ${periods.forecast_years.length === 1 ? "anno" : "anni"})`}
              />
              <Rigga
                etichetta="Data del documento"
                valore={formatDateItalian(generated_at)}
              />
            </tbody>
          </table>
        </CardContent>
      </Card>
    </section>
  );
}
