/**
 * Da dove viene il valore proiettato di una riga di conto economico, nella tab
 * Proiezione e nella Stampa.
 *
 * Tre casi, e uno è nuovo:
 *  - riga **modificabile** (`EDITABLE_CE_CODES`): vale quel che l'utente ha
 *    scritto, che il client manda come override;
 *  - riga **dedotta** (`DERIVED_CE_CODES`): le due variazioni di magazzino, che
 *    dal 2026-09-16 il motore ricava dal movimento dello stato patrimoniale
 *    (decisione del proprietario). Il client non le manda più come override —
 *    lo faceva per tutte e 22 le righe, anche quelle mai toccate, e quell'override
 *    scavalcava sempre il calcolo — e a schermo mostra il valore che il motore ha
 *    persistito. Prima del primo salvataggio quel valore non esiste ancora: lì
 *    resta l'annualizzazione del parziale, che è la stessa stima di prima;
 *  - tutte le altre: annualizzazione del parziale, come sempre.
 *
 * È una funzione sola perché i due componenti la calcolavano ciascuno per conto
 * proprio: due grafie della stessa regola sono due modi di andare alla deriva.
 */
import { DERIVED_CE_CODES, EDITABLE_CE_CODES } from "@/lib/pratica-codes";

export interface FonteCeProiettato {
  overrides: Record<string, string>;
  /** Le righe dedotte, lette dall'ultimo previsionale persistito. */
  derivati?: Record<string, number> | null;
  annualizzato: (code: string) => number;
}

export function valoreCeProiettato(code: string, fonte: FonteCeProiettato): number {
  if (EDITABLE_CE_CODES.includes(code)) {
    return Number.parseFloat(fonte.overrides[code] || "0");
  }
  const derivato = fonte.derivati?.[code];
  if (derivato !== undefined && derivato !== null) return derivato;
  return fonte.annualizzato(code);
}

/**
 * Le righe dedotte lette dal conto economico previsionale persistito, o `null`
 * quando non ce n'è ancora uno. Un previsionale che non contiene la riga non è
 * uno zero: è un'assenza, e la riga ricade sull'annualizzazione.
 */
export function ceDerivatiDaForecast(
  forecastIncome: Record<string, number> | null | undefined,
): Record<string, number> | null {
  if (!forecastIncome) return null;
  const derivati: Record<string, number> = {};
  for (const code of DERIVED_CE_CODES) {
    const valore = forecastIncome[code];
    if (typeof valore === "number" && Number.isFinite(valore)) derivati[code] = valore;
  }
  return Object.keys(derivati).length > 0 ? derivati : null;
}
