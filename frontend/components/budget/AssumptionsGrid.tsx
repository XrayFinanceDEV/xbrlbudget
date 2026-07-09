"use client";

// Generic assumptions table: rows are data (AssumptionRowDef), columns are
// read-only historical years + editable forecast years. Replaces the
// hand-rolled CEAssumptionsTable/SPAssumptionsTable row JSX.
import { Info } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import type { BalanceSheet, BudgetAssumptionsCreate, IncomeStatement } from "@/types/api";
import { AssumptionRowDef, computeAutoDays } from "./assumption-rows";

type Historical = Record<number, { income: IncomeStatement; balance: BalanceSheet }>;

const INPUT_CLS =
  "w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card " +
  "text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary";

function formatHistoricalCell(row: AssumptionRowDef, data?: { income: IncomeStatement }): string {
  if (!row.historicalField || !data?.income) return "—";
  const raw = (data.income as unknown as Record<string, string>)[row.historicalField];
  const v = parseFloat(raw ?? "");
  if (isNaN(v)) return "—";
  return new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 }).format(v);
}

export function AssumptionsGrid({
  rows,
  historicalYears,
  forecastYears,
  historicalData,
  assumptions,
  onUpdate,
  showHistorical = true,
}: {
  rows: AssumptionRowDef[];
  historicalYears: number[];
  forecastYears: number[];
  historicalData: Historical;
  assumptions: Record<number, Partial<BudgetAssumptionsCreate>>;
  onUpdate: (year: number, field: string, value: number | boolean | null) => void;
  showHistorical?: boolean;
}) {
  const histCols = showHistorical ? historicalYears : [];
  const baseYear = historicalYears[historicalYears.length - 1];

  const valueOf = (year: number, row: AssumptionRowDef) => {
    const v = (assumptions[year] as Record<string, unknown> | undefined)?.[row.fields[0]];
    return v === null || v === undefined ? "" : String(v);
  };

  const writeAll = (year: number, row: AssumptionRowDef, value: number | boolean | null) => {
    for (const field of row.fields) onUpdate(year, field, value);
  };

  const diverges = (year: number, row: AssumptionRowDef): boolean => {
    if (!row.divergenceField) return false;
    const a = assumptions[year] as Record<string, unknown> | undefined;
    return a !== undefined && a[row.fields[0]] !== a[row.divergenceField];
  };

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-border border border-border">
        <thead className="bg-muted">
          <tr>
            <th className="px-3 py-2 text-left text-xs font-bold text-foreground uppercase tracking-wider border-r border-border sticky left-0 bg-muted z-10" style={{ minWidth: "300px" }}>
              Ipotesi
            </th>
            {histCols.map((year) => (
              <th key={year} className="px-3 py-2 text-center text-xs font-bold text-foreground uppercase border-r border-border" style={{ minWidth: "110px" }}>
                {year}
              </th>
            ))}
            {forecastYears.map((year) => (
              <th key={year} className="px-3 py-2 text-center text-xs font-bold text-primary uppercase border-r border-border bg-primary/10" style={{ minWidth: "110px" }}>
                {year}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-card divide-y divide-border">
          {rows.map((row) => (
            <tr key={row.key} className="hover:bg-muted/50">
              <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
                <div className="font-medium flex items-center gap-1">
                  {row.label}
                  {row.tooltip && (
                    <span title={row.tooltip}>
                      <Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" />
                    </span>
                  )}
                </div>
              </td>
              {histCols.map((year) => (
                <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                  {formatHistoricalCell(row, historicalData[year])}
                </td>
              ))}
              {forecastYears.map((year) => (
                <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                  {row.kind === "bool" ? (
                    <div className="flex justify-center">
                      <Checkbox
                        checked={Boolean((assumptions[year] as Record<string, unknown> | undefined)?.[row.fields[0]])}
                        onCheckedChange={(checked) => writeAll(year, row, checked === true)}
                      />
                    </div>
                  ) : (
                    <div className="relative">
                      <input
                        type="number"
                        step={row.step ?? "1"}
                        min={row.min}
                        max={row.max}
                        value={valueOf(year, row)}
                        placeholder={
                          row.autoPlaceholder
                            ? `auto: ${computeAutoDays(row.autoPlaceholder, historicalData[baseYear]?.income, historicalData[baseYear]?.balance) ?? "—"}`
                            : row.nullable ? "auto" : "0"
                        }
                        // Select the current value on focus so typing REPLACES it instead
                        // of appending — the user no longer has to clear the cell first.
                        onFocus={(e) => e.target.select()}
                        onChange={(e) => {
                          const raw = e.target.value;
                          if (raw === "") {
                            writeAll(year, row, row.nullable ? null : 0);
                          } else {
                            const v = parseFloat(raw);
                            writeAll(year, row, isNaN(v) ? (row.nullable ? null : 0) : v);
                          }
                        }}
                        className={INPUT_CLS}
                      />
                      {diverges(year, row) && (
                        <Badge
                          variant="outline"
                          className="absolute -top-2 -right-1 px-1 py-0 text-[9px]"
                          title="Le crescite variabile/fissa divergono: valori distinti in Avanzate. Digitando qui vengono riallineate."
                        >
                          A
                        </Badge>
                      )}
                    </div>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
