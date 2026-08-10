// Key P&L items the user can override
export const EDITABLE_CE_CODES = [
  "ce01_ricavi_vendite",
  "ce02_variazioni_rimanenze",
  "ce03_lavori_interni",
  "ce04_altri_ricavi",
  "ce05_materie_prime",
  "ce06_servizi",
  "ce07_godimento_beni",
  "ce08_costi_personale",
  "ce09_ammortamenti",
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
  "ce18_proventi_straordinari",
  "ce19_oneri_straordinari",
  "ce20_imposte",
];

export const CE_OVERRIDE_FIELD_BY_CODE: Record<string, string> = {
  ce01_ricavi_vendite: "ce01_override",
  ce02_variazioni_rimanenze: "ce02_override",
  ce03_lavori_interni: "ce03_override",
  ce03a_incrementi_immobilizzazioni: "ce03a_override",
  ce04_altri_ricavi: "ce04_override",
  ce05_materie_prime: "ce05_override",
  ce06_servizi: "ce06_override",
  ce07_godimento_beni: "ce07_override",
  ce08_costi_personale: "ce08_override",
  ce08a_tfr_accrual: "ce08a_override",
  ce08b_salari_stipendi: "ce08b_override",
  ce08c_oneri_sociali: "ce08c_override",
  ce08d_altri_costi_personale: "ce08d_override",
  ce09_ammortamenti: "ce09_override",
  ce09a_ammort_immateriali: "ce09a_override",
  ce09b_ammort_materiali: "ce09b_override",
  ce09c_svalutazioni: "ce09c_override",
  ce09d_svalutazione_crediti: "ce09d_override",
  ce10_var_rimanenze_mat_prime: "ce10_override",
  ce11_accantonamenti: "ce11_override",
  ce11b_altri_accantonamenti: "ce11b_override",
  ce12_oneri_diversi: "ce12_override",
  ce13_proventi_partecipazioni: "ce13_override",
  ce14_altri_proventi_finanziari: "ce14_override",
  ce15_oneri_finanziari: "ce15_override",
  ce16_utili_perdite_cambi: "ce16_override",
  ce17a_rivalutazioni: "ce17a_override",
  ce17b_svalutazioni: "ce17b_override",
  ce18_proventi_straordinari: "ce18_override",
  ce19_oneri_straordinari: "ce19_override",
  ce20_imposte: "ce20_override",
};

export function buildCeOverridePayload(values: Record<string, string>): Record<string, number | null> {
  return Object.fromEntries(
    Object.entries(CE_OVERRIDE_FIELD_BY_CODE).map(([code, field]) => {
      const raw = values[code]?.trim();
      const parsed = raw ? Number.parseFloat(raw) : Number.NaN;
      return [field, Number.isFinite(parsed) ? parsed : null];
    })
  );
}

// Codes that make up EBITDA: VP items are positive, cost items are negative
export const VP_CODES = ["ce01_ricavi_vendite", "ce02_variazioni_rimanenze", "ce03_lavori_interni", "ce03a_incrementi_immobilizzazioni", "ce04_altri_ricavi"];
export const EBITDA_COST_CODES = [
  "ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
  "ce08_costi_personale", "ce10_var_rimanenze_mat_prime",
  "ce11_accantonamenti", "ce11b_altri_accantonamenti", "ce12_oneri_diversi",
];

// Always show these rows even when both values are zero
export const ALWAYS_SHOW_CODES = new Set([
  "ce20_imposte", "_ebitda", "_ebitda_pct", "_net_profit",
  "_totale_attivo", "_totale_passivo",
  // CE section headers and subtotals
  "_hdr_a", "_hdr_b", "_hdr_c", "_hdr_d", "_hdr_e",
  "_totale_vp", "_totale_cp", "_ebit",
  "_totale_fin", "_totale_straord", "_profit_before_tax",
  // BS section headers and subtotals
  "_hdr_attivo", "_hdr_immob", "_hdr_circ", "_hdr_passivo", "_hdr_pn", "_hdr_debiti",
  "_totale_immob", "_totale_circ", "_totale_pn", "_totale_debiti", "_differenza",
  // Debt creditor-type group headers — always visible (OIC art. 2424 structure)
  "_debt_banche", "_debt_altri_finanz", "_debt_obbligazioni",
  "_debt_fornitori", "_debt_tributari", "_debt_previdenza", "_debt_altri",
]);

// BS codes: sp01-sp10 = Attivo, sp11-sp18 = Passivo
export const ATTIVO_CODES = [
  "sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
  "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve",
  "sp07_crediti_lungo", "sp08_attivita_finanziarie", "sp09_disponibilita_liquide",
  "sp10_ratei_risconti_attivi",
];
export const PASSIVO_CODES = [
  "sp11_capitale", "sp12_riserve", "sp13_utile_perdita",
  "sp14_fondi_rischi", "sp15_tfr", "sp16_debiti_breve",
  "sp17_debiti_lungo", "sp18_ratei_risconti_passivi",
];

// Detail fields that should always show when their parent is non-zero
export const DETAIL_PARENTS: Record<string, string> = {
  sp05a_materie_prime: "sp05_rimanenze",
  sp05b_prodotti_in_corso: "sp05_rimanenze",
  sp05c_lavori_in_corso: "sp05_rimanenze",
  sp05d_prodotti_finiti: "sp05_rimanenze",
  sp05e_acconti: "sp05_rimanenze",
  sp06a_crediti_clienti_breve: "sp06_crediti_breve",
  sp06b_crediti_controllate_breve: "sp06_crediti_breve",
  sp06c_crediti_collegate_breve: "sp06_crediti_breve",
  sp06d_crediti_controllanti_breve: "sp06_crediti_breve",
  sp06e_crediti_tributari_breve: "sp06_crediti_breve",
  sp06f_imposte_anticipate_breve: "sp06_crediti_breve",
  sp06g_crediti_altri_breve: "sp06_crediti_breve",
  sp07a_crediti_clienti_lungo: "sp07_crediti_lungo",
  sp07b_crediti_controllate_lungo: "sp07_crediti_lungo",
  sp07c_crediti_collegate_lungo: "sp07_crediti_lungo",
  sp07d_crediti_controllanti_lungo: "sp07_crediti_lungo",
  sp07e_crediti_tributari_lungo: "sp07_crediti_lungo",
  sp07f_imposte_anticipate_lungo: "sp07_crediti_lungo",
  sp07g_crediti_altri_lungo: "sp07_crediti_lungo",
  sp04a_partecipazioni: "sp04_immob_finanziarie",
  sp04b_crediti_immob_breve: "sp04_immob_finanziarie",
  sp04c_crediti_immob_lungo: "sp04_immob_finanziarie",
  sp04d_altri_titoli: "sp04_immob_finanziarie",
  sp04e_strumenti_derivati_attivi: "sp04_immob_finanziarie",
  sp12a_riserva_sovrapprezzo: "sp12_riserve",
  sp12b_riserve_rivalutazione: "sp12_riserve",
  sp12c_riserva_legale: "sp12_riserve",
  sp12d_riserve_statutarie: "sp12_riserve",
  sp12e_altre_riserve: "sp12_riserve",
  sp12f_riserva_copertura_flussi: "sp12_riserve",
  sp12g_utili_perdite_portati: "sp12_riserve",
  sp12h_riserva_neg_azioni_proprie: "sp12_riserve",
  ce08b_salari_stipendi: "ce08_costi_personale",
  ce08c_oneri_sociali: "ce08_costi_personale",
  ce08a_tfr_accrual: "ce08_costi_personale",
  ce08d_altri_costi_personale: "ce08_costi_personale",
  ce09a_ammort_immateriali: "ce09_ammortamenti",
  ce09b_ammort_materiali: "ce09_ammortamenti",
  ce09c_svalutazioni: "ce09_ammortamenti",
  ce09d_svalutazione_crediti: "ce09_ammortamenti",
  ce17a_rivalutazioni: "ce17_rettifiche_attivita_fin",
  ce17b_svalutazioni: "ce17_rettifiche_attivita_fin",
  sp16a_debiti_banche_breve: "sp16_debiti_breve",
  sp16b_debiti_altri_finanz_breve: "sp16_debiti_breve",
  sp16c_debiti_obbligazioni_breve: "sp16_debiti_breve",
  sp16d_debiti_fornitori_breve: "sp16_debiti_breve",
  sp16e_debiti_tributari_breve: "sp16_debiti_breve",
  sp16f_debiti_previdenza_breve: "sp16_debiti_breve",
  sp16g_altri_debiti_breve: "sp16_debiti_breve",
  sp17a_debiti_banche_lungo: "sp17_debiti_lungo",
  sp17b_debiti_altri_finanz_lungo: "sp17_debiti_lungo",
  sp17c_debiti_obbligazioni_lungo: "sp17_debiti_lungo",
  sp17d_debiti_fornitori_lungo: "sp17_debiti_lungo",
  sp17e_debiti_tributari_lungo: "sp17_debiti_lungo",
  sp17f_debiti_previdenza_lungo: "sp17_debiti_lungo",
  sp17g_altri_debiti_lungo: "sp17_debiti_lungo",
};
// Extra-Accounting Alerts (Segnali Extracontabili)
export const EXTRA_ALERT_DEFS: Array<{ key: string; label: string }> = [
  {
    key: "retribuzioni",
    label:
      "Debiti per retribuzione scaduti da almeno 30 giorni pari a oltre il 50% dell'ammontare complessivo mensile delle retribuzioni",
  },
  {
    key: "fornitori",
    label:
      "Debiti verso fornitori scaduti da almeno 90 giorni di ammontare superiore ai debiti non ancora scaduti",
  },
  {
    key: "banche",
    label:
      "Esposizioni nei confronti delle banche e altri intermediari finanziari scadute da più di 60 giorni o che abbiano superato il limite degli affidamenti da più di 60 giorni, purché rappresentino almeno il 5% del totale delle esposizioni",
  },
  {
    key: "inps",
    label:
      "INPS: ritardo di oltre 90 giorni nel versamento di contributi previdenziali di ammontare superiore al 30% di quelli dovuti nell'anno precedente e all'importo di €15.000 (con lavoratori subordinati) o €5.000 (senza lavoratori subordinati)",
  },
  {
    key: "inail",
    label:
      "INAIL: ritardo di oltre 90 giorni nel versamento di premi assicurativi di ammontare superiore a €5.000",
  },
  {
    key: "riscossione",
    label:
      "Agente della Riscossione: crediti affidati per la riscossione, auto dichiarati o definitivamente accertati e scaduti da oltre 90 giorni, superiori a €100.000 (imprese individuali), €200.000 (società di persone), €500.000 (società di capitali)",
  },
  {
    key: "iva",
    label:
      "Agenzia delle Entrate: debiti IVA scaduti e non versati superiori a €20.000, o superiori a €5.000 se di entità pari ad oltre il 10% del volume d'affari dell'anno precedente",
  },
];

