// Reconcile sub-fields with imported aggregates.
// When imported aggregates don't match the sum of detail sub-fields,
// allocate the gap to the designated plug field.
export function reconcileSubfields(data: Record<string, number>) {
  const reconcile = (details: string[], parent: string, plug: string) => {
    const total = data[parent] ?? 0;
    const sum = details.reduce((s, k) => s + (data[k] ?? 0), 0);
    const gap = total - sum;
    if (Math.abs(gap) > 0.01) {
      data[plug] = (data[plug] ?? 0) + gap;
    }
  };

  // Immob. finanziarie: gap → sp04a_partecipazioni
  reconcile(
    ["sp04a_partecipazioni", "sp04b_crediti_immob_breve", "sp04c_crediti_immob_lungo", "sp04d_altri_titoli", "sp04e_strumenti_derivati_attivi"],
    "sp04_immob_finanziarie", "sp04a_partecipazioni"
  );
  // Rimanenze: gap → sp05e_acconti
  reconcile(
    ["sp05a_materie_prime", "sp05b_prodotti_in_corso", "sp05c_lavori_in_corso", "sp05d_prodotti_finiti", "sp05e_acconti"],
    "sp05_rimanenze", "sp05e_acconti"
  );
  // Riserve: gap → sp12e_altre_riserve
  reconcile(
    ["sp12a_riserva_sovrapprezzo", "sp12b_riserve_rivalutazione", "sp12c_riserva_legale",
     "sp12d_riserve_statutarie", "sp12e_altre_riserve", "sp12f_riserva_copertura_flussi",
     "sp12g_utili_perdite_portati", "sp12h_riserva_neg_azioni_proprie"],
    "sp12_riserve", "sp12e_altre_riserve"
  );
  // Crediti breve: gap → sp06g_crediti_altri_breve
  reconcile(
    ["sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve", "sp06c_crediti_collegate_breve",
     "sp06d_crediti_controllanti_breve", "sp06e_crediti_tributari_breve", "sp06f_imposte_anticipate_breve", "sp06g_crediti_altri_breve"],
    "sp06_crediti_breve", "sp06g_crediti_altri_breve"
  );
  // Crediti lungo: gap → sp07g_crediti_altri_lungo
  reconcile(
    ["sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo", "sp07c_crediti_collegate_lungo",
     "sp07d_crediti_controllanti_lungo", "sp07e_crediti_tributari_lungo", "sp07f_imposte_anticipate_lungo", "sp07g_crediti_altri_lungo"],
    "sp07_crediti_lungo", "sp07g_crediti_altri_lungo"
  );
  // Personale: gap → ce08b_salari_stipendi (main account)
  reconcile(
    ["ce08b_salari_stipendi", "ce08c_oneri_sociali", "ce08a_tfr_accrual", "ce08d_altri_costi_personale"],
    "ce08_costi_personale", "ce08b_salari_stipendi"
  );
  // Ammortamenti: gap → ce09c_svalutazioni
  reconcile(
    ["ce09a_ammort_immateriali", "ce09b_ammort_materiali", "ce09c_svalutazioni", "ce09d_svalutazione_crediti"],
    "ce09_ammortamenti", "ce09c_svalutazioni"
  );
  // Debiti breve: gap → sp16g_altri_debiti_breve
  reconcile(
    ["sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve", "sp16c_debiti_obbligazioni_breve",
     "sp16d_debiti_fornitori_breve", "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve", "sp16g_altri_debiti_breve"],
    "sp16_debiti_breve", "sp16g_altri_debiti_breve"
  );
  // Debiti lungo: gap → sp17g_altri_debiti_lungo
  reconcile(
    ["sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo", "sp17c_debiti_obbligazioni_lungo",
     "sp17d_debiti_fornitori_lungo", "sp17e_debiti_tributari_lungo", "sp17f_debiti_previdenza_lungo", "sp17g_altri_debiti_lungo"],
    "sp17_debiti_lungo", "sp17g_altri_debiti_lungo"
  );

  // Attivo vs Passivo: small import-rounding imbalance (≤ 5 €) → plug into sp09 (cash).
  // Rettifiche are double-entry so balance is preserved after this one-shot adjustment.
  const attivoKeys = ["sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
    "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve", "sp07_crediti_lungo",
    "sp08_attivita_finanziarie", "sp09_disponibilita_liquide", "sp10_ratei_risconti_attivi"];
  const passivoKeys = ["sp11_capitale", "sp12_riserve", "sp13_utile_perdita",
    "sp14_fondi_rischi", "sp15_tfr", "sp16_debiti_breve", "sp17_debiti_lungo", "sp18_ratei_risconti_passivi"];
  const attivo = attivoKeys.reduce((s, k) => s + (data[k] ?? 0), 0);
  const passivo = passivoKeys.reduce((s, k) => s + (data[k] ?? 0), 0);
  const bsGap = attivo - passivo;
  if (Math.abs(bsGap) > 0.01 && Math.abs(bsGap) <= 5) {
    data["sp09_disponibilita_liquide"] = (data["sp09_disponibilita_liquide"] ?? 0) - bsGap;
  }
}

