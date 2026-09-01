/**
 * Stato patrimoniale proiettato della tab Proiezione («Calcola proiezione SP»).
 *
 * Gemello lato client di `ForecastEngine._normalize_balance_sheet_cents`, che
 * l'`IntraYearEngine` applica alla propria proiezione
 * (`calculations/intra_year_engine.py:576`): **prima si arrotondano le righe,
 * poi si ricalcola la cassa sugli aggregati arrotondati**. Il plug è per
 * costruzione il residuo dei valori che l'utente legge, quindi Totale Attivo e
 * Totale Passivo coincidono al centesimo — anzi, qui all'euro, perché
 * l'anteprima si rende con `formatEuro` a zero decimali.
 *
 * L'ordine inverso — plug in piena precisione e diciotto arrotondamenti
 * indipendenti dopo — faceva divergere i due totali fino a 1 €: l'anteprima
 * raccontava un bilancio diverso da quello persistito.
 *
 * Modulo puro: nessun import da `app/` o `components/`, così resta provabile in
 * `environment: node`.
 */

import { scaledOrCarried } from "@/lib/pratica-turnover";
import { ATTIVO_CODES, PASSIVO_CODES } from "@/lib/pratica-codes";

/** Le voci dell'attivo diverse dalla cassa: il plug è il loro complemento. */
export const ASSET_CODES_WITHOUT_CASH = ATTIVO_CODES.filter(
  (code) => code !== "sp09_disponibilita_liquide",
);

export interface ProjectedBsInputs {
  /** Valori del periodo infrannuale, per codice SP aggregato. */
  partial: Record<string, number>;
  /** Valori dell'anno di riferimento, per codice SP aggregato. */
  reference: Record<string, number>;
  /** Falso quando manca l'anno di riferimento: niente rapporti di rotazione. */
  hasReference: boolean;
  /** CE dell'anno di riferimento: base dei rapporti di rotazione. */
  refRevenue: number;
  refMaterials: number;
  refServices: number;
  /** CE proiettato: scala il circolante. */
  projRevenue: number;
  projMaterials: number;
  projServices: number;
  /** Utile/perdita proiettato — finisce tale e quale in `sp13`. */
  projNetProfit: number;
}

export interface ProjectedBs {
  /** I 18 codici aggregati, già arrotondati all'euro. */
  values: Record<string, number>;
  totalAssets: number;
  totalLiabilities: number;
  /**
   * Quanto è stato assorbito nei debiti a breve perché il plug era negativo
   * (0 quando la cassa copre). È un fabbisogno non finanziato, non un mutuo:
   * l'`IntraYearEngine` in quel caso non crea debito e alza la diagnostica
   * `unfunded_financing_requirement`.
   */
  absorbedIntoShortTermDebt: number;
}

const val = (source: Record<string, number>, code: string): number => {
  const raw = source[code];
  return Number.isFinite(raw) ? (raw as number) : 0;
};

/** Scala di arrotondamento dell'anteprima: l'euro, come `formatEuro`. */
const roundRow = (value: number): number =>
  Number.isFinite(value) ? Math.round(value) : 0;

const sumCodes = (values: Record<string, number>, codes: readonly string[]): number =>
  codes.reduce((acc, code) => acc + val(values, code), 0);

/**
 * Costruisce lo stato patrimoniale proiettato dai valori infrannuali, dai
 * rapporti di rotazione dell'anno di riferimento e dal CE proiettato.
 *
 * L'ordine delle operazioni è la sostanza di questa funzione: arrotonda ogni
 * riga, POI ricava la cassa. Invertirlo rimette in circolo lo sbilancio da
 * arrotondamento.
 */
export function computeProjectedBS(inputs: ProjectedBsInputs): ProjectedBs {
  const {
    partial,
    reference,
    hasReference,
    refRevenue,
    refMaterials,
    refServices,
    projRevenue,
    projMaterials,
    projServices,
    projNetProfit,
  } = inputs;

  const partialVal = (code: string) => val(partial, code);
  const refVal = (code: string) => val(reference, code);

  const projPurchases = projMaterials + projServices;
  const refPurchases = refMaterials + refServices;

  // Circolante: giacenza scalata col rapporto di rotazione dell'anno di
  // riferimento, oppure — rapporto degenere o riferimento assente — la giacenza
  // infrannuale osservata. Stessa regola di `_turnover_ratio` nel motore.
  const sp05 =
    hasReference && projMaterials !== 0
      ? scaledOrCarried(
          refVal("sp05_rimanenze"),
          refMaterials,
          projMaterials,
          partialVal("sp05_rimanenze"),
        )
      : partialVal("sp05_rimanenze");
  const sp06 =
    hasReference && projRevenue !== 0
      ? scaledOrCarried(
          refVal("sp06_crediti_breve"),
          refRevenue,
          projRevenue,
          partialVal("sp06_crediti_breve"),
        )
      : partialVal("sp06_crediti_breve");
  const sp16 =
    hasReference && projPurchases !== 0
      ? scaledOrCarried(
          refVal("sp16_debiti_breve"),
          refPurchases,
          projPurchases,
          partialVal("sp16_debiti_breve"),
        )
      : partialVal("sp16_debiti_breve");

  // PASSO 1 — le righe, arrotondate. `sp09` non c'è: è il residuo di queste.
  const values: Record<string, number> = {
    sp01_crediti_soci: roundRow(partialVal("sp01_crediti_soci")),
    sp02_immob_immateriali: roundRow(partialVal("sp02_immob_immateriali")),
    sp03_immob_materiali: roundRow(partialVal("sp03_immob_materiali")),
    sp04_immob_finanziarie: roundRow(partialVal("sp04_immob_finanziarie")),
    sp05_rimanenze: roundRow(sp05),
    sp06_crediti_breve: roundRow(sp06),
    sp07_crediti_lungo: roundRow(partialVal("sp07_crediti_lungo")),
    sp08_attivita_finanziarie: roundRow(partialVal("sp08_attivita_finanziarie")),
    sp10_ratei_risconti_attivi: roundRow(partialVal("sp10_ratei_risconti_attivi")),
    sp11_capitale: roundRow(partialVal("sp11_capitale")),
    sp12_riserve: roundRow(partialVal("sp12_riserve")),
    sp13_utile_perdita: roundRow(projNetProfit),
    sp14_fondi_rischi: roundRow(partialVal("sp14_fondi_rischi")),
    sp15_tfr: roundRow(partialVal("sp15_tfr")),
    sp16_debiti_breve: roundRow(sp16),
    sp17_debiti_lungo: roundRow(partialVal("sp17_debiti_lungo")),
    sp18_ratei_risconti_passivi: roundRow(partialVal("sp18_ratei_risconti_passivi")),
  };

  // PASSO 2 — il plug di cassa, residuo degli aggregati ARROTONDATI.
  const assetsWithoutCash = sumCodes(values, ASSET_CODES_WITHOUT_CASH);
  let cash = sumCodes(values, PASSIVO_CODES) - assetsWithoutCash;

  // PASSO 3 — plug negativo: l'anteprima lo assorbe nei debiti a breve. Somma
  // di interi, quindi la quadratura del passo 2 sopravvive.
  let absorbedIntoShortTermDebt = 0;
  if (cash < 0) {
    absorbedIntoShortTermDebt = -cash;
    values.sp16_debiti_breve += absorbedIntoShortTermDebt;
    cash = 0;
  }
  values.sp09_disponibilita_liquide = cash;

  return {
    values,
    totalAssets: sumCodes(values, ATTIVO_CODES),
    totalLiabilities: sumCodes(values, PASSIVO_CODES),
    absorbedIntoShortTermDebt,
  };
}
