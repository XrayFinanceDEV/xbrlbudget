/**
 * Dalla risposta di POST /preview alle righe dell'anteprima di ogni passo.
 * Solo somme, differenze e percentuali di numeri che il motore ha gia'
 * restituito: qui non si deriva nulla (spec 2026-09-08 §7).
 */
import type { BalanceSheet, ForecastPreviewError, ForecastPreviewYear, IncomeStatement } from "@/types/api";
import type { HistoricalData } from "@/lib/budget-trend";
import { computeAutoDays } from "@/lib/budget-turnover";
import { euro, num, pctOf } from "@/lib/budget-format";
import type { PregressoKey } from "@/types/api";
import { PREGRESSO_LABELS } from "@/lib/budget-pregresso-circolante";
import { legacyNoteFor } from "@/lib/budget-pregresso-tabella";

export interface PreviewCell { value: number | null; pct?: number | null; days?: number | null; note?: string }
export type PreviewRowKind = "value" | "sub" | "total" | "kpi";
export interface PreviewRow { key: string; label: string; kind: PreviewRowKind; base: PreviewCell; years: PreviewCell[] }

const row = (key: string, label: string, kind: PreviewRowKind, base: PreviewCell, years: PreviewCell[]): PreviewRow =>
  ({ key, label, kind, base, years });

/**
 * Unico punto del CE ricapitolato: valore della produzione, costi della
 * produzione (per macro-voce) e area finanziaria/straordinaria, con la stessa
 * formula canonica di computeEffectiveTaxRate (assumption-rows.ts) — quella
 * funzione la importa da qui, cosi' la formula esiste in un solo posto.
 *
 * «Canonica» vuol dire una cosa precisa: la stessa di `calculate_ce_result`
 * (`calculations/ce_result.py`), che e' cio' che scrivono `/analysis`, il
 * riclassificato e il report. Due punti su cui questa funzione se n'era
 * discostata, e che il test congela:
 *
 * - `ce11b_altri_accantonamenti` entra nei costi della produzione. Il motore
 *   lo SCRIVE nel CE previsionale (`forecast_engine.py`, con `ce11b_override`
 *   fra le colonne idratate): ometterlo faceva discordare MOL, RO, EBT e
 *   «Valore della produzione» dei passi 1-4 e 7 da ogni altra vista sulla
 *   stessa azienda.
 * - la sezione D e' `ce17a − ce17b` quando UNO dei due dettagli e' valorizzato,
 *   e l'aggregato `ce17` viene ignorato; sommarli sempre entrambi conta due
 *   volte la stessa rettifica.
 */
export function ceAggregates(income: Record<string, unknown>): {
  vp: number; main: number; alt: number; amm: number; fin: number; mol: number; ro: number; ebt: number;
} {
  const g = (k: string) => num(income[k]);
  const vp = g("ce01_ricavi_vendite") + g("ce02_variazioni_rimanenze") + g("ce03_lavori_interni")
    + g("ce03a_incrementi_immobilizzazioni") + g("ce04_altri_ricavi");
  const main = g("ce05_materie_prime") + g("ce06_servizi") + g("ce07_godimento_beni") + g("ce08_costi_personale");
  const alt = g("ce10_var_rimanenze_mat_prime") + g("ce11_accantonamenti") + g("ce11b_altri_accantonamenti")
    + g("ce12_oneri_diversi");
  const amm = g("ce09_ammortamenti");
  const riva = g("ce17a_rivalutazioni"), sval = g("ce17b_svalutazioni");
  const rettificheD = riva !== 0 || sval !== 0 ? riva - sval : g("ce17_rettifiche_attivita_fin");
  const fin = g("ce13_proventi_partecipazioni") + g("ce14_altri_proventi_finanziari") - g("ce15_oneri_finanziari")
    + g("ce16_utili_perdite_cambi") + rettificheD
    + g("ce18_proventi_straordinari") - g("ce19_oneri_straordinari");
  const mol = vp - main - alt;
  const ro = mol - amm;
  const ebt = ro + fin;
  return { vp, main, alt, amm, fin, mol, ro, ebt };
}

/**
 * L'anteprima del passo Scenario (Task 11 §1): niente chiamata a `/preview`,
 * solo un recap del bilancio storico gia' caricato — ricavi, incidenza % di
 * ce05/ce06/ce08 sui ricavi, il MOL canonico di `ceAggregates` e i giorni
 * `computeAutoDays` per DSO/DIO/DPO. La colonna "base" del `PreviewPanel` e'
 * l'anno base vero (`baseYear`, lo stesso del titolo «Bilancio {baseYear} ·
 * anno base»), le colonne `years` sono gli anni storici PRECEDENTI (fix
 * round 1, rilievo 2 — la colonna base mostrava `historicalYears[0]`, il
 * primo anno in archivio, disallineata dal titolo): nessun anno e' mostrato
 * due volte, e il vero anno base non finisce fra colonne che altrove nel
 * wizard significano "anni di previsione".
 */
export function rowsAnnoBase(baseYear: number, historicalYears: number[], historical: HistoricalData): PreviewRow[] {
  if (historicalYears.length === 0) return [];
  const anniPrecedenti = historicalYears.filter((y) => y !== baseYear);
  const baseEntry = historical[baseYear];
  const restEntries = anniPrecedenti.map((y) => historical[y]);

  const revenueOf = (e: HistoricalData[number] | undefined): number | null => (e ? num(e.income.ce01_ricavi_vendite) : null);

  const incidenceRow = (key: string, label: string, field: keyof IncomeStatement): PreviewRow => {
    const cellFor = (e: HistoricalData[number] | undefined): PreviewCell => {
      if (!e) return { value: null };
      const v = num(e.income[field]);
      return { value: v, pct: pctOf(v, num(e.income.ce01_ricavi_vendite)) };
    };
    return row(key, label, "value", cellFor(baseEntry), restEntries.map(cellFor));
  };

  // MOL da ceAggregates, l'unico aggregatore canonico del modulo: e' la
  // stessa "MOL" che rowsCosti e rowsAltreVociCe calcolano sullo stesso anno
  // base. Una formula locale piu' semplice (quella letterale del brief,
  // ce01+ce04-ce05-ce06-ce07-ce08-ce12) diverge da quella canonica per
  // (ce02+ce03+ce03a)-(ce10+ce11) — variazione rimanenze, lavori interni o
  // accantonamenti non nulli danno due "MOL" diversi passando dal passo 1 al
  // passo 3 (fix round 1, rilievo 1).
  const molOf = (e: HistoricalData[number] | undefined): number | null =>
    e ? ceAggregates(e.income as unknown as Record<string, unknown>).mol : null;

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

/**
 * Il pregresso di circolante che il motore ha davvero scadenziato, saldo per
 * saldo (Task 7): apertura in colonna base, poi per ogni anno il residuo a
 * breve, quello oltre l'esercizio, il chiuso e — dove c'e' — l'inesigibile.
 * Lettura pura di `details.pregresso`: qui non si scadenzia nulla, il piano lo
 * svolge `runoff_schedule` in Python.
 *
 * `mode: "legacy"` non e' un residuo di zero: e' un saldo per cui NESSUN piano
 * e' stato dichiarato, e che quindi segue le formule di sempre. La nota che lo
 * dice NON e' la stessa frase su tutti e cinque i saldi (`legacyNoteFor`,
 * `lib/budget-pregresso-tabella.ts`, rilievo 4 del giro di correzione 1):
 * fornitori e crediti si chiudono davvero nel primo anno perche' un driver di
 * volume li rigenera comunque, ma previdenziali e altri debiti — senza un
 * driver dietro — crescono per percentuale e non si chiudono in alcun senso
 * visibile. Confondere «nessun piano» con «residuo pagato» sarebbe un difetto
 * a se'; dire "chiude" di un saldo che invece cresce sarebbe l'altro.
 */
export function rowsPregressoRunoff(years: ForecastPreviewYear[], keys: readonly PregressoKey[]): PreviewRow[] {
  if (years.length === 0) return [];
  const empty = (): PreviewCell[] => years.map(() => ({ value: null }));
  const out: PreviewRow[] = [
    row("pregresso-head", "Pregresso: residuo a breve · oltre", "total", { value: null }, empty()),
  ];
  for (const key of keys) {
    const det = years.map((y) => y.details.pregresso?.[key] ?? null);
    const pick = (f: "residual_short" | "residual_long" | "closed" | "writeoff"): PreviewCell[] =>
      det.map((d) => ({ value: d ? num(d[f]) : null }));
    const residuo = pick("residual_short").map((c, i) =>
      det[i]?.mode === "legacy" ? { ...c, note: legacyNoteFor(key) } : c);
    out.push(row(`pregresso-${key}`, `${PREGRESSO_LABELS[key]} · residuo a breve`, "value",
      { value: det[0] ? num(det[0].opening) : null }, residuo));
    out.push(row(`pregresso-${key}-long`, "oltre l'esercizio", "sub", { value: null }, pick("residual_long")));
    out.push(row(`pregresso-${key}-closed`, "chiuso nell'anno", "sub", { value: null }, pick("closed")));
    // L'inesigibile esiste sul solo piano dei crediti: si mostra quando il
    // motore ne dichiara uno, invece di aggiungere quattro righe a zero.
    const writeoff = pick("writeoff");
    if (writeoff.some((c) => c.value !== null && c.value !== 0)) {
      out.push(row(`pregresso-${key}-writeoff`, "di cui inesigibile", "sub", { value: null }, writeoff));
    }
  }
  return out;
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

/** Un anno sulla VIA MANUALE non ha una liquidazione da mostrare: il motore
 *  dichiara zero invece di inventare gli importi, e uno zero letto come
 *  «versato niente» sarebbe peggio del vuoto. */
const IMPOSTE_MANUALE = "posizione tributaria manuale";

/**
 * Come si sono PAGATE le imposte di ogni anno (Task 8): il saldo maturato a
 * fine anno precedente, l'acconto sull'anno in corso, la rata del tributario
 * rateizzato, e cio' che resta aperto a fine anno.
 *
 * Lettura pura di `details.imposte`: il kernel e'
 * `tax_settlement_saldo_acconto` (`calculations/projection_common.py`), qui
 * non si liquida nulla. L'uscita di cassa e' l'unica somma, ed e' la stessa
 * del kernel (`saldo_paid + acconti_paid + rate_paid`).
 *
 * `mode: "manual"` non e' un anno pagato a zero: e' un anno in cui una
 * percentuale di crescita su `sp06e`/`sp16e` ha preso il posto del piano. Le
 * celle di quegli anni restano VUOTE con la loro nota — tranne l'imposta
 * dell'anno, che il motore dichiara in entrambe le vie. Quando ogni anno e'
 * manuale non resta nulla da incolonnare: una riga sola, con la nota.
 */
export function rowsImposteSaldoAcconto(years: ForecastPreviewYear[]): PreviewRow[] {
  if (years.length === 0) return [];
  // Una chiave assente vale zero, ma il MODO assente non e' «automatico»:
  // senza `imposte` non c'e' liquidazione da mostrare, e la riga si comporta
  // come sulla via manuale invece di stampare colonne di zeri.
  const det = years.map((y) => y.details?.imposte ?? null);
  const manuale = det.map((d) => d === null || d.mode !== "saldo_acconto");
  const head = row("imposte-pagamenti", "Pagamenti dell'anno", "total", { value: null },
    years.map((_, i) => (manuale[i] ? { value: null, note: IMPOSTE_MANUALE } : { value: null })));
  if (manuale.every(Boolean)) return [head];

  const cells = (f: (d: NonNullable<(typeof det)[number]>) => number, sempre = false): PreviewCell[] =>
    det.map((d, i) =>
      d !== null && (sempre || !manuale[i]) ? { value: num(f(d)) } : { value: null, note: IMPOSTE_MANUALE });
  const someNonZero = (cs: PreviewCell[]) => cs.some((c) => c.value !== null && c.value !== 0);

  const out: PreviewRow[] = [head];
  // L'imposta dell'anno il motore la dichiara anche sulla via manuale: e' la
  // sola cifra vera di quegli anni, e nasconderla direbbe meno del dovuto.
  //
  // «correnti», non «dell'anno»: nel motore `total_tax = current_tax +
  // deferred_expense` (`forecast_engine.py:1287`) e questa riga legge SOLO
  // `current_tax`, la componente che partecipa alla liquidazione di
  // saldo/acconto — la riga «Imposte» del CE ricapitolato (`rowsImposte`,
  // sopra) e' invece `ce20`, il totale. Con differenze temporanee non nulle le
  // due divergono davvero (misurato: sonda del motore, +40.000 di differenza
  // tassabile al 25% -> ce20 − current_tax = 10.000, l'imposta differita), e la stessa
  // etichetta sulle due righe farebbe leggere due numeri diversi come se
  // fossero la stessa cosa (fix1 R7).
  out.push(row("imposte-current", "Imposte correnti dell'anno", "value", { value: null },
    cells((d) => d.current_tax, true)));
  out.push(row("imposte-saldo", "Saldo dell'anno precedente versato", "sub", { value: null },
    cells((d) => d.saldo_paid)));
  out.push(row("imposte-acconti", "Acconti versati", "sub", { value: null },
    cells((d) => d.acconti_paid)));
  // Le rate esistono solo con un rateizzato scadenziato, il credito solo
  // quando l'acconto ha superato l'imposta: righe a zero fisso non si mostrano.
  const rate = cells((d) => d.rate_paid);
  if (someNonZero(rate)) out.push(row("imposte-rate", "Rate del rateizzato", "sub", { value: null }, rate));
  out.push(row("imposte-cassa", "Uscita di cassa per imposte", "kpi", { value: null },
    cells((d) => d.saldo_paid + d.acconti_paid + d.rate_paid)));
  // «Saldo d'imposta da versare l'anno dopo», non «Debito tributario a fine
  // anno»: quella riga sta gia' sopra (`rowsImposte`, chiave "trib") ed e'
  // `sp16e` — nel motore `sp16e = generated_debt + residual_short` del piano a
  // rate (`forecast_engine.py:2117`), quindi con un piano a rate le due righe
  // divergono SEMPRE della rata a breve (misurato: sonda del motore, 20.000
  // contro 0 su due anni). `generated_debt` e' solo la parte generata
  // dall'imposta dell'anno, senza il rateizzato pregresso: due etichette
  // quasi identiche sopra due numeri diversi, nello stesso riquadro, erano il
  // difetto (fix1 R1).
  out.push(row("imposte-debito", "Saldo d'imposta da versare l'anno dopo", "value", { value: null },
    cells((d) => d.generated_debt)));
  const credito = cells((d) => d.generated_credit);
  if (someNonZero(credito)) {
    out.push(row("imposte-credito", "Credito tributario a fine anno", "value", { value: null }, credito));
  }
  return out;
}

/**
 * L'importo del fabbisogno scoperto dentro un messaggio del motore, o `null`
 * se il messaggio e' un altro.
 *
 * Riconoscimento UNICO — una sola regex per l'anteprima (che riceve
 * `ForecastPreviewError`, con l'anno) e per il salvataggio in blocco (che
 * riceve una sola stringa, senza anno: `assumptions_service.py` incapsula
 * `str(e)` in «Assumptions saved successfully, but forecast generation
 * failed: …»). Due regex divergerebbero alla prima modifica del messaggio del
 * motore, e uno dei due canali tornerebbe in silenzio all'inglese grezzo.
 */
export function unfundedAmountFromMessage(message: string): number | null {
  const m = /Unfunded financing requirement ([\d,]+\.\d{2})/i.exec(message);
  return m ? parseFloat(m[1].replace(/,/g, "")) : null;
}

export function unfundedFromError(error: ForecastPreviewError | null): { year: number; amount: number } | null {
  if (!error || error.year === null) return null;
  const amount = unfundedAmountFromMessage(error.message);
  return amount === null ? null : { year: error.year, amount };
}

// ── Cassa assorbita e scoperto di c/c (Task 12) ────────────────────────────

export interface ScopertoAnno { year: number; cassaAssorbita: number; scopertoGenerato: number; scopertoResiduo: number }

export interface ScopertoAvvisi {
  anni: ScopertoAnno[];
  /** Il fabbisogno di picco del piano e l'anno in cui cade: il numero e la data
   *  che si portano in banca. `null` quando il motore non dichiara scoperto. */
  picco: { amount: number; year: number } | null;
  /** Avviso tenue: il piano consuma cassa, anche se la cassa resta positiva. */
  cassa: string | null;
  /** Avviso forte: il piano ha acceso uno scoperto, con gli importi. */
  scoperto: string | null;
}

/**
 * Gli avvisi di cassa e di scoperto dell'anteprima, letti da cio' che il motore
 * DICHIARA (`details.cassa_assorbita`, `scoperto_*`, `fabbisogno_picco*`): qui
 * non si deriva nulla, e il picco non si ricalcola come massimo dei residui —
 * lo dichiara il motore, uguale su ogni anno.
 *
 * Una chiave assente vale zero (il tipo le tiene facoltative): e' la lettura
 * prudente, perche' il motore le dichiara sempre, e un'anteprima di una
 * versione vecchia non deve inventare un avviso.
 *
 * L'avviso di cassa esiste anche senza scoperto, ed e' il punto: l'utente
 * deve sapere che il piano gli consuma liquidita' PRIMA che diventi uno
 * scoperto. Con lo scoperto spento e un fabbisogno scoperto il motore si
 * ferma, e quel caso lo dice gia' `previewNotice`: qui non si ripete.
 */
export function scopertoAvvisi(years: ForecastPreviewYear[]): ScopertoAvvisi {
  const anni = years.map((y) => ({
    year: y.year,
    cassaAssorbita: num(y.details.cassa_assorbita),
    scopertoGenerato: num(y.details.scoperto_generato),
    scopertoResiduo: num(y.details.scoperto_residuo),
  }));
  const primo = years[0]?.details;
  const pAmount = num(primo?.fabbisogno_picco);
  const pYear = primo?.fabbisogno_picco_anno ?? null;
  const picco = pAmount > 0 && pYear !== null ? { amount: pAmount, year: pYear } : null;

  const assorbita = anni.filter((a) => a.cassaAssorbita > 0);
  const cassa = assorbita.length === 0 ? null
    : `Il piano assorbe cassa: ${assorbita.map((a) => `${euro(a.cassaAssorbita)} nel ${a.year}`).join(", ")}. `
      + "La liquidità si riduce anche dove resta positiva.";

  const generato = anni.filter((a) => a.scopertoGenerato > 0);
  const scoperto = generato.length === 0 && picco === null ? null
    : `Scoperto di conto corrente generato dal piano: ${
      generato.map((a) => `${euro(a.scopertoGenerato)} nel ${a.year}`).join(", ") || "nessuno nuovo"}. `
      + (picco ? `Fabbisogno di picco ${euro(picco.amount)} nel ${picco.year}: è la finanza che queste ipotesi richiedono.` : "");

  return { anni, picco, cassa, scoperto };
}
