// Presentation decisions for one PreviewCell (lib/budget-preview-rows.ts):
// what to show as the main figure, what (if anything) goes under it, and
// whether a note travels with it. Extracted out of PreviewPanel so it is
// testable without a DOM (environment: node, no jsdom in this repo).
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import type { PreviewCell, PreviewRowKind } from "@/lib/budget-preview-rows";

export function describeCell(cell: PreviewCell): { main: string; sub: string | null; note: string | null } {
  // `value === null` and "no pct/days" are independent facts: a percentage-
  // or-days-only row (rowsFatturato's "cumulata", rowsCircolante's
  // "ccn-pct") carries value: null on purpose and still has a real pct to
  // show — value nullity must never swallow pct/days/note.
  const main = cell.value === null ? "—" : formatCurrency(cell.value);
  const hasPct = cell.pct !== undefined && cell.pct !== null;
  const hasDays = cell.days !== undefined && cell.days !== null;
  const sub = hasPct ? formatPercentage(cell.pct! / 100) : hasDays ? `${cell.days} gg` : null;
  const note = cell.note ?? null;
  return { main, sub, note };
}

export function rowClass(kind: PreviewRowKind): string {
  switch (kind) {
    case "sub":
      return "text-muted-foreground text-xs";
    case "total":
      return "font-semibold border-t border-border bg-muted/40";
    case "kpi":
      return "font-semibold";
    default:
      return "";
  }
}
