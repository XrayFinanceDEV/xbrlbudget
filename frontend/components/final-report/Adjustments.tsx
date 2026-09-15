/**
 * Sezione 4 — Rettifiche apportate (design §6.2) del report finale.
 *
 * Presentazione pura: nessun hook, nessun calcolo. Il modello porta già
 * soltanto gli eventi economici effettivi (le voci `confirm` sono escluse a
 * monte) e l'effetto netto calcolato dal backend: qui si mostra, non si somma.
 * Per ogni rettifica si distinguono le DUE zampe — voce modificata e
 * contropartita, ciascuna con il proprio delta firmato — e lo stato di
 * conferma del giornale.
 */

import { Card, CardContent } from "@/components/ui/card";
import type { Adjustments } from "@/types/final-report";
import { CircleAlert, CircleCheck } from "lucide-react";
import { formatDateTimeItalian, formatSignedEuro, MISSING_VALUE } from "./final-report-format";

export interface ReportAdjustmentsProps {
  adjustments: Adjustments;
}

export function ReportAdjustments({ adjustments }: ReportAdjustmentsProps) {
  const entries = adjustments.entries;
  const ConfirmationIcon = adjustments.confirmed ? CircleCheck : CircleAlert;

  return (
    <section aria-labelledby="final-report-adjustments-title">
      <Card>
        <CardContent className="py-4 print:py-2">
          <h2
            id="final-report-adjustments-title"
            className="mb-1 text-xl font-bold print:text-lg"
          >
            Rettifiche apportate
          </h2>

          <p
            className="mb-3 flex items-center gap-1.5 text-sm print:text-xs"
            data-testid="rettifiche-conferma"
          >
            <ConfirmationIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
            {adjustments.confirmed
              ? "Giornale rettifiche confermato."
              : "Giornale rettifiche NON confermato: i valori qui sotto restano provvisori."}
          </p>

          {entries === undefined ? (
            <p className="text-sm text-muted-foreground print:text-xs">
              Dettaglio delle rettifiche non disponibile: è dichiarato solo l{""}
              <span className="font-medium">effetto netto</span> in fondo alla sezione.
            </p>
          ) : entries.length === 0 ? (
            <p className="text-sm text-muted-foreground print:text-xs">
              Nessuna rettifica economica registrata. Le voci di sola conferma non sono
              riportate in questo elenco.
            </p>
          ) : (
            <table className="w-full text-sm print:text-xs">
              <caption className="sr-only">
                Rettifiche economiche: voce modificata, contropartita, delta e motivazione
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
                    Voce modificata
                  </th>
                  <th scope="col" className="border-b px-3 py-1.5 text-right font-medium print:px-1">
                    Delta
                  </th>
                  <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
                    Contropartita
                  </th>
                  <th scope="col" className="border-b px-3 py-1.5 text-right font-medium print:px-1">
                    Delta contropartita
                  </th>
                  <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
                    Motivazione
                  </th>
                  <th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">
                    Data
                  </th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id}>
                    <th
                      scope="row"
                      className="border-b px-3 py-1.5 text-left align-top font-medium print:px-1"
                    >
                      {e.edited_label}
                      <span className="block text-xs font-normal text-muted-foreground">
                        {e.edited_field}
                      </span>
                    </th>
                    <td className="border-b px-3 py-1.5 text-right align-top tabular-nums print:px-1">
                      {formatSignedEuro(e.edit_delta)}
                    </td>
                    <td className="border-b px-3 py-1.5 align-top print:px-1">
                      {e.counterpart_label}
                      <span className="block text-xs text-muted-foreground">
                        {e.counterpart_field}
                      </span>
                    </td>
                    <td className="border-b px-3 py-1.5 text-right align-top tabular-nums print:px-1">
                      {formatSignedEuro(e.counterpart_delta)}
                    </td>
                    <td className="border-b px-3 py-1.5 align-top print:px-1">
                      {e.explanation ?? MISSING_VALUE}
                    </td>
                    <td className="border-b px-3 py-1.5 align-top print:px-1 whitespace-nowrap">
                      {formatDateTimeItalian(e.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th
                    scope="row"
                    colSpan={4}
                    className="border-t px-3 py-1.5 text-left font-semibold print:px-1"
                  >
                    Effetto netto sugli aggregati (riconciliazione prima &rarr; rettifiche
                    &rarr; dopo, calcolata dal documento)
                  </th>
                  <td
                    colSpan={2}
                    className="border-t px-3 py-1.5 text-right font-semibold tabular-nums print:px-1"
                  >
                    {formatSignedEuro(adjustments.net_effect)}
                  </td>
                </tr>
              </tfoot>
            </table>
          )}

          {entries === undefined && (
            <p className="mt-2 text-sm font-medium print:text-xs">
              Effetto netto dichiarato: {formatSignedEuro(adjustments.net_effect)}
            </p>
          )}
          {entries !== undefined && entries.length === 0 && (
            <p className="mt-2 text-sm font-medium print:text-xs">
              Effetto netto dichiarato: {formatSignedEuro(adjustments.net_effect)}
            </p>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
