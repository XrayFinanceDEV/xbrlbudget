/** Decisione 8 del proprietario (2026-09-14): fornitori a zero nell'anno base sono un problema di
 *  riclassifica (PROVA AMBIENTA: `_distribute_sp16_operativo` dell'infrannuale li ha messi in
 *  «altri debiti»), non del percorso. Si segnala soltanto, ai passi 4 e 5. */
import type { BalanceSheet, IncomeStatement } from "@/types/api";
import { num } from "@/lib/budget-format";

const eur = (v: number) => `${new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 }).format(Math.round(v))} €`;

export function fornitoriZeroAvviso(baseYear: number, baseBs: BalanceSheet | null | undefined, baseInc: IncomeStatement | null | undefined) {
  if (!baseBs || !baseInc) return null;
  const bs = baseBs as unknown as Record<string, unknown>, inc = baseInc as unknown as Record<string, unknown>;
  const acquisti = num(inc.ce05_materie_prime) + num(inc.ce06_servizi) + num(inc.ce07_godimento_beni);
  if (num(bs.sp16d_debiti_fornitori_breve) !== 0 || acquisti <= 0) return null;
  return {
    titolo: "Non risultano debiti verso fornitori nell'anno di partenza. Controllare le riclassifiche dei debiti!",
    dettaglio: `I costi di acquisto del ${baseYear} sono ${eur(acquisti)}, i giorni di pagamento non si possono calcolare. Gli altri debiti a breve valgono ${eur(num(bs.sp16g_altri_debiti_breve))}.`,
  };
}
