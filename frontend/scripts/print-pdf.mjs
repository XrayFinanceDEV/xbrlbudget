#!/usr/bin/env node
/**
 * Genera il PDF di una pagina dell'app, per verificare l'IMPAGINAZIONE di
 * stampa.
 *
 * Perche' esiste: `emulateMedia({ media: "print" })` da' le misure giuste ma
 * NON impagina — non mostra mai un'interruzione di pagina sbagliata. L'unico
 * modo di sapere se un grafico si spezza, o se la tabella degli indicatori
 * finisce da sola su una pagina, e' produrre il PDF e guardarlo.
 *
 * Playwright NON e' una dipendenza di questo progetto, di proposito: serve solo
 * qui, e trascinarla in `package.json` metterebbe un browser da centinaia di MB
 * nel lockfile di tutti. Si installa al bisogno:
 *
 *   npm i -D playwright && npx playwright install chromium
 *
 * Uso (con backend + frontend gia' avviati, vedi CLAUDE.md «Run (dev)»):
 *
 *   # 1. la pagina e' gia' raggiungibile per URL
 *   node scripts/print-pdf.mjs --url http://localhost:3000/report --out /tmp/report.pdf
 *
 *   # 2. la pagina dipende da stato locale (pratica selezionata, tab Stampa):
 *   #    si apre un browser vero, ci si arriva a mano, poi Invio in terminale
 *   node scripts/print-pdf.mjs --interactive --url http://localhost:3000/pratica \
 *     --wait-for "#stampa-content" --out /tmp/stampa.pdf
 *
 * Opzioni:
 *   --url <u>        pagina di partenza (obbligatoria)
 *   --out <path>     file PDF da scrivere (default: ./print.pdf)
 *   --wait-for <sel> selettore da attendere prima di stampare
 *   --interactive    apre il browser e aspetta Invio prima di stampare
 *   --settle <ms>    attesa extra per far disegnare i grafici (default 2500)
 */

import { writeFileSync } from "node:fs";
import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";

function arg(name, fallback = undefined) {
  const i = process.argv.indexOf(`--${name}`);
  if (i === -1) return fallback;
  const next = process.argv[i + 1];
  return next && !next.startsWith("--") ? next : true;
}

const url = arg("url");
const out = arg("out", "print.pdf");
const waitFor = arg("wait-for");
const interactive = arg("interactive", false) === true;
const settle = Number(arg("settle", 2500));

if (!url || url === true) {
  console.error("manca --url. Vedi l'intestazione di questo file.");
  process.exit(2);
}

let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  console.error(
    "playwright non e' installato.\n" +
      "  npm i -D playwright && npx playwright install chromium",
  );
  process.exit(3);
}

const browser = await chromium.launch({ headless: !interactive });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

// Gli errori della pagina sono la causa piu' comune di un PDF vuoto: si vedono.
page.on("console", (m) => {
  if (m.type() === "error") console.error("[console]", m.text());
});
page.on("pageerror", (e) => console.error("[pageerror]", e.message));

await page.goto(url, { waitUntil: "networkidle" });

if (interactive) {
  const rl = createInterface({ input: stdin, output: stdout });
  await rl.question(
    "Porta il browser sulla pagina da stampare (es. tab Stampa), poi premi Invio... ",
  );
  rl.close();
}

if (typeof waitFor === "string") {
  await page.waitForSelector(waitFor, { timeout: 60_000 });
}

// Recharts disegna dopo il layout, con un'animazione: senza questa attesa il
// PDF esce con i riquadri vuoti.
await page.waitForTimeout(settle);
await page
  .waitForFunction(() => document.querySelectorAll(".recharts-surface").length > 0, {
    timeout: 10_000,
  })
  .catch(() => console.warn("[avviso] nessun grafico trovato nella pagina"));

const pdf = await page.pdf({
  format: "A4",
  printBackground: true,
  // I margini veri stanno in `@page` dentro `app/globals.css`: qui si lascia
  // fare a lui, altrimenti si sommano e l'impaginazione misurata non e' quella
  // che esce dalla stampante.
  preferCSSPageSize: true,
});

writeFileSync(out, pdf);
console.log(`PDF scritto in ${out} (${(pdf.length / 1024).toFixed(0)} KB)`);

await browser.close();
