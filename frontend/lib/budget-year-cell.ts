/**
 * Se una singola casella della tabella per anno sia modificabile, e perche' no.
 *
 * Perche' esiste: `YearInputTable` sapeva spegnere solo una RIGA intera
 * (`off`), e una riga vale per tutti gli anni. Ma un `ce05_override` forza la
 * voce su UN anno, non sul piano: al passo 3 la casella «parte variabile
 * 2025» accettava un numero senza un solo segnale mentre l'anteprima restava
 * ferma sull'importo forzato, e il badge «forzato in CE Prev.» si accendeva
 * sulle righe di TUTTI gli anni perche' bastava che un anno qualunque avesse
 * l'override. L'utente digitava in una casella che non serve a niente, e
 * l'unico indizio era acceso anche dove la casella funziona.
 *
 * La granularita' quindi e' l'ANNO. Qui e non dentro il componente perche' un
 * componente in questo repo non e' collaudabile (nessun jsdom, e non va
 * aggiunto): la stessa lezione del giro precedente, quando `off` spegneva anni
 * che il motore usava ancora.
 *
 * Precedenza: `off` (la riga intera) batte `offYears` (alcuni anni). Le due
 * ragioni sono diverse — una quota all'estremo annulla la voce su tutto il
 * piano, un override la sostituisce su un anno — quindi ognuna porta la
 * propria spiegazione, e la spiegazione della piu' generale vince.
 */

export interface YearCellOff {
  /** La riga intera e' inerte: nessun anno e' modificabile. */
  off?: boolean;
  /** Il perche' della riga inerte, mostrato come `title`. */
  offNote?: string;
  /** SOLO questi anni sono inerti: gli altri restano modificabili. */
  offYears?: number[];
  /** Il perche' dell'anno inerte, mostrato come `title`. */
  offYearsNote?: string;
}

export interface YearCellState {
  disabled: boolean;
  /** `undefined` quando non c'e' nulla da spiegare: una casella viva non
   *  porta un tooltip, e una casella spenta senza motivo dichiarato e'
   *  esattamente il difetto da cui nasce questo modulo. */
  title?: string;
}

const VIVA: YearCellState = { disabled: false };

export function yearCellState(row: YearCellOff, year: number): YearCellState {
  if (row.off) return { disabled: true, title: row.offNote };
  if (row.offYears?.includes(year)) return { disabled: true, title: row.offYearsNote };
  return VIVA;
}
