/**
 * La guida illustrata dentro l'app (`/guida`). La fonte resta una sola,
 * `docs/GUIDA-ILLUSTRATA.md` con le schermate in `docs/images/guida/`: la
 * pagina la legge al build, e `scripts/copia-guida.mjs` (predev/prebuild)
 * porta le immagini in `public/guida/`. Qui la traduzione dei riferimenti del
 * markdown in indirizzi dell'app e l'indice laterale — modulo puro, testato in node.
 */

import GithubSlugger from "github-slugger";
import type { Heading } from "mdast";
import { fromMarkdown } from "mdast-util-from-markdown";
import { toString } from "mdast-util-to-string";
import { visit } from "unist-util-visit";

/** Prefisso delle schermate nel markdown, relativo a `docs/`. */
const PREFISSO_IMMAGINI = "images/guida/";

/** `images/guida/01-home.jpg` → `/guida/01-home.jpg`; ogni altro src resta com'è. */
export function srcImmagineGuida(src: string | undefined): string | undefined {
  if (!src) return src;
  return src.startsWith(PREFISSO_IMMAGINI) ? `/guida/${src.slice(PREFISSO_IMMAGINI.length)}` : src;
}

/**
 * Dove porta un link della guida dentro l'app: un'àncora resta un'àncora, un
 * indirizzo web resta tale. I rimandi alle pagine tecniche (`budget/…md`)
 * non esistono nell'app — sono documentazione del repo — quindi `null`: la
 * pagina li rende come testo, non come link rotti.
 */
export function hrefGuida(href: string | undefined): string | null {
  if (!href) return null;
  if (href.startsWith("#") || /^https?:\/\//.test(href) || href.startsWith("mailto:")) return href;
  return null;
}

export interface VoceIndiceGuida {
  id: string;
  testo: string;
  livello: 1 | 2;
}

/**
 * L'indice laterale della guida: i titoli `#` e `##`, con gli stessi id che
 * `rehype-slug` mette sulla pagina — uno slugger solo, che conta TUTTI i
 * titoli in ordine (anche `###`), così i duplicati prendono lo stesso
 * suffisso `-1`. Il titolo della guida e la sezione «Indice» restano fuori:
 * il primo è già in testa alla pagina, la seconda è l'indice stesso.
 */
export function indiceGuida(markdown: string): VoceIndiceGuida[] {
  const slugger = new GithubSlugger();
  const voci: VoceIndiceGuida[] = [];
  visit(fromMarkdown(markdown), "heading", (nodo: Heading) => {
    const testo = toString(nodo).trim();
    const id = slugger.slug(testo);
    if (nodo.depth <= 2) voci.push({ id, testo, livello: nodo.depth as 1 | 2 });
  });
  return voci.slice(1).filter((v) => v.testo !== "Indice");
}

// --- Ritorno dalla guida --------------------------------------------------------
// La guida nasconde nav e stepper, e dentro l'iframe non c'è il «indietro» del
// browser: senza un link esplicito l'utente resta chiuso nella guida. Il bottone
// «Guida» porta con sé la pagina di partenza (`?da=`); la barra della guida la offre
// come ritorno, accanto alla home.

/** Il link al bottone «Guida» da `pathname`, che diventa il ritorno. */
export function hrefVersoGuida(pathname: string): string {
  if (!pathname || pathname.startsWith("/guida")) return "/guida";
  return `/guida?da=${encodeURIComponent(pathname)}`;
}

/** La pagina a cui tornare: solo un percorso interno dell'app, mai la guida stessa
 *  né un indirizzo esterno (`//host`, `https:`); altrimenti la home. */
export function ritornoDallaGuida(da: string | null | undefined): string {
  if (!da || !da.startsWith("/") || da.startsWith("//") || da.startsWith("/\\")) return "/";
  if (da.startsWith("/guida")) return "/";
  return da;
}

const ETICHETTE_RITORNO: Array<[string, string]> = [
  ["/pratica", "Torna alla pratica"],
  ["/budget", "Torna agli scenari"],
  ["/forecast/income", "Torna al CE previsionale"],
  ["/forecast/balance", "Torna allo SP previsionale"],
  ["/forecast/reclassified", "Torna al riclassificato"],
  ["/cashflow", "Torna al rendiconto"],
  ["/report", "Torna al report"],
  ["/import", "Torna all'import"],
];

/** L'etichetta del link di ritorno; `null` quando il ritorno è la home (c'è già il
 *  link «Aziende & Pratiche»). */
export function etichettaRitornoGuida(ritorno: string): string | null {
  if (ritorno === "/") return null;
  const trovata = ETICHETTE_RITORNO.find(([prefisso]) => ritorno === prefisso || ritorno.startsWith(prefisso + "/"));
  return trovata ? trovata[1] : "Torna indietro";
}
