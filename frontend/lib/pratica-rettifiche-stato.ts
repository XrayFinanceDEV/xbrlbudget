/**
 * Stato di una scheda Rettifiche (storico / bilancio di verifica): quale badge
 * mostra la sua tab.
 *
 * Modulo puro (nessun import da `app/` o `components/`, vedi CLAUDE.md), così
 * la decisione è provabile senza montare il wizard.
 */

export interface StatoScheda {
  /**
   * `false` finché il server non ha risposto. `exists` da solo NON è una
   * risposta: parte da `true` e torna a `true` a ogni cambio di identità
   * (azienda, anno, mesi coperti), quindi vale «non lo so», non «c'è».
   */
  resolved: boolean;
  /** `false` solo dopo un 404: per quell'anno non esiste alcun FinancialYear. */
  exists: boolean;
  confirmed: boolean;
}

/** `null` = nessun badge: la scheda non c'è, oppure non si sa ancora. */
export type BadgeScheda = "confermata" | "da confermare" | null;

export function badgeScheda(scheda: StatoScheda): BadgeScheda {
  // Nessun badge finché non si sa: «da confermare» su una scheda che risponde
  // 404 pubblicizza un lavoro che non si può fare, e `exists` rialzato a `true`
  // dal reset di identità lo farebbe ricomparire per la durata di ogni fetch.
  if (!scheda.resolved || !scheda.exists) return null;
  return scheda.confirmed ? "confermata" : "da confermare";
}
