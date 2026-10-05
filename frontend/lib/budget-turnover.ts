import type { BalanceSheet, IncomeStatement } from "@/types/api";
import { num } from "@/lib/budget-format";

/**
 * I giorni di rotazione «auto» derivati dall'anno base: il valore che il motore
 * applica quando il campo resta vuoto, ed è quindi il valore che il segnaposto
 * `auto:` può promettere.
 *
 * Il ramo `dso` (ULTIMO allineamento, fix finale 2): senza piano `crediti_commerciali` e' il DSO sui
 * soli clienti (sp06a + sp07a, con i ripieghi del motore); col piano resta quello sull'intero
 * commerciale a breve, come il motore. Il resto di questo paragrafo descrive lo scorporo.
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
 * stesso modo — numeratore le sole materie (`sp05a`), denominatore il consumo dell'anno
 * base, non il fatturato. Il ripiego sull'aggregato meno `sp05e` scatta solo quando la
 * base non ha ALCUNA sotto-voce di `sp05` (tutte e cinque a zero, aggregato positivo) —
 * la stessa regola di `_materie_base` nel motore: un `sp05a` a zero con un'altra
 * sotto-voce valorizzata (es. `sp05c`) NON è "nessun dettaglio", è materie davvero a
 * zero, e il ripiego la confonderebbe con un'altra rimanenza.
 *
 * #62 nota S04: `dio` è il gruppo 1 (`sp05a + sp05b`, materie e semilavorati, sul consumo) e
 * `dio_pf` il gruppo 2 (`sp05d` sui ricavi). Il numero si restituisce anche quando supera 365
 * (807 gg su AMBIENTA): è il dato storico, e decide il chiamante se mostrarlo come
 * segnaposto o solo come nota — il motore, in quel caso, riporta il saldo.
 */
export function computeAutoDays(
  kind: "dso" | "dio" | "dio_pf" | "dpo",
  income: IncomeStatement | undefined,
  balance: BalanceSheet | undefined,
  opzioni: { pianoCrediti?: boolean } = {},
): number | null {
  if (!income || !balance) return null;
  const revenue = num(income.ce01_ricavi_vendite);
  const purchases = num(income.ce05_materie_prime) + num(income.ce06_servizi);
  let numerator = 0;
  let denominator = 0;
  if (kind === "dso") {
    const comm = Math.max(
      0,
      num(balance.sp06_crediti_breve)
        - num(balance.sp06e_crediti_tributari_breve)
        - num(balance.sp06f_imposte_anticipate_breve),
    );
    if (opzioni.pianoCrediti) {
      // Col piano `crediti_commerciali` il motore deriva il DSO sull'intero commerciale a breve.
      numerator = comm;
    } else {
      // Senza piano (#61 S03/S27) il DSO governa i soli CLIENTI, breve + oltre: sp06a + sp07a,
      // con gli stessi ripieghi del motore (`_calcola_stato_patrimoniale`, blocco DSO).
      const dettaglioBreve = ["sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve",
        "sp06c_crediti_collegate_breve", "sp06d_crediti_controllanti_breve", "sp06g_crediti_altri_breve"]
        .reduce((a, f) => a + num(balance[f as keyof BalanceSheet] as string), 0);
      const clientiBreve = dettaglioBreve === 0 && comm > 0 ? comm : num(balance.sp06a_crediti_clienti_breve);
      const dettaglioOltre = ["sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo",
        "sp07c_crediti_collegate_lungo", "sp07d_crediti_controllanti_lungo",
        "sp07e_crediti_tributari_lungo", "sp07g_crediti_altri_lungo"]
        .reduce((a, f) => a + num(balance[f as keyof BalanceSheet] as string), 0);
      const clientiOltre = dettaglioOltre === 0
        ? Math.max(0, num(balance.sp07_crediti_lungo) - num(balance.sp07f_imposte_anticipate_lungo))
        : num(balance.sp07a_crediti_clienti_lungo);
      numerator = clientiBreve + clientiOltre;
    }
    denominator = revenue;
  }
  if (kind === "dio") {
    // Gruppo 1 (#62 nota S04): materie prime + semilavorati sul consumo.
    const gruppo1 = num(balance.sp05a_materie_prime) + num(balance.sp05b_prodotti_in_corso);
    const sottoVociTotale = gruppo1
      + num(balance.sp05c_lavori_in_corso)
      + num(balance.sp05d_prodotti_finiti)
      + num(balance.sp05e_acconti);
    const aggregato = num(balance.sp05_rimanenze);
    numerator = sottoVociTotale === 0 && aggregato > 0
      ? aggregato - num(balance.sp05e_acconti)
      : gruppo1;
    denominator = num(income.ce05_materie_prime) + num(income.ce10_var_rimanenze_mat_prime);
  }
  if (kind === "dio_pf") {
    // Gruppo 2: prodotti finiti e merci sui ricavi.
    numerator = num(balance.sp05d_prodotti_finiti);
    denominator = revenue;
  }
  if (kind === "dpo") { numerator = num(balance.sp16d_debiti_fornitori_breve); denominator = purchases; }
  if (denominator <= 0) return null;
  return Math.round((numerator / denominator) * 360);
}
