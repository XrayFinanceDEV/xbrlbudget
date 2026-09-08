#!/usr/bin/env node
/**
 * Prova di regressione per `print-pdf.mjs`. NON e' una suite vitest: la config
 * (`vitest.config.ts`) include solo `lib/**\/*.test.ts`, e questo file dipende
 * da Playwright, che di proposito non sta in `package.json`. Si esegue a mano:
 *
 *   node scripts/print-pdf.selftest.mjs
 *
 * Serve un display (il caso 1 apre un Chromium headed) e `pdftotext` (poppler)
 * per leggere il testo del PDF prodotto.
 *
 * Che cosa dimostra. Il server qui sotto imita la tab Stampa: la «tab attiva»
 * vive in `localStorage`, come `PraticaContext.analysisStep`, e il contenuto
 * marcato compare solo quando e' selezionata. Il caso 1 apre headed, la pagina
 * si sposta da sola sulla tab Stampa (l'utente che naviga a mano), poi Invio:
 * il PDF deve contenere il marcatore, il valore scritto in `localStorage` E
 * `HeadlessChrome` — cioe' la stampa e' avvenuta davvero in un contesto
 * headless portandosi dietro lo stato. E' il percorso che salva `--interactive`
 * su un Chromium che non implementa `Page.printToPDF` in headed.
 *
 * Il caso 1 forza `--print-mode reprint` di proposito: su un Chromium recente
 * la misura di `auto` risponde «so stampare in headed», il ripiego non
 * girerebbe mai, e proprio il percorso da verificare resterebbe senza prova.
 * Cio' che `auto` sceglie da solo lo copre il caso 2, che controlla la sola
 * cosa non ambientale: che la decisione sia annunciata PRIMA dell'Invio.
 */

import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { execFileSync } from "node:child_process";
import { mkdtempSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT = process.env.PRINT_PDF_SCRIPT ?? join(dirname(fileURLToPath(import.meta.url)), "print-pdf.mjs");
const MARKER = "MARCATORESTAMPA";
const TOKEN = "TOKENDALLOSTATOLOCALE";
const PROMPT = "premi Invio";

const PAGE = `<!doctype html>
<html lang="it"><head><meta charset="utf-8"><title>finta pratica</title></head>
<body>
<div id="root">niente</div>
<svg class="recharts-surface" width="10" height="10"></svg>
<script>
  var force = new URL(location.href).searchParams.get("forceStampa") === "1";
  function render() {
    var raw = null;
    try { raw = JSON.parse(localStorage.getItem("pratica") || "null"); } catch (e) {}
    var step = force ? "stampa" : (raw && raw.analysisStep);
    document.getElementById("root").innerHTML = step === "stampa"
      ? '<div id="stampa-content"><p>${MARKER}</p><p>' + ((raw && raw.token) || "${TOKEN}") + '</p>'
        + '<p>' + navigator.userAgent.replace(/[^A-Za-z]/g, "") + '</p></div>'
      : "<p>tab anagrafiche</p>";
  }
  render();
  // L'utente che clicca sulla tab Stampa nel browser headed.
  setTimeout(function () {
    localStorage.setItem("pratica", JSON.stringify({ analysisStep: "stampa", token: "${TOKEN}" }));
    render();
  }, 400);
</script>
</body></html>`;

const server = createServer((_req, res) => {
  res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  res.end(PAGE);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}/`;
const dir = mkdtempSync(join(tmpdir(), "print-pdf-selftest-"));

function pdfText(path) {
  if (!existsSync(path)) return null;
  return execFileSync("pdftotext", [path, "-"], { encoding: "utf8" }).replace(/\s+/g, "");
}

// Esegue lo script; se `answerPrompt` invia Invio non appena compare la domanda.
function run(args, { answerPrompt = false } = {}) {
  return new Promise((resolve) => {
    const child = spawn("node", [SCRIPT, ...args], { stdio: ["pipe", "pipe", "pipe"] });
    let outText = "";
    let answered = false;
    child.stdout.on("data", (b) => {
      outText += b;
      if (answerPrompt && !answered && outText.includes(PROMPT)) {
        answered = true;
        // Il timer della pagina scatta a 400 ms: si lascia margine.
        setTimeout(() => child.stdin.end("\n"), 1500);
      }
    });
    child.stderr.on("data", (b) => (outText += b));
    if (!answerPrompt) child.stdin.end();
    child.on("close", (code) => resolve({ code, out: outText }));
  });
}

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "OK  " : "FAIL"}  ${name}${detail ? " — " + detail : ""}`);
}

// Senza questo, un caso che muore in `stderr` si legge solo come «exit 1».
function dumpOnFailure(label, before, out) {
  if (results.slice(before).every((r) => r.ok)) return;
  console.log(`--- output di ${label} ---\n${out.trim()}\n---`);
}

// --- Caso 1: --interactive con ristampa headless (il percorso della issue #44)
{
  const out = join(dir, "reprint.pdf");
  const before = results.length;
  const r = await run(
    ["--interactive", "--print-mode", "reprint", "--url", base,
      "--wait-for", "#stampa-content", "--settle", "200", "--out", out],
    { answerPrompt: true },
  );
  const text = pdfText(out);
  check("reprint: lo script esce senza errore", r.code === 0, `exit ${r.code}`);
  check("reprint: il PDF esiste ed e' leggibile", text !== null);
  check("reprint: il PDF contiene la tab Stampa", !!text && text.includes(MARKER));
  check("reprint: lo stato di localStorage e' passato al contesto headless", !!text && text.includes(TOKEN));
  check(
    "reprint: la stampa e' avvenuta davvero in headless",
    !!text && text.includes("HeadlessChrome"),
    text && !text.includes("HeadlessChrome") ? "stampato dal browser headed" : "",
  );
  dumpOnFailure("reprint", before, r.out);
}

// --- Caso 2: --interactive con decisione ANNUNCIATA prima dell'Invio
{
  const out = join(dir, "auto.pdf");
  const before = results.length;
  const r = await run(
    ["--interactive", "--url", base, "--wait-for", "#stampa-content",
      "--settle", "200", "--out", out],
    { answerPrompt: true },
  );
  const text = pdfText(out);
  const iNotice = r.out.indexOf("[stampa]");
  const iPrompt = r.out.indexOf(PROMPT);
  check("auto: lo script esce senza errore", r.code === 0, `exit ${r.code}`);
  check("auto: il PDF contiene la tab Stampa", !!text && text.includes(MARKER));
  check(
    "auto: il modo di stampa e' annunciato PRIMA dell'Invio",
    iNotice !== -1 && iPrompt !== -1 && iNotice < iPrompt,
    `avviso@${iNotice} prompt@${iPrompt}`,
  );
  dumpOnFailure("auto", before, r.out);
}

// --- Caso 3: il modo 1 (URL diretto, headless) resta invariato
{
  const out = join(dir, "diretto.pdf");
  const before = results.length;
  const r = await run([
    "--url", `${base}?forceStampa=1`, "--wait-for", "#stampa-content",
    "--settle", "200", "--out", out,
  ]);
  const text = pdfText(out);
  check("modo 1: lo script esce senza errore", r.code === 0, `exit ${r.code}`);
  check("modo 1: il PDF contiene la tab Stampa", !!text && text.includes(MARKER));
  check("modo 1: stampato headless come sempre", !!text && text.includes("HeadlessChrome"));
  dumpOnFailure("modo 1", before, r.out);
}

server.close();
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} verifiche superate (PDF in ${dir})`);
process.exit(failed ? 1 : 0);
