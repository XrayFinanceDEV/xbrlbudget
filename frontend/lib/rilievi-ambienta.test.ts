// Banco di triage dei rilievi AMBIENTA — lato wizard. Spec: docs/superpowers/specs/2026-09-25-triage-rilievi-ambienta-design.md.
// Oracolo = comportamento che il consulente si aspetta: un test rosso vuol dire che il difetto c'è.
import { describe, expect, it } from "vitest";

async function fn<T = any>(mod: string, name: string): Promise<T | null> {
  try {
    const m: any = await import(/* @vite-ignore */ mod);
    return (m?.[name] as T) ?? null;
  } catch {
    return null;
  }
}

describe("rilievi AMBIENTA · wizard", () => {
  // A01 confermato dal triage 2026-09-25: lo scostamento digitato è salvato come percentuale
  // assoluta e non si mantiene quando la crescita ricavi cambia in seguito.
  it.fails("A01 lo scostamento digitato resta lo scostamento dopo un cambio dei ricavi", async (ctx) => {
    const change = await fn<(d: number | null, r: number) => number>("@/lib/budget-costi-step", "variableGrowthChange");
    const dev = await fn<(g: number | null, r: number) => string>("@/lib/budget-costi-step", "variableGrowthDeviation");
    if (!change || !dev) return ctx.skip();
    const salvato = change(-5, 5); // ricavi +5, scostamento −5 → materie 0
    expect(salvato).toBe(0);
    // I ricavi passano a +7 dopo: il consulente si aspetta che lo scostamento resti −5 (materie +2).
    expect(dev(salvato, 7)).toBe("-5");
  });

  it("A03 il passo Imposte ha un campo per anno collegato a tax_advances_paid", async (ctx) => {
    const row = await fn<(p: unknown, pct: number) => { field: string }>("@/lib/budget-imposte-step", "accontiRow");
    if (!row) return ctx.skip();
    expect(row({ forecast_years: [] }, 100).field).toBe("tax_advances_paid");
  });

  // A05 rimosso da questo file (fix round 1, controller): congelare i valori dell'anteprima quando
  // si passa a Manuale è comportamento voluto, fissato da
  // frontend/lib/budget-sp-manuale.test.ts:52-58 ("scegliere Manuale congela i valori dell'anteprima
  // per anno") — non un verdetto del wizard. Il rilievo del consulente riguarda Manuale con i CAMPI
  // VUOTI, cioè che cosa fa il MOTORE quando sp04 non ha né override né indicizzazione: spostato in
  // tests/test_rilievi_ambienta.py
  // (test_A05_immobilizzazioni_finanziarie_senza_regola_non_seguono_i_ricavi).

  // Ruling (controller): l'oracolo del brief (`riga.driver` null con casella spenta e indicizzazione
  // {sp16f:"ricavi"}) sarebbe rosso per uno stato legittimo — a casella spenta la tendina e' l'unico
  // comando attivo, quindi un driver non nullo e' corretto, non un difetto. Il rilievo vero del
  // consulente e' un altro: lo schermo diceva «Cresce con il costo del personale» mentre l'output
  // cresceva coi ricavi, casella NON spuntata. Il test verifica quindi che l'etichetta di sp16f
  // concordi con ciò che il motore farà davvero: a casella spenta la tendina governa e l'etichetta
  // non deve nominare «personale»; a casella accesa e' la casella a governare e l'etichetta deve
  // nominare «personale».
  it("A06 l'etichetta dei previdenziali dice quello che fa il motore", async (ctx) => {
    const rows = await fn<any>("@/lib/budget-circolante-step", "minorFieldsRows");
    if (!rows) return ctx.skip();
    const baseBs = { sp16f_debiti_previdenza_breve: 163536.55 };

    // Casella spenta, tendina su "ricavi": il motore segue i ricavi (indicizzazione esplicita).
    const spenta: any[] = rows(baseBs, { sp16f: "ricavi" }, false, []);
    const rigaSpenta = spenta.find((r) => r.code === "sp16f" || r.balanceField === "sp16f_debiti_previdenza_breve");
    expect(rigaSpenta).toBeDefined();
    expect(String(rigaSpenta.andamento ?? "")).not.toMatch(/personale/);

    // Casella accesa: il motore ignora la tendina e segue il personale.
    const accesa: any[] = rows(baseBs, {}, true, []);
    const rigaAccesa = accesa.find((r) => r.code === "sp16f" || r.balanceField === "sp16f_debiti_previdenza_breve");
    expect(rigaAccesa).toBeDefined();
    expect(String(rigaAccesa.andamento ?? "")).toMatch(/personale/);
  });
});
