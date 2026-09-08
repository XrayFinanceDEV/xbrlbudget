/**
 * Dalla risposta di POST /preview alle righe dell'anteprima di ogni passo.
 * Solo somme, differenze e percentuali di numeri che il motore ha gia'
 * restituito: qui non si deriva nulla (spec 2026-09-08 §7).
 */
import type { BalanceSheet, ForecastPreviewError, ForecastPreviewYear, IncomeStatement } from "@/types/api";

export interface PreviewCell { value: number | null; pct?: number | null; days?: number | null; note?: string }
export type PreviewRowKind = "value" | "sub" | "total" | "kpi";
export interface PreviewRow { key: string; label: string; kind: PreviewRowKind; base: PreviewCell; years: PreviewCell[] }

const num = (v: unknown): number => (typeof v === "number" ? v : parseFloat(String(v ?? "0")) || 0);
const pctOf = (v: number | null, den: number): number | null => (v === null || den === 0 ? null : (v / den) * 100);
const row = (key: string, label: string, kind: PreviewRowKind, base: PreviewCell, years: PreviewCell[]): PreviewRow =>
  ({ key, label, kind, base, years });

export function rowsFatturato(baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[] {
  const b01 = num(baseInc.ce01_ricavi_vendite), b04 = num(baseInc.ce04_altri_ricavi);
  let prev01 = b01, prev04 = b04;
  const r01: PreviewCell[] = [], d01: PreviewCell[] = [], r04: PreviewCell[] = [], vp: PreviewCell[] = [], cum: PreviewCell[] = [];
  for (const y of years) {
    const v01 = num(y.income_statement.ce01_ricavi_vendite), v04 = num(y.income_statement.ce04_altri_ricavi);
    r01.push({ value: v01, pct: prev01 ? ((v01 - prev01) / prev01) * 100 : null });
    d01.push({ value: v01 - prev01 });
    r04.push({ value: v04, pct: prev04 ? ((v04 - prev04) / prev04) * 100 : null });
    vp.push({ value: v01 + v04 });
    cum.push({ value: null, pct: b01 ? ((v01 - b01) / b01) * 100 : null });
    prev01 = v01; prev04 = v04;
  }
  return [
    row("ce01", "Ricavi delle vendite", "kpi", { value: b01 }, r01),
    row("delta", "variazione assoluta", "sub", { value: null }, d01),
    row("ce04", "Altri ricavi e proventi", "value", { value: b04 }, r04),
    row("vp", "Valore della produzione", "total", { value: b01 + b04 }, vp),
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
      mol: cell(rev + num(i.ce04_altri_ricavi) - main - num(i.ce12_oneri_diversi), rev),
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
    row("mol", "MOL stimato", "kpi", cell(b.rev + b.other - bMain - b.alt, b.rev), pick("mol")),
    row("fornitori", "Debiti verso fornitori stimati", "value", { value: null }, pick("forn")),
  ];
}

export function rowsAltreVociCe(baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[] {
  const g = (i: Record<string, unknown>, k: string) => num(i[k]);
  const mk = (i: Record<string, unknown>) => {
    const vp = g(i, "ce01_ricavi_vendite") + g(i, "ce04_altri_ricavi");
    const main = g(i, "ce05_materie_prime") + g(i, "ce06_servizi") + g(i, "ce07_godimento_beni") + g(i, "ce08_costi_personale");
    const alt = g(i, "ce12_oneri_diversi"), amm = g(i, "ce09_ammortamenti"), of = g(i, "ce15_oneri_finanziari");
    const mol = vp - main - alt, ro = mol - amm;
    return { vp, main: -main, alt: -alt, mol, amm: -amm, ro, of: -of, ebt: ro - of, rev: g(i, "ce01_ricavi_vendite") };
  };
  const b = mk(baseInc as unknown as Record<string, unknown>);
  const ys = years.map((y) => mk(y.income_statement));
  const r = (key: keyof typeof b, label: string, kind: PreviewRowKind, withPct = false): PreviewRow =>
    row(key, label, kind, { value: b[key], ...(withPct ? { pct: pctOf(b[key], b.rev) } : {}) },
      ys.map((c) => ({ value: c[key], ...(withPct ? { pct: pctOf(c[key], c.rev) } : {}) })));
  return [
    r("vp", "Valore della produzione", "value"), r("main", "Costi principali", "sub"),
    r("alt", "Oneri diversi di gestione", "sub"), r("mol", "MOL", "kpi", true),
    r("amm", "Ammortamenti", "sub"), r("ro", "Risultato operativo", "kpi"),
    r("of", "Oneri finanziari", "sub"), r("ebt", "Risultato ante imposte", "total"),
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
  // Risultato ante imposte ricapitolato dal CE gia' scritto dal motore, con la
  // stessa formula canonica di computeEffectiveTaxRate (assumption-rows.ts):
  // valore della produzione, costi della produzione e area finanziaria/straordinaria
  // con i loro segni, cosi' le due non possono divergere.
  const mk = (i: Record<string, unknown>, bs?: Record<string, unknown>) => {
    const vp = g(i, "ce01_ricavi_vendite") + g(i, "ce02_variazioni_rimanenze")
      + g(i, "ce03_lavori_interni") + g(i, "ce03a_incrementi_immobilizzazioni") + g(i, "ce04_altri_ricavi");
    const costs = g(i, "ce05_materie_prime") + g(i, "ce06_servizi") + g(i, "ce07_godimento_beni")
      + g(i, "ce08_costi_personale") + g(i, "ce09_ammortamenti") + g(i, "ce10_var_rimanenze_mat_prime")
      + g(i, "ce11_accantonamenti") + g(i, "ce12_oneri_diversi");
    const fin = g(i, "ce13_proventi_partecipazioni") + g(i, "ce14_altri_proventi_finanziari")
      - g(i, "ce15_oneri_finanziari") + g(i, "ce16_utili_perdite_cambi") + g(i, "ce17_rettifiche_attivita_fin")
      + g(i, "ce18_proventi_straordinari") - g(i, "ce19_oneri_straordinari");
    const ebt = vp - costs + fin, tax = g(i, "ce20_imposte");
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
