/**
 * Quando ha senso (ri)caricare l'elenco aziende, ridotto a una chiave
 * PRIMITIVA da mettere nell'array di dipendenze dell'effetto.
 *
 * `AuthContext` fa scendere `isLoading` **a tempo** (5 s dentro l'iframe, 1 s
 * fuori), non alla ricezione del token: il token del parent Formula Finance
 * può quindi arrivare quando `authLoading` è già `false` e non si muoverà più.
 * Un effetto che dipende dal solo `authLoading` non riparte, il primo
 * caricamento è già fallito con 401, e l'iframe resta su «Impossibile caricare
 * le aziende» finché qualcuno non ricarica la pagina a mano.
 *
 * La chiave copre entrambe le informazioni:
 * - `null` finché l'autenticazione non è risolta → non si carica nulla;
 * - `"anon"` risolta senza token — è il caso legittimo fuori dall'iframe, dove
 *   il backend usa il fallback `DEV_USER_ID`, e il caso del timeout scaduto;
 * - `"auth"` risolta con un token.
 *
 * Un valore primitivo, non un oggetto: un letterale in un array di dipendenze
 * cambia identità a ogni render e fa ri-innescare l'effetto da solo (invariante
 * «Frontend» di CLAUDE.md). E la chiave non dipende da nulla che l'effetto
 * scriva, quindi non può oscillare.
 */

export type StatoAuth = {
  authLoading: boolean;
  isAuthenticated: boolean;
};

export function companiesLoadKey(
  authLoading: boolean,
  isAuthenticated: boolean
): string | null {
  if (authLoading) return null;
  return isAuthenticated ? "auth" : "anon";
}
