import type { AssumptionsMap } from "@/lib/budget-horizon";
import type { SpIndexingDriver } from "@/types/api";
import { numOrNull } from "@/lib/budget-format";

/** The preview has SP line items, but no `total_assets` computed property. */
const ASSET_FIELDS = [
  "sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
  "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve",
  "sp07_crediti_lungo", "sp08_attivita_finanziarie", "sp09_disponibilita_liquide",
  "sp10_ratei_risconti_attivi",
] as const;

export function previewTotalAssets(balance: Record<string, unknown> | null | undefined): number | null {
  if (!balance) return null;
  const amounts = ASSET_FIELDS.map((field) => numOrNull(balance[field]));
  return amounts.some((amount) => amount === null)
    ? null
    : amounts.reduce<number>((sum, amount) => sum + (amount ?? 0), 0);
}

/** An absent SP override means the forecast engine is still calculating this year. */
export function manualSpValue(
  assumptions: AssumptionsMap, year: number, field: string, previewValue: number | null,
): number | null {
  const raw = assumptions[year]?.sp_overrides?.[field];
  return raw == null ? previewValue : Number(raw);
}

function withoutKey<T>(bag: Record<string, T> | null | undefined, key: string): Record<string, T> | null {
  const { [key]: _removed, ...rest } = bag ?? {};
  return Object.keys(rest).length > 0 ? rest : null;
}

/** A mode switch keeps the chosen rule and the absolute balances mutually exclusive. */
export function withSpRule(
  assumptions: AssumptionsMap,
  years: number[],
  code: string,
  field: string,
  growthField: string,
  driver: SpIndexingDriver | null,
  projected: Record<number, number | null>,
): AssumptionsMap {
  const next = { ...assumptions };
  for (const year of years) {
    const row = next[year] ?? {};
    const indexing = withoutKey(row.sp_indexing, code);
    const overrides = withoutKey(row.sp_overrides, field);
    const projectedValue = projected[year];
    next[year] = {
      ...row,
      [growthField]: null,
      sp_indexing: driver ? { ...indexing, [code]: driver } : indexing,
      sp_overrides: driver || projectedValue == null
        ? overrides
        : { ...overrides, [field]: projectedValue },
    };
  }
  return next;
}

/** First edit fixes the whole row in euros, so later recalculations cannot move untouched years. */
export function withManualSpAmount(
  assumptions: AssumptionsMap,
  years: number[],
  yearToEdit: number,
  code: string,
  field: string,
  growthField: string,
  amount: number,
  projected: Record<number, number | null>,
): AssumptionsMap {
  const next = { ...assumptions };
  for (const year of years) {
    const row = next[year] ?? {};
    const original = row.sp_overrides?.[field];
    const value = year === yearToEdit ? amount : original ?? projected[year];
    next[year] = {
      ...row,
      [growthField]: null,
      sp_indexing: withoutKey(row.sp_indexing, code),
      sp_overrides: value == null ? row.sp_overrides ?? null : { ...(row.sp_overrides ?? {}), [field]: Number(value) },
    };
  }
  return next;
}
