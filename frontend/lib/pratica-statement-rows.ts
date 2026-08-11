import type { IntraYearComparisonItem } from "@/types/api";
import { reconcileSubfields } from "@/lib/pratica-reconcile";
import { VP_CODES, ATTIVO_CODES, PASSIVO_CODES } from "@/lib/pratica-codes";
import { labelOf } from "@/lib/ivcee-catalog";

export function buildBalanceItemsWithTotals(
  rawItems: IntraYearComparisonItem[],
): IntraYearComparisonItem[] {
  // Reconcile sub-fields per year so debt/crediti/rimanenze details always show
  // when the parent aggregate has a value (common in bilancio abbreviato imports
  // where sub-fields arrive as 0 and the gap lives in the aggregate).
  const reconcilePerYear = (key: "partial_value" | "reference_value" | "prior_value") => {
    const data: Record<string, number> = {};
    for (const it of rawItems) data[it.code] = it[key] ?? 0;
    reconcileSubfields(data);
    return data;
  };
  const partialData = reconcilePerYear("partial_value");
  const refData = reconcilePerYear("reference_value");
  const priorData = reconcilePerYear("prior_value");
  const items: IntraYearComparisonItem[] = rawItems.map((it) => ({
    ...it,
    partial_value: partialData[it.code] ?? it.partial_value,
    reference_value: refData[it.code] ?? it.reference_value,
    prior_value: priorData[it.code] ?? it.prior_value,
    // Keep annualized_value as caller supplied — Projection tab writes projected BS
    // values there; for the Comparison tab the backend already mirrors partial into
    // annualized (BS is point-in-time).
  }));

  const byCode = new Map(items.map((i) => [i.code, i]));
  const safePct = (a: number, b: number) => (b !== 0 ? (a / b) * 100 : 0);

  const v = (code: string, key: "partial_value" | "reference_value" | "annualized_value" | "prior_value") =>
    byCode.get(code)?.[key] ?? 0;

  const makeRow = (code: string, label: string, partial: number, ref: number, annualized: number, prior: number = 0): IntraYearComparisonItem => ({
    code, label,
    partial_value: partial,
    reference_value: ref,
    prior_value: prior,
    pct_of_reference: safePct(partial, ref),
    annualized_value: annualized,
  });

  const hdr = (code: string, label: string): IntraYearComparisonItem =>
    makeRow(code, label, 0, 0, 0, 0);

  const item = (code: string): IntraYearComparisonItem =>
    byCode.get(code) ?? { code, label: code, partial_value: 0, reference_value: 0, prior_value: 0, pct_of_reference: 0, annualized_value: 0 };

  // Etichetta CONTESTUALE: qui la riga sta in un prospetto, sotto
  // l'intestazione del proprio aggregato, quindi la forma breve basta.
  // La forma autonoma serve altrove (giornale rettifiche, selettore).
  // Il rientro delle sotto-voci NON sta nel testo (le etichette del catalogo
  // non hanno spazi iniziali): lo applica chi rende la riga — pl-6 sui codici
  // di DETAIL_PARENTS in ComparisonTable/ProjectionTable.
  const labeled = (code: string): IntraYearComparisonItem => ({
    ...item(code),
    label: labelOf(code, "contestuale"),
  });

  // Subtotals
  const IMMOB_CODES = ["sp02_immob_immateriali", "sp03_immob_materiali", "sp04_immob_finanziarie"];
  const CIRC_CODES = ["sp05_rimanenze", "sp06_crediti_breve", "sp07_crediti_lungo", "sp08_attivita_finanziarie", "sp09_disponibilita_liquide"];
  const PN_CODES = ["sp11_capitale", "sp12_riserve", "sp13_utile_perdita"];
  const DEBT_CODES = ["sp16_debiti_breve", "sp17_debiti_lungo"];

  const sumCodes = (codes: string[], key: "partial_value" | "reference_value" | "annualized_value" | "prior_value") =>
    codes.reduce((acc, c) => acc + v(c, key), 0);

  const totImmobP = sumCodes(IMMOB_CODES, "partial_value");
  const totImmobR = sumCodes(IMMOB_CODES, "reference_value");
  const totImmobA = sumCodes(IMMOB_CODES, "annualized_value");
  const totImmobPr = sumCodes(IMMOB_CODES, "prior_value");

  const totCircP = sumCodes(CIRC_CODES, "partial_value");
  const totCircR = sumCodes(CIRC_CODES, "reference_value");
  const totCircA = sumCodes(CIRC_CODES, "annualized_value");
  const totCircPr = sumCodes(CIRC_CODES, "prior_value");

  const totAttivoP = sumCodes(ATTIVO_CODES, "partial_value");
  const totAttivoR = sumCodes(ATTIVO_CODES, "reference_value");
  const totAttivoA = sumCodes(ATTIVO_CODES, "annualized_value");
  const totAttivoPr = sumCodes(ATTIVO_CODES, "prior_value");

  const totPNP = sumCodes(PN_CODES, "partial_value");
  const totPNR = sumCodes(PN_CODES, "reference_value");
  const totPNA = sumCodes(PN_CODES, "annualized_value");
  const totPNPr = sumCodes(PN_CODES, "prior_value");

  const totDebtP = sumCodes(DEBT_CODES, "partial_value");
  const totDebtR = sumCodes(DEBT_CODES, "reference_value");
  const totDebtA = sumCodes(DEBT_CODES, "annualized_value");
  const totDebtPr = sumCodes(DEBT_CODES, "prior_value");

  const totPassivoP = sumCodes(PASSIVO_CODES, "partial_value");
  const totPassivoR = sumCodes(PASSIVO_CODES, "reference_value");
  const totPassivoA = sumCodes(PASSIVO_CODES, "annualized_value");
  const totPassivoPr = sumCodes(PASSIVO_CODES, "prior_value");

  return [
    // ATTIVO
    hdr("_hdr_attivo", "ATTIVO"),
    labeled("sp01_crediti_soci"),
    // B) IMMOBILIZZAZIONI
    hdr("_hdr_immob", "B) IMMOBILIZZAZIONI"),
    labeled("sp02_immob_immateriali"),
    labeled("sp03_immob_materiali"),
    labeled("sp04_immob_finanziarie"),
    labeled("sp04a_partecipazioni"),
    labeled("sp04b_crediti_immob_breve"),
    labeled("sp04c_crediti_immob_lungo"),
    labeled("sp04d_altri_titoli"),
    labeled("sp04e_strumenti_derivati_attivi"),
    makeRow("_totale_immob", "Totale Immobilizzazioni", totImmobP, totImmobR, totImmobA, totImmobPr),
    // C) ATTIVO CIRCOLANTE
    hdr("_hdr_circ", "C) ATTIVO CIRCOLANTE"),
    labeled("sp05_rimanenze"),
    labeled("sp06_crediti_breve"),
    labeled("sp06a_crediti_clienti_breve"),
    labeled("sp06b_crediti_controllate_breve"),
    labeled("sp06c_crediti_collegate_breve"),
    labeled("sp06d_crediti_controllanti_breve"),
    labeled("sp06e_crediti_tributari_breve"),
    labeled("sp06f_imposte_anticipate_breve"),
    labeled("sp06g_crediti_altri_breve"),
    labeled("sp07_crediti_lungo"),
    labeled("sp07a_crediti_clienti_lungo"),
    labeled("sp07b_crediti_controllate_lungo"),
    labeled("sp07c_crediti_collegate_lungo"),
    labeled("sp07d_crediti_controllanti_lungo"),
    labeled("sp07e_crediti_tributari_lungo"),
    labeled("sp07f_imposte_anticipate_lungo"),
    labeled("sp07g_crediti_altri_lungo"),
    labeled("sp08_attivita_finanziarie"),
    labeled("sp09_disponibilita_liquide"),
    makeRow("_totale_circ", "Totale Attivo Circolante", totCircP, totCircR, totCircA, totCircPr),
    // D) Ratei
    labeled("sp10_ratei_risconti_attivi"),
    makeRow("_totale_attivo", "TOTALE ATTIVO", totAttivoP, totAttivoR, totAttivoA, totAttivoPr),
    // PASSIVO E PATRIMONIO NETTO
    hdr("_hdr_passivo", "PASSIVO E PATRIMONIO NETTO"),
    // A) PATRIMONIO NETTO
    hdr("_hdr_pn", "A) PATRIMONIO NETTO"),
    labeled("sp11_capitale"),
    labeled("sp12a_riserva_sovrapprezzo"),
    labeled("sp12b_riserve_rivalutazione"),
    labeled("sp12c_riserva_legale"),
    labeled("sp12d_riserve_statutarie"),
    labeled("sp12e_altre_riserve"),
    labeled("sp12f_riserva_copertura_flussi"),
    labeled("sp12g_utili_perdite_portati"),
    labeled("sp13_utile_perdita"),
    labeled("sp12h_riserva_neg_azioni_proprie"),
    makeRow("_totale_pn", "Totale Patrimonio Netto", totPNP, totPNR, totPNA, totPNPr),
    // B) Fondi
    labeled("sp14_fondi_rischi"),
    // C) TFR
    labeled("sp15_tfr"),
    // D) DEBITI — grouped by creditor type (OIC art. 2424), each with entro/oltre sub-rows
    hdr("_hdr_debiti", "D) DEBITI"),
    ...(() => {
      const groupSum = (breve: string, lungo: string, key: "partial_value" | "reference_value" | "annualized_value" | "prior_value") =>
        v(breve, key) + v(lungo, key);
      const debtGroup = (code: string, label: string, breve: string, lungo: string): IntraYearComparisonItem[] => [
        makeRow(
          code, label,
          groupSum(breve, lungo, "partial_value"),
          groupSum(breve, lungo, "reference_value"),
          groupSum(breve, lungo, "annualized_value"),
          groupSum(breve, lungo, "prior_value"),
        ),
        labeled(breve),
        labeled(lungo),
      ];
      return [
        ...debtGroup("_debt_banche", "1) Debiti verso banche", "sp16a_debiti_banche_breve", "sp17a_debiti_banche_lungo"),
        ...debtGroup("_debt_altri_finanz", "2) Debiti verso altri finanziatori", "sp16b_debiti_altri_finanz_breve", "sp17b_debiti_altri_finanz_lungo"),
        ...debtGroup("_debt_obbligazioni", "3) Debiti obbligazionari", "sp16c_debiti_obbligazioni_breve", "sp17c_debiti_obbligazioni_lungo"),
        ...debtGroup("_debt_fornitori", "7) Debiti verso fornitori", "sp16d_debiti_fornitori_breve", "sp17d_debiti_fornitori_lungo"),
        ...debtGroup("_debt_tributari", "12) Debiti tributari", "sp16e_debiti_tributari_breve", "sp17e_debiti_tributari_lungo"),
        ...debtGroup("_debt_previdenza", "13) Debiti previdenziali", "sp16f_debiti_previdenza_breve", "sp17f_debiti_previdenza_lungo"),
        ...debtGroup("_debt_altri", "14) Altri debiti", "sp16g_altri_debiti_breve", "sp17g_altri_debiti_lungo"),
      ];
    })(),
    makeRow("_totale_debiti", "Totale Debiti", totDebtP, totDebtR, totDebtA, totDebtPr),
    // E) Ratei passivi
    labeled("sp18_ratei_risconti_passivi"),
    makeRow("_totale_passivo", "TOTALE PASSIVO E PATRIMONIO NETTO", totPassivoP, totPassivoR, totPassivoA, totPassivoPr),
    // Differenza
    makeRow("_differenza", "DIFFERENZA (Attivo - Passivo)",
      totAttivoP - totPassivoP, totAttivoR - totPassivoR, totAttivoA - totPassivoA, totAttivoPr - totPassivoPr),
  ];
}

export function buildIncomeItemsWithEbitda(
  items: IntraYearComparisonItem[],
  periodMonths: number,
): IntraYearComparisonItem[] {
  const byCode = new Map(items.map((i) => [i.code, i]));
  const factor = 12 / periodMonths;
  const safePct = (a: number, b: number) => (b !== 0 ? (a / b) * 100 : 0);

  const v = (code: string, key: "partial_value" | "reference_value" | "prior_value") =>
    byCode.get(code)?.[key] ?? 0;
  const ann = (code: string) => byCode.get(code)?.annualized_value ?? 0;
  const sum = (codes: string[], key: "partial_value" | "reference_value" | "prior_value") =>
    codes.reduce((acc, c) => acc + v(c, key), 0);
  const sumAnn = (codes: string[]) =>
    codes.reduce((acc, c) => acc + ann(c), 0);

  // Lookup or zero-item helper
  const item = (code: string): IntraYearComparisonItem =>
    byCode.get(code) ?? { code, label: code, partial_value: 0, reference_value: 0, prior_value: 0, pct_of_reference: 0, annualized_value: 0 };

  // Helper: create a synthetic row
  const makeRow = (code: string, label: string, partial: number, ref: number, annualized: number, prior: number = 0): IntraYearComparisonItem => ({
    code, label,
    partial_value: partial,
    reference_value: ref,
    prior_value: prior,
    pct_of_reference: safePct(partial, ref),
    annualized_value: annualized,
  });

  // Header row (no values)
  const hdr = (code: string, label: string): IntraYearComparisonItem =>
    makeRow(code, label, 0, 0, 0, 0);

  // Subtotals
  const partialVP = sum(VP_CODES, "partial_value");
  const refVP = sum(VP_CODES, "reference_value");
  const priorVP = sum(VP_CODES, "prior_value");
  const annVP = sumAnn(VP_CODES);

  const COST_CODES_ALL = ["ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
    "ce08_costi_personale", "ce09_ammortamenti", "ce10_var_rimanenze_mat_prime",
    "ce11_accantonamenti", "ce11b_altri_accantonamenti", "ce12_oneri_diversi"];
  const partialCP = sum(COST_CODES_ALL, "partial_value");
  const refCP = sum(COST_CODES_ALL, "reference_value");
  const priorCP = sum(COST_CODES_ALL, "prior_value");
  const annCP = sumAnn(COST_CODES_ALL);

  const partialEbitda = partialVP - (partialCP - v("ce09_ammortamenti", "partial_value"));
  const refEbitda = refVP - (refCP - v("ce09_ammortamenti", "reference_value"));
  const priorEbitda = priorVP - (priorCP - v("ce09_ammortamenti", "prior_value"));
  const annEbitda = annVP - (annCP - ann("ce09_ammortamenti"));

  const partialEbit = partialVP - partialCP;
  const refEbit = refVP - refCP;
  const priorEbit = priorVP - priorCP;
  const annEbit = annVP - annCP;

  const FIN_INCOME = ["ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari", "ce16_utili_perdite_cambi"];
  const FIN_COST = ["ce15_oneri_finanziari"];
  const partialFin = sum(FIN_INCOME, "partial_value") - sum(FIN_COST, "partial_value");
  const refFin = sum(FIN_INCOME, "reference_value") - sum(FIN_COST, "reference_value");
  const priorFin = sum(FIN_INCOME, "prior_value") - sum(FIN_COST, "prior_value");
  const annFin = sumAnn(FIN_INCOME) - sumAnn(FIN_COST);

  const partialStraord = v("ce18_proventi_straordinari", "partial_value") - v("ce19_oneri_straordinari", "partial_value");
  const refStraord = v("ce18_proventi_straordinari", "reference_value") - v("ce19_oneri_straordinari", "reference_value");
  const priorStraord = v("ce18_proventi_straordinari", "prior_value") - v("ce19_oneri_straordinari", "prior_value");
  const annStraord = ann("ce18_proventi_straordinari") - ann("ce19_oneri_straordinari");

  const partialRettifiche = v("ce17_rettifiche_attivita_fin", "partial_value");
  const refRettifiche = v("ce17_rettifiche_attivita_fin", "reference_value");
  const priorRettifiche = v("ce17_rettifiche_attivita_fin", "prior_value");
  const annRettifiche = ann("ce17_rettifiche_attivita_fin");

  const partialPBT = partialEbit + partialFin + partialRettifiche + partialStraord;
  const refPBT = refEbit + refFin + refRettifiche + refStraord;
  const priorPBT = priorEbit + priorFin + priorRettifiche + priorStraord;
  const annPBT = annEbit + annFin + annRettifiche + annStraord;

  const partialNetProfit = partialPBT - v("ce20_imposte", "partial_value");
  const refNetProfit = refPBT - v("ce20_imposte", "reference_value");
  const priorNetProfit = priorPBT - v("ce20_imposte", "prior_value");
  const annNetProfit = annPBT - ann("ce20_imposte");

  const partialRevenue = v("ce01_ricavi_vendite", "partial_value");
  const refRevenue = v("ce01_ricavi_vendite", "reference_value");

  // Etichetta CONTESTUALE: qui la riga sta in un prospetto, sotto
  // l'intestazione del proprio aggregato, quindi la forma breve basta.
  // La forma autonoma serve altrove (giornale rettifiche, selettore).
  // Il rientro delle sotto-voci NON sta nel testo (le etichette del catalogo
  // non hanno spazi iniziali): lo applica chi rende la riga — pl-6 sui codici
  // di DETAIL_PARENTS in ComparisonTable/ProjectionTable.
  const labeled = (code: string): IntraYearComparisonItem => ({
    ...item(code),
    label: labelOf(code, "contestuale"),
  });

  return [
    // A) VALORE DELLA PRODUZIONE
    hdr("_hdr_a", "A) VALORE DELLA PRODUZIONE"),
    labeled("ce01_ricavi_vendite"),
    labeled("ce02_variazioni_rimanenze"),
    labeled("ce03_lavori_interni"),
    labeled("ce04_altri_ricavi"),
    makeRow("_totale_vp", "Totale Valore della Produzione", partialVP, refVP, annVP, priorVP),
    // B) COSTI DELLA PRODUZIONE
    hdr("_hdr_b", "B) COSTI DELLA PRODUZIONE"),
    labeled("ce05_materie_prime"),
    labeled("ce06_servizi"),
    labeled("ce07_godimento_beni"),
    labeled("ce08_costi_personale"),
    labeled("ce08b_salari_stipendi"),
    labeled("ce08c_oneri_sociali"),
    labeled("ce08a_tfr_accrual"),
    labeled("ce08d_altri_costi_personale"),
    labeled("ce09_ammortamenti"),
    labeled("ce09a_ammort_immateriali"),
    labeled("ce09b_ammort_materiali"),
    labeled("ce09c_svalutazioni"),
    labeled("ce09d_svalutazione_crediti"),
    labeled("ce10_var_rimanenze_mat_prime"),
    labeled("ce11_accantonamenti"),
    labeled("ce11b_altri_accantonamenti"),
    labeled("ce12_oneri_diversi"),
    makeRow("_totale_cp", "Totale Costi della Produzione", partialCP, refCP, annCP, priorCP),
    makeRow("_ebitda", "EBITDA (MOL)", partialEbitda, refEbitda, annEbitda, priorEbitda),
    makeRow("_ebit", "EBIT (Risultato Operativo)", partialEbit, refEbit, annEbit, priorEbit),
    // C) PROVENTI E ONERI FINANZIARI
    hdr("_hdr_c", "C) PROVENTI E ONERI FINANZIARI"),
    labeled("ce13_proventi_partecipazioni"),
    labeled("ce14_altri_proventi_finanziari"),
    labeled("ce15_oneri_finanziari"),
    labeled("ce16_utili_perdite_cambi"),
    makeRow("_totale_fin", "Totale proventi e oneri finanziari (15 + 16 - 17 +/- 17-bis)", partialFin, refFin, annFin, priorFin),
    // D) RETTIFICHE DI VALORE
    hdr("_hdr_d", "D) RETTIFICHE DI VALORE DI ATTIVITÀ E PASSIVITÀ FINANZIARIE"),
    labeled("ce17a_rivalutazioni"),
    labeled("ce17b_svalutazioni"),
    labeled("ce17_rettifiche_attivita_fin"),
    // E) PROVENTI E ONERI STRAORDINARI
    hdr("_hdr_e", "E) PROVENTI E ONERI STRAORDINARI"),
    labeled("ce18_proventi_straordinari"),
    labeled("ce19_oneri_straordinari"),
    makeRow("_totale_straord", "Totale Proventi/Oneri Straordinari", partialStraord, refStraord, annStraord, priorStraord),
    // Risultato prima delle imposte
    makeRow("_profit_before_tax", "Risultato prima delle imposte (A - B +/- C +/- D +/- E)", partialPBT, refPBT, annPBT, priorPBT),
    labeled("ce20_imposte"),
    makeRow("_net_profit", "21) Utile (perdita) dell'esercizio", partialNetProfit, refNetProfit, annNetProfit, priorNetProfit),
  ];
}

