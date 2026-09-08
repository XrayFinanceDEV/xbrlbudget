import { describe, expect, it } from "vitest";
import {
  CRISIS_SCORING_KEYS,
  INDICATOR_DEFS,
  buildIndicatorChartData,
  computeCrisisRating,
  crisisScores,
  computeIndicators,
  invertedScore,
  linearScore,
  safeDivide,
  scoreDotColor,
  scoreIndicator,
} from "./pratica-indicators";

/** Azienda sana: utile, poco debito, buona liquidita'. */
const BS_SANA: Record<string, number> = {
  sp02_immob_immateriali: 20_000,
  sp03_immob_materiali: 300_000,
  sp05_rimanenze: 150_000,
  sp06_crediti_breve: 250_000,
  sp09_disponibilita_liquide: 80_000,
  sp11_capitale: 100_000,
  sp12_riserve: 250_000,
  sp13_utile_perdita: 90_000,
  sp16_debiti_breve: 260_000,
  sp16a_debiti_banche_breve: 60_000,
  sp17_debiti_lungo: 100_000,
  sp17a_debiti_banche_lungo: 100_000,
};

const IS_SANA: Record<string, number> = {
  ce01_ricavi_vendite: 1_200_000,
  ce05_materie_prime: 400_000,
  ce06_servizi: 300_000,
  ce08_costi_personale: 250_000,
  ce09_ammortamenti: 50_000,
  ce15_oneri_finanziari: 12_000,
  ce20_imposte: 30_000,
};

describe("linearScore / invertedScore", () => {
  it("clampa agli estremi", () => {
    expect(linearScore(0, 1, 2)).toBe(0);
    expect(linearScore(5, 1, 2)).toBe(1);
  });

  it("interpola linearmente a meta' scala", () => {
    expect(linearScore(1.5, 1, 2)).toBeCloseTo(0.5, 10);
  });

  it("invertedScore e' il complemento a 1", () => {
    expect(invertedScore(1.5, 1, 2)).toBeCloseTo(0.5, 10);
    expect(invertedScore(0, 1, 2)).toBe(1);
  });
});

describe("safeDivide", () => {
  it("divide normalmente", () => {
    expect(safeDivide(10, 4)).toBe(2.5);
  });

  it("denominatore zero: restituisce 0, non Infinity", () => {
    expect(safeDivide(10, 0)).toBe(0);
  });
});

/**
 * Come BS_SANA ma con crediti esigibili oltre l'esercizio successivo (sp07):
 * pin per il fix "sp07_crediti_lungo assente dal totale attivo".
 */
const BS_CON_SP07: Record<string, number> = {
  ...BS_SANA,
  sp07_crediti_lungo: 120_000,
};

describe("computeIndicators", () => {
  const ind = computeIndicators(BS_SANA, IS_SANA);

  it("produce tutti i campi dell'IndicatorSet", () => {
    for (const k of [
      "dscr", "ebitda_margin", "mt", "ccn", "current_ratio", "ms",
      "copertura_immob", "indipendenza", "pfn", "pfn_ebitda",
      "roi", "roe", "ros", "of_mol", "of_revenue",
      "materials_revenue", "services_revenue",
      "_ebitda_raw", "_quick_ratio", "_equity_over_fixed", "_revenue_raw",
    ]) {
      expect(Number.isFinite(ind[k as keyof typeof ind])).toBe(true);
    }
  });

  it("EBITDA = VP - costi operativi, ammortamenti esclusi", () => {
    // 1.200.000 - (400.000 + 300.000 + 250.000) = 250.000
    expect(ind._ebitda_raw).toBeCloseTo(250_000, 2);
  });

  it("margine EBITDA in percentuale assoluta, non in decimali", () => {
    expect(ind.ebitda_margin).toBeGreaterThan(1);
    expect(ind.ebitda_margin).toBeCloseTo(250_000 / 1_200_000 * 100, 2);
  });

  it("bilancio vuoto: nessun NaN ne' Infinity", () => {
    const empty = computeIndicators({}, {});
    for (const value of Object.values(empty)) {
      expect(Number.isFinite(value)).toBe(true);
    }
  });

  it("sp07_crediti_lungo entra nel totale attivo: indipendenza e ROI per valore esatto", () => {
    // fixedAssets = 20.000 + 300.000 = 320.000
    // currentAssets = 150.000 (rimanenze) + 250.000 (sp06) + 80.000 (cassa) = 480.000
    // totalAssets = fixedAssets + currentAssets + sp07 (120.000) = 920.000
    // equity = 100.000 + 250.000 + 90.000 = 440.000
    // indipendenza = equity / totalAssets * 100
    const conSp07 = computeIndicators(BS_CON_SP07, IS_SANA);
    expect(conSp07.indipendenza).toBeCloseTo((440_000 / 920_000) * 100, 6);
    // ebit = ebitda (250.000) - ammortamenti (50.000) = 200.000
    // roi = ebit / totalAssets * 100
    expect(conSp07.roi).toBeCloseTo((200_000 / 920_000) * 100, 6);
  });

  it("sp07_crediti_lungo non entra nell'attivo circolante: current_ratio invariato", () => {
    // sp07 e' escluso da currentAssets per costruzione: aggiungerlo al bilancio
    // non deve spostare il current_ratio, solo il totale attivo (test sopra).
    const senzaSp07 = computeIndicators(BS_SANA, IS_SANA);
    const conSp07 = computeIndicators(BS_CON_SP07, IS_SANA);
    expect(conSp07.current_ratio).toBeCloseTo(senzaSp07.current_ratio, 10);
    expect(conSp07.current_ratio).toBeCloseTo(480_000 / 260_000, 10);
  });
});

describe("scoreIndicator", () => {
  const ind = computeIndicators(BS_SANA, IS_SANA);

  it("ogni punteggio sta in [0,1]", () => {
    for (const k of ["dscr", "ebitda_margin", "current_ratio", "indipendenza",
                     "roi", "roe", "ros", "pfn_ebitda", "of_mol"] as const) {
      const s = scoreIndicator(k, ind);
      expect(s).toBeGreaterThanOrEqual(0);
      expect(s).toBeLessThanOrEqual(1);
    }
  });

  it("EBITDA negativo con PFN positiva: pfn_ebitda vale 0", () => {
    const bad = { ...ind, _ebitda_raw: -10_000, pfn: 50_000, pfn_ebitda: -5 };
    expect(scoreIndicator("pfn_ebitda", bad)).toBe(0);
  });

  it("EBITDA negativo senza oneri finanziari: of_mol vale 0,5", () => {
    const bad = { ...ind, _ebitda_raw: -10_000, of_mol: 0 };
    expect(scoreIndicator("of_mol", bad)).toBe(0.5);
  });
});

describe("computeCrisisRating", () => {
  it("nessun indicatore oltre soglia e nessun segnale: A3", () => {
    expect(computeCrisisRating([1, 1, 1, 0.9], 0).code).toBe("A3");
  });

  it("due indicatori oltre soglia e nessun segnale: A2", () => {
    expect(computeCrisisRating([0.1, 0.2, 1, 1], 0).code).toBe("A2");
  });

  it("i segnali extracontabili peggiorano il rating", () => {
    // `!==` da solo sopravvive a una mutazione che invertisse la direzione
    // (più segnali → rating MIGLIORE): si fissano i due codici concreti letti
    // dall'implementazione, non solo la loro diversità. I codici sono
    // ordinati dal migliore al peggiore (A3 > A2 > A1 > B3 > B2 > B1 > C3 >
    // C2 > C1 > D): "senza" deve restare il migliore possibile, "con" deve
    // essere effettivamente peggiore, non un codice qualunque diverso.
    const senza = computeCrisisRating([1, 1, 1, 1], 0).code;
    const con = computeCrisisRating([1, 1, 1, 1], 3).code;
    expect(senza).toBe("A3");
    expect(con).toBe("C3");
  });
});

describe("scoreDotColor", () => {
  it("verde sopra 0,67, giallo in mezzo, rosso sotto 0,33", () => {
    // Valori esatti, non solo differenza a coppie: una mutazione che
    // scambiasse verde e rosso (buono↔cattivo su un rating di rischio
    // creditizio) sopravviverebbe a un semplice `not.toBe`.
    expect(scoreDotColor(0.9)).toBe("bg-green-500");
    expect(scoreDotColor(0.5)).toBe("bg-yellow-500");
    expect(scoreDotColor(0.1)).toBe("bg-red-500");
  });
});

// «Oneri finanziari su fatturato» e' un indicatore NUOVO, non un rinominato:
// `of_mol` risponde a un'altra domanda (quanto pesano gli oneri sulla capacita'
// di generare cassa, non sul giro d'affari) ed e' quello usato dal punteggio.
describe("of_revenue — oneri finanziari su fatturato", () => {
  it("e' oneri finanziari sui ricavi, in percentuale assoluta", () => {
    const ind = computeIndicators(BS_SANA, IS_SANA);
    // 12.000 / 1.200.000 = 1%
    expect(ind.of_revenue).toBeCloseTo(1, 10);
  });

  it("non e' of_mol: stesso numeratore, denominatore diverso", () => {
    const ind = computeIndicators(BS_SANA, IS_SANA);
    // MOL = 250.000, ricavi = 1.200.000: i due rapporti non possono coincidere
    expect(ind.of_mol).toBeCloseTo(12_000 / 250_000 * 100, 10);
    expect(ind.of_revenue).not.toBeCloseTo(ind.of_mol, 3);
  });

  // Il difetto che la spec chiama per nome: `scoreIndicator` ha
  // `default: return 0.5`, quindi un indicatore aggiunto a INDICATOR_DEFS
  // senza il proprio `case` prende punteggio neutro su OGNI azienda — pallino
  // giallo per tutti, per sempre, senza errore e senza test rosso.
  it("ha una regola di punteggio propria, non il neutro di default", () => {
    const buona = computeIndicators(BS_SANA, { ...IS_SANA, ce15_oneri_finanziari: 12_000 });
    const pessima = computeIndicators(BS_SANA, { ...IS_SANA, ce15_oneri_finanziari: 72_000 });
    expect(buona.of_revenue).toBeCloseTo(1, 10);
    expect(pessima.of_revenue).toBeCloseTo(6, 10);

    const sBuona = scoreIndicator("of_revenue", buona);
    const sPessima = scoreIndicator("of_revenue", pessima);
    expect(sBuona).toBe(1);      // <=1% dei ricavi: ottimo
    expect(sPessima).toBe(0);    // >=5% dei ricavi: critico
    expect(sBuona).not.toBe(0.5);
    expect(sPessima).not.toBe(0.5);
  });

  it("interpola fra le due soglie", () => {
    const media = computeIndicators(BS_SANA, { ...IS_SANA, ce15_oneri_finanziari: 36_000 });
    expect(media.of_revenue).toBeCloseTo(3, 10);
    expect(scoreIndicator("of_revenue", media)).toBeCloseTo(0.5, 10);
  });

  // Denominatore degenere. `safeDivide` restituisce 0, e su un punteggio
  // INVERTITO uno zero significherebbe «ottimo»: senza il ramo dedicato
  // un'azienda senza ricavi risulterebbe la piu' sana del corpus, e sarebbe
  // indistinguibile da una che oneri finanziari non ne ha davvero. E'
  // l'asimmetria che gli altri rapporti sui ricavi non hanno — `ros` ed
  // `ebitda_margin` sono punteggi diretti, dove lo zero degenera da solo.
  it("ricavi a zero non producono un verdetto di eccellenza", () => {
    const senzaRicavi = computeIndicators(BS_SANA, { ...IS_SANA, ce01_ricavi_vendite: 0 });
    expect(senzaRicavi.of_revenue).toBe(0);
    expect(scoreIndicator("of_revenue", senzaRicavi)).not.toBe(1);
  });

  // Un denominatore assente e' «non lo so», non una contraddizione: un
  // verdetto negativo vuole una contraddizione misurata.
  it("ricavi a zero danno il neutro, non una condanna", () => {
    const senzaRicavi = computeIndicators(BS_SANA, { ...IS_SANA, ce01_ricavi_vendite: 0 });
    expect(scoreIndicator("of_revenue", senzaRicavi)).toBe(0.5);
  });

  // Il neutro degenere NON e' il neutro di `default`: senza il `case`, anche
  // un'azienda con ricavi veri prenderebbe 0,5.
  it("il neutro vale solo sul degenere, non su un'azienda con ricavi", () => {
    const conRicavi = computeIndicators(BS_SANA, IS_SANA);
    expect(conRicavi._revenue_raw).toBeGreaterThan(0);
    expect(scoreIndicator("of_revenue", conRicavi)).not.toBe(0.5);
  });

  it("oneri finanziari a zero, con ricavi veri, restano un'eccellenza", () => {
    const senzaOneri = computeIndicators(BS_SANA, { ...IS_SANA, ce15_oneri_finanziari: 0 });
    expect(scoreIndicator("of_revenue", senzaOneri)).toBe(1);
  });

  it("of_mol resta invariato nel calcolo e nel punteggio", () => {
    const ind = computeIndicators(BS_SANA, IS_SANA);
    expect(ind.of_mol).toBeCloseTo(4.8, 10);
    expect(scoreIndicator("of_mol", ind)).toBeCloseTo(invertedScore(4.8, 5, 30), 10);
  });

  it("compare in tabella accanto agli altri", () => {
    const riga = INDICATOR_DEFS.find((d) => d.key === "of_revenue");
    expect(riga).toBeDefined();
    expect(riga!.format).toBe("pct");
    // e of_mol non e' stato sostituito
    expect(INDICATOR_DEFS.some((d) => d.key === "of_mol")).toBe(true);
  });
});

// `computeCrisisRating` conta quanti punteggi stanno sotto 0,33, e le sue
// bande (0 / 1-2 / 3 / 4-5 «oltre») sono tarate sul NUMERO di indicatori che
// le alimentano. Un indicatore in piu' sposta quindi la classe di rischio di
// aziende reali senza che nessuno l'abbia deciso.
describe("of_revenue non entra nel punteggio di crisi", () => {
  it("il set del punteggio esclude of_revenue e tiene of_mol", () => {
    expect(CRISIS_SCORING_KEYS).not.toContain("of_revenue");
    expect(CRISIS_SCORING_KEYS).toContain("of_mol");
  });

  it("il set del punteggio ha un elemento in meno della tabella", () => {
    expect(CRISIS_SCORING_KEYS.length).toBe(INDICATOR_DEFS.length - 1);
  });

  // Oneri finanziari al 6% dei ricavi: `of_revenue` prende 0, cioe' sarebbe un
  // «oltre» in piu'. Il conteggio del punteggio non deve muoversi.
  it("un of_revenue pessimo non aggiunge un «oltre» al punteggio", () => {
    const ind = computeIndicators(BS_SANA, { ...IS_SANA, ce15_oneri_finanziari: 72_000 });
    expect(scoreIndicator("of_revenue", ind)).toBe(0);

    const oltreConTutti = INDICATOR_DEFS
      .map((d) => scoreIndicator(d.key, ind))
      .filter((s) => s < 0.33).length;
    const oltreDelPunteggio = crisisScores(ind).filter((s) => s < 0.33).length;

    expect(oltreDelPunteggio).toBe(oltreConTutti - 1);
  });

  it("crisisScores e' allineato a CRISIS_SCORING_KEYS", () => {
    const ind = computeIndicators(BS_SANA, IS_SANA);
    expect(crisisScores(ind)).toEqual(
      CRISIS_SCORING_KEYS.map((k) => scoreIndicator(k, ind)),
    );
  });
});

// #29. La #25 aveva chiuso la RESA — sul grafico `dscr` e `roe` valgono `null`
// quando il loro denominatore non esiste — ma il PUNTEGGIO era rimasto a 0, e
// 0 e' sotto 0,33, cioe' un «oltre soglia». Un'azienda SENZA oneri finanziari,
// che su quell'indicatore e' la piu' sana possibile, veniva spinta in una
// classe di rischio peggiore proprio dall'assenza di debito oneroso.
describe("i denominatori che non esistono non producono un «oltre» (#29)", () => {
  it("senza oneri finanziari il DSCR vale 0,5, non 0", () => {
    const ind = computeIndicators(BS_SANA, { ...IS_SANA, ce15_oneri_finanziari: 0 });
    expect(ind._oneri_finanziari_raw).toBe(0);
    expect(scoreIndicator("dscr", ind)).toBe(0.5);
  });

  it("con oneri finanziari il DSCR resta quello di prima", () => {
    // La correzione tocca il solo ramo degenere: dove il rapporto esiste, la
    // scala CNDCEC (1,0 / 1,5) e' intatta.
    const ind = computeIndicators(BS_SANA, IS_SANA);
    expect(ind._oneri_finanziari_raw).toBeGreaterThan(0);
    expect(scoreIndicator("dscr", ind)).toBe(linearScore(ind.dscr, 1.0, 1.5));
  });

  it("un DSCR davvero basso resta 0: il ramo degenere non e' una scappatoia", () => {
    const ind = computeIndicators(BS_SANA, {
      ...IS_SANA,
      ce15_oneri_finanziari: 400_000,
    });
    expect(scoreIndicator("dscr", ind)).toBe(0);
  });

  it("a patrimonio netto nullo il ROE vale 0,5, non 0", () => {
    const bs = { ...BS_SANA, sp11_capitale: 0, sp12_riserve: 0, sp13_utile_perdita: 0 };
    const ind = computeIndicators(bs, IS_SANA);
    expect(ind._equity_raw).toBe(0);
    expect(scoreIndicator("roe", ind)).toBe(0.5);
  });

  it("a patrimonio netto NEGATIVO il ROE vale 0,5: il rapporto cambia segno per il denominatore", () => {
    // Un utile diviso un PN negativo esce negativo per il denominatore, non per
    // la redditivita': il numero non e' un ROE. Il dissesto lo contano gia'
    // `indipendenza`, `ms` e `copertura_immob`, che su un PN negativo vanno tutti
    // a zero — non serve contarlo una quarta volta con un rapporto senza senso.
    const bs = { ...BS_SANA, sp11_capitale: 10_000, sp12_riserve: 0, sp13_utile_perdita: -300_000 };
    const ind = computeIndicators(bs, IS_SANA);
    expect(ind._equity_raw).toBeLessThan(0);
    expect(scoreIndicator("roe", ind)).toBe(0.5);
    // Il dissesto resta contato altrove.
    expect(scoreIndicator("indipendenza", ind)).toBe(0);
    expect(scoreIndicator("ms", ind)).toBe(0);
  });

  it("con patrimonio netto positivo il ROE resta quello di prima", () => {
    const ind = computeIndicators(BS_SANA, IS_SANA);
    expect(ind._equity_raw).toBeGreaterThan(0);
    expect(scoreIndicator("roe", ind)).toBe(linearScore(ind.roe, 0, 12));
  });

  it("una perdita vera con patrimonio netto positivo resta 0", () => {
    const ind = computeIndicators(BS_SANA, { ...IS_SANA, ce05_materie_prime: 1_500_000 });
    expect(ind._equity_raw).toBeGreaterThan(0);
    expect(ind.roe).toBeLessThan(0);
    expect(scoreIndicator("roe", ind)).toBe(0);
  });

  it("il punteggio e' ora coerente col grafico: dove non c'e' punto, non c'e' «oltre»", () => {
    // E' la contraddizione che l'issue descrive: azienda sana e senza oneri
    // finanziari, nessun punto sul grafico «Sostenibilita' del debito» e nessun
    // «oltre» nel conteggio di crisi.
    const ind = computeIndicators(BS_SANA, { ...IS_SANA, ce15_oneri_finanziari: 0 });
    const [riga] = buildIndicatorChartData([{ periodo: "Storico", indicatori: ind }]);
    expect(riga.dscr).toBeNull();
    expect(scoreIndicator("dscr", ind)).toBeGreaterThanOrEqual(0.33);
  });

  it("le bande di computeCrisisRating restano tarate sullo stesso numero di indicatori", () => {
    // L'alternativa scartata era togliere `dscr` da `CRISIS_SCORING_KEYS`: le
    // bande sono calibrate sul NUMERO di indicatori che le alimentano, quindi
    // toglierne uno le sposta. Il conteggio non cambia, cambia solo il verdetto
    // del caso degenere.
    expect(CRISIS_SCORING_KEYS).toContain("dscr");
    expect(CRISIS_SCORING_KEYS).toContain("roe");
    expect(CRISIS_SCORING_KEYS.length).toBe(INDICATOR_DEFS.length - 1);
    expect(crisisScores(computeIndicators(BS_SANA, IS_SANA)).length).toBe(
      CRISIS_SCORING_KEYS.length,
    );
  });
});
