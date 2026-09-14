import * as React from "react";
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

/** Testo nudo: React Escape gli apostrofi (`&#x27;`) e le virgolette, e i
 *  tag si portano via le classi. Si confronta ciò che l'occhio legge. */
const plain = (html: string): string =>
  html
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/<[^>]*>/g, " ");

import { PROVENANCE_ORDER, ProvenanceBadge, ProvenanceLegend, provenanceView } from "./ProvenanceBadge";

/**
 * Il badge d'origine. §6.4 elenca sei provenienze, §8 vieta il significato
 * affidato al solo colore: qui ogni origine deve avere una parola, e la sua
 * spiegazione deve restare leggibile anche a schermo senza accessi o stampata in
 * bianco e nero.
 */
describe("le sei origini del contratto v1", () => {
  it("sono sei, e nessuna resta senza parola", () => {
    expect(PROVENANCE_ORDER).toEqual(["user", "automatic", "default", "override", "ignored", "legacy_unknown"]);
    for (const provenance of PROVENANCE_ORDER) {
      const view = provenanceView(provenance);
      expect(view.label.trim().length).toBeGreaterThan(0);
      expect(view.description.trim().length).toBeGreaterThan(0);
      expect(view.known).toBe(true);
    }
  });

  it("le sei parole sono sei parole diverse", () => {
    const labels = PROVENANCE_ORDER.map((provenance) => provenanceView(provenance).label);
    expect(new Set(labels).size).toBe(6);
  });

  it("`legacy_unknown` non si traveste da `default`", () => {
    expect(provenanceView("legacy_unknown").label).not.toBe(provenanceView("default").label);
    expect(provenanceView("legacy_unknown").description).toContain("tracciamento");
  });

  it("`ignored` si vede anche senza colore", () => {
    expect(provenanceView("ignored").label).toBe("Ignorato");
    expect(provenanceView("ignored").description).toContain("non usato");
  });
});

describe("ProvenanceBadge", () => {
  it("un'icona e una parola, non solo il colore", () => {
    for (const provenance of PROVENANCE_ORDER) {
      const html = renderToStaticMarkup(<ProvenanceBadge provenance={provenance} />);
      expect(html).toContain("<svg");
      expect(plain(html)).toContain(provenanceView(provenance).label);
      // La spiegazione è nel testo (a schermo e per gli screen reader), non in
      // un `title` che all'export PDF non arriva.
      expect(plain(html)).toContain(provenanceView(provenance).description);
    }
  });

  it("una riga non attiva lo dice a parole", () => {
    const html = renderToStaticMarkup(<ProvenanceBadge provenance="user" active={false} />);
    expect(html).toContain("non attivo nel percorso corrente");
  });

  it("un'origine che non è delle sei non ricade su «default»", () => {
    const view = provenanceView("pilotato_da_altrove");
    expect(view.known).toBe(false);
    expect(view.label).toBe("Origine non dichiarata");
    expect(view.description).toContain("pilotato_da_altrove");

    const html = renderToStaticMarkup(<ProvenanceBadge provenance={"pilotato_da_altrove" as never} />);
    expect(plain(html)).toContain("Origine non dichiarata");
    expect(html).not.toContain(">Default<");
  });
});

describe("ProvenanceLegend", () => {
  it("sei voci, tutte e sei le parole", () => {
    const html = renderToStaticMarkup(<ProvenanceLegend />);
    expect(html).toContain('aria-label="Legenda delle origini delle ipotesi"');
    for (const provenance of PROVENANCE_ORDER) {
      expect(plain(html)).toContain(provenanceView(provenance).label);
      expect(plain(html)).toContain(provenanceView(provenance).description);
    }
    expect((html.match(/<li/g) ?? []).length).toBe(6);
  });
});
