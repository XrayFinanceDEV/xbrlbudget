// Catalogo IV-CEE: una riga per ogni voce di bilancio (SP e CE), con padre,
// sezione, ordine ed etichette a due ruoli (autonoma / contestuale).
//
// Nessun dato è inventato: tutto è ricavato dalle fonti esistenti.
//  - quali codici + ordine fra pari: RETTIFICHE_BS_ATTIVO / RETTIFICHE_BS_PN /
//    RETTIFICHE_BS_OTHER_PASSIVO / DEBT_GROUPS / CE_A..CE_IMPOSTE
//    (lib/pratica-rettifiche-rules.ts). ATTENZIONE: Rettifiche NON è, come si
//    era supposto, l'elenco più completo dei sei. Mancano:
//      * quattro aggregati di primo livello (sp12_riserve, sp16_debiti_breve,
//        sp17_debiti_lungo, sp18_ratei_risconti_passivi), che Rettifiche non
//        rende come righe editabili ma ATTIVO_CODES/PASSIVO_CODES richiedono;
//      * cinque voci che altre viste pinnate rendono davvero (sp14a..sp14d e
//        ce03a_incrementi_immobilizzazioni) — vedi VOCI_NON_IN_RETTIFICHE.
//  - il padre: DETAIL_PARENTS (lib/pratica-codes.ts), più EXTRA_PARENTS per le
//    voci che quella mappa non copre. Assente = voce di primo livello.
//  - la sezione: ATTIVO_CODES per l'attivo (e le sue sotto-voci); sp11/sp12*/
//    sp13 per il patrimonio netto; il resto degli sp per il passivo; ce* per
//    il conto economico.
//  - le etichette: vedi labelFor() più sotto — COUNTERPART_PICKER_LABELS vince
//    per ognuna delle sue chiavi: sono tutti sotto-conti la cui grafia breve
//    del Confronto (es. "1) Verso clienti", "entro 12 mesi") non distingue
//    entro/oltre né la voce padre senza un'intestazione sopra; altrimenti
//    vince la grafia del Confronto (CONFRONTO_RELABEL, copiata dalle mappe
//    `relabel` interne — non esportate — di lib/pratica-statement-rows.ts,
//    righe 52 e 341); RETTIFICHE_LABELS è l'ultima risorsa per i pochi codici
//    che il Confronto non rietichetta (sp05a..sp05e, sp12_riserve); infine
//    EXTRA_LABELS per le cinque voci che nessuna di quelle mappe nomina.

import {
  RETTIFICHE_LABELS,
  COUNTERPART_PICKER_LABELS,
  RETTIFICHE_BS_ATTIVO,
  RETTIFICHE_BS_PN,
  RETTIFICHE_BS_OTHER_PASSIVO,
  DEBT_GROUPS,
  CE_A,
  CE_B,
  CE_C,
  CE_D,
  CE_E,
  CE_IMPOSTE,
} from "./pratica-rettifiche-rules";
import { DETAIL_PARENTS, ATTIVO_CODES, PASSIVO_CODES } from "./pratica-codes";

export type IvceeSection = "attivo" | "passivo" | "patrimonio" | "ce";

export interface Voce {
  code: string;
  /** codice dell'aggregato che la contiene; null per una voce di primo livello */
  parent: string | null;
  section: IvceeSection;
  /** ordine fra pari sotto lo stesso padre */
  order: number;
  /** auto-esplicativa: usabile senza contesto (giornale, selettore, dialoghi) */
  label: string;
  /** breve: presuppone l'intestazione sopra. Assente = usa `label`. */
  shortLabel?: string;
}

// ===== Grafia del Confronto (relabel), copiata da lib/pratica-statement-rows.ts =====
// Le due mappe `relabel` locali lì (BS riga 52, CE riga 341) non sono esportate;
// questa è una copia letterale, senza i rientri (" 1) ..." → "1) ..."), che qui
// vengono strippati a runtime con .trim() per sicurezza.
// La copia è tenuta allineata alle mappe vive dal test
// "la copia della grafia del Confronto non è andata alla deriva"
// (lib/ivcee-catalog-parity.test.ts), che rilegge il sorgente: senza quel test
// una modifica alle mappe durante i Task 3-8 renderebbe il catalogo sbagliato
// in silenzio. Test e copia muoiono insieme alle mappe (Task 7/9).
const CONFRONTO_RELABEL: Record<string, string> = {
  // BS — da pratica-statement-rows.ts riga 52
  sp01_crediti_soci: "A) Crediti verso soci per versamenti ancora dovuti",
  sp02_immob_immateriali: "I - Immobilizzazioni immateriali",
  sp03_immob_materiali: "II - Immobilizzazioni materiali",
  sp04_immob_finanziarie: "III - Immobilizzazioni finanziarie",
  sp04a_partecipazioni: "1) Partecipazioni",
  sp04b_crediti_immob_breve: "2) Crediti (entro es. successivo)",
  sp04c_crediti_immob_lungo: "2) Crediti (oltre es. successivo)",
  sp04d_altri_titoli: "3) Altri titoli",
  sp04e_strumenti_derivati_attivi: "4) Strumenti finanziari derivati attivi",
  sp05_rimanenze: "I - Rimanenze",
  sp06_crediti_breve: "II - Crediti (entro esercizio successivo)",
  sp06a_crediti_clienti_breve: "1) Verso clienti",
  sp06b_crediti_controllate_breve: "2) Verso imprese controllate",
  sp06c_crediti_collegate_breve: "3) Verso imprese collegate",
  sp06d_crediti_controllanti_breve: "4) Verso controllanti",
  sp06e_crediti_tributari_breve: "5-bis) Crediti tributari",
  sp06f_imposte_anticipate_breve: "5-ter) Imposte anticipate",
  sp06g_crediti_altri_breve: "5-quater) Verso altri",
  sp07_crediti_lungo: "II - Crediti (oltre esercizio successivo)",
  sp07a_crediti_clienti_lungo: "1) Verso clienti",
  sp07b_crediti_controllate_lungo: "2) Verso imprese controllate",
  sp07c_crediti_collegate_lungo: "3) Verso imprese collegate",
  sp07d_crediti_controllanti_lungo: "4) Verso controllanti",
  sp07e_crediti_tributari_lungo: "5-bis) Crediti tributari",
  sp07f_imposte_anticipate_lungo: "5-ter) Imposte anticipate",
  sp07g_crediti_altri_lungo: "5-quater) Verso altri",
  sp08_attivita_finanziarie: "III - Attività finanziarie che non costituiscono immobilizzazioni",
  sp09_disponibilita_liquide: "IV - Disponibilità liquide",
  sp10_ratei_risconti_attivi: "D) Ratei e risconti attivi",
  sp11_capitale: "I - Capitale",
  sp12a_riserva_sovrapprezzo: "II - Riserva da soprapprezzo delle azioni",
  sp12b_riserve_rivalutazione: "III - Riserve di rivalutazione",
  sp12c_riserva_legale: "IV - Riserva legale",
  sp12d_riserve_statutarie: "V - Riserve statutarie",
  sp12e_altre_riserve: "VI - Altre riserve",
  sp12f_riserva_copertura_flussi: "VII - Riserva per copertura flussi finanziari",
  sp12g_utili_perdite_portati: "VIII - Utili (perdite) portati a nuovo",
  sp13_utile_perdita: "IX - Utile (perdita) dell'esercizio",
  sp12h_riserva_neg_azioni_proprie: "X - Riserva negativa per azioni proprie",
  sp14_fondi_rischi: "B) Fondi per rischi e oneri",
  sp15_tfr: "C) Trattamento di fine rapporto di lavoro subordinato",
  sp16_debiti_breve: "Debiti (entro esercizio successivo)",
  sp16a_debiti_banche_breve: "entro 12 mesi",
  sp16b_debiti_altri_finanz_breve: "entro 12 mesi",
  sp16c_debiti_obbligazioni_breve: "entro 12 mesi",
  sp16d_debiti_fornitori_breve: "entro 12 mesi",
  sp16e_debiti_tributari_breve: "entro 12 mesi",
  sp16f_debiti_previdenza_breve: "entro 12 mesi",
  sp16g_altri_debiti_breve: "entro 12 mesi",
  sp17_debiti_lungo: "Debiti (oltre esercizio successivo)",
  sp17a_debiti_banche_lungo: "oltre 12 mesi",
  sp17b_debiti_altri_finanz_lungo: "oltre 12 mesi",
  sp17c_debiti_obbligazioni_lungo: "oltre 12 mesi",
  sp17d_debiti_fornitori_lungo: "oltre 12 mesi",
  sp17e_debiti_tributari_lungo: "oltre 12 mesi",
  sp17f_debiti_previdenza_lungo: "oltre 12 mesi",
  sp17g_altri_debiti_lungo: "oltre 12 mesi",
  sp18_ratei_risconti_passivi: "E) Ratei e risconti passivi",
  // CE — da pratica-statement-rows.ts riga 341
  ce01_ricavi_vendite: "1) Ricavi delle vendite e delle prestazioni",
  ce02_variazioni_rimanenze: "2) Var. rimanenze di prodotti in c/lav., semilav. e finiti",
  ce03_lavori_interni: "4) Incrementi di immobilizzazioni per lavori interni",
  ce04_altri_ricavi: "5) Altri ricavi e proventi",
  ce05_materie_prime: "6) Per materie prime, sussidiarie, di consumo e di merci",
  ce06_servizi: "7) Per servizi",
  ce07_godimento_beni: "8) Per godimento di beni di terzi",
  ce08_costi_personale: "9) Per il personale",
  ce08b_salari_stipendi: "a) Salari e stipendi",
  ce08c_oneri_sociali: "b) Oneri sociali",
  ce08a_tfr_accrual: "c) Trattamento di fine rapporto",
  ce08d_altri_costi_personale: "e) Altri costi del personale",
  ce09_ammortamenti: "10) Ammortamenti e svalutazioni",
  ce09a_ammort_immateriali: "a) Ammortamento immobilizzazioni immateriali",
  ce09b_ammort_materiali: "b) Ammortamento immobilizzazioni materiali",
  ce09c_svalutazioni: "c) Altre svalutazioni delle immobilizzazioni",
  ce09d_svalutazione_crediti: "d) Svalutazione crediti attivo circolante",
  ce10_var_rimanenze_mat_prime: "11) Var. rimanenze di materie prime, suss., di cons. e merci",
  ce11_accantonamenti: "12) Accantonamenti per rischi",
  ce11b_altri_accantonamenti: "13) Altri accantonamenti",
  ce12_oneri_diversi: "14) Oneri diversi di gestione",
  ce13_proventi_partecipazioni: "15) Proventi da partecipazioni",
  ce14_altri_proventi_finanziari: "16) Altri proventi finanziari",
  ce15_oneri_finanziari: "17) Interessi e altri oneri finanziari",
  ce16_utili_perdite_cambi: "17-bis) Utili e perdite su cambi",
  ce17_rettifiche_attivita_fin: "Totale rettifiche di valore (18 - 19)",
  ce17a_rivalutazioni: "18) Rivalutazioni",
  ce17b_svalutazioni: "19) Svalutazioni",
  ce18_proventi_straordinari: "Proventi straordinari",
  ce19_oneri_straordinari: "Oneri straordinari",
  ce20_imposte: "20) Imposte sul reddito dell'esercizio",
};

// ===== Voci rese dalle viste pinnate ma assenti da ogni elenco di Rettifiche =====
// Cinque codici non compaiono in RETTIFICHE_BS_* / DEBT_GROUPS / CE_*, né in
// RETTIFICHE_LABELS, CONFRONTO_RELABEL, COUNTERPART_PICKER_LABELS o
// DETAIL_PARENTS: la catena delle etichette e quella dei padri arrivano vuote.
// Etichetta, padre e ordine relativo sono presi ALLA LETTERA dalla vista che
// già li rende — nessun testo è inventato.

// Dettaglio dei fondi per rischi e oneri: copia letterale del gruppo
// "Fondi per rischi e oneri" di BALANCE_HIERARCHY_GROUPS
// (lib/ivcee-balance-catalog.ts:79-88), che dichiara sia il testo sia
// l'aggregato di appartenenza (`aggregate: "sp14_fondi_rischi"`). Sono righe
// vere del prospetto SP: compaiono in ATTESI_BALANCE, l'invariante pinnata.
// Non si importa da lì per non creare un ciclo quando il Task 4 assorbirà
// quel modulo nel catalogo; la copia è tenuta allineata dal test
// "il dettaglio dei fondi rischi riproduce ivcee-balance-catalog".
const SP14_DETAIL: ReadonlyArray<readonly [string, string]> = [
  ["sp14a_fondi_trattamento_quiescenza", "Quiescenza"],
  ["sp14b_fondi_imposte", "Imposte, anche differite"],
  ["sp14c_strumenti_derivati_passivi", "Derivati passivi"],
  ["sp14d_altri_fondi", "Altri fondi"],
];

// Riga resa da /forecast/income (app/forecast/income/page.tsx:562) e sommata
// nel Valore della Produzione (VP_CODES, lib/pratica-codes.ts:72). `lib/` non
// può importare da `app/`: il testo è copiato, non derivabile con un test.
// Nessuna fonte le assegna un padre, quindi è voce di primo livello
// (regola del brief: fuori da DETAIL_PARENTS ⇒ parent null).
const CE03A_CODE = "ce03a_incrementi_immobilizzazioni";
const CE03A_LABEL = "4) Incrementi di immobilizzazioni per lavori interni";

const EXTRA_LABELS: Record<string, string> = {
  ...Object.fromEntries(SP14_DETAIL),
  [CE03A_CODE]: CE03A_LABEL,
};

const EXTRA_PARENTS: Record<string, string> = Object.fromEntries(
  SP14_DETAIL.map(([code]) => [code, "sp14_fondi_rischi"] as const),
);

function parentOf(code: string): string | null {
  return DETAIL_PARENTS[code] ?? EXTRA_PARENTS[code] ?? null;
}

// L'ultimo `?? code` non è cosmetico: senza di esso un codice che nessuna
// mappa etichetta fa esplodere .trim() su undefined MENTRE si valuta VOCI, cioè
// al caricamento del modulo — ogni pagina che importa il catalogo si rompe. Si
// preferisce la degradazione morbida (stesso contratto di labelOf: mai vuoto)
// perché un'etichetta mancante non deve poter spegnere l'applicazione; il
// difetto è comunque intercettato in CI dal test strutturale
// "nessuna etichetta è il codice stesso".
function labelFor(code: string): { label: string; shortLabel?: string } {
  const relabel = CONFRONTO_RELABEL[code];
  const pickerLabel = COUNTERPART_PICKER_LABELS[code];
  const label = (
    pickerLabel ?? relabel ?? RETTIFICHE_LABELS[code] ?? EXTRA_LABELS[code] ?? code
  ).trim();
  const shortLabel = relabel !== undefined && relabel.trim() !== label ? relabel.trim() : undefined;
  return shortLabel !== undefined ? { label, shortLabel } : { label };
}

// ===== Quali codici, in che ordine =====
// L'elenco di Rettifiche più i 4 aggregati di primo livello e le 5 voci che
// quella vista non rende (vedi commenti in testa al file). Le voci aggiunte
// sono inserite nel punto in cui la vista che le rende le colloca: sp14a..d
// subito dopo sp14_fondi_rischi (BALANCE_HIERARCHY_GROUPS), ce03a fra
// ce03_lavori_interni e ce04_altri_ricavi (app/forecast/income/page.tsx).
const ALL_CODES: string[] = [
  ...RETTIFICHE_BS_ATTIVO,
  ...RETTIFICHE_BS_PN,
  "sp12_riserve",
  ...RETTIFICHE_BS_OTHER_PASSIVO.flatMap((c) =>
    c === "sp14_fondi_rischi" ? [c, ...SP14_DETAIL.map(([code]) => code)] : [c],
  ),
  "sp16_debiti_breve",
  ...DEBT_GROUPS.flatMap((g) => [...g.entro, ...g.oltre]),
  "sp17_debiti_lungo",
  "sp18_ratei_risconti_passivi",
  ...CE_A.flatMap((c) => (c === "ce03_lavori_interni" ? [c, CE03A_CODE] : [c])),
  ...CE_B,
  ...CE_C,
  ...CE_D,
  ...CE_E,
  ...CE_IMPOSTE,
];

function sectionOf(code: string): IvceeSection {
  if (code.startsWith("ce")) return "ce";
  if (/^sp(0[1-9]|10)/.test(code)) return "attivo";
  if (/^sp(11|12|13)/.test(code)) return "patrimonio";
  return "passivo"; // sp14-sp18 e le loro sotto-voci
}

// Voci di primo livello CE, nell'ordine di ALL_CODES (le sotto-voci
// ce08a-d/ce09a-d/ce17a-b hanno un padre e sono escluse qui).
const CE_TOP_LEVEL = ALL_CODES.filter((c) => sectionOf(c) === "ce" && parentOf(c) === null);

function topLevelOrder(code: string, section: IvceeSection): number {
  if (section === "attivo") return ATTIVO_CODES.indexOf(code);
  if (section === "ce") return CE_TOP_LEVEL.indexOf(code);
  return PASSIVO_CODES.indexOf(code); // patrimonio + passivo condividono l'elenco sp11-sp18
}

// L'ordine fra pari si legge da ALL_CODES, non da un pool separato: ALL_CODES
// contiene per costruzione OGNI voce del catalogo e vi si riversano interi gli
// elenchi di origine, quindi filtrarlo per padre restituisce lo stesso ordine
// relativo delle fonti. Un pool parziale (com'era CHILD_POOL) dimenticava
// interi aggregati — sp14, sp18, CE_A, CE_C, CE_E — e i loro figli finivano a
// order -1 senza che nessun test se ne accorgesse.
function childOrder(code: string, parent: string): number {
  const siblings = ALL_CODES.filter((c) => parentOf(c) === parent);
  return siblings.indexOf(code);
}

export const VOCI: readonly Voce[] = ALL_CODES.map((code) => {
  const section = sectionOf(code);
  const parent = parentOf(code);
  const order = parent === null ? topLevelOrder(code, section) : childOrder(code, parent);
  const { label, shortLabel } = labelFor(code);
  return { code, parent, section, order, label, shortLabel };
});

const BY_CODE = new Map(VOCI.map((v) => [v.code, v] as const));

export function voce(code: string): Voce | undefined {
  return BY_CODE.get(code);
}

export function labelOf(code: string, role: "autonoma" | "contestuale" = "autonoma"): string {
  const v = BY_CODE.get(code);
  if (!v) return code;
  return role === "contestuale" ? v.shortLabel ?? v.label : v.label;
}

const CHILDREN = new Map<string, Voce[]>();
for (const v of VOCI) {
  if (v.parent === null) continue;
  const list = CHILDREN.get(v.parent) ?? [];
  list.push(v);
  CHILDREN.set(v.parent, list);
}
for (const list of CHILDREN.values()) list.sort((a, b) => a.order - b.order);

/** I figli diretti di un aggregato, in ordine. */
export function childrenOf(code: string): Voce[] {
  return CHILDREN.get(code) ?? [];
}

/** Il codice e tutta la sua discendenza, in ordine di resa. */
export function subtree(code: string): Voce[] {
  const root = BY_CODE.get(code);
  if (!root) return [];
  const out: Voce[] = [root];
  for (const child of childrenOf(code)) out.push(...subtree(child.code));
  return out;
}

/**
 * Somma le FOGLIE del sottoalbero. Sommare anche i nodi intermedi
 * conterebbe due volte lo stesso importo: un aggregato È la somma dei figli.
 */
export function aggregate(values: Record<string, number>, code: string): number {
  const figli = childrenOf(code);
  if (figli.length === 0) return values[code] ?? 0;
  return figli.reduce((s, f) => s + aggregate(values, f.code), 0);
}

const depthOf = (v: Voce): number => {
  let d = 0;
  let cur = v;
  while (cur.parent !== null) {
    const p = BY_CODE.get(cur.parent);
    if (!p) break;
    cur = p;
    d += 1;
  }
  return d;
};

/** Le voci di una sezione, in ordine di resa, fino alla profondità indicata. */
export function sectionRows(section: IvceeSection, maxDepth?: number): Voce[] {
  const roots = VOCI.filter((v) => v.section === section && v.parent === null)
    .sort((a, b) => a.order - b.order);
  const out: Voce[] = [];
  const walk = (v: Voce) => {
    if (maxDepth !== undefined && depthOf(v) > maxDepth) return;
    out.push(v);
    for (const c of childrenOf(v.code)) walk(c);
  };
  roots.forEach(walk);
  return out;
}
