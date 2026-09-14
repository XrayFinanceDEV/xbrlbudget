/**
 * Sezione 5 — Dall'infrannuale alla chiusura (design §§6.1, 6.3) del report
 * finale.
 *
 * Presentazione pura: nessun hook, nessun calcolo, nessuna anualizzazione.
 * Per ogni voce mette in colonne separate il progressivo osservato, il
 * comparabile, la proiezione automatica, l'override dell'utente e il valore
 * di chiusura usato: ciò che è osservato si distingue da ciò che è stimato
 * senza dover inferire nulla. Gli alert extra-contabili completano il quadro
 * e non toccano i numeri.
 *
 * Su bilancio e startup la sezione dice esplicitamente che non è applicabile:
 * il documento non tace una sezione prevista dall'indice (§6.1).
 */

import { Card, CardContent } from "@/components/ui/card";
import type { ExtraAccountingAlerts, InfrannualClosing, WorkflowType } from "@/types/final-report";
import { CircleCheck, MinusCircle } from "lucide-react";
import { formatDateItalian, formatEuro, WORKFLOW_LABELS } from "./final-report-format";

export interface ReportClosingProps {
  workflow: WorkflowType;
  /** Presente solo nel workflow infrannuale; altrove `null`/`undefined`. */
  closing?: InfrannualClosing | null;
}

const ALERT_LABELS: Array<{ key: keyof ExtraAccountingAlerts; label: string }> = [
  { key: "retribuzioni", label: "Retribuzioni" },
  { key: "fornitori", label: "Fornitori" },
  { key: "banche", label: "Banche" },
  { key: "inps", label: "INPS" },
  { key: "inail", label: "INAIL" },
  { key: "riscossione", label: "Cartelle di riscossione" },
  { key: "iva", label: "IVA" },
];

export function ReportClosing({ workflow, closing }: ReportClosingProps) {
  if (workflow !== "infrannuale" || !closing) {
    return (
      <section aria-labelledby="final-report-closing-title">
        <Card>
          <CardContent className="py-4 print:py-2">
            <h2 id="final-report-closing-title" className="mb-1 text-xl font-bold print:text-lg">
              Dall&apos;infrannuale alla chiusura
            </h2>
            <p className="text-sm text-muted-foreground print:text-xs" data-testid="chiusura-non-applicabile">
              {workflow === "infrannuale"
                ? "Percorso infrannuale senza dati di chiusura nel documento: sezione non compilabile."
                : `Sezione non applicabile: il ${WORKFLOW_LABELS[workflow].toLowerCase()} non prevede una chiusura infrannuale.`}
            </p>
          </CardContent>
        </Card>
      </section>
    );
  }

  return (
    <section aria-labelledby="final-report-closing-title">
      <Card>
        <CardContent className="py-4 print:py-2">
          <h2 id="final-report-closing-title" className="mb-1 text-xl font-bold print:text-lg">
            Dall&apos;infrannuale alla chiusura
          </h2>
          <p className="mb-3 text-sm text-muted-foreground print:text-xs">
            Confronto fra progressivo alla data del {formatDateItalian(closing.period_end)},
            proiezione a fine esercizio e valore di chiusura usato come base del budget.
            Un trattino (<span className="font-medium">—</span>) indica un valore non
            presente: uno 0,00 è uno zero, non un&apos;assenza.
          </p>

          <table className="w-full text-sm print:text-xs">
            <caption className="sr-only">
              Chiusura infrannuale: progressivo osservato, comparabile, proiezione automatica,
              override e valore di chiusura usato, per voce
            </caption>
            <thead>
              <tr>
                <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
                  Voce
                </th>
                <th scope="col" className="border-b px-3 py-1.5 text-right font-medium print:px-1">
                  Progressivo osservato
                </th>
                <th scope="col" className="border-b px-3 py-1.5 text-right font-medium print:px-1">
                  Comparabile
                </th>
                <th scope="col" className="border-b px-3 py-1.5 text-right font-medium print:px-1">
                  Proiezione automatica
                </th>
                <th scope="col" className="border-b px-3 py-1.5 text-right font-medium print:px-1">
                  Override utente
                </th>
                <th scope="col" className="border-b px-3 py-1.5 text-right font-medium print:px-1">
                  Chiusura usata
                </th>
              </tr>
            </thead>
            <tbody>
              {closing.values.map((v) => (
                <tr key={v.code}>
                  <th
                    scope="row"
                    className="border-b px-3 py-1.5 text-left align-top font-medium print:px-1"
                  >
                    {v.label}
                    <span className="block text-xs font-normal text-muted-foreground">
                      {v.code}
                    </span>
                  </th>
                  <td className="border-b px-3 py-1.5 text-right align-top tabular-nums print:px-1">
                    {formatEuro(v.observed)}
                  </td>
                  <td className="border-b px-3 py-1.5 text-right align-top tabular-nums print:px-1">
                    {formatEuro(v.comparable)}
                  </td>
                  <td className="border-b px-3 py-1.5 text-right align-top tabular-nums print:px-1">
                    {formatEuro(v.automatic)}
                  </td>
                  <td className="border-b px-3 py-1.5 text-right align-top tabular-nums print:px-1">
                    {formatEuro(v.override)}
                  </td>
                  <td
                    className="border-b px-3 py-1.5 text-right align-top font-semibold tabular-nums print:px-1"
                    data-testid={`chiusura-usata-${v.code}`}
                  >
                    {formatEuro(v.closing_used)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3 className="mt-4 text-base font-semibold print:text-sm">
            Segnali extra-contabili
          </h3>
          <p className="text-sm text-muted-foreground print:text-xs">
            Segnalazioni persistite sulla chiusura: completano il quadro e non modificano i
            calcoli.
          </p>
          <table className="mt-1 w-full text-sm print:text-xs">
            <caption className="sr-only">
              Segnali extra-contabili persistiti sulla chiusura infrannuale
            </caption>
            <thead>
              <tr>
                <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
                  Area
                </th>
                <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
                  Stato del segnale
                </th>
              </tr>
            </thead>
            <tbody>
              {ALERT_LABELS.map(({ key, label }) => (
                <tr key={key}>
                  <th
                    scope="row"
                    className="border-b px-3 py-1.5 text-left align-top font-medium print:px-1"
                  >
                    {label}
                  </th>
                  <td className="border-b px-3 py-1.5 align-top print:px-1">
                    <span className="inline-flex items-center gap-1.5">
                      {closing.extra_accounting_alerts[key] ? (
                        <>
                          <CircleCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
                          Segnale attivo
                        </>
                      ) : (
                        <>
                          <MinusCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                          Nessun segnale
                        </>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </section>
  );
}
