"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useApp } from "@/contexts/AppContext";
import { usePratica } from "@/contexts/PraticaContext";
import { usePrimaryAction } from "@/contexts/PraticaActionContext";
import {
  importXBRL,
  importPDF,
  importOCR,
  getCompany,
  getCompanyYears,
  createBudgetScenario,
  getBudgetScenario,
  bulkUpsertAssumptions,
  getIntraYearComparison,
  getScenarioAnalysis,
} from "@/lib/api";
import { useRettificheYear } from "@/hooks/use-rettifiche-year";
import { blockedStep } from "@/lib/pratica-steps";
import type {
  BudgetScenario,
  IntraYearComparison,
  IntraYearComparisonItem,
  ScenarioAnalysis,
  RettificaEntry,
} from "@/types/api";
import { toast } from "sonner";
import {
  Upload,
  ArrowRight,
  BarChart3,
  FileText,
  Loader2,
  Check,
  Trash2,
  TrendingUp,
  TrendingDown,
  RotateCcw,
  AlertTriangle,
} from "lucide-react";
import { getErrorMessage } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { AnagraficheStep } from "@/components/pratica/AnagraficheStep";
import { RettificheTab } from "@/components/pratica/RettificheTab";
import { ComparisonTable } from "@/components/pratica/ComparisonTable";
import { ProjectionTable } from "@/components/pratica/ProjectionTable";
import { ExtraAccountingAlerts } from "@/components/pratica/ExtraAccountingAlerts";
import { IndicatoriTable } from "@/components/pratica/IndicatoriTable";
import { StampaContent } from "@/components/pratica/StampaContent";
import {
  MONTH_LABELS,
  SECTOR_OPTIONS,
  formatEuro,
  formatPct,
} from "@/lib/pratica-format";
import {
  EDITABLE_CE_CODES,
  buildCeOverridePayload,
  VP_CODES,
  EBITDA_COST_CODES,
  ATTIVO_CODES,
  PASSIVO_CODES,
} from "@/lib/pratica-codes";
import { reconcileSubfields } from "@/lib/pratica-reconcile";
import { scaledOrCarried } from "@/lib/pratica-turnover";
import {
  buildBalanceItemsWithTotals,
  buildIncomeItemsWithEbitda,
} from "@/lib/pratica-statement-rows";

export default function InfraannualePage() {
  const { companies, refreshCompanies, setSelectedCompanyId } = useApp();

  // Wizard state
  const { pratica, setAnalysisStep, updatePratica } = usePratica();
  const activeTab = pratica?.analysisStep ?? "anagrafiche";
  const setActiveTab = setAnalysisStep;

  // Step 1: Import
  const [importType, setImportType] = useState<"pdf" | "xbrl">("pdf");
  const [file, setFile] = useState<File | null>(null);
  // Bumped only when we programmatically clear a file input (reset / new import), to
  // force the uncontrolled <input type="file"> to remount and drop its displayed name.
  // It must NOT depend on whether a file is selected: keying on file-presence remounted
  // the input on the FIRST pick (clearing the shown name), which looked like the upload
  // failed and only "worked" on the second attempt.
  const [fileResetKey, setFileResetKey] = useState(0);
  const [fiscalYear, setFiscalYear] = useState(new Date().getFullYear());
  const [periodMonths, setPeriodMonths] = useState(9);
  const [companyMode, setCompanyMode] = useState<"new" | "existing">("new");
  const [selectedCompany, setSelectedCompany] = useState<number | null>(null);
  const [newCompanyName, setNewCompanyName] = useState("");
  const [sector, setSector] = useState(1);
  const [importing, setImporting] = useState(false);
  const [activeImportMethod, setActiveImportMethod] = useState<
    "pdf" | "pdf_ocr" | "xbrl" | null
  >(null);
  const [importResult, setImportResult] = useState<{
    companyId: number;
    companyName: string;
    ocrEngine?: string;
    ocrVersion?: string | null;
    extractionMethod?: string;
    detailLevel?: string;
    sourceDetailFields?: number;
  } | null>(null);
  const [missingRefYear, setMissingRefYear] = useState<number | null>(null);

  // Second import (historical year when infra-year PDF has only 1 column)
  const [refFile, setRefFile] = useState<File | null>(null);
  const [importingRef, setImportingRef] = useState(false);

  // Step 1b: Rettifiche (Adjustments) — one hook per FinancialYear.
  // A rettifica on EITHER year invalidates everything computed from it: the
  // comparison, the projection and the analysis. Nothing is recomputed silently
  // — the user goes back through Confronto → Proiezione. The warning fires only
  // when a projection already exists, so a first pass isn't nagged. The test
  // reads a ref, not the closure, so projectedBS stays out of the deps: listing
  // it would re-create this callback on every projection change and re-run the
  // hooks' useCallbacks.
  const invalidateDownstream = useCallback(() => {
    const hadProjection = projectedBSRef.current !== null;
    setComparison(null);
    setProjectedBS(null);
    setAnalysis(null);
    if (hadProjection) {
      toast.warning("Bilancio modificato — ricalcola la proiezione");
    }
  }, []);
  const verifica = useRettificheYear(
    importResult?.companyId ?? null,
    fiscalYear,
    periodMonths < 12 ? periodMonths : undefined,
    invalidateDownstream,
  );
  const storico = useRettificheYear(
    importResult?.companyId ?? null,
    fiscalYear - 1,
    undefined,               // full 12-month year
    invalidateDownstream,
  );

  // Read-only "Storico" column inside the Bilancio di verifica tab. Derived from
  // the storico hook so a correction on one tab moves the column on the other
  // with no refetch. Bilancio abbreviato imports populate only aggregates, so
  // reconcileSubfields plugs the gap into the "altri" sub-fields — otherwise the
  // column shows a total with every detail row empty.
  const referenceYearData = useMemo(() => {
    if (!storico.data) return null;
    const merged: Record<string, number> = {
      ...storico.data.balance_sheet,
      ...storico.data.income_statement,
    };
    reconcileSubfields(merged);
    return merged;
  }, [storico.data]);

  // Gate: entrambe le schede (storico se esiste, verifica sempre) devono
  // essere confermate prima di sbloccare gli step successivi.
  const allRettificheConfirmed = verifica.confirmed && (!storico.exists || storico.confirmed);

  // Il context è una cache; la verità è il log letto dal server. Riallinea lo
  // stepper quando i dati arrivano (mount, refresh di pagina, cambio anno).
  //
  // GUARDIA — non rimuovere: gli hook `useRettificheYear` caricano SOLO sulla
  // tab Rettifiche (vedi l'effetto poco sotto), quindi su un mount qualunque
  // (es. rientro su /pratica dallo stepper dopo essere stati su /budget)
  // `verifica`/`storico` sono ancora a `data: null, confirmed: false` mentre
  // il context ha già un `rettificheConfirmed` valido da localStorage. Senza
  // questa guardia l'effetto scriveva incondizionatamente `false` a ogni
  // mount, cancellando una conferma legittima — e da quando `blockedStep()`
  // legge la stessa cache per il render gate, questo trasformava il gate in
  // un falso blocco su Confronto/Proiezione/Indicatori/Stampa per un utente
  // che AVEVA confermato. "Risolto" = i dati sono arrivati (`data !== null`)
  // oppure il server ha risposto 404 (`!exists`, storico può non esistere).
  // Non scrivere PRIMA che l'anno sia risolto; scrivere SEMPRE una volta
  // risolto (anche `false`, es. dopo "Ripristina originale" che azzera
  // `confirmed` su un anno già caricato).
  const verificaResolved = verifica.data !== null || !verifica.exists;
  const storicoResolved = storico.data !== null || !storico.exists;
  useEffect(() => {
    if (!verificaResolved || !storicoResolved) return;
    updatePratica({
      rettificheConfirmed: {
        verifica: verifica.confirmed,
        storico: storico.exists ? storico.confirmed : true,
      },
    });
    // updatePratica è stabile; dipendere dall'oggetto verifica/storico
    // rifarebbe scattare l'effetto a ogni render (vedi CLAUDE.md, Rettifiche).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verifica.confirmed, storico.confirmed, storico.exists, verificaResolved, storicoResolved]);

  // Unica porta verso il Confronto: sia il banner "Conferma e prosegui" sia il
  // bottone del dialogo Riepilogo (onNext dell'istanza "verifica") passano di
  // qui, altrimenti si può arrivare al Confronto senza aver mai confermato le
  // rettifiche. save()/confirm() ora risalgono l'esito: su errore (rete, 500)
  // non avanziamo e non scriviamo un context che dichiara confermato un
  // marker mai persistito.
  const handleConfirmRettifiche = useCallback(async () => {
    const okVerifica = await verifica.confirm();
    if (!okVerifica) {
      // confirm() resolves false without a toast of its own (data not yet
      // loaded, or the save it wraps failed and already toasted a generic
      // message) — this is the headline control, it must never fail quietly.
      toast.error(
        "Impossibile confermare le rettifiche del bilancio di verifica. Riprova.",
      );
      return;
    }
    if (storico.exists) {
      const okStorico = await storico.confirm();
      if (!okStorico) {
        // Worst case: verifica is already confirmed and persisted server-side
        // but storico is not — tell the user plainly so they don't assume
        // nothing happened and silently proceed on a half-confirmed pratica.
        toast.error(
          "Bilancio di verifica confermato, ma le rettifiche dello storico non sono state salvate. Riprova a confermare lo storico prima di proseguire.",
        );
        return;
      }
    }
    updatePratica({ rettificheConfirmed: { verifica: true, storico: true } });
    setActiveTab("comparison");
    // verifica/storico sono oggetti nuovi a ogni render: dipendere dai singoli
    // membri usati tiene l'handler stabile senza doverlo ricreare a ogni giro.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verifica.confirm, storico.confirm, storico.exists, updatePratica, setActiveTab]);

  const rettificheDaConfermare =
    (verifica.exists && !verifica.confirmed ? 1 : 0) +
    (storico.exists && !storico.confirmed ? 1 : 0);

  // Le condizioni sono copiate INVARIATE dal bottone che questo sostituisce
  // (era app/pratica/page.tsx:4155-4167).
  const rettificheDisabled =
    verifica.saving ||
    storico.saving ||
    verifica.loading ||
    storico.loading ||
    !verifica.exists ||
    allRettificheConfirmed;

  // La registrazione unica `primary` (comprese le tab Confronto e Proiezione,
  // Task 5) vive più sotto, dopo `saveProjection12M` — da cui il case
  // "comparison" dipende — perché uno useMemo eseguito qui sopra non potrebbe
  // ancora chiudere su un `const` dichiarato più avanti nel componente
  // (temporal dead zone). Vedi la registrazione subito prima del `return`.

  // Rettifiche sub-tab (storico vs bilancio di verifica). Default to storico;
  // fall back to verifica when there is no historical year to correct.
  const [subTab, setSubTab] = useState<"storico" | "verifica">("storico");
  useEffect(() => {
    if (!storico.exists) setSubTab("verifica");
  }, [storico.exists]);

  // Step 2: Comparison
  const [scenario, setScenario] = useState<BudgetScenario | null>(null);
  const [comparison, setComparison] = useState<IntraYearComparison | null>(null);
  const [loadingComparison, setLoadingComparison] = useState(false);

  // Step 3: Projection overrides
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [projectedBS, setProjectedBS] = useState<IntraYearComparisonItem[] | null>(null);
  const projectedBSRef = useRef<IntraYearComparisonItem[] | null>(null);
  useEffect(() => {
    projectedBSRef.current = projectedBS;
  }, [projectedBS]);

  // Step 4: Results
  const [analysis, setAnalysis] = useState<ScenarioAnalysis | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [extraAlerts, setExtraAlerts] = useState<Record<string, boolean>>({});
  const [ratingVisible, setRatingVisible] = useState(false);
  const [showNoAlertsConfirm, setShowNoAlertsConfirm] = useState(false);

  // Refresh companies list on mount and when page regains focus
  useEffect(() => {
    refreshCompanies();

    const handleFocus = () => refreshCompanies();
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [refreshCompanies]);

  // Auto-select first company if needed
  useEffect(() => {
    if (companies.length > 0 && !selectedCompany) {
      setSelectedCompany(companies[0].id);
    }
  }, [companies, selectedCompany]);

  // Preseleziona l'azienda già stabilita in Anagrafiche: senza questo il
  // picker dell'Import riparte da "Nuova azienda" con nome vuoto e invita a
  // crearne un duplicato. Tenuto sullo scalare pratica?.companyId (mai
  // sull'oggetto pratica) e SENZA dipendere da selectedCompany, così vince
  // sempre sull'effetto "auto-seleziona la prima azienda" qui sopra
  // indipendentemente dall'ordine di flush, e non riparte più dopo — il
  // picker resta comunque modificabile dall'utente.
  useEffect(() => {
    if (pratica?.companyId != null) {
      setCompanyMode("existing");
      setSelectedCompany(pratica.companyId);
    }
  }, [pratica?.companyId]);

  // Riidratazione dopo refresh (F5). Il progresso del wizard vive in useState
  // locali (importResult, scenario, fiscalYear, periodMonths, …) che NON
  // sopravvivono a un refresh, mentre il context (persistito in localStorage)
  // sì. Senza questo effetto, dopo F5 lo stepper mostra uno step avanzato
  // (es. "comparison") ma loadComparison/loadAnalysis restano fermi al loro
  // guard `!importResult || !scenario` — pagina bianca, nessun errore.
  //
  // Riidratazione fedele: recupera scenario + azienda dal server e ripopola i
  // 4 stati locali; gli effetti già esistenti (auto-load Rettifiche, auto-load
  // Confronto, auto-load Analisi) fanno il resto da soli quando vedono
  // importResult/scenario valorizzati. Se il context non ha abbastanza dati
  // (companyId/infrannualeScenarioId mancanti) o la fetch fallisce, fallback
  // onesto: si torna allo step Import e si spiega perché — mai una pagina
  // bianca.
  //
  // Guardia con useRef (non solo scalari in dep-array): l'effetto deve
  // tentare la riidratazione ESATTAMENTE una volta, altrimenti un secondo
  // tentativo potrebbe partire mentre il primo è ancora in corso (dipende da
  // pratica?.analysisStep, che può cambiare per altri motivi nel frattempo).
  const rehydrationAttempted = useRef(false);
  const [rehydrationFailed, setRehydrationFailed] = useState(false);
  useEffect(() => {
    if (rehydrationAttempted.current) return;
    if (!pratica) return; // context non ancora letto da localStorage
    if (pratica.workflow !== "bilancio") return;
    if (importResult) return; // stato locale già presente, nessun refresh da recuperare

    const pastImport = pratica.analysisStep !== "anagrafiche" && pratica.analysisStep !== "import";
    if (!pastImport) return;

    if (pratica.companyId == null || pratica.infrannualeScenarioId == null) {
      rehydrationAttempted.current = true;
      setRehydrationFailed(true);
      setActiveTab("import");
      return;
    }

    rehydrationAttempted.current = true;
    const companyId = pratica.companyId;
    const infrannualeScenarioId = pratica.infrannualeScenarioId;
    (async () => {
      try {
        const [company, scenarioData] = await Promise.all([
          getCompany(companyId),
          getBudgetScenario(companyId, infrannualeScenarioId),
        ]);
        setScenario(scenarioData);
        setImportResult({ companyId, companyName: company.name });
        setFiscalYear(pratica.fiscalYear ?? scenarioData.base_year + 1);
        setPeriodMonths(pratica.periodMonths ?? scenarioData.period_months ?? 12);
      } catch {
        setRehydrationFailed(true);
        setActiveTab("import");
      }
    })();
    // Deliberatamente sugli scalari, non sull'oggetto pratica: l'effetto deve
    // tentare la riidratazione una volta sola (vedi rehydrationAttempted),
    // dipendere dall'oggetto lo rifarebbe scattare a ogni updatePratica
    // successivo (es. il salvataggio del rettificheConfirmed poco sopra).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    pratica?.workflow,
    pratica?.companyId,
    pratica?.infrannualeScenarioId,
    pratica?.analysisStep,
    pratica?.fiscalYear,
    pratica?.periodMonths,
    importResult,
    setActiveTab,
  ]);

  // Helper: create scenario and advance to comparison step
  const createScenarioAndAdvance = async (
    companyId: number,
    companyName: string,
    ocrMetadata?: {
      ocrEngine?: string;
      ocrVersion?: string | null;
      extractionMethod?: string;
      detailLevel?: string;
      sourceDetailFields?: number;
    }
  ) => {
    const refYear = fiscalYear - 1;
    const scenarioData = await createBudgetScenario(companyId, {
      company_id: companyId,
      name: `Infrannuale ${periodMonths}M ${fiscalYear}`,
      base_year: refYear,
      scenario_type: "infrannuale",
      period_months: periodMonths,
    });
    setScenario(scenarioData);
    setImportResult((previous) => ({
      companyId,
      companyName,
      ocrEngine: ocrMetadata?.ocrEngine ?? previous?.ocrEngine,
      ocrVersion: ocrMetadata?.ocrVersion ?? previous?.ocrVersion,
      extractionMethod: ocrMetadata?.extractionMethod ?? previous?.extractionMethod,
      detailLevel: ocrMetadata?.detailLevel ?? previous?.detailLevel,
      sourceDetailFields: ocrMetadata?.sourceDetailFields ?? previous?.sourceDetailFields,
    }));
    // Senza questo lo stepper non sblocca mai Confronto/Proiezione: i suoi gate
    // leggono infrannualeScenarioId dal context, non dallo state locale del
    // wizard. periodMonths va scritto per intero (anche 12) — pratica-steps.ts
    // usa il valore letterale per nascondere lo step Proiezione sul bilancio
    // annuale; normalizzarlo a undefined (come fa l'hook rettifiche) rompe quel confronto.
    updatePratica({
      companyId,
      fiscalYear,
      periodMonths,
      infrannualeScenarioId: scenarioData.id,
    });
    toast.success(`Importazione completata: ${companyName}`);
    setActiveTab("rettifiche");
  };

  // STEP 1: Import Handler (infra-year PDF/XBRL)
  const handleImport = async (
    requestedMethod: "pdf" | "pdf_ocr" | "xbrl" = importType
  ) => {
    if (!file) {
      toast.error("Seleziona un file da importare");
      return;
    }

    if (companyMode === "new" && !newCompanyName.trim()) {
      toast.error("Inserisci il nome dell'azienda");
      return;
    }

    if (companyMode === "existing" && !selectedCompany) {
      toast.error("Seleziona un'azienda");
      return;
    }

    setImporting(true);
    setActiveImportMethod(requestedMethod);
    // Clear stale rettifiche state from any previous import
    verifica.clear();
    storico.clear();
    setSubTab("storico");
    try {
      let companyId: number;
      let companyName: string;
      let ocrMetadata:
        | {
            ocrEngine?: string;
            ocrVersion?: string | null;
            extractionMethod?: string;
            detailLevel?: string;
            sourceDetailFields?: number;
          }
        | undefined;

      if (requestedMethod === "pdf" || requestedMethod === "pdf_ocr") {
        const importFn = requestedMethod === "pdf_ocr" ? importOCR : importPDF;
        const result = await importFn(
          file,
          fiscalYear,
          companyMode === "new" ? newCompanyName : undefined,
          companyMode === "existing" ? selectedCompany : undefined,
          companyMode === "new",
          companyMode === "new" ? sector : undefined,
          periodMonths
        );
        companyId = result.company_id;
        companyName = result.company_name;
        if (requestedMethod === "pdf_ocr") {
          ocrMetadata = {
            ocrEngine: result.ocr_engine,
            ocrVersion: result.ocr_version,
            extractionMethod: result.extraction_method,
            detailLevel: result.detail_level,
            sourceDetailFields: result.source_detail_fields,
          };
        }
      } else {
        const result = await importXBRL(
          file,
          companyMode === "existing" ? selectedCompany : undefined,
          companyMode === "new",
          companyMode === "new" ? sector : undefined,
          periodMonths
        );
        companyId = result.company_id;
        companyName = result.company_name;
      }

      await refreshCompanies();
      setSelectedCompanyId(companyId);
      setMissingRefYear(null);

      // Check if reference year exists (may have been imported from dual-column PDF)
      const years = await getCompanyYears(companyId);
      const refYear = fiscalYear - 1;
      if (!years.includes(refYear)) {
        setImportResult({ companyId, companyName, ...ocrMetadata });
        setMissingRefYear(refYear);
        toast.warning(
          `Dati ${fiscalYear} importati. Serve il bilancio storico ${refYear} per procedere.`
        );
        return;
      }

      await createScenarioAndAdvance(companyId, companyName, ocrMetadata);
    } catch (error: unknown) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      let fallback: string;
      if (status === 503) {
        fallback = "Il servizio OCR non è disponibile. Riprova più tardi o usa l'import PDF standard.";
      } else if (status === 504) {
        fallback = "L'OCR ha impiegato troppo tempo. Riprova con un documento più breve.";
      } else if (status === 400 || status === 422) {
        fallback = "Dati non validi. Verificare il file e l'anno fiscale.";
      } else {
        fallback = "Errore durante l'importazione";
      }
      toast.error(getErrorMessage(error, fallback));
    } finally {
      setImporting(false);
      setActiveImportMethod(null);
    }
  };

  // STEP 1b: Import reference year (historical full-year balance sheet)
  const handleImportRefYear = async () => {
    if (!refFile || !importResult || !missingRefYear) return;

    setImportingRef(true);
    try {
      await importPDF(
        refFile,
        missingRefYear,
        undefined,                  // no company name (existing company)
        importResult.companyId,     // attach to same company
        false,                      // don't create company
        undefined,                  // sector already set
        undefined                   // no period_months = full 12-month year
      );

      // Verify it worked
      const years = await getCompanyYears(importResult.companyId);
      if (!years.includes(missingRefYear)) {
        toast.error(`Importazione riuscita ma anno ${missingRefYear} non trovato`);
        return;
      }

      setMissingRefYear(null);
      await createScenarioAndAdvance(importResult.companyId, importResult.companyName);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nell'importazione del bilancio storico";
      toast.error(msg);
    } finally {
      setImportingRef(false);
    }
  };

  // STEP 1c: Proceed WITHOUT the reference year (pure-annualization mode).
  // The engine falls back to annualizing the partial year (value * 12 / months)
  // when the prior-year balance sheet is unavailable.
  const handleSkipRefYear = async () => {
    if (!importResult) return;
    setImportingRef(true);
    try {
      setMissingRefYear(null);
      await createScenarioAndAdvance(importResult.companyId, importResult.companyName);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nella creazione dello scenario";
      toast.error(msg);
    } finally {
      setImportingRef(false);
    }
  };

  // STEP 2: Load Comparison
  const loadComparison = useCallback(async () => {
    if (!importResult || !scenario) return;

    setLoadingComparison(true);
    try {
      const data = await getIntraYearComparison(importResult.companyId, scenario.id);
      setComparison(data);

      // Try to restore saved projections from existing forecast data
      let restored = false;
      try {
        const existingAnalysis = await getScenarioAnalysis(importResult.companyId, scenario.id);
        const forecastIS = existingAnalysis.forecast_years?.[0]?.income_statement;
        const forecastBS = existingAnalysis.forecast_years?.[0]?.balance_sheet;
        if (forecastIS && Object.keys(forecastIS).length > 0) {
          // Restore CE overrides from saved forecast income statement
          const saved: Record<string, string> = {};
          for (const code of EDITABLE_CE_CODES) {
            if (code in forecastIS) {
              saved[code] = Math.round(forecastIS[code]).toString();
            }
          }
          if (Object.keys(saved).length > 0) {
            setOverrides(saved);
            restored = true;
          }

          // Restore BS projection from saved forecast balance sheet
          if (forecastBS && Object.keys(forecastBS).length > 0) {
            const projItems: IntraYearComparisonItem[] = data.balance_items.map((item) => ({
              ...item,
              annualized_value: Math.round(forecastBS[item.code] ?? item.partial_value),
            }));
            setProjectedBS(buildBalanceItemsWithTotals(projItems));
          }

          setAnalysis(existingAnalysis);
        }
      } catch {
        // No existing forecast — that's fine, use defaults
      }

      if (!restored) {
        // Pre-populate overrides with annualized values (fresh scenario)
        const defaults: Record<string, string> = {};
        for (const item of data.income_items) {
          if (EDITABLE_CE_CODES.includes(item.code)) {
            defaults[item.code] = Math.round(item.annualized_value).toString();
          }
        }
        setOverrides(defaults);
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nel caricamento confronto";
      toast.error(msg);
    } finally {
      setLoadingComparison(false);
    }
  }, [importResult, scenario]);

  useEffect(() => {
    if (activeTab !== "rettifiche" || !importResult) return;
    if (!verifica.data) verifica.load();
    if (!storico.data && storico.exists) storico.load();
  }, [activeTab, importResult, verifica.data, verifica.load, storico.data, storico.exists, storico.load]);

  // Toast once per failed load attempt (tracked by fiscal year), not every
  // time the user returns to the Rettifiche step for the same missing year.
  const missingYearToastRef = useRef<number | null>(null);
  useEffect(() => {
    if (activeTab !== "rettifiche") return;
    if (!verifica.exists) {
      if (missingYearToastRef.current !== fiscalYear) {
        missingYearToastRef.current = fiscalYear;
        toast.error(
          `Dati per l'anno ${fiscalYear} non trovati. Verificare l'anno fiscale inserito.`
        );
      }
    } else {
      missingYearToastRef.current = null;
    }
  }, [activeTab, verifica.exists, fiscalYear]);

  useEffect(() => {
    // Confronto, Proiezione, Indicatori e Stampa leggono tutti `comparison` —
    // non solo la tab "comparison" stessa. Senza coprire anche le altre tre,
    // un mount (o una riidratazione dopo F5) che atterra direttamente su
    // "projection"/"results"/"stampa" non lo carica mai: quelle tab
    // aspettano per sempre un dato che nessun effect va a prendere.
    const needsComparison =
      activeTab === "comparison" ||
      activeTab === "projection" ||
      activeTab === "results" ||
      activeTab === "stampa";
    if (needsComparison && !comparison && scenario) {
      loadComparison();
    }
  }, [activeTab, comparison, scenario, loadComparison]);

  // STEP 3: Generate Projection

  // Calculate projected BS from CE overrides + historical turnover ratios,
  // then save assumptions to backend to generate forecast
  const calculateProjectedBS = async () => {
    if (!comparison || !importResult || !scenario) return;

    const refBS = new Map(comparison.balance_items.map((i) => [i.code, i]));
    const refCE = new Map(comparison.income_items.map((i) => [i.code, i]));

    const refVal = (code: string) => refBS.get(code)?.reference_value ?? 0;
    const partialVal = (code: string) => refBS.get(code)?.partial_value ?? 0;
    const refCEVal = (code: string) => refCE.get(code)?.reference_value ?? 0;
    const projCEVal = (code: string) => parseFloat(overrides[code] || "0");

    // Projected P&L values for turnover computation
    const projRevenue = projCEVal("ce01_ricavi_vendite");
    const projMaterials = projCEVal("ce05_materie_prime");
    const projServices = projCEVal("ce06_servizi");
    const projPurchases = projMaterials + projServices;

    // Compute projected net profit from overrides (same logic as ProjectionTable)
    const allCostCodes = [
      ...EBITDA_COST_CODES, "ce09_ammortamenti",
      "ce15_oneri_finanziari", "ce17b_svalutazioni", "ce19_oneri_straordinari", "ce20_imposte",
    ];
    const allIncomeCodes = [
      ...VP_CODES,
      "ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari",
      "ce16_utili_perdite_cambi", "ce17a_rivalutazioni", "ce18_proventi_straordinari",
    ];
    const projIncome = allIncomeCodes.reduce(
      (acc, c) => acc + (EDITABLE_CE_CODES.includes(c) ? projCEVal(c) : (refCE.get(c)?.annualized_value ?? 0)), 0
    );
    const projCosts = allCostCodes.reduce(
      (acc, c) => acc + (EDITABLE_CE_CODES.includes(c) ? projCEVal(c) : (refCE.get(c)?.annualized_value ?? 0)), 0
    );
    const projNetProfit = projIncome - projCosts;

    // Turnover ratios from historical (reference year = full 12 months)
    const refRevenue = refCEVal("ce01_ricavi_vendite");
    const refPurchases = refCEVal("ce05_materie_prime") + refCEVal("ce06_servizi");

    // Projected working capital items. Without a reference year there are no
    // turnover ratios, so we carry the partial-year stocks (matches the backend
    // pure-annualization mode).
    //
    // Con un anno di riferimento, il rapporto passa comunque da
    // `scaledOrCarried`: un denominatore trascurabile (AIC SRL fattura su
    // ce04 e porta ce01 = 100,92 €) genera un moltiplicatore da 10.258x che
    // gonfiava i crediti a 166,68 M. Stessa regola del backend
    // (`_turnover_ratio` in intra_year_engine.py), altrimenti lo schermo e il
    // record persistito raccontano due bilanci diversi.
    const hasRef = comparison.has_reference;
    const sp05 = hasRef && projMaterials !== 0
      ? scaledOrCarried(refVal("sp05_rimanenze"), refCEVal("ce05_materie_prime"), projMaterials, partialVal("sp05_rimanenze"))
      : partialVal("sp05_rimanenze");
    const sp06 = hasRef && projRevenue !== 0
      ? scaledOrCarried(refVal("sp06_crediti_breve"), refRevenue, projRevenue, partialVal("sp06_crediti_breve"))
      : partialVal("sp06_crediti_breve");
    let sp16 = hasRef && projPurchases !== 0
      ? scaledOrCarried(refVal("sp16_debiti_breve"), refPurchases, projPurchases, partialVal("sp16_debiti_breve"))
      : partialVal("sp16_debiti_breve");

    // Other items from infrannuale (partial year)
    const sp01 = partialVal("sp01_crediti_soci");
    const sp02 = partialVal("sp02_immob_immateriali");
    const sp03 = partialVal("sp03_immob_materiali");
    const sp04 = partialVal("sp04_immob_finanziarie");
    const sp07 = partialVal("sp07_crediti_lungo");
    const sp08 = partialVal("sp08_attivita_finanziarie");
    const sp10 = partialVal("sp10_ratei_risconti_attivi");
    const sp11 = partialVal("sp11_capitale");
    const sp12 = partialVal("sp12_riserve");
    const sp14 = partialVal("sp14_fondi_rischi");
    const sp15 = partialVal("sp15_tfr");
    const sp17 = partialVal("sp17_debiti_lungo");
    const sp18 = partialVal("sp18_ratei_risconti_passivi");

    // sp13 = projected net profit
    const sp13 = projNetProfit;

    // Cash plug: Passivo - Attivo (without cash)
    const totalAssetNoCash = sp01 + sp02 + sp03 + sp04 + sp05 + sp06 + sp07 + sp08 + sp10;
    const totalLiabilities = sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18;
    let sp09 = totalLiabilities - totalAssetNoCash;

    if (sp09 < 0) {
      // Negative cash → increase short-term debt
      sp16 = sp16 + Math.abs(sp09);
      sp09 = 0;
    }

    // Build projected items with same structure as comparison
    const projValues: Record<string, number> = {
      sp01_crediti_soci: sp01, sp02_immob_immateriali: sp02,
      sp03_immob_materiali: sp03, sp04_immob_finanziarie: sp04,
      sp05_rimanenze: sp05, sp06_crediti_breve: sp06,
      sp07_crediti_lungo: sp07, sp08_attivita_finanziarie: sp08,
      sp09_disponibilita_liquide: sp09, sp10_ratei_risconti_attivi: sp10,
      sp11_capitale: sp11, sp12_riserve: sp12, sp13_utile_perdita: sp13,
      sp14_fondi_rischi: sp14, sp15_tfr: sp15, sp16_debiti_breve: sp16,
      sp17_debiti_lungo: sp17, sp18_ratei_risconti_passivi: sp18,
    };

    const safePct = (a: number, b: number) => (b !== 0 ? (a / b) * 100 : 0);
    const projItems: IntraYearComparisonItem[] = comparison.balance_items.map((item) => ({
      ...item,
      annualized_value: Math.round(projValues[item.code] ?? partialVal(item.code)),
    }));

    setProjectedBS(buildBalanceItemsWithTotals(projItems));

    // Save assumptions to backend and generate forecast
    try {
      const refItems = comparison.income_items.reduce(
        (acc, item) => ({ ...acc, [item.code]: item.reference_value }),
        {} as Record<string, number>
      );
      const calcGrowth = (code: string): number => {
        const overrideVal = parseFloat(overrides[code] || "0");
        const refV = refItems[code] || 0;
        if (refV === 0) return 0;
        return ((overrideVal / refV) - 1) * 100;
      };

      const result = await bulkUpsertAssumptions(importResult.companyId, scenario.id, {
        assumptions: [{
          forecast_year: fiscalYear,
          revenue_growth_pct: calcGrowth("ce01_ricavi_vendite"),
          other_revenue_growth_pct: calcGrowth("ce04_altri_ricavi"),
          variable_materials_growth_pct: calcGrowth("ce05_materie_prime"),
          fixed_materials_growth_pct: calcGrowth("ce05_materie_prime"),
          variable_services_growth_pct: calcGrowth("ce06_servizi"),
          fixed_services_growth_pct: calcGrowth("ce06_servizi"),
          rent_growth_pct: calcGrowth("ce07_godimento_beni"),
          personnel_growth_pct: calcGrowth("ce08_costi_personale"),
          other_costs_growth_pct: calcGrowth("ce12_oneri_diversi"),
          ...buildCeOverridePayload(overrides),
          tax_rate: 27.9,
          fixed_materials_percentage: 40,
          fixed_services_percentage: 40,
          depreciation_rate: 20,
          depreciation_rate_intangible: 20,
          investments: 0,
          receivables_short_growth_pct: 0,
          receivables_long_growth_pct: 0,
          payables_short_growth_pct: 0,
          interest_rate_receivables: 0,
          interest_rate_payables: 0,
          financing_amount: 0,
          financing_duration_years: 0,
          financing_interest_rate: 0,
        }],
        auto_generate: true,
      });
      setAnalysis(null); // Clear stale analysis so Indicatori tab reloads
      // The backend returns success:true even when generation fails
      // (assumptions_service.py:210-217) — check the explicit flag, otherwise
      // the Indicatori tab silently renders an empty "Proiezione" column after
      // a success toast, with the real reason only in the response message.
      if (result?.forecast_generated === false) {
        toast.warning(
          result?.message ?? "Ipotesi salvate, ma la proiezione non è stata generata"
        );
      } else {
        toast.success("Proiezione calcolata e salvata");
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nel salvataggio proiezione";
      toast.error(msg);
    }
  };

  // Auto-save projection with 0% growth for 12M infrannuale (no annualization needed)
  const saveProjection12M = async () => {
    if (!comparison || !importResult || !scenario) return;

    // Pre-fill overrides from comparison partial values (= full year when 12M)
    const defaults: Record<string, string> = {};
    for (const item of comparison.income_items) {
      if (EDITABLE_CE_CODES.includes(item.code)) {
        defaults[item.code] = Math.round(item.partial_value).toString();
      }
    }
    setOverrides(defaults);
    const effectiveOverrides = Object.keys(overrides).length > 0 ? overrides : defaults;

    // Set projectedBS from comparison balance items (already full-year values)
    const projItems: IntraYearComparisonItem[] = comparison.balance_items.map((item) => ({
      ...item,
      annualized_value: item.partial_value,
    }));
    setProjectedBS(buildBalanceItemsWithTotals(projItems));

    // Calculate growth rates from imported 12M values vs reference year
    try {
      const refItems = comparison.income_items.reduce(
        (acc, item) => ({ ...acc, [item.code]: item.reference_value }),
        {} as Record<string, number>
      );
      const calcGrowth = (code: string): number => {
        const importedVal = comparison.income_items.find(i => i.code === code)?.partial_value ?? 0;
        const refV = refItems[code] || 0;
        if (refV === 0) return 0;
        return ((importedVal / refV) - 1) * 100;
      };

      const result = await bulkUpsertAssumptions(importResult.companyId, scenario.id, {
        assumptions: [{
          forecast_year: fiscalYear,
          revenue_growth_pct: calcGrowth("ce01_ricavi_vendite"),
          other_revenue_growth_pct: calcGrowth("ce04_altri_ricavi"),
          variable_materials_growth_pct: calcGrowth("ce05_materie_prime"),
          fixed_materials_growth_pct: calcGrowth("ce05_materie_prime"),
          variable_services_growth_pct: calcGrowth("ce06_servizi"),
          fixed_services_growth_pct: calcGrowth("ce06_servizi"),
          rent_growth_pct: calcGrowth("ce07_godimento_beni"),
          personnel_growth_pct: calcGrowth("ce08_costi_personale"),
          other_costs_growth_pct: calcGrowth("ce12_oneri_diversi"),
          ...buildCeOverridePayload(effectiveOverrides),
          sp_overrides: Object.fromEntries(
            comparison.balance_items
              .filter((item) => item.code.startsWith("sp"))
              .map((item) => [item.code, item.partial_value])
          ),
          tax_rate: 27.9,
          fixed_materials_percentage: 40,
          fixed_services_percentage: 40,
          depreciation_rate: 20,
          depreciation_rate_intangible: 20,
          investments: 0,
          receivables_short_growth_pct: 0,
          receivables_long_growth_pct: 0,
          payables_short_growth_pct: 0,
          interest_rate_receivables: 0,
          interest_rate_payables: 0,
          financing_amount: 0,
          financing_duration_years: 0,
          financing_interest_rate: 0,
        }],
        auto_generate: true,
      });
      setAnalysis(null); // Clear stale analysis so Indicatori tab reloads
      // Same silent-failure guard as calculateProjectedBS above.
      if (result?.forecast_generated === false) {
        toast.warning(
          result?.message ?? "Ipotesi salvate, ma la proiezione non è stata generata"
        );
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nel salvataggio proiezione";
      toast.error(msg);
    }
  };

  // STEP 4: Load Analysis
  const loadAnalysis = useCallback(async () => {
    if (!importResult || !scenario) return;

    setLoadingAnalysis(true);
    try {
      const data = await getScenarioAnalysis(importResult.companyId, scenario.id);
      setAnalysis(data);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nel caricamento analisi";
      toast.error(msg);
    } finally {
      setLoadingAnalysis(false);
    }
  }, [importResult, scenario]);

  useEffect(() => {
    if ((activeTab === "results" || activeTab === "stampa") && !analysis && scenario) {
      loadAnalysis();
    }
  }, [activeTab, analysis, scenario, loadAnalysis]);

  const goFromComparison = useCallback(async () => {
    if (periodMonths === 12) {
      await saveProjection12M();
      setActiveTab("results");
    } else {
      setActiveTab("projection");
    }
  }, [periodMonths, saveProjection12M, setActiveTab]);

  // Unica registrazione per tutte le tab: `null` lascia il fallback di
  // navigazione alla barra (Import, Indicatori) o l'azione al componente
  // figlio (Stampa → StampaContent).
  const primary = useMemo<{
    label: string | null;
    onClick: () => void | Promise<void>;
    disabled: boolean;
    reason: string | null;
  }>(() => {
    switch (activeTab) {
      case "rettifiche":
        // Già confermate: l'azione diventa navigazione, altrimenti il primario
        // resterebbe disabilitato per sempre (vedi la nota in fondo al passo).
        if (allRettificheConfirmed) {
          return {
            label: "Vai al Confronto",
            onClick: () => setActiveTab("comparison"),
            disabled: false,
            reason: null,
          };
        }
        return {
          label: "Conferma e vai al Confronto",
          onClick: handleConfirmRettifiche,
          disabled: rettificheDisabled,
          reason: !verifica.exists
            ? "Bilancio di verifica non caricato"
            : verifica.saving || storico.saving
            ? "Salvataggio in corso"
            : verifica.loading || storico.loading
            ? "Caricamento in corso"
            : null,
        };
      case "comparison":
        return {
          label: periodMonths === 12 ? "Vai agli Indicatori" : "Vai alla Proiezione",
          onClick: goFromComparison,
          disabled: !comparison,
          reason: !comparison ? "Confronto non ancora caricato" : null,
        };
      case "projection":
        // Un solo primario che calcola E avanza: se la proiezione non è
        // ancora stata calcolata la calcola, poi passa agli Indicatori. Il
        // bottone secondario "Calcola Proiezione SP" nell'header della card
        // resta per il ricalcolo manuale dopo una modifica agli override.
        return {
          label: "Calcola e vai agli Indicatori",
          onClick: async () => {
            if (!projectedBS) await calculateProjectedBS();
            setActiveTab("results");
          },
          disabled: !comparison,
          reason: !comparison ? "Confronto non ancora caricato" : null,
        };
      case "results":
        // A 12 mesi non esiste uno step Proiezione (vedi buildPraticaSteps):
        // lì projectedBS non è un prerequisito per passare alla Stampa.
        return {
          label: "Vai alla Stampa",
          onClick: () => setActiveTab("stampa"),
          disabled: !projectedBS && periodMonths !== 12,
          reason: !projectedBS && periodMonths !== 12 ? "Proiezione non calcolata" : null,
        };
      default:
        return { label: null, onClick: () => {}, disabled: false, reason: null };
    }
  }, [
    activeTab,
    setActiveTab,
    handleConfirmRettifiche,
    rettificheDisabled,
    allRettificheConfirmed,
    verifica.exists,
    verifica.saving,
    verifica.loading,
    storico.saving,
    storico.loading,
    periodMonths,
    comparison,
    projectedBS,
    goFromComparison,
    calculateProjectedBS,
  ]);

  // Difesa in profondità: i rami `activeTab === …` qui sotto non consultano i
  // gate del percorso. Vedi blockedStep() in lib/pratica-steps.ts per cosa
  // questo controllo copre e cosa deliberatamente non copre.
  const blocked = useMemo(() => blockedStep(pratica, activeTab), [pratica, activeTab]);

  usePrimaryAction(primary);

  return (
    <>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {rehydrationFailed && (
          <Alert variant="destructive" className="mb-6">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Pratica da riaprire</AlertTitle>
            <AlertDescription>
              Il progresso di questa pratica non è stato ritrovato dopo l&apos;aggiornamento
              della pagina. Riparti dall&apos;importazione oppure riapri la pratica dalla
              home.
            </AlertDescription>
          </Alert>
        )}

        {blocked && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <AlertTriangle className="h-5 w-5" /> Passaggio non ancora raggiungibile
              </CardTitle>
              <CardDescription>
                {blocked.reason ?? "Completa prima i passaggi precedenti."}
              </CardDescription>
            </CardHeader>
            {blocked.back && (
              <CardContent>
                <Button
                  onClick={() => {
                    if (blocked.back) setActiveTab(blocked.back.id);
                  }}
                >
                  Torna a {blocked.back.label}
                </Button>
              </CardContent>
            )}
          </Card>
        )}

        {!blocked && (<>

        {/* STEP 0: ANAGRAFICHE */}
        {activeTab === "anagrafiche" && (
          <AnagraficheStep
            onReady={(companyId) => {
              updatePratica({ companyId });
              setActiveTab("import");
            }}
          />
        )}

        {/* STEP 1: IMPORT */}
        {activeTab === "import" && <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Importa Bilancio Infrannuale</CardTitle>
              <CardDescription>
                Carica il bilancio parziale (es. situazione al 30/09/2025)
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Import Type */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Tipo di file</Label>
                  <Select
                    value={importType}
                    onValueChange={(v) => setImportType(v as "pdf" | "xbrl")}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pdf">PDF</SelectItem>
                      <SelectItem value="xbrl">XBRL</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>File</Label>
                  <Input
                    key={`main-file-${fileResetKey}`}
                    type="file"
                    accept={importType === "xbrl" ? ".xbrl,.XBRL,.xml,.XML" : ".pdf,.PDF"}
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                  />
                </div>
              </div>

              {/* Period */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Anno fiscale</Label>
                  <Input
                    type="number"
                    value={fiscalYear}
                    onChange={(e) => setFiscalYear(parseInt(e.target.value) || 2025)}
                    min={2000}
                    max={2100}
                  />
                </div>
                <div>
                  <Label>Periodo (mesi coperti)</Label>
                  <Select
                    value={periodMonths.toString()}
                    onValueChange={(v) => setPeriodMonths(parseInt(v))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(MONTH_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Company */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Azienda</Label>
                  <Select
                    value={companyMode}
                    onValueChange={(v) => setCompanyMode(v as "new" | "existing")}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="existing">Azienda esistente</SelectItem>
                      <SelectItem value="new">Nuova azienda</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {companyMode === "existing" ? (
                  <div>
                    <Label>Seleziona azienda</Label>
                    <Select
                      value={selectedCompany?.toString() || ""}
                      onValueChange={(v) => setSelectedCompany(parseInt(v))}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Seleziona..." />
                      </SelectTrigger>
                      <SelectContent>
                        {companies.map((c) => (
                          <SelectItem key={c.id} value={c.id.toString()}>
                            {c.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ) : (
                  <div>
                    <Label>Nome azienda</Label>
                    <Input
                      value={newCompanyName}
                      onChange={(e) => setNewCompanyName(e.target.value)}
                      placeholder="Ragione sociale"
                    />
                  </div>
                )}
              </div>

              {companyMode === "new" && (
                <div className="w-1/2">
                  <Label>Settore</Label>
                  <Select
                    value={sector.toString()}
                    onValueChange={(v) => setSector(parseInt(v))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(SECTOR_OPTIONS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {value}. {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {importResult && missingRefYear ? (
                <div className="space-y-4">
                  <div className="p-4 rounded-lg bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800">
                    <div className="flex items-center gap-2">
                      <Check className="h-5 w-5 text-green-600 dark:text-green-400" />
                      <p className="font-medium text-green-800 dark:text-green-300">
                        Dati infrannuali {fiscalYear} importati per {importResult.companyName}
                      </p>
                    </div>
                    {importResult.ocrEngine && (
                      <p className="mt-2 text-sm text-green-700 dark:text-green-400">
                        OCR {importResult.ocrEngine}
                        {importResult.ocrVersion ? ` ${importResult.ocrVersion}` : ""}
                        {importResult.extractionMethod ? ` · ${importResult.extractionMethod}` : ""}
                        {importResult.detailLevel ? ` · dettaglio ${importResult.detailLevel}` : ""}
                        {typeof importResult.sourceDetailFields === "number"
                          ? ` (${importResult.sourceDetailFields} campi dalla fonte)`
                          : ""}
                      </p>
                    )}
                  </div>
                  <div className="p-4 rounded-lg bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800">
                    <div className="flex items-center gap-2">
                      <Upload className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
                      <p className="font-medium text-yellow-800 dark:text-yellow-300">
                        Serve il bilancio storico {missingRefYear}
                      </p>
                    </div>
                    <p className="text-sm text-yellow-700 dark:text-yellow-400 mt-2">
                      Il PDF infrannuale non conteneva i dati dell&apos;anno precedente.
                      Carica il bilancio completo {missingRefYear} per un confronto storico
                      completo, oppure prosegui senza: la proiezione verrà calcolata per
                      pura annualizzazione del periodo (valore × 12 / mesi).
                    </p>
                    <div className="flex items-center gap-3 mt-4">
                      <Input
                        key={`ref-file-${fileResetKey}`}
                        type="file"
                        accept=".pdf"
                        className="flex-1"
                        onChange={(e) => setRefFile(e.target.files?.[0] || null)}
                      />
                      <Button
                        onClick={handleImportRefYear}
                        disabled={importingRef || !refFile}
                      >
                        {importingRef ? (
                          <>
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            Importazione...
                          </>
                        ) : (
                          <>
                            <Upload className="h-4 w-4 mr-2" />
                            Importa {missingRefYear}
                          </>
                        )}
                      </Button>
                    </div>
                    <div className="mt-3">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-yellow-800 dark:text-yellow-300"
                        onClick={handleSkipRefYear}
                        disabled={importingRef}
                      >
                        <ArrowRight className="h-4 w-4 mr-2" />
                        Prosegui senza l&apos;anno precedente (solo annualizzazione)
                      </Button>
                    </div>
                  </div>
                </div>
              ) : importResult && scenario ? (
                <div className="p-4 rounded-lg bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800">
                  <div className="flex items-center gap-2">
                    <Check className="h-5 w-5 text-green-600 dark:text-green-400" />
                    <p className="font-medium text-green-800 dark:text-green-300">
                      Importazione completata: {importResult.companyName}
                    </p>
                  </div>
                  {importResult.ocrEngine && (
                    <p className="mt-2 text-sm text-green-700 dark:text-green-400">
                      OCR {importResult.ocrEngine}
                      {importResult.ocrVersion ? ` ${importResult.ocrVersion}` : ""}
                      {importResult.extractionMethod ? ` · ${importResult.extractionMethod}` : ""}
                      {importResult.detailLevel ? ` · dettaglio ${importResult.detailLevel}` : ""}
                      {typeof importResult.sourceDetailFields === "number"
                        ? ` (${importResult.sourceDetailFields} campi dalla fonte)`
                        : ""}
                    </p>
                  )}
                </div>
              ) : (
                <div className="flex flex-wrap justify-end gap-3">
                  {importType === "pdf" ? (
                    /* Il pulsante ImportOCR (MinerU) non si rende: l'endpoint
                       /import/pdf-ocr non e' pronto e MinerU non e' distribuito sul
                       VPS (profilo compose, mai in produzione). Il percorso resta
                       vivo lato client - importOCR e handleImport("pdf_ocr") non
                       sono stati rimossi - cosi' riesporlo e' rimettere il pulsante,
                       non riscrivere il ramo. */
                    <Button
                      onClick={() => handleImport("pdf")}
                      disabled={importing || !file}
                    >
                      {activeImportMethod === "pdf" ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <Upload className="h-4 w-4 mr-2" />
                      )}
                      {activeImportMethod === "pdf"
                        ? "Importazione..."
                        : "Importa e Continua"}
                    </Button>
                  ) : (
                    <Button
                      onClick={() => handleImport("xbrl")}
                      disabled={importing || !file}
                    >
                      {activeImportMethod === "xbrl" ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <Upload className="h-4 w-4 mr-2" />
                      )}
                      {activeImportMethod === "xbrl"
                        ? "Importazione XBRL..."
                        : "Importa XBRL e Continua"}
                    </Button>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>}

        {/* STEP 1b: RETTIFICHE */}
        {activeTab === "rettifiche" && <>
        <Tabs value={subTab} onValueChange={(v) => setSubTab(v as "storico" | "verifica")} className="space-y-4">
          <TabsList>
            <TabsTrigger value="storico" disabled={!storico.exists}>
              Rettifiche Storico {fiscalYear - 1}
            </TabsTrigger>
            <TabsTrigger value="verifica">
              Rettifiche Bil. di verifica {periodMonths < 12 ? `${periodMonths}M ` : ""}{fiscalYear}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="storico">
            {storico.exists ? (
              <RettificheTab
                adjustableData={storico.data}
                referenceYearData={null}
                referenceYear={fiscalYear - 2}
                periodMonths={12}
                fiscalYear={fiscalYear - 1}
                corrections={storico.corrections}
                setCorrections={storico.setCorrections}
                loading={storico.loading}
                saving={storico.saving}
                adjustmentsApplied={storico.applied}
                onSave={storico.save}
                onReset={storico.reset}
                onNext={() => setSubTab("verifica")}
              />
            ) : (
              <Card>
                <CardContent className="py-12 text-center text-muted-foreground">
                  Nessun bilancio storico caricato per il {fiscalYear - 1}. La proiezione
                  gira in annualizzazione pura sui dati del periodo.
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="verifica">
            {verifica.exists ? (
              <RettificheTab
                adjustableData={verifica.data}
                referenceYearData={referenceYearData}
                referenceYear={fiscalYear - 1}
                periodMonths={periodMonths}
                fiscalYear={fiscalYear}
                corrections={verifica.corrections}
                setCorrections={verifica.setCorrections}
                loading={verifica.loading}
                saving={verifica.saving}
                adjustmentsApplied={verifica.applied}
                onSave={verifica.save}
                onReset={verifica.reset}
                onNext={handleConfirmRettifiche}
              />
            ) : (
              <Card>
                <CardContent className="py-12 text-center text-muted-foreground">
                  Dati per il bilancio di verifica {periodMonths < 12 ? `${periodMonths}M ` : ""}
                  {fiscalYear} non trovati. Verificare l&apos;anno fiscale e il periodo (mesi
                  coperti) inseriti nella scheda Importazione.
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>

        <div className="mt-6 rounded-lg border border-border bg-card p-4">
          <p className="text-sm text-muted-foreground">
            {allRettificheConfirmed
              ? "Rettifiche confermate. Puoi proseguire con il confronto."
              : `Conferma le rettifiche per sbloccare gli step successivi (${rettificheDaConfermare} ${
                  rettificheDaConfermare === 1 ? "scheda" : "schede"
                } da confermare). Se il bilancio non quadra puoi confermare lo stesso: l'avviso resta.`}
          </p>
        </div>
        </>}

        {/* STEP 2: COMPARISON */}
        {activeTab === "comparison" && <div className="space-y-6">
          {loadingComparison ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
                <p className="mt-2 text-muted-foreground">Caricamento confronto...</p>
              </CardContent>
            </Card>
          ) : comparison ? (
            <>
              {!comparison.has_reference && (
                <div className="p-4 rounded-lg bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800">
                  <p className="text-sm text-blue-800 dark:text-blue-300">
                    <strong>Modalità annualizzazione pura:</strong> nessun bilancio
                    storico {comparison.reference_year} disponibile. La proiezione 12 mesi
                    è ottenuta annualizzando il periodo (valore × 12 / {comparison.period_months})
                    e le colonne di confronto con l&apos;anno precedente non sono disponibili.
                  </p>
                </div>
              )}
              {/* Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {["ce01_ricavi_vendite", "ce08_costi_personale", "ce05_materie_prime", "ce06_servizi"].map(
                  (code) => {
                    const item = comparison.income_items.find((i) => i.code === code);
                    if (!item) return null;
                    const expectedPct = (comparison.period_months / 12) * 100;
                    const isAbove = item.pct_of_reference > expectedPct;
                    return (
                      <Card key={code}>
                        <CardContent className="pt-4">
                          <p className="text-xs text-muted-foreground truncate">
                            {item.label}
                          </p>
                          <p className="text-lg font-bold">
                            {formatEuro(item.partial_value)}
                          </p>
                          {comparison.has_reference ? (
                            <div className="flex items-center gap-1 mt-1">
                              {isAbove ? (
                                <TrendingUp className="h-3 w-3 text-green-600 dark:text-green-400" />
                              ) : (
                                <TrendingDown className="h-3 w-3 text-red-600 dark:text-red-400" />
                              )}
                              <span
                                className={`text-xs ${
                                  isAbove
                                    ? "text-green-600 dark:text-green-400"
                                    : "text-red-600 dark:text-red-400"
                                }`}
                              >
                                {formatPct(item.pct_of_reference)} vs storico
                              </span>
                            </div>
                          ) : (
                            <p className="text-xs text-muted-foreground mt-1">
                              annualizzato: {formatEuro(item.annualized_value)}
                            </p>
                          )}
                        </CardContent>
                      </Card>
                    );
                  }
                )}
              </div>

              {/* P&L Comparison Table */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    {comparison.has_reference
                      ? `Conto Economico - Confronto ${comparison.period_months}M ${comparison.partial_year} vs 12M ${comparison.reference_year}`
                      : `Conto Economico - ${comparison.period_months}M ${comparison.partial_year} → annualizzato 12M`}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ComparisonTable
                    items={buildIncomeItemsWithEbitda(comparison.income_items, comparison.period_months)}
                    periodMonths={comparison.period_months}
                    referenceYear={comparison.reference_year}
                    partialYear={comparison.partial_year}
                    priorYear={comparison.prior_year}
                    showAnnualized={periodMonths !== 12}
                    showRevenuePct
                  />
                </CardContent>
              </Card>

              {/* BS Comparison Table */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Stato Patrimoniale - Confronto
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ComparisonTable
                    items={buildBalanceItemsWithTotals(comparison.balance_items)}
                    periodMonths={comparison.period_months}
                    referenceYear={comparison.reference_year}
                    partialYear={comparison.partial_year}
                    priorYear={comparison.prior_year}
                    showAnnualized={false}
                  />
                </CardContent>
              </Card>
            </>
          ) : null}
        </div>}

        {/* STEP 3: PROJECTION */}
        {activeTab === "projection" && <div className="space-y-6">
          {loadingComparison ? (
          <Card>
            <CardContent className="py-12 text-center">
              <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
              <p className="mt-2 text-muted-foreground">Caricamento confronto...</p>
            </CardContent>
          </Card>
          ) : comparison ? (
          <>
          {/* P&L Projection */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Conto Economico - Proiezione {fiscalYear}
              </CardTitle>
              <CardDescription>
                I valori Proiezione sono modificabili. Pre-compilati con
                annualizzazione ({periodMonths}M → 12M).
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ProjectionTable
                items={buildIncomeItemsWithEbitda(comparison.income_items, comparison.period_months)}
                periodMonths={comparison.period_months}
                referenceYear={comparison.reference_year}
                partialYear={comparison.partial_year}
                showRevenuePct
                overrides={overrides}
                onOverrideChange={(code, value) => {
                  setOverrides((prev) => ({ ...prev, [code]: value }));
                  setProjectedBS(null); // Recalculate needed
                }}
              />
            </CardContent>
          </Card>

          {/* BS Projection */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <div>
                <CardTitle className="text-base">
                  Stato Patrimoniale - Proiezione {fiscalYear}
                </CardTitle>
                <CardDescription>
                  Crediti, debiti e rimanenze calcolati con stessi giorni di rotazione dello storico.
                  Liquidità come differenza.
                </CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={calculateProjectedBS}>
                <BarChart3 className="h-4 w-4 mr-2" />
                Calcola Proiezione SP
              </Button>
            </CardHeader>
            <CardContent>
              <ComparisonTable
                items={projectedBS ?? buildBalanceItemsWithTotals(
                  comparison.balance_items.map((i) => ({ ...i, annualized_value: NaN }))
                )}
                periodMonths={comparison.period_months}
                referenceYear={comparison.reference_year}
                partialYear={comparison.partial_year}
                priorYear={comparison.prior_year}
                showAnnualized
              />
            </CardContent>
          </Card>
          </>
          ) : (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-muted-foreground">
                Completa prima il Confronto nel passaggio 2.
              </p>
            </CardContent>
          </Card>
          )}
        </div>}

        {/* STEP 4: INDICATORI */}
        {activeTab === "results" && <div className="space-y-6">
          {loadingAnalysis ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
                <p className="mt-2 text-muted-foreground">Caricamento indicatori...</p>
              </CardContent>
            </Card>
          ) : analysis && comparison ? (
            <>
              <ExtraAccountingAlerts alerts={extraAlerts} onChange={(a) => { setExtraAlerts(a); setRatingVisible(false); }} />

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Indicatori Finanziari</CardTitle>
                  <CardDescription>
                    {periodMonths === 12
                      ? `Confronto: storico ${comparison.reference_year}, infrannuale 12M ${comparison.partial_year}`
                      : `Confronto: storico ${comparison.reference_year}, infrannuale ${comparison.period_months}M ${comparison.partial_year} (annualizzato), proiezione 12M ${comparison.partial_year}`}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <IndicatoriTable
                    comparison={comparison}
                    forecastBs={analysis.forecast_years?.[0]?.balance_sheet || {}}
                    forecastIs={analysis.forecast_years?.[0]?.income_statement || {}}
                    extraAlerts={extraAlerts}
                    showRating={ratingVisible}
                    hideProiezione={periodMonths === 12}
                  />
                </CardContent>
              </Card>

              {!ratingVisible && (
                <div className="flex justify-center">
                  <AlertDialog open={showNoAlertsConfirm} onOpenChange={setShowNoAlertsConfirm}>
                    <AlertDialogTrigger asChild>
                      <Button onClick={() => {
                        const hasAlerts = Object.values(extraAlerts).some(Boolean);
                        if (hasAlerts) {
                          setRatingVisible(true);
                        } else {
                          setShowNoAlertsConfirm(true);
                        }
                      }}>
                        <BarChart3 className="h-4 w-4 mr-2" />
                        Calcola Rating
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Segnali Extracontabili</AlertDialogTitle>
                        <AlertDialogDescription>
                          Conferma che non ci sono segnali extra contabili della crisi
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Annulla</AlertDialogCancel>
                        <AlertDialogAction onClick={() => { setShowNoAlertsConfirm(false); setRatingVisible(true); }}>
                          Conferma
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              )}
            </>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <p className="text-muted-foreground">
                  Genera prima la proiezione nel passaggio 3.
                </p>
              </CardContent>
            </Card>
          )}
        </div>}

        {/* STEP 5: STAMPA */}
        {activeTab === "stampa" && <div className="space-y-6">
          {loadingAnalysis ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
                <p className="mt-2 text-muted-foreground">Caricamento dati...</p>
              </CardContent>
            </Card>
          ) : analysis && comparison && (projectedBS || periodMonths === 12) ? (
            <StampaContent
              comparison={comparison}
              overrides={overrides}
              projectedBS={projectedBS ?? buildBalanceItemsWithTotals(
                comparison.balance_items.map((i) => ({ ...i, annualized_value: i.partial_value }))
              )}
              forecastBs={analysis.forecast_years?.[0]?.balance_sheet || {}}
              forecastIs={analysis.forecast_years?.[0]?.income_statement || {}}
              extraAlerts={extraAlerts}
              companyName={importResult?.companyName || ""}
              fiscalYear={fiscalYear}
              periodMonths={periodMonths}
              companyId={importResult?.companyId}
              scenarioId={scenario?.id}
              onBeforePromote={periodMonths === 12 ? saveProjection12M : undefined}
            />
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <p className="text-muted-foreground">
                  Completa prima i passaggi precedenti.
                </p>
              </CardContent>
            </Card>
          )}
        </div>}

        </>)}

      </div>
    </>
  );
}

