"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatCurrency } from "@/lib/formatters";
import { BALANCE_STATEMENT_ROWS } from "@/lib/ivcee-catalog";
import { IS_LABELS } from "./report-types";
import type { ScenarioAnalysis } from "@/types/api";

interface ReportAppendicesProps {
  data: ScenarioAnalysis;
  section?: "bs" | "is";
}

// Detailed IV-CEE (art. 2424) balance-sheet rows — same structure as the
// "Proiezioni patrimoniali" page (frontend/app/forecast/balance/page.tsx) so the
// final report shows the FULL detail (crediti tributari, imposte anticipate, debiti
// per tipo entro/oltre 12 mesi, riserve, ...) instead of the macro voci only.
const BS_DETAIL_ROWS = BALANCE_STATEMENT_ROWS;

const IS_REVENUE_KEYS = [
  "ce01_ricavi_vendite",
  "ce02_variazioni_rimanenze",
  "ce03_lavori_interni",
  "ce04_altri_ricavi",
];

const IS_COST_KEYS = [
  "ce05_materie_prime",
  "ce06_servizi",
  "ce07_godimento_beni",
  "ce08_costi_personale",
  "ce09_ammortamenti",
  "ce10_var_rimanenze_mat_prime",
  "ce11_accantonamenti",
  "ce12_oneri_diversi",
];

const IS_FINANCIAL_KEYS = [
  "ce13_proventi_partecipazioni",
  "ce14_altri_proventi_finanziari",
  "ce15_oneri_finanziari",
  "ce16_utili_perdite_cambi",
  "ce17_rettifiche_attivita_fin",
];

const IS_OTHER_KEYS = [
  "ce18_proventi_straordinari",
  "ce19_oneri_straordinari",
  "ce20_imposte",
];

export function ReportAppendices({ data, section }: ReportAppendicesProps) {
  const allYears = [...data.historical_years, ...data.forecast_years].sort(
    (a, b) => a.year - b.year
  );

  const showBS = !section || section === "bs";
  const showIS = !section || section === "is";

  return (
    <section id={section ? `appendices-${section}` : "appendices"}>
      <div className="space-y-6">
        {/* Balance Sheet */}
        {showBS && <Card>
          <CardHeader>
            <CardTitle className="text-lg">Stato Patrimoniale</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table className="print:text-[11px] print-compact-table">
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-[250px] print:min-w-0">Voce</TableHead>
                    {allYears.map((y) => (
                      <TableHead key={y.year} className="text-right min-w-[110px] print:min-w-0 print:px-1">
                        {y.year}
                        {y.type === "forecast" && (
                          <span className="text-xs text-muted-foreground ml-1">(P)</span>
                        )}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {BS_DETAIL_ROWS.filter((row) => {
                    // Hide indented DETAIL sub-rows when no historical year populates
                    // them — avoids showing mechanical forecast-only breakdowns when the
                    // imported data (abbreviato) only carried aggregate totals. Mirrors
                    // the "Proiezioni patrimoniali" page behaviour.
                    if (!row.field || !row.label.startsWith("  ")) return true;
                    return data.historical_years.some(
                      (y) => Math.abs((y.balance_sheet[row.field!] as number) || 0) >= 0.5
                    );
                  }).map((row, idx) => {
                    const rowClass = row.isTotal
                      ? "bg-muted/50 border-t-2 font-bold"
                      : row.isSubtotal
                      ? "border-t font-semibold"
                      : "";
                    const indented = row.label.startsWith("  ");
                    return (
                      <TableRow key={`${row.label}-${idx}`} className={rowClass}>
                        <TableCell className={indented ? "pl-8 text-muted-foreground" : undefined}>
                          {row.label.trim()}
                        </TableCell>
                        {allYears.map((y) => {
                          const bs = y.balance_sheet as Record<string, number>;
                          const val = row.computed
                            ? row.computed(bs)
                            : row.field
                            ? bs[row.field] || 0
                            : null;
                          return (
                            <TableCell key={y.year} className="text-right">
                              {val === null ? "" : formatCurrency(val)}
                            </TableCell>
                          );
                        })}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>}

        {/* Income Statement */}
        {showIS && <Card>
          <CardHeader>
            <CardTitle className="text-lg">Conto Economico</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table className="print:text-[11px] print-compact-table">
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-[250px] print:min-w-0">Voce</TableHead>
                    {allYears.map((y) => (
                      <TableHead key={y.year} className="text-right min-w-[110px] print:min-w-0 print:px-1">
                        {y.year}
                        {y.type === "forecast" && (
                          <span className="text-xs text-muted-foreground ml-1">(P)</span>
                        )}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {/* Revenue section */}
                  <TableRow className="bg-muted/50">
                    <TableCell className="font-bold" colSpan={allYears.length + 1}>
                      A) VALORE DELLA PRODUZIONE
                    </TableCell>
                  </TableRow>
                  {IS_REVENUE_KEYS.map((key) => (
                    <TableRow key={key}>
                      <TableCell>{IS_LABELS[key] || key}</TableCell>
                      {allYears.map((y) => (
                        <TableCell key={y.year} className="text-right">
                          {formatCurrency(y.income_statement[key] || 0)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                  <TableRow className="border-t font-semibold">
                    <TableCell>Totale Valore Produzione</TableCell>
                    {allYears.map((y) => (
                      <TableCell key={y.year} className="text-right">
                        {formatCurrency(y.income_statement.production_value || 0)}
                      </TableCell>
                    ))}
                  </TableRow>

                  {/* Cost section */}
                  <TableRow className="bg-muted/50">
                    <TableCell className="font-bold" colSpan={allYears.length + 1}>
                      B) COSTI DELLA PRODUZIONE
                    </TableCell>
                  </TableRow>
                  {IS_COST_KEYS.map((key) => (
                    <TableRow key={key}>
                      <TableCell>{IS_LABELS[key] || key}</TableCell>
                      {allYears.map((y) => (
                        <TableCell key={y.year} className="text-right">
                          {formatCurrency(y.income_statement[key] || 0)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}

                  {/* EBITDA */}
                  <TableRow className="border-t font-semibold">
                    <TableCell>EBITDA (MOL)</TableCell>
                    {allYears.map((y) => (
                      <TableCell key={y.year} className="text-right">
                        {formatCurrency(y.income_statement.ebitda || 0)}
                      </TableCell>
                    ))}
                  </TableRow>

                  {/* EBIT */}
                  <TableRow className="font-semibold">
                    <TableCell>EBIT (Risultato Operativo)</TableCell>
                    {allYears.map((y) => (
                      <TableCell key={y.year} className="text-right">
                        {formatCurrency(y.income_statement.ebit || 0)}
                      </TableCell>
                    ))}
                  </TableRow>

                  {/* Financial section */}
                  <TableRow className="bg-muted/50">
                    <TableCell className="font-bold" colSpan={allYears.length + 1}>
                      C) PROVENTI E ONERI FINANZIARI
                    </TableCell>
                  </TableRow>
                  {IS_FINANCIAL_KEYS.map((key) => (
                    <TableRow key={key}>
                      <TableCell>{IS_LABELS[key] || key}</TableCell>
                      {allYears.map((y) => (
                        <TableCell key={y.year} className="text-right">
                          {formatCurrency(y.income_statement[key] || 0)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}

                  {/* Other */}
                  <TableRow className="bg-muted/50">
                    <TableCell className="font-bold" colSpan={allYears.length + 1}>
                      D/E) STRAORDINARI E IMPOSTE
                    </TableCell>
                  </TableRow>
                  {IS_OTHER_KEYS.map((key) => (
                    <TableRow key={key}>
                      <TableCell>{IS_LABELS[key] || key}</TableCell>
                      {allYears.map((y) => (
                        <TableCell key={y.year} className="text-right">
                          {formatCurrency(y.income_statement[key] || 0)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}

                  {/* Net profit */}
                  <TableRow className="border-t-2 font-bold">
                    <TableCell>UTILE (PERDITA) D&apos;ESERCIZIO</TableCell>
                    {allYears.map((y) => (
                      <TableCell key={y.year} className="text-right">
                        {formatCurrency(y.income_statement.net_profit || 0)}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>}
      </div>
    </section>
  );
}
