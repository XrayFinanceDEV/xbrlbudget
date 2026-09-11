"use client";

/**
 * Il contenitore del percorso a sette passi delle ipotesi (spec 2026-09-08,
 * Task 15): sostituisce la vecchia tab «Ipotesi» di `/budget` per gli scenari
 * nati da un bilancio. Lo startup resta su `ScenarioFormStartup`.
 *
 * Qui dentro non si DECIDE nulla: un componente in questo repo non e'
 * collaudabile (nessun jsdom, e non va aggiunto). Quale sottotitolo, quale
 * riga in fondo, quale passo aprire al ritorno, e soprattutto se il
 * salvataggio sia riuscito, stanno tutti in `lib/budget-wizard-steps.ts` con
 * la loro suite in `environment: node`. Questo file monta lo stato, li
 * chiama e rende.
 *
 * Un solo motore di proiezione, e sta in Python: l'anteprima e' una POST a
 * `/scenarios/{id}/preview` — nessun numero mostrato dai passi viene
 * ricalcolato qui.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { JSX } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { usePratica } from "@/contexts/PraticaContext";
import { usePrimaryAction } from "@/contexts/PraticaActionContext";
import { useInvalidateAnalysis, useInvalidateScenarios } from "@/hooks/use-queries";
import { useForecastPreview } from "@/hooks/use-forecast-preview";
import { useScenarioAssumptions } from "@/hooks/use-scenario-assumptions";
import { bulkUpsertAssumptions, updateBudgetScenario } from "@/lib/api";
import { assumptionRowsForSave } from "@/lib/budget-horizon";
import {
  WIZARD_STEPS,
  nextStep,
  parseStoredStep,
  prevStep,
  primaryLabel,
  saveOutcome,
  stepFooterHint,
  stepLead,
  stepStorageKey,
  stepsUpTo,
  wizardChrome,
  type WizardStepKey,
} from "@/lib/budget-wizard-steps";
import { getErrorMessage } from "@/lib/utils";
import { righeErroriIpotesi } from "@/lib/budget-bulk-errors";
import type { BudgetScenario } from "@/types/api";
import { WizardRail } from "./WizardRail";
import type { StepProps } from "./types";
import { StepScenario } from "./steps/StepScenario";
import { StepFatturato } from "./steps/StepFatturato";
import { StepCosti } from "./steps/StepCosti";
import { StepAltreVociCE } from "./steps/StepAltreVociCE";
import { StepCircolante } from "./steps/StepCircolante";
import { StepPregressoNuovo } from "./steps/StepPregressoNuovo";
import { StepImposte } from "./steps/StepImposte";

/** Lettura/scrittura di `localStorage` che non fa cadere il wizard quando lo
 *  storage non e' disponibile (Safari privato, iframe con cookie bloccati). */
function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage non disponibile: il passo semplicemente non si ricorda */
  }
}

export function BudgetWizard({
  companyId,
  years,
  scenario,
  onCancel,
}: {
  companyId: number;
  years: number[];
  scenario: BudgetScenario;
  onCancel: () => void;
}): JSX.Element {
  const router = useRouter();
  const { pratica } = usePratica();
  const invalidateScenarios = useInvalidateScenarios();
  const invalidateAnalysis = useInvalidateAnalysis();
  const s = useScenarioAssumptions({ companyId, years, scenario });

  const [name, setName] = useState(scenario.name);
  const [description, setDescription] = useState(scenario.description ?? "");
  const [isActive, setIsActive] = useState(scenario.is_active === 1);
  const [inflation, setInflation] = useState(2);
  const [step, setStep] = useState<WizardStepKey>("scenario");
  const [visited, setVisited] = useState<Set<WizardStepKey>>(new Set(["scenario"]));
  const [saving, setSaving] = useState(false);

  // Il passo ricordato si legge in un effetto, MAI nell'inizializzatore di
  // `useState`: Next sbaglia l'idratazione se il primo render del client non
  // e' identico a quello del server.
  //
  // `ripristinatoPer` tiene l'id dello scenario per cui il ripristino e' gia'
  // avvenuto. Serve perche' i due effetti girano nello stesso commit, in
  // ordine di dichiarazione: senza il cancello, l'effetto di scrittura qui
  // sotto scriverebbe il passo VECCHIO sotto la chiave NUOVA prima che il
  // `setStep` di questo sia atterrato.
  const [ripristinatoPer, setRipristinatoPer] = useState<number | null>(null);
  useEffect(() => {
    const ricordato = parseStoredStep(readStorage(stepStorageKey(scenario.id))) ?? "scenario";
    setStep(ricordato);
    // Chi riapre al passo 7 ci era arrivato passando per gli altri sei:
    // segnare visitato il solo passo ripristinato mostrerebbe sei pallini
    // grigi accanto a un settimo attivo.
    setVisited(new Set(stepsUpTo(ricordato)));
    setRipristinatoPer(scenario.id);
  }, [scenario.id]);

  // Lo stato persistito si scrive in un effetto, mai dentro un updater di
  // `setState`: `reactStrictMode` invoca gli updater due volte in sviluppo.
  // L'effetto non dipende da cio' che scrive (`visited` non e' fra le
  // dipendenze: l'updater lo legge, non l'effetto).
  useEffect(() => {
    if (ripristinatoPer !== scenario.id) return;
    writeStorage(stepStorageKey(scenario.id), step);
    setVisited((v) => (v.has(step) ? v : new Set(v).add(step)));
    window.scrollTo({ top: 0 });
  }, [ripristinatoPer, scenario.id, step]);

  // Le righe che vanno all'anteprima sono le stesse che vanno al salvataggio,
  // e vengono sempre dalla mappa IDRATATA: prima che le ipotesi salvate siano
  // atterrate la mappa non rappresenta lo scenario, e il bulk cancella e
  // reinserisce. `null` = «non ancora», non «nessuna riga».
  const rows = useMemo(
    () =>
      s.idratato ? assumptionRowsForSave(s.assumptions, s.forecastYears, scenario.id) : null,
    [s.idratato, s.forecastYears, s.assumptions, scenario.id],
  );

  // Il passo 1 non ha nulla da proiettare (la sua scheda ricapitola lo
  // storico gia' caricato): niente chiamata di anteprima finche' non si entra
  // nel percorso vero.
  const preview = useForecastPreview({
    companyId,
    scenarioId: scenario.id,
    rows,
    enabled: step !== "scenario",
  });

  const save = useCallback(async () => {
    if (!s.idratato || !rows) {
      toast.error("Ipotesi non ancora caricate: attendi, o ricarica la pagina");
      return;
    }
    if (!name.trim()) {
      toast.error("Il nome dello scenario è obbligatorio");
      setStep("scenario");
      return;
    }
    setSaving(true);
    try {
      await updateBudgetScenario(companyId, scenario.id, {
        name: name.trim(),
        description,
        is_active: isActive ? 1 : 0,
      });
      const result = await bulkUpsertAssumptions(companyId, scenario.id, {
        assumptions: rows,
        auto_generate: true,
      });
      // 200 con previsionale rifiutato: la verita' e' in `forecast_generated`,
      // la ragione in `message` (CLAUDE.md § Previsionale). Chi legge l'HTTP
      // 200 dipinge una colonna Proiezione vuota sotto un toast verde.
      //
      // Niente rami e niente `return` anticipato: l'esito e' un oggetto e si
      // consuma per intero, sempre nello stesso ordine. Togliere una riga qui
      // non puo' piu' produrre una navigazione dopo un rifiuto — la
      // condizione sta in `saveOutcome`, con la sua prova.
      const esito = saveOutcome(result);
      if (esito.ok) toast.success(esito.message);
      else toast.error(esito.message);
      if (esito.step) setStep(esito.step);
      if (esito.route) {
        invalidateScenarios(companyId);
        invalidateAnalysis(companyId, scenario.id);
        router.push(esito.route);
      }
    } catch (err) {
      const righe = righeErroriIpotesi(err);
      if (righe) {
        toast.error("Ipotesi non salvate: correggi i campi indicati", {
          description: (
            <ul className="list-disc pl-4">
              {righe.map((riga) => <li key={riga}>{riga}</li>)}
            </ul>
          ),
        });
      } else {
        toast.error(getErrorMessage(err, "Impossibile salvare le ipotesi"));
      }
    } finally {
      setSaving(false);
    }
  }, [
    s.idratato,
    rows,
    name,
    description,
    isActive,
    companyId,
    scenario.id,
    invalidateScenarios,
    invalidateAnalysis,
    router,
  ]);

  const goNext = useCallback(() => {
    const n = nextStep(step);
    if (n) setStep(n);
    else void save();
  }, [step, save]);

  // La barra della pratica ha un'azione primaria sola: fuori dal percorso
  // pratica non c'e' barra da alimentare, e `label: null` la lascia al
  // fallback.
  usePrimaryAction({
    label: pratica ? primaryLabel(step) : null,
    onClick: goNext,
    disabled: saving || !s.idratato,
    reason: saving
      ? "Calcolo in corso"
      : !s.idratato
      ? "Lettura delle ipotesi salvate in corso"
      : null,
  });

  const stepProps: StepProps = {
    companyId,
    scenarioId: scenario.id,
    baseYear: s.baseYear,
    forecastYears: s.forecastYears,
    assumptions: s.assumptions,
    historical: s.historicalData,
    historicalYears: s.historicalYears,
    preview,
    update: s.updateAssumption,
    updateAll: s.updateAll,
    updateFinancingLoans: s.updateFinancingLoans,
    updateTemporaryDifferences: s.updateTemporaryDifferences,
    updateSpIndexing: s.updateSpIndexing,
    updatePregresso: s.updatePregresso,
  };

  const active = WIZARD_STEPS.find((w) => w.key === step) ?? WIZARD_STEPS[0];
  const indietro = prevStep(step);
  // Quali comandi rende il wizard e dove: dentro la pratica la sua barra in
  // fondo sarebbe COPERTA da quella del percorso, e il click su «Indietro»
  // finirebbe sull'«Avanti» del percorso. La decisione, misurata nel
  // browser, sta in lib/budget-wizard-steps.ts con la sua prova.
  const chrome = wizardChrome(pratica !== null);

  const annulla = (
    <Button variant="outline" size={chrome.headerControls ? "sm" : "default"} onClick={onCancel}>
      Annulla
    </Button>
  );
  const indietroButton = (
    <Button
      variant="outline"
      size={chrome.headerControls ? "sm" : "default"}
      disabled={!indietro}
      onClick={() => {
        if (indietro) setStep(indietro);
      }}
    >
      Indietro
    </Button>
  );

  return (
    <div className={chrome.containerClass}>
      <WizardRail
        active={step}
        visited={visited}
        horizon={s.numYears}
        baseYear={s.baseYear}
        onGo={setStep}
      />

      <div className="mb-4 mt-4 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{active.title}</h1>
          <p className="text-sm text-muted-foreground">{stepLead(step, s.baseYear)}</p>
        </div>
        {/* Dentro la pratica «Avanti» sta nella barra del percorso, ma
            «Annulla» e «Indietro» non hanno un equivalente li': risalgono
            qui, dove nulla li copre. */}
        {chrome.headerControls && (
          <div className="flex shrink-0 items-center gap-2">
            {annulla}
            {indietroButton}
          </div>
        )}
      </div>

      {step === "scenario" && (
        <StepScenario
          {...stepProps}
          name={name}
          setName={setName}
          description={description}
          setDescription={setDescription}
          isActive={isActive}
          setIsActive={setIsActive}
          numYears={s.numYears}
          setNumYears={s.setNumYears}
          notaAnnoBase={s.notaAnnoBase}
          isNew={s.isNew}
          inflation={inflation}
          setInflation={setInflation}
        />
      )}
      {step === "fatturato" && <StepFatturato {...stepProps} />}
      {step === "costi" && <StepCosti {...stepProps} />}
      {step === "altre-voci-ce" && <StepAltreVociCE {...stepProps} />}
      {step === "circolante" && <StepCircolante {...stepProps} />}
      {step === "pregresso-nuovo" && <StepPregressoNuovo {...stepProps} />}
      {step === "imposte" && <StepImposte {...stepProps} />}

      {chrome.bottomBar && (
        <div className="fixed inset-x-0 bottom-0 z-10 flex items-center gap-3 border-t bg-background px-6 py-2.5">
          <span className="mr-auto text-xs text-muted-foreground">{stepFooterHint(step)}</span>
          {annulla}
          {indietroButton}
          {chrome.primaryButton && (
            <Button onClick={goNext} disabled={saving || !s.idratato}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : primaryLabel(step)}
            </Button>
          )}
        </div>
      )}
      {/* La posizione nel percorso resta visibile anche senza barra propria:
          dentro la pratica quella del percorso mostra solo il primario. */}
      {!chrome.bottomBar && (
        <p className="mt-6 text-xs text-muted-foreground">{stepFooterHint(step)}</p>
      )}
    </div>
  );
}
