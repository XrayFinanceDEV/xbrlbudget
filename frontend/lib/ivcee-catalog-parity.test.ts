import { describe, expect, it } from "vitest";
import { BALANCE_HIERARCHY_GROUPS, BALANCE_STATEMENT_ROWS, INCOME_STATEMENT_ROWS, VOCI, aggregate, labelOf, voce } from "@/lib/ivcee-catalog";
import {
  CE_A, CE_B, CE_C, CE_D, CE_E, CE_IMPOSTE,
  COUNTERPART_PICKER_LABELS,
  DEBT_GROUPS,
  RETTIFICHE_BS_ATTIVO, RETTIFICHE_BS_OTHER_PASSIVO, RETTIFICHE_BS_PN,
  RETTIFICHE_LABELS,
} from "@/lib/pratica-rettifiche-rules";
import {
  buildBalanceItemsWithTotals,
  buildIncomeItemsWithEbitda,
} from "@/lib/pratica-statement-rows";
import type { IntraYearComparisonItem } from "@/types/api";

/** Una riga di prospetto: il campo se c'è, altrimenti un marcatore stabile. */
const rowKey = (r: { field?: string; label: string }) => r.field ?? `computed:${r.label}`;

/** Ordine di resa di RettificheTab: attivo, PN, altri passivi, gruppi debiti, CE. */
const rettificheCodes = (): string[] => [
  ...RETTIFICHE_BS_ATTIVO,
  ...RETTIFICHE_BS_PN,
  ...RETTIFICHE_BS_OTHER_PASSIVO,
  ...DEBT_GROUPS.flatMap((g) => [...g.entro, ...g.oltre]),
  ...CE_A, ...CE_B, ...CE_C, ...CE_D, ...CE_E, ...CE_IMPOSTE,
];

const item = (code: string): IntraYearComparisonItem => ({
  code, label: code,
  partial_value: 1000, reference_value: 900, prior_value: 800,
  pct_of_reference: 0, annualized_value: 0,
});

/** Fixture: ogni codice che le viste possono ricevere dal server. */
const BS_FIXTURE = [
  "sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
  "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve",
  "sp07_crediti_lungo", "sp08_attivita_finanziarie", "sp09_disponibilita_liquide",
  "sp10_ratei_risconti_attivi", "sp11_capitale", "sp12_riserve",
  "sp13_utile_perdita", "sp14_fondi_rischi", "sp15_tfr",
  "sp16_debiti_breve", "sp17_debiti_lungo", "sp18_ratei_risconti_passivi",
].map(item);

const CE_FIXTURE = [
  "ce01_ricavi_vendite", "ce02_variazioni_rimanenze", "ce03_lavori_interni",
  "ce04_altri_ricavi", "ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
  "ce08_costi_personale", "ce09_ammortamenti", "ce10_var_rimanenze_mat_prime",
  "ce11_accantonamenti", "ce12_oneri_diversi", "ce13_proventi_partecipazioni",
  "ce14_altri_proventi_finanziari", "ce15_oneri_finanziari", "ce16_utili_perdite_cambi",
  "ce17_rettifiche_attivita_fin", "ce18_proventi_straordinari",
  "ce19_oneri_straordinari", "ce20_imposte",
].map(item);

// Generato al Task 1 dallo stato pre-refactoring. Questi elenchi NON vanno
// aggiornati per far passare un test: se cambiano, una vista ha perso o
// riordinato una riga, ed è quello il difetto.
const ATTESI_BALANCE: string[] = [
  "computed:ATTIVO",
  "sp01_crediti_soci",
  "computed:B) IMMOBILIZZAZIONI",
  "sp02_immob_immateriali",
  "sp03_immob_materiali",
  "sp04_immob_finanziarie",
  "sp04a_partecipazioni",
  "sp04b_crediti_immob_breve",
  "sp04c_crediti_immob_lungo",
  "computed:Totale crediti immobilizzati",
  "sp04d_altri_titoli",
  "sp04e_strumenti_derivati_attivi",
  "fixed_assets",
  "computed:C) ATTIVO CIRCOLANTE",
  "sp05_rimanenze",
  "sp05a_materie_prime",
  "sp05b_prodotti_in_corso",
  "sp05c_lavori_in_corso",
  "sp05d_prodotti_finiti",
  "sp05e_acconti",
  "sp06_crediti_breve",
  "sp06a_crediti_clienti_breve",
  "sp06b_crediti_controllate_breve",
  "sp06c_crediti_collegate_breve",
  "sp06d_crediti_controllanti_breve",
  "sp06e_crediti_tributari_breve",
  "sp06f_imposte_anticipate_breve",
  "sp06g_crediti_altri_breve",
  "sp07_crediti_lungo",
  "sp07a_crediti_clienti_lungo",
  "sp07b_crediti_controllate_lungo",
  "sp07c_crediti_collegate_lungo",
  "sp07d_crediti_controllanti_lungo",
  "sp07e_crediti_tributari_lungo",
  "sp07f_imposte_anticipate_lungo",
  "sp07g_crediti_altri_lungo",
  "sp08_attivita_finanziarie",
  "sp09_disponibilita_liquide",
  "current_assets",
  "sp10_ratei_risconti_attivi",
  "total_assets",
  "computed:PASSIVO E PATRIMONIO NETTO",
  "computed:A) PATRIMONIO NETTO",
  "sp11_capitale",
  "sp12a_riserva_sovrapprezzo",
  "sp12b_riserve_rivalutazione",
  "sp12c_riserva_legale",
  "sp12d_riserve_statutarie",
  "sp12e_altre_riserve",
  "sp12f_riserva_copertura_flussi",
  "sp12g_utili_perdite_portati",
  "sp12h_riserva_neg_azioni_proprie",
  "sp13_utile_perdita",
  "computed:Totale patrimonio netto",
  "sp14_fondi_rischi",
  "sp14a_fondi_trattamento_quiescenza",
  "sp14b_fondi_imposte",
  "sp14c_strumenti_derivati_passivi",
  "sp14d_altri_fondi",
  "sp15_tfr",
  "computed:D) DEBITI",
  "computed:Banche",
  "sp16a_debiti_banche_breve",
  "sp17a_debiti_banche_lungo",
  "computed:Altri finanziatori",
  "sp16b_debiti_altri_finanz_breve",
  "sp17b_debiti_altri_finanz_lungo",
  "computed:Obbligazioni",
  "sp16c_debiti_obbligazioni_breve",
  "sp17c_debiti_obbligazioni_lungo",
  "computed:Fornitori",
  "sp16d_debiti_fornitori_breve",
  "sp17d_debiti_fornitori_lungo",
  "computed:Debiti tributari",
  "sp16e_debiti_tributari_breve",
  "sp17e_debiti_tributari_lungo",
  "computed:Debiti previdenziali",
  "sp16f_debiti_previdenza_breve",
  "sp17f_debiti_previdenza_lungo",
  "computed:Altri debiti",
  "sp16g_altri_debiti_breve",
  "sp17g_altri_debiti_lungo",
  "computed:Totale debiti",
  "sp18_ratei_risconti_passivi",
  "computed:TOTALE PASSIVO E PATRIMONIO NETTO",
  "computed:DIFFERENZA (Attivo - Passivo)",
];
const ATTESI_INCOME: string[] = [
  "computed:A) VALORE DELLA PRODUZIONE",
  "ce01_ricavi_vendite",
  "ce02_variazioni_rimanenze",
  "ce03_lavori_interni",
  "ce03a_incrementi_immobilizzazioni",
  "ce04_altri_ricavi",
  "production_value",
  "computed:B) COSTI DELLA PRODUZIONE",
  "ce05_materie_prime",
  "ce06_servizi",
  "ce07_godimento_beni",
  "ce08_costi_personale",
  "ce08b_salari_stipendi",
  "ce08c_oneri_sociali",
  "ce08a_tfr_accrual",
  "computed:d) Trattamento di quiescenza e simili",
  "ce08d_altri_costi_personale",
  "computed:10) Ammortamenti e svalutazioni:",
  "ce09a_ammort_immateriali",
  "ce09b_ammort_materiali",
  "ce09c_svalutazioni",
  "ce09d_svalutazione_crediti",
  "ce09_ammortamenti",
  "ce10_var_rimanenze_mat_prime",
  "ce11_accantonamenti",
  "ce11b_altri_accantonamenti",
  "ce12_oneri_diversi",
  "production_cost",
  "ebitda",
  "ebit",
  "computed:C) PROVENTI E ONERI FINANZIARI",
  "ce13_proventi_partecipazioni",
  "ce14_altri_proventi_finanziari",
  "ce15_oneri_finanziari",
  "ce16_utili_perdite_cambi",
  "financial_result",
  "computed:D) RETTIFICHE DI VALORE ATTIVITA' FINANZIARIE",
  "ce17a_rivalutazioni",
  "ce17b_svalutazioni",
  "ce17_rettifiche_attivita_fin",
  "computed:E) PROVENTI E ONERI STRAORDINARI",
  "ce18_proventi_straordinari",
  "ce19_oneri_straordinari",
  "extraordinary_result",
  "profit_before_tax",
  "ce20_imposte",
  "net_profit",
];
const ATTESI_RETTIFICHE: string[] = [
  "sp01_crediti_soci",
  "sp02_immob_immateriali",
  "sp03_immob_materiali",
  "sp04_immob_finanziarie",
  "sp04a_partecipazioni",
  "sp04b_crediti_immob_breve",
  "sp04c_crediti_immob_lungo",
  "sp04d_altri_titoli",
  "sp04e_strumenti_derivati_attivi",
  "sp05_rimanenze",
  "sp05a_materie_prime",
  "sp05b_prodotti_in_corso",
  "sp05c_lavori_in_corso",
  "sp05d_prodotti_finiti",
  "sp05e_acconti",
  "sp06_crediti_breve",
  "sp06a_crediti_clienti_breve",
  "sp06b_crediti_controllate_breve",
  "sp06c_crediti_collegate_breve",
  "sp06d_crediti_controllanti_breve",
  "sp06e_crediti_tributari_breve",
  "sp06f_imposte_anticipate_breve",
  "sp06g_crediti_altri_breve",
  "sp07_crediti_lungo",
  "sp07a_crediti_clienti_lungo",
  "sp07b_crediti_controllate_lungo",
  "sp07c_crediti_collegate_lungo",
  "sp07d_crediti_controllanti_lungo",
  "sp07e_crediti_tributari_lungo",
  "sp07f_imposte_anticipate_lungo",
  "sp07g_crediti_altri_lungo",
  "sp08_attivita_finanziarie",
  "sp09_disponibilita_liquide",
  "sp10_ratei_risconti_attivi",
  "sp11_capitale",
  "sp12a_riserva_sovrapprezzo",
  "sp12b_riserve_rivalutazione",
  "sp12c_riserva_legale",
  "sp12d_riserve_statutarie",
  "sp12e_altre_riserve",
  "sp12f_riserva_copertura_flussi",
  "sp12g_utili_perdite_portati",
  "sp13_utile_perdita",
  "sp12h_riserva_neg_azioni_proprie",
  "sp14_fondi_rischi",
  "sp15_tfr",
  "sp16a_debiti_banche_breve",
  "sp17a_debiti_banche_lungo",
  "sp16b_debiti_altri_finanz_breve",
  "sp17b_debiti_altri_finanz_lungo",
  "sp16c_debiti_obbligazioni_breve",
  "sp17c_debiti_obbligazioni_lungo",
  "sp16d_debiti_fornitori_breve",
  "sp17d_debiti_fornitori_lungo",
  "sp16e_debiti_tributari_breve",
  "sp17e_debiti_tributari_lungo",
  "sp16f_debiti_previdenza_breve",
  "sp17f_debiti_previdenza_lungo",
  "sp16g_altri_debiti_breve",
  "sp17g_altri_debiti_lungo",
  "ce01_ricavi_vendite",
  "ce02_variazioni_rimanenze",
  "ce03_lavori_interni",
  "ce04_altri_ricavi",
  "ce05_materie_prime",
  "ce06_servizi",
  "ce07_godimento_beni",
  "ce08_costi_personale",
  "ce08b_salari_stipendi",
  "ce08c_oneri_sociali",
  "ce08a_tfr_accrual",
  "ce08d_altri_costi_personale",
  "ce09_ammortamenti",
  "ce09a_ammort_immateriali",
  "ce09b_ammort_materiali",
  "ce09c_svalutazioni",
  "ce09d_svalutazione_crediti",
  "ce10_var_rimanenze_mat_prime",
  "ce11_accantonamenti",
  "ce11b_altri_accantonamenti",
  "ce12_oneri_diversi",
  "ce13_proventi_partecipazioni",
  "ce14_altri_proventi_finanziari",
  "ce15_oneri_finanziari",
  "ce16_utili_perdite_cambi",
  "ce17a_rivalutazioni",
  "ce17b_svalutazioni",
  "ce17_rettifiche_attivita_fin",
  "ce18_proventi_straordinari",
  "ce19_oneri_straordinari",
  "ce20_imposte",
];
const ATTESI_CONFRONTO_BS: string[] = [
  "_hdr_attivo",
  "sp01_crediti_soci",
  "_hdr_immob",
  "sp02_immob_immateriali",
  "sp03_immob_materiali",
  "sp04_immob_finanziarie",
  "sp04a_partecipazioni",
  "sp04b_crediti_immob_breve",
  "sp04c_crediti_immob_lungo",
  "sp04d_altri_titoli",
  "sp04e_strumenti_derivati_attivi",
  "_totale_immob",
  "_hdr_circ",
  "sp05_rimanenze",
  "sp06_crediti_breve",
  "sp06a_crediti_clienti_breve",
  "sp06b_crediti_controllate_breve",
  "sp06c_crediti_collegate_breve",
  "sp06d_crediti_controllanti_breve",
  "sp06e_crediti_tributari_breve",
  "sp06f_imposte_anticipate_breve",
  "sp06g_crediti_altri_breve",
  "sp07_crediti_lungo",
  "sp07a_crediti_clienti_lungo",
  "sp07b_crediti_controllate_lungo",
  "sp07c_crediti_collegate_lungo",
  "sp07d_crediti_controllanti_lungo",
  "sp07e_crediti_tributari_lungo",
  "sp07f_imposte_anticipate_lungo",
  "sp07g_crediti_altri_lungo",
  "sp08_attivita_finanziarie",
  "sp09_disponibilita_liquide",
  "_totale_circ",
  "sp10_ratei_risconti_attivi",
  "_totale_attivo",
  "_hdr_passivo",
  "_hdr_pn",
  "sp11_capitale",
  "sp12a_riserva_sovrapprezzo",
  "sp12b_riserve_rivalutazione",
  "sp12c_riserva_legale",
  "sp12d_riserve_statutarie",
  "sp12e_altre_riserve",
  "sp12f_riserva_copertura_flussi",
  "sp12g_utili_perdite_portati",
  "sp13_utile_perdita",
  "sp12h_riserva_neg_azioni_proprie",
  "_totale_pn",
  "sp14_fondi_rischi",
  "sp15_tfr",
  "_hdr_debiti",
  "_debt_banche",
  "sp16a_debiti_banche_breve",
  "sp17a_debiti_banche_lungo",
  "_debt_altri_finanz",
  "sp16b_debiti_altri_finanz_breve",
  "sp17b_debiti_altri_finanz_lungo",
  "_debt_obbligazioni",
  "sp16c_debiti_obbligazioni_breve",
  "sp17c_debiti_obbligazioni_lungo",
  "_debt_fornitori",
  "sp16d_debiti_fornitori_breve",
  "sp17d_debiti_fornitori_lungo",
  "_debt_tributari",
  "sp16e_debiti_tributari_breve",
  "sp17e_debiti_tributari_lungo",
  "_debt_previdenza",
  "sp16f_debiti_previdenza_breve",
  "sp17f_debiti_previdenza_lungo",
  "_debt_altri",
  "sp16g_altri_debiti_breve",
  "sp17g_altri_debiti_lungo",
  "_totale_debiti",
  "sp18_ratei_risconti_passivi",
  "_totale_passivo",
  "_differenza",
];
const ATTESI_CONFRONTO_CE: string[] = [
  "_hdr_a",
  "ce01_ricavi_vendite",
  "ce02_variazioni_rimanenze",
  "ce03_lavori_interni",
  "ce04_altri_ricavi",
  "_totale_vp",
  "_hdr_b",
  "ce05_materie_prime",
  "ce06_servizi",
  "ce07_godimento_beni",
  "ce08_costi_personale",
  "ce08b_salari_stipendi",
  "ce08c_oneri_sociali",
  "ce08a_tfr_accrual",
  "ce08d_altri_costi_personale",
  "ce09_ammortamenti",
  "ce09a_ammort_immateriali",
  "ce09b_ammort_materiali",
  "ce09c_svalutazioni",
  "ce09d_svalutazione_crediti",
  "ce10_var_rimanenze_mat_prime",
  "ce11_accantonamenti",
  "ce11b_altri_accantonamenti",
  "ce12_oneri_diversi",
  "_totale_cp",
  "_ebitda",
  "_ebit",
  "_hdr_c",
  "ce13_proventi_partecipazioni",
  "ce14_altri_proventi_finanziari",
  "ce15_oneri_finanziari",
  "ce16_utili_perdite_cambi",
  "_totale_fin",
  "_hdr_d",
  "ce17a_rivalutazioni",
  "ce17b_svalutazioni",
  "ce17_rettifiche_attivita_fin",
  "_hdr_e",
  "ce18_proventi_straordinari",
  "ce19_oneri_straordinari",
  "_totale_straord",
  "_profit_before_tax",
  "ce20_imposte",
  "_net_profit",
];

describe("invariante: nessuna vista perde o riordina righe", () => {
  it("prospetto SP (forecast/balance e report-appendices)", () => {
    expect(BALANCE_STATEMENT_ROWS.map(rowKey)).toEqual(ATTESI_BALANCE);
  });

  it("prospetto CE (forecast/income)", () => {
    expect(INCOME_STATEMENT_ROWS.map(rowKey)).toEqual(ATTESI_INCOME);
  });

  it("Rettifiche: ordine di resa completo", () => {
    expect(rettificheCodes()).toEqual(ATTESI_RETTIFICHE);
  });

  it("Confronto: righe SP costruite dal server", () => {
    expect(buildBalanceItemsWithTotals(BS_FIXTURE).map((i) => i.code)).toEqual(ATTESI_CONFRONTO_BS);
  });

  it("Confronto: righe CE costruite dal server", () => {
    expect(buildIncomeItemsWithEbitda(CE_FIXTURE, 9).map((i) => i.code)).toEqual(ATTESI_CONFRONTO_CE);
  });
});

describe("cross-check: il catalogo riproduce la regola delle etichette", () => {
  it("ogni codice etichettato dalle fonti vecchie esiste nel catalogo", () => {
    const known = new Set(VOCI.map((v) => v.code));
    const mancanti = Object.keys(RETTIFICHE_LABELS).filter((c) => !known.has(c));
    expect(mancanti).toEqual([]);
  });

  it("i sotto-conti coperti dal selettore usano il suo testo come etichetta autonoma", () => {
    for (const [code, atteso] of Object.entries(COUNTERPART_PICKER_LABELS)) {
      expect(labelOf(code)).toBe(atteso);
    }
  });

  it("nessuna etichetta del catalogo conserva i rientri delle fonti vecchie", () => {
    const conRientro = VOCI.filter((v) => v.label.startsWith(" "));
    expect(conRientro.map((v) => v.code)).toEqual([]);
  });
});

/**
 * Il catalogo teneva una COPIA a mano di DUE fonti vive. Al Task 7 una delle
 * due è sparita: le mappe `relabel` interne di pratica-statement-rows.ts non
 * esistono più — le due funzioni chiamano `labelOf(code, "contestuale")`, e
 * `CONFRONTO_RELABEL` dentro il catalogo non è più la copia di niente: è la
 * fonte. I due test che sorvegliavano quella copia sono stati RIMOSSI qui, e
 * il motivo è registrato perché una loro sparizione silenziosa si legge come
 * una perdita di copertura:
 *
 *  - "la copia della grafia del Confronto non è andata alla deriva" rileggeva
 *    le due mappe dal sorgente con una regex. Senza le mappe la regex non
 *    trova nulla: il test non ha più una fonte indipendente con cui
 *    confrontare il catalogo, e la duplicazione che sorvegliava non esiste
 *    più — è risolta, non solo non più testata.
 *  - "l'etichetta contestuale coincide con quella resa dal Confronto"
 *    confrontava l'etichetta della riga con `labelOf(code, "contestuale")`.
 *    Ora la riga PORTA quel valore per costruzione: il test confronterebbe il
 *    catalogo con se stesso e non potrebbe più fallire. Un test verde che non
 *    può fallire si legge come copertura e non lo è.
 *
 * Restano: l'asserzione che il Task 7 rende davvero necessaria (subito qui
 * sotto — non tautologica, vedi il commento sul posto) e la sorveglianza sul
 * gruppo "Fondi per rischi e oneri", la cui fonte (BALANCE_HIERARCHY_GROUPS)
 * è ancora viva e ancora un letterale scritto a mano separatamente.
 */
describe("anti-deriva: le copie nel catalogo seguono ancora le fonti vive", () => {
  // NON è tautologico, a differenza del test che sostituisce: `labelOf` su un
  // codice sconosciuto restituisce IL CODICE, e da quando il Confronto non ha
  // più un `?? orig.label` di riserva (Task 7) una voce tolta dal catalogo — o
  // una riga aggiunta al prospetto con un codice che il catalogo non conosce —
  // si renderebbe come "sp05a_materie_prime" dentro la tabella. Nessun'altra
  // asserzione se ne accorgerebbe: ATTESI_CONFRONTO_* pinna i CODICI, non le
  // etichette. Le due liste confrontate qui restano indipendenti (l'elenco di
  // ALL_CODES viene dagli elenchi di Rettifiche; quello reso è scritto a mano
  // dentro i due builder).
  it("ogni codice reso dal Confronto esiste nel catalogo", () => {
    const conosciuti = new Set(VOCI.map((v) => v.code));
    const righe = [
      ...buildBalanceItemsWithTotals(BS_FIXTURE),
      ...buildIncomeItemsWithEbitda(CE_FIXTURE, 9),
    ];
    // I codici sintetici ("_hdr_*", "_totale_*", "_debt_*", "_ebitda", ...)
    // portano un'etichetta letterale e non passano da labelOf; quali siano è
    // pinnato per intero da ATTESI_CONFRONTO_BS/CE qui sopra.
    const orfani = righe
      .map((r) => r.code)
      .filter((c) => !c.startsWith("_") && !conosciuti.has(c));
    expect(orfani).toEqual([]);
  });

  it("il dettaglio dei fondi rischi riproduce BALANCE_HIERARCHY_GROUPS", () => {
    const gruppo = BALANCE_HIERARCHY_GROUPS.find((g) => g.aggregate === "sp14_fondi_rischi");
    expect(gruppo).toBeDefined();
    const atteso = gruppo!.details.map(([code, label], i) => ({
      code,
      label,
      parent: "sp14_fondi_rischi",
      order: i,
    }));
    const ottenuto = atteso.map(({ code }) => {
      const v = voce(code);
      return { code, label: v?.label, parent: v?.parent, order: v?.order };
    });
    expect(ottenuto).toEqual(atteso);
  });
});

// ===== Task 6: report-composition — rinuncia documentata =====
//
// report-composition.tsx (righe 47-51) somma a mano quattro gruppi di codici
// SP per un grafico di composizione percentuale. Il piano chiedeva di
// verificare se quelle quattro somme potessero diventare `aggregate(bs, code)`
// dal catalogo. Risposta misurata: NO per due dei quattro gruppi, e la
// sostituzione parziale (solo dove concorda) non vale la doppia via di
// calcolo che introdurrebbe. `report-composition.tsx` NON è stato toccato.
//
// Motivo: `aggregate()` somma le FOGLIE del sottoalbero di un codice (vedi
// ivcee-catalog.ts:321-329). Il BalanceSheet che report-composition riceve da
// /analysis è già aggregato dal backend: sp04_immob_finanziarie,
// sp06_crediti_breve e sp07_crediti_lungo sono valorizzati, le loro
// sotto-voci (sp04a-e, sp06a-g, sp07a-g — tutte con parent nel catalogo, vedi
// DETAIL_PARENTS in pratica-codes.ts) no. Su un codice con figli e figli a
// zero, aggregate() restituisce 0, non il valore del padre — sarebbe uno zero
// silenzioso nel grafico stampato, peggio della somma a mano che sostituisce
// (nota del piano: "Un aggregatore che restituisce zero su dati reali è
// peggio della somma a mano che sostituisce").
//
// Valori misurati con la fixture del brief (Task 6, Step 1), aggregati-soli,
// sotto-voci non valorizzate:
//   aggregate(BS, "sp04_immob_finanziarie") = 0   (5 figli: sp04a..e)
//   aggregate(BS, "sp06_crediti_breve")     = 0   (7 figli: sp06a..g)
//   aggregate(BS, "sp07_crediti_lungo")     = 0   (7 figli: sp07a..g)
//   aggregate(BS, "sp08_attivita_finanziarie")   = 20  (nessun figlio: foglia)
//   aggregate(BS, "sp09_disponibilita_liquide")  = 80  (nessun figlio: foglia)
//   aggregate(BS, "sp01_crediti_soci")      = 10  (foglia)
//   aggregate(BS, "sp02_immob_immateriali") = 100 (foglia)
//   aggregate(BS, "sp03_immob_materiali")   = 200 (foglia)
//
// Effetto per gruppo (BALANCE_HIERARCHY_GROUPS conferma che sp04/06/07 hanno
// figli; sp01/02/03/08/09 non compaiono mai come parent, quindi sono foglie):
//   immobilizzazioni: a mano 360 (100+200+50+10) vs aggregate() 310 — perde
//     esattamente i 50 di sp04_immob_finanziarie.
//   crediti:          a mano 460 (400+60)        vs aggregate() 0   — persi
//     entrambi gli aggregati.
//   liquidità:        a mano 100 (80+20)          vs aggregate() 100 — qui
//     concordano perché sp08/sp09 sono foglie senza sotto-voci nel catalogo.
//
// Questo test pin-a il comportamento vero (non quello sperato dal Task 6,
// Step 1 del piano) per impedire che una futura modifica colleghi
// `aggregate()` a report-composition e azzeri silenziosamente immobilizzazioni
// e crediti nel grafico.
describe("report-composition: aggregate() su dati aggregati-soli — rinuncia documentata", () => {
  const BS: Record<string, number> = {
    sp01_crediti_soci: 10, sp02_immob_immateriali: 100, sp03_immob_materiali: 200,
    sp04_immob_finanziarie: 50, sp05_rimanenze: 300,
    sp06_crediti_breve: 400, sp07_crediti_lungo: 60,
    sp08_attivita_finanziarie: 20, sp09_disponibilita_liquide: 80,
  };

  it("sp04/sp06/sp07 hanno figli nel catalogo: aggregate() li azzera su dati solo-aggregato", () => {
    expect(aggregate(BS, "sp04_immob_finanziarie")).toBe(0);
    expect(aggregate(BS, "sp06_crediti_breve")).toBe(0);
    expect(aggregate(BS, "sp07_crediti_lungo")).toBe(0);
  });

  it("immobilizzazioni: la somma a mano (360) e aggregate() (310) divergono — non sostituibile", () => {
    const aMano = BS.sp02_immob_immateriali + BS.sp03_immob_materiali
      + BS.sp04_immob_finanziarie + BS.sp01_crediti_soci;
    expect(aMano).toBe(360);
    const viaAggregate = aggregate(BS, "sp02_immob_immateriali")
      + aggregate(BS, "sp03_immob_materiali")
      + aggregate(BS, "sp04_immob_finanziarie")
      + aggregate(BS, "sp01_crediti_soci");
    expect(viaAggregate).toBe(310);
    expect(viaAggregate).not.toBe(aMano);
  });

  it("crediti: la somma a mano (460) e aggregate() (0) divergono — non sostituibile", () => {
    const aMano = BS.sp06_crediti_breve + BS.sp07_crediti_lungo;
    expect(aMano).toBe(460);
    const viaAggregate = aggregate(BS, "sp06_crediti_breve") + aggregate(BS, "sp07_crediti_lungo");
    expect(viaAggregate).toBe(0);
    expect(viaAggregate).not.toBe(aMano);
  });

  it("liquidità: sp08/sp09 sono foglie nel catalogo — qui aggregate() concorda (100)", () => {
    const aMano = BS.sp09_disponibilita_liquide + BS.sp08_attivita_finanziarie;
    const viaAggregate = aggregate(BS, "sp09_disponibilita_liquide")
      + aggregate(BS, "sp08_attivita_finanziarie");
    expect(aMano).toBe(100);
    expect(viaAggregate).toBe(aMano);
  });
});
