/**
 * Raggruppamento e etichette della diagnostica del report finale (M1-08B).
 *
 * Modulo puro: nessuna cella JSX. Decide tre cose che i test devono poter
 * controllare senza un browser: l'ordine delle severità, l'etichetta italiana di
 * una sezione del modello, e che fine fanno i valori che l'enumerazione del
 * contratto v1 non prevede.
 *
 * Il principio è quello del file di progetto («Un verdetto negativo vuole una
 * contraddizione, non un controllo assente»): una chiave diagnostica che non
 * arriva è «non lo so», e si dichiara come tale — mai come un elenco pulito.
 */
import type { ComponentType } from "react";
import type { Diagnostic, DiagnosticSeverity } from "@/types/final-report";
import { CircleAlert, Info, TriangleAlert } from "lucide-react";

/** Ordine di lettura: prima ciò che blocca. */
export const SEVERITY_ORDER: readonly DiagnosticSeverity[] = ["error", "warning", "info"];

export interface SeverityView {
  label: string;
  description: string;
  Icon: ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;
  className: string;
  /** ``false`` per una severità che il contratto v1 non enumerà. */
  known: boolean;
}

const SEVERITIES: Record<DiagnosticSeverity, SeverityView> = {
  error: {
    label: "Errore",
    description: "Blocca la finalizzazione del documento.",
    Icon: CircleAlert,
    className: "text-red-700 dark:text-red-400",
    known: true,
  },
  warning: {
    label: "Avviso",
    description: "Non blocca, ma resta da verificare.",
    Icon: TriangleAlert,
    className: "text-amber-700 dark:text-amber-400",
    known: true,
  },
  info: {
    label: "Nota",
    description: "Segnalazione senza effetti sul verdetto.",
    Icon: Info,
    className: "text-sky-700 dark:text-sky-400",
    known: true,
  },
};

/** La resa di una severità. Un valore fuori elenco (payload di un'altra
 *  versione, chiave scritta male) ha una sua voce: non si appoggia a «info»,
 *  che sarebbe il più silenzioso dei ripieghi. */
export function severityView(severity: DiagnosticSeverity | string): SeverityView {
  const view = (SEVERITIES as Record<string, SeverityView | undefined>)[severity];
  if (view) return view;
  return {
    label: "Severità non dichiarata",
    description: `Il valore "${String(severity)}" non è una delle tre severità del contratto v1.`,
    Icon: Info,
    className: "text-foreground",
    known: false,
  };
}

/** Le sezioni che l'assembler usa nella diagnostica, in italiano. Il codice
 *  tecnico resta visibile accanto: è la chiave che si cerca nei log e nei test. */
const SECTION_LABELS: Record<string, string> = {
  assumptions: "Ipotesi del budget",
  adjustments: "Rettifiche",
  chain: "Catena della pratica",
  closing: "Chiusura infrannuale",
  forecast: "Previsionale",
  narrative: "Narrazione",
  sources: "Origine e qualità dei dati",
};

export function sectionLabel(section: string): string {
  return SECTION_LABELS[section] ?? section;
}

export function isKnownSection(section: string): boolean {
  return Object.prototype.hasOwnProperty.call(SECTION_LABELS, section);
}

export interface SectionGroup {
  section: string;
  label: string;
  /** `false` per una sezione che il report non conosca: si rende, non si elimina. */
  known: boolean;
  items: Diagnostic[];
}

export interface SeverityGroup {
  severity: string;
  view: SeverityView;
  /** Una severità che non è delle tre: il gruppo si dichiara, non si fonde. */
  known: boolean;
  count: number;
  sections: SectionGroup[];
}

/**
 * Diagnostica raggruppata per severità e per sezione.
 *
 * L'ordine è deterministico: prima gli errori, poi gli avvisi, poi le note;
 * dentro una severità, le sezioni nell'ordine in cui compaiono nell'elenco —
 * riordinarle per nome farebbe sembrare che il raggruppamento abbia un senso
 * alfabetico che non ha.
 */
export function groupDiagnostics(items: readonly Diagnostic[]): SeverityGroup[] {
  const bySeverity = new Map<string, Diagnostic[]>();
  for (const item of items) {
    const list = bySeverity.get(item.severity) ?? [];
    list.push(item);
    bySeverity.set(item.severity, list);
  }

  const build = (severity: string, known: boolean): SeverityGroup => {
    const list = bySeverity.get(severity) ?? [];
    const sections: SectionGroup[] = [];
    for (const item of list) {
      const existing = sections.find((candidate) => candidate.section === item.section);
      if (existing) existing.items.push(item);
      else {
        sections.push({
          section: item.section,
          label: sectionLabel(item.section),
          known: isKnownSection(item.section),
          items: [item],
        });
      }
    }
    return { severity, view: severityView(severity), known, count: list.length, sections };
  };

  const ordered = SEVERITY_ORDER.filter((severity) => bySeverity.has(severity)).map((severity) =>
    build(severity, true),
  );
  const rest = [...bySeverity.keys()]
    .filter((severity) => !(SEVERITY_ORDER as readonly string[]).includes(severity))
    .map((severity) => build(severity, false));
  return [...ordered, ...rest];
}

/** Il conto per severità, nell'ordine canonico: una riga di riepilogo che non
 *  richiede di leggere l'elenco per sapere se ci sono errori. */
export function severityCounts(
  items: readonly Diagnostic[],
): Array<{ severity: string; view: SeverityView; count: number; known: boolean }> {
  const groups = groupDiagnostics(items);
  const declared = SEVERITY_ORDER.map((severity) => ({
    severity,
    view: severityView(severity),
    count: groups.find((group) => group.severity === severity)?.count ?? 0,
    known: true,
  }));
  const extra = groups
    .filter((group) => !group.known)
    .map((group) => ({ severity: group.severity, view: group.view, count: group.count, known: false }));
  return [...declared, ...extra];
}
