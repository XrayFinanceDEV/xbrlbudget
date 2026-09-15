import * as React from "react";
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ReadinessBanner, readinessReasons, readinessView } from "./ReadinessBanner";
import type { Diagnostic, Readiness } from "@/types/final-report";

const REASON: Diagnostic = {
  code: "forecast_stale",
  severity: "error",
  section: "forecast",
  message: "Forecast precedente alle ipotesi salvate.",
};

function banner(readiness: Readiness): string {
  return renderToStaticMarkup(<ReadinessBanner readiness={readiness} />);
}

/**
 * §8: `ready`, `draft`, `blocked` con una lista di motivi (codice, severità,
 * sezione, messaggio). Il colore non basta: icona, etichetta e spiegazione
 * devono esserci sempre, e «motivi non dichiarati» non è «nessun motivo».
 */
describe("i tre stati", () => {
  it("hanno ciascuno una parola e una frase", () => {
    expect(readinessView("ready")).toMatchObject({ label: "Pronto", role: "status" });
    expect(readinessView("draft").label).toBe("Bozza");
    expect(readinessView("blocked")).toMatchObject({ label: "Bloccato", role: "alert" });
    for (const status of ["ready", "draft", "blocked"]) {
      const view = readinessView(status);
      expect(view.title.length).toBeGreaterThan(0);
      expect(view.description.length).toBeGreaterThan(10);
    }
  });

  it("uno stato che non è dei tre non ricade su «pronto»", () => {
    const view = readinessView("finalizzato");
    expect(view.label).toBe("Stato non riconosciuto");
    expect(view.description).toContain("finalizzato");
    expect(view.role).toBe("alert");
    const html = banner({ status: "finalizzato" as Readiness["status"] });
    expect(html).toContain("Stato di finalizzazione non riconosciuto");
    expect(html).not.toContain(">Pronto<");
  });

  it("l'etichetta si legge, non sta solo nel bordo colorato", () => {
    for (const [status, label] of [
      ["ready", "Pronto"],
      ["draft", "Bozza"],
      ["blocked", "Bloccato"],
    ] as const) {
      const html = banner({ status });
      expect(html).toContain(label);
      expect(html).toContain("<svg");
    }
  });
});

describe("i motivi del verdetto", () => {
  it("portano messaggio, severità, sezione e codice", () => {
    const html = banner({ status: "blocked", reasons: [REASON] });
    expect(html).toContain("Forecast precedente alle ipotesi salvate.");
    expect(html).toContain("Errore");
    expect(html).toContain("forecast");
    expect(html).toContain("forecast_stale");
    expect(html).toContain('role="alert"');
  });

  it("una lista vuota e un'assenza sono due frasi diverse", () => {
    expect(readinessReasons({ status: "draft" })).toMatchObject({ declared: false, items: [] });
    expect(readinessReasons({ status: "draft", reasons: [] })).toMatchObject({ declared: true, items: [] });

    expect(banner({ status: "draft", reasons: [] })).toContain("Nessun motivo dichiarato");
    expect(banner({ status: "draft" })).toContain("Il modello non dichiara i motivi");
  });

  it("un verdetto «pronto» con un errore dentro si dichiara come incongruenza", () => {
    const html = banner({ status: "ready", reasons: [REASON] });
    expect(html).toContain("Incongruenza");
    expect(readinessReasons({ status: "ready", reasons: [REASON] }).contradiction).toBe(true);
    expect(readinessReasons({ status: "ready", reasons: [] }).contradiction).toBe(false);
  });

  it("un motivo con una severità che non è delle tre resta leggibile", () => {
    const strange = { ...REASON, severity: "critico" as Diagnostic["severity"] };
    const html = banner({ status: "blocked", reasons: [strange] });
    expect(html).toContain("Severità non dichiarata");
    expect(html).toContain("critico");
  });
});
