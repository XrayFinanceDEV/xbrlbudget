/**
 * Il blocco «Ipotesi del budget» del report finale (M1-08B).
 *
 * Rende le sette sezioni del wizard, nell'ordine del catalogo (§6.4), con un
 * valore per anno, il badge d'origine su ogni riga e le tabelle nidificate dove
 * il valore non è uno scalare.
 *
 * Componente di sola presentazione: nessun hook, nessuna chiamata, nessun
 * ricalcolo — i valori sono quelli persistiti dal motore, e il report li
 * racconta come il motore li ha lasciati. Le decisioni (ordine, colonne, stati)
 * stanno in `AssumptionsCatalog`, la formattazione in `AssumptionsFormat`.
 */
import * as React from "react";
import { CircleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
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
import type { AssumptionSection } from "@/types/final-report";
import {
  CANONICAL_SECTION_KEYS,
  assumptionRowState,
  hasNestedTable,
  layoutSections,
  readFinalReport,
  rowCells,
  sectionColumns,
  type SchemaVerdict,
} from "./AssumptionsCatalog";
import { ROW_HEAD, scalarKindOf } from "./AssumptionsFormat";
import { AssumptionsNestedTables, ScalarCell } from "./AssumptionsTables";
import { ProvenanceBadge, ProvenanceLegend } from "./ProvenanceBadge";

export interface AssumptionsSectionsProps {
  /** Il payload dell'endpoint: un `FinalReportModel` v1, o qualcosa che va dichiarato. */
  model: unknown;
  /** Ancora per il sommario di §9. */
  id?: string;
  /** Profondità del titolo del blocco; le sette sezioni scendono di un livello. */
  headingLevel?: 2 | 3;
  /** La legenda delle sei origini (in corpo: §8 vieta il significato solo cromatico). */
  showLegend?: boolean;
}

/**
 * Che cosa si rende quando il payload non è un modello leggibile: uno stato
 * dichiarato, non un documento a metà. §5.2 — una versione maggiore si rifiuta,
 * non si interpreta.
 */
export function AssumptionsSchemaNotice({ verdict }: { verdict: Extract<SchemaVerdict, { ok: false }> }) {
  const unknown = verdict.kind === "unknown";
  return (
    <section id="ipotesi-budget" aria-labelledby="ipotesi-budget-title">
      <Alert variant={unknown ? "default" : "destructive"} role="status">
        <CircleAlert className="h-4 w-4" />
        <AlertTitle>{unknown ? "Schema del report non supportato" : "Schema del report non leggibile"}</AlertTitle>
        <AlertDescription>
          <p>{verdict.message}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Nessuna ipotesi viene mostrata: rendere solo le sezioni riconosciute produrrebbe un
            documento che sembra completo e non lo è.
          </p>
        </AlertDescription>
      </Alert>
    </section>
  );
}

export interface AssumptionsSectionProps {
  section: { key: string; title: string; assumptions: AssumptionSection["assumptions"]; missing?: boolean };
  years: readonly number[];
  /** Il tag del titolo di sezione, deciso dal chiamante per non rompere l'outlining. */
  Heading: "h2" | "h3" | "h4";
  idPrefix?: string;
}

/** Una sezione: una tabella accessibile (caption + scope), più le sue nidificate. */
export function AssumptionsSectionTable({ section, years, Heading, idPrefix = "ipotesi" }: AssumptionsSectionProps) {
  // Un passo sotto il titolo di sezione: le tabelle nidificate sono figlie di una riga.
  const NestedHeading: "h4" | "h5" = Heading === "h4" ? "h5" : "h4";
  const columns = sectionColumns(section.assumptions, years);
  const anchor = `${idPrefix}-${section.key}`;
  const nested = section.assumptions.filter(hasNestedTable);

  return (
    <section id={anchor} aria-labelledby={`${anchor}-title`} className="print:break-inside-avoid">
      <Heading id={`${anchor}-title`} className="text-lg font-semibold">
        {section.title}
      </Heading>
      {section.missing ? (
        <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
          <CircleAlert className="mr-1 inline h-3 w-3" aria-hidden="true" />
          Sezione non portata dal payload: le sette sezioni sono il contratto, e questa si rende vuota
          invece di sparire.
        </p>
      ) : null}

      {section.assumptions.length === 0 ? (
        <Card className="mt-2">
          <CardContent className="py-3 text-sm text-muted-foreground">
            Nessuna ipotesi materializzata in questa sezione: il piano usa i valori derivati dal
            motore, nessun pilota dichiarato.
          </CardContent>
        </Card>
      ) : (
        <Table className="mt-2 print:text-[11px]">
          <TableCaption>
            {`${section.title}: valori per anno (${years.length > 0 ? years.join(", ") : "nessun anno di previsione"}). ` +
              "Ogni riga dichiara la propria origine."}
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Ipotesi</TableHead>
              {columns.map((column) => (
                <TableHead key={`${anchor}-${column.label}`} scope="col" className="text-right">
                  {column.label}
                  {column.extra ? <span className="sr-only"> colonna aggiunta: più valori che anni</span> : null}
                </TableHead>
              ))}
              <TableHead scope="col">Origine</TableHead>
              <TableHead scope="col">Stato</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {section.assumptions.map((assumption) => {
              const kind = scalarKindOf(assumption.field);
              const state = assumptionRowState(assumption);
              return (
                <TableRow key={`${anchor}-${assumption.field}`}>
                  <th scope="row" className={ROW_HEAD}>
                    {assumption.label}
                    <span className="block text-xs font-normal text-muted-foreground">
                      {assumption.field}
                    </span>
                  </th>
                  {rowCells(assumption.values, columns).map((value, index) => (
                    <ScalarCell key={`${anchor}-${assumption.field}-${index}`} value={value.value} kind={kind} />
                  ))}
                  <TableCell>
                    <ProvenanceBadge provenance={assumption.provenance} active={assumption.active} />
                  </TableCell>
                  <TableCell className={cn("text-xs", state?.level === "warning" && "text-amber-700 dark:text-amber-400")}>
                    {state ? (
                      <>
                        {state.level === "warning" && <CircleAlert className="mr-1 inline h-3 w-3" aria-hidden="true" />}
                        {state.text}
                      </>
                    ) : (
                      "In uso nel piano"
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      {nested.map((assumption) => (
        <AssumptionsNestedTables
          key={`${anchor}-nested-${assumption.field}`}
          assumption={assumption}
          years={years}
          Heading={NestedHeading}
        />
      ))}
    </section>
  );
}

/** Le sette sezioni del wizard, nell'ordine del catalogo, con le anomalie dichiarate. */
export function AssumptionsSections({
  model,
  id = "ipotesi-budget",
  headingLevel = 2,
  showLegend = true,
}: AssumptionsSectionsProps) {
  const verdict = readFinalReport(model, "Ipotesi del budget");
  if (!verdict.ok) return <AssumptionsSchemaNotice verdict={verdict} />;

  const { sections, unknown, missing, duplicates } = layoutSections(verdict.model.assumption_sections);
  const years = verdict.model.practice.periods.forecast_years;
  const BlockHeading = headingLevel === 3 ? "h3" : "h2";

  return (
    <section id={id} aria-labelledby={`${id}-title`} className="space-y-6">
      <div>
        <BlockHeading id={`${id}-title`} className={headingLevel === 3 ? "text-lg font-semibold" : "text-2xl font-bold"}>
          Ipotesi del budget
        </BlockHeading>
        <p className="mt-1 text-sm text-muted-foreground">
          Le {CANONICAL_SECTION_KEYS.length} sezioni del percorso ipotesi, nell&apos;ordine del catalogo,
          con l&apos;origine dichiarata per ogni valore.
        </p>
        {showLegend ? <ProvenanceLegend className="mt-3" /> : null}
      </div>

      {duplicates.length > 0 ? (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          <CircleAlert className="mr-1 inline h-3 w-3" aria-hidden="true" />
          Sezioni arrivate due volte nel payload ({duplicates.join(", ")}): le righe sono state
          accodate alla prima, nessun valore scartato.
        </p>
      ) : null}
      {missing.length > 0 ? (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          <CircleAlert className="mr-1 inline h-3 w-3" aria-hidden="true" />
          Sezioni canoniche non portate dal payload ({missing.join(", ")}).
        </p>
      ) : null}

      {sections.map((section) => (
        <AssumptionsSectionTable
          key={section.key}
          section={section}
          years={years}
          Heading={headingLevel === 3 ? "h4" : "h3"}
          idPrefix={id}
        />
      ))}

      {unknown.map((section) => (
        <section key={`unknown-${section.key}`} className="print:break-inside-avoid">
          <h3 className="text-lg font-semibold text-amber-800 dark:text-amber-300">
            Sezione non riconosciuta: {section.title || section.key}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Il catalogo delle {CANONICAL_SECTION_KEYS.length} sezioni non conosce la chiave &quot;
            {section.key}&quot;. Le righe si mostrano qui, fuori ordine, perché nasconderle varrebbe
            come un&apos;ipotesi che non esiste.
          </p>
          {section.assumptions.map((assumption) => (
            <p key={assumption.field} className="text-sm">
              <span className="font-medium">{assumption.label}</span>{" "}
              <span className="text-muted-foreground">({assumption.field})</span>{" "}
              <ProvenanceBadge provenance={assumption.provenance} active={assumption.active} />
            </p>
          ))}
        </section>
      ))}
    </section>
  );
}
