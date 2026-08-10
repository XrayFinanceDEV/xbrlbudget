import { describe, expect, it } from "vitest";
import { reconcileSubfields } from "./pratica-reconcile";

describe("reconcileSubfields", () => {
  it("bilancio abbreviato: il gap dell'aggregato finisce nel campo plug", () => {
    const data: Record<string, number> = {
      sp16_debiti_breve: 100_000,
      sp16a_debiti_banche_breve: 40_000,
      sp16d_debiti_fornitori_breve: 25_000,
    };
    reconcileSubfields(data);
    expect(data.sp16g_altri_debiti_breve).toBe(35_000);
  });

  it("dettaglio gia' quadrato: nessun plug", () => {
    const data: Record<string, number> = {
      sp05_rimanenze: 50_000,
      sp05a_materie_prime: 20_000,
      sp05d_prodotti_finiti: 30_000,
      sp05e_acconti: 0,
    };
    reconcileSubfields(data);
    expect(data.sp05e_acconti).toBe(0);
  });

  it("gap negativo: il plug puo' diventare negativo", () => {
    const data: Record<string, number> = {
      sp12_riserve: 10_000,
      sp12c_riserva_legale: 15_000,
    };
    reconcileSubfields(data);
    expect(data.sp12e_altre_riserve).toBe(-5_000);
  });

  it("scarto sotto il centesimo: ignorato", () => {
    const data: Record<string, number> = {
      sp06_crediti_breve: 1_000,
      sp06a_crediti_clienti_breve: 999.995,
    };
    reconcileSubfields(data);
    expect(data.sp06g_crediti_altri_breve).toBeUndefined();
  });

  it("sbilancio attivo/passivo <= 5 EUR: assorbito dalla cassa", () => {
    const data: Record<string, number> = {
      sp03_immob_materiali: 60_000,
      sp09_disponibilita_liquide: 40_003,
      sp11_capitale: 10_000,
      sp16_debiti_breve: 90_000,
      sp16g_altri_debiti_breve: 90_000,
    };
    reconcileSubfields(data);
    expect(data.sp09_disponibilita_liquide).toBe(40_000);
  });

  it("sbilancio attivo/passivo > 5 EUR: NON assorbito, resta visibile", () => {
    const data: Record<string, number> = {
      sp03_immob_materiali: 60_000,
      sp09_disponibilita_liquide: 40_050,
      sp11_capitale: 10_000,
      sp16_debiti_breve: 90_000,
      sp16g_altri_debiti_breve: 90_000,
    };
    reconcileSubfields(data);
    expect(data.sp09_disponibilita_liquide).toBe(40_050);
  });

  it("riconcilia tutti e nove gli aggregati in una sola passata", () => {
    const data: Record<string, number> = {
      sp04_immob_finanziarie: 1_000,
      sp05_rimanenze: 2_000,
      sp06_crediti_breve: 3_000,
      sp07_crediti_lungo: 4_000,
      sp12_riserve: 5_000,
      sp16_debiti_breve: 6_000,
      sp17_debiti_lungo: 7_000,
      ce08_costi_personale: 8_000,
      ce09_ammortamenti: 9_000,
    };
    reconcileSubfields(data);
    expect(data.sp04a_partecipazioni).toBe(1_000);
    expect(data.sp05e_acconti).toBe(2_000);
    expect(data.sp06g_crediti_altri_breve).toBe(3_000);
    expect(data.sp07g_crediti_altri_lungo).toBe(4_000);
    expect(data.sp12e_altre_riserve).toBe(5_000);
    expect(data.sp16g_altri_debiti_breve).toBe(6_000);
    expect(data.sp17g_altri_debiti_lungo).toBe(7_000);
    expect(data.ce08b_salari_stipendi).toBe(8_000);
    expect(data.ce09c_svalutazioni).toBe(9_000);
  });

  it("gruppi con dettaglio valorizzato: sp04, sp07, sp17, ce08, ce09", () => {
    const data: Record<string, number> = {
      // sp04_immob_finanziarie: dettaglio 1.500, aggregato 2.000 -> gap 500 nel plug sp04a
      sp04_immob_finanziarie: 2_000,
      sp04b_crediti_immob_breve: 1_000,
      sp04d_altri_titoli: 500,
      // sp07_crediti_lungo: dettaglio 3.000, aggregato 3.800 -> gap 800 nel plug sp07g
      sp07_crediti_lungo: 3_800,
      sp07a_crediti_clienti_lungo: 2_000,
      sp07c_crediti_collegate_lungo: 1_000,
      // sp17_debiti_lungo: dettaglio 7.000, aggregato 7.300 -> gap 300 nel plug sp17g
      sp17_debiti_lungo: 7_300,
      sp17a_debiti_banche_lungo: 5_000,
      sp17d_debiti_fornitori_lungo: 2_000,
      // ce08_costi_personale: dettaglio 1.500, aggregato 2.000 -> gap 500 nel plug ce08b
      ce08_costi_personale: 2_000,
      ce08c_oneri_sociali: 1_200,
      ce08a_tfr_accrual: 300,
      // ce09_ammortamenti: dettaglio 2.000, aggregato 2.100 -> gap 100 nel plug ce09c
      ce09_ammortamenti: 2_100,
      ce09a_ammort_immateriali: 800,
      ce09b_ammort_materiali: 1_200,
    };
    // Attivo (sp04 2.000 + sp07 3.800 = 5.800) vs Passivo (sp17 7.300) = -1.500:
    // ben oltre la banda di assorbimento (<= 5 EUR), quindi il passo finale
    // Attivo/Passivo non tocca sp09 e non puo' perturbare le asserzioni sotto.
    reconcileSubfields(data);
    expect(data.sp04a_partecipazioni).toBe(500);
    expect(data.sp07g_crediti_altri_lungo).toBe(800);
    expect(data.sp17g_altri_debiti_lungo).toBe(300);
    expect(data.ce08b_salari_stipendi).toBe(500);
    expect(data.ce09c_svalutazioni).toBe(100);
  });
});
