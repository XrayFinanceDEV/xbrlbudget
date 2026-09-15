import { describe, expect, it } from "vitest";
import {
  DEAD_FIELDS, ROUTE_DOPO_CALCOLO, STEP_FIELDS, WIZARD_STEPS, groupWizardSteps, horizonLabel, nextStep,
  parseStoredStep, prevStep, railBadges,
  primaryLabel, saveOutcome, stepFooterHint, stepForErrorMessage, stepLead, stepStorageKey,
  stepsUpTo, wizardChrome, type WizardStep,
} from "./budget-wizard-steps";

describe("budget-wizard-steps", () => {
  it("ha sette passi numerati in ordine, in tre gruppi, con i due passi nuovi marcati", () => {
    expect(WIZARD_STEPS.map((s) => s.key)).toEqual([
      "scenario", "fatturato", "costi", "circolante", "patrimoniale-pregresso", "patrimoniale-piano", "imposte",
    ]);
    expect(WIZARD_STEPS.map((s) => s.group)).toEqual([
      "Impostazione", "Conto economico", "Conto economico",
      "Stato patrimoniale", "Stato patrimoniale", "Stato patrimoniale", "Stato patrimoniale",
    ]);
    expect(WIZARD_STEPS.filter((s) => s.badge === "nuovo").map((s) => s.n)).toEqual([5, 6]);
    expect(WIZARD_STEPS.map((s) => s.title)).toEqual([
      "Scenario", "Fatturato", "Costi", "Capitale circolante", "Patrimoniale pregresso", "Patrimoniale piano", "Imposte",
    ]);
  });
  it("ogni campo esposto appartiene a un solo passo e i campi morti a nessuno", () => {
    const seen = new Map<string, string>();
    for (const [step, fields] of Object.entries(STEP_FIELDS)) {
      for (const f of fields) {
        expect(seen.has(f), `${f} in ${seen.get(f)} e ${step}`).toBe(false);
        seen.set(f, step);
      }
    }
    for (const dead of DEAD_FIELDS) expect(seen.has(dead)).toBe(false);
    expect(seen.get("revenue_growth_pct")).toBe("fatturato");
    expect(seen.get("fixed_materials_percentage")).toBe("costi");
    expect(seen.get("sp16e_growth_pct")).toBe("imposte");
    expect(seen.get("existing_debt_repayment_years")).toBe("patrimoniale-pregresso");
    expect(seen.get("other_costs_growth_pct")).toBe("costi");
    expect(seen.get("bank_lines_amount")).toBe("patrimoniale-pregresso");
    expect(seen.get("tfr_payments")).toBe("patrimoniale-piano");
    expect(seen.get("sp16g_growth_pct")).toBe("patrimoniale-piano");
    expect(seen.get("inflation_pct")).toBe("scenario");
  });
  it("etichetta del primario e navigazione", () => {
    expect(primaryLabel("costi")).toBe("Avanti");
    expect(primaryLabel("imposte")).toBe("Salva e calcola previsionale");
    expect(nextStep("scenario")).toBe("fatturato");
    expect(nextStep("imposte")).toBeNull();
    expect(prevStep("scenario")).toBeNull();
    expect(stepForErrorMessage("Fabbisogno finanziario scoperto di 84.120,00: aggiungi ...")).toBe("patrimoniale-piano");
    expect(stepForErrorMessage("Modifica il piano nel passo «Patrimoniale pregresso», oppure svuota la cella.")).toBe("patrimoniale-pregresso");
    expect(stepForErrorMessage("Liquidazioni TFR 2027: superano il fondo. Correggi al passo Patrimoniale piano.")).toBe("patrimoniale-piano");
    expect(stepForErrorMessage("Il debito tributario si scadenzia al passo «Imposte».")).toBe("imposte");
    expect(stepForErrorMessage("altro")).toBe("imposte");
    expect(stepStorageKey(12)).toBe("budget-wizard-step:12");
  });
  it("raggruppa per identita' di gruppo, non per vicinanza (I3)", () => {
    // Fixture deliberatamente non contigua: A, B, A. Un raggruppamento che si
    // fonde solo col vicino precedente produrrebbe due gruppi "A".
    const steps: WizardStep[] = [
      { n: 1, key: "scenario", title: "Uno", subtitle: "", group: "Impostazione" },
      { n: 2, key: "fatturato", title: "Due", subtitle: "", group: "Conto economico" },
      { n: 3, key: "costi", title: "Tre", subtitle: "", group: "Impostazione" },
    ];
    const grouped = groupWizardSteps(steps);
    expect(grouped).toHaveLength(2);
    expect(grouped.map((g) => g.group)).toEqual(["Impostazione", "Conto economico"]);
    expect(grouped[0].steps.map((s) => s.key)).toEqual(["scenario", "costi"]);
    expect(grouped[1].steps.map((s) => s.key)).toEqual(["fatturato"]);
  });
  it("sui sette passi veri produce i tre gruppi noti, in ordine", () => {
    const grouped = groupWizardSteps(WIZARD_STEPS);
    expect(grouped.map((g) => g.group)).toEqual(["Impostazione", "Conto economico", "Stato patrimoniale"]);
    expect(grouped.reduce((n, g) => n + g.steps.length, 0)).toBe(7);
  });
});

describe("stepLead", () => {
  it("ogni passo ha un sottotitolo non vuoto", () => {
    for (const s of WIZARD_STEPS) expect(stepLead(s.key, 2024).length).toBeGreaterThan(0);
  });
  it("l'anno base e' quello vero, non il 2025 scritto a mano nel prototipo", () => {
    expect(stepLead("scenario", 2022)).toContain("2022");
    expect(stepLead("scenario", 2022)).not.toContain("2025");
    expect(stepLead("circolante", 2022)).toContain("2022");
  });
});

describe("stepFooterHint", () => {
  it("porta la posizione nel percorso", () => {
    expect(stepFooterHint("scenario")).toBe("Passo 1 di 7 · Scenario");
    expect(stepFooterHint("circolante")).toBe("Passo 4 di 7 · Capitale circolante");
  });
  it("l'ultimo passo dice dove si atterra dopo il calcolo", () => {
    const hint = stepFooterHint("imposte");
    expect(hint).toContain("Passo 7 di 7");
    expect(hint).toContain("CE Prev.");
    expect(hint).toContain("SP Prev.");
  });
});

describe("parseStoredStep", () => {
  it("riconosce un passo valido", () => {
    expect(parseStoredStep("circolante")).toBe("circolante");
  });
  it("una chiave assente o un valore ignoto non aprono un passo inesistente", () => {
    expect(parseStoredStep(null)).toBeNull();
    expect(parseStoredStep(undefined)).toBeNull();
    expect(parseStoredStep("")).toBeNull();
    expect(parseStoredStep("riepilogo")).toBeNull();
    // Non deve bastare che la stringa sia una proprieta' di Object.prototype.
    expect(parseStoredStep("toString")).toBeNull();
  });
});

describe("stepsUpTo", () => {
  it("porta tutti i passi fino a quello dato, compreso", () => {
    expect(stepsUpTo("scenario")).toEqual(["scenario"]);
    expect(stepsUpTo("costi")).toEqual(["scenario", "fatturato", "costi"]);
    expect(stepsUpTo("imposte")).toHaveLength(7);
  });
  it("chi riapre al passo 7 non trova sei pallini grigi", () => {
    // Segnare come visitato il solo passo ripristinato farebbe dire alla
    // guida il contrario di dove si trova l'utente.
    expect(stepsUpTo("imposte")).toContain("scenario");
    expect(stepsUpTo("imposte")).toContain("circolante");
  });
});

describe("wizardChrome", () => {
  it("dentro la pratica il wizard NON rende la propria barra in fondo", () => {
    // Due barre a bottom:0: quella della pratica (z-30, sticky) copre quella
    // del wizard (z-10, fixed), e il click su «Indietro» finisce sull'«Avanti»
    // del percorso. Misurato nel browser, non dedotto.
    const c = wizardChrome(true);
    expect(c.bottomBar).toBe(false);
    expect(c.primaryButton).toBe(false);
    // Ma Annulla e Indietro devono restare raggiungibili: risalgono in testa.
    expect(c.headerControls).toBe(true);
    // Nessuna barra `fixed` da compensare.
    expect(c.containerClass).toBe("");
  });
  it("fuori dalla pratica la barra del wizard e' l'unica e resta", () => {
    const c = wizardChrome(false);
    expect(c.bottomBar).toBe(true);
    expect(c.primaryButton).toBe(true);
    expect(c.headerControls).toBe(false);
    expect(c.containerClass).toBe("pb-24");
  });
  it("i comandi esistono sempre in esattamente un posto", () => {
    for (const inPratica of [true, false]) {
      const c = wizardChrome(inPratica);
      // Mai due barre insieme, e mai zero posti in cui premere Indietro.
      expect(c.bottomBar).toBe(!c.headerControls);
      // Il `pb-24` esiste se e solo se c'e' una barra `fixed` da compensare.
      expect(c.containerClass === "pb-24").toBe(c.bottomBar);
    }
  });
});

describe("saveOutcome", () => {
  it("un previsionale rifiutato torna 200: la verita' e' in forecast_generated", () => {
    const out = saveOutcome({
      forecast_generated: false,
      message: "Fabbisogno finanziario scoperto di 84.120,00",
    });
    expect(out.ok).toBe(false);
    // Il toast e' la stessa frase dell'anteprima (`saveNotice`), rifinita
    // dal riconoscimento del fabbisogno; il PASSO si decide sul messaggio
    // grezzo, gia' italiano alla fonte.
    expect(out.message).toContain("Fabbisogno finanziario scoperto");
    expect(out.step).toBe("patrimoniale-piano");
  });
  it("un rifiuto non naviga MAI: niente toast verde su una Proiezione vuota", () => {
    // E' il difetto piu' costoso documentato in CLAUDE.md, e prima era
    // rimediabile togliendo un `return` dal componente senza rompere nulla.
    expect(saveOutcome({ forecast_generated: false, message: "x" }).route).toBeNull();
    expect(saveOutcome({ forecast_generated: false }).route).toBeNull();
  });
  it("un rifiuto senza ragione ha comunque un messaggio, e cade sull'ultimo passo", () => {
    expect(saveOutcome({ forecast_generated: false, message: "   " })).toEqual({
      ok: false, message: "Previsionale non generato", step: "imposte", route: null,
    });
  });
  it("si atterra sul CE previsionale, dove i numeri appena calcolati si leggono", () => {
    expect(saveOutcome({ forecast_generated: true }).route).toBe(ROUTE_DOPO_CALCOLO);
    expect(ROUTE_DOPO_CALCOLO).toBe("/forecast/income");
  });
  it("solo un false esplicito e' un rifiuto: un campo assente non e' una negazione", () => {
    const atteso = { ok: true, message: "Previsionale calcolato", step: null, route: ROUTE_DOPO_CALCOLO };
    expect(saveOutcome({ forecast_generated: true })).toEqual(atteso);
    expect(saveOutcome({})).toEqual(atteso);
    expect(saveOutcome(null)).toEqual(atteso);
    expect(saveOutcome(undefined)).toEqual(atteso);
  });
  it("un successo non sposta il passo: si resta dove si e', poi si naviga", () => {
    expect(saveOutcome({ forecast_generated: true }).step).toBeNull();
  });
});

describe("horizonLabel", () => {
  it("piu' anni: plurale e intervallo", () => {
    expect(horizonLabel(3, 2026)).toBe("Orizzonte 3 anni · 2027 – 2029");
    expect(horizonLabel(5, 2025)).toBe("Orizzonte 5 anni · 2026 – 2030");
  });
  it("un anno solo: singolare, e nessun intervallo che ripete lo stesso anno", () => {
    // Prima si leggeva «Orizzonte 1 anni · 2027 – 2027»: due errori in sette parole.
    expect(horizonLabel(1, 2026), "un piano di un anno non e' «1 anni»").toBe("Orizzonte 1 anno · 2027");
  });
  it("nessun anno di piano non e' un intervallo a rovescio", () => {
    expect(horizonLabel(0, 2026)).toBe("Nessun anno di piano");
    expect(horizonLabel(-2, 2026)).toBe("Nessun anno di piano");
  });
});

describe("stepForErrorMessage · scoperto di c/c (Task 12)", () => {
  it("il tetto dello scoperto superato riporta al passo in cui lo scoperto si concede", () => {
    expect(stepForErrorMessage(
      "Scoperto di conto corrente oltre il tetto concesso: servono 5.014.777,78, il tetto concesso e' 100.000,00",
    )).toBe("patrimoniale-piano");
  });
});

describe("stepForErrorMessage · rifiuti che nominano il passo (m-B)", () => {
  it("un rifiuto fornitori che dice «passo Patrimoniale pregresso» atterra sul passo 5", () => {
    // Messaggio reale di `_rifiuto_override_governati` (via
    // `_messaggio_override_oltre`), generato da `c8317ca`, aggiornato al nome
    // di passo del giro di rilievi (Task 6: `_PREGRESSO_PASSO_DEFAULT`).
    expect(stepForErrorMessage(
      "L'override di sp17d_debiti_fornitori_lungo non è ammesso: i debiti verso fornitori hanno un piano di scadenziamento, e il suo calendario rigenera quella riga ogni anno, l'ultimo compreso. Il valore forzato verrebbe salvato e cancellato in silenzio l'anno dopo, con la cassa ad assorbire la differenza senza alcun flusso. La via lecita è modificare il piano al passo Patrimoniale pregresso, oppure svuotare la cella (value: null) e lasciare che la riga segua il piano.",
    )).toBe("patrimoniale-pregresso");
  });
  it("vale anche con il nome del passo virgolettato", () => {
    expect(stepForErrorMessage(
      "Modifica il piano nel passo «Patrimoniale pregresso», oppure svuota la cella (value: null).",
    )).toBe("patrimoniale-pregresso");
  });
  it("il fabbisogno non coperto continua ad atterrare sul passo 6", () => {
    expect(stepForErrorMessage(
      "Fabbisogno finanziario scoperto di 44.885,64: aggiungi un'ipotesi di finanziamento esplicita",
    )).toBe("patrimoniale-piano");
  });
  it("un errore generico atterra su Imposte come prima", () => {
    expect(stepForErrorMessage("Revenue must be positive in the base year")).toBe("imposte");
  });
});

describe("stepForErrorMessage · piano dei tributari al passo 5, non al passo 7 (Task 16)", () => {
  // Decisione del proprietario (2026-09-15): saldo, rateizzato e rate dei
  // debiti tributari si scadenziano al passo 5 «Patrimoniale pregresso», non
  // al passo 7 «Imposte» (che tiene solo aliquota, differenze temporanee, via
  // manuale e acconto). Il motore Python (`_PREGRESSO_PASSO`,
  // `calculations/forecast_engine.py`) è corretto da un altro task del lotto
  // e OGGI nomina ancora «Imposte» in questi tre messaggi — le stringhe qui
  // sotto sono il testo POST-correzione: `stepForErrorMessage` instrada già
  // per contenuto («patrimoniale pregresso» in qualunque punto del testo), e
  // non ha bisogno di modifiche per riconoscerlo; questi test lo mettono agli
  // atti prima che il motore cambi.
  it("`_messaggio_override_oltre('sp17e_debiti_tributari_lungo', 'debiti_tributari')` atterra sul passo 5", () => {
    expect(stepForErrorMessage(
      "L'override di sp17e_debiti_tributari_lungo non è ammesso: i debiti tributari hanno un piano " +
      "di scadenziamento, e il suo calendario rigenera quella riga ogni anno, l'ultimo compreso. Il valore " +
      "forzato verrebbe salvato e cancellato in silenzio l'anno dopo, con la cassa ad assorbire la differenza " +
      "senza alcun flusso. Modifica il piano al passo «Patrimoniale pregresso», oppure svuota la cella " +
      "(value: null) e lascia che la riga segua il piano.",
    )).toBe("patrimoniale-pregresso");
  });
  it("il ramo Ruling 63 (`sp17e` senza piano ancora da impostare) atterra sul passo 5", () => {
    expect(stepForErrorMessage(
      "L'override di sp17e_debiti_tributari_lungo non è ammesso: la posizione tributaria è a saldo + acconto, " +
      "e l'anno dopo riparte dal saldo e dalle rate che questa posizione dichiara, non da questa riga. Il valore " +
      "forzato sparirebbe senza alcun versamento, con la cassa ad assorbire la differenza. Imposta un piano di " +
      "scadenziamento dei debiti tributari al passo «Patrimoniale pregresso», oppure svuota la cella (value: null).",
    )).toBe("patrimoniale-pregresso");
  });
  it("il rifiuto N-I1 (transizione via manuale → automatico) atterra sul passo 5", () => {
    expect(stepForErrorMessage(
      "Il piano dei debiti tributari non può ripartire da meno di ciò che resta da rateizzare: l'anno 2027 " +
      "esce dalla via manuale lasciando 12.000,00, ma all'anno 2028 ne restano da rateizzare 14.666,66. Tieni " +
      "in via manuale anche l'anno 2028, oppure lascia nell'anno 2027 un debito tributario (sp16e + sp17e, per " +
      "percentuale o per override) non inferiore a 14.666,66, o modifica il piano al passo «Patrimoniale pregresso».",
    )).toBe("patrimoniale-pregresso");
  });
  it("un rifiuto che parla di acconto senza nominare un piano resta sul passo 7", () => {
    // L'acconto e la via manuale non hanno un calendario da scadenziare al
    // passo 5: restano decisioni del passo 7, e un messaggio che le riguarda
    // non nomina «Patrimoniale pregresso» — cade sul ramo di default.
    expect(stepForErrorMessage(
      "L'acconto versato nel 2027 supera l'imposta di competenza: la differenza resta credito verso l'erario " +
      "e non genera alcun rimborso automatico.",
    )).toBe("imposte");
  });
  it("un rifiuto sulla via manuale (sp06e/sp16e) resta sul passo 7", () => {
    expect(stepForErrorMessage(
      "La via manuale governa sp06e e sp16e per percentuale di crescita: il piano di saldo, rate e acconti " +
      "dichiarato altrove viene ignorato per l'intera durata della via manuale.",
    )).toBe("imposte");
  });
});

describe("railBadges (Task 9)", () => {
  it("«da integrare» sovrascrive «nuovo» del catalogo, gli altri passi «nuovo» restano", () => {
    expect(railBadges(["scenario"])).toEqual({ scenario: "da integrare", "patrimoniale-pregresso": "nuovo", "patrimoniale-piano": "nuovo" });
  });
  it("senza migrazione restano solo i badge «nuovo» del catalogo", () => {
    expect(railBadges([])).toEqual({ "patrimoniale-pregresso": "nuovo", "patrimoniale-piano": "nuovo" });
  });
});
