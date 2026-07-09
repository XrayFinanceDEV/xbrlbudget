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
type BSDetailRow = {
  label: string;
  field?: string;
  computed?: (bs: Record<string, number>) => number;
  isTotal?: boolean;
  isSubtotal?: boolean;
};

const n = (bs: Record<string, number>, f: string): number => (bs[f] as number) || 0;

const BS_DETAIL_ROWS: BSDetailRow[] = [
  { label: "ATTIVO", isTotal: true },
  { label: "A) Crediti verso soci per versamenti ancora dovuti", field: "sp01_crediti_soci" },
  { label: "B) IMMOBILIZZAZIONI", isSubtotal: true },
  { label: "I - Immobilizzazioni immateriali", field: "sp02_immob_immateriali" },
  { label: "II - Immobilizzazioni materiali", field: "sp03_immob_materiali" },
  { label: "III - Immobilizzazioni finanziarie", field: "sp04_immob_finanziarie" },
  { label: "  1) Partecipazioni", field: "sp04a_partecipazioni" },
  { label: "  2) Crediti (entro esercizio)", field: "sp04b_crediti_immob_breve" },
  { label: "  2) Crediti (oltre esercizio)", field: "sp04c_crediti_immob_lungo" },
  { label: "  3) Altri titoli", field: "sp04d_altri_titoli" },
  { label: "  4) Strumenti finanziari derivati attivi", field: "sp04e_strumenti_derivati_attivi" },
  { label: "Totale Immobilizzazioni", field: "fixed_assets", isSubtotal: true },
  { label: "C) ATTIVO CIRCOLANTE", isSubtotal: true },
  { label: "I - Rimanenze", field: "sp05_rimanenze" },
  { label: "II - Crediti (entro esercizio successivo)", field: "sp06_crediti_breve" },
  { label: "  1) Verso clienti", field: "sp06a_crediti_clienti_breve" },
  { label: "  2) Verso imprese controllate", field: "sp06b_crediti_controllate_breve" },
  { label: "  3) Verso imprese collegate", field: "sp06c_crediti_collegate_breve" },
  { label: "  4) Verso controllanti", field: "sp06d_crediti_controllanti_breve" },
  { label: "  5-bis) Crediti tributari", field: "sp06e_crediti_tributari_breve" },
  { label: "  5-ter) Imposte anticipate", field: "sp06f_imposte_anticipate_breve" },
  { label: "  5-quater) Verso altri", field: "sp06g_crediti_altri_breve" },
  { label: "II - Crediti (oltre esercizio successivo)", field: "sp07_crediti_lungo" },
  { label: "  1) Verso clienti", field: "sp07a_crediti_clienti_lungo" },
  { label: "  5-bis) Crediti tributari", field: "sp07e_crediti_tributari_lungo" },
  { label: "  5-ter) Imposte anticipate", field: "sp07f_imposte_anticipate_lungo" },
  { label: "  5-quater) Verso altri", field: "sp07g_crediti_altri_lungo" },
  { label: "III - Attività finanziarie non immobilizzate", field: "sp08_attivita_finanziarie" },
  { label: "IV - Disponibilità liquide", field: "sp09_disponibilita_liquide" },
  { label: "Totale Attivo Circolante", field: "current_assets", isSubtotal: true },
  { label: "D) Ratei e risconti attivi", field: "sp10_ratei_risconti_attivi" },
  { label: "TOTALE ATTIVO", field: "total_assets", isTotal: true },
  { label: "PASSIVO E PATRIMONIO NETTO", isTotal: true },
  { label: "A) PATRIMONIO NETTO", isSubtotal: true },
  { label: "I - Capitale", field: "sp11_capitale" },
  { label: "II - Riserva da soprapprezzo delle azioni", field: "sp12a_riserva_sovrapprezzo" },
  { label: "III - Riserve di rivalutazione", field: "sp12b_riserve_rivalutazione" },
  { label: "IV - Riserva legale", field: "sp12c_riserva_legale" },
  { label: "V - Riserve statutarie", field: "sp12d_riserve_statutarie" },
  { label: "VI - Altre riserve", field: "sp12e_altre_riserve" },
  { label: "VII - Riserva copertura flussi finanziari attesi", field: "sp12f_riserva_copertura_flussi" },
  { label: "VIII - Utili (perdite) portati a nuovo", field: "sp12g_utili_perdite_portati" },
  { label: "IX - Utile (perdita) dell'esercizio", field: "sp13_utile_perdita" },
  { label: "X - Riserva negativa per azioni proprie", field: "sp12h_riserva_neg_azioni_proprie" },
  { label: "Totale Patrimonio Netto", field: "total_equity", isSubtotal: true },
  { label: "B) Fondi per rischi e oneri", field: "sp14_fondi_rischi" },
  { label: "C) Trattamento di fine rapporto", field: "sp15_tfr" },
  { label: "D) DEBITI", isSubtotal: true },
  { label: "1) Debiti verso banche", computed: (bs) => n(bs, "sp16a_debiti_banche_breve") + n(bs, "sp17a_debiti_banche_lungo") },
  { label: "  entro 12 mesi", field: "sp16a_debiti_banche_breve" },
  { label: "  oltre 12 mesi", field: "sp17a_debiti_banche_lungo" },
  { label: "2) Debiti verso altri finanziatori", computed: (bs) => n(bs, "sp16b_debiti_altri_finanz_breve") + n(bs, "sp17b_debiti_altri_finanz_lungo") },
  { label: "  entro 12 mesi", field: "sp16b_debiti_altri_finanz_breve" },
  { label: "  oltre 12 mesi", field: "sp17b_debiti_altri_finanz_lungo" },
  { label: "3) Debiti obbligazionari", computed: (bs) => n(bs, "sp16c_debiti_obbligazioni_breve") + n(bs, "sp17c_debiti_obbligazioni_lungo") },
  { label: "  entro 12 mesi", field: "sp16c_debiti_obbligazioni_breve" },
  { label: "  oltre 12 mesi", field: "sp17c_debiti_obbligazioni_lungo" },
  { label: "7) Debiti verso fornitori", computed: (bs) => n(bs, "sp16d_debiti_fornitori_breve") + n(bs, "sp17d_debiti_fornitori_lungo") },
  { label: "  entro 12 mesi", field: "sp16d_debiti_fornitori_breve" },
  { label: "  oltre 12 mesi", field: "sp17d_debiti_fornitori_lungo" },
  { label: "12) Debiti tributari", computed: (bs) => n(bs, "sp16e_debiti_tributari_breve") + n(bs, "sp17e_debiti_tributari_lungo") },
  { label: "  entro 12 mesi", field: "sp16e_debiti_tributari_breve" },
  { label: "  oltre 12 mesi", field: "sp17e_debiti_tributari_lungo" },
  { label: "13) Debiti previdenziali", computed: (bs) => n(bs, "sp16f_debiti_previdenza_breve") + n(bs, "sp17f_debiti_previdenza_lungo") },
  { label: "  entro 12 mesi", field: "sp16f_debiti_previdenza_breve" },
  { label: "  oltre 12 mesi", field: "sp17f_debiti_previdenza_lungo" },
  { label: "14) Altri debiti", computed: (bs) => n(bs, "sp16g_altri_debiti_breve") + n(bs, "sp17g_altri_debiti_lungo") },
  { label: "  entro 12 mesi", field: "sp16g_altri_debiti_breve" },
  { label: "  oltre 12 mesi", field: "sp17g_altri_debiti_lungo" },
  { label: "Totale Debiti", field: "total_debt", isSubtotal: true },
  { label: "E) Ratei e risconti passivi", field: "sp18_ratei_risconti_passivi" },
  {
    label: "TOTALE PASSIVO E PATRIMONIO NETTO",
    computed: (bs) => n(bs, "total_equity") + n(bs, "total_debt") + n(bs, "sp14_fondi_rischi") + n(bs, "sp15_tfr") + n(bs, "sp18_ratei_risconti_passivi"),
    isTotal: true,
  },
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
