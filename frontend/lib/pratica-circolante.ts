/**
 * I tre metodi con cui l'infrannuale proietta il circolante, e come si chiamano
 * a schermo.
 *
 * Non è solo un'etichetta: la scelta cambia i giorni di incasso e pagamento con
 * cui la proiezione arriva al 31/12, e su un caso reale vale mezzo milione di
 * cassa proiettata. Per questo la tendina porta anche la frase che dice cosa
 * assume ciascuno — chi sceglie deve sapere cosa sta assumendo.
 *
 * `storico` è il valore di partenza perché è il comportamento di sempre: nessuno
 * scenario già salvato cambia numeri finché l'utente non sceglie (nel motore un
 * `working_capital_mode` nullo vale «storico»).
 */
export const MODI_CIRCOLANTE = ["storico", "infrannuale", "equilibrio"] as const;

export type ModoCircolante = (typeof MODI_CIRCOLANTE)[number];

export const MODO_CIRCOLANTE_PREDEFINITO: ModoCircolante = "storico";

interface DescrizioneModo {
  /** Quel che si legge nella tendina, anche a menu chiuso. */
  etichetta: string;
  /** Cosa assume questo metodo, in una riga sotto la tendina. */
  spiegazione: string;
}

const DESCRIZIONI: Record<ModoCircolante, DescrizioneModo> = {
  storico: {
    etichetta: "Circolante storico",
    spiegazione:
      "Giorni di incasso, pagamento e giacenza dell'anno intero precedente: è un bilancio assestato, ma assume che tu torni a quel comportamento.",
  },
  infrannuale: {
    etichetta: "Circolante infrannuale",
    spiegazione:
      "I giorni osservati nel periodo, portati avanti: è il circolante che l'azienda ha adesso, anche quando non si finanzia da solo.",
  },
  equilibrio: {
    etichetta: "Circolante di equilibrio",
    spiegazione:
      "I giorni che fanno chiudere la cassa a zero, cercati fra quelli osservati e quelli dell'anno precedente: mai fuori da comportamenti già avuti.",
  },
};

export function etichettaModoCircolante(modo: ModoCircolante): string {
  return DESCRIZIONI[modo].etichetta;
}

export function spiegazioneModoCircolante(modo: ModoCircolante): string {
  return DESCRIZIONI[modo].spiegazione;
}

/** Vero per un valore che il motore accetta: guardia sul valore della tendina. */
export function isModoCircolante(valore: string): valore is ModoCircolante {
  return (MODI_CIRCOLANTE as readonly string[]).includes(valore);
}
