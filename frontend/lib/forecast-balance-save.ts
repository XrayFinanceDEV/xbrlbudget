/**
 * L'esito di «Salva modifiche»/«Salva tutto» negli editor di cella del
 * previsionale — SP Prev. (`/forecast/balance`) e CE Prev.
 * (`/forecast/income`): che cosa succede alle modifiche in sospeso
 * (`pendingEdits`) dopo un tentativo di salvataggio, riuscito o no.
 *
 * Estratta da `handleSaveOverrides` di SP Prev. (rilievo 6, giro di
 * correzione 1): quel `catch` mostra gia' un `toast.error`, ma non toccava
 * `pendingEdits` — la cella continuava a leggere `pendingValue ?? value`
 * (`ForecastBalancePage`, componente cella editabile) e mostrava il numero
 * DIGITATO, quello che il server ha rifiutato, indistinguibile da un
 * salvataggio riuscito a parte il bordo giallo «modifica in sospeso». Viola
 * l'invariante di CLAUDE.md § Frontend — «un salvataggio che il server ha
 * rifiutato non si applica mai localmente» — anche se qui non si tratta di
 * applicare un valore backend, ma di NON disapplicare quello rifiutato.
 * `handleSaveAll` di CE Prev. (giro di correzione 2) aveva lo stesso buco,
 * un riduttore locale distinto ma strutturalmente identico
 * (`PendingEdits = Record<string, number | null>`).
 *
 * Giro di correzione 2: `PUT /assumptions/{year}` e `PATCH /ce-override`
 * ora salvano e rigenerano nella STESSA transazione lato server
 * (`assumptions_service.update_single_year_assumptions`/
 * `apply_ce_overrides`) — un override che il motore rifiuta non resta
 * piu' scritto (`db.rollback()`), quindi non c'e' piu' nulla da
 * disinquinare sul server. Questa funzione resta comunque necessaria:
 * `pendingEdits` e' stato LOCALE, e senza svuotarlo la cella continuerebbe
 * a mostrare il valore digitato anche se il server non l'ha mai applicato.
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
