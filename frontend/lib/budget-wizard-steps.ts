/** I sette passi del percorso ipotesi (spec 2026-09-08 §4). Modulo puro. */
export type WizardStepKey =
  | "scenario" | "fatturato" | "costi" | "altre-voci-ce"
  | "circolante" | "pregresso-nuovo" | "imposte";

export interface WizardStep {
  n: number; key: WizardStepKey; title: string; subtitle: string;
  group: "Impostazione" | "Conto economico" | "Stato patrimoniale";
}

export const WIZARD_STEPS: readonly WizardStep[] = [
  { n: 1, key: "scenario", title: "Scenario", subtitle: "nome, anno base, orizzonte", group: "Impostazione" },
  { n: 2, key: "fatturato", title: "Fatturato", subtitle: "ricavi e altri ricavi", group: "Conto economico" },
  { n: 3, key: "costi", title: "Costi principali", subtitle: "quota fissa e variabile", group: "Conto economico" },
  { n: 4, key: "altre-voci-ce", title: "Altre voci CE", subtitle: "voci minori e automatiche", group: "Conto economico" },
  { n: 5, key: "circolante", title: "Capitale circolante", subtitle: "giorni medi", group: "Stato patrimoniale" },
  { n: 6, key: "pregresso-nuovo", title: "Pregresso e nuovo", subtitle: "debiti, finanziamenti, investimenti", group: "Stato patrimoniale" },
  { n: 7, key: "imposte", title: "Imposte", subtitle: "aliquota e pagamento", group: "Stato patrimoniale" },
];

export const STEP_FIELDS: Record<WizardStepKey, readonly string[]> = {
  scenario: [],
  fatturato: ["revenue_growth_pct", "other_revenue_growth_pct"],
  costi: [
    "fixed_materials_percentage", "fixed_services_percentage",
    "variable_materials_growth_pct", "variable_services_growth_pct",
    "fixed_materials_growth_pct", "fixed_services_growth_pct",
    "personnel_growth_pct", "rent_growth_pct",
  ],
  "altre-voci-ce": ["other_costs_growth_pct"],
  circolante: [
    "dso_days", "dio_days", "dpo_days", "receivables_long_growth_pct",
    "sp01_growth_pct", "sp04_growth_pct", "sp06e_growth_pct", "sp06f_growth_pct",
    "sp08_growth_pct", "sp10_growth_pct", "sp14_growth_pct", "sp16f_growth_pct",
    "sp16g_growth_pct", "sp17d_growth_pct", "sp17f_growth_pct", "sp17g_growth_pct",
    "sp18_growth_pct", "previdenza_scales_with_personnel", "tfr_accrual_suspended",
  ],
  "pregresso-nuovo": [
    "existing_debt_repayment_years", "altri_finanz_repayment_years", "financing_loans",
    "financing_amount", "financing_duration_years", "financing_interest_rate",
    "tangible_investments", "intangible_investments",
    "depreciation_rate", "depreciation_rate_intangible",
    "asset_disposal_nbv", "asset_disposal_proceeds", "cash_sweep_enabled", "cash_sweep_min_cash",
  ],
  imposte: ["tax_rate", "tax_advances_paid", "tax_temporary_differences", "sp16e_growth_pct", "sp17e_growth_pct"],
};

/**
 * Colonne che il motore non legge e che nessun passo mostra. Le prime tre
 * (`investments`, `receivables_short_growth_pct`, `payables_short_growth_pct`)
 * sono fra le 87 chiavi idratate e rispedite dal salvataggio; le due
 * `interest_rate_*` NON lo sono — esistono nel tipo ma non passano da
 * `hydrateAssumptions`, quindi non fanno neppure il giro.
 */
export const DEAD_FIELDS = [
  "investments", "receivables_short_growth_pct", "payables_short_growth_pct",
  "interest_rate_receivables", "interest_rate_payables",
] as const;

export interface WizardStepGroup { group: WizardStep["group"]; steps: WizardStep[] }

/** Raggruppa per identita' di `group`, non per vicinanza nell'elenco: due
 *  passi con lo stesso `group` finiscono nello stesso gruppo anche se un
 *  passo di un altro gruppo li separa. L'ordine dei gruppi e' quello della
 *  prima comparsa. */
export function groupWizardSteps(steps: readonly WizardStep[]): WizardStepGroup[] {
  const byGroup = new Map<WizardStep["group"], WizardStep[]>();
  for (const step of steps) {
    const existing = byGroup.get(step.group);
    if (existing) existing.push(step);
    else byGroup.set(step.group, [step]);
  }
  return Array.from(byGroup, ([group, groupSteps]) => ({ group, steps: groupSteps }));
}

export function primaryLabel(step: WizardStepKey): string {
  return step === "imposte" ? "Salva e calcola previsionale" : "Avanti";
}

export function stepForErrorMessage(message: string): WizardStepKey {
  return /unfunded financing requirement/i.test(message) ? "pregresso-nuovo" : "imposte";
}

export function stepStorageKey(scenarioId: number): string {
  return `budget-wizard-step:${scenarioId}`;
}

/**
 * Il sottotitolo del passo: i testi del prototipo
 * (`docs/superpowers/specs/2026-09-08-percorso-ipotesi-budget-prototipo.html`,
 * i `<p class="lead">`), con l'anno base vero al posto del 2025 scritto a
 * mano nel prototipo — su uno scenario che parte da un altro anno la frase
 * affermerebbe il contrario di cio' che si legge a schermo.
 */
export function stepLead(step: WizardStepKey, baseYear: number): string {
  switch (step) {
    case "scenario":
      return `Da dove parte il piano e quanto lontano guarda. Tutto il resto si misura rispetto al bilancio ${baseYear}.`;
    case "fatturato":
      return "Quanto crescono i ricavi, anno per anno. Tutti i costi variabili del passo successivo seguono questa curva.";
    case "costi":
      return "Materie prime, servizi, personale e godimento beni di terzi: l'87% dei costi operativi. Prima quanto è fisso, poi come si muove.";
    case "altre-voci-ce":
      return "Le voci minori e quelle che il piano calcola da solo. Modifica solo ciò che ti serve.";
    case "circolante":
      return `Giorni medi di incasso, giacenza e pagamento. Vuoto significa «come nel ${baseYear}».`;
    case "pregresso-nuovo":
      return "A sinistra il bilancio che c'è già e come si scadenzia. A destra quello che il piano genera. Non si mescolano.";
    case "imposte":
      return "Calcolate dal piano sull'utile ante imposte. Correggi l'aliquota o il modo in cui i debiti tributari vengono pagati.";
  }
}

/** La riga di posizione della barra in basso. L'ultimo passo dice dove si
 *  atterra dopo il calcolo, invece di ripetere il proprio titolo. */
export function stepFooterHint(step: WizardStepKey): string {
  const s = WIZARD_STEPS.find((w) => w.key === step);
  if (!s) return "";
  return step === "imposte"
    ? `Passo ${s.n} di ${WIZARD_STEPS.length} · dopo il calcolo vai in CE Prev. e SP Prev. per i correttivi finali`
    : `Passo ${s.n} di ${WIZARD_STEPS.length} · ${s.title}`;
}

/**
 * Il passo ricordato in `localStorage`, o `null`. Una chiave assente, un
 * valore scritto da una versione precedente o una stringa qualsiasi non
 * devono aprire il wizard su un passo che non esiste: si torna al primo.
 */
export function parseStoredStep(raw: string | null | undefined): WizardStepKey | null {
  return raw != null && (ORDER as string[]).includes(raw) ? (raw as WizardStepKey) : null;
}

export interface WizardChrome {
  /** La barra fissa in fondo al wizard. */
  bottomBar: boolean;
  /** «Annulla» e «Indietro» resi in testa al passo, accanto al titolo. */
  headerControls: boolean;
  /** Il primario («Avanti» / «Salva e calcola») reso dal wizard. */
  primaryButton: boolean;
  /** La classe del contenitore: spazio in fondo solo se la barra fissa c'e'. */
  containerClass: string;
}

/**
 * Quali comandi rende il wizard, e dove.
 *
 * Misurato nel browser: dentro una pratica ci sono DUE barre ancorate a
 * `bottom: 0`. Quella della pratica (`PraticaActionBar`, `sticky`, z-index
 * 30) parte 4 px piu' in alto, e' 4 px piu' alta e sta sopra quella del
 * wizard (`fixed`, z-index 10), coprendola per intero:
 * `document.elementFromPoint` al centro del pulsante «Indietro» del wizard
 * restituisce l'«Avanti» della pratica. Non e' un difetto estetico —
 * l'utente vede scritto «Indietro» e premendo **esce dal passo Budget e
 * avanza il percorso**, sulla via d'ingresso normale.
 *
 * Dentro la pratica il wizard quindi non rende la propria barra: il primario
 * lo registra gia' in `usePrimaryAction`, e la barra della pratica lo mostra.
 * «Annulla» e «Indietro» non hanno un equivalente li', quindi risalgono in
 * testa al passo, accanto al titolo, dove nulla li copre. Fuori dalla pratica
 * (navigazione diretta su `/budget`) la barra del wizard e' l'unica e resta.
 *
 * `containerClass` segue la stessa decisione: il `pb-24` serve solo a non
 * farsi coprire l'ultima riga dalla barra `fixed` del wizard. La barra della
 * pratica e' `sticky`, resta in flusso e non copre nulla.
 */
export function wizardChrome(inPratica: boolean): WizardChrome {
  return inPratica
    ? { bottomBar: false, headerControls: true, primaryButton: false, containerClass: "" }
    : { bottomBar: true, headerControls: false, primaryButton: true, containerClass: "pb-24" };
}

/** La forma che interessa della risposta del bulk delle assumptions. */
export interface BulkSaveResult {
  forecast_generated?: boolean;
  message?: string | null;
}

export interface SaveOutcome {
  /** Il previsionale e' stato davvero generato. */
  ok: boolean;
  /** Il testo del toast, che sia di successo o di errore. */
  message: string;
  /** Il passo su cui portare l'utente, o `null` per restare dov'e'. */
  step: WizardStepKey | null;
  /**
   * La rotta su cui atterrare (e il segnale per invalidare le query), oppure
   * `null` se non si naviga.
   *
   * E' un CAMPO — e una stringa nullable, non un booleano — di proposito. La
   * navigazione dopo un previsionale rifiutato (toast verde su una colonna
   * Proiezione vuota) e' il difetto piu' costoso documentato in CLAUDE.md, ed
   * era rimediabile togliendo un `return` dal componente senza far cadere un
   * test. Ora la condizione sta qui, con la sua prova; e nel componente
   * `router.push(esito.route)` **non compila** senza il suo guardiano,
   * perche' `string | null` non e' una rotta.
   */
  route: string | null;
}

/** Dove si atterra dopo un previsionale generato: il CE previsionale, dove si
 *  leggono e si ritoccano i numeri appena calcolati. */
export const ROUTE_DOPO_CALCOLO = "/forecast/income";

/**
 * Che cosa e' successo davvero al salvataggio, e che cosa fare di conseguenza.
 *
 * `PUT /scenarios/{id}/assumptions` risponde **200 anche quando il
 * previsionale e' stato rifiutato** (CLAUDE.md § Previsionale): la verita' e'
 * in `forecast_generated`, la ragione in `message`. Leggere l'HTTP 200
 * dipinge una colonna Proiezione vuota sotto un toast verde — ed e' per
 * questo che la decisione sta qui, con la sua prova, e non dentro il
 * componente.
 *
 * Solo un `false` esplicito e' un rifiuto: un campo assente non e' una
 * negazione, e trattarlo come tale bloccherebbe un salvataggio riuscito.
 */
export function saveOutcome(result: BulkSaveResult | null | undefined): SaveOutcome {
  if (!result || result.forecast_generated !== false) {
    return { ok: true, message: "Previsionale calcolato", step: null, route: ROUTE_DOPO_CALCOLO };
  }
  const message = result.message?.trim() ? result.message.trim() : "Previsionale non generato";
  return { ok: false, message, step: stepForErrorMessage(message), route: null };
}

const ORDER = WIZARD_STEPS.map((s) => s.key);

export function nextStep(step: WizardStepKey): WizardStepKey | null {
  const i = ORDER.indexOf(step);
  return i >= 0 && i < ORDER.length - 1 ? ORDER[i + 1] : null;
}

export function prevStep(step: WizardStepKey): WizardStepKey | null {
  const i = ORDER.indexOf(step);
  return i > 0 ? ORDER[i - 1] : null;
}

/**
 * I passi dal primo fino a quello dato, compreso.
 *
 * Serve al ripristino: chi torna su uno scenario e riapre al passo 7 ci e'
 * arrivato passando per gli altri sei. Segnare come visitato il solo passo
 * ripristinato mostrerebbe sei pallini grigi accanto a un settimo attivo —
 * la guida direbbe il contrario di dove si trova l'utente.
 */
export function stepsUpTo(step: WizardStepKey): WizardStepKey[] {
  const i = ORDER.indexOf(step);
  return i < 0 ? [ORDER[0]] : ORDER.slice(0, i + 1);
}
