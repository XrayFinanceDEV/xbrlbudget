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
