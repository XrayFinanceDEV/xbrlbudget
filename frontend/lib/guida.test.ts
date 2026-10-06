import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import { describe, it, expect } from "vitest";
import { hrefGuida, indiceGuida, srcImmagineGuida } from "./guida";

describe("guida in app", () => {
  it("le schermate passano da docs/images/guida a /guida", () => {
    expect(srcImmagineGuida("images/guida/01-home.jpg")).toBe("/guida/01-home.jpg");
    expect(srcImmagineGuida("https://example.com/x.png")).toBe("https://example.com/x.png");
    expect(srcImmagineGuida(undefined)).toBeUndefined();
  });

  it("restano link solo le ancore e gli indirizzi web", () => {
    expect(hrefGuida("#3-rettifiche")).toBe("#3-rettifiche");
    expect(hrefGuida("https://formulafinance.it")).toBe("https://formulafinance.it");
    expect(hrefGuida("budget/FORECASTING_GUIDE.md")).toBeNull();
    expect(hrefGuida("frontend/RETTIFICHE.md#2")).toBeNull();
    expect(hrefGuida(undefined)).toBeNull();
  });

  it("l'indice laterale usa gli stessi id della pagina resa", () => {
    const md = readFileSync(join(__dirname, "..", "..", "docs", "GUIDA-ILLUSTRATA.md"), "utf-8");
    const html = renderToStaticMarkup(
      createElement(ReactMarkdown, { remarkPlugins: [remarkGfm], rehypePlugins: [rehypeSlug] }, md),
    );
    const voci = indiceGuida(md);
    expect(voci.length).toBeGreaterThan(10);
    expect(voci[0].testo).toMatch(/^0\. La home/);
    expect(voci.some((v) => v.testo === "Indice")).toBe(false);
    for (const v of voci) expect(html).toContain(`id="${v.id}"`);
  });

  it("i duplicati prendono il suffisso contando anche i ### e il titolo resta fuori", () => {
    const voci = indiceGuida("# Guida\n\n## Indice\n\n# A\n\n### Note\n\n## Note\n");
    expect(voci).toEqual([
      { id: "a", testo: "A", livello: 1 },
      { id: "note-1", testo: "Note", livello: 2 },
    ]);
  });
});
