/**
 * La migrazione in memoria di uno scenario salvato PRIMA del giro di rilievi del 14/09
 * (spec 2026-09-15 §4.8, decisione 1). Modulo puro: nessun import da `app/` o `components/`.
 *
 * Ricalcola cio' che si puo' (parte variabile sui ricavi, «rimborso in N anni» in contratti per
 * anno, finanziamento legacy in contratto nuovo) e DICHIARA cio' che serve dall'utente. La mappa
 * restituita e' sporca: l'anteprima gira su quella, e si persiste al primo salvataggio.
 */
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { withOtherLenders } from "@/lib/budget-horizon";
import type { WizardStepKey } from "@/lib/budget-wizard-steps";
import { baseBankDebt } from "@/lib/base-bank-debt";
import { num } from "@/lib/budget-format";
// La costante vive in `budget-inflazione.ts` (Task 10): un solo valore, non
// due definizioni che potrebbero divergere (dispatch del Task 10).
import { INFLAZIONE_PREDEFINITA } from "@/lib/budget-inflazione";
import type { FinancingLoanInput, OtherLenderInput } from "@/types/api";

export { INFLAZIONE_PREDEFINITA };

export interface EsitoMigrazione {
  map: AssumptionsMap;
  ricalcolato: string[];
  daIntegrare: { step: WizardStepKey; testo: string }[];
}

export function isScenarioPrecedente(map: AssumptionsMap, forecastYears: number[]): boolean {
  const first = forecastYears[0];
  if (first === undefined || !map[first]) return false;
  return map[first].inflation_pct === null || map[first].inflation_pct === undefined;
}

/** Rate uguali su `n` anni, troncate all'orizzonte: oltre l'orizzonte il residuo resta aperto. */
export function rateUguali(totale: number, anni: number, orizzonte: number): number[] {
  if (totale <= 0 || anni <= 0) return Array.from({ length: orizzonte }, () => 0);
  const rata = Math.round((totale / anni) * 100) / 100;
  return Array.from({ length: orizzonte }, (_, i) => (i < anni ? rata : 0));
}

export function migraScenario(
  map: AssumptionsMap, forecastYears: number[], baseBs: Record<string, unknown> | null | undefined, baseYear: number,
): EsitoMigrazione {
  const first = forecastYears[0];
  const out: AssumptionsMap = {};
  const ricalcolato: string[] = [];
  const daIntegrare: EsitoMigrazione["daIntegrare"] = [];
  let variabiliCambiate = false;
  let finanziamentiConvertiti = 0;

  for (const y of forecastYears) {
    const r = { ...map[y] };
    const rev = num(r.revenue_growth_pct ?? 0);
    if (num(r.variable_materials_growth_pct ?? 0) !== rev || num(r.variable_services_growth_pct ?? 0) !== rev) variabiliCambiate = true;
    r.variable_materials_growth_pct = rev;
    r.variable_services_growth_pct = rev;
    r.fixed_materials_growth_auto = false;
    r.fixed_services_growth_auto = false;
    r.inflation_pct = INFLAZIONE_PREDEFINITA;
    r.tfr_payments = r.tfr_payments ?? 0;
    const amt = num(r.financing_amount ?? 0), dur = num(r.financing_duration_years ?? 0);
    if (amt > 0 && dur > 0) {
      const nuovo: FinancingLoanInput = {
        name: `Nuovo finanziamento ${y}`, amount: amt, opening_residual: 0, duration_years: dur,
        interest_rate: num(r.financing_interest_rate ?? 0), grace_years: 0, balloon_pct: 0,
      };
      r.financing_loans = [...(r.financing_loans ?? []), nuovo];
      r.financing_amount = 0;
      finanziamentiConvertiti += 1;
    }
    out[y] = r;
  }
  // Testo riformulato rispetto al piano: «Parte variabile...» (maiuscola)
  // non conteneva la sottostringa minuscola «parte variabile» che il test
  // cerca — scarto di formato, dichiarato nel rapporto del Task 9.
  if (variabiliCambiate) ricalcolato.push("Le vecchie percentuali della parte variabile (materie prime e servizi) sono sostituite dalla crescita dei ricavi.");
  ricalcolato.push("Parte fissa: le vecchie percentuali restano, perché sono già un'ipotesi scritta dall'utente.");
  if (finanziamentiConvertiti > 0) ricalcolato.push(`Nuovo finanziamento: ${finanziamentiConvertiti === 1 ? "la riga legacy è diventata un contratto con nome" : `le ${finanziamentiConvertiti} righe legacy sono diventate contratti con nome`}.`);
  ricalcolato.push("Ricavi, personale, godimento e oneri diversi: tenuti come erano salvati.");

  if (first !== undefined && out[first]) {
    const p = out[first];
    const debito = baseBankDebt(baseBs);
    const breve = num(baseBs?.sp16a_debiti_banche_breve);
    const anniBanca = num(p.existing_debt_repayment_years ?? 0);
    const haContratti = (p.financing_loans ?? []).some((l) => num(l.opening_residual) > 0);
    p.bank_lines_amount = 0;
    p.bank_lines_rule = "costante";
    p.bank_lines_rate = num(p.financing_interest_rate ?? 0) || null;
    if (debito > 0 && !haContratti) {
      const contratto: FinancingLoanInput = {
        name: anniBanca > 0 ? `Debiti verso banche · da «rimborso in ${anniBanca} anni»` : "Debiti verso banche",
        amount: 0, opening_residual: debito, interest_rate: num(p.financing_interest_rate ?? 0),
        grace_years: 0, balloon_pct: 0, duration_years: null,
        repayments: rateUguali(debito, anniBanca, forecastYears.length),
      };
      p.financing_loans = [contratto, ...(p.financing_loans ?? [])];
      ricalcolato.push(anniBanca > 0
        ? `«Rimborso in ${anniBanca} anni» delle banche: convertito in un finanziamento, con rimborsi uguali per anno.`
        : "Debiti verso banche: un solo finanziamento senza rimborsi nel piano, da scadenziare.");
      daIntegrare.push({ step: "patrimoniale-pregresso", testo: `Debiti verso banche: dividi i ${breve.toLocaleString("it-IT")} € a breve fra fidi e anticipi (si rinnovano) e quota dei mutui; il resto è un solo finanziamento da ${debito.toLocaleString("it-IT")} €, da spacchettare nei contratti veri o confermare.` });
    }
    p.existing_debt_repayment_years = null;
    const altri = num(baseBs?.sp16b_debiti_altri_finanz_breve) + num(baseBs?.sp17b_debiti_altri_finanz_lungo);
    const anniAltri = num(p.altri_finanz_repayment_years ?? 0);
    if (altri > 0) {
      const voce: OtherLenderInput = {
        name: anniAltri > 0 ? `Altri finanziatori · da «rimborso in ${anniAltri} anni»` : "Altri finanziatori",
        opening_residual: altri, interest_rate: 0, repayments: rateUguali(altri, anniAltri, forecastYears.length),
      };
      Object.assign(out, withOtherLenders(out, forecastYears, [voce]));
      if (anniAltri > 0) ricalcolato.push(`«Rimborso in ${anniAltri} anni» degli altri finanziatori: convertito in un finanziatore con rimborsi uguali per anno.`);
    }
    out[first].altri_finanz_repayment_years = null;
    daIntegrare.unshift({ step: "scenario", testo: "Inflazione attesa: il vecchio scenario non la salvava; è impostata al 2%." });
    if (!p.pregresso) daIntegrare.push({ step: "patrimoniale-pregresso", testo: "Voci oltre 12 mesi: il vecchio scenario non le scadenziava. Verifica se tributari rateizzati, altri debiti e crediti hanno movimenti nel piano, o restano aperti." });
  }
  ricalcolato.push(`Il previsionale cambierà al prossimo salvataggio: CE Prev. e SP Prev. mostrano ancora quello calcolato sul bilancio ${baseYear}.`);
  return { map: out, ricalcolato, daIntegrare };
}
