export function safeDivide(a: number, b: number): number {
  return b !== 0 ? a / b : 0;
}

export interface IndicatorSet {
  dscr: number;
  ebitda_margin: number;
  mt: number;
  ccn: number;
  current_ratio: number;
  ms: number;
  copertura_immob: number;
  indipendenza: number;
  pfn: number;
  pfn_ebitda: number;
  roi: number;
  roe: number;
  ros: number;
  // Due domande diverse, tenute entrambe: `of_mol` dice quanto pesano gli
  // oneri sulla capacita' di generare cassa ed e' quello usato dal punteggio
  // di crisi; `of_revenue` dice quanto pesano sul giro d'affari.
  of_mol: number;
  of_revenue: number;
  materials_revenue: number;
  services_revenue: number;
  // Internal fields for scoring
  _ebitda_raw: number;
  _quick_ratio: number;
  _equity_over_fixed: number;
  // Serve a `scoreIndicator("of_revenue")`: il rapporto da solo non distingue
  // «oneri nulli» da «ricavi nulli», e su un punteggio invertito i due
  // porterebbero allo stesso verdetto di eccellenza.
  _revenue_raw: number;
}

// Linear interpolation score: 0 at `low`, 1 at `high`, clamped [0,1]
export function linearScore(value: number, low: number, high: number): number {
  if (value <= low) return 0;
  if (value >= high) return 1;
  return (value - low) / (high - low);
}

// Score where lower values are better (inverted)
export function invertedScore(value: number, goodBelow: number, badAbove: number): number {
  return 1 - linearScore(value, goodBelow, badAbove);
}

export function computeIndicators(
  bs: Record<string, number>,
  is_: Record<string, number>,
): IndicatorSet {
  const v = (obj: Record<string, number>, key: string) => obj[key] || 0;

  // P&L aggregates
  const revenue = v(is_, "ce01_ricavi_vendite");
  const vp =
    revenue +
    v(is_, "ce02_variazioni_rimanenze") +
    v(is_, "ce03_lavori_interni") +
    v(is_, "ce03a_incrementi_immobilizzazioni") +
    v(is_, "ce04_altri_ricavi");
  const opCosts =
    v(is_, "ce05_materie_prime") +
    v(is_, "ce06_servizi") +
    v(is_, "ce07_godimento_beni") +
    v(is_, "ce08_costi_personale") +
    v(is_, "ce10_var_rimanenze_mat_prime") +
    v(is_, "ce11_accantonamenti") +
    v(is_, "ce11b_altri_accantonamenti") +
    v(is_, "ce12_oneri_diversi");
  const ebitda = vp - opCosts;
  const depreciation = v(is_, "ce09_ammortamenti");
  const ebit = ebitda - depreciation;
  const oneriFinanziari = v(is_, "ce15_oneri_finanziari");
  const imposte = v(is_, "ce20_imposte");

  // Net profit
  const financialIncome =
    v(is_, "ce13_proventi_partecipazioni") +
    v(is_, "ce14_altri_proventi_finanziari") +
    v(is_, "ce16_utili_perdite_cambi");
  const extraResult =
    v(is_, "ce18_proventi_straordinari") -
    v(is_, "ce19_oneri_straordinari");
  const netProfit =
    ebit -
    oneriFinanziari +
    financialIncome +
    extraResult +
    v(is_, "ce17_rettifiche_attivita_fin") -
    imposte;

  // BS aggregates
  const fixedAssets =
    v(bs, "sp02_immob_immateriali") +
    v(bs, "sp03_immob_materiali") +
    v(bs, "sp04_immob_finanziarie");
  const inventory = v(bs, "sp05_rimanenze");
  const cash = v(bs, "sp09_disponibilita_liquide");
  const financialAssets = v(bs, "sp08_attivita_finanziarie");
  const currentAssets =
    inventory +
    v(bs, "sp06_crediti_breve") +
    financialAssets +
    cash +
    v(bs, "sp10_ratei_risconti_attivi");
  // sp07_crediti_lungo (crediti esigibili oltre l'esercizio successivo) is deliberately
  // excluded from currentAssets above (it is not a current asset) but MUST be added back
  // here: it is still part of Totale Attivo (see ATTIVO_CODES in pratica-codes.ts and
  // attivoKeys in pratica-reconcile.ts, which both include it). Omitting it here understates
  // totalAssets and therefore overstates `indipendenza` and `roi` — the wrong direction for
  // a credit-risk indicator. Do not "simplify" this back out.
  const totalAssets =
    v(bs, "sp01_crediti_soci") + fixedAssets + currentAssets + v(bs, "sp07_crediti_lungo");
  const equity =
    v(bs, "sp11_capitale") +
    v(bs, "sp12_riserve") +
    v(bs, "sp13_utile_perdita");
  const currentLiabilities = v(bs, "sp16_debiti_breve");
  const longTermDebt = v(bs, "sp17_debiti_lungo");

  // PFN: financial debt = banche + obbligazioni (excluding soci finanziamenti / altri finanz.)
  // Priority 1: direct bank debt sub-fields (entro/oltre detail available)
  const bankDebt =
    v(bs, "sp16a_debiti_banche_breve") + v(bs, "sp17a_debiti_banche_lungo") +
    v(bs, "sp16c_debiti_obbligazioni_breve") + v(bs, "sp17c_debiti_obbligazioni_lungo");
  const hasDirectBankDebt = bankDebt > 0;
  // Priority 2: subtract known non-financial debts (fornitori, tributari, previdenza,
  // altri finanz./soci) from total. Exclude sp16g/sp17g ("altri debiti") — those are
  // plug fields that absorb unclassified amounts after reconcileSubfields.
  const knownNonBankDebt =
    v(bs, "sp16b_debiti_altri_finanz_breve") + v(bs, "sp17b_debiti_altri_finanz_lungo") +
    v(bs, "sp16d_debiti_fornitori_breve") + v(bs, "sp17d_debiti_fornitori_lungo") +
    v(bs, "sp16e_debiti_tributari_breve") + v(bs, "sp17e_debiti_tributari_lungo") +
    v(bs, "sp16f_debiti_previdenza_breve") + v(bs, "sp17f_debiti_previdenza_lungo");
  const totalDebt = currentLiabilities + longTermDebt;
  const hasNonBankDetail = knownNonBankDebt > 0;
  const totalFinancialDebt = hasDirectBankDebt
    ? bankDebt
    : hasNonBankDetail
      ? totalDebt - knownNonBankDebt
      : totalDebt;  // abbreviato: no detail at all, use total as fallback
  const pfn = totalFinancialDebt - cash - financialAssets;

  // DSCR = (EBITDA - Imposte) / Oneri finanziari
  const dscr = safeDivide(ebitda - imposte, oneriFinanziari);

  return {
    dscr,
    ebitda_margin: safeDivide(ebitda, revenue) * 100,
    mt: currentAssets - inventory - currentLiabilities,
    ccn: currentAssets - currentLiabilities,
    current_ratio: safeDivide(currentAssets, currentLiabilities),
    ms: equity - fixedAssets,
    copertura_immob: safeDivide(equity + longTermDebt, fixedAssets) * 100,
    indipendenza: safeDivide(equity, totalAssets) * 100,
    pfn,
    pfn_ebitda: safeDivide(pfn, ebitda),
    roi: safeDivide(ebit, totalAssets) * 100,
    roe: safeDivide(netProfit, equity) * 100,
    ros: safeDivide(ebit, revenue) * 100,
    of_mol: safeDivide(oneriFinanziari, ebitda) * 100,
    of_revenue: safeDivide(oneriFinanziari, revenue) * 100,
    materials_revenue: safeDivide(v(is_, "ce05_materie_prime"), revenue) * 100,
    services_revenue: safeDivide(v(is_, "ce06_servizi"), revenue) * 100,
    _ebitda_raw: ebitda,
    _quick_ratio: safeDivide(currentAssets - inventory, currentLiabilities),
    _equity_over_fixed: safeDivide(equity, fixedAssets) * 100,
    _revenue_raw: revenue,
  };
}

// Score each indicator 0-1 based on Italian banking/CNDCEC practice
export function scoreIndicator(
  key: keyof IndicatorSet,
  ind: IndicatorSet,
): number {
  switch (key) {
    // DSCR: <1 crisis (CNDCEC), 1-1.2 grey zone, >1.2 good, >1.5 solid
    case "dscr":
      return linearScore(ind.dscr, 1.0, 1.5);
    // EBITDA margin: <5% concerning, >20% excellent
    case "ebitda_margin":
      return linearScore(ind.ebitda_margin, 5, 20);
    // MT: scored via quick ratio - <0.8 critical, >1.3 solid
    case "mt":
      return linearScore(ind._quick_ratio, 0.8, 1.3);
    // CCN: scored via current ratio
    case "ccn":
      return linearScore(ind.current_ratio, 0.8, 1.5);
    // Current ratio: <0.8 critical, >1.5 solid
    case "current_ratio":
      return linearScore(ind.current_ratio, 0.8, 1.5);
    // MS: scored via equity/fixed assets - 50% weak, 120% strong
    case "ms":
      return linearScore(ind._equity_over_fixed, 50, 120);
    // Copertura: <80% critical, >150% solid
    case "copertura_immob":
      return linearScore(ind.copertura_immob, 80, 150);
    // Indipendenza: <15% fragile, >50% optimal
    case "indipendenza":
      return linearScore(ind.indipendenza, 15, 50);
    // PFN: scored via PFN/EBITDA (lower is better)
    case "pfn":
      if (ind._ebitda_raw <= 0 && ind.pfn > 0) return 0;
      return invertedScore(ind.pfn_ebitda, 0, 6);
    // PFN/EBITDA: <=0 great (no net debt), >6 critical (BCE threshold)
    case "pfn_ebitda":
      if (ind._ebitda_raw <= 0 && ind.pfn > 0) return 0;
      return invertedScore(ind.pfn_ebitda, 0, 6);
    // ROI: <0 loss, >12% good
    case "roi":
      return linearScore(ind.roi, 0, 12);
    // ROE: <0 loss, >12% good
    case "roe":
      return linearScore(ind.roe, 0, 12);
    // ROS: <0 loss, >10% good
    case "ros":
      return linearScore(ind.ros, 0, 10);
    // OF/MOL: <5% excellent, >30% critical (inverted)
    case "of_mol":
      if (ind._ebitda_raw <= 0) return ind.of_mol > 0 ? 0 : 0.5;
      return invertedScore(ind.of_mol, 5, 30);
    // OF/fatturato: <1% ottimo, >5% critico (invertito). Soglie della pratica
    // bancaria italiana, le stesse su cui e' tarato `of_mol`.
    //
    // Il ramo a ricavi zero non e' una rifinitura. `safeDivide` restituisce 0,
    // e su un punteggio INVERTITO uno zero vale «ottimo»: senza questo ramo
    // un'azienda senza ricavi risulterebbe la piu' sana del corpus, e sarebbe
    // indistinguibile da una che oneri finanziari non ne ha davvero. Gli altri
    // rapporti sui ricavi (`ros`, `ebitda_margin`) sono punteggi DIRETTI e
    // degenerano verso il basso da soli: l'asimmetria e' solo qui.
    //
    // Il verdetto degenere e' 0,5 e non 0 perche' un denominatore assente e'
    // «non lo so», non una contraddizione: un verdetto negativo vuole una
    // contraddizione misurata, non un controllo che manca.
    case "of_revenue":
      if (ind._revenue_raw <= 0) return 0.5;
      return invertedScore(ind.of_revenue, 1, 5);
    default:
      return 0.5;
  }
}

export const INDICATOR_DEFS: Array<{
  key: keyof IndicatorSet;
  label: string;
  format: "euro" | "pct" | "ratio";
}> = [
  { key: "dscr", label: "DSCR", format: "ratio" },
  { key: "ebitda_margin", label: "EBITDA %", format: "pct" },
  { key: "mt", label: "Margine di Tesoreria", format: "euro" },
  { key: "ccn", label: "CCN", format: "euro" },
  { key: "current_ratio", label: "Liquidità Corrente", format: "ratio" },
  { key: "ms", label: "Margine di Struttura", format: "euro" },
  { key: "copertura_immob", label: "Copertura Immobilizzazioni", format: "pct" },
  { key: "indipendenza", label: "Indipendenza Finanziaria", format: "pct" },
  { key: "pfn", label: "PFN", format: "euro" },
  { key: "pfn_ebitda", label: "PFN / EBITDA", format: "ratio" },
  { key: "roi", label: "ROI", format: "pct" },
  { key: "roe", label: "ROE", format: "pct" },
  { key: "ros", label: "ROS", format: "pct" },
  { key: "of_mol", label: "Oneri Finanziari / MOL", format: "pct" },
  { key: "of_revenue", label: "Oneri Finanziari / Fatturato", format: "pct" },
];

/**
 * Gli indicatori che alimentano il PUNTEGGIO di crisi, che non sono tutti
 * quelli che la tabella RENDE.
 *
 * `of_revenue` e' fuori di proposito. `computeCrisisRating` conta quanti
 * punteggi stanno sotto 0,33 e le sue bande (0 / 1-2 / 3 / 4-5 «oltre») sono
 * tarate sul NUMERO di indicatori che le alimentano: aggiungerne uno
 * sposterebbe la classe di rischio di aziende reali senza che nessuno
 * l'abbia deciso. E sugli oneri finanziari il punteggio usa gia' `of_mol` —
 * contare anche `of_revenue` peserebbe due volte lo stesso fatto, solo su un
 * altro denominatore.
 *
 * Il pallino di riga resta invece calcolato per OGNI indicatore: e' una
 * valutazione della singola voce, non un voto sull'azienda.
 */
export const CRISIS_SCORING_KEYS: Array<keyof IndicatorSet> = INDICATOR_DEFS
  .filter((d) => d.key !== "of_revenue")
  .map((d) => d.key);

/** I punteggi da passare a `computeCrisisRating`, nell'ordine canonico. */
export function crisisScores(ind: IndicatorSet): number[] {
  return CRISIS_SCORING_KEYS.map((k) => scoreIndicator(k, ind));
}

// Dot color and overall rating from score
/**
 * Una serie dei grafici della sezione Indicatori: l'etichetta della colonna e
 * il suo set di indicatori, oppure `null` quando quel periodo non esiste
 * (bilancio già annuale, o previsionale non ancora generato).
 */
export type SerieIndicatori = { periodo: string; indicatori: IndicatorSet | null };

/** Riga appiattita come la vuole Recharts: etichetta + tutti gli indicatori. */
export type RigaGraficoIndicatori = { periodo: string } & IndicatorSet;

/**
 * Costruisce le righe dei due grafici (incidenza economica ed equilibrio
 * finanziario) da un elenco di serie.
 *
 * Vive qui, e non dentro il componente, perché la consumano DUE viste — la tab
 * Indicatori e la Stampa — e perché è l'unica parte testabile: la suite di
 * questo progetto gira senza DOM (`environment: "node"`), quindi il componente
 * si verifica nel browser e la logica si verifica qui.
 *
 * Una serie assente viene SCARTATA, non resa a zero: una barra a zero sarebbe
 * indistinguibile da un'azienda con EBITDA nullo.
 */
export function buildIndicatorChartData(serie: SerieIndicatori[]): RigaGraficoIndicatori[] {
  return serie
    .filter((s): s is { periodo: string; indicatori: IndicatorSet } => s.indicatori !== null)
    .map((s) => ({ periodo: s.periodo, ...s.indicatori }));
}

export function scoreDotColor(score: number): string {
  if (score >= 0.67) return "bg-green-500";
  if (score >= 0.33) return "bg-yellow-500";
  return "bg-red-500";
}


// Crisis rating: combines indicators "oltre soglia" (score < 0.33) with extra-accounting alerts
// An indicator is "oltre soglia" when its score falls in the red zone
export function computeCrisisRating(
  scores: number[],
  alertCount: number,
): { code: string; label: string; color: string } {
  const oltreCount = scores.filter((s) => s < 0.33).length;

  // From best to worst:
  // A3: 0 oltre + 0 segnali
  if (oltreCount === 0 && alertCount === 0)
    return { code: "A3", label: "Nessun rischio", color: "text-green-600 dark:text-green-400" };
  // A2: 1-2 oltre + 0 segnali
  if (oltreCount <= 2 && alertCount === 0)
    return { code: "A2", label: "Rischio minimo", color: "text-green-600 dark:text-green-400" };
  // A1: 3 oltre + 0 segnali
  if (oltreCount === 3 && alertCount === 0)
    return { code: "A1", label: "Rischio basso", color: "text-green-600 dark:text-green-400" };
  // B3: 4-5 oltre + 0 segnali
  if (oltreCount <= 5 && alertCount === 0)
    return { code: "B3", label: "Rischio moderato", color: "text-yellow-600 dark:text-yellow-400" };
  // B2: 1 segnale e/o >4 oltre
  if (alertCount <= 1 && oltreCount <= 5)
    return { code: "B2", label: "Rischio significativo", color: "text-yellow-600 dark:text-yellow-400" };
  // B1: 2 segnali e/o >4 oltre
  if (alertCount <= 2 && oltreCount <= 5)
    return { code: "B1", label: "Rischio elevato", color: "text-orange-600 dark:text-orange-400" };
  // C3: 3 segnali e/o >5 oltre
  if (alertCount <= 3 && oltreCount <= 6)
    return { code: "C3", label: "Rischio alto", color: "text-orange-600 dark:text-orange-400" };
  // C2: 3 segnali e/o >6 oltre
  if (alertCount <= 3 && oltreCount <= 7)
    return { code: "C2", label: "Rischio grave", color: "text-red-600 dark:text-red-400" };
  // C1: 3+ segnali e >5 oltre
  if (alertCount >= 3 && oltreCount > 5)
    return { code: "C1", label: "Pre-crisi", color: "text-red-600 dark:text-red-400" };
  // D: 4+ segnali + 5+ oltre
  return { code: "D", label: "Crisi", color: "text-red-600 dark:text-red-400" };
}

