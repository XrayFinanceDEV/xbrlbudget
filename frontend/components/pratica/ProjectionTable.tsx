"use client";

import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  formatEuro,
  formatPct,
  formatInputNumber,
  parseInputNumber,
} from "@/lib/pratica-format";
import { ALWAYS_SHOW_CODES, DETAIL_PARENTS, EDITABLE_CE_CODES, VP_CODES } from "@/lib/pratica-codes";
import type { IntraYearComparisonItem } from "@/types/api";

// Projection Table Component (same layout as ComparisonTable but with editable Proiezione)
export function ProjectionTable({
  items,
  periodMonths,
  referenceYear,
  partialYear,
  showRevenuePct = false,
  overrides,
  onOverrideChange,
}: {
  items: IntraYearComparisonItem[];
  periodMonths: number;
  referenceYear: number;
  partialYear: number;
  showRevenuePct?: boolean;
  overrides: Record<string, string>;
  onOverrideChange: (code: string, value: string) => void;
}) {
  const refDate = `31/12/${referenceYear}`;
  const lastDay = new Date(partialYear, periodMonths, 0).getDate();
  const partialDate = `${lastDay}/${String(periodMonths).padStart(2, "0")}/${partialYear}`;
  const projDate = `31/12/${partialYear}`;

  // Revenue values for % computation
  const refRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.reference_value ?? 0)
    : 0;
  const partialRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.partial_value ?? 0)
    : 0;

  const pctOnRevenue = (value: number, revenue: number) =>
    revenue !== 0 ? (value / revenue) * 100 : 0;

  // Get projected value: override if editable, annualized otherwise
  const getProjectedValue = (item: IntraYearComparisonItem): number => {
    if (EDITABLE_CE_CODES.includes(item.code)) {
      return parseFloat(overrides[item.code] || "0");
    }
    return item.annualized_value;
  };

  // Compute projected revenue for % column
  const projRevenue = showRevenuePct
    ? parseFloat(overrides["ce01_ricavi_vendite"] || "0")
    : 0;

  // Helper: get projected value for a CE code (override if editable, annualized otherwise)
  const pv = (code: string): number =>
    EDITABLE_CE_CODES.includes(code)
      ? parseFloat(overrides[code] || "0")
      : (items.find((i) => i.code === code)?.annualized_value ?? 0);

  // Compute projected subtotals from overrides
  const projVP = VP_CODES.reduce((acc, c) => acc + pv(c), 0);
  const PROJ_COST_CODES_ALL = ["ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
    "ce08_costi_personale", "ce09_ammortamenti", "ce10_var_rimanenze_mat_prime",
    "ce11_accantonamenti", "ce11b_altri_accantonamenti", "ce12_oneri_diversi"];
  const projCP = PROJ_COST_CODES_ALL.reduce((acc, c) => acc + pv(c), 0);
  const projEbitda = projVP - (projCP - pv("ce09_ammortamenti"));
  const projEbit = projVP - projCP;

  const projFin = ["ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari", "ce16_utili_perdite_cambi"].reduce((acc, c) => acc + pv(c), 0)
    - pv("ce15_oneri_finanziari");
  // ce17 is an aggregate (rivalutazioni - svalutazioni); derive from its sub-fields so overrides apply
  const projRettifiche = pv("ce17a_rivalutazioni") - pv("ce17b_svalutazioni");
  const projStraord = pv("ce18_proventi_straordinari") - pv("ce19_oneri_straordinari");
  const projPBT = projEbit + projFin + projRettifiche + projStraord;
  const projNetProfit = projPBT - pv("ce20_imposte");

  const colSpan = showRevenuePct ? 2 : 1;

  return (
    <Table>
      <TableHeader>
        {/* Row 1: Category labels */}
        <TableRow className="border-b-0">
          <TableHead rowSpan={2} className="align-bottom">Voce</TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-muted-foreground text-xs font-normal">
            Storico
          </TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-xs font-normal">
            Infrannuale
          </TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-xs font-normal">
            Proiezione
          </TableHead>
          <TableHead className="text-center pb-0 text-muted-foreground text-xs font-normal">
            Proiezione / Storico
          </TableHead>
        </TableRow>
        {/* Row 2: Dates */}
        <TableRow>
          <TableHead className="text-right text-xs font-semibold">{refDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          <TableHead className="text-right text-xs font-semibold">{partialDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          <TableHead className="text-right text-xs font-semibold">{projDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          <TableHead className="text-right text-xs font-semibold">delta %</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items
          .filter(
            (item) =>
              ALWAYS_SHOW_CODES.has(item.code) ||
              item.partial_value !== 0 ||
              item.reference_value !== 0 ||
              item.prior_value !== 0
          )
          .map((item) => {
            const isHeader = item.code.startsWith("_hdr_");
            const isSubtotal = ["_totale_vp", "_totale_cp", "_totale_fin", "_totale_straord",
              "_ebitda", "_ebit", "_profit_before_tax", "_net_profit"].includes(item.code);
            const isPctRow = item.code === "_ebitda_pct";
            const isEditable = EDITABLE_CE_CODES.includes(item.code);
            const isDetail = item.code in DETAIL_PARENTS;

            // Section headers
            if (isHeader) {
              const totalCols = 1 + colSpan + colSpan + colSpan + 1;
              return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={totalCols} className="text-sm font-bold py-2">
                    {item.label}
                  </TableCell>
                </TableRow>
              );
            }

            // Projected value: from overrides for editable, computed for synthetic rows
            let projValue: number;
            if (item.code === "_totale_vp") projValue = projVP;
            else if (item.code === "_totale_cp") projValue = projCP;
            else if (item.code === "_ebitda") projValue = projEbitda;
            else if (item.code === "_ebit") projValue = projEbit;
            else if (item.code === "_totale_fin") projValue = projFin;
            else if (item.code === "_totale_straord") projValue = projStraord;
            else if (item.code === "_profit_before_tax") projValue = projPBT;
            else if (item.code === "_net_profit") projValue = projNetProfit;
            else projValue = getProjectedValue(item);

            const delta = item.reference_value !== 0
              ? ((projValue - item.reference_value) / Math.abs(item.reference_value)) * 100
              : 0;
            const isPositive = delta > 1;
            const isNegative = delta < -1;

            return (
              <TableRow
                key={item.code}
                className={cn(
                  isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10",
                )}
              >
                <TableCell className={cn(
                  "text-sm",
                  isSubtotal ? "font-semibold" : isDetail ? "pl-6 text-muted-foreground font-normal" : "font-medium",
                )}>
                  {item.label}
                </TableCell>
                {/* Reference (historical) */}
                <TableCell className="text-right text-sm text-muted-foreground">
                  {isPctRow ? formatPct(item.reference_value) : formatEuro(item.reference_value)}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.reference_value, refRevenue))}
                  </TableCell>
                )}
                {/* Partial (infrannuale) */}
                <TableCell className="text-right text-sm">
                  {isPctRow ? formatPct(item.partial_value) : formatEuro(item.partial_value)}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.partial_value, partialRevenue))}
                  </TableCell>
                )}
                {/* Projection (editable for CE items, computed for totals) */}
                <TableCell className="text-right text-sm">
                  {isEditable ? (
                    <Input
                      type="text"
                      inputMode="numeric"
                      className="w-32 ml-auto text-right h-8 text-sm"
                      value={formatInputNumber(overrides[item.code] || "")}
                      onChange={(e) => onOverrideChange(item.code, parseInputNumber(e.target.value))}
                    />
                  ) : isPctRow ? (
                    formatPct(projValue)
                  ) : (
                    <span className="font-medium">{formatEuro(projValue)}</span>
                  )}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(projValue, projRevenue))}
                  </TableCell>
                )}
                {/* Delta % */}
                <TableCell className="text-right text-sm">
                  {isPctRow ? (
                    <span className="text-muted-foreground">-</span>
                  ) : (
                    <span
                      className={
                        isPositive
                          ? "text-green-600 dark:text-green-400"
                          : isNegative
                          ? "text-red-600 dark:text-red-400"
                          : "text-muted-foreground"
                      }
                    >
                      {delta > 0 ? "+" : ""}{formatPct(delta)}
                    </span>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
      </TableBody>
    </Table>
  );
}

