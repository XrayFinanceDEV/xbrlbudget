/**
 * Dalla risposta di POST /preview alle righe dell'anteprima di ogni passo.
 * Solo somme, differenze e percentuali di numeri che il motore ha gia'
 * restituito: qui non si deriva nulla (spec 2026-09-08 §7).
 */
import type { BalanceSheet, ForecastPreviewError, ForecastPreviewYear, IncomeStatement } from "@/types/api";
import type { HistoricalData } from "@/lib/budget-trend";
import { computeAutoDays } from "@/lib/budget-turnover";

export interface PreviewCell { value: number | null; pct?: number | null; days?: number | null; note?: string }
export type PreviewRowKind = "value" | "sub" | "total" | "kpi";
export interface PreviewRow { key: string; label: string; kind: PreviewRowKind; base: PreviewCell; years: PreviewCell[] }

const num = (v: unknown): number => (typeof v === "number" ? v : parseFloat(String(v ?? "0")) || 0);
const pctOf = (v: number | null, den: number): number | null => (v === null || den === 0 ? null : (v / den) * 100);
const row = (key: string, label: string, kind: PreviewRowKind, base: PreviewCell, years: PreviewCell[]): PreviewRow =>
  ({ key, label, kind, base, years });

/**
 * Unico punto del CE ricapitolato: valore della produzione, costi della
 * produzione (per macro-voce) e area finanziaria/straordinaria, con la stessa
 * formula canonica di computeEffectiveTaxRate (assumption-rows.ts) — quella
 * funzione la importa da qui, cosi' la formula esiste in un solo posto.
 */
export function ceAggregates(income: Record<string, unknown>): {
  vp: number; main: number; alt: number; amm: number; fin: number; mol: number; ro: number; ebt: number;
} {
  const g = (k: string) => num(income[k]);
  const vp = g("ce01_ricavi_vendite") + g("ce02_variazioni_rimanenze") + g("ce03_lavori_interni")
    + g("ce03a_incrementi_immobilizzazioni") + g("ce04_altri_ricavi");
  const main = g("ce05_materie_prime") + g("ce06_servizi") + g("ce07_godimento_beni") + g("ce08_costi_personale");
  const alt = g("ce10_var_rimanenze_mat_prime") + g("ce11_accantonamenti") + g("ce12_oneri_diversi");
  const amm = g("ce09_ammortamenti");
  const fin = g("ce13_proventi_partecipazioni") + g("ce14_altri_proventi_finanziari") - g("ce15_oneri_finanziari")
    + g("ce16_utili_perdite_cambi") + g("ce17_rettifiche_attivita_fin")
    + g("ce18_proventi_straordinari") - g("ce19_oneri_straordinari");
  const mol = vp - main - alt;
  const ro = mol - amm;
  const ebt = ro + fin;
  return { vp, main, alt, amm, fin, mol, ro, ebt };
}

/**
 * L'anteprima del passo Scenario (Task 11 §1): niente chiamata a `/preview`,
 * solo un recap del bilancio storico gia' caricato — ricavi, incidenza % di
 * ce05/ce06/ce08 sui ricavi, il MOL semplificato dato dal brief e i giorni
 * `computeAutoDays` per DSO/DIO/DPO. `historicalYears[0]` fa da colonna
 * "base" (il primo anno disponibile in archivio) e il resto degli anni
 * storici, base compreso l'anno base vero e proprio, sono le colonne
 * `years`: nessun anno e' mostrato due volte.
 */
export function rowsAnnoBase(historicalYears: number[], historical: HistoricalData): PreviewRow[] {
  if (historicalYears.length === 0) return [];
  const [primoAnno, ...restoAnni] = historicalYears;
  const baseEntry = historical[primoAnno];
  const restEntries = restoAnni.map((y) => historical[y]);

  const revenueOf = (e: HistoricalData[number] | undefined): number | null => (e ? num(e.income.ce01_ricavi_vendite) : null);

  const incidenceRow = (key: string, label: string, field: keyof IncomeStatement): PreviewRow => {
    const cellFor = (e: HistoricalData[number] | undefined): PreviewCell => {
      if (!e) return { value: null };
      const v = num(e.income[field]);
      return { value: v, pct: pctOf(v, num(e.income.ce01_ricavi_vendite)) };
    };
    return row(key, label, "value", cellFor(baseEntry), restEntries.map(cellFor));
  };

  // MOL = ce01+ce04-ce05-ce06-ce07-ce08-ce12 (Task 11 §1): la formula del
  // brief, piu' semplice della cascata di ceAggregates perche' qui non c'e'
  // bisogno di scorporare rimanenze/accantonamenti dal solo storico.
  const molOf = (e: HistoricalData[number] | undefined): number | null => {
    if (!e) return null;
    const i = e.income;
    return num(i.ce01_ricavi_vendite) + num(i.ce04_altri_ricavi) - num(i.ce05_materie_prime)
      - num(i.ce06_servizi) - num(i.ce07_godimento_beni) - num(i.ce08_costi_personale) - num(i.ce12_oneri_diversi);
  };

  const daysRow = (key: string, label: string, kind: "dso" | "dio" | "dpo"): PreviewRow => {
    const cellFor = (e: HistoricalData[number] | undefined): PreviewCell =>
      ({ value: null, days: e ? computeAutoDays(kind, e.income, e.balance) : null });
    return row(key, label, "value", cellFor(baseEntry), restEntries.map(cellFor));
  };

  return [
    row("ricavi", "Ricavi delle vendite", "kpi",
      { value: revenueOf(baseEntry) }, restEntries.map((e) => ({ value: revenueOf(e) }))),
    incidenceRow("ce05", "Materie prime", "ce05_materie_prime"),
    incidenceRow("ce06", "Servizi", "ce06_servizi"),
    incidenceRow("ce08", "Personale", "ce08_costi_personale"),
    row("mol", "MOL", "kpi", { value: molOf(baseEntry) }, restEntries.map((e) => ({ value: molOf(e) }))),
    daysRow("dso", "Giorni incasso clienti (DSO)", "dso"),
    daysRow("dio", "Giorni rotazione magazzino (DIO)", "dio"),
    daysRow("dpo", "Giorni pagamento fornitori (DPO)", "dpo"),
  ];
}

export function rowsFatturato(baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[] {
  const b01 = num(baseInc.ce01_ricavi_vendite), b04 = num(baseInc.ce04_altri_ricavi);
  const bVp = ceAggregates(baseInc as unknown as Record<string, unknown>).vp;
  let prev01 = b01, prev04 = b04;
  const r01: PreviewCell[] = [], d01: PreviewCell[] = [], r04: PreviewCell[] = [], vp: PreviewCell[] = [], cum: PreviewCell[] = [];
  for (const y of years) {
    const v01 = num(y.income_statement.ce01_ricavi_vendite), v04 = num(y.income_statement.ce04_altri_ricavi);
    r01.push({ value: v01, pct: prev01 ? ((v01 - prev01) / prev01) * 100 : null });
    d01.push({ value: v01 - prev01 });
    r04.push({ value: v04, pct: prev04 ? ((v04 - prev04) / prev04) * 100 : null });
    vp.push({ value: ceAggregates(y.income_statement).vp });
    cum.push({ value: null, pct: b01 ? ((v01 - b01) / b01) * 100 : null });
    prev01 = v01; prev04 = v04;
  }
  return [
    row("ce01", "Ricavi delle vendite", "kpi", { value: b01 }, r01),
    row("delta", "variazione assoluta", "sub", { value: null }, d01),
    row("ce04", "Altri ricavi e proventi", "value", { value: b04 }, r04),
    row("vp", "Valore della produzione", "total", { value: bVp }, vp),
    row("cumulata", "crescita cumulata sul base", "sub", { value: null }, cum),
  ];
}

export function rowsCosti(
  baseInc: IncomeStatement, fixedShare: { materials: number; services: number }, years: ForecastPreviewYear[],
): PreviewRow[] {
  const b = {
    rev: num(baseInc.ce01_ricavi_vendite), other: num(baseInc.ce04_altri_ricavi),
    mat: num(baseInc.ce05_materie_prime), serv: num(baseInc.ce06_servizi),
    god: num(baseInc.ce07_godimento_beni), pers: num(baseInc.ce08_costi_personale), alt: num(baseInc.ce12_oneri_diversi),
  };
  const bFixed = b.mat * fixedShare.materials / 100 + b.serv * fixedShare.services / 100 + b.pers + b.god;
  const bVar = b.mat + b.serv - (b.mat * fixedShare.materials / 100 + b.serv * fixedShare.services / 100);
  const bMain = b.mat + b.serv + b.god + b.pers;
  const cell = (v: number | null, rev: number, note?: string): PreviewCell => ({ value: v, pct: pctOf(v, rev), ...(note ? { note } : {}) });
  const cols = years.map((y) => {
    const i = y.income_statement, d = y.details;
    const rev = num(i.ce01_ricavi_vendite);
    const mat = num(i.ce05_materie_prime), serv = num(i.ce06_servizi), god = num(i.ce07_godimento_beni), pers = num(i.ce08_costi_personale);
    const main = mat + serv + god + pers;
    const split = d.ce05_fixed !== null && d.ce06_fixed !== null && d.ce05_variable !== null && d.ce06_variable !== null;
    const fixed = split ? d.ce05_fixed! + d.ce06_fixed! + pers + god : null;
    const variable = split ? d.ce05_variable! + d.ce06_variable! : null;
    const note = split ? undefined : "forzato in CE Prev.";
    return {
      rev: { value: rev } as PreviewCell,
      main: cell(main, rev), fixed: cell(fixed, rev, note), variable: cell(variable, rev, note),
      mat: cell(mat, rev), serv: cell(serv, rev), pers: cell(pers, rev), god: cell(god, rev),
      mol: cell(ceAggregates(i).mol, rev),
      forn: { value: num(y.balance_sheet.sp16d_debiti_fornitori_breve), days: d.dpo_applied } as PreviewCell,
    };
  });
  const pick = (k: keyof (typeof cols)[number]) => cols.map((c) => c[k]);
  return [
    row("ricavi", "Ricavi delle vendite", "sub", { value: b.rev }, pick("rev")),
    row("principali", "Costi principali", "total", cell(bMain, b.rev), pick("main")),
    row("fissi", "di cui fissi", "sub", cell(bFixed, b.rev), pick("fixed")),
    row("variabili", "di cui variabili", "sub", cell(bVar, b.rev), pick("variable")),
    row("ce05", "Materie prime", "value", cell(b.mat, b.rev), pick("mat")),
    row("ce06", "Servizi", "value", cell(b.serv, b.rev), pick("serv")),
    row("ce08", "Personale", "value", cell(b.pers, b.rev), pick("pers")),
    row("ce07", "Godimento beni di terzi", "value", cell(b.god, b.rev), pick("god")),
    row("mol", "MOL stimato", "kpi", cell(ceAggregates(baseInc as unknown as Record<string, unknown>).mol, b.rev), pick("mol")),
    row("fornitori", "Debiti verso fornitori stimati", "value", { value: null }, pick("forn")),
  ];
}

export function rowsAltreVociCe(baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[] {
  // Cascata vp -> main -> alt -> MOL -> amm -> RO -> fin -> ebt: ogni riga (tranne i
  // subtotali kpi) porta gia' il segno con cui va sommata, cosi' vp + main + alt + amm
  // + fin torna esattamente ebt (stessa formula canonica di ceAggregates).
  const bRev = num(baseInc.ce01_ricavi_vendite);
  const b = ceAggregates(baseInc as unknown as Record<string, unknown>);
  const ys = years.map((y) => ({ agg: ceAggregates(y.income_statement), rev: num(y.income_statement.ce01_ricavi_vendite) }));
  const r = (
    key: keyof ReturnType<typeof ceAggregates>, label: string, kind: PreviewRowKind, sign: 1 | -1 = 1, withPct = false,
  ): PreviewRow =>
    row(key, label, kind, { value: sign * b[key], ...(withPct ? { pct: pctOf(sign * b[key], bRev) } : {}) },
      ys.map(({ agg, rev }) => ({ value: sign * agg[key], ...(withPct ? { pct: pctOf(sign * agg[key], rev) } : {}) })));
  return [
    r("vp", "Valore della produzione", "value"), r("main", "Costi principali", "sub", -1),
    r("alt", "Altre voci dei costi della produzione", "sub", -1), r("mol", "MOL", "kpi", 1, true),
    r("amm", "Ammortamenti e svalutazioni", "sub", -1), r("ro", "Risultato operativo", "kpi"),
    r("fin", "Proventi e oneri finanziari e straordinari", "value"), r("ebt", "Risultato ante imposte", "total"),
  ];
}

export function rowsCircolante(baseBs: BalanceSheet, baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[] {
  const bCred = num(baseBs.sp06_crediti_breve) - num(baseBs.sp06e_crediti_tributari_breve) - num(baseBs.sp06f_imposte_anticipate_breve);
  const bMag = num(baseBs.sp05_rimanenze), bForn = num(baseBs.sp16d_debiti_fornitori_breve), bRev = num(baseInc.ce01_ricavi_vendite);
  const bCcn = bCred + bMag - bForn;
  let prevCcn = bCcn;
  const cells = years.map((y) => {
    const bs = y.balance_sheet, d = y.details;
    const cred = num(bs.sp06_crediti_breve) - num(bs.sp06e_crediti_tributari_breve) - num(bs.sp06f_imposte_anticipate_breve);
    const mag = num(bs.sp05_rimanenze), forn = num(bs.sp16d_debiti_fornitori_breve), rev = num(y.income_statement.ce01_ricavi_vendite);
    const ccn = cred + mag - forn;
    const out = { cred: { value: cred, days: d.dso_applied }, mag: { value: mag, days: d.dio_applied },
      forn: { value: -forn, days: d.dpo_applied }, ccn: { value: ccn }, pct: { value: null, pct: pctOf(ccn, rev) },
      cash: { value: -(ccn - prevCcn) } };
    prevCcn = ccn;
    return out;
  });
  const pick = (k: keyof (typeof cells)[number]) => cells.map((c) => c[k] as PreviewCell);
  return [
    row("crediti", "Crediti commerciali", "value", { value: bCred }, pick("cred")),
    row("rimanenze", "Rimanenze", "value", { value: bMag }, pick("mag")),
    row("fornitori", "Debiti verso fornitori", "value", { value: -bForn }, pick("forn")),
    row("ccn", "Capitale circolante commerciale", "total", { value: bCcn }, pick("ccn")),
    row("ccn-pct", "in % dei ricavi", "sub", { value: null, pct: pctOf(bCcn, bRev) }, pick("pct")),
    row("cassa", "assorbimento di cassa nell'anno", "sub", { value: null }, pick("cash")),
  ];
}

const finDebt = (bs: Record<string, unknown>) =>
  num(bs.sp16a_debiti_banche_breve) + num(bs.sp17a_debiti_banche_lungo) + num(bs.sp16b_debiti_altri_finanz_breve)
  + num(bs.sp17b_debiti_altri_finanz_lungo) + num(bs.sp16c_debiti_obbligazioni_breve) + num(bs.sp17c_debiti_obbligazioni_lungo);

export function rowsPregressoNuovo(baseBs: BalanceSheet, years: ForecastPreviewYear[]): PreviewRow[] {
  const bb = baseBs as unknown as Record<string, unknown>;
  const mk = (bs: Record<string, unknown>) => {
    const bank = num(bs.sp16a_debiti_banche_breve) + num(bs.sp17a_debiti_banche_lungo);
    const altri = num(bs.sp16b_debiti_altri_finanz_breve) + num(bs.sp17b_debiti_altri_finanz_lungo);
    const cash = num(bs.sp09_disponibilita_liquide);
    const immob = num(bs.sp02_immob_immateriali) + num(bs.sp03_immob_materiali);
    return { bank, altri, immob, cash, pfn: finDebt(bs) - cash };
  };
  const b = mk(bb), ys = years.map((y) => mk(y.balance_sheet));
  const r = (key: keyof typeof b, label: string, kind: PreviewRowKind): PreviewRow =>
    row(key, label, kind, { value: b[key] }, ys.map((c) => ({ value: c[key] })));
  return [
    r("bank", "Debiti bancari", "value"), r("altri", "Altri finanziatori", "value"),
    r("immob", "Immobilizzazioni nette", "value"), r("cash", "Cassa", "kpi"),
    r("pfn", "Posizione finanziaria netta", "total"),
  ];
}

export function rowsImposte(baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[] {
  const g = (i: Record<string, unknown>, k: string) => num(i[k]);
  // Risultato ante imposte ricapitolato dal CE gia' scritto dal motore: stessa
  // formula canonica di computeEffectiveTaxRate (assumption-rows.ts), qui unica
  // in ceAggregates, cosi' le due non possono divergere.
  const mk = (i: Record<string, unknown>, bs?: Record<string, unknown>) => {
    const ebt = ceAggregates(i).ebt, tax = g(i, "ce20_imposte");
    return { ebt, tax: -tax, net: ebt - tax, trib: bs ? num(bs.sp16e_debiti_tributari_breve) : null };
  };
  const b = mk(baseInc as unknown as Record<string, unknown>);
  const ys = years.map((y) => mk(y.income_statement, y.balance_sheet));
  const r = (key: keyof typeof b, label: string, kind: PreviewRowKind): PreviewRow =>
    row(key === "tax" ? "ce20" : key, label, kind, { value: b[key] }, ys.map((c) => ({ value: c[key] })));
  return [r("ebt", "Risultato ante imposte", "value"), r("tax", "Imposte", "sub"),
    r("net", "Utile netto", "kpi"), r("trib", "Debiti tributari a fine anno", "value")];
}

export function unfundedFromError(error: ForecastPreviewError | null): { year: number; amount: number } | null {
  if (!error || error.year === null) return null;
  const m = /Unfunded financing requirement ([\d,]+\.\d{2})/i.exec(error.message);
  if (!m) return null;
  return { year: error.year, amount: parseFloat(m[1].replace(/,/g, "")) };
}
