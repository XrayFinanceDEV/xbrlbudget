// Report section definitions and Italian labels

export interface ReportSection {
  id: string;
  title: string;
  shortTitle: string;
}

export const REPORT_SECTIONS: ReportSection[] = [
  { id: "cover", title: "Dati Aziendali", shortTitle: "Copertina" },
  { id: "dashboard", title: "Dashboard Sintetica", shortTitle: "Dashboard" },
  { id: "composition", title: "Composizione Patrimoniale", shortTitle: "Composizione" },
  { id: "income-margins", title: "Conto Economico e Margini", shortTitle: "Margini" },
  { id: "structural", title: "Analisi Strutturale", shortTitle: "Struttura" },
  { id: "ratios", title: "Indici Finanziari", shortTitle: "Indici" },
  { id: "scoring", title: "Scoring e Rating", shortTitle: "Scoring" },
  { id: "break-even", title: "Break Even Point", shortTitle: "BEP" },
  { id: "cashflow", title: "Rendiconto Finanziario", shortTitle: "Cashflow" },
  { id: "appendices", title: "Appendici - Dati Completi", shortTitle: "Appendici" },
  { id: "notes", title: "Note Metodologiche", shortTitle: "Note" },
];

// EM-Score lookup table (mirrored from pdf_service/em_score.py)
export const EM_SCORE_TABLE: Array<{ min: number; rating: string }> = [
  { min: 8.15, rating: "AAA" },
  { min: 7.60, rating: "AA+" },
  { min: 7.30, rating: "AA" },
  { min: 7.00, rating: "AA-" },
  { min: 6.85, rating: "A+" },
  { min: 6.65, rating: "A" },
  { min: 6.40, rating: "A-" },
  { min: 6.25, rating: "BBB+" },
  { min: 5.85, rating: "BBB" },
  { min: 5.65, rating: "BBB-" },
  { min: 5.25, rating: "BB+" },
  { min: 4.95, rating: "BB" },
  { min: 4.75, rating: "BB-" },
  { min: 4.50, rating: "B+" },
  { min: 4.15, rating: "B" },
  { min: 3.75, rating: "B-" },
  { min: 3.20, rating: "CCC+" },
  { min: 2.50, rating: "CCC" },
  { min: 1.75, rating: "CCC-" },
  { min: -999, rating: "D" },
];

export const EM_SCORE_DESCRIPTIONS: Record<string, string> = {
  "AAA": "Sicurezza massima",
  "AA+": "Sicurezza elevata",
  "AA": "Sicurezza elevata",
  "AA-": "Ampia solvibilita",
  "A+": "Solvibilita",
  "A": "Solvibilita",
  "A-": "Solvibilita sufficiente",
  "BBB+": "Vulnerabilita",
  "BBB": "Vulnerabilita",
  "BBB-": "Vulnerabilita elevata",
  "BB+": "Rischio",
  "BB": "Rischio",
  "BB-": "Rischio elevato",
  "B+": "Rischio molto elevato",
  "B": "Rischio molto elevato",
  "B-": "Rischio altissimo",
  "CCC+": "Rischio di insolvenza",
  "CCC": "Insolvenza imminente",
  "CCC-": "Insolvenza imminente",
  "D": "Insolvenza",
};

// Italian labels for balance sheet items
export const BS_LABELS: Record<string, string> = {
  sp01_crediti_soci: "Crediti verso Soci",
  sp02_immob_immateriali: "Immobilizzazioni Immateriali",
  sp03_immob_materiali: "Immobilizzazioni Materiali",
  sp04_immob_finanziarie: "Immobilizzazioni Finanziarie",
  sp05_rimanenze: "Rimanenze",
  sp06_crediti_breve: "Crediti (entro 12 mesi)",
  sp07_crediti_lungo: "Crediti (oltre 12 mesi)",
  sp08_attivita_finanziarie: "Attivita Finanziarie",
  sp09_disponibilita_liquide: "Disponibilita Liquide",
  sp10_ratei_risconti_attivi: "Ratei e Risconti Attivi",
  sp11_capitale: "Capitale Sociale",
  sp12_riserve: "Riserve",
  sp13_utile_perdita: "Utile (Perdita) d'Esercizio",
  sp14_fondi_rischi: "Fondi per Rischi e Oneri",
  sp15_tfr: "TFR",
  sp16_debiti_breve: "Debiti (entro 12 mesi)",
  sp17_debiti_lungo: "Debiti (oltre 12 mesi)",
  sp18_ratei_risconti_passivi: "Ratei e Risconti Passivi",
};

// Italian labels for income statement items
export const IS_LABELS: Record<string, string> = {
  ce01_ricavi_vendite: "Ricavi delle Vendite",
  ce02_variazioni_rimanenze: "Variazione Rimanenze Prodotti",
  ce03_lavori_interni: "Lavori in Economia",
  ce04_altri_ricavi: "Altri Ricavi e Proventi",
  ce05_materie_prime: "Materie Prime e Consumo",
  ce06_servizi: "Servizi",
  ce07_godimento_beni: "Godimento Beni di Terzi",
  ce08_costi_personale: "Costi del Personale",
  ce09_ammortamenti: "Ammortamenti e Svalutazioni",
  ce10_var_rimanenze_mat_prime: "Variazione Rimanenze Materie",
  ce11_accantonamenti: "Accantonamenti per Rischi",
  ce12_oneri_diversi: "Oneri Diversi di Gestione",
  ce13_proventi_partecipazioni: "Proventi da Partecipazioni",
  ce14_altri_proventi_finanziari: "Altri Proventi Finanziari",
  ce15_oneri_finanziari: "Oneri Finanziari",
  ce16_utili_perdite_cambi: "Utili/Perdite su Cambi",
  ce17_rettifiche_attivita_fin: "Rettifiche Attivita Finanziarie",
  ce18_proventi_straordinari: "Proventi Straordinari",
  ce19_oneri_straordinari: "Oneri Straordinari",
  ce20_imposte: "Imposte sul Reddito",
};

export function getEMScoreColor(rating: string): string {
  if (rating.startsWith("AAA") || rating.startsWith("AA")) return "text-green-600 dark:text-green-400";
  if (rating.startsWith("A") || rating.startsWith("BBB")) return "text-blue-600 dark:text-blue-400";
  if (rating.startsWith("BB")) return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

// Unified blue/gray chart palette for the report
// Primary series use saturated blues; secondary/negative use grays
export const CHART_COLORS = [
  "var(--chart-1)", // bright blue
  "var(--chart-2)", // mid blue
  "var(--chart-3)", // light blue
  "var(--chart-4)", // slate blue
  "var(--chart-5)", // gray blue
];

// Semantic colors used in waterfall / bar charts for positive vs negative
export const CHART_POSITIVE = "var(--chart-1)";  // blue
export const CHART_NEGATIVE = "var(--chart-4)";  // dark slate
export const CHART_NEUTRAL = "var(--chart-5)";   // gray
export const CHART_ACCENT = "var(--chart-2)";    // mid blue
export const CHART_MUTED = "var(--chart-5)";     // muted gray-blue

// Gauge zones: use blue gradient instead of red/yellow/green
export const GAUGE_ZONES_BAD_GOOD = [
  { color: "hsl(var(--chart-4))" },   // dark slate (bad)
  { color: "hsl(var(--chart-5))" },   // gray-blue  (neutral)
  { color: "hsl(var(--chart-1))" },   // bright blue (good)
];

// Reference line colors (muted, not traffic-light)
export const REF_LINE_UPPER = "var(--chart-1)";   // blue threshold
export const REF_LINE_LOWER = "var(--chart-4)";   // dark slate threshold
