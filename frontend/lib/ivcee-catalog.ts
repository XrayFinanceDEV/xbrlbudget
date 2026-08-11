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
//  - le etichette: vedi labelFor() più sotto — GRAFIA_SELETTORE vince per
//    ognuna delle sue chiavi: sono tutti sotto-conti la cui grafia breve
//    del Confronto (es. "1) Verso clienti", "entro 12 mesi") non distingue
//    entro/oltre né la voce padre senza un'intestazione sopra; altrimenti
//    vince la grafia del Confronto (CONFRONTO_RELABEL); GRAFIA_RETTIFICHE è
//    l'ultima risorsa per i pochi codici che il Confronto non rietichetta
//    (sp05a..sp05e, sp12_riserve); infine EXTRA_LABELS per le cinque voci che
//    nessuna di quelle mappe nomina.
//
// Le TRE grafie vivono tutte qui dentro, private al modulo (Task 9). Erano
// due export di lib/pratica-rettifiche-rules.ts (RETTIFICHE_LABELS,
// COUNTERPART_PICKER_LABELS) e una mappa interna a lib/pratica-statement-rows.ts
// (`relabel`, assorbita al Task 7): tre posti da cui si poteva ribattezzare una
// voce senza passare da qui. Il testo NON è stato riscritto — i due blocchi
// sono stati spostati carattere per carattere; ivcee-catalog-parity.test.ts
// congela ogni etichetta resa (ATTESI_CONFRONTO_LABELS, ATTESI_LABELS_AUTONOME).

import {
  type AcctCategory,
  COUNTERPART_GROUPS,
  NON_POSTABLE_FIELDS,
  fieldCategory,
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
  /**
   * Sotto-voce di DETTAGLIO: la vista Rettifiche la rientra di un livello.
   * NON è la profondità nel grafo dei padri (vedi depthOf, e il commento su
   * isDettaglio più sotto): sp12a..h e ce17a/b hanno un padre e NON sono
   * dettaglio. Il dato è quello che GRAFIA_RETTIFICHE portava come due spazi
   * iniziali nell'etichetta — un dato di resa nascosto dentro il testo.
   */
  dettaglio?: true;
}

// ===== Grafia di Rettifiche (ex RETTIFICHE_LABELS di pratica-rettifiche-rules.ts) =====
// Spostata qui al Task 9, verbatim. I due spazi iniziali di alcune voci NON
// sono decorazione: sono il dato di rientro che RettificheTab leggeva
// direttamente da questa mappa. Ora sono letti UNA volta, in labelFor(), e
// promossi al campo `dettaglio` della voce; labelFor() trimma l'etichetta.
const GRAFIA_RETTIFICHE: Record<string, string> = {
  // SP - Attivo
  sp01_crediti_soci: "A) Crediti verso soci",
  sp02_immob_immateriali: "B.I) Immobilizzazioni immateriali",
  sp03_immob_materiali: "B.II) Immobilizzazioni materiali",
  sp04_immob_finanziarie: "B.III) Immobilizzazioni finanziarie",
  sp04a_partecipazioni: "  1) Partecipazioni",
  sp04b_crediti_immob_breve: "  2) Crediti (entro es. successivo)",
  sp04c_crediti_immob_lungo: "  2) Crediti (oltre es. successivo)",
  sp04d_altri_titoli: "  3) Altri titoli",
  sp04e_strumenti_derivati_attivi: "  4) Strumenti finanziari derivati attivi",
  sp05_rimanenze: "C.I) Rimanenze",
  sp05a_materie_prime: "  1) Materie prime, sussidiarie e di consumo",
  sp05b_prodotti_in_corso: "  2) Prodotti in c/lavorazione e semilavorati",
  sp05c_lavori_in_corso: "  3) Lavori in corso su ordinazione",
  sp05d_prodotti_finiti: "  4) Prodotti finiti e merci",
  sp05e_acconti: "  5) Acconti",
  sp06_crediti_breve: "C.II) Crediti (entro es. successivo)",
  sp06a_crediti_clienti_breve: "  1) Verso clienti",
  sp06b_crediti_controllate_breve: "  2) Verso imprese controllate",
  sp06c_crediti_collegate_breve: "  3) Verso imprese collegate",
  sp06d_crediti_controllanti_breve: "  4) Verso controllanti",
  sp06e_crediti_tributari_breve: "  5-bis) Crediti tributari",
  sp06f_imposte_anticipate_breve: "  5-ter) Imposte anticipate",
  sp06g_crediti_altri_breve: "  5-quater) Verso altri",
  sp07_crediti_lungo: "C.II) Crediti (oltre es. successivo)",
  sp07a_crediti_clienti_lungo: "  1) Verso clienti",
  sp07b_crediti_controllate_lungo: "  2) Verso imprese controllate",
  sp07c_crediti_collegate_lungo: "  3) Verso imprese collegate",
  sp07d_crediti_controllanti_lungo: "  4) Verso controllanti",
  sp07e_crediti_tributari_lungo: "  5-bis) Crediti tributari",
  sp07f_imposte_anticipate_lungo: "  5-ter) Imposte anticipate",
  sp07g_crediti_altri_lungo: "  5-quater) Verso altri",
  sp08_attivita_finanziarie: "C.III) Attività finanziarie",
  sp09_disponibilita_liquide: "C.IV) Disponibilità liquide",
  sp10_ratei_risconti_attivi: "D) Ratei e risconti attivi",
  // SP - Passivo
  sp11_capitale: "A.I) Capitale",
  sp12a_riserva_sovrapprezzo: "A.II) Riserva da soprapprezzo azioni",
  sp12b_riserve_rivalutazione: "A.III) Riserve di rivalutazione",
  sp12c_riserva_legale: "A.IV) Riserva legale",
  sp12d_riserve_statutarie: "A.V) Riserve statutarie",
  sp12e_altre_riserve: "A.VI) Altre riserve",
  sp12f_riserva_copertura_flussi: "A.VII) Riserva per copertura flussi finanziari",
  sp12_riserve: "A.II-VIII) Totale riserve",
  sp12g_utili_perdite_portati: "A.VIII) Utili (perdite) portati a nuovo",
  sp13_utile_perdita: "A.IX) Utile (perdita) esercizio",
  sp12h_riserva_neg_azioni_proprie: "A.X) Riserva negativa per azioni proprie in portafoglio",
  sp14_fondi_rischi: "B) Fondi per rischi e oneri",
  sp15_tfr: "C) Trattamento di fine rapporto di lavoro subordinato",
  sp16a_debiti_banche_breve: "D) Debiti vs banche (entro)",
  sp16b_debiti_altri_finanz_breve: "D) Debiti vs altri finanz. (entro)",
  sp16c_debiti_obbligazioni_breve: "D) Debiti obbligazionari (entro)",
  sp16d_debiti_fornitori_breve: "D) Debiti vs fornitori (entro)",
  sp16e_debiti_tributari_breve: "D) Debiti tributari (entro)",
  sp16f_debiti_previdenza_breve: "D) Debiti previdenziali (entro)",
  sp16g_altri_debiti_breve: "D) Altri debiti (entro)",
  sp17a_debiti_banche_lungo: "D) Debiti vs banche (oltre)",
  sp17b_debiti_altri_finanz_lungo: "D) Debiti vs altri finanz. (oltre)",
  sp17c_debiti_obbligazioni_lungo: "D) Debiti obbligazionari (oltre)",
  sp17d_debiti_fornitori_lungo: "D) Debiti vs fornitori (oltre)",
  sp17e_debiti_tributari_lungo: "D) Debiti tributari (oltre)",
  sp17f_debiti_previdenza_lungo: "D) Debiti previdenziali (oltre)",
  sp17g_altri_debiti_lungo: "D) Altri debiti (oltre)",
  sp18_ratei_risconti_passivi: "E) Ratei e risconti",
  // CE
  ce01_ricavi_vendite: "1) Ricavi delle vendite e delle prestazioni",
  ce02_variazioni_rimanenze: "2) Var. rimanenze di prodotti in c/lav., semilav. e finiti",
  ce03_lavori_interni: "4) Incrementi di immobilizzazioni per lavori interni",
  ce04_altri_ricavi: "5) Altri ricavi e proventi",
  ce05_materie_prime: "6) Per materie prime, sussidiarie, di consumo e di merci",
  ce06_servizi: "7) Per servizi",
  ce07_godimento_beni: "8) Per godimento di beni di terzi",
  ce08_costi_personale: "9) Per il personale",
  ce08b_salari_stipendi: "  a) Salari e stipendi",
  ce08c_oneri_sociali: "  b) Oneri sociali",
  ce08a_tfr_accrual: "  c) Trattamento di fine rapporto",
  ce08d_altri_costi_personale: "  e) Altri costi",
  ce09_ammortamenti: "10) Ammortamenti e svalutazioni",
  ce09a_ammort_immateriali: "  a) Ammort. delle immobilizzazioni immateriali",
  ce09b_ammort_materiali: "  b) Ammort. delle immobilizzazioni materiali",
  ce09c_svalutazioni: "  c) Altre svalutazioni delle immobilizzazioni",
  ce09d_svalutazione_crediti: "  d) Svalutazioni dei crediti dell'attivo circ. e disp. liquide",
  ce10_var_rimanenze_mat_prime: "11) Var. rimanenze di materie prime, suss., di cons. e merci",
  ce11_accantonamenti: "12) Accantonamenti per rischi",
  ce11b_altri_accantonamenti: "13) Altri accantonamenti",
  ce12_oneri_diversi: "14) Oneri diversi di gestione",
  ce13_proventi_partecipazioni: "15) Proventi da partecipazioni",
  ce14_altri_proventi_finanziari: "16) Altri proventi finanziari",
  ce15_oneri_finanziari: "17) Interessi e altri oneri finanziari",
  ce16_utili_perdite_cambi: "17-bis) Utili e perdite su cambi",
  ce17a_rivalutazioni: "18) Rivalutazioni",
  ce17b_svalutazioni: "19) Svalutazioni",
  ce17_rettifiche_attivita_fin: "Totale rettifiche di valore (18 - 19)",
  ce18_proventi_straordinari: "Proventi straordinari",
  ce19_oneri_straordinari: "Oneri straordinari",
  ce20_imposte: "20) Imposte sul reddito dell'esercizio",
};

// ===== Grafia del selettore di contropartita (ex COUNTERPART_PICKER_LABELS) =====
// Spostata qui al Task 9, verbatim. Vince su tutte e 38 le sue chiavi: sono
// sotto-conti che nel giornale e nel selettore compaiono SENZA l'intestazione
// del proprio aggregato, quindi la grafia breve del Confronto non basta.
const GRAFIA_SELETTORE: Record<string, string> = {
  sp16a_debiti_banche_breve: "Debiti vs banche (entro)",
  sp16b_debiti_altri_finanz_breve: "Debiti vs altri finanz. (entro)",
  sp16c_debiti_obbligazioni_breve: "Debiti obbligazionari (entro)",
  sp16d_debiti_fornitori_breve: "Debiti vs fornitori (entro)",
  sp16e_debiti_tributari_breve: "Debiti tributari (entro)",
  sp16f_debiti_previdenza_breve: "Debiti previdenziali (entro)",
  sp16g_altri_debiti_breve: "Altri debiti (entro)",
  sp17a_debiti_banche_lungo: "Debiti vs banche (oltre)",
  sp17b_debiti_altri_finanz_lungo: "Debiti vs altri finanz. (oltre)",
  sp17c_debiti_obbligazioni_lungo: "Debiti obbligazionari (oltre)",
  sp17d_debiti_fornitori_lungo: "Debiti vs fornitori (oltre)",
  sp17e_debiti_tributari_lungo: "Debiti tributari (oltre)",
  sp17f_debiti_previdenza_lungo: "Debiti previdenziali (oltre)",
  sp17g_altri_debiti_lungo: "Altri debiti (oltre)",
  sp06a_crediti_clienti_breve: "Crediti vs clienti (entro)",
  sp06b_crediti_controllate_breve: "Crediti vs controllate (entro)",
  sp06c_crediti_collegate_breve: "Crediti vs collegate (entro)",
  sp06d_crediti_controllanti_breve: "Crediti vs controllanti (entro)",
  sp06e_crediti_tributari_breve: "Crediti tributari (entro)",
  sp06f_imposte_anticipate_breve: "Imposte anticipate (entro)",
  sp06g_crediti_altri_breve: "Altri crediti (entro)",
  sp07a_crediti_clienti_lungo: "Crediti vs clienti (oltre)",
  sp07b_crediti_controllate_lungo: "Crediti vs controllate (oltre)",
  sp07c_crediti_collegate_lungo: "Crediti vs collegate (oltre)",
  sp07d_crediti_controllanti_lungo: "Crediti vs controllanti (oltre)",
  sp07e_crediti_tributari_lungo: "Crediti tributari (oltre)",
  sp07f_imposte_anticipate_lungo: "Imposte anticipate (oltre)",
  sp07g_crediti_altri_lungo: "Altri crediti (oltre)",
  sp04a_partecipazioni: "Partecipazioni",
  sp04b_crediti_immob_breve: "Crediti immobilizzati (entro)",
  sp04c_crediti_immob_lungo: "Crediti immobilizzati (oltre)",
  sp04d_altri_titoli: "Altri titoli",
  sp04e_strumenti_derivati_attivi: "Strumenti finanz. derivati attivi",
  sp05a_materie_prime: "Rimanenze materie prime",
  sp05b_prodotti_in_corso: "Prodotti in corso di lavorazione",
  sp05c_lavori_in_corso: "Lavori in corso su ordinazione",
  sp05d_prodotti_finiti: "Prodotti finiti e merci",
  sp05e_acconti: "Acconti (rimanenze)",
};

// ===== Grafia del Confronto (ex `relabel` di lib/pratica-statement-rows.ts) =====
// NON è più una copia: al Task 7 le due mappe `relabel` locali di
// pratica-statement-rows.ts (BS e CE) sono state rimosse e i due builder
// chiamano labelOf(code, "contestuale"). Questa tabella è quindi la FONTE della
// grafia contestuale, non il suo duplicato, e con essa è sparito il test che ne
// sorvegliava la deriva ("la copia della grafia del Confronto...").
// I rientri delle sotto-voci non sono stati riportati (" 1) ..." → "1) ..."):
// il rientro è resa, non dato — lo applica la vista (pl-6 sui codici di
// DETAIL_PARENTS). Il .trim() a runtime in labelFor() resta per sicurezza.
// Due chiavi — sp16_debiti_breve e sp17_debiti_lungo — il Confronto non le ha
// mai rese come riga propria (le somma soltanto): restano qui perché nessun'altra
// mappa (GRAFIA_RETTIFICHE compresa) nomina quei due aggregati.
const CONFRONTO_RELABEL: Record<string, string> = {
  // BS
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
  // CE
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
// GRAFIA_RETTIFICHE, CONFRONTO_RELABEL, GRAFIA_SELETTORE o
// DETAIL_PARENTS: la catena delle etichette e quella dei padri arrivano vuote.
// Etichetta, padre e ordine relativo sono presi ALLA LETTERA dalla vista che
// già li rende — nessun testo è inventato.

// Dettaglio dei fondi per rischi e oneri: copia letterale del gruppo
// "Fondi per rischi e oneri" di BALANCE_HIERARCHY_GROUPS (più sotto in
// questo stesso file — assorbito da lib/ivcee-balance-catalog.ts al Task 4),
// che dichiara sia il testo sia l'aggregato di appartenenza
// (`aggregate: "sp14_fondi_rischi"`). Sono righe vere del prospetto SP:
// compaiono in ATTESI_BALANCE, l'invariante pinnata. Restano due letterali
// scritti a mano separatamente (non l'uno derivato dall'altro) — unificarli
// creerebbe un riferimento in avanti a una costante definita centinaia di
// righe più sotto; la copia è tenuta allineata dal test
// "il dettaglio dei fondi rischi riproduce BALANCE_HIERARCHY_GROUPS".
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
function labelFor(code: string): { label: string; shortLabel?: string; dettaglio?: true } {
  const relabel = CONFRONTO_RELABEL[code];
  const rettifiche = GRAFIA_RETTIFICHE[code];
  const pickerLabel = GRAFIA_SELETTORE[code];
  const label = (
    pickerLabel ?? relabel ?? rettifiche ?? EXTRA_LABELS[code] ?? code
  ).trim();
  const shortLabel = relabel !== undefined && relabel.trim() !== label ? relabel.trim() : undefined;
  // Unico punto in cui i due spazi iniziali di GRAFIA_RETTIFICHE vengono letti.
  const dettaglio = rettifiche !== undefined && rettifiche.startsWith("  ") ? true : undefined;
  return {
    label,
    ...(shortLabel !== undefined ? { shortLabel } : {}),
    ...(dettaglio !== undefined ? { dettaglio } : {}),
  };
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
  const { label, shortLabel, dettaglio } = labelFor(code);
  return { code, parent, section, order, label, shortLabel, dettaglio };
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

const depthOfVoce = (v: Voce): number => {
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

/** Quanti aggregati stanno sopra la voce (0 = voce di primo livello). */
export function depthOf(code: string): number {
  const v = BY_CODE.get(code);
  return v === undefined ? 0 : depthOfVoce(v);
}

/**
 * La voce è una sotto-voce di dettaglio, quella che Rettifiche rientra.
 * NON coincide con depthOf(code) > 0, e la differenza è misurata, non
 * supposta: sulle 78 righe che RettificheTab rende con renderSection,
 * depthOf > 0 ne seleziona 42, questa 32. Le 10 di scarto sono sp12a..h e
 * ce17a/b — voci che il catalogo appende a un aggregato sintetico
 * (sp12_riserve, ce17_rettifiche_attivita_fin) ma che nello schema art. 2424
 * stanno al livello dei numeri romani / dei numeri arabi di sezione, portano
 * già la propria lettera ("A.II)", "18)") e non vanno rientrate.
 * Il confronto è pinnato in ivcee-catalog-parity.test.ts.
 */
export function isDettaglio(code: string): boolean {
  return BY_CODE.get(code)?.dettaglio === true;
}

/** Le voci di una sezione, in ordine di resa, fino alla profondità indicata. */
export function sectionRows(section: IvceeSection, maxDepth?: number): Voce[] {
  const roots = VOCI.filter((v) => v.section === section && v.parent === null)
    .sort((a, b) => a.order - b.order);
  const out: Voce[] = [];
  const walk = (v: Voce) => {
    if (maxDepth !== undefined && depthOfVoce(v) > maxDepth) return;
    out.push(v);
    for (const c of childrenOf(v.code)) walk(c);
  };
  roots.forEach(walk);
  return out;
}

// ===== Contropartite selezionabili nel picker di Rettifiche =====
// Arrivava da pratica-rettifiche-rules.ts: era l'ULTIMO consumatore delle due
// grafie oltre a questo catalogo, e senza di loro non poteva restare là (il
// catalogo importa quel modulo: la direzione opposta chiuderebbe un ciclo,
// fatale al caricamento — vedi Task 8). La POLITICA resta di là
// (NON_POSTABLE_FIELDS, fieldCategory, COUNTERPART_GROUPS): qui c'è solo la
// proiezione. L'elenco dei codici è quello di GRAFIA_RETTIFICHE, non VOCI:
// VOCI ne ha 7 in più — sp14a..d e ce03a, che nel selettore non sono mai
// comparse, più sp16_debiti_breve e sp17_debiti_lungo, che sarebbero comunque
// esclusi da NON_POSTABLE_FIELDS (quindi solo 5 cambierebbero il menu, ma i
// codici in più sono 7). Il campo `label` non viene reso (RettificheTab usa
// labelOf sul codice) ma è calcolato come prima, per non cambiare nulla di
// nascosto.
export const COUNTERPART_OPTIONS: Array<{ group: string; category: AcctCategory; field: string; label: string }> = (() => {
  return Object.keys(GRAFIA_RETTIFICHE)
    .filter((k) => !NON_POSTABLE_FIELDS.has(k))
    .sort()
    .flatMap((field) => {
      const cat = fieldCategory(field);
      if (!cat) return [];
      const group = COUNTERPART_GROUPS.find((g) => g.category === cat)!.label;
      const label = GRAFIA_SELETTORE[field] ?? GRAFIA_RETTIFICHE[field].trim();
      return [{ group, category: cat, field, label }];
    });
})();

// ===== Prospetto SP per riga (forecast/balance, report-appendices) =====
// Assorbito da lib/ivcee-balance-catalog.ts (Task 4). Tipi, helper e lista
// copiati senza modifiche di contenuto, salvo la sostituzione nel blocco
// debiti entro/oltre più sotto: la catena di ternari che ricostruiva i nomi
// dei campi da un suffisso ora li legge da childrenOf(), che il catalogo già
// possiede. Non è la sostituzione descritta nel piano — quella (etichetta
// da labelOf().replace(...)) rompeva ATTESI_BALANCE su 4 dei 7 gruppi
// (labelOf ritorna il testo più lungo del picker, "Debiti vs banche (entro)",
// non "Banche"); vedi il commento sul posto dove la didascalia è risolta.

export type BalanceValues = Record<string, number | null | undefined>;

export interface BalanceStatementRow {
  label: string;
  field?: string;
  computed?: (balance: BalanceValues) => number;
  isTotal?: boolean;
  isSubtotal?: boolean;
  indent?: boolean;
}

const n = (balance: BalanceValues, field: string): number => Number(balance[field] || 0);
const sum = (balance: BalanceValues, fields: string[]): number =>
  fields.reduce((total, field) => total + n(balance, field), 0);

export const BALANCE_HIERARCHY_GROUPS = [
  {
    title: "Immobilizzazioni finanziarie",
    aggregate: "sp04_immob_finanziarie",
    details: [
      ["sp04a_partecipazioni", "Partecipazioni"],
      ["sp04b_crediti_immob_breve", "Crediti entro 12 mesi"],
      ["sp04c_crediti_immob_lungo", "Crediti oltre 12 mesi"],
      ["sp04d_altri_titoli", "Altri titoli"],
      ["sp04e_strumenti_derivati_attivi", "Derivati attivi"],
    ],
  },
  {
    title: "Rimanenze",
    aggregate: "sp05_rimanenze",
    details: [
      ["sp05a_materie_prime", "Materie prime"],
      ["sp05b_prodotti_in_corso", "Prodotti in corso"],
      ["sp05c_lavori_in_corso", "Lavori in corso"],
      ["sp05d_prodotti_finiti", "Prodotti finiti"],
      ["sp05e_acconti", "Acconti"],
    ],
  },
  {
    title: "Crediti entro 12 mesi",
    aggregate: "sp06_crediti_breve",
    details: [
      ["sp06a_crediti_clienti_breve", "Clienti"],
      ["sp06b_crediti_controllate_breve", "Controllate"],
      ["sp06c_crediti_collegate_breve", "Collegate"],
      ["sp06d_crediti_controllanti_breve", "Controllanti"],
      ["sp06e_crediti_tributari_breve", "Crediti tributari"],
      ["sp06f_imposte_anticipate_breve", "Imposte anticipate"],
      ["sp06g_crediti_altri_breve", "Altri"],
    ],
  },
  {
    title: "Crediti oltre 12 mesi",
    aggregate: "sp07_crediti_lungo",
    details: [
      ["sp07a_crediti_clienti_lungo", "Clienti"],
      ["sp07b_crediti_controllate_lungo", "Controllate"],
      ["sp07c_crediti_collegate_lungo", "Collegate"],
      ["sp07d_crediti_controllanti_lungo", "Controllanti"],
      ["sp07e_crediti_tributari_lungo", "Crediti tributari"],
      ["sp07f_imposte_anticipate_lungo", "Imposte anticipate"],
      ["sp07g_crediti_altri_lungo", "Altri"],
    ],
  },
  {
    title: "Riserve",
    aggregate: "sp12_riserve",
    details: [
      ["sp12a_riserva_sovrapprezzo", "Sovrapprezzo azioni"],
      ["sp12b_riserve_rivalutazione", "Rivalutazione"],
      ["sp12c_riserva_legale", "Riserva legale"],
      ["sp12d_riserve_statutarie", "Riserve statutarie"],
      ["sp12e_altre_riserve", "Altre riserve"],
      ["sp12f_riserva_copertura_flussi", "Copertura flussi"],
      ["sp12g_utili_perdite_portati", "Utili/perdite portati"],
      ["sp12h_riserva_neg_azioni_proprie", "Riserva negativa azioni proprie"],
    ],
  },
  {
    title: "Fondi per rischi e oneri",
    aggregate: "sp14_fondi_rischi",
    details: [
      ["sp14a_fondi_trattamento_quiescenza", "Quiescenza"],
      ["sp14b_fondi_imposte", "Imposte, anche differite"],
      ["sp14c_strumenti_derivati_passivi", "Derivati passivi"],
      ["sp14d_altri_fondi", "Altri fondi"],
    ],
  },
  {
    title: "Debiti entro 12 mesi",
    aggregate: "sp16_debiti_breve",
    details: [
      ["sp16a_debiti_banche_breve", "Banche"],
      ["sp16b_debiti_altri_finanz_breve", "Altri finanziatori"],
      ["sp16c_debiti_obbligazioni_breve", "Obbligazioni"],
      ["sp16d_debiti_fornitori_breve", "Fornitori"],
      ["sp16e_debiti_tributari_breve", "Debiti tributari"],
      ["sp16f_debiti_previdenza_breve", "Debiti previdenziali"],
      ["sp16g_altri_debiti_breve", "Altri debiti"],
    ],
  },
  {
    title: "Debiti oltre 12 mesi",
    aggregate: "sp17_debiti_lungo",
    details: [
      ["sp17a_debiti_banche_lungo", "Banche"],
      ["sp17b_debiti_altri_finanz_lungo", "Altri finanziatori"],
      ["sp17c_debiti_obbligazioni_lungo", "Obbligazioni"],
      ["sp17d_debiti_fornitori_lungo", "Fornitori"],
      ["sp17e_debiti_tributari_lungo", "Debiti tributari"],
      ["sp17f_debiti_previdenza_lungo", "Debiti previdenziali"],
      ["sp17g_altri_debiti_lungo", "Altri debiti"],
    ],
  },
] as const;

const debtTotal = (balance: BalanceValues) => n(balance, "sp16_debiti_breve") + n(balance, "sp17_debiti_lungo");
const equityTotal = (balance: BalanceValues) => n(balance, "sp11_capitale") + n(balance, "sp12_riserve") + n(balance, "sp13_utile_perdita");
const liabilityTotal = (balance: BalanceValues) => equityTotal(balance) + debtTotal(balance) + sum(balance, ["sp14_fondi_rischi", "sp15_tfr", "sp18_ratei_risconti_passivi"]);

export const BALANCE_STATEMENT_ROWS: BalanceStatementRow[] = [
  { label: "ATTIVO", isTotal: true },
  { label: "A) Crediti verso soci per versamenti ancora dovuti", field: "sp01_crediti_soci" },
  { label: "B) IMMOBILIZZAZIONI", isSubtotal: true },
  { label: "I - Immobilizzazioni immateriali", field: "sp02_immob_immateriali", indent: true },
  { label: "II - Immobilizzazioni materiali", field: "sp03_immob_materiali", indent: true },
  { label: "III - Immobilizzazioni finanziarie", field: "sp04_immob_finanziarie", indent: true },
  { label: "1) Partecipazioni", field: "sp04a_partecipazioni", indent: true },
  { label: "2) Crediti entro 12 mesi", field: "sp04b_crediti_immob_breve", indent: true },
  { label: "2) Crediti oltre 12 mesi", field: "sp04c_crediti_immob_lungo", indent: true },
  { label: "Totale crediti immobilizzati", computed: (b) => sum(b, ["sp04b_crediti_immob_breve", "sp04c_crediti_immob_lungo"]), indent: true },
  { label: "3) Altri titoli", field: "sp04d_altri_titoli", indent: true },
  { label: "4) Strumenti finanziari derivati attivi", field: "sp04e_strumenti_derivati_attivi", indent: true },
  { label: "Totale immobilizzazioni", field: "fixed_assets", isSubtotal: true },
  { label: "C) ATTIVO CIRCOLANTE", isSubtotal: true },
  { label: "I - Rimanenze", field: "sp05_rimanenze", indent: true },
  { label: "  materie prime", field: "sp05a_materie_prime", indent: true },
  { label: "  prodotti in corso", field: "sp05b_prodotti_in_corso", indent: true },
  { label: "  lavori in corso", field: "sp05c_lavori_in_corso", indent: true },
  { label: "  prodotti finiti", field: "sp05d_prodotti_finiti", indent: true },
  { label: "  acconti", field: "sp05e_acconti", indent: true },
  { label: "II - Crediti entro 12 mesi", field: "sp06_crediti_breve", indent: true },
  ...BALANCE_HIERARCHY_GROUPS[2].details.map(([field, label]) => ({ label: `  ${label}`, field, indent: true })),
  { label: "II - Crediti oltre 12 mesi", field: "sp07_crediti_lungo", indent: true },
  ...BALANCE_HIERARCHY_GROUPS[3].details.map(([field, label]) => ({ label: `  ${label}`, field, indent: true })),
  { label: "III - Attività finanziarie non immobilizzate", field: "sp08_attivita_finanziarie", indent: true },
  { label: "IV - Disponibilità liquide", field: "sp09_disponibilita_liquide", indent: true },
  { label: "Totale attivo circolante", field: "current_assets", isSubtotal: true },
  { label: "D) Ratei e risconti attivi", field: "sp10_ratei_risconti_attivi" },
  { label: "TOTALE ATTIVO", field: "total_assets", isTotal: true },
  { label: "PASSIVO E PATRIMONIO NETTO", isTotal: true },
  { label: "A) PATRIMONIO NETTO", isSubtotal: true },
  { label: "I - Capitale", field: "sp11_capitale", indent: true },
  ...BALANCE_HIERARCHY_GROUPS[4].details.map(([field, label]) => ({ label, field, indent: true })),
  { label: "IX - Utile (perdita) dell'esercizio", field: "sp13_utile_perdita", indent: true },
  { label: "Totale patrimonio netto", computed: equityTotal, isSubtotal: true },
  { label: "B) Fondi per rischi e oneri", field: "sp14_fondi_rischi" },
  ...BALANCE_HIERARCHY_GROUPS[5].details.map(([field, label]) => ({ label: `  ${label}`, field, indent: true })),
  { label: "C) Trattamento di fine rapporto", field: "sp15_tfr" },
  { label: "D) DEBITI", isSubtotal: true },
  ...(() => {
    const entroList = childrenOf("sp16_debiti_breve");
    const oltreList = childrenOf("sp17_debiti_lungo");
    if (entroList.length !== oltreList.length) {
      throw new Error(
        `catalogo incoerente: ${entroList.length} debiti entro vs ${oltreList.length} oltre`,
      );
    }
    // La didascalia di gruppo ("Banche", "Altri finanziatori", ...) non ha
    // fonte nel catalogo: labelOf(entro.code) risolve al testo del picker
    // ("Debiti vs banche (entro)"), più lungo; labelOf(..., "contestuale")
    // risolve a "entro 12 mesi", che è la sotto-riga, non l'intestazione di
    // gruppo; DEBT_GROUPS (lib/pratica-rettifiche-rules.ts) porta la
    // numerazione OIC ("1) Debiti verso banche"). Nessuno dei tre coincide
    // con ATTESI_BALANCE. Manca un terzo ruolo di etichetta (o un
    // `groupLabel` sull'aggregato sp16/sp17 nel catalogo) — non lo si
    // aggiunge qui: è una decisione dei task successivi. Fino ad allora la
    // didascalia si legge dal gruppo che già la porta,
    // BALANCE_HIERARCHY_GROUPS[6]/[7] poco sopra in questo file, cercando
    // per CODICE (non per indice: un ottavo figlio in childrenOf non deve
    // silenziosamente ricevere una didascalia sbagliata o assente).
    const captionFor = (code: string): string => {
      const found = BALANCE_HIERARCHY_GROUPS[6].details.find(([f]) => f === code)?.[1];
      if (!found) throw new Error(`nessuna etichetta di gruppo per ${code}`);
      return found;
    };
    return entroList.flatMap((entro, i) => {
      const oltre = oltreList[i];
      return [
        { label: captionFor(entro.code),
          computed: (b: BalanceValues) => n(b, entro.code) + n(b, oltre.code), indent: true },
        { label: "  entro 12 mesi", field: entro.code, indent: true },
        { label: "  oltre 12 mesi", field: oltre.code, indent: true },
      ];
    });
  })(),
  { label: "Totale debiti", computed: debtTotal, isSubtotal: true },
  { label: "E) Ratei e risconti passivi", field: "sp18_ratei_risconti_passivi" },
  { label: "TOTALE PASSIVO E PATRIMONIO NETTO", computed: liabilityTotal, isTotal: true },
  { label: "DIFFERENZA (Attivo - Passivo)", computed: (b) => n(b, "total_assets") - liabilityTotal(b), isSubtotal: true },
];

export const balanceRowValue = (balance: BalanceValues, row: BalanceStatementRow): number => {
  if (row.computed) return row.computed(balance);
  return row.field ? n(balance, row.field) : 0;
};

// ===== Prospetto CE per riga (forecast/income) =====
// Spostato verbatim da app/forecast/income/page.tsx (IncomeStatementTable,
// `const rows` intorno alla riga 549): stessa forma di BALANCE_STATEMENT_ROWS,
// così i due prospetti si rendono con lo stesso codice. Unico adattamento:
// `indent: 1` → `indent: true` (il tipo locale del componente portava un
// livello numerico; BalanceStatementRow porta un booleano) — tocca ce08b/c/a/d,
// ce09a/b/c/d (+ il suo subtotale "Totale ammortamenti e svalutazioni"),
// ce17a/ce17b. Nessun'altra proprietà, etichetta o ordine è stata cambiata.
// NOTA (non risolta qui, per scelta): "4) Incrementi di immobilizzazioni per
// lavori interni" è la stessa dicitura autonoma già assegnata a
// ce03_lavori_interni in CONFRONTO_RELABEL più sopra in questo file — il
// Confronto e questa vista non concordano su quale voce porti quel testo.
// Spostata così com'era: non è compito di questo task scegliere un vincitore.
export const INCOME_STATEMENT_ROWS: BalanceStatementRow[] = [
  // A) VALORE DELLA PRODUZIONE
  { label: "A) VALORE DELLA PRODUZIONE", isTotal: true },
  { label: "1) Ricavi delle vendite e delle prestazioni", field: "ce01_ricavi_vendite" },
  { label: "2) Variazioni delle rim. di prodotti in corso di lav., semilav. e finiti", field: "ce02_variazioni_rimanenze" },
  { label: "3) Variazioni dei lavori in corso su ordinazione", field: "ce03_lavori_interni" },
  { label: "4) Incrementi di immobilizzazioni per lavori interni", field: "ce03a_incrementi_immobilizzazioni" },
  { label: "5) Altri ricavi e proventi", field: "ce04_altri_ricavi" },
  { label: "Totale Valore della Produzione", field: "production_value", isSubtotal: true },
  // B) COSTI DELLA PRODUZIONE
  { label: "B) COSTI DELLA PRODUZIONE", isTotal: true },
  { label: "6) Materie prime, sussidiarie, di consumo e di merci", field: "ce05_materie_prime" },
  { label: "7) Servizi", field: "ce06_servizi" },
  { label: "8) Godimento di beni di terzi", field: "ce07_godimento_beni" },
  { label: "9) Personale", field: "ce08_costi_personale" },
  { label: "a) Salari e stipendi", field: "ce08b_salari_stipendi", indent: true },
  { label: "b) Oneri sociali", field: "ce08c_oneri_sociali", indent: true },
  { label: "c) Trattamento di fine rapporto", field: "ce08a_tfr_accrual", indent: true },
  { label: "d) Trattamento di quiescenza e simili" },
  { label: "e) Altri costi del personale", field: "ce08d_altri_costi_personale", indent: true },
  { label: "10) Ammortamenti e svalutazioni:" },
  { label: "a) Ammortamento delle immobilizzazioni immateriali", field: "ce09a_ammort_immateriali", indent: true },
  { label: "b) Ammortamento delle immobilizzazioni materiali", field: "ce09b_ammort_materiali", indent: true },
  { label: "c) Altre svalutazioni delle immobilizzazioni", field: "ce09c_svalutazioni", indent: true },
  { label: "d) Sval. dei crediti compresi nell'attivo circ. e delle disp. liquide", field: "ce09d_svalutazione_crediti", indent: true },
  { label: "Totale ammortamenti e svalutazioni", field: "ce09_ammortamenti", indent: true },
  { label: "11) Variazioni delle rim. di materie prime, sussidiarie, di cons. e merci", field: "ce10_var_rimanenze_mat_prime" },
  { label: "12) Accantonamenti per rischi", field: "ce11_accantonamenti" },
  { label: "13) Altri accantonamenti", field: "ce11b_altri_accantonamenti" },
  { label: "14) Oneri diversi di gestione", field: "ce12_oneri_diversi" },
  { label: "Totale Costi della Produzione", field: "production_cost", isSubtotal: true },
  // EBITDA
  { label: "EBITDA (MOL)", field: "ebitda", isSubtotal: true },
  // EBIT
  { label: "EBIT (Risultato Operativo)", field: "ebit", isSubtotal: true },
  // C) PROVENTI E ONERI FINANZIARI
  { label: "C) PROVENTI E ONERI FINANZIARI", isTotal: true },
  { label: "15) Proventi da partecipazioni", field: "ce13_proventi_partecipazioni" },
  { label: "16) Altri proventi finanziari", field: "ce14_altri_proventi_finanziari" },
  { label: "17) Interessi e altri oneri finanziari", field: "ce15_oneri_finanziari" },
  { label: "17-bis) Utili e perdite su cambi", field: "ce16_utili_perdite_cambi" },
  { label: "Totale Proventi/Oneri Finanziari", field: "financial_result", isSubtotal: true },
  // D) RETTIFICHE DI VALORE
  { label: "D) RETTIFICHE DI VALORE ATTIVITA' FINANZIARIE", isTotal: true },
  { label: "18) Rivalutazioni", field: "ce17a_rivalutazioni", indent: true },
  { label: "19) Svalutazioni", field: "ce17b_svalutazioni", indent: true },
  { label: "Totale rettifiche di valore", field: "ce17_rettifiche_attivita_fin", isSubtotal: true },
  // E) PROVENTI E ONERI STRAORDINARI
  { label: "E) PROVENTI E ONERI STRAORDINARI", isTotal: true },
  { label: "20) Proventi straordinari", field: "ce18_proventi_straordinari" },
  { label: "21) Oneri straordinari", field: "ce19_oneri_straordinari" },
  { label: "Totale Proventi/Oneri Straordinari", field: "extraordinary_result", isSubtotal: true },
  // RISULTATO PRIMA DELLE IMPOSTE
  { label: "Risultato prima delle imposte", field: "profit_before_tax", isSubtotal: true },
  // IMPOSTE
  { label: "22) Imposte sul reddito", field: "ce20_imposte" },
  // UTILE/PERDITA
  { label: "23) UTILE (PERDITA) DELL'ESERCIZIO", field: "net_profit", isTotal: true },
];
