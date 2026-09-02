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
 * Il modo 2 e la stampa headed: `page.pdf()` esiste solo dove Chromium
 * implementa `Page.printToPDF`. Non e' piu' vero che serva per forza headless —
 * misurato il 2026-09-02 su Playwright 1.62.1 / Chromium 151.0.7922.34, dove
 * `page.pdf()` riesce anche con `headless: false` — ma sui Chromium piu' vecchi
 * non c'e', e li' il modo 2 moriva sull'ultima riga, DOPO che l'utente aveva
 * gia' navigato a mano e premuto Invio. Percio' la capacita' non si assume: si
 * misura appena aperto il browser, prima di chiedere l'Invio, e quando manca si
 * ristampa la stessa pagina in un contesto headless riusando `storageState()` —
 * che e' esattamente dove la tab Stampa tiene il suo stato (`PraticaContext`
 * persiste `analysisStep` in `localStorage`).
 *
 * Attenzione al modo `reprint`: passano cookie e `localStorage`, NON lo stato
 * tenuto in memoria. Il JWT dell'iframe vive solo nello state di React, quindi
 * la ristampa vuole il backend in modo dev (`DEV_USER_ID`).
 *
 * Opzioni:
 *   --url <u>        pagina di partenza (obbligatoria)
 *   --out <path>     file PDF da scrivere (default: ./print.pdf)
 *   --wait-for <sel> selettore da attendere prima di stampare
 *   --interactive    apre il browser e aspetta Invio prima di stampare
 *   --settle <ms>    attesa extra per far disegnare i grafici (default 2500)
 *   --print-mode <m> auto (default) | direct | reprint — vedi sopra. Fuori da
 *                    `--interactive` si stampa sempre `direct`: il browser e'
 *                    gia' headless e non c'e' niente da ristampare.
 *
 * La prova di regressione di questo script e' `print-pdf.selftest.mjs`, accanto
 * a lui: non e' in vitest (dipende da Playwright) e si esegue a mano.
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
const printMode = arg("print-mode", "auto");

if (!url || url === true) {
  console.error("manca --url. Vedi l'intestazione di questo file.");
  process.exit(2);
}

if (!["auto", "direct", "reprint"].includes(printMode)) {
  console.error(`--print-mode sconosciuto: ${printMode}. Ammessi: auto, direct, reprint.`);
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

const VIEWPORT = { width: 1440, height: 1000 };

const PDF_OPTIONS = {
  format: "A4",
  printBackground: true,
  // I margini veri stanno in `@page` dentro `app/globals.css`: qui si lascia
  // fare a lui, altrimenti si sommano e l'impaginazione misurata non e' quella
  // che esce dalla stampante.
  preferCSSPageSize: true,
};

// Gli errori della pagina sono la causa piu' comune di un PDF vuoto: si vedono.
function watchPageErrors(page) {
  page.on("console", (m) => {
    if (m.type() === "error") console.error("[console]", m.text());
  });
  page.on("pageerror", (e) => console.error("[pageerror]", e.message));
}

// Il browser sa stampare in questo modo? Si misura su una pagina vuota, subito,
// invece di scoprirlo alla fine su quella vera.
// Contesto usa-e-getta: `browser.newPage()` ne apre uno implicito che rifiuta
// una seconda pagina, e la pagina vera non va toccata.
async function canPrint(browser) {
  const context = await browser.newContext();
  try {
    const scratch = await context.newPage();
    await scratch.setContent("<!doctype html><title>probe</title>");
    await scratch.pdf({ format: "A4" });
    return true;
  } catch {
    return false;
  } finally {
    await context.close();
  }
}

// Attese e stampa: identiche su entrambi i percorsi, cosi' il PDF del modo 2
// non e' misurato diversamente da quello del modo 1.
async function capture(page) {
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

  return page.pdf(PDF_OPTIONS);
}

let browser = await chromium.launch({ headless: !interactive });
let page = await browser.newPage({ viewport: VIEWPORT });
watchPageErrors(page);

await page.goto(url, { waitUntil: "networkidle" });

// Fuori da --interactive il browser e' gia' headless: `direct` e' l'unico modo
// sensato, e il modo 1 resta quello di sempre.
let mode = interactive ? printMode : "direct";

if (interactive && mode === "auto") {
  mode = (await canPrint(browser)) ? "direct" : "reprint";
  console.log(
    mode === "direct"
      ? "[stampa] questo Chromium stampa anche in headed: si stampa la pagina che vedi."
      : "[stampa] questo Chromium non stampa in headed: dopo l'Invio la pagina verra'\n" +
          "          ristampata in un contesto headless riusando cookie e localStorage.\n" +
          "          Lo stato tenuto solo in memoria (il JWT dell'iframe) non passa:\n" +
          "          serve il backend in modo dev (DEV_USER_ID).",
  );
}

if (interactive) {
  const rl = createInterface({ input: stdin, output: stdout });
  await rl.question(
    "Porta il browser sulla pagina da stampare (es. tab Stampa), poi premi Invio... ",
  );
  rl.close();
}

let pdf;

if (mode === "reprint") {
  // Si porta di la' lo stato che la pagina ha davvero persistito, e l'URL su cui
  // l'utente e' finito: per la tab Stampa sono `localStorage` (PraticaContext) e
  // /pratica, quindi il contesto headless riapre la stessa tab.
  const storageState = await page.context().storageState();
  const finalUrl = page.url();
  await browser.close();

  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: VIEWPORT, storageState });
  page = await context.newPage();
  watchPageErrors(page);
  await page.goto(finalUrl, { waitUntil: "networkidle" });
  pdf = await capture(page);
} else {
  pdf = await capture(page);
}

writeFileSync(out, pdf);
console.log(`PDF scritto in ${out} (${(pdf.length / 1024).toFixed(0)} KB, modo ${mode})`);

await browser.close();
