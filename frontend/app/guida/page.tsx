import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Metadata } from "next";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import { hrefGuida, srcImmagineGuida } from "@/lib/guida";

export const metadata: Metadata = {
  title: "Guida illustrata - XBRL Budget",
};

// La fonte e' docs/GUIDA-ILLUSTRATA.md, letta al build: la pagina e' statica.
// Nel container la cartella docs/ sta in /docs (Dockerfile.frontend), cioe'
// sempre ../docs rispetto al frontend, come in sviluppo.
function leggiGuida(): string {
  return readFileSync(join(process.cwd(), "..", "docs", "GUIDA-ILLUSTRATA.md"), "utf-8");
}

const componenti: Components = {
  h1: ({ children, id }) => (
    <h1 id={id} className="mt-12 mb-4 scroll-mt-4 border-b border-border pb-2 text-2xl font-bold text-foreground first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children, id }) => (
    <h2 id={id} className="mt-10 mb-3 scroll-mt-4 text-xl font-semibold text-foreground">{children}</h2>
  ),
  h3: ({ children, id }) => (
    <h3 id={id} className="mt-8 mb-2 scroll-mt-4 text-lg font-semibold text-foreground">{children}</h3>
  ),
  h4: ({ children, id }) => (
    <h4 id={id} className="mt-6 mb-2 scroll-mt-4 font-semibold text-foreground">{children}</h4>
  ),
  p: ({ children }) => <p className="my-3 leading-7 text-foreground">{children}</p>,
  ul: ({ children }) => <ul className="my-3 ml-6 list-disc space-y-1.5">{children}</ul>,
  ol: ({ children }) => <ol className="my-3 ml-6 list-decimal space-y-1.5">{children}</ol>,
  li: ({ children }) => <li className="leading-7">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-4 border-l-4 border-primary/40 bg-muted/40 px-4 py-1 text-muted-foreground">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-8 border-border" />,
  a: ({ href, children }) => {
    const destinazione = hrefGuida(href);
    if (!destinazione) {
      // Rimando a una pagina tecnica del repo: non esiste nell'app.
      return <span className="font-medium" title={href}>{children}</span>;
    }
    const esterno = /^https?:\/\//.test(destinazione);
    return (
      <a
        href={destinazione}
        className="font-medium text-primary underline underline-offset-4"
        {...(esterno ? { target: "_blank", rel: "noreferrer" } : {})}
      >
        {children}
      </a>
    );
  },
  img: ({ src, alt }) => (
    // Schermate statiche servite da public/guida: next/image non aggiunge nulla.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={srcImmagineGuida(typeof src === "string" ? src : undefined)}
      alt={alt ?? ""}
      loading="lazy"
      className="my-4 w-full rounded-md border border-border shadow-sm"
    />
  ),
  table: ({ children }) => (
    <div className="my-4 overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-border bg-muted px-3 py-2 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border border-border px-3 py-2 align-top">{children}</td>,
  pre: ({ children }) => (
    <pre className="my-4 overflow-x-auto rounded-md bg-muted p-4 text-xs">{children}</pre>
  ),
  code: ({ children }) => (
    <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
  ),
};

export default function GuidaPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSlug]} components={componenti}>
        {leggiGuida()}
      </ReactMarkdown>
    </div>
  );
}
