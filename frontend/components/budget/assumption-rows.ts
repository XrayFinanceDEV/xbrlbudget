// Config-driven row definitions for the budget assumptions form.
// Spec: docs/superpowers/specs/2026-07-06-budget-assumptions-simplification-design.md
// A row with fields.length > 1 DUAL-WRITES the same value into every listed
// column (Materie/Servizi %: variable == fixed growth makes the fixed/variable
// split mathematically irrelevant — see forecast_engine.py:220-242).
import type { IncomeStatement } from "@/types/api";
import { num } from "@/lib/budget-format";
import { FIELD_RULES, type FieldName } from "@/lib/budget-field-rules";
import { ceAggregates } from "@/lib/budget-preview-rows";

export type AssumptionRowDef = {
  key: string;
  label: string;
  tooltip?: string;
  kind: "pct" | "eur" | "years" | "days" | "bool";
  /** columns written; >1 = dual-write the same value into each */
  fields: string[];
  /** CE/BS field rendered in the read-only historical columns */
  historicalField?: string;
  /** when set: show a "personalizzato in Avanzate" badge if
   *  assumptions[divergenceField] !== assumptions[fields[0]] */
  divergenceField?: string;
  /** empty input maps to null instead of 0 (auto/constant semantics) */
  nullable?: boolean;
  /** placeholder shows the auto-derived base-year value */
  autoPlaceholder?: "dso" | "dio" | "dpo";
  step?: string;
  min?: number;
  max?: number;
};

/** Cio' che una riga aggiunge alla regola del campo. `key` e `label` sono
 *  obbligatori: senza il cast di prima, una riga senza etichetta non compila. */
type RowExtras = Pick<AssumptionRowDef, "key" | "label">
  & Partial<Omit<AssumptionRowDef, "key" | "label" | "fields">>;

/** kind/min/max/step/nullable come from FIELD_RULES (lib/budget-field-rules.ts) —
 *  the row only adds label/tooltip/fields/historicalField/etc. Rule keyed on
 *  fields[0]; dual-write rows share one rule across their fields.
 *
 *  I campi sono tipati `FieldName`, cioe' le sole chiavi di `FIELD_RULES`: una
 *  riga costruita su un campo che non ha una regola non compila piu'. Prima
 *  faceva lo spread di `undefined` e nasceva senza `kind` e senza `min/max/step`,
 *  con `tsc` pulito e la suite verde. */
const rule = (fields: [FieldName, ...FieldName[]], over: RowExtras): AssumptionRowDef =>
  ({ fields, ...FIELD_RULES[fields[0]], ...over });

export const ESSENTIAL_ROWS: AssumptionRowDef[] = [
  rule(["revenue_growth_pct"], { key: "ricavi", label: "Ricavi %", historicalField: "ce01_ricavi_vendite",
        tooltip: "Variazione % dei ricavi rispetto all'anno precedente di piano" }),
  rule(["variable_materials_growth_pct", "fixed_materials_growth_pct"],
       { key: "materie", label: "Materie prime %", historicalField: "ce05_materie_prime",
         divergenceField: "fixed_materials_growth_pct",
         tooltip: "Variazione % dei costi per materie. Quote variabile/fissa distinte in Avanzate" }),
  rule(["variable_services_growth_pct", "fixed_services_growth_pct"],
       { key: "servizi", label: "Servizi %", historicalField: "ce06_servizi",
         divergenceField: "fixed_services_growth_pct",
         tooltip: "Variazione % dei costi per servizi. Quote variabile/fissa distinte in Avanzate" }),
  rule(["personnel_growth_pct"], { key: "personale", label: "Personale %", historicalField: "ce08_costi_personale" }),
  rule(["other_costs_growth_pct"], { key: "altri-costi", label: "Altri costi (oneri diversi) %",
        historicalField: "ce12_oneri_diversi" }),
  rule(["tangible_investments"], { key: "capex-mat", label: "Investimenti materiali €" }),
  rule(["intangible_investments"], { key: "capex-imm", label: "Investimenti immateriali €" }),
  rule(["existing_debt_repayment_years"], { key: "rimborso-banche", label: "Rimborso debiti bancari (anni)",
        tooltip: "Anni di rimborso del debito bancario esistente. Vuoto = debito costante" }),
  rule(["financing_amount"], { key: "fin-importo", label: "Nuovo finanziamento €" }),
  rule(["financing_duration_years"], { key: "fin-durata", label: "Nuovo finanziamento: durata (anni)" }),
  rule(["financing_interest_rate"], { key: "fin-tasso", label: "Nuovo finanziamento: tasso %" }),
];

export const ADVANCED_GROUPS: { title: string; rows: AssumptionRowDef[] }[] = [
  {
    title: "Ricavi e costi — dettaglio",
    rows: [
      rule(["other_revenue_growth_pct"], { key: "altri-ricavi", label: "Altri ricavi %",
            historicalField: "ce04_altri_ricavi" }),
      rule(["rent_growth_pct"], { key: "affitti", label: "Godimento beni di terzi %",
            historicalField: "ce07_godimento_beni" }),
      rule(["fixed_materials_percentage"], { key: "quota-fissa-mat", label: "% quota fissa materie",
            tooltip: "Quota di costi materie che NON scala col variabile. Rilevante solo se le due crescite divergono" }),
      rule(["fixed_services_percentage"], { key: "quota-fissa-serv", label: "% quota fissa servizi" }),
      rule(["variable_materials_growth_pct"], { key: "var-materie", label: "Var. % costi variabili materie" }),
      rule(["fixed_materials_growth_pct"], { key: "fix-materie", label: "Var. % costi fissi materie" }),
      rule(["variable_services_growth_pct"], { key: "var-servizi", label: "Var. % costi variabili servizi" }),
      rule(["fixed_services_growth_pct"], { key: "fix-servizi", label: "Var. % costi fissi servizi" }),
    ],
  },
  {
    title: "Capitale circolante",
    rows: [
      rule(["dso_days"], { key: "dso", label: "Giorni incasso clienti (DSO)", autoPlaceholder: "dso" }),
      rule(["dio_days"], { key: "dio", label: "Giorni rotazione magazzino (DIO)", autoPlaceholder: "dio" }),
      rule(["dpo_days"], { key: "dpo", label: "Giorni pagamento fornitori (DPO)", autoPlaceholder: "dpo" }),
      rule(["receivables_long_growth_pct"], { key: "crediti-oltre", label: "Crediti oltre 12 mesi %" }),
    ],
  },
  {
    title: "Stato patrimoniale",
    rows: [
      rule(["sp01_growth_pct"], { key: "sp01", label: "Crediti verso soci %" }),
      rule(["sp04_growth_pct"], { key: "sp04", label: "Immobilizzazioni finanziarie %" }),
      rule(["sp06e_growth_pct"], { key: "sp06e", label: "Crediti tributari %",
            tooltip: "Variazione % anno-su-anno dei crediti tributari (IVA a credito ecc.). Vuoto = costanti. NON legati ai ricavi" }),
      rule(["sp06f_growth_pct"], { key: "sp06f", label: "Imposte anticipate %",
            tooltip: "Variazione % anno-su-anno delle imposte anticipate. Vuoto = costanti. NON legate ai ricavi" }),
      rule(["sp08_growth_pct"], { key: "sp08", label: "Attività finanziarie %" }),
      rule(["sp10_growth_pct"], { key: "sp10", label: "Ratei e risconti attivi %" }),
      rule(["sp14_growth_pct"], { key: "sp14", label: "Fondi per rischi e oneri %" }),
      rule(["sp16e_growth_pct"], { key: "sp16e", label: "Debiti tributari entro %" }),
      rule(["sp16f_growth_pct"], { key: "sp16f", label: "Debiti previdenziali entro %" }),
      rule(["sp16g_growth_pct"], { key: "sp16g", label: "Altri debiti entro %" }),
      rule(["sp17d_growth_pct"], { key: "sp17d", label: "Debiti fornitori oltre %" }),
      rule(["sp17e_growth_pct"], { key: "sp17e", label: "Debiti tributari oltre %" }),
      rule(["sp17f_growth_pct"], { key: "sp17f", label: "Debiti previdenziali oltre %" }),
      rule(["sp17g_growth_pct"], { key: "sp17g", label: "Altri debiti oltre %" }),
      rule(["sp18_growth_pct"], { key: "sp18", label: "Ratei e risconti passivi %" }),
      rule(["asset_disposal_nbv"], { key: "cessioni-nbv", label: "Cessioni: valore contabile netto €" }),
      rule(["asset_disposal_proceeds"], { key: "cessioni-prezzo", label: "Cessioni: corrispettivo €" }),
      rule(["altri_finanz_repayment_years"], { key: "altri-finanz", label: "Rimborso altri finanziatori (anni)" }),
      rule(["depreciation_rate"], { key: "amm-mat", label: "Ammortamento nuovi investimenti materiali %" }),
      rule(["depreciation_rate_intangible"], { key: "amm-imm", label: "Ammortamento nuovi investimenti immateriali %" }),
      rule(["tfr_accrual_suspended"], { key: "tfr-inps", label: "TFR versato a INPS/fondi (accantonamento sospeso)" }),
      rule(["previdenza_scales_with_personnel"], { key: "previdenza-personale",
            label: "Debiti previdenziali scalano col costo del personale" }),
      rule(["cash_sweep_enabled"], { key: "cash-sweep",
            label: "Cash sweep (usa cassa in eccesso per rimborsare debito)" }),
      rule(["cash_sweep_min_cash"], { key: "cash-sweep-min", label: "Cash sweep: cassa minima €" }),
    ],
  },
  {
    title: "Fiscale",
    rows: [
      rule(["tax_rate"], { key: "tax", label: "Aliquota fiscale % (override)",
            tooltip: "Il motore usa l'aliquota EFFETTIVA dell'anno base quando plausibile; questo valore è il fallback" }),
      rule(["tax_advances_paid"], { key: "tax-advances", label: "Acconti imposte versati €",
            tooltip: "Riduce il debito tributario di fine anno; un'eccedenza viene riclassificata tra i crediti tributari" }),
    ],
  },
];

/** Effective base-year tax rate (ce20 / PBT), or null when not derivable.
 *  Mirrors the engine's preference (forecast_engine.py:374-390). PBT comes from
 *  ceAggregates (lib/budget-preview-rows.ts) so the formula exists in one place. */
export function computeEffectiveTaxRate(income: IncomeStatement): number | null {
  const pbt = ceAggregates(income as unknown as Record<string, unknown>).ebt;
  const tax = num(income.ce20_imposte);
  if (pbt <= 0 || tax <= 0) return null;
  const rate = (tax / pbt) * 100;
  return rate > 0 && rate <= 60 ? Math.round(rate * 10) / 10 : null;
}
