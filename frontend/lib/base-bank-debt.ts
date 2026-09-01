/**
 * Il debito bancario dell'anno base, **come lo calcola il motore**.
 *
 * Replica esatta di `calculations/projection_common.py:base_bank_debt`. La
 * scelta fra «esporlo dall'API» e «replicarne la formula» è caduta sulla
 * seconda perché questo lotto è dichiaratamente di solo frontend — nessuna
 * modifica a DB, motori o endpoint — e la spec ammette entrambe purché la
 * formula sia replicata **esattamente** e la scelta sia dichiarata.
 *
 * Il prezzo della scelta: se la formula Python cambia, questa resta indietro
 * in silenzio. `lib/base-bank-debt.test.ts` fissa i casi che contano, ma non
 * può accorgersi di una modifica fatta di là — chi tocca `base_bank_debt`
 * deve toccare anche questo file.
 *
 * **Perché non basta `sp16a + sp17a`.** Il motore assegna alle banche anche
 * gli scarti POSITIVI fra l'aggregato e la somma dei suoi dettagli, su
 * entrambe le scadenze: è la convenzione usata in tutta l'app, e su un
 * bilancio abbreviato (dettagli a zero, tutto nell'aggregato) i due numeri
 * differiscono di tutto il debito. Ricalcolarlo con la formula «ovvia»
 * mostrerebbe come coperto un piano che il server poi rifiuta.
 */

const BANK_FIELDS = ["sp16a_debiti_banche_breve", "sp17a_debiti_banche_lungo"] as const;

const NON_BANK_SHORT_FIELDS = [
  "sp16b_debiti_altri_finanz_breve",
  "sp16c_debiti_obbligazioni_breve",
  "sp16d_debiti_fornitori_breve",
  "sp16e_debiti_tributari_breve",
  "sp16f_debiti_previdenza_breve",
  "sp16g_altri_debiti_breve",
] as const;

const NON_BANK_LONG_FIELDS = [
  "sp17b_debiti_altri_finanz_lungo",
  "sp17c_debiti_obbligazioni_lungo",
  "sp17d_debiti_fornitori_lungo",
  "sp17e_debiti_tributari_lungo",
  "sp17f_debiti_previdenza_lungo",
  "sp17g_altri_debiti_lungo",
] as const;

/** Le colonne monetarie arrivano dall'API come stringhe. */
type FonteBilancio = Record<string, unknown> | null | undefined;

function v(bs: FonteBilancio, field: string): number {
  const raw = bs?.[field];
  const n = typeof raw === "number" ? raw : Number(raw ?? 0);
  return Number.isFinite(n) ? n : 0;
}

export function baseBankDebt(bs: FonteBilancio): number {
  const somma = (campi: readonly string[]) =>
    campi.reduce((acc, f) => acc + v(bs, f), 0);

  const explicitBanks = somma(BANK_FIELDS);
  const shortGap =
    v(bs, "sp16_debiti_breve") -
    (v(bs, "sp16a_debiti_banche_breve") + somma(NON_BANK_SHORT_FIELDS));
  const longGap =
    v(bs, "sp17_debiti_lungo") -
    (v(bs, "sp17a_debiti_banche_lungo") + somma(NON_BANK_LONG_FIELDS));

  // `max(0, gap)`: uno scarto NEGATIVO (dettagli che superano l'aggregato) non
  // toglie debito alle banche — è un difetto di import, non un credito.
  const totale = explicitBanks + Math.max(0, shortGap) + Math.max(0, longGap);

  // Arrotondamento al centesimo: il motore lavora in `Decimal`, qui si somma
  // in virgola mobile. Su importi con decimali le due strade divergono di
  // ~1e-10 (misurato: 1.000.500,00 contro 1.000.499,9999999999) — irrilevante
  // contro la tolleranza di un centesimo, ma è un numero che va mostrato
  // all'utente come «lo stesso» del motore, e non ha senso portarsi dietro
  // una coda che non esiste di là.
  return Math.round(totale * 100) / 100;
}

/**
 * La somma dei residui iniziali dichiarati sul PRIMO anno di piano: è la sola
 * annata in cui il motore li ammette.
 */
export function sommaResiduiIniziali(
  loans: ReadonlyArray<{ opening_residual?: number | null }> | undefined,
): number {
  return (loans ?? []).reduce((acc, l) => acc + (Number(l.opening_residual) || 0), 0);
}

/**
 * Il vincolo è tutto-o-niente e **al centesimo**: se almeno un residuo è
 * valorizzato, il motore sostituisce il piano forfettario con lo scadenzario
 * dettagliato e pretende che la somma pareggi il debito bancario dell'anno
 * base, altrimenti solleva
 * «The sum of financing opening residuals must equal base-year bank debt».
 *
 * Tolleranza di 1 centesimo perché i residui si scrivono in euro e il
 * confronto lato server è su `Decimal`.
 */
export function statoResidui(
  bs: FonteBilancio,
  loans: ReadonlyArray<{ opening_residual?: number | null }> | undefined,
): {
  debitoBancario: number;
  sommaResidui: number;
  differenza: number;
  /** Almeno un residuo valorizzato: da qui in poi il vincolo è attivo. */
  attivo: boolean;
  /** Il previsionale verrà rifiutato se generato così com'è. */
  bloccante: boolean;
} {
  const debitoBancario = baseBankDebt(bs);
  const sommaResidui = sommaResiduiIniziali(loans);
  const differenza = debitoBancario - sommaResidui;
  const attivo = sommaResidui > 0;
  return {
    debitoBancario,
    sommaResidui,
    differenza,
    attivo,
    bloccante: attivo && Math.abs(differenza) > 0.01,
  };
}
