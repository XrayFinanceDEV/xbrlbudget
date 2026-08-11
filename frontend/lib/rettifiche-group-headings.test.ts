import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { labelOf } from "@/lib/ivcee-catalog";
import {
  CE_A, CE_B, CE_C, CE_D, CE_E, CE_IMPOSTE,
  DEBT_GROUPS,
  RETTIFICHE_BS_ATTIVO, RETTIFICHE_BS_OTHER_PASSIVO, RETTIFICHE_BS_PN,
} from "@/lib/pratica-rettifiche-rules";

/**
 * Con la grafia autonoma del catalogo la scheda Rettifiche mostra numeri
 * romani che RICOMINCIANO dentro ogni lettera dello schema art. 2424:
 * "I - Immobilizzazioni immateriali" e "I - Rimanenze" convivono nella stessa
 * colonna. Il numero significa qualcosa solo sotto la riga che apre la sua
 * lettera. Questo test sorveglia proprio quell'invariante:
 *
 *   ogni voce resa da Rettifiche la cui etichetta autonoma inizia con un
 *   numero romano cade dentro un raggruppamento dichiarato dalla vista.
 *
 * Le intestazioni sono righe di RESA e stanno nel componente (non nel
 * catalogo, non negli elenchi RETTIFICHE_BS_*), e l'armatura dei test qui
 * — vitest.config.ts: `include: ["lib/**\/*.test.ts"]`, `environment: "node"` —
 * non monta React. Quindi la tabella dei raggruppamenti si rilegge dal
 * SORGENTE del componente. È il punto debole del test: se un domani quella
 * costante cambia forma la regex non la trova più. Per questo il caso
 * "il componente dichiara dei raggruppamenti" fallisce esplicitamente su zero
 * risultati, invece di lasciare che l'assenza di dati faccia passare tutto.
 */
const SORGENTE = fileURLToPath(
  new URL("../components/pratica/RettificheTab.tsx", import.meta.url),
);
const src = readFileSync(SORGENTE, "utf-8");

const spans = [
  ...src.matchAll(/\{ heading: "([^"]+)", from: "([^"]+)"(?:, until: "([^"]+)")? \}/g),
].map((m) => ({ heading: m[1], from: m[2], until: m[3] as string | undefined }));

/** Gli elenchi passati a renderSection, uno per chiamata e nell'ordine di resa. */
const SEZIONI: string[][] = [
  RETTIFICHE_BS_ATTIVO,
  RETTIFICHE_BS_PN,
  RETTIFICHE_BS_OTHER_PASSIVO,
  ["sp18_ratei_risconti_passivi"],
  CE_A, CE_B, CE_C, CE_D, CE_E, CE_IMPOSTE,
];
/** Le sotto-righe dei debiti, rese fuori da renderSection (blocco "D) Debiti"). */
const DEBITI = DEBT_GROUPS.flatMap((g) => [...g.entro, ...g.oltre]);

/** Stessa regola del componente: `until` è ESCLUSIVO. */
const coperti = (fields: string[]): Set<string> => {
  const out = new Set<string>();
  let span: (typeof spans)[number] | null = null;
  for (const field of fields) {
    const starts = spans.find((g) => g.from === field);
    if (starts) span = starts;
    else if (span && span.until === field) span = null;
    if (span) out.add(field);
  }
  return out;
};

const NUMERO_ROMANO = /^(I|II|III|IV|V|VI|VII|VIII|IX|X)\s*[-–)]/;
const conNumeroRomano = (codes: string[]) => codes.filter((c) => NUMERO_ROMANO.test(labelOf(c)));

describe("Rettifiche: i numeri romani hanno un'intestazione che li ancora", () => {
  it("il componente dichiara dei raggruppamenti (guardia anti-vuoto)", () => {
    expect(spans.length).toBeGreaterThan(0);
  });

  it("ogni raggruppamento cita codici che la vista rende davvero", () => {
    const resi = new Set([...SEZIONI.flat(), ...DEBITI]);
    const ignoti = spans
      .flatMap((g) => [g.from, g.until])
      .filter((c): c is string => c !== undefined && !resi.has(c));
    expect(ignoti).toEqual([]);
  });

  it("esistono voci con numero romano (guardia anti-vuoto)", () => {
    expect(conNumeroRomano(SEZIONI.flat()).length).toBeGreaterThan(0);
  });

  it("nessuna voce con numero romano resta senza intestazione", () => {
    const scoperte: string[] = [];
    for (const fields of SEZIONI) {
      const dentro = coperti(fields);
      for (const code of conNumeroRomano(fields)) {
        if (!dentro.has(code)) scoperte.push(code);
      }
    }
    expect(scoperte).toEqual([]);
  });

  it("le sotto-righe dei debiti non portano numeri romani (niente da ancorare)", () => {
    expect(conNumeroRomano(DEBITI)).toEqual([]);
  });

  it("una voce che apre già la propria lettera non finisce dentro un gruppo", () => {
    // sp01 (A), sp10 (D) e sp18 (E) sono di livello-lettera: rientrarle sotto
    // B)/C) le farebbe leggere come sotto-voci di un aggregato che non le contiene.
    const dentroAttivo = coperti(RETTIFICHE_BS_ATTIVO);
    expect(dentroAttivo.has("sp01_crediti_soci")).toBe(false);
    expect(dentroAttivo.has("sp10_ratei_risconti_attivi")).toBe(false);
    expect(coperti(["sp18_ratei_risconti_passivi"]).size).toBe(0);
  });
});
