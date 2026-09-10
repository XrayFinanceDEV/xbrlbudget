/**
 * L'esito di «Salva modifiche» in SP Prev. (`/forecast/balance`): che cosa
 * succede alle modifiche in sospeso (`pendingEdits`) dopo un tentativo di
 * salvataggio, riuscito o no.
 *
 * Estratta da `handleSaveOverrides` (rilievo 6, giro di correzione 1): quel
 * `catch` mostra gia' un `toast.error`, ma non tocca `pendingEdits` — la
 * cella continua a leggere `pendingValue ?? value` (`ForecastBalancePage`,
 * componente cella editabile) e mostra il numero DIGITATO, quello che il
 * server ha rifiutato, indistinguibile da un salvataggio riuscito a parte il
 * bordo giallo «modifica in sospeso». Viola l'invariante di CLAUDE.md §
 * Frontend — «un salvataggio che il server ha rifiutato non si applica mai
 * localmente» — anche se qui non si tratta di applicare un valore backend,
 * ma di NON disapplicare quello rifiutato.
 *
 * `PUT /assumptions/{year}` (`updateBudgetAssumptions`, chiamata per ogni
 * anno prima di `generateForecast`) scrive `sp_overrides` senza rigenerare:
 * un fallimento successivo di `POST /generate` lascia quell'override
 * persistito ma INUTILIZZATO — il previsionale mostrato resta quello di
 * prima, il vero valore del server. Tenere `pendingEdits` con l'importo
 * rifiutato dopo un fallimento fa mentire la cella su quale valore vince.
 *
 * Modulo puro: nessun import da `app/` o da `components/`.
 */
export type PendingSpEdits = Record<string, number | null>;

export type SaveAttemptOutcome = "success" | "error";

/**
 * Le modifiche in sospeso dopo un tentativo di salvataggio.
 *
 * Successo: il previsionale appena rigenerato riflette gli override
 * scritti — la cella li rilegge dal server, non serve piu' tenerli in
 * sospeso. Fallimento: la generazione non e' avvenuta, e la cella deve
 * tornare al valore vero del server — non continuare a mostrare quello
 * rifiutato come se fosse stato applicato.
 *
 * Nei DUE casi il risultato e' lo stesso — nessuna modifica in sospeso — ma
 * per una ragione opposta, e va detta: qui non si "dimentica" un dettaglio,
 * si decide che un rifiuto non lascia tracce locali del valore rifiutato.
 */
export function pendingEditsAfterSave(
  _pending: PendingSpEdits,
  _outcome: SaveAttemptOutcome,
): PendingSpEdits {
  return {};
}
