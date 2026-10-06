import { describe, it, expect } from "vitest";
import {
  EDITABLE_RETTIFICHE,
  NON_POSTABLE_FIELDS,
  applicaMovimento,
  destinazioneModifica,
  sottovociDaScegliere,
} from "./pratica-rettifiche-rules";
import { DETAIL_PARENTS } from "./pratica-codes";
import { etichettaSottovoce } from "./ivcee-catalog";

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

describe("sotto-voci delle immobilizzazioni", () => {
  // FACCHINETTI ZINCATURA, 2026-10-06: +30.000 di ammortamento materiali con
  // contropartita sull'aggregato sp03 e il dettaglio sp03a-e importato -> la
  // guardia del server rifiuta, «aggregati−dettagli 0→30.000».
  const conDettaglio: Record<string, number> = {
    sp03_immob_materiali: 100_000,
    sp03b_impianti_macchinari: 80_000,
    sp03d_altri_beni: 20_000,
  };
  const valore = (v: Record<string, number>) => (k: string) => v[k] ?? 0;

  it("si sceglie la sotto-voce solo quando l'import ha il dettaglio", () => {
    const scelte = sottovociDaScegliere("sp03_immob_materiali", valore(conDettaglio));
    expect(scelte.map((s) => s.field)).toEqual([
      "sp03a_terreni_fabbricati", "sp03b_impianti_macchinari", "sp03c_attrezzature",
      "sp03d_altri_beni", "sp03e_immob_in_corso",
    ]);
    // Senza dettaglio l'aggregato resta la destinazione: il divario scende, la guardia passa.
    expect(sottovociDaScegliere("sp03_immob_materiali", valore({ sp03_immob_materiali: 100_000 }))).toEqual([]);
    // Una voce senza sotto-voci non ha secondo menu.
    expect(sottovociDaScegliere("sp09_disponibilita_liquide", valore(conDettaglio))).toEqual([]);
  });

  it("le immateriali hanno le sette sotto-voci di legge", () => {
    const scelte = sottovociDaScegliere("sp02_immob_immateriali", valore({ sp02e_avviamento: 1 }));
    expect(scelte).toHaveLength(7);
  });

  it("un movimento su una sotto-voce muove anche il suo aggregato, e si annulla", () => {
    const v = { ...conDettaglio };
    applicaMovimento(v, conDettaglio, "sp03b_impianti_macchinari", -30_000);
    expect(v.sp03b_impianti_macchinari).toBe(50_000);
    expect(v.sp03_immob_materiali).toBe(70_000);
    applicaMovimento(v, conDettaglio, "sp03b_impianti_macchinari", 30_000);
    expect(v).toEqual(conDettaglio);
  });

  it("un movimento sull'aggregato o su un'altra voce tocca solo quella", () => {
    const v = { ...conDettaglio };
    applicaMovimento(v, conDettaglio, "sp03_immob_materiali", -5);
    applicaMovimento(v, conDettaglio, "ce09b_ammort_materiali", 5);
    expect(v.sp03_immob_materiali).toBe(99_995);
    expect(v.sp03b_impianti_macchinari).toBe(80_000);
    expect(v.ce09b_ammort_materiali).toBe(5);
  });

  it("l'etichetta nomina aggregato e sotto-voce", () => {
    expect(etichettaSottovoce("sp03b_impianti_macchinari")).toBe(
      "II - Immobilizzazioni materiali › 2) Impianti e macchinario",
    );
    expect(etichettaSottovoce("sp09_disponibilita_liquide")).toBeNull();
  });
});
