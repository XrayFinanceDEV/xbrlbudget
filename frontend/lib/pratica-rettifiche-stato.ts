/**
 * Stato delle due schede Rettifiche (storico + bilancio di verifica): quale
 * badge mostra una tab, e che cosa dice la riga di stato sopra le tab.
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

export type RigaRettifiche =
  | { kind: "confermate"; schedeEsistenti: number }
  | { kind: "nessuna-scheda" }
  | { kind: "verifica-mancante" }
  | { kind: "da-confermare"; daConfermare: number; schedeEsistenti: number };

export function contaSchedeEsistenti(verifica: StatoScheda, storico: StatoScheda): number {
  return (verifica.exists ? 1 : 0) + (storico.exists ? 1 : 0);
}

export function contaDaConfermare(verifica: StatoScheda, storico: StatoScheda): number {
  return (
    (verifica.exists && !verifica.confirmed ? 1 : 0) +
    (storico.exists && !storico.confirmed ? 1 : 0)
  );
}

/**
 * @param tutteConfermate il gate `allRettificheConfirmed` della pagina, passato
 *        da fuori di proposito: è lui a sbloccare gli step successivi e non
 *        deve avere una seconda definizione qui dentro.
 */
export function rigaRettifiche(
  verifica: StatoScheda,
  storico: StatoScheda,
  tutteConfermate: boolean,
): RigaRettifiche {
  const esistenti = contaSchedeEsistenti(verifica, storico);
  if (tutteConfermate) return { kind: "confermate", schedeEsistenti: esistenti };
  if (esistenti === 0) return { kind: "nessuna-scheda" };
  // Il caso da intercettare dipende da `verifica.exists`, non dal conteggio
  // delle schede: con lo storico presente e confermato il conteggio vale 1, il
  // ramo «nessuna scheda» non scatta e restava un «Restano 0 schede da
  // confermare» — un numero giusto sotto una spiegazione che non spiega niente.
  // È anche l'unico modo di arrivare a `daConfermare === 0` senza che
  // `tutteConfermate` sia vero: da qui in giù N ≥ 1 è garantito.
  if (!verifica.exists) return { kind: "verifica-mancante" };
  return {
    kind: "da-confermare",
    daConfermare: contaDaConfermare(verifica, storico),
    schedeEsistenti: esistenti,
  };
}
