/**
 * Le tabelle nidificate delle ipotesi (M1-08B): prestiti, piano del pregresso,
 * differenze temporanee, override di conto economico e di stato patrimoniale,
 * indicizzazione.
 *
 * §6.4 le vuole «tabelle nidificate, non campi serializzati in testo»: il
 * rendering passa di qui, e `JSON.stringify` non è mai una cella.
 *
 * Le decisioni stanno nel modello di vista (`*ViewModel`, funzioni pure), non
 * nel JSX: i componenti distribuiscono celle già decise e non calcolano nulla.
 * Non c'è un `number` in giro per gli importi — viaggiano come `DecimalString`
 * e si formattano da stringa (`AssumptionsFormat`).
 */
import * as React from "react";
import { CircleAlert } from "lucide-react";

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
import { nestedTablesOf, type NestedTable } from "./AssumptionsCatalog";
import {
  describeScalar,
  ROW_HEAD,
  indexingDriverLabel,
  overrideFieldLabel,
  PREGRESSO_BALANCES,
  temporaryDifferenceKind,
  temporaryDifferenceMaturity,
  yearsText,
  type ScalarKind,
} from "./AssumptionsFormat";
import type { AssumptionValue, DecimalString, RunoffPlan, TaxRunoffPlan } from "@/types/final-report";

export interface Cell {
  text: string;
  /** Testo per gli screen reader: nomina l'assenza o l'unità dove il testo è un trattino. */
  srText?: string;
  /** Intestazione di riga (`<th scope="row">`). */
  header?: boolean;
  /** `null` dichiarato: il trattino non è uno zero. */
  absent?: boolean;
  /** Valore negativo: il segno resta nel testo, non passa dal colore. */
  negative?: boolean;
  /** Il testo non è un decimale riconosciuto: si mostra com'è, con un avviso. */
  malformed?: boolean;
}

export interface NestedTableViewModel {
  id: NestedTable["kind"];
  title: string;
  caption: string;
  columns: string[];
  rows: Cell[][];
  /** Che la tabella non ha righe, detto a parole: un `<tbody>` vuoto non è un «nessun dato». */
  note?: string;
}

function cell(value: DecimalString | null, kind: ScalarKind = "eur"): Cell {
  const view = describeScalar(value, kind);
  return {
    text: view.text,
    srText: view.srText,
    absent: view.absent,
    negative: view.negative,
    malformed: view.malformed,
  };
}

const label = (text: string): Cell => ({ text, header: true });

/**
 * Quante colonne d'anno servono davvero: gli anni del piano e, se un piano ne
 * porta di più, anche quelle in più. Il numero guida l'intestazione, quindi le
 * righe non possono mai eccedere le colonne.
 */
function amountColumnCount(years: readonly number[], plans: readonly RunoffPlan[]): number {
  const declared = plans.reduce(
    (max, plan) => Math.max(max, plan.amounts.length, plan.writeoff?.length ?? 0),
    0,
  );
  return Math.max(years.length, declared, 1);
}

function yearColumns(count: number, years: readonly number[]): string[] {
  return Array.from({ length: count }, (_, index) =>
    index < years.length ? String(years[index]) : `Quota ${index + 1} (anno non dichiarato)`,
  );
}

/** Allinea una sequenza di importi alle colonne, senza perderne nessuno. */
function alignAmounts(amounts: readonly DecimalString[], columns: number): Cell[] {
  return Array.from({ length: columns }, (_, index) => (index < amounts.length ? cell(amounts[index]) : cell(null)));
}

/** Prestiti: una riga per contratto. Un prestito senza nome diventa «Prestito n»,
 *  non una riga sparita: senza nome resta un finanziamento. */
export function financingLoansViewModel(
  loans: NonNullable<AssumptionValue["financing_loans"]>,
): NestedTableViewModel {
  return {
    id: "financing_loans",
    title: "Finanziamenti e prestiti",
    caption: `Finanziamenti e prestiti del piano: ${loans.length} ${loans.length === 1 ? "contratto" : "contratti"}`,
    columns: ["Prestito", "Importo", "Residuo ad apertura", "Durata", "Tasso", "Preammortamento", "Quota finale"],
    rows: loans.map((loan, index) => [
      label(loan.name && loan.name.trim() !== "" ? loan.name : `Prestito ${index + 1} (senza nome)`),
      cell(loan.amount),
      cell(loan.opening_residual),
      { text: loan.duration_years == null ? "durata non dichiarata" : yearsText(loan.duration_years) },
      cell(loan.interest_rate, "pct"),
      { text: loan.grace_years === 0 ? "nessun preammortamento" : yearsText(loan.grace_years) },
      cell(loan.balloon_pct, "pct"),
    ]),
    note: loans.length === 0 ? "Nessun prestito nel piano: nessun finanziamento nuovo previsto." : undefined,
  };
}

export function financingRepaymentsViewModel(
  loans: NonNullable<AssumptionValue["financing_loans"]>,
  years: readonly number[],
): NestedTableViewModel {
  return {
    id: "financing_repayments",
    title: "Rimborsi dei finanziamenti",
    caption: "Rimborsi dichiarati per anno dei finanziamenti",
    columns: ["Prestito", "Anno", "Rimborso"],
    rows: loans.flatMap((loan, loanIndex) => (loan.repayments ?? []).map((amount, index) => [
      label(loan.name && loan.name.trim() !== "" ? loan.name : `Prestito ${loanIndex + 1} (senza nome)`),
      { text: years[index] == null ? `Quota ${index + 1} (anno non dichiarato)` : String(years[index]) },
      cell(amount),
    ])),
  };
}

export function otherLendersViewModel(
  lenders: NonNullable<AssumptionValue["other_lenders"]>,
): NestedTableViewModel {
  return {
    id: "other_lenders",
    title: "Altri finanziatori",
    caption: `Altri finanziatori del piano: ${lenders.length}`,
    columns: ["Finanziatore", "Residuo ad apertura", "Tasso"],
    rows: lenders.map((lender, index) => [
      label(lender.name && lender.name.trim() !== "" ? lender.name : `Finanziatore ${index + 1} (senza nome)`),
      cell(lender.opening_residual),
      cell(lender.interest_rate, "pct"),
    ]),
    note: lenders.length === 0 ? "Nessun altro finanziatore dichiarato." : undefined,
  };
}

export function otherLenderRepaymentsViewModel(
  lenders: NonNullable<AssumptionValue["other_lenders"]>,
  years: readonly number[],
): NestedTableViewModel {
  return {
    id: "other_lender_repayments",
    title: "Rimborsi agli altri finanziatori",
    caption: "Rimborsi dichiarati per anno agli altri finanziatori",
    columns: ["Finanziatore", "Anno", "Rimborso"],
    rows: lenders.flatMap((lender, lenderIndex) => lender.repayments.map((amount, index) => [
      label(lender.name && lender.name.trim() !== "" ? lender.name : `Finanziatore ${lenderIndex + 1} (senza nome)`),
      { text: years[index] == null ? `Quota ${index + 1} (anno non dichiarato)` : String(years[index]) },
      cell(amount),
    ])),
  };
}

/**
 * Pregresso: le cinque posizioni, ognuna dichiarata anche quando non ha un piano.
 *
 * Una posizione senza piano rende una riga «nessun piano»: saltarla farebbe
 * contare quattro posizioni su cinque, e il lettore non ha modo di accorgersi
 * che la quinta esiste e non è stata letta.
 */
export function pregressoViewModel(
  pregresso: NonNullable<AssumptionValue["pregresso"]>,
  years: readonly number[],
): NestedTableViewModel {
  const plans = PREGRESSO_BALANCES.map((balance) => pregresso[balance.key] as RunoffPlan | null | undefined).filter(
    (plan): plan is RunoffPlan => plan !== null && plan !== undefined,
  );
  const columns = amountColumnCount(years, plans);
  const rows: Cell[][] = [];
  for (const balance of PREGRESSO_BALANCES) {
    const plan = pregresso[balance.key] as RunoffPlan | null | undefined;
    if (plan === null || plan === undefined) {
      rows.push([
        label(balance.label),
        { text: "nessun piano", srText: `Nessun piano di rientro per ${balance.label.toLowerCase()}` },
        ...Array.from({ length: columns }, () => cell(null)),
      ]);
      continue;
    }
    rows.push([label(balance.label), cell(plan.opening), ...alignAmounts(plan.amounts, columns)]);
    if (plan.non_incassato != null) {
      rows.push([
        label(`${balance.label} — non incassato`),
        { text: plan.non_incassato ? "sì" : "no" },
        ...Array.from({ length: columns }, () => cell(null)),
      ]);
    }
    if (plan.writeoff !== null && plan.writeoff !== undefined) {
      rows.push([
        label(`${balance.label} — stralcio`),
        cell(null),
        ...alignAmounts(plan.writeoff, columns),
      ]);
    }
  }
  const planned = plans.length;
  return {
    id: "pregresso",
    title: "Piano del pregresso",
    caption: `Piano del pregresso: quote riscosse o pagate per anno (${planned} ${planned === 1 ? "posizione pianificata" : "posizioni pianificate"} su ${PREGRESSO_BALANCES.length})`,
    columns: ["Posizione", "Apertura", ...yearColumns(columns, years)],
    rows,
    note: planned === 0 ? "Nessuna posizione del pregresso ha un piano di rientro." : undefined,
  };
}

/** Le tre cifre del rateizzato tributario, quando il pregresso le dichiara. */
export function taxPlanViewModel(tributari: TaxRunoffPlan): NestedTableViewModel {
  return {
    id: "pregresso",
    title: "Debiti tributari: saldo, rateizzato, acconto",
    caption: "Debiti tributari: saldo dovuto nell'anno, rateizzato ancora aperto, percentuale di acconto",
    columns: ["Voce", "Valore"],
    rows: [
      [label("Saldo dovuto"), cell(tributari.saldo)],
      [label("Rateizzato"), cell(tributari.rateizzato)],
      [label("Acconto"), cell(tributari.acconto_pct, "pct")],
    ],
  };
}

/** Differenze temporanee (imposte anticipate e differite). */
export function temporaryDifferencesViewModel(
  differences: NonNullable<AssumptionValue["temporary_differences"]>,
): NestedTableViewModel {
  return {
    id: "temporary_differences",
    title: "Differenze temporanee",
    caption: `Differenze temporanee su basi diverse: ${differences.length} ${differences.length === 1 ? "voce" : "voci"}`,
    columns: ["Voce", "Natura", "Scadenza", "Residuo iniziale", "Incrementi", "Smobilizzi", "Aliquota"],
    rows: differences.map((difference) => [
      label(difference.name),
      { text: temporaryDifferenceKind(difference.kind) },
      { text: temporaryDifferenceMaturity(difference.maturity) },
      cell(difference.opening_amount),
      cell(difference.additions),
      cell(difference.reversals),
      cell(difference.tax_rate ?? null, "pct"),
    ]),
    note: differences.length === 0 ? "Nessuna differenza temporanea dichiarata." : undefined,
  };
}

/** Override di conto economico: il codice della colonna resta in una colonna sua. */
export function ceOverridesViewModel(rows: NonNullable<AssumptionValue["ce_overrides"]>): NestedTableViewModel {
  return {
    id: "ce_overrides",
    title: "Override del conto economico",
    caption: `Voci di conto economico forzate a valore assoluto: ${rows.length}`,
    columns: ["Voce", "Campo", "Valore forzato"],
    rows: rows.map((row) => [label(overrideFieldLabel(row.field)), { text: row.field }, cell(row.value)]),
    note: rows.length === 0 ? "Nessun override di conto economico." : undefined,
  };
}

/** Override di stato patrimoniale (il sacco `sp_overrides`). */
export function spOverridesViewModel(rows: NonNullable<AssumptionValue["sp_overrides"]>): NestedTableViewModel {
  return {
    id: "sp_overrides",
    title: "Override dello stato patrimoniale",
    caption: `Voci di stato patrimoniale forzate a valore assoluto: ${rows.length}`,
    columns: ["Voce", "Campo", "Valore forzato"],
    rows: rows.map((row) => [label(overrideFieldLabel(row.field)), { text: row.field }, cell(row.value)]),
    note: rows.length === 0 ? "Nessun override di stato patrimoniale." : undefined,
  };
}

/** Indicizzazione di una voce patrimoniale a un pilota di conto economico. */
export function spIndexingViewModel(rows: NonNullable<AssumptionValue["sp_indexing"]>): NestedTableViewModel {
  return {
    id: "sp_indexing",
    title: "Indicizzazione delle voci patrimoniali",
    caption: `Voci patrimoniali indicizzate a un pilota di conto economico: ${rows.length}`,
    columns: ["Voce", "Campo", "Guidato da"],
    rows: rows.map((row) => [
      label(overrideFieldLabel(row.field)),
      { text: row.field },
      { text: indexingDriverLabel(row.driver) },
    ]),
    note: rows.length === 0 ? "Nessuna voce patrimoniale indicizzata." : undefined,
  };
}

/** Il modello di vista di una tabella nidificata. */
export function nestedTableViewModel(table: NestedTable, years: readonly number[]): NestedTableViewModel {
  switch (table.kind) {
    case "financing_loans":
      return financingLoansViewModel(table.rows);
    case "financing_repayments":
      return financingRepaymentsViewModel(table.rows, years);
    case "pregresso":
      return pregressoViewModel(table.plan, years);
    case "temporary_differences":
      return temporaryDifferencesViewModel(table.rows);
    case "ce_overrides":
      return ceOverridesViewModel(table.rows);
    case "sp_overrides":
      return spOverridesViewModel(table.rows);
    case "sp_indexing":
      return spIndexingViewModel(table.rows);
    case "other_lenders":
      return otherLendersViewModel(table.rows);
    case "other_lender_repayments":
      return otherLenderRepaymentsViewModel(table.rows, years);
  }
}

function NestedTableCard({
  model,
  owner,
  Heading,
}: {
  model: NestedTableViewModel;
  owner: string;
  Heading: "h4" | "h5";
}) {
  return (
    <Card className="print:break-inside-avoid">
      <CardHeader className="pb-2">
        <Heading className="text-base font-semibold">
          {model.title}
          <span className="block text-xs font-normal text-muted-foreground">Ipotesi: {owner}</span>
        </Heading>
      </CardHeader>
      <CardContent>
        <Table className="print:text-[11px]">
          <TableCaption>{model.caption}</TableCaption>
          <TableHeader>
            <TableRow>
              {model.columns.map((column) => (
                <TableHead key={`${model.id}-${column}`}>{column}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {model.rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={model.columns.length} className="text-muted-foreground">
                  {model.note ?? "Nessun dato da mostrare."}
                </TableCell>
              </TableRow>
            ) : (
              model.rows.map((row, rowIndex) => (
                <TableRow key={`${model.id}-${rowIndex}`}>
                  {row.map((item, columnIndex) =>
                    item.header ? (
                      <th key={columnIndex} scope="row" className={ROW_HEAD}>
                        {item.text}
                      </th>
                    ) : (
                      <TableCell key={columnIndex} className={cn("tabular-nums", item.negative && "font-medium")}>
                        {item.text}
                        {item.absent ? <span className="sr-only">{item.srText ?? "nessun valore"}</span> : null}
                        {item.negative ? <span className="sr-only"> negativo</span> : null}
                        {item.malformed ? (
                          <span className="ml-1 inline-flex items-center gap-1 text-xs text-destructive">
                            <CircleAlert className="h-3 w-3" aria-hidden="true" />
                            valore non riconosciuto
                          </span>
                        ) : null}
                      </TableCell>
                    ),
                  )}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        {model.rows.length > 0 && model.note ? (
          <p className="mt-2 text-xs text-muted-foreground">{model.note}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

/**
 * Le tabelle nidificate di una riga di ipotesi, in ordine canonico.
 *
 * Il `pregresso` dei debiti tributari vale due tabelle: il piano per anno e le
 * sue tre cifre (saldo, rateizzato, acconto), che nominate in una colonna a parte
 * non si appoggiano a un'intestazione che vuol dire altro.
 */
export function AssumptionsNestedTables({
  assumption,
  years,
  Heading = "h4",
}: {
  assumption: AssumptionValue;
  years: readonly number[];
  /** Il livello dei titoli delle tabelle nidificate, un passo sotto quello della sezione. */
  Heading?: "h4" | "h5";
}) {
  const tables = nestedTablesOf(assumption);
  if (tables.length === 0) return null;

  return (
    <div className="mt-3 space-y-3">
      {tables.map((table, index) => (
        <React.Fragment key={`${table.kind}-${index}`}>
          <NestedTableCard model={nestedTableViewModel(table, years)} owner={assumption.label} Heading={Heading} />
          {table.kind === "pregresso" && table.plan.debiti_tributari ? (
            <NestedTableCard
              model={taxPlanViewModel(table.plan.debiti_tributari)}
              owner={assumption.label}
              Heading={Heading}
            />
          ) : null}
        </React.Fragment>
      ))}
    </div>
  );
}

/** Una cella di valore scalare, con le sue verità in testo: assente, zero, negativo. */
export function ScalarCell({ value, kind }: { value: DecimalString | boolean | null; kind: ScalarKind }) {
  const view = describeScalar(value, kind);
  return (
    <TableCell className={cn("tabular-nums", view.negative && "font-medium")}>
      {view.text}
      {view.absent ? <span className="sr-only">{view.srText}</span> : null}
      {view.negative ? <span className="sr-only"> negativo</span> : null}
      {view.malformed ? (
        <span className="ml-1 inline-flex items-center gap-1 text-xs text-destructive">
          <CircleAlert className="h-3 w-3" aria-hidden="true" />
          valore non riconosciuto
        </span>
      ) : null}
    </TableCell>
  );
}
