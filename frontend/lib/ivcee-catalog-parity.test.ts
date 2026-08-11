import { describe, expect, it } from "vitest";
import {
  BALANCE_HIERARCHY_GROUPS, BALANCE_STATEMENT_ROWS, INCOME_STATEMENT_ROWS, VOCI,
  COUNTERPART_OPTIONS,
  aggregate, depthOf, isDettaglio, labelOf, voce,
} from "@/lib/ivcee-catalog";
import {
  CE_A, CE_B, CE_C, CE_D, CE_E, CE_IMPOSTE,
  DEBT_GROUPS,
  RETTIFICHE_BS_ATTIVO, RETTIFICHE_BS_OTHER_PASSIVO, RETTIFICHE_BS_PN,
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

/**
 * Caratterizzazione delle ETICHETTE, generata dallo stato corrente e poi
 * congelata. Serve una rete diversa da ATTESI_CONFRONTO_BS/CE: quegli elenchi
 * pinnano i CODICI e il loro ordine, quindi una modifica al TESTO di
 * un'etichetta li lascia verdi. Dal Task 7 la grafia contestuale non ha piu'
 * una fonte esterna con cui confrontarsi (le due mappe `relabel` di
 * pratica-statement-rows.ts non esistono piu': CONFRONTO_RELABEL, dentro
 * ivcee-catalog.ts, e' la fonte) — un refuso li' cambierebbe in silenzio
 * Confronto, Proiezione e Stampa.
 *
 * ATTENZIONE — natura diversa dagli altri ATTESI_*: un cambiamento
 * DELIBERATO di un'etichetta e' legittimo, e allora si aggiorna la riga
 * corrispondente NELLO STESSO commit che cambia il testo. Quello che non e'
 * mai legittimo e' aggiornarla per far tornare verde la suite senza sapere
 * perche' il testo si e' mosso.
 */
const ATTESI_CONFRONTO_LABELS: ReadonlyArray<readonly [string, string]> = [
  ["sp01_crediti_soci", "A) Crediti verso soci per versamenti ancora dovuti"],
  ["sp02_immob_immateriali", "I - Immobilizzazioni immateriali"],
  ["sp03_immob_materiali", "II - Immobilizzazioni materiali"],
  ["sp04_immob_finanziarie", "III - Immobilizzazioni finanziarie"],
  ["sp04a_partecipazioni", "1) Partecipazioni"],
  ["sp04b_crediti_immob_breve", "2) Crediti (entro es. successivo)"],
  ["sp04c_crediti_immob_lungo", "2) Crediti (oltre es. successivo)"],
  ["sp04d_altri_titoli", "3) Altri titoli"],
  ["sp04e_strumenti_derivati_attivi", "4) Strumenti finanziari derivati attivi"],
  ["sp05_rimanenze", "I - Rimanenze"],
  ["sp06_crediti_breve", "II - Crediti (entro esercizio successivo)"],
  ["sp06a_crediti_clienti_breve", "1) Verso clienti"],
  ["sp06b_crediti_controllate_breve", "2) Verso imprese controllate"],
  ["sp06c_crediti_collegate_breve", "3) Verso imprese collegate"],
  ["sp06d_crediti_controllanti_breve", "4) Verso controllanti"],
  ["sp06e_crediti_tributari_breve", "5-bis) Crediti tributari"],
  ["sp06f_imposte_anticipate_breve", "5-ter) Imposte anticipate"],
  ["sp06g_crediti_altri_breve", "5-quater) Verso altri"],
  ["sp07_crediti_lungo", "II - Crediti (oltre esercizio successivo)"],
  ["sp07a_crediti_clienti_lungo", "1) Verso clienti"],
  ["sp07b_crediti_controllate_lungo", "2) Verso imprese controllate"],
  ["sp07c_crediti_collegate_lungo", "3) Verso imprese collegate"],
  ["sp07d_crediti_controllanti_lungo", "4) Verso controllanti"],
  ["sp07e_crediti_tributari_lungo", "5-bis) Crediti tributari"],
  ["sp07f_imposte_anticipate_lungo", "5-ter) Imposte anticipate"],
  ["sp07g_crediti_altri_lungo", "5-quater) Verso altri"],
  ["sp08_attivita_finanziarie", "III - Attività finanziarie che non costituiscono immobilizzazioni"],
  ["sp09_disponibilita_liquide", "IV - Disponibilità liquide"],
  ["sp10_ratei_risconti_attivi", "D) Ratei e risconti attivi"],
  ["sp11_capitale", "I - Capitale"],
  ["sp12a_riserva_sovrapprezzo", "II - Riserva da soprapprezzo delle azioni"],
  ["sp12b_riserve_rivalutazione", "III - Riserve di rivalutazione"],
  ["sp12c_riserva_legale", "IV - Riserva legale"],
  ["sp12d_riserve_statutarie", "V - Riserve statutarie"],
  ["sp12e_altre_riserve", "VI - Altre riserve"],
  ["sp12f_riserva_copertura_flussi", "VII - Riserva per copertura flussi finanziari"],
  ["sp12g_utili_perdite_portati", "VIII - Utili (perdite) portati a nuovo"],
  ["sp13_utile_perdita", "IX - Utile (perdita) dell'esercizio"],
  ["sp12h_riserva_neg_azioni_proprie", "X - Riserva negativa per azioni proprie"],
  ["sp14_fondi_rischi", "B) Fondi per rischi e oneri"],
  ["sp15_tfr", "C) Trattamento di fine rapporto di lavoro subordinato"],
  ["sp16a_debiti_banche_breve", "entro 12 mesi"],
  ["sp17a_debiti_banche_lungo", "oltre 12 mesi"],
  ["sp16b_debiti_altri_finanz_breve", "entro 12 mesi"],
  ["sp17b_debiti_altri_finanz_lungo", "oltre 12 mesi"],
  ["sp16c_debiti_obbligazioni_breve", "entro 12 mesi"],
  ["sp17c_debiti_obbligazioni_lungo", "oltre 12 mesi"],
  ["sp16d_debiti_fornitori_breve", "entro 12 mesi"],
  ["sp17d_debiti_fornitori_lungo", "oltre 12 mesi"],
  ["sp16e_debiti_tributari_breve", "entro 12 mesi"],
  ["sp17e_debiti_tributari_lungo", "oltre 12 mesi"],
  ["sp16f_debiti_previdenza_breve", "entro 12 mesi"],
  ["sp17f_debiti_previdenza_lungo", "oltre 12 mesi"],
  ["sp16g_altri_debiti_breve", "entro 12 mesi"],
  ["sp17g_altri_debiti_lungo", "oltre 12 mesi"],
  ["sp18_ratei_risconti_passivi", "E) Ratei e risconti passivi"],
  ["ce01_ricavi_vendite", "1) Ricavi delle vendite e delle prestazioni"],
  ["ce02_variazioni_rimanenze", "2) Var. rimanenze di prodotti in c/lav., semilav. e finiti"],
  ["ce03_lavori_interni", "4) Incrementi di immobilizzazioni per lavori interni"],
  ["ce04_altri_ricavi", "5) Altri ricavi e proventi"],
  ["ce05_materie_prime", "6) Per materie prime, sussidiarie, di consumo e di merci"],
  ["ce06_servizi", "7) Per servizi"],
  ["ce07_godimento_beni", "8) Per godimento di beni di terzi"],
  ["ce08_costi_personale", "9) Per il personale"],
  ["ce08b_salari_stipendi", "a) Salari e stipendi"],
  ["ce08c_oneri_sociali", "b) Oneri sociali"],
  ["ce08a_tfr_accrual", "c) Trattamento di fine rapporto"],
  ["ce08d_altri_costi_personale", "e) Altri costi del personale"],
  ["ce09_ammortamenti", "10) Ammortamenti e svalutazioni"],
  ["ce09a_ammort_immateriali", "a) Ammortamento immobilizzazioni immateriali"],
  ["ce09b_ammort_materiali", "b) Ammortamento immobilizzazioni materiali"],
  ["ce09c_svalutazioni", "c) Altre svalutazioni delle immobilizzazioni"],
  ["ce09d_svalutazione_crediti", "d) Svalutazione crediti attivo circolante"],
  ["ce10_var_rimanenze_mat_prime", "11) Var. rimanenze di materie prime, suss., di cons. e merci"],
  ["ce11_accantonamenti", "12) Accantonamenti per rischi"],
  ["ce11b_altri_accantonamenti", "13) Altri accantonamenti"],
  ["ce12_oneri_diversi", "14) Oneri diversi di gestione"],
  ["ce13_proventi_partecipazioni", "15) Proventi da partecipazioni"],
  ["ce14_altri_proventi_finanziari", "16) Altri proventi finanziari"],
  ["ce15_oneri_finanziari", "17) Interessi e altri oneri finanziari"],
  ["ce16_utili_perdite_cambi", "17-bis) Utili e perdite su cambi"],
  ["ce17a_rivalutazioni", "18) Rivalutazioni"],
  ["ce17b_svalutazioni", "19) Svalutazioni"],
  ["ce17_rettifiche_attivita_fin", "Totale rettifiche di valore (18 - 19)"],
  ["ce18_proventi_straordinari", "Proventi straordinari"],
  ["ce19_oneri_straordinari", "Oneri straordinari"],
  ["ce20_imposte", "20) Imposte sul reddito dell'esercizio"],
];

/**
 * Le etichette AUTONOME di tutte e 100 le voci del catalogo — quelle che
 * rendono il giornale delle rettifiche, il selettore di contropartita, i
 * dialoghi e ogni riga di Rettifiche. Rimpiazza la copertura del cross-check
 * di transizione rimosso al Task 9 ("i sotto-conti coperti dal selettore usano
 * il suo testo come etichetta autonoma"), che confrontava 38 di questi testi
 * con COUNTERPART_PICKER_LABELS: quella mappa non esiste piu' come fonte
 * separata, quindi il confronto e' con lo stato congelato, non con una copia.
 * Stessa avvertenza dell'array qui sopra.
 */
const ATTESI_LABELS_AUTONOME: ReadonlyArray<readonly [string, string]> = [
  ["sp01_crediti_soci", "A) Crediti verso soci per versamenti ancora dovuti"],
  ["sp02_immob_immateriali", "I - Immobilizzazioni immateriali"],
  ["sp03_immob_materiali", "II - Immobilizzazioni materiali"],
  ["sp04_immob_finanziarie", "III - Immobilizzazioni finanziarie"],
  ["sp04a_partecipazioni", "Partecipazioni"],
  ["sp04b_crediti_immob_breve", "Crediti immobilizzati (entro)"],
  ["sp04c_crediti_immob_lungo", "Crediti immobilizzati (oltre)"],
  ["sp04d_altri_titoli", "Altri titoli"],
  ["sp04e_strumenti_derivati_attivi", "Strumenti finanz. derivati attivi"],
  ["sp05_rimanenze", "I - Rimanenze"],
  ["sp05a_materie_prime", "Rimanenze materie prime"],
  ["sp05b_prodotti_in_corso", "Prodotti in corso di lavorazione"],
  ["sp05c_lavori_in_corso", "Lavori in corso su ordinazione"],
  ["sp05d_prodotti_finiti", "Prodotti finiti e merci"],
  ["sp05e_acconti", "Acconti (rimanenze)"],
  ["sp06_crediti_breve", "II - Crediti (entro esercizio successivo)"],
  ["sp06a_crediti_clienti_breve", "Crediti vs clienti (entro)"],
  ["sp06b_crediti_controllate_breve", "Crediti vs controllate (entro)"],
  ["sp06c_crediti_collegate_breve", "Crediti vs collegate (entro)"],
  ["sp06d_crediti_controllanti_breve", "Crediti vs controllanti (entro)"],
  ["sp06e_crediti_tributari_breve", "Crediti tributari (entro)"],
  ["sp06f_imposte_anticipate_breve", "Imposte anticipate (entro)"],
  ["sp06g_crediti_altri_breve", "Altri crediti (entro)"],
  ["sp07_crediti_lungo", "II - Crediti (oltre esercizio successivo)"],
  ["sp07a_crediti_clienti_lungo", "Crediti vs clienti (oltre)"],
  ["sp07b_crediti_controllate_lungo", "Crediti vs controllate (oltre)"],
  ["sp07c_crediti_collegate_lungo", "Crediti vs collegate (oltre)"],
  ["sp07d_crediti_controllanti_lungo", "Crediti vs controllanti (oltre)"],
  ["sp07e_crediti_tributari_lungo", "Crediti tributari (oltre)"],
  ["sp07f_imposte_anticipate_lungo", "Imposte anticipate (oltre)"],
  ["sp07g_crediti_altri_lungo", "Altri crediti (oltre)"],
  ["sp08_attivita_finanziarie", "III - Attività finanziarie che non costituiscono immobilizzazioni"],
  ["sp09_disponibilita_liquide", "IV - Disponibilità liquide"],
  ["sp10_ratei_risconti_attivi", "D) Ratei e risconti attivi"],
  ["sp11_capitale", "I - Capitale"],
  ["sp12a_riserva_sovrapprezzo", "II - Riserva da soprapprezzo delle azioni"],
  ["sp12b_riserve_rivalutazione", "III - Riserve di rivalutazione"],
  ["sp12c_riserva_legale", "IV - Riserva legale"],
  ["sp12d_riserve_statutarie", "V - Riserve statutarie"],
  ["sp12e_altre_riserve", "VI - Altre riserve"],
  ["sp12f_riserva_copertura_flussi", "VII - Riserva per copertura flussi finanziari"],
  ["sp12g_utili_perdite_portati", "VIII - Utili (perdite) portati a nuovo"],
  ["sp13_utile_perdita", "IX - Utile (perdita) dell'esercizio"],
  ["sp12h_riserva_neg_azioni_proprie", "X - Riserva negativa per azioni proprie"],
  ["sp12_riserve", "A.II-VIII) Totale riserve"],
  ["sp14_fondi_rischi", "B) Fondi per rischi e oneri"],
  ["sp14a_fondi_trattamento_quiescenza", "Quiescenza"],
  ["sp14b_fondi_imposte", "Imposte, anche differite"],
  ["sp14c_strumenti_derivati_passivi", "Derivati passivi"],
  ["sp14d_altri_fondi", "Altri fondi"],
  ["sp15_tfr", "C) Trattamento di fine rapporto di lavoro subordinato"],
  ["sp16_debiti_breve", "Debiti (entro esercizio successivo)"],
  ["sp16a_debiti_banche_breve", "Debiti vs banche (entro)"],
  ["sp17a_debiti_banche_lungo", "Debiti vs banche (oltre)"],
  ["sp16b_debiti_altri_finanz_breve", "Debiti vs altri finanz. (entro)"],
  ["sp17b_debiti_altri_finanz_lungo", "Debiti vs altri finanz. (oltre)"],
  ["sp16c_debiti_obbligazioni_breve", "Debiti obbligazionari (entro)"],
  ["sp17c_debiti_obbligazioni_lungo", "Debiti obbligazionari (oltre)"],
  ["sp16d_debiti_fornitori_breve", "Debiti vs fornitori (entro)"],
  ["sp17d_debiti_fornitori_lungo", "Debiti vs fornitori (oltre)"],
  ["sp16e_debiti_tributari_breve", "Debiti tributari (entro)"],
  ["sp17e_debiti_tributari_lungo", "Debiti tributari (oltre)"],
  ["sp16f_debiti_previdenza_breve", "Debiti previdenziali (entro)"],
  ["sp17f_debiti_previdenza_lungo", "Debiti previdenziali (oltre)"],
  ["sp16g_altri_debiti_breve", "Altri debiti (entro)"],
  ["sp17g_altri_debiti_lungo", "Altri debiti (oltre)"],
  ["sp17_debiti_lungo", "Debiti (oltre esercizio successivo)"],
  ["sp18_ratei_risconti_passivi", "E) Ratei e risconti passivi"],
  ["ce01_ricavi_vendite", "1) Ricavi delle vendite e delle prestazioni"],
  ["ce02_variazioni_rimanenze", "2) Var. rimanenze di prodotti in c/lav., semilav. e finiti"],
  ["ce03_lavori_interni", "4) Incrementi di immobilizzazioni per lavori interni"],
  ["ce03a_incrementi_immobilizzazioni", "4) Incrementi di immobilizzazioni per lavori interni"],
  ["ce04_altri_ricavi", "5) Altri ricavi e proventi"],
  ["ce05_materie_prime", "6) Per materie prime, sussidiarie, di consumo e di merci"],
  ["ce06_servizi", "7) Per servizi"],
  ["ce07_godimento_beni", "8) Per godimento di beni di terzi"],
  ["ce08_costi_personale", "9) Per il personale"],
  ["ce08b_salari_stipendi", "a) Salari e stipendi"],
  ["ce08c_oneri_sociali", "b) Oneri sociali"],
  ["ce08a_tfr_accrual", "c) Trattamento di fine rapporto"],
  ["ce08d_altri_costi_personale", "e) Altri costi del personale"],
  ["ce09_ammortamenti", "10) Ammortamenti e svalutazioni"],
  ["ce09a_ammort_immateriali", "a) Ammortamento immobilizzazioni immateriali"],
  ["ce09b_ammort_materiali", "b) Ammortamento immobilizzazioni materiali"],
  ["ce09c_svalutazioni", "c) Altre svalutazioni delle immobilizzazioni"],
  ["ce09d_svalutazione_crediti", "d) Svalutazione crediti attivo circolante"],
  ["ce10_var_rimanenze_mat_prime", "11) Var. rimanenze di materie prime, suss., di cons. e merci"],
  ["ce11_accantonamenti", "12) Accantonamenti per rischi"],
  ["ce11b_altri_accantonamenti", "13) Altri accantonamenti"],
  ["ce12_oneri_diversi", "14) Oneri diversi di gestione"],
  ["ce13_proventi_partecipazioni", "15) Proventi da partecipazioni"],
  ["ce14_altri_proventi_finanziari", "16) Altri proventi finanziari"],
  ["ce15_oneri_finanziari", "17) Interessi e altri oneri finanziari"],
  ["ce16_utili_perdite_cambi", "17-bis) Utili e perdite su cambi"],
  ["ce17a_rivalutazioni", "18) Rivalutazioni"],
  ["ce17b_svalutazioni", "19) Svalutazioni"],
  ["ce17_rettifiche_attivita_fin", "Totale rettifiche di valore (18 - 19)"],
  ["ce18_proventi_straordinari", "Proventi straordinari"],
  ["ce19_oneri_straordinari", "Oneri straordinari"],
  ["ce20_imposte", "20) Imposte sul reddito dell'esercizio"],
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

describe("le etichette non si muovono", () => {
  it("Confronto: la grafia contestuale delle 87 voci rese", () => {
    const codici = [
      ...buildBalanceItemsWithTotals(BS_FIXTURE),
      ...buildIncomeItemsWithEbitda(CE_FIXTURE, 9),
    ]
      .map((r) => r.code)
      .filter((c) => !c.startsWith("_"));
    expect(codici.map((c) => [c, labelOf(c, "contestuale")])).toEqual(ATTESI_CONFRONTO_LABELS);
  });

  it("catalogo: la grafia autonoma di tutte le voci", () => {
    expect(VOCI.map((v) => [v.code, labelOf(v.code)])).toEqual(ATTESI_LABELS_AUTONOME);
  });
});


/**
 * Il rientro delle righe di Rettifiche. Fino al Task 9 RettificheTab lo
 * deduceva da `RETTIFICHE_LABELS[field].startsWith("  ")` — misurava lo spazio
 * bianco di un'etichetta. Ora lo chiede al catalogo (`isDettaglio`). Le 32
 * voci qui sotto sono ESATTAMENTE quelle che il vecchio oracolo selezionava,
 * generate prima della sostituzione: e' la prova che la resa non si e' mossa.
 */
const ATTESI_RIENTRATI: string[] = [
  "sp04a_partecipazioni",
  "sp04b_crediti_immob_breve",
  "sp04c_crediti_immob_lungo",
  "sp04d_altri_titoli",
  "sp04e_strumenti_derivati_attivi",
  "sp05a_materie_prime",
  "sp05b_prodotti_in_corso",
  "sp05c_lavori_in_corso",
  "sp05d_prodotti_finiti",
  "sp05e_acconti",
  "sp06a_crediti_clienti_breve",
  "sp06b_crediti_controllate_breve",
  "sp06c_crediti_collegate_breve",
  "sp06d_crediti_controllanti_breve",
  "sp06e_crediti_tributari_breve",
  "sp06f_imposte_anticipate_breve",
  "sp06g_crediti_altri_breve",
  "sp07a_crediti_clienti_lungo",
  "sp07b_crediti_controllate_lungo",
  "sp07c_crediti_collegate_lungo",
  "sp07d_crediti_controllanti_lungo",
  "sp07e_crediti_tributari_lungo",
  "sp07f_imposte_anticipate_lungo",
  "sp07g_crediti_altri_lungo",
  "ce08b_salari_stipendi",
  "ce08c_oneri_sociali",
  "ce08a_tfr_accrual",
  "ce08d_altri_costi_personale",
  "ce09a_ammort_immateriali",
  "ce09b_ammort_materiali",
  "ce09c_svalutazioni",
  "ce09d_svalutazione_crediti",
];

/** Le 78 righe che RettificheTab passa a renderSection (i debiti hanno un
 *  loro blocco, debtRow, che non chiede il rientro a nessuno). */
const RIGHE_RENDER_SECTION: string[] = [
  ...RETTIFICHE_BS_ATTIVO,
  ...RETTIFICHE_BS_PN,
  ...RETTIFICHE_BS_OTHER_PASSIVO,
  "sp18_ratei_risconti_passivi",
  ...CE_A, ...CE_B, ...CE_C, ...CE_D, ...CE_E, ...CE_IMPOSTE,
];

describe("Rettifiche: il rientro passa dal catalogo, non dagli spazi", () => {
  it("isDettaglio seleziona le stesse 32 voci del vecchio oracolo", () => {
    expect(RIGHE_RENDER_SECTION.filter(isDettaglio)).toEqual(ATTESI_RIENTRATI);
  });

  it("depthOf > 0 NON e' equivalente: ne selezionerebbe 42", () => {
    const perProfondita = RIGHE_RENDER_SECTION.filter((c) => depthOf(c) > 0);
    expect(perProfondita).toHaveLength(42);
    // Le 10 di troppo: voci con un padre nel catalogo che pero' portano gia'
    // la propria lettera/numero di schema e nella vista restano a filo.
    expect(perProfondita.filter((c) => !isDettaglio(c))).toEqual([
      "sp12a_riserva_sovrapprezzo",
      "sp12b_riserve_rivalutazione",
      "sp12c_riserva_legale",
      "sp12d_riserve_statutarie",
      "sp12e_altre_riserve",
      "sp12f_riserva_copertura_flussi",
      "sp12g_utili_perdite_portati",
      "sp12h_riserva_neg_azioni_proprie",
      "ce17a_rivalutazioni",
      "ce17b_svalutazioni",
    ]);
    // ...e nessuna voce rientrata sfugge alla profondita': il rientro e' un
    // sottoinsieme proprio dei figli, non un insieme diverso.
    expect(ATTESI_RIENTRATI.filter((c) => depthOf(c) === 0)).toEqual([]);
  });
});

/**
 * Il `describe("cross-check: il catalogo riproduce la regola delle etichette")`
 * che stava qui e' stato rimosso al Task 9 insieme alle sue fonti. Serviva a
 * garantire che il catalogo riproducesse fedelmente RETTIFICHE_LABELS e
 * COUNTERPART_PICKER_LABELS mentre le tre mappe coesistevano; ora quelle due
 * non esistono piu' come export separati (sono private dentro
 * ivcee-catalog.ts, spostate verbatim), quindi non c'e' piu' una seconda
 * copia da cui divergere. Delle sue tre asserzioni:
 *  - "ogni codice etichettato dalle fonti vecchie esiste nel catalogo" era
 *    stato tolto come tautologico, con la motivazione "i codici SONO quelli
 *    del catalogo". La motivazione era FALSA e vale la pena scriverlo:
 *    ALL_CODES si costruisce da RETTIFICHE_BS_* / DEBT_GROUPS / CE_* piu' gli
 *    extra, NON da GRAFIA_RETTIFICHE. E COUNTERPART_OPTIONS itera
 *    Object.keys(GRAFIA_RETTIFICHE), quindi una chiave aggiunta a quella mappa
 *    e a nessun elenco di righe produrrebbe un'opzione del selettore la cui
 *    etichetta e' il nome grezzo del campo (labelOf su un codice sconosciuto
 *    restituisce il codice). Oggi nessuna delle 93 chiavi cade fuori
 *    dall'universo reso, ma la rete c'era: e' rimessa qui sotto, riformulata
 *    sul consumatore vero (il selettore) invece che sulla fonte morta;
 *  - "i sotto-conti coperti dal selettore usano il suo testo come etichetta
 *    autonoma" copriva 38 etichette. Quella copertura NON e' stata persa: e'
 *    dentro ATTESI_LABELS_AUTONOME, che pinna tutte e 100;
 *  - "nessuna etichetta conserva i rientri" non dipendeva dalle fonti morte ed
 *    e' viva qui sotto: vale anche per una voce aggiunta domani.
 * ("nessuna etichetta e' il codice stesso" vive gia' in ivcee-catalog.test.ts.)
 */
describe("struttura delle etichette", () => {
  it("ogni opzione del selettore e' una voce vera del catalogo", () => {
    const conosciuti = new Set(VOCI.map((v) => v.code));
    const orfani = COUNTERPART_OPTIONS.map((o) => o.field).filter((f) => !conosciuti.has(f));
    expect(orfani).toEqual([]);
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
// report-composition.tsx (righe 53-57, erano 47-51 prima che il Task 9 vi
// inserisse il commento di divieto) somma a mano quattro gruppi di codici
// SP per un grafico di composizione percentuale. Il piano chiedeva di
// verificare se quelle quattro somme potessero diventare `aggregate(bs, code)`
// dal catalogo. Risposta misurata: NO per due dei quattro gruppi, e la
// sostituzione parziale (solo dove concorda) non vale la doppia via di
// calcolo che introdurrebbe. Le quattro somme sono rimaste come erano; al
// Task 9 il file ha ricevuto SOLO un commento di sei righe che vieta la
// sostituzione e rimanda a questo describe (prima la ragione viveva solo in
// un messaggio di commit che quel file non aveva mai toccato).
//
// Motivo: `aggregate()` somma le FOGLIE del sottoalbero di un codice (vedi
// ivcee-catalog.ts:497-505). Il BalanceSheet che report-composition riceve da
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
