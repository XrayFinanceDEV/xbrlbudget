import type { BalanceSheet, IncomeStatement } from "@/types/api";
import { num } from "@/lib/budget-format";

/**
 * I giorni di rotazione «auto» derivati dall'anno base: il valore che il motore
 * applica quando il campo resta vuoto, ed è quindi il valore che il segnaposto
 * `auto:` può promettere.
 *
 * Il ramo `dso` scorpora dall'aggregato dei crediti a breve i crediti tributari
 * (`sp06e`) e le imposte anticipate (`sp06f`), perché il motore fa lo stesso:
 * non sono crediti commerciali e non devono scalare coi ricavi, quindi li porta
 * avanti a parte e guida col DSO i soli secchi commerciali. Il segnaposto usava
 * l'aggregato intero e prometteva 122 giorni dove il motore ne applicava 116 —
 * l'utente leggeva 122, lasciava il campo vuoto convinto di averli accettati, e
 * ne otteneva 116. Su un anno base senza quelle due componenti le due formule
 * coincidono, ed è per questo che il difetto era invisibile.
 *
 * Il clamp a zero è quello del motore: un aggregato incoerente non deve
 * produrre giorni negativi, cioè crediti negativi nel piano.
 *
 * DPO non ha scorpori: il motore lo applica sull'aggregato intero.
 *
 * Il ramo `dio` (spec B01, 2026-09-26) non guida più le rimanenze sui ricavi: il motore
 * calcola le materie prime (`sp05a`) dal CONSUMO dell'anno (`ce05 + ce10`), perché
 * un'azienda che compra e consuma materie non le vende. Il segnaposto scorpora allo
 * stesso modo — numeratore le sole materie (`sp05a`, o l'aggregato meno `sp05e` quando
 * la base non ha alcuna sotto-voce di dettaglio), denominatore il consumo dell'anno base,
 * non il fatturato.
 */
export function computeAutoDays(
  kind: "dso" | "dio" | "dpo",
  income: IncomeStatement | undefined,
  balance: BalanceSheet | undefined,
): number | null {
  if (!income || !balance) return null;
  const revenue = num(income.ce01_ricavi_vendite);
  const purchases = num(income.ce05_materie_prime) + num(income.ce06_servizi);
  let numerator = 0;
  let denominator = 0;
  if (kind === "dso") {
    numerator = Math.max(
      0,
      num(balance.sp06_crediti_breve)
        - num(balance.sp06e_crediti_tributari_breve)
        - num(balance.sp06f_imposte_anticipate_breve),
    );
    denominator = revenue;
  }
  if (kind === "dio") {
    const materiePrime = num(balance.sp05a_materie_prime);
    numerator = materiePrime > 0
      ? materiePrime
      : num(balance.sp05_rimanenze) - num(balance.sp05e_acconti);
    denominator = num(income.ce05_materie_prime) + num(income.ce10_var_rimanenze_mat_prime);
  }
  if (kind === "dpo") { numerator = num(balance.sp16d_debiti_fornitori_breve); denominator = purchases; }
  if (denominator <= 0) return null;
  return Math.round((numerator / denominator) * 360);
}
