/**
 * Formattazione dei valori delle ipotesi nel report finale (M1-08B).
 *
 * Modulo puro: nessun React, nessun hook, nessuna chiamata di rete. Il report
 * non ricalcola nulla — `FinalReportModel` porta gli importi già decisi dal
 * motore come `DecimalString` (stringa decimale piana, CLAUDE.md › «Decimals»),
 * quindi anche qui si formatta la stringa e non si passa mai da un `number`:
 * `Number("123456789012345.67")` perde le unità e mostrerebbe un importo
 * diverso da quello persistito.
 *
 * Il valore `null` non è uno zero: è «nessun valore», e si rende con un
 * trattino e una spiegazione testuale. Lo zero vero si rende come «0».
 */
import { fieldRule } from "@/lib/budget-field-rules";
import { ETICHETTE_REGOLA_FIDI } from "@/lib/budget-finanziamenti-pregresso";
import { labelOf, VOCI } from "@/lib/ivcee-catalog";
import { STRING_ASSUMPTION_FIELDS, type AssumptionScalar, type DecimalString } from "@/types/final-report";

/** La grammatica ammessa dal contratto v1 sul filo JSON. */
const PLAIN_DECIMAL = /^(-|\+)?(0|[1-9]\d*)(?:\.(\d+))?$/;

/** `text`: un'ipotesi che è una scelta e non una misura (la regola dei fidi). */
export type ScalarKind = "pct" | "eur" | "years" | "days" | "bool" | "number" | "text";

export interface ScalarView {
  /** Che cosa si legge in tabella. */
  text: string;
  /** `null`: nessun valore. Non è uno zero e non va confuso con uno zero. */
  absent: boolean;
  /** L'importo è negativo (il segno resta nel testo, mai solo nel colore). */
  negative: boolean;
  /** L'importo è esattamente zero. */
  zero: boolean;
  /** Testo per chi legge con uno screen reader: unità e assenza dichiarate. */
  srText: string;
  /** La stringa ricevuta non è un decimale piano: si mostra com'è, mai a zero. */
  malformed: boolean;
}

/** Raggruppa le migliaia con il punto, come si legge in italiano. */
function thousands(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

/**
 * Un decimale piano in formato italiano, senza toccarne una cifra: nessuna
 * arrotondazione, nessun `toFixed`, nessuna conversione in `number`.
 * `"-1234.50"` → `"-1.234,50"`; `"0.00"` → `"0,00"`; `"1e3"` → `"1e3"` (tale e
 * quale, marcato `malformed` da `describeScalar`).
 */
export function formatDecimalString(raw: string): string {
  const match = PLAIN_DECIMAL.exec(raw.trim());
  if (!match) return raw.trim();
  const sign = match[1] === "-" ? "-" : "";
  const integer = thousands(match[2]);
  const fraction = match[3] ? `,${match[3]}` : "";
  // Il segno su «zero» non è un valore negativo: "-0.00" è lo zero di un
  // rigiro contabile, e scriverlo con il meno farebbe vedere un debito dove
  // non ce n'è nessuno.
  const isZero = match[2] === "0" && !/[1-9]/.test(match[3] ?? "");
  return isZero ? `${integer}${fraction}` : `${sign}${integer}${fraction}`;
}

const UNIT_SUFFIX: Record<ScalarKind, string> = {
  pct: "%",
  eur: " €",
  years: " anni",
  days: " giorni",
  bool: "",
  number: "",
  text: "",
};

const UNIT_WORD: Record<ScalarKind, string> = {
  pct: "per cento",
  eur: "euro",
  years: "anni",
  days: "giorni",
  bool: "",
  number: "",
  text: "",
};

/** L'unità di un campo: la stessa regola che usa il wizard (`FIELD_RULES`), non
 *  una seconda tabella scritta a mano qui accanto. */
export function scalarKindOf(field: string): ScalarKind {
  if (STRING_ASSUMPTION_FIELDS.has(field)) return "text";
  return fieldRule(field)?.kind ?? "number";
}

/** Il testo leggibile di un valore di ipotesi, con le sue quattro verità:
 *  assente, zero, negativo, booleano. Nessuna di esse viene silenziata. */
export function describeScalar(value: AssumptionScalar, kind: ScalarKind): ScalarView {
  if (value === null) {
    return {
      text: "—",
      absent: true,
      negative: false,
      zero: false,
      srText: "nessun valore",
      malformed: false,
    };
  }
  if (typeof value === "boolean") {
    const text = value ? "Sì" : "No";
    return { text, absent: false, negative: false, zero: false, srText: text, malformed: false };
  }
  if (kind === "text") {
    // Una scelta si legge con le parole del wizard; un valore che il wizard non conosce si mostra
    // com'è e si segnala, come un decimale malformato — mai tradotto in una regola a caso.
    const etichetta = ETICHETTE_REGOLA_FIDI[value];
    const text = etichetta ?? value;
    return { text, absent: false, negative: false, zero: false, srText: text, malformed: etichetta === undefined };
  }
  const malformed = !PLAIN_DECIMAL.test(value.trim());
  const base = formatDecimalString(value);
  const numeric = malformed ? null : Number(value);
  const negative = numeric !== null && numeric < 0;
  const zero = numeric !== null && numeric === 0;
  const suffix = kind === "bool" ? "" : UNIT_SUFFIX[kind];
  const unit = kind === "bool" || kind === "number" ? "" : ` ${UNIT_WORD[kind]}`;
  return {
    text: `${base}${suffix}`,
    absent: false,
    negative,
    zero,
    srText: `${base}${unit}`,
    malformed,
  };
}

/** Un numero intero di un contesto non monetario (durata, anni di rimborso). */
export function integerText(value: number): string {
  return thousands(String(Math.trunc(value)));
}

/** «1 anno» / «5 anni»: l'italiano non ha bisogno di un motore di calcolo. */
export function yearsText(value: number): string {
  return value === 1 ? "1 anno" : `${integerText(value)} anni`;
}

/**
 * L'etichetta italiana di una voce forzata da un override (`ce02_override`,
 * `sp09_disponibilita_liquide`, `sp16g`).
 *
 * Il catalogo IV-CEE è l'unica fonte: `labelOf` su un codice che non conosce
 * restituisce il codice, e qui lo si mostra così com'è. Il prefisso viene usato
 * solo se in catalogo c'è UNA SOLA voce con quel prefisso: due candidati
 * significherebbe scegliere un'etichetta a intuito, che è esattamente ciò che le
 * regole d'estrazione vietano (CLAUDE.md › «mai dedurre la parentela fra conti
 * dal prefisso»).
 */
export function overrideFieldLabel(field: string): string {
  const exact = VOCI.find((voce) => voce.code === field);
  if (exact) return labelOf(exact.code);
  const base = field.replace(/_override$/, "");
  if (base !== field) {
    const whole = VOCI.find((voce) => voce.code === base);
    if (whole) return labelOf(whole.code);
  }
  const candidates = VOCI.filter((voce) => voce.code.startsWith(`${base}_`));
  return candidates.length === 1 ? labelOf(candidates[0].code) : field;
}

/** Le cinque posizioni del pregresso, nell'ordine in cui il motore le scandisce. */
export const PREGRESSO_BALANCES: Array<{ key: keyof import("@/types/final-report").Pregresso; label: string }> = [
  { key: "crediti_commerciali", label: "Crediti commerciali" },
  { key: "debiti_fornitori", label: "Debiti fornitori" },
  { key: "debiti_tributari", label: "Debiti tributari" },
  { key: "debiti_previdenziali", label: "Debiti previdenziali" },
  { key: "altri_debiti", label: "Altri debiti" },
];

/** Natura di una differenza temporanea (`deductible` / `taxable`). */
export function temporaryDifferenceKind(kind: "deductible" | "taxable"): string {
  return kind === "deductible" ? "Deducibile" : "Tassabile";
}

/** Scadenza di una differenza temporanea. */
export function temporaryDifferenceMaturity(maturity: "short" | "long"): string {
  return maturity === "short" ? "Breve" : "Lunga";
}

/** Che cosa pilota una voce indicizzata. */
export function indexingDriverLabel(driver: "ricavi" | "acquisti" | "personale"): string {
  return driver === "ricavi" ? "Ricavi" : driver === "acquisti" ? "Acquisti" : "Personale";
}

/** Le colonne di valore di una tabella nidificata, in ordine. */
export function runoffColumnLabels(years: readonly number[]): string[] {
  return years.length > 0 ? years.map((year) => String(year)) : ["Quota 1"];
}

/** La cella-intestazione di riga di una tabella di prospetto: `th scope="row"`,
 *  con il padding di `TableCell` (shadcn qui non offre `asChild`). */
export const ROW_HEAD = "p-2 text-left align-middle font-medium text-foreground";
