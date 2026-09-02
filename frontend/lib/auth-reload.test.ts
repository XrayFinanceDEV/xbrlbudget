import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { companiesLoadKey, type StatoAuth } from "@/lib/auth-reload";

/**
 * Il token può arrivare DOPO che `isLoading` di `AuthContext` è già sceso: quel
 * flag scende a tempo (5 s in iframe, 1 s fuori), non alla ricezione del token.
 * Quando succede, il primo caricamento parte senza `Authorization`, prende 401 e
 * scrive «Impossibile caricare le aziende»; se l'effetto guarda solo
 * `authLoading` — che non si muove più — l'arrivo del token non lo fa ripartire
 * e l'iframe resta sull'errore per sempre, senza una via d'uscita che non sia un
 * ricaricamento manuale della pagina (dentro un iframe, non ovvio da fare).
 *
 * `companiesLoadKey` è la chiave PRIMITIVA su cui dipende l'effetto di
 * AppContext: cambia a ogni transizione che rende sensato ritentare, e non
 * cambia mai per conto proprio. Primitiva perché un oggetto letterale in un
 * array di dipendenze cambia identità a ogni render e l'effetto si ri-innesca
 * da solo (invariante «Frontend» di CLAUDE.md).
 *
 * Il conteggio qui sotto riproduce la semantica di React per una dipendenza
 * primitiva: l'effetto gira al primo render e a ogni render in cui la
 * dipendenza è cambiata.
 */

const IN_CARICAMENTO: StatoAuth = { authLoading: true, isAuthenticated: false };
const RISOLTO_CON_TOKEN: StatoAuth = { authLoading: false, isAuthenticated: true };
const RISOLTO_SENZA_TOKEN: StatoAuth = { authLoading: false, isAuthenticated: false };

/** Quante volte l'effetto arriva a chiamare `loadCompanies()` sulla sequenza. */
function caricamenti(sequenza: StatoAuth[]): number {
  let precedente: string | null | undefined = undefined;
  let chiamate = 0;
  for (const stato of sequenza) {
    const chiave = companiesLoadKey(stato.authLoading, stato.isAuthenticated);
    const primoRender = precedente === undefined;
    if (primoRender || chiave !== precedente) {
      // corpo dell'effetto
      if (chiave !== null) chiamate++;
    }
    precedente = chiave;
  }
  return chiamate;
}

describe("companiesLoadKey", () => {
  it("non fa caricare nulla finché l'autenticazione non è risolta", () => {
    expect(companiesLoadKey(true, false)).toBeNull();
    expect(companiesLoadKey(true, true)).toBeNull();
    expect(caricamenti([IN_CARICAMENTO, IN_CARICAMENTO])).toBe(0);
  });

  it("caso normale (token prima del timeout): una sola chiamata, non due", () => {
    // AUTH_TOKEN aggiorna token e isLoading nello stesso handler: React li
    // raggruppa in un unico render.
    expect(caricamenti([IN_CARICAMENTO, RISOLTO_CON_TOKEN])).toBe(1);
  });

  it("token dopo il timeout: l'arrivo del token fa ripartire il caricamento", () => {
    expect(
      caricamenti([IN_CARICAMENTO, RISOLTO_SENZA_TOKEN, RISOLTO_CON_TOKEN])
    ).toBe(2);
  });

  it("AUTH_LOGOUT seguito da un nuovo AUTH_TOKEN ricarica anch'esso", () => {
    const sequenza = [
      IN_CARICAMENTO,
      RISOLTO_CON_TOKEN,
      RISOLTO_SENZA_TOKEN, // AUTH_LOGOUT: azzera il token senza rialzare isLoading
      RISOLTO_CON_TOKEN, // nuovo AUTH_TOKEN
    ];
    expect(caricamenti(sequenza)).toBe(3);
    // e l'ultima transizione è davvero un caricamento in più rispetto al
    // troncamento prima del nuovo token
    expect(caricamenti(sequenza.slice(0, 3))).toBe(2);
  });

  it("fuori dall'iframe, senza token, si carica lo stesso (fallback DEV_USER_ID)", () => {
    expect(caricamenti([IN_CARICAMENTO, RISOLTO_SENZA_TOKEN])).toBe(1);
  });

  it("non si ri-innesca da solo: render ripetuti sullo stesso stato non ricaricano", () => {
    expect(
      caricamenti([
        IN_CARICAMENTO,
        RISOLTO_CON_TOKEN,
        RISOLTO_CON_TOKEN,
        RISOLTO_CON_TOKEN,
      ])
    ).toBe(1);
  });

  it("la chiave è un primitivo: uguaglianza per valore, non per identità", () => {
    expect(companiesLoadKey(false, true)).toBe(companiesLoadKey(false, true));
    expect(typeof companiesLoadKey(false, true)).toBe("string");
    expect(companiesLoadKey(false, true)).not.toBe(companiesLoadKey(false, false));
  });
});

describe("AppContext usa davvero la chiave", () => {
  const sorgente = readFileSync(
    join(__dirname, "..", "contexts", "AppContext.tsx"),
    "utf8"
  );

  it("importa companiesLoadKey", () => {
    expect(sorgente).toMatch(/companiesLoadKey/);
    expect(sorgente).toMatch(/from "@\/lib\/auth-reload"/);
  });

  it("l'effetto che carica l'elenco dipende dalla chiave, non dal solo authLoading", () => {
    const effetto = sorgente.match(
      /useEffect\(\(\) => \{[^]*?loadCompanies\(\);[^]*?\}, \[([^\]]*)\]\);/
    );
    expect(effetto, "effetto di caricamento aziende non trovato").not.toBeNull();
    const dipendenze = effetto![1];
    // `authKey` copre sia authLoading sia isAuthenticated: senza, un token che
    // arriva dopo il timeout non fa ripartire nulla.
    expect(dipendenze).toMatch(/\bauthKey\b/);
  });
});
