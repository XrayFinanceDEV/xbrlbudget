// Stable final-report section ids. ReportTOC and /report consume this same
// list so an Italian display-title change never breaks deep links or PDF work.
export interface ReportSection { id: string; title: string; shortTitle: string }

export const REPORT_SECTIONS: readonly ReportSection[] = [
  { id: "scope", title: "Copertina e perimetro", shortTitle: "Perimetro" },
  { id: "executive-summary", title: "Sintesi esecutiva", shortTitle: "Sintesi" },
  { id: "sources", title: "Origine e qualità dei dati", shortTitle: "Fonti" },
  { id: "adjustments", title: "Rettifiche apportate", shortTitle: "Rettifiche" },
  { id: "closing", title: "Dall'infrannuale alla chiusura", shortTitle: "Chiusura" },
  { id: "assumptions", title: "Ipotesi del budget", shortTitle: "Ipotesi" },
  { id: "income-forecast", title: "Conto economico previsionale", shortTitle: "CE" },
  { id: "balance-forecast", title: "Stato patrimoniale previsionale", shortTitle: "SP" },
  { id: "cashflow-sustainability", title: "Flussi di cassa e sostenibilità finanziaria", shortTitle: "Cassa" },
  { id: "indicators-risks", title: "Indicatori e rischi", shortTitle: "Indicatori" },
  { id: "diagnostics", title: "Diagnostica e punti da verificare", shortTitle: "Diagnostica" },
  { id: "appendices", title: "Appendici e metodologia", shortTitle: "Appendici" },
];

// Kept for the legacy analytical components still used elsewhere in the app.
export const EM_SCORE_TABLE: Array<{ min: number; rating: string }> = [
  { min: 8.15, rating: "AAA" }, { min: 7.6, rating: "AA+" }, { min: 7.3, rating: "AA" },
  { min: 7, rating: "AA-" }, { min: 6.85, rating: "A+" }, { min: 6.65, rating: "A" },
  { min: 6.4, rating: "A-" }, { min: 6.25, rating: "BBB+" }, { min: 5.85, rating: "BBB" },
  { min: 5.65, rating: "BBB-" }, { min: 5.25, rating: "BB+" }, { min: 4.95, rating: "BB" },
  { min: 4.75, rating: "BB-" }, { min: 4.5, rating: "B+" }, { min: 4.15, rating: "B" },
  { min: 3.75, rating: "B-" }, { min: 3.2, rating: "CCC+" }, { min: 2.5, rating: "CCC" },
  { min: 1.75, rating: "CCC-" }, { min: -999, rating: "D" },
];
export const EM_SCORE_DESCRIPTIONS: Record<string, string> = { AAA: "Sicurezza massima", "AA+": "Sicurezza elevata", AA: "Sicurezza elevata", "AA-": "Ampia solvibilita", "A+": "Solvibilita", A: "Solvibilita", "A-": "Solvibilita sufficiente", "BBB+": "Vulnerabilita", BBB: "Vulnerabilita", "BBB-": "Vulnerabilita elevata", "BB+": "Rischio", BB: "Rischio", "BB-": "Rischio elevato", "B+": "Rischio molto elevato", B: "Rischio molto elevato", "B-": "Rischio altissimo", "CCC+": "Rischio di insolvenza", CCC: "Insolvenza imminente", "CCC-": "Insolvenza imminente", D: "Insolvenza" };
export const IS_LABELS: Record<string, string> = { ce01_ricavi_vendite: "Ricavi delle Vendite", ce02_variazioni_rimanenze: "Variazione Rimanenze Prodotti", ce03_lavori_interni: "Lavori in Economia", ce04_altri_ricavi: "Altri Ricavi e Proventi", ce05_materie_prime: "Materie Prime e Consumo", ce06_servizi: "Servizi", ce07_godimento_beni: "Godimento Beni di Terzi", ce08_costi_personale: "Costi del Personale", ce09_ammortamenti: "Ammortamenti e Svalutazioni", ce10_var_rimanenze_mat_prime: "Variazione Rimanenze Materie", ce11_accantonamenti: "Accantonamenti per Rischi", ce12_oneri_diversi: "Oneri Diversi di Gestione", ce13_proventi_partecipazioni: "Proventi da Partecipazioni", ce14_altri_proventi_finanziari: "Altri Proventi Finanziari", ce15_oneri_finanziari: "Oneri Finanziari", ce16_utili_perdite_cambi: "Utili/Perdite su Cambi", ce17_rettifiche_attivita_fin: "Rettifiche Attivita Finanziarie", ce18_proventi_straordinari: "Proventi Straordinari", ce19_oneri_straordinari: "Oneri Straordinari", ce20_imposte: "Imposte sul Reddito" };
export function getEMScoreColor(rating: string): string {
  if (rating.startsWith("AAA") || rating.startsWith("AA")) return "text-green-600 dark:text-green-400";
  if (rating.startsWith("A") || rating.startsWith("BBB")) return "text-blue-600 dark:text-blue-400";
  if (rating.startsWith("BB")) return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}
