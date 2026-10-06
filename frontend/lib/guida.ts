/**
 * La guida illustrata dentro l'app (`/guida`). La fonte resta una sola,
 * `docs/GUIDA-ILLUSTRATA.md` con le schermate in `docs/images/guida/`: la
 * pagina la legge al build, e `scripts/copia-guida.mjs` (predev/prebuild)
 * porta le immagini in `public/guida/`. Qui solo la traduzione dei
 * riferimenti del markdown in indirizzi dell'app — modulo puro, testato in node.
 */

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
