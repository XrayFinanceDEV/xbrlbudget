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
  ...[
    ["Banche", "a"], ["Altri finanziatori", "b"], ["Obbligazioni", "c"],
    ["Fornitori", "d"], ["Debiti tributari", "e"], ["Debiti previdenziali", "f"], ["Altri debiti", "g"],
  ].flatMap(([label, suffix]) => [
    { label, computed: (b: BalanceValues) => sum(b, [`sp16${suffix}_debiti_${suffix === "a" ? "banche" : suffix === "b" ? "altri_finanz" : suffix === "c" ? "obbligazioni" : suffix === "d" ? "fornitori" : suffix === "e" ? "tributari" : suffix === "f" ? "previdenza" : "altri"}_breve`, `sp17${suffix}_debiti_${suffix === "a" ? "banche" : suffix === "b" ? "altri_finanz" : suffix === "c" ? "obbligazioni" : suffix === "d" ? "fornitori" : suffix === "e" ? "tributari" : suffix === "f" ? "previdenza" : "altri"}_lungo`]), indent: true },
    { label: "  entro 12 mesi", field: BALANCE_HIERARCHY_GROUPS[6].details.find(([field]) => field.startsWith(`sp16${suffix}`))?.[0], indent: true },
    { label: "  oltre 12 mesi", field: BALANCE_HIERARCHY_GROUPS[7].details.find(([field]) => field.startsWith(`sp17${suffix}`))?.[0], indent: true },
  ]),
  { label: "Totale debiti", computed: debtTotal, isSubtotal: true },
  { label: "E) Ratei e risconti passivi", field: "sp18_ratei_risconti_passivi" },
  { label: "TOTALE PASSIVO E PATRIMONIO NETTO", computed: liabilityTotal, isTotal: true },
  { label: "DIFFERENZA (Attivo - Passivo)", computed: (b) => n(b, "total_assets") - liabilityTotal(b), isSubtotal: true },
];

export const balanceRowValue = (balance: BalanceValues, row: BalanceStatementRow): number => {
  if (row.computed) return row.computed(balance);
  return row.field ? n(balance, row.field) : 0;
};
