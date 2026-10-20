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

/**
 * Lo spacchettamento dell'utile importato: la parte del risultato dello SP che il
 * conto economico non spiega è il risultato di esercizi precedenti non ancora
 * girato a patrimonio netto, e va negli utili (perdite) portati a nuovo. `null`
 * quando SP e CE coincidono al centesimo.
 *
 * Un bilancio di verifica (infrannuale, o al 31/12 prima della chiusura) stampa
 * spesso un solo "utile" dato dalla differenza attivo − passivo: Unicarton
 * 31/08/2026 chiude lo SP a 241.711,59 col CE a 68.247,80, e i 173.463,79 di
 * differenza sono l'utile 2025 non destinato. L'import non lo deduce (decisione
 * del proprietario su budget_680, 2026-10-06): lo segnala, e l'utente lo separa
 * da qui. La distribuzione fra le riserve resta alle riclassifiche SP→SP.
 *
 * SEGNO. delta = sp13 importato − utile CE, da sommare agli utili portati a
 * nuovo: una perdita pregressa dà un delta negativo. Alla conferma
 * `recalcAggregates` riporta sp13 al risultato del CE, quindi il passivo non
 * cambia e lo scarto CE↔SP si chiude: la guardia del server lo accetta.
 */
export function risultatoPrecedente(
  sp13Importato: number,
  utileCe: number,
): ChiusuraSbilancio | null {
  const delta = Math.round((sp13Importato - utileCe) * 100) / 100;
  if (Math.abs(delta) <= TOLLERANZA_QUADRATURA) return null;
  const field = "sp12g_utili_perdite_portati";
  const label = labelOf(field);
  return {
    field,
    label,
    side: "passivo",
    delta,
    explanation:
      `Spacchettamento dell'utile importato: ${formatEuroPreciso(Math.abs(delta))} ` +
      `di ${delta >= 0 ? "utile" : "perdita"} di esercizi precedenti non ancora ` +
      `destinato, portato a ${label}`,
  };
}
