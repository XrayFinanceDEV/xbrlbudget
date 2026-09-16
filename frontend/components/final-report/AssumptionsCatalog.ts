/**
 * Le decisioni «di catalogo» del blocco ipotesi: quali sette sezioni si rendono,
 * in quale ordine, come si allineano i valori per anno, e che cosa dire quando
 * il payload non è un `FinalReportModel` v1 leggibile.
 *
 * Modulo puro (nessun React): è qui che vive ciò che i test devono verificare,
 * secondo la regola di §5 del piano — «le decisioni testabili restano in moduli
 * puri». Il componente sotto si limita a restituirla.
 *
 * L'ordine delle sezioni non è scritto a mano: viene da
 * `contracts/final_report_assumption_sections.json`, la stessa fonte che valida
 * il modello lato backend (`backend/app/schemas/final_report.py`). Una seconda
 * lista copiata qui divergerebbe alla prima sezione nuova, e il report ne
 * mostrerebbe sei con la stessa sicurezza di sette.
 */
import {
  ASSUMPTION_SECTION_CATALOG,
  FINAL_REPORT_SCHEMA_VERSION,
  isFinalReportModel,
  type AssumptionScalar,
  type AssumptionSection,
  type AssumptionSectionKey,
  type AssumptionValue,
  type FinalReportModel,
} from "@/types/final-report";
import { DEAD_FIELDS } from "@/lib/budget-wizard-steps";

/** Le sette chiavi canoniche, nell'ordine del catalogo. */
export const CANONICAL_SECTION_KEYS: readonly AssumptionSectionKey[] = ASSUMPTION_SECTION_CATALOG.map(
  (section) => section.key,
);

/** Il titolo italiano di una sezione: vince quello del payload (§6.1 vuole
 *  identificatori stabili separati dalle etichette), il catalogo è il ripiego. */
export function sectionTitle(key: AssumptionSectionKey, payloadTitle?: string): string {
  if (payloadTitle && payloadTitle.trim() !== "") return payloadTitle;
  const entry = ASSUMPTION_SECTION_CATALOG.find((section) => section.key === key);
  return entry ? entry.title : `Sezione ${key}`;
}

export interface SectionLayout {
  /** Le sette sezioni canoniche, nell'ordine del catalogo, coi loro valori. */
  sections: Array<{ key: AssumptionSectionKey; title: string; assumptions: AssumptionValue[] }>;
  /** Chiavi del payload che il catalogo non conosce: si dichiarano, non si eliminano. */
  unknown: Array<{ key: string; title: string; assumptions: AssumptionValue[] }>;
  /** Chiavi canoniche che il payload non porta: la sezione vuota si rende lo stesso. */
  missing: AssumptionSectionKey[];
  /** Una chiave arrivata due volte: la seconda non cancella la prima, si dichiara. */
  duplicates: AssumptionSectionKey[];
}

/**
 * Riordina le sezioni del payload secondo il catalogo, e dichiara tutto ciò che
 * il catalogo non prevedeva: sezione sconosciuta, assente, duplicata.
 */
export function layoutSections(sections: readonly AssumptionSection[]): SectionLayout {
  const byKey = new Map<string, AssumptionSection[]>();
  for (const section of sections) {
    const list = byKey.get(section.key) ?? [];
    list.push(section);
    byKey.set(section.key, list);
  }

  const layout: SectionLayout = { sections: [], unknown: [], missing: [], duplicates: [] };
  for (const key of CANONICAL_SECTION_KEYS) {
    const found = byKey.get(key) ?? [];
    if (found.length > 1) layout.duplicates.push(key);
    if (found.length === 0) layout.missing.push(key);
    layout.sections.push({
      key,
      title: sectionTitle(key, found[0]?.title),
      assumptions: found.flatMap((section) => section.assumptions),
    });
    byKey.delete(key);
  }
  for (const leftover of byKey.values()) {
    for (const section of leftover) {
      layout.unknown.push({ key: section.key, title: section.title, assumptions: section.assumptions });
    }
  }
  return layout;
}

export interface YearColumn {
  year: number | null;
  /** Etichetta di colonna: l'anno, oppure la sua assenza dichiarata. */
  label: string;
  /** Colonna aggiunta perché il payload porta più valori che anni di previsione. */
  extra: boolean;
}

/**
 * Le colonne di una sezione: gli anni dell'orizzonte e, se una riga ne porta di
 * più, una colonna «anno non dichiarato» per ciascuno.
 *
 * Le colonne si decidono una volta per la sezione intera: una tabella dove una
 * riga ha cinque celle e un'altra ne ha tre non è una tabella, è un elenco di
 * righe che condividono il caso.
 */
export function sectionColumns(
  assumptions: readonly AssumptionValue[],
  years: readonly number[],
): YearColumn[] {
  const widest = assumptions.reduce((max, assumption) => Math.max(max, assumption.values.length), years.length);
  const columns: YearColumn[] = years.map((year) => ({ year, label: String(year), extra: false }));
  for (let index = years.length; index < widest; index += 1) {
    columns.push({ year: null, label: `Anno non dichiarato (${index + 1})`, extra: true });
  }
  return columns;
}

export interface ScalarCellView {
  value: AssumptionScalar;
  /** La colonna esiste, il valore no: «—», non 0, e non una cella in meno. */
  absent: boolean;
}

/** Una cella per colonna, allineata per indice. */
export function rowCells(
  values: readonly AssumptionScalar[],
  columns: readonly YearColumn[],
): ScalarCellView[] {
  return columns.map((_, index) =>
    index < values.length ? { value: values[index], absent: false } : { value: null, absent: true },
  );
}

/** Un campo che il wizard considera inerte: nessun suo valore è un pilota attivo. */
export function isDeadField(field: string): boolean {
  return (DEAD_FIELDS as readonly string[]).includes(field);
}

/** Le tabelle nidificate del contratto v1, valorizzate. */
export type NestedTable =
  | { kind: "financing_loans"; rows: NonNullable<AssumptionValue["financing_loans"]> }
  | { kind: "financing_repayments"; rows: NonNullable<AssumptionValue["financing_loans"]> }
  | { kind: "pregresso"; plan: NonNullable<AssumptionValue["pregresso"]> }
  | { kind: "temporary_differences"; rows: NonNullable<AssumptionValue["temporary_differences"]> }
  | { kind: "ce_overrides"; rows: NonNullable<AssumptionValue["ce_overrides"]> }
  | { kind: "sp_overrides"; rows: NonNullable<AssumptionValue["sp_overrides"]> }
  | { kind: "sp_indexing"; rows: NonNullable<AssumptionValue["sp_indexing"]> }
  | { kind: "other_lenders"; rows: NonNullable<AssumptionValue["other_lenders"]> }
  | { kind: "other_lender_repayments"; rows: NonNullable<AssumptionValue["other_lenders"]> };

/**
 * Le tabelle nidificate di una riga, in ordine canonico.
 *
 * Il contratto ne ammette una sola per riga; se il payload ne porta più di una
 * si rendono tutte: silenziare un `pregresso` perchée è arrivato accanto a uno
 * `sp_overrides` vorrebbe dire nascondere un piano di rientro.
 */
export function nestedTablesOf(assumption: AssumptionValue): NestedTable[] {
  const tables: NestedTable[] = [];
  if (assumption.financing_loans != null) {
    tables.push({ kind: "financing_loans", rows: assumption.financing_loans });
    if (assumption.financing_loans.some((loan) => loan.repayments != null)) {
      tables.push({ kind: "financing_repayments", rows: assumption.financing_loans });
    }
  }
  if (assumption.pregresso != null) tables.push({ kind: "pregresso", plan: assumption.pregresso });
  if (assumption.temporary_differences != null) {
    tables.push({ kind: "temporary_differences", rows: assumption.temporary_differences });
  }
  if (assumption.ce_overrides != null) tables.push({ kind: "ce_overrides", rows: assumption.ce_overrides });
  if (assumption.sp_overrides != null) tables.push({ kind: "sp_overrides", rows: assumption.sp_overrides });
  if (assumption.sp_indexing != null) tables.push({ kind: "sp_indexing", rows: assumption.sp_indexing });
  if (assumption.other_lenders != null) {
    tables.push({ kind: "other_lenders", rows: assumption.other_lenders });
    tables.push({ kind: "other_lender_repayments", rows: assumption.other_lenders });
  }
  return tables;
}

/** Una tabella nidificata del contratto v1 è valorizzata. */
export function hasNestedTable(assumption: AssumptionValue): boolean {
  return (
    assumption.financing_loans != null ||
    assumption.pregresso != null ||
    assumption.temporary_differences != null ||
    assumption.ce_overrides != null ||
    assumption.sp_indexing != null ||
    assumption.sp_overrides != null ||
    assumption.other_lenders != null
  );
}

/** Lo stato dichiarativo di una riga: una parola, non un colore. */
export interface RowState {
  text: string;
  level: "info" | "warning";
}

/**
 * Che cosa una riga dice di sé, oltre al valore.
 *
 * Un campo `ignored`, una riga `active: false` e un `DEAD_FIELD` sono tre cose
 * diverse e non vanno confuse con un valore «normale»: §6.4 vuole che i campi
 * inerti non appaiano come piloti attivi, e il contratto li manda comunque
 * (`provenance: "ignored"`) perché il report li mostri come non usati.
 */
export function assumptionRowState(assumption: AssumptionValue): RowState | null {
  if (isDeadField(assumption.field)) {
    return { text: "Campo inerte: il motore non lo legge, non è un pilota attivo.", level: "warning" };
  }
  if (assumption.provenance === "ignored") {
    return { text: "Non usato nel percorso corrente.", level: "warning" };
  }
  if (!assumption.active) {
    return { text: "Riga non attiva in questo scenario.", level: "info" };
  }
  if (hasNestedTable(assumption)) {
    return { text: "Dettaglio nella tabella sotto.", level: "info" };
  }
  return null;
}

export type SchemaVerdict =
  | { ok: true; model: FinalReportModel }
  | { ok: false; kind: "unknown"; message: string }
  | { ok: false; kind: "malformed"; message: string };

/**
 * Il confine del renderer: §5.2 vuole che una versione diversa si rifiuti, non
 * che si renda a metà. Il messaggio porta il numero di versione letto, perché
 * «documento non supportato» senza dato è un «non lo so» travestito da verdetto.
 */
export function readFinalReport(payload: unknown, context: string): SchemaVerdict {
  if (payload === null || payload === undefined) {
    return { ok: false, kind: "malformed", message: `${context}: nessun modello ricevuto.` };
  }
  if (typeof payload === "object" && !Array.isArray(payload) && "schema_version" in payload) {
    const version = (payload as { schema_version?: unknown }).schema_version;
    if (version !== FINAL_REPORT_SCHEMA_VERSION) {
      return {
        ok: false,
        kind: "unknown",
        message: `Schema versione ${String(version)}: questo renderer conosce solo la v${FINAL_REPORT_SCHEMA_VERSION}.`,
      };
    }
  }
  if (!isFinalReportModel(payload)) {
    return {
      ok: false,
      kind: "malformed",
      message: `${context}: il payload dichiara la v${FINAL_REPORT_SCHEMA_VERSION} ma non ne rispetta il contratto.`,
    };
  }
  return { ok: true, model: payload };
}
