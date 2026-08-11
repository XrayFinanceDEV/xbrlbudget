// ===== PROPOSAL RULES =====
// When a field is edited, propose a counterpart adjustment shown in the review dialog.
// "same" = counterpart moves in same direction as delta (e.g. cost up → liability up)
// "inverse" = counterpart moves opposite (e.g. depreciation up → asset down)
export interface ProposalRule {
  editable: string;
  counterpart: string;
  direction: "same" | "inverse";
  explanation: string; // Italian description of the double-entry logic
  // Optional: allow splitting the counterpart amount between two fields
  splitAlt?: { field: string; label: string };
  // Optional: alternative counterpart when the delta is negative (e.g. credit decrease → loss, not revenue decrease)
  counterpartNeg?: string;
  directionNeg?: "same" | "inverse";
  explanationNeg?: string;
  splitAltNeg?: { field: string; label: string };
}
export const PROPOSAL_RULES: ProposalRule[] = [
  // ===== BS ATTIVO → CE =====
  { editable: "sp01_crediti_soci", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs soci → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti vs soci → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp02_immob_immateriali", counterpart: "ce03_lavori_interni", direction: "same", explanation: "Più immob. immateriali → più incrementi per lavori interni" },
  { editable: "sp03_immob_materiali", counterpart: "ce03_lavori_interni", direction: "same", explanation: "Più immob. materiali → più incrementi per lavori interni" },
  { editable: "sp04a_partecipazioni", counterpart: "ce13_proventi_partecipazioni", direction: "same", explanation: "Più partecipazioni → più proventi da partecipazioni" },
  { editable: "sp04b_crediti_immob_breve", counterpart: "ce14_altri_proventi_finanziari", direction: "same", explanation: "Più crediti immob. breve → più proventi finanziari" },
  { editable: "sp04c_crediti_immob_lungo", counterpart: "ce14_altri_proventi_finanziari", direction: "same", explanation: "Più crediti immob. lungo → più proventi finanziari" },
  { editable: "sp04d_altri_titoli", counterpart: "ce14_altri_proventi_finanziari", direction: "same", explanation: "Più altri titoli → più proventi finanziari" },
  { editable: "sp04e_strumenti_derivati_attivi", counterpart: "ce14_altri_proventi_finanziari", direction: "same", explanation: "Più strumenti derivati attivi → più proventi finanziari" },
  { editable: "sp05_rimanenze", counterpart: "ce02_variazioni_rimanenze", direction: "same", explanation: "Più rimanenze → variazione positiva rimanenze" },
  { editable: "sp05a_materie_prime", counterpart: "ce10_var_rimanenze_mat_prime", direction: "inverse", explanation: "Più rimanenze materie → meno variazione mat. prime (costo)" },
  { editable: "sp05b_prodotti_in_corso", counterpart: "ce02_variazioni_rimanenze", direction: "same", explanation: "Più prodotti in c/lav → variazione positiva rimanenze" },
  { editable: "sp05c_lavori_in_corso", counterpart: "ce02_variazioni_rimanenze", direction: "same", explanation: "Più lavori in corso → variazione positiva rimanenze" },
  { editable: "sp05d_prodotti_finiti", counterpart: "ce02_variazioni_rimanenze", direction: "same", explanation: "Più prodotti finiti → variazione positiva rimanenze" },
  { editable: "sp05e_acconti", counterpart: "ce05_materie_prime", direction: "same", explanation: "Più acconti a fornitori → più costi materie prime" },
  { editable: "sp06_crediti_breve", counterpart: "ce01_ricavi_vendite", direction: "same", explanation: "Più crediti commerciali → più ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp06a_crediti_clienti_breve", counterpart: "ce01_ricavi_vendite", direction: "same", explanation: "Più crediti vs clienti → più ricavi vendite", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti clienti → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp06b_crediti_controllate_breve", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs controllate → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti controllate → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp06c_crediti_collegate_breve", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs collegate → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti collegate → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp06d_crediti_controllanti_breve", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs controllanti → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti controllanti → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp06e_crediti_tributari_breve", counterpart: "ce20_imposte", direction: "inverse", explanation: "Più crediti tributari → meno imposte" },
  { editable: "sp06f_imposte_anticipate_breve", counterpart: "ce20_imposte", direction: "inverse", explanation: "Più imposte anticipate → meno imposte correnti" },
  { editable: "sp06g_crediti_altri_breve", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti diversi → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti diversi → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp07_crediti_lungo", counterpart: "ce01_ricavi_vendite", direction: "same", explanation: "Più crediti oltre → più ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti oltre → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp07a_crediti_clienti_lungo", counterpart: "ce01_ricavi_vendite", direction: "same", explanation: "Più crediti clienti oltre → più ricavi vendite", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti clienti oltre → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp07b_crediti_controllate_lungo", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs controllate oltre → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti controllate oltre → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp07c_crediti_collegate_lungo", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs collegate oltre → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti collegate oltre → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp07d_crediti_controllanti_lungo", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti vs controllanti oltre → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti controllanti oltre → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp07e_crediti_tributari_lungo", counterpart: "ce20_imposte", direction: "inverse", explanation: "Più crediti tributari oltre → meno imposte" },
  { editable: "sp07f_imposte_anticipate_lungo", counterpart: "ce20_imposte", direction: "inverse", explanation: "Più imposte anticipate oltre → meno imposte correnti" },
  { editable: "sp07g_crediti_altri_lungo", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più crediti diversi oltre → più altri ricavi", counterpartNeg: "ce09d_svalutazione_crediti", directionNeg: "inverse", explanationNeg: "Meno crediti diversi oltre → svalutazione crediti / oneri diversi", splitAltNeg: { field: "ce12_oneri_diversi", label: "14) Oneri diversi di gestione" } },
  { editable: "sp08_attivita_finanziarie", counterpart: "ce14_altri_proventi_finanziari", direction: "same", explanation: "Più attività finanziarie → più proventi finanziari" },
  { editable: "sp09_disponibilita_liquide", counterpart: "ce01_ricavi_vendite", direction: "same", explanation: "Più liquidità → più ricavi (incasso)" },
  { editable: "sp10_ratei_risconti_attivi", counterpart: "ce04_altri_ricavi", direction: "same", explanation: "Più ratei attivi → più altri ricavi di competenza" },
  // ===== BS PASSIVO → CE =====
  { editable: "sp11_capitale", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più capitale → più liquidità (conferimento)" },
  { editable: "sp12a_riserva_sovrapprezzo", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più riserva sovrapprezzo → più liquidità (conferimento)" },
  { editable: "sp12b_riserve_rivalutazione", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più riserve rivalutazione → più liquidità" },
  { editable: "sp12c_riserva_legale", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più riserva legale → più liquidità" },
  { editable: "sp12d_riserve_statutarie", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più riserve statutarie → più liquidità" },
  { editable: "sp12e_altre_riserve", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più altre riserve → più liquidità" },
  { editable: "sp12f_riserva_copertura_flussi", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più riserva copertura flussi → più liquidità" },
  { editable: "sp12h_riserva_neg_azioni_proprie", counterpart: "sp09_disponibilita_liquide", direction: "inverse", explanation: "Più riserva neg. azioni proprie → meno liquidità (riacquisto)" },
  { editable: "sp12g_utili_perdite_portati", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più utili a nuovo → più liquidità" },
  { editable: "sp14_fondi_rischi", counterpart: "ce11_accantonamenti", direction: "same", explanation: "Più fondi rischi → più accantonamenti" },
  { editable: "sp15_tfr", counterpart: "ce08a_tfr_accrual", direction: "same", explanation: "Più fondo TFR → più accantonamento TFR" },
  { editable: "sp16a_debiti_banche_breve", counterpart: "ce15_oneri_finanziari", direction: "same", explanation: "Più debiti vs banche → più oneri finanziari" },
  { editable: "sp16b_debiti_altri_finanz_breve", counterpart: "ce15_oneri_finanziari", direction: "same", explanation: "Più debiti finanziari → più oneri finanziari" },
  { editable: "sp16c_debiti_obbligazioni_breve", counterpart: "ce15_oneri_finanziari", direction: "same", explanation: "Più debiti obbligazionari → più oneri finanziari" },
  { editable: "sp16d_debiti_fornitori_breve", counterpart: "ce06_servizi", direction: "same", explanation: "Più debiti fornitori → più costi per servizi / materie prime", splitAlt: { field: "ce05_materie_prime", label: "6) Per materie prime" } },
  { editable: "sp16e_debiti_tributari_breve", counterpart: "ce20_imposte", direction: "same", explanation: "Più debiti tributari → più imposte" },
  { editable: "sp16f_debiti_previdenza_breve", counterpart: "ce08c_oneri_sociali", direction: "same", explanation: "Più debiti previdenziali → più oneri sociali" },
  { editable: "sp16g_altri_debiti_breve", counterpart: "ce12_oneri_diversi", direction: "same", explanation: "Più altri debiti → più oneri diversi" },
  { editable: "sp17a_debiti_banche_lungo", counterpart: "ce15_oneri_finanziari", direction: "same", explanation: "Più debiti vs banche lungo → più oneri finanziari" },
  { editable: "sp17b_debiti_altri_finanz_lungo", counterpart: "ce15_oneri_finanziari", direction: "same", explanation: "Più debiti finanziari lungo → più oneri finanziari" },
  { editable: "sp17c_debiti_obbligazioni_lungo", counterpart: "ce15_oneri_finanziari", direction: "same", explanation: "Più debiti obbligazionari lungo → più oneri finanziari" },
  { editable: "sp17d_debiti_fornitori_lungo", counterpart: "ce06_servizi", direction: "same", explanation: "Più debiti fornitori lungo → più costi per servizi / materie prime", splitAlt: { field: "ce05_materie_prime", label: "6) Per materie prime" } },
  { editable: "sp17e_debiti_tributari_lungo", counterpart: "ce20_imposte", direction: "same", explanation: "Più debiti tributari lungo → più imposte" },
  { editable: "sp17f_debiti_previdenza_lungo", counterpart: "ce08c_oneri_sociali", direction: "same", explanation: "Più debiti previdenziali lungo → più oneri sociali" },
  { editable: "sp17g_altri_debiti_lungo", counterpart: "ce12_oneri_diversi", direction: "same", explanation: "Più altri debiti lungo → più oneri diversi" },
  { editable: "sp18_ratei_risconti_passivi", counterpart: "ce07_godimento_beni", direction: "same", explanation: "Più ratei passivi → più godimento beni di terzi" },
  // ===== CE → BS =====
  { editable: "ce01_ricavi_vendite", counterpart: "sp06a_crediti_clienti_breve", direction: "same", explanation: "Più ricavi → più crediti vs clienti" },
  { editable: "ce02_variazioni_rimanenze", counterpart: "sp05b_prodotti_in_corso", direction: "same", explanation: "Più variazione rimanenze → più rimanenze prodotti in c/lav" },
  { editable: "ce03_lavori_interni", counterpart: "sp03_immob_materiali", direction: "same", explanation: "Più incrementi per lavori interni → più immob. materiali" },
  { editable: "ce04_altri_ricavi", counterpart: "sp06g_crediti_altri_breve", direction: "same", explanation: "Più altri ricavi → più crediti diversi" },
  { editable: "ce05_materie_prime", counterpart: "sp16d_debiti_fornitori_breve", direction: "same", explanation: "Più costi materie prime → più debiti vs fornitori" },
  { editable: "ce06_servizi", counterpart: "sp16d_debiti_fornitori_breve", direction: "same", explanation: "Più costi servizi → più debiti vs fornitori" },
  { editable: "ce07_godimento_beni", counterpart: "sp18_ratei_risconti_passivi", direction: "same", explanation: "Più godimento beni terzi → più ratei e risconti passivi" },
  { editable: "ce08_costi_personale", counterpart: "sp16f_debiti_previdenza_breve", direction: "same", explanation: "Più costi personale → più debiti previdenziali" },
  { editable: "ce08b_salari_stipendi", counterpart: "sp16f_debiti_previdenza_breve", direction: "same", explanation: "Più salari e stipendi → più debiti previdenziali" },
  { editable: "ce08c_oneri_sociali", counterpart: "sp16f_debiti_previdenza_breve", direction: "same", explanation: "Più oneri sociali → più debiti previdenziali" },
  { editable: "ce08a_tfr_accrual", counterpart: "sp15_tfr", direction: "same", explanation: "Più TFR accantonato → più fondo TFR" },
  { editable: "ce08d_altri_costi_personale", counterpart: "sp16g_altri_debiti_breve", direction: "same", explanation: "Più altri costi personale → più altri debiti" },
  { editable: "ce09a_ammort_immateriali", counterpart: "sp02_immob_immateriali", direction: "inverse", explanation: "Più ammortamento → meno immobilizzazioni immateriali" },
  { editable: "ce09b_ammort_materiali", counterpart: "sp03_immob_materiali", direction: "inverse", explanation: "Più ammortamento → meno immobilizzazioni materiali" },
  { editable: "ce09c_svalutazioni", counterpart: "sp04a_partecipazioni", direction: "inverse", explanation: "Più svalutazioni → meno partecipazioni" },
  { editable: "ce09d_svalutazione_crediti", counterpart: "sp06a_crediti_clienti_breve", direction: "inverse", explanation: "Più svalutazione crediti → meno crediti verso clienti" },
  { editable: "ce11_accantonamenti", counterpart: "sp14_fondi_rischi", direction: "same", explanation: "Più accantonamenti rischi → più fondi per rischi e oneri" },
  { editable: "ce11b_altri_accantonamenti", counterpart: "sp14_fondi_rischi", direction: "same", explanation: "Più altri accantonamenti → più fondi rischi" },
  { editable: "ce12_oneri_diversi", counterpart: "sp16g_altri_debiti_breve", direction: "same", explanation: "Più oneri diversi → più altri debiti" },
  { editable: "ce13_proventi_partecipazioni", counterpart: "sp04a_partecipazioni", direction: "same", explanation: "Più proventi partecipazioni → più partecipazioni" },
  { editable: "ce14_altri_proventi_finanziari", counterpart: "sp08_attivita_finanziarie", direction: "same", explanation: "Più proventi finanziari → più attività finanziarie" },
  { editable: "ce15_oneri_finanziari", counterpart: "sp16a_debiti_banche_breve", direction: "same", explanation: "Più oneri finanziari → più debiti vs banche" },
  { editable: "ce16_utili_perdite_cambi", counterpart: "sp09_disponibilita_liquide", direction: "same", explanation: "Più utili su cambi → più liquidità" },
  { editable: "ce17a_rivalutazioni", counterpart: "sp04a_partecipazioni", direction: "same", explanation: "Più rivalutazioni → più partecipazioni" },
  { editable: "ce17b_svalutazioni", counterpart: "sp04a_partecipazioni", direction: "inverse", explanation: "Più svalutazioni → meno partecipazioni" },
  { editable: "ce18_proventi_straordinari", counterpart: "sp06g_crediti_altri_breve", direction: "same", explanation: "Più proventi straordinari → più crediti diversi" },
  { editable: "ce19_oneri_straordinari", counterpart: "sp16g_altri_debiti_breve", direction: "same", explanation: "Più oneri straordinari → più altri debiti" },
  { editable: "ce20_imposte", counterpart: "sp16e_debiti_tributari_breve", direction: "same", explanation: "Più imposte → più debiti tributari" },
];

// All editable fields = all proposal rule editables (every editable field has a proposal rule)
export const EDITABLE_RETTIFICHE = new Set(PROPOSAL_RULES.map((r) => r.editable));
// Fields that are counterpart targets — shown with special styling after proposals are applied
export const AUTO_ADJUSTED = new Set(PROPOSAL_RULES.map((r) => r.counterpart));

// Aggregate/computed fields that must NOT be used as counterparts —
// they are rebuilt from their sub-fields in recalcAggregates (or from CE for sp13),
// so posting a direct delta to them would be silently wiped out.
export const NON_POSTABLE_FIELDS = new Set([
  "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve", "sp07_crediti_lungo",
  "sp12_riserve", "sp13_utile_perdita", "sp16_debiti_breve", "sp17_debiti_lungo",
  "ce08_costi_personale", "ce09_ammortamenti", "ce17_rettifiche_attivita_fin",
]);

// Field categorization for double-entry counterpart filtering.
export type AcctCategory = "ATTIVO" | "PASSIVO" | "CE_POS" | "CE_NEG";
export const CE_POSITIVE_FIELDS = new Set([
  "ce01_ricavi_vendite", "ce02_variazioni_rimanenze", "ce03_lavori_interni", "ce04_altri_ricavi",
  "ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari", "ce16_utili_perdite_cambi",
  "ce17a_rivalutazioni", "ce18_proventi_straordinari",
]);
export const CE_NEGATIVE_FIELDS = new Set([
  "ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
  "ce08a_tfr_accrual", "ce08b_salari_stipendi", "ce08c_oneri_sociali", "ce08d_altri_costi_personale",
  "ce09a_ammort_immateriali", "ce09b_ammort_materiali", "ce09c_svalutazioni", "ce09d_svalutazione_crediti",
  "ce10_var_rimanenze_mat_prime", "ce11_accantonamenti", "ce11b_altri_accantonamenti", "ce12_oneri_diversi",
  "ce15_oneri_finanziari", "ce17b_svalutazioni", "ce19_oneri_straordinari", "ce20_imposte",
]);
export function fieldCategory(field: string): AcctCategory | null {
  if (/^sp(0[1-9]|10)/.test(field)) return "ATTIVO";
  if (/^sp1[1-8]/.test(field)) return "PASSIVO";
  if (CE_POSITIVE_FIELDS.has(field)) return "CE_POS";
  if (CE_NEGATIVE_FIELDS.has(field)) return "CE_NEG";
  return null;
}

// Double-entry categories allowed for a given edit direction and mode.
// "rettifica" = cross-side double-entry (BS↔CE or ATTIVO↔PASSIVO) — affects P&L.
// "riclassifica" = same-side reclassification (SP→SP or CE→CE) — no P&L impact.
export function allowedCounterpartCategories(editedField: string, _delta: number, mode: ProposalMode): Set<AcctCategory> {
  const cat = fieldCategory(editedField);
  if (mode === "riclassifica") {
    // Same-side only: ATTIVO↔ATTIVO, PASSIVO↔PASSIVO, CE↔CE (any CE sub-type)
    if (cat === "ATTIVO") return new Set<AcctCategory>(["ATTIVO"]);
    if (cat === "PASSIVO") return new Set<AcctCategory>(["PASSIVO"]);
    if (cat === "CE_POS" || cat === "CE_NEG") return new Set<AcctCategory>(["CE_POS", "CE_NEG"]);
    return new Set<AcctCategory>(["ATTIVO", "PASSIVO", "CE_POS", "CE_NEG"]);
  }
  // "rettifica" — cross-side: show every counterpart category, sign is auto-computed
  // via computeCpDelta so the user can pick freely without producing an unbalanced posting.
  if (cat === "ATTIVO") return new Set<AcctCategory>(["PASSIVO", "CE_POS", "CE_NEG"]);
  if (cat === "PASSIVO") return new Set<AcctCategory>(["ATTIVO", "CE_POS", "CE_NEG"]);
  if (cat === "CE_POS" || cat === "CE_NEG") return new Set<AcctCategory>(["ATTIVO", "PASSIVO"]);
  return new Set<AcctCategory>(["ATTIVO", "PASSIVO", "CE_POS", "CE_NEG"]);
}

// Double-entry sign rule, derived from A - L - C - R - Rev + Cost = 0.
// Same coefficient group ({ATTIVO, CE_NEG} vs {PASSIVO, CE_POS}) → opposite delta;
// cross-group → same delta. Returns the counterpart delta given an edit delta.
export function computeCpDelta(editedField: string, counterpartField: string, editDelta: number): number {
  const ec = fieldCategory(editedField);
  const cc = fieldCategory(counterpartField);
  if (!ec || !cc) return -editDelta;
  const coeff = (c: AcctCategory) => (c === "ATTIVO" || c === "CE_NEG") ? 1 : -1;
  return coeff(ec) === coeff(cc) ? -editDelta : editDelta;
}

// Gruppi del menu a tendina delle contropartite. L'ELENCO delle opzioni
// (COUNTERPART_OPTIONS) e le etichette delle voci stanno nel catalogo,
// lib/ivcee-catalog.ts: qui resta la politica (chi puo' essere contropartita di
// cosa), la' la tassonomia. Al Task 9 questo file ha perso RETTIFICHE_LABELS e
// COUNTERPART_PICKER_LABELS, che erano una seconda e una terza fonte per il
// nome di una voce; ora il nome ha una fonte sola.
export const COUNTERPART_GROUPS: Array<{ label: string; category: AcctCategory }> = [
  { label: "SP — Attivo", category: "ATTIVO" },
  { label: "SP — Passivo", category: "PASSIVO" },
  { label: "CE — Ricavi e Proventi", category: "CE_POS" },
  { label: "CE — Costi e Oneri", category: "CE_NEG" },
];

// Fields to show in the rettifiche table, organized by section
export const RETTIFICHE_BS_ATTIVO = [
  "sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
  "sp04_immob_finanziarie",
  "sp04a_partecipazioni", "sp04b_crediti_immob_breve", "sp04c_crediti_immob_lungo",
  "sp04d_altri_titoli", "sp04e_strumenti_derivati_attivi",
  "sp05_rimanenze",
  "sp05a_materie_prime", "sp05b_prodotti_in_corso", "sp05c_lavori_in_corso",
  "sp05d_prodotti_finiti", "sp05e_acconti",
  "sp06_crediti_breve",
  "sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve",
  "sp06c_crediti_collegate_breve", "sp06d_crediti_controllanti_breve",
  "sp06e_crediti_tributari_breve", "sp06f_imposte_anticipate_breve",
  "sp06g_crediti_altri_breve",
  "sp07_crediti_lungo",
  "sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo",
  "sp07c_crediti_collegate_lungo", "sp07d_crediti_controllanti_lungo",
  "sp07e_crediti_tributari_lungo", "sp07f_imposte_anticipate_lungo",
  "sp07g_crediti_altri_lungo",
  "sp08_attivita_finanziarie", "sp09_disponibilita_liquide",
  "sp10_ratei_risconti_attivi",
];
export const RETTIFICHE_BS_PN = [
  "sp11_capitale",
  "sp12a_riserva_sovrapprezzo", "sp12b_riserve_rivalutazione", "sp12c_riserva_legale",
  "sp12d_riserve_statutarie", "sp12e_altre_riserve", "sp12f_riserva_copertura_flussi",
  "sp12g_utili_perdite_portati",
  "sp13_utile_perdita",
  "sp12h_riserva_neg_azioni_proprie",
];
export const RETTIFICHE_BS_OTHER_PASSIVO = [
  "sp14_fondi_rischi", "sp15_tfr",
];
// Debt groups split by subtype so each entro/oltre pair is individually editable
export const DEBT_GROUPS: Array<{ label: string; entro: string[]; oltre: string[] }> = [
  { label: "1) Debiti verso banche", entro: ["sp16a_debiti_banche_breve"], oltre: ["sp17a_debiti_banche_lungo"] },
  { label: "2) Debiti verso altri finanziatori", entro: ["sp16b_debiti_altri_finanz_breve"], oltre: ["sp17b_debiti_altri_finanz_lungo"] },
  { label: "3) Debiti obbligazionari", entro: ["sp16c_debiti_obbligazioni_breve"], oltre: ["sp17c_debiti_obbligazioni_lungo"] },
  { label: "7) Debiti verso fornitori", entro: ["sp16d_debiti_fornitori_breve"], oltre: ["sp17d_debiti_fornitori_lungo"] },
  { label: "12) Debiti tributari", entro: ["sp16e_debiti_tributari_breve"], oltre: ["sp17e_debiti_tributari_lungo"] },
  { label: "13) Debiti previdenziali", entro: ["sp16f_debiti_previdenza_breve"], oltre: ["sp17f_debiti_previdenza_lungo"] },
  { label: "14) Altri debiti", entro: ["sp16g_altri_debiti_breve"], oltre: ["sp17g_altri_debiti_lungo"] },
];
// Main-level fields for total calculation (excludes detail sub-fields to avoid double-counting)
export const PASSIVO_TOTAL_FIELDS = [
  "sp11_capitale", "sp12_riserve", "sp13_utile_perdita",
  "sp14_fondi_rischi", "sp15_tfr",
  "sp16_debiti_breve", "sp17_debiti_lungo", "sp18_ratei_risconti_passivi",
];
// CE split by IV CEE section for proper subtotal placement
export const CE_A = [
  "ce01_ricavi_vendite", "ce02_variazioni_rimanenze", "ce03_lavori_interni",
  "ce04_altri_ricavi",
];
export const CE_B = [
  "ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
  "ce08_costi_personale",
  "ce08b_salari_stipendi", "ce08c_oneri_sociali", "ce08a_tfr_accrual", "ce08d_altri_costi_personale",
  "ce09_ammortamenti",
  "ce09a_ammort_immateriali", "ce09b_ammort_materiali",
  "ce09c_svalutazioni", "ce09d_svalutazione_crediti",
  "ce10_var_rimanenze_mat_prime", "ce11_accantonamenti", "ce11b_altri_accantonamenti",
  "ce12_oneri_diversi",
];
export const CE_C = [
  "ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari",
  "ce15_oneri_finanziari", "ce16_utili_perdite_cambi",
];
export const CE_D = [
  "ce17a_rivalutazioni", "ce17b_svalutazioni", "ce17_rettifiche_attivita_fin",
];
export const CE_E = [
  "ce18_proventi_straordinari", "ce19_oneri_straordinari",
];
export const CE_IMPOSTE = ["ce20_imposte"];

// Proposal generated for the review dialog
export type ProposalMode = "rettifica" | "riclassifica" | "correggi_import";
export interface DoubleEntryProposal {
  id: number;
  mode: ProposalMode;
  editedField: string;
  editedLabel: string;
  delta: number;
  counterpartField: string;
  counterpartLabel: string;
  proposedDelta: number;
  accepted: boolean;
  explanation: string;
  // Optional split: allows distributing the amount between two counterpart fields
  splitAlt?: {
    field: string;
    label: string;
    amount: number; // amount allocated to the alternative (rest goes to main counterpart)
  };
}

export const RETTIFICHE_MAX = 20;

