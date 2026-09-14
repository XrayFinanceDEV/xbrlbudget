/**
 * Il pannello di diagnostica del report finale (M1-08B).
 *
 * §6.1 (sezione 11) e §8: errori bloccanti, avvisi e note, raggruppati per
 * severità e per sezione, con icona + parola + codice accanto al colore.
 *
 * Due stati che si somigliano e non sono la stessa cosa:
 *   - `diagnostics: []`      → «nessuna segnalazione», il documento è pulito;
 *   - `diagnostics` assente  → «il modello non dichiara l'elenco», che è un «non
 *     lo so» e si legge come tale (CLAUDE.md › «Un estrattore dichiara sempre le
 *     proprie chiavi diagnostiche, anche a zero»).
 * Il pannello li rende diversi, e il riepilogo esce sempre a tre righe — anche a
 * zero — perché un assente e uno zero non devono avere lo stesso aspetto.
 */
import * as React from "react";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { Diagnostic } from "@/types/final-report";
import { ROW_HEAD } from "./AssumptionsFormat";
import { groupDiagnostics, severityCounts, sectionLabel } from "./DiagnosticsGrouping";

export interface DiagnosticsPanelProps {
  /** `undefined` = chiave assente dal modello: «non dichiarato», non «pulito». */
  diagnostics: readonly Diagnostic[] | undefined;
  /** Il blocco vive in una pagina (2) o dentro una sezione (3). */
  headingLevel?: 2 | 3;
  id?: string;
  className?: string;
}

/** Il titolo del pannello, §6.1. */
export const DIAGNOSTICS_TITLE = "Diagnostica e punti da verificare";

export function DiagnosticsPanel({
  diagnostics,
  headingLevel = 2,
  id = "diagnostica",
  className,
}: DiagnosticsPanelProps) {
  const BlockHeading: "h2" | "h3" = headingLevel === 3 ? "h3" : "h2";
  const GroupHeading: "h3" | "h4" = headingLevel === 3 ? "h4" : "h3";
  const SectionHeading: "h4" | "h5" = headingLevel === 3 ? "h5" : "h4";
  const declared = Array.isArray(diagnostics);
  const items = declared ? diagnostics : [];
  const counts = severityCounts(items);
  const groups = groupDiagnostics(items);

  return (
    <section id={id} aria-labelledby={`${id}-title`} className={cn("space-y-4", className)}>
      <BlockHeading
        id={`${id}-title`}
        className={headingLevel === 3 ? "text-lg font-semibold" : "text-2xl font-bold"}
      >
        {DIAGNOSTICS_TITLE}
      </BlockHeading>

      {!declared ? (
        <Card className="border-dashed border-amber-400">
          <CardContent className="py-3 text-sm">
            Il modello non dichiara la lista diagnostica: sotto non c&apos;è nulla perché nulla è
            arrivato, non perché il documento risulti pulito.
          </CardContent>
        </Card>
      ) : null}

      <Table className="print:text-[11px]">
        <TableCaption>Segnalazioni per gravità: un conteggio dichiarato anche dove è zero.</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Gravità</TableHead>
            <TableHead scope="col" className="text-right">
              Segnalazioni
            </TableHead>
            <TableHead scope="col">Che cosa significa</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {counts.map((row) => (
            <TableRow key={row.severity}>
              <th scope="row" className={ROW_HEAD}>
                <span className={cn("inline-flex items-center gap-2", row.view.className)}>
                  <row.view.Icon className="h-4 w-4" aria-hidden="true" />
                  {row.view.label}
                  {!row.known ? (
                    <span className="text-xs font-normal">gravità non dichiarata dal contratto v1</span>
                  ) : null}
                </span>
              </th>
              <TableCell className="text-right tabular-nums">
                {row.count}
                <span className="sr-only">{row.count === 1 ? " segnalazione" : " segnalazioni"}</span>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">{row.view.description}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {declared && items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nessun rilievo dichiarato: nessun controllo ha trovato punti da verificare.
        </p>
      ) : null}

      {groups.map((group) => (
        <Card key={`${id}-${group.severity}`} className="print:break-inside-avoid">
          <CardHeader className="pb-2">
            <GroupHeading id={`${id}-${group.severity}-title`} className={cn("flex items-center gap-2 text-base font-semibold", group.view.className)}>
              <group.view.Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {group.view.label}
              <span className="text-xs font-normal text-muted-foreground">
                {group.count} {group.count === 1 ? "segnalazione" : "segnalazioni"}
              </span>
              {!group.known ? (
                <span className="text-xs font-normal">
                  — gravità &quot;{group.severity}&quot; non è una delle tre del contratto v1
                </span>
              ) : null}
            </GroupHeading>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {group.sections.map((section) => (
                <div key={`${id}-${group.severity}-${section.section}`}>
                  <SectionHeading className="text-sm font-semibold">
                    {section.label}
                    {!section.known ? (
                      <span className="ml-1 text-xs font-normal text-muted-foreground">
                        — sezione non dichiarata
                      </span>
                    ) : null}
                  </SectionHeading>
                  <ul className="mt-1 space-y-1" aria-label={`${sectionLabel(section.section)}: segnalazioni`}>
                    {section.items.map((item, index) => (
                      <li key={`${item.code}-${index}`} className="text-sm">
                        <span className="font-medium">{item.message}</span>{" "}
                        <span className="text-xs text-muted-foreground">
                          codice {item.code}, sezione {item.section}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </section>
  );
}
