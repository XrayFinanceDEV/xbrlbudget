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
import { BS_LABELS, IS_LABELS } from "./report-types";
import type { ScenarioAnalysis, ScenarioAnalysisYearData } from "@/types/api";

interface ReportAppendicesProps {
  data: ScenarioAnalysis;
}

const BS_KEYS = [
  "sp01_crediti_soci",
  "sp02_immob_immateriali",
  "sp03_immob_materiali",
  "sp04_immob_finanziarie",
  "sp05_rimanenze",
  "sp06_crediti_breve",
  "sp07_crediti_lungo",
  "sp08_attivita_finanziarie",
  "sp09_disponibilita_liquide",
  "sp10_ratei_risconti_attivi",
];

const BS_EQUITY_KEYS = [
  "sp11_capitale",
  "sp12_riserve",
  "sp13_utile_perdita",
];

const BS_LIABILITY_KEYS = [
  "sp14_fondi_rischi",
  "sp15_tfr",
  "sp16_debiti_breve",
  "sp17_debiti_lungo",
  "sp18_ratei_risconti_passivi",
];

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

function getValue(yearData: ScenarioAnalysisYearData, key: string): number {
  return (yearData.balance_sheet[key] ?? yearData.income_statement[key] ?? 0) as number;
}

export function ReportAppendices({ data }: ReportAppendicesProps) {
  const allYears = [...data.historical_years, ...data.forecast_years].sort(
    (a, b) => a.year - b.year
  );

  return (
    <section id="appendices">
      <div className="space-y-6">
        {/* Balance Sheet */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Stato Patrimoniale</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-[250px]">Voce</TableHead>
                    {allYears.map((y) => (
                      <TableHead key={y.year} className="text-right min-w-[110px]">
                        {y.year}
                        {y.type === "forecast" && (
                          <span className="text-xs text-muted-foreground ml-1">(P)</span>
                        )}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {/* Assets header */}
                  <TableRow className="bg-muted/50">
                    <TableCell className="font-bold" colSpan={allYears.length + 1}>
                      ATTIVO
                    </TableCell>
                  </TableRow>
                  {BS_KEYS.map((key) => (
                    <TableRow key={key}>
                      <TableCell>{BS_LABELS[key] || key}</TableCell>
                      {allYears.map((y) => (
                        <TableCell key={y.year} className="text-right">
                          {formatCurrency(y.balance_sheet[key] || 0)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                  <TableRow className="border-t-2 font-bold">
                    <TableCell>TOTALE ATTIVO</TableCell>
                    {allYears.map((y) => (
                      <TableCell key={y.year} className="text-right">
                        {formatCurrency(y.balance_sheet.total_assets || 0)}
                      </TableCell>
                    ))}
                  </TableRow>

                  {/* Equity header */}
                  <TableRow className="bg-muted/50">
                    <TableCell className="font-bold" colSpan={allYears.length + 1}>
                      PATRIMONIO NETTO
                    </TableCell>
                  </TableRow>
                  {BS_EQUITY_KEYS.map((key) => (
                    <TableRow key={key}>
                      <TableCell>{BS_LABELS[key] || key}</TableCell>
                      {allYears.map((y) => (
                        <TableCell key={y.year} className="text-right">
                          {formatCurrency(y.balance_sheet[key] || 0)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                  <TableRow className="border-t font-semibold">
                    <TableCell>Totale Patrimonio Netto</TableCell>
                    {allYears.map((y) => (
                      <TableCell key={y.year} className="text-right">
                        {formatCurrency(y.balance_sheet.total_equity || 0)}
                      </TableCell>
                    ))}
                  </TableRow>

                  {/* Liabilities header */}
                  <TableRow className="bg-muted/50">
                    <TableCell className="font-bold" colSpan={allYears.length + 1}>
                      PASSIVO
                    </TableCell>
                  </TableRow>
                  {BS_LIABILITY_KEYS.map((key) => (
                    <TableRow key={key}>
                      <TableCell>{BS_LABELS[key] || key}</TableCell>
                      {allYears.map((y) => (
                        <TableCell key={y.year} className="text-right">
                          {formatCurrency(y.balance_sheet[key] || 0)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                  <TableRow className="border-t-2 font-bold">
                    <TableCell>TOTALE PASSIVO E NETTO</TableCell>
                    {allYears.map((y) => {
                      const total = (y.balance_sheet.total_equity || 0) +
                        (y.balance_sheet.sp14_fondi_rischi || 0) +
                        (y.balance_sheet.sp15_tfr || 0) +
                        (y.balance_sheet.sp16_debiti_breve || 0) +
                        (y.balance_sheet.sp17_debiti_lungo || 0) +
                        (y.balance_sheet.sp18_ratei_risconti_passivi || 0);
                      return (
                        <TableCell key={y.year} className="text-right">
                          {formatCurrency(total)}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>

        {/* Income Statement */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Conto Economico</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-[250px]">Voce</TableHead>
                    {allYears.map((y) => (
                      <TableHead key={y.year} className="text-right min-w-[110px]">
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
        </Card>
      </div>
    </section>
  );
}
