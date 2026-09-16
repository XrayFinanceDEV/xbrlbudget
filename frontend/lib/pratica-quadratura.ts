/**
 * La quadratura del foglio rettificato: UNA sola aritmetica per il riquadro in
 * testa alla scheda Rettifiche, per il riepilogo di conferma e per la chiusura
 * dello scarto. Prima erano tre copie, e la prima che si muove fa dire alle
 * altre due una cosa diversa sullo stesso bilancio.
 *
 * Le due soglie non sono la stessa cosa:
 *
 *  - `TOLLERANZA_QUADRATURA` (0,01 €) — sopra questa il foglio **non quadra**.
 *    È la soglia del motore (`check_quadratura`, e il cancello della proiezione
 *    in `calculations/intra_year_engine.py`), non una scelta di questa schermata.
 *    Qui c'era 1 €: un foglio fuori di 23 centesimi si mostrava **verde**, il
 *    pulsante «Chiudi sbilancio» non compariva — è legato allo stesso giudizio —
 *    e poi la Proiezione si rifiutava di partire proprio per quello scarto, che
 *    nessuna schermata aveva mai mostrato (misurato su AMBIENTA 2026/6M, attivo
 *    2.460.463,09 contro passivo 2.460.463,32).
 *
 *  - `SOGLIA_CHIUSURA_AUTOMATICA` (2 €) — fino a qui lo scarto è rumore di
 *    arrotondamento dell'importazione e alla conferma si chiude **da solo**,
 *    registrato in giornale come ogni altra rettifica (decisione del
 *    proprietario, 2026-09-16). Sopra, la chiusura resta un gesto dell'utente:
 *    quell'importo non è più rumore e va capito prima di imputarlo.
 *
 * Nessun importo nasce in silenzio: la chiusura automatica scrive una voce del
 * giornale, visibile e cancellabile, con la destinazione scritta a chiare
 * lettere.
 */
import { ATTIVO_CODES, PASSIVO_CODES } from "@/lib/pratica-codes";
import { labelOf } from "@/lib/ivcee-catalog";
import { formatEuroPreciso } from "@/lib/pratica-format";

export const TOLLERANZA_QUADRATURA = 0.01;
export const SOGLIA_CHIUSURA_AUTOMATICA = 2;

/**
 * Le due destinazioni di default della chiusura, una per lato. `side` guida il
 * SEGNO del delta, non l'indice nell'array: dedurlo dal prefisso del codice
 * funzionerebbe oggi e si romperebbe al primo campo aggiunto fuori schema.
 */
const BERSAGLI: { field: string; side: "attivo" | "passivo" }[] = [
  { field: "sp09_disponibilita_liquide", side: "attivo" },
  { field: "sp16g_altri_debiti_breve", side: "passivo" },
];

export interface ChiusuraSbilancio {
  field: string;
  label: string;
  side: "attivo" | "passivo";
  /** Da sommare a `field`. */
  delta: number;
  explanation: string;
}

/** Attivo − passivo, arrotondato al centesimo. Solo le voci di primo livello. */
export function scartoQuadratura(values: Record<string, number>): number {
  const somma = (codes: string[]) =>
    codes.reduce((s, k) => s + (values[k] ?? 0), 0);
  return Math.round((somma(ATTIVO_CODES) - somma(PASSIVO_CODES)) * 100) / 100;
}

export function quadra(scarto: number): boolean {
  return Math.abs(scarto) <= TOLLERANZA_QUADRATURA;
}

/**
 * La rettifica che chiude lo scarto, o `null` se il foglio già quadra.
 *
 * SEGNO. scarto = attivo − passivo.
 *   scarto > 0 (l'attivo eccede)  → si toglie dalla cassa.
 *   scarto < 0 (il passivo eccede) → si tolgono altri debiti.
 * In entrambi i casi: delta = −scarto su un campo dell'attivo, +scarto su uno
 * del passivo.
 */
export function chiusuraSbilancio(scarto: number): ChiusuraSbilancio | null {
  if (quadra(scarto)) return null;
  const bersaglio = scarto > 0 ? BERSAGLI[0] : BERSAGLI[1];
  const label = labelOf(bersaglio.field);
  return {
    field: bersaglio.field,
    label,
    side: bersaglio.side,
    delta: bersaglio.side === "attivo" ? -scarto : scarto,
    explanation:
      `Correzione di quadratura: scarto di importazione ` +
      `${formatEuroPreciso(Math.abs(scarto))} imputato a ${label}`,
  };
}

/**
 * La chiusura che la conferma delle Rettifiche applica da sola. `null` quando
 * il foglio quadra (niente da fare) e quando lo scarto supera i 2 €: sopra
 * quella soglia decide l'utente, dal pulsante.
 */
export function chiusuraAutomatica(scarto: number): ChiusuraSbilancio | null {
  if (Math.abs(scarto) > SOGLIA_CHIUSURA_AUTOMATICA) return null;
  return chiusuraSbilancio(scarto);
}
