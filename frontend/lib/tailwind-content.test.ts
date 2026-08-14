import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

/**
 * Una classe Tailwind scritta in un file che `content` non scandisce NON viene
 * generata: la regola non esiste nel CSS e l'elemento resta senza stile, in
 * silenzio. Nessun errore, nessun warning — solo un pallino trasparente.
 *
 * È successo davvero: `scoreDotColor` e `ratingColor` sono migrate in `lib/`
 * con la decomposizione di `app/pratica/page.tsx`, ma `content` elencava solo
 * `pages|components|app`. Risultato: `bg-green-500`, `bg-yellow-500` e
 * `bg-red-500` mai emesse e TUTTI i pallini del rating invisibili in
 * Indicatori e in Stampa.
 *
 * Questo test fissa l'invariante generale — ogni cartella che contiene
 * letterali di classe deve stare in `content` — non i tre nomi di classe
 * del caso specifico.
 */

const CARTELLE_SORGENTE = ["lib", "hooks", "contexts", "app", "components"];

/** Prefissi che identificano un letterale come classe di utilità Tailwind. */
const CLASSE_UTILITY =
  /\b(?:bg|text|border|ring|fill|stroke)-(?:green|red|yellow|orange|blue|slate|gray|zinc|emerald|amber)-\d{2,3}\b/;

function fileSorgente(dir: string): string[] {
  const out: string[] = [];
  const cammina = (d: string) => {
    for (const voce of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, voce.name);
      if (voce.isDirectory()) cammina(p);
      else if (/\.tsx?$/.test(voce.name) && !voce.name.includes(".test.")) out.push(p);
    }
  };
  try {
    cammina(dir);
  } catch {
    /* cartella assente: nulla da controllare */
  }
  return out;
}

function globDiContent(): string[] {
  const cfg = readFileSync("tailwind.config.ts", "utf8");
  const blocco = cfg.match(/content:\s*\[([\s\S]*?)\]/);
  if (!blocco) throw new Error("tailwind.config.ts: array `content` non trovato");
  return [...blocco[1].matchAll(/["'`]([^"'`]+)["'`]/g)].map((m) => m[1]);
}

/** La cartella di primo livello è coperta da almeno un glob di `content`? */
function coperta(cartella: string, globs: string[]): boolean {
  return globs.some((g) => g.replace(/^\.\//, "").split("/")[0] === cartella);
}

describe("tailwind content", () => {
  it("scandisce ogni cartella che contiene letterali di classe Tailwind", () => {
    const globs = globDiContent();
    const scoperte: string[] = [];

    for (const cartella of CARTELLE_SORGENTE) {
      if (coperta(cartella, globs)) continue;
      const colpevoli = fileSorgente(cartella).filter((f) =>
        CLASSE_UTILITY.test(readFileSync(f, "utf8")),
      );
      if (colpevoli.length) scoperte.push(`${cartella}/ → ${colpevoli.join(", ")}`);
    }

    expect(
      scoperte,
      "Queste cartelle contengono classi Tailwind ma non sono in `content`: " +
        "le classi non verranno generate e gli elementi resteranno senza stile.\n" +
        scoperte.join("\n"),
    ).toEqual([]);
  });

  it("copre lib/, dove vivono i colori di scoreDotColor e ratingColor", () => {
    // Fissa esplicitamente la regressione osservata: i pallini del rating
    // prendono il colore da lib/pratica-indicators.ts.
    expect(coperta("lib", globDiContent())).toBe(true);
  });
});
