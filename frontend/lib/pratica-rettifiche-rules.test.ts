import { describe, it, expect } from "vitest";
import {
  EDITABLE_RETTIFICHE,
  NON_POSTABLE_FIELDS,
  destinazioneModifica,
} from "./pratica-rettifiche-rules";
import { DETAIL_PARENTS } from "./pratica-codes";

describe("destinazioneModifica", () => {
  // Un totale ricostruito da recalcAggregates cancella la modifica e lascia la
  // contropartita: AMBIENTA, +200.000 sui costi del personale -> sbilancio 200.000,03.
  const totaliModificabili = [...EDITABLE_RETTIFICHE].filter((f) => NON_POSTABLE_FIELDS.has(f));

  it("ogni totale modificabile manda la modifica a una propria sotto-voce", () => {
    expect(totaliModificabili.sort()).toEqual(
      ["ce08_costi_personale", "sp05_rimanenze", "sp06_crediti_breve", "sp07_crediti_lungo"],
    );
    for (const totale of totaliModificabili) {
      const destinazione = destinazioneModifica(totale);
      expect(NON_POSTABLE_FIELDS.has(destinazione)).toBe(false);
      expect(DETAIL_PARENTS[destinazione]).toBe(totale);
    }
  });

  it("i costi del personale vanno su salari e stipendi", () => {
    expect(destinazioneModifica("ce08_costi_personale")).toBe("ce08b_salari_stipendi");
  });

  it("una voce che non e' un totale resta se stessa", () => {
    expect(destinazioneModifica("ce06_servizi")).toBe("ce06_servizi");
    expect(destinazioneModifica("sp16f_debiti_previdenza_breve")).toBe("sp16f_debiti_previdenza_breve");
  });
});
