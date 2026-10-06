// Porta le schermate della guida illustrata (docs/images/guida/) in
// public/guida/, dove Next le serve come /guida/<file>. Gira prima di
// `next dev` e `next build`: la fonte resta in docs/, public/guida e' generata
// (gitignorata). Nel container la cartella docs/ sta in /docs, cioe' sempre
// ../docs rispetto al frontend.
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontend = join(dirname(fileURLToPath(import.meta.url)), "..");
const origine = join(frontend, "..", "docs", "images", "guida");
const destinazione = join(frontend, "public", "guida");

if (!existsSync(origine)) {
  console.warn(`[copia-guida] ${origine} non esiste: la guida resta senza immagini.`);
  process.exit(0);
}
rmSync(destinazione, { recursive: true, force: true });
mkdirSync(destinazione, { recursive: true });
cpSync(origine, destinazione, { recursive: true });
console.log(`[copia-guida] schermate copiate in ${destinazione}`);
