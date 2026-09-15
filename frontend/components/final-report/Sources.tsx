/**
 * Sezione 3 — Origine e qualità dei dati (design §§5.4, 6.1, 8) del report finale.
 *
 * Presentazione pura: nessun hook, nessuna chiamata API. Rende il percorso
 * della pratica, la tabella delle revisioni delle fonti e lo stato di qualità
 * dei dati di partenza con le sue diagnostiche. Dove una revisione non è
 * disponibile il campo è `null` e la sezione lo dice a parole — la
 * precisione non si inventa (§5.4). Icone e testo, mai il solo colore (§8).
 */

import { Card, CardContent } from "@/components/ui/card";
import type {
  Diagnostic,
  SourceDataQuality,
  SourceRevision,
  WorkflowType,
} from "@/types/final-report";
import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import {
  formatDateTimeItalian,
  MISSING_VALUE,
  QUALITY_LABELS,
  SEVERITY_LABELS,
  SOURCE_LABELS,
  WORKFLOW_LABELS,
} from "./final-report-format";

export interface ReportSourcesProps {
  workflow: WorkflowType;
  budgetScenarioName?: string;
  sourceRevisions: SourceRevision[];
  sourceDataQuality: SourceDataQuality;
}

const SEVERITY_ICONS = {
  info: Info,
  warning: TriangleAlert,
  error: CircleAlert,
} as const;

function Diagnosi({ items, idLabel }: { items: Diagnostic[]; idLabel: string }) {
  if (items.length === 0) return null;
  return (
    <table className="mt-2 w-full text-sm print:text-xs">
      <caption className="sr-only">{idLabel}</caption>
      <thead>
        <tr>
          <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
            Codice
          </th>
          <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
            Gravità
          </th>
          <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
            Sezione
          </th>
          <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
            Messaggio
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((d, i) => {
          const Icon = SEVERITY_ICONS[d.severity];
          return (
            <tr key={`${d.code}-${i}`}>
              <td className="border-b px-3 py-1.5 print:px-1">{d.code}</td>
              <td className="border-b px-3 py-1.5 print:px-1">
                <span className="inline-flex items-center gap-1.5">
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {SEVERITY_LABELS[d.severity]}
                </span>
              </td>
              <td className="border-b px-3 py-1.5 print:px-1">{d.section}</td>
              <td className="border-b px-3 py-1.5 print:px-1">{d.message}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function ReportSources({
  workflow,
  budgetScenarioName,
  sourceRevisions,
  sourceDataQuality,
}: ReportSourcesProps) {
  const QualityIcon =
    sourceDataQuality.status === "complete" ? CircleCheck : TriangleAlert;
  const diagnostics = sourceDataQuality.diagnostics ?? [];

  return (
    <section aria-labelledby="final-report-sources-title">
      <Card>
        <CardContent className="py-4 print:py-2">
          <h2 id="final-report-sources-title" className="mb-1 text-xl font-bold print:text-lg">
            Origine e qualità dei dati
          </h2>
          <p className="mb-3 text-sm text-muted-foreground print:text-xs">
            {WORKFLOW_LABELS[workflow]}
            {budgetScenarioName ? ` · scenario «${budgetScenarioName}»` : ""} ·{" "}
            {sourceRevisions.length} {sourceRevisions.length === 1 ? "fonte censita" : "fonti censite"}.
          </p>

          <h3 className="text-base font-semibold print:text-sm">Revisioni delle fonti</h3>
          <table className="mt-1 w-full text-sm print:text-xs">
            <caption className="sr-only">
              Identificativi e revisioni delle fonti da cui deriva il documento
            </caption>
            <thead>
              <tr>
                <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
                  Fonte
                </th>
                <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
                  Identificativo
                </th>
                <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
                  Revisione
                </th>
                <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
                  Aggiornata al
                </th>
                <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
                  Disponibilità
                </th>
              </tr>
            </thead>
            <tbody>
              {sourceRevisions.map((rev, i) => (
                <tr key={`${rev.source}-${i}`}>
                  <th
                    scope="row"
                    className="border-b px-3 py-1.5 text-left align-top font-medium print:px-1"
                  >
                    {SOURCE_LABELS[rev.source]}
                  </th>
                  <td className="border-b px-3 py-1.5 align-top print:px-1">
                    {rev.identifier ?? MISSING_VALUE}
                  </td>
                  <td className="border-b px-3 py-1.5 align-top print:px-1">
                    {rev.revision === null || rev.revision === undefined
                      ? "non disponibile"
                      : rev.revision}
                  </td>
                  <td className="border-b px-3 py-1.5 align-top print:px-1">
                    {rev.revision_at ? formatDateTimeItalian(rev.revision_at) : MISSING_VALUE}
                  </td>
                  <td className="border-b px-3 py-1.5 align-top print:px-1">
                    {rev.available === false ? (
                      <span className="inline-flex items-center gap-1.5">
                        <CircleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
                        Non disponibile
                      </span>
                    ) : rev.available === true ? (
                      <span className="inline-flex items-center gap-1.5">
                        <CircleCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
                        Disponibile
                      </span>
                    ) : (
                      "stato non dichiarato"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3 className="mt-4 text-base font-semibold print:text-sm">Qualità dei dati</h3>
          <p className="mt-1 flex items-center gap-1.5 text-sm print:text-xs">
            <QualityIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
            Completezza delle fonti: {QUALITY_LABELS[sourceDataQuality.status]}
          </p>
          {diagnostics.length > 0 ? (
            <Diagnosi items={diagnostics} idLabel="Diagnostiche sulla qualità dei dati" />
          ) : (
            <p className="mt-1 text-sm text-muted-foreground print:text-xs">
              Nessun avviso dalle fonti.
            </p>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
