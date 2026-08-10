"use client";

import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { useAuth } from "@/contexts/AuthContext";
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
  getBudgetScenarios,
  bulkUpsertAssumptions,
  getIntraYearComparison,
  getScenarioAnalysis,
  promoteProjection,
  getInfrannualeAIComments,
  generateInfrannualeAIComments,
  saveInfrannualeAIComments,
  type InfrannualeAIComments,
} from "@/lib/api";
import { useRettificheYear } from "@/hooks/use-rettifiche-year";
import { blockedStep } from "@/lib/pratica-steps";
import type {
  BudgetScenario,
  IntraYearComparison,
  IntraYearComparisonItem,
  ScenarioAnalysis,
  AdjustableFinancialYear,
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
  Printer,
  Trash2,
  TrendingUp,
  TrendingDown,
  RotateCcw,
  Sparkles,
  AlertTriangle,
} from "lucide-react";
import { cn, getErrorMessage } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  BarChart as RechartsBarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
} from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { AnagraficheStep } from "@/components/pratica/AnagraficheStep";
import { RettificheTab } from "@/components/pratica/RettificheTab";
import {
  MONTH_LABELS,
  SECTOR_OPTIONS,
  formatEuro,
  formatPct,
  formatInputNumber,
  parseInputNumber,
} from "@/lib/pratica-format";
import {
  EDITABLE_CE_CODES,
  CE_OVERRIDE_FIELD_BY_CODE,
  buildCeOverridePayload,
  KEY_BS_CODES,
  VP_CODES,
  EBITDA_COST_CODES,
  ALWAYS_SHOW_CODES,
  ATTIVO_CODES,
  PASSIVO_CODES,
  DETAIL_PARENTS,
  EXTRA_ALERT_DEFS,
} from "@/lib/pratica-codes";
import { reconcileSubfields } from "@/lib/pratica-reconcile";
import {
  safeDivide,
  linearScore,
  invertedScore,
  computeIndicators,
  scoreIndicator,
  INDICATOR_DEFS,
  scoreDotColor,
  computeCrisisRating,
  type IndicatorSet,
} from "@/lib/pratica-indicators";
import {
  buildBalanceItemsWithTotals,
  buildIncomeItemsWithEbitda,
} from "@/lib/pratica-statement-rows";

const economicIncidenceChartConfig = {
  ebitda_margin: { label: "EBITDA / Ricavi", color: "hsl(var(--chart-2))" },
  materials_revenue: { label: "Materie / Ricavi", color: "hsl(var(--chart-3))" },
  services_revenue: { label: "Servizi / Ricavi", color: "hsl(var(--chart-4))" },
} satisfies ChartConfig;

const financialMarginsChartConfig = {
  mt: { label: "Margine di Tesoreria", color: "hsl(var(--chart-1))" },
  ms: { label: "Margine di Struttura", color: "hsl(var(--chart-2))" },
  pfn: { label: "PFN", color: "hsl(var(--chart-5))" },
} satisfies ChartConfig;

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
    reconcileSubfields,
    invalidateDownstream,
  );
  const storico = useRettificheYear(
    importResult?.companyId ?? null,
    fiscalYear - 1,
    undefined,               // full 12-month year
    reconcileSubfields,
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
  useEffect(() => {
    updatePratica({
      rettificheConfirmed: {
        verifica: verifica.confirmed,
        storico: storico.exists ? storico.confirmed : true,
      },
    });
    // updatePratica è stabile; dipendere dall'oggetto verifica/storico
    // rifarebbe scattare l'effetto a ogni render (vedi CLAUDE.md, Rettifiche).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verifica.confirmed, storico.confirmed, storico.exists]);

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

    // Turnover days from historical (reference year = full 12 months)
    const refRevenue = refCEVal("ce01_ricavi_vendite");
    const refPurchases = refCEVal("ce05_materie_prime") + refCEVal("ce06_servizi");

    const receivableDays = refRevenue !== 0 ? (refVal("sp06_crediti_breve") / refRevenue) * 365 : 0;
    const inventoryDays = refCEVal("ce05_materie_prime") !== 0
      ? (refVal("sp05_rimanenze") / refCEVal("ce05_materie_prime")) * 365 : 0;
    const payableDays = refPurchases !== 0 ? (refVal("sp16_debiti_breve") / refPurchases) * 365 : 0;

    // Projected working capital items. Without a reference year there are no
    // turnover ratios, so we carry the partial-year stocks (matches the backend
    // pure-annualization mode).
    const hasRef = comparison.has_reference;
    const sp05 = hasRef && projMaterials !== 0 ? projMaterials * inventoryDays / 365 : partialVal("sp05_rimanenze");
    const sp06 = hasRef && projRevenue !== 0 ? projRevenue * receivableDays / 365 : partialVal("sp06_crediti_breve");
    let sp16 = hasRef && projPurchases !== 0 ? projPurchases * payableDays / 365 : partialVal("sp16_debiti_breve");

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
                    <>
                      <Button
                        variant="outline"
                        onClick={() => handleImport("pdf")}
                        disabled={importing || !file}
                      >
                        {activeImportMethod === "pdf" ? (
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <Upload className="h-4 w-4 mr-2" />
                        )}
                        {activeImportMethod === "pdf"
                          ? "Importazione standard..."
                          : "Importa standard e Continua"}
                      </Button>
                      <Button
                        onClick={() => handleImport("pdf_ocr")}
                        disabled={importing || !file}
                      >
                        {activeImportMethod === "pdf_ocr" ? (
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <Upload className="h-4 w-4 mr-2" />
                        )}
                        {activeImportMethod === "pdf_ocr"
                          ? "Estrazione MinerU e analisi contabile..."
                          : "ImportOCR (MinerU) e Continua"}
                      </Button>
                    </>
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

// Comparison Table Component
function ComparisonTable({
  items,
  periodMonths,
  referenceYear,
  partialYear,
  priorYear,
  showAnnualized,
  showRevenuePct = false,
}: {
  items: IntraYearComparisonItem[];
  periodMonths: number;
  referenceYear: number;
  partialYear: number;
  priorYear: number | null;
  showAnnualized: boolean;
  showRevenuePct?: boolean;
}) {
  const expectedPct = (periodMonths / 12) * 100;
  const hasPriorYear = priorYear != null && items.some((i) => i.prior_value !== 0);

  // Revenue values for % computation
  const partialRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.partial_value ?? 0)
    : 0;
  const refRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.reference_value ?? 0)
    : 0;
  const priorRevenue = showRevenuePct && hasPriorYear
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.prior_value ?? 0)
    : 0;

  const pctOnRevenue = (value: number, revenue: number) =>
    revenue !== 0 ? (value / revenue) * 100 : 0;

  // Column date labels
  const priorDate = priorYear ? `31/12/${priorYear}` : "";
  const refDate = `31/12/${referenceYear}`;
  const lastDay = new Date(partialYear, periodMonths, 0).getDate();
  const partialDate = `${lastDay}/${String(periodMonths).padStart(2, "0")}/${partialYear}`;
  const projDate = `31/12/${partialYear}`;

  // Revenue for annualized % computation
  const annualizedRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.annualized_value ?? 0)
    : 0;

  // Column spans for group headers
  const colSpan = showRevenuePct ? 2 : 1;

  return (
    <Table>
      <TableHeader>
        {/* Row 1: Category labels */}
        <TableRow className="border-b-0">
          <TableHead rowSpan={2} className="align-bottom">Voce</TableHead>
          {hasPriorYear && (
            <TableHead colSpan={colSpan} className="text-center pb-0 text-muted-foreground text-xs font-normal">
              Storico
            </TableHead>
          )}
          <TableHead colSpan={colSpan} className="text-center pb-0 text-muted-foreground text-xs font-normal">
            Storico
          </TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-xs font-normal">
            Infrannuale
          </TableHead>
          {showAnnualized && (
            <TableHead colSpan={colSpan} className="text-center pb-0 text-xs font-normal">
              Proiezione
            </TableHead>
          )}
          <TableHead className="text-center pb-0 text-muted-foreground text-xs font-normal">
            {showAnnualized ? "Proiezione / Storico" : "Infrannuale / Storico"}
          </TableHead>
        </TableRow>
        {/* Row 2: Dates */}
        <TableRow>
          {hasPriorYear && (
            <TableHead className="text-right text-xs font-semibold">{priorDate}</TableHead>
          )}
          {hasPriorYear && showRevenuePct && (
            <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>
          )}
          <TableHead className="text-right text-xs font-semibold">{refDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          <TableHead className="text-right text-xs font-semibold">{partialDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          {showAnnualized && (
            <TableHead className="text-right text-xs font-semibold">{projDate}</TableHead>
          )}
          {showAnnualized && showRevenuePct && (
            <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>
          )}
          <TableHead className="text-right text-xs font-semibold">delta %</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items
          .filter(
            (item) =>
              ALWAYS_SHOW_CODES.has(item.code) ||
              item.partial_value !== 0 ||
              item.reference_value !== 0 ||
              item.prior_value !== 0
          )
          .map((item) => {
            const isHeader = item.code.startsWith("_hdr_");
            const isSubtotal = ["_totale_vp", "_totale_cp", "_totale_fin", "_totale_straord",
              "_ebitda", "_ebit", "_profit_before_tax", "_net_profit",
              "_totale_attivo", "_totale_passivo",
              "_totale_immob", "_totale_circ", "_totale_pn", "_totale_debiti", "_differenza"].includes(item.code);
            const isPctRow = item.code === "_ebitda_pct";
            const isDetail = item.code in DETAIL_PARENTS;

            // Section headers: bold label spanning all columns
            if (isHeader) {
              // Count total columns: 1 (label) + [colSpan (prior)] + colSpan (ref) + colSpan (partial) + [colSpan (ann)] + 1 (delta)
              const totalCols = 1 + (hasPriorYear ? colSpan : 0) + colSpan + colSpan + (showAnnualized ? colSpan : 0) + 1;
              return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={totalCols} className="text-sm font-bold py-2">
                    {item.label}
                  </TableCell>
                </TableRow>
              );
            }

            return (
              <TableRow
                key={item.code}
                className={cn(
                  isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10",
                )}
              >
                <TableCell className={cn(
                  "text-sm",
                  isSubtotal ? "font-semibold" : isDetail ? "pl-6 text-muted-foreground font-normal" : "font-medium",
                )}>
                  {item.label}
                </TableCell>
                {/* Prior year (anno precedente) */}
                {hasPriorYear && (
                  <TableCell className="text-right text-sm text-muted-foreground">
                    {isPctRow ? formatPct(item.prior_value) : formatEuro(item.prior_value)}
                  </TableCell>
                )}
                {hasPriorYear && showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.prior_value, priorRevenue))}
                  </TableCell>
                )}
                {/* Reference (historical) */}
                <TableCell className="text-right text-sm text-muted-foreground">
                  {isPctRow ? formatPct(item.reference_value) : formatEuro(item.reference_value)}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.reference_value, refRevenue))}
                  </TableCell>
                )}
                {/* Partial (infrannuale) */}
                <TableCell className="text-right text-sm">
                  {isPctRow ? formatPct(item.partial_value) : formatEuro(item.partial_value)}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.partial_value, partialRevenue))}
                  </TableCell>
                )}
                {showAnnualized && (
                  <TableCell className="text-right text-sm font-medium">
                    {isNaN(item.annualized_value) ? (
                      <span className="text-muted-foreground">-</span>
                    ) : isPctRow ? "-" : formatEuro(item.annualized_value)}
                  </TableCell>
                )}
                {showAnnualized && showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && !isNaN(item.annualized_value) && formatPct(pctOnRevenue(item.annualized_value, annualizedRevenue))}
                  </TableCell>
                )}
                {(() => {
                  const compareValue = showAnnualized ? item.annualized_value : item.partial_value;
                  if (isNaN(compareValue)) {
                    return <TableCell className="text-right text-sm text-muted-foreground">-</TableCell>;
                  }
                  const delta = item.reference_value !== 0
                    ? ((compareValue - item.reference_value) / Math.abs(item.reference_value)) * 100
                    : 0;
                  const isPositive = delta > 1;
                  const isNegative = delta < -1;
                  return (
                    <TableCell className="text-right text-sm">
                      {isPctRow ? (
                        <span className="text-muted-foreground">-</span>
                      ) : (
                        <span
                          className={
                            isPositive
                              ? "text-green-600 dark:text-green-400"
                              : isNegative
                              ? "text-red-600 dark:text-red-400"
                              : "text-muted-foreground"
                          }
                        >
                          {delta > 0 ? "+" : ""}{formatPct(delta)}
                        </span>
                      )}
                    </TableCell>
                  );
                })()}
              </TableRow>
            );
          })}
      </TableBody>
    </Table>
  );
}

// Projection Table Component (same layout as ComparisonTable but with editable Proiezione)
function ProjectionTable({
  items,
  periodMonths,
  referenceYear,
  partialYear,
  showRevenuePct = false,
  overrides,
  onOverrideChange,
}: {
  items: IntraYearComparisonItem[];
  periodMonths: number;
  referenceYear: number;
  partialYear: number;
  showRevenuePct?: boolean;
  overrides: Record<string, string>;
  onOverrideChange: (code: string, value: string) => void;
}) {
  const refDate = `31/12/${referenceYear}`;
  const lastDay = new Date(partialYear, periodMonths, 0).getDate();
  const partialDate = `${lastDay}/${String(periodMonths).padStart(2, "0")}/${partialYear}`;
  const projDate = `31/12/${partialYear}`;

  // Revenue values for % computation
  const refRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.reference_value ?? 0)
    : 0;
  const partialRevenue = showRevenuePct
    ? (items.find((i) => i.code === "ce01_ricavi_vendite")?.partial_value ?? 0)
    : 0;

  const pctOnRevenue = (value: number, revenue: number) =>
    revenue !== 0 ? (value / revenue) * 100 : 0;

  // Get projected value: override if editable, annualized otherwise
  const getProjectedValue = (item: IntraYearComparisonItem): number => {
    if (EDITABLE_CE_CODES.includes(item.code)) {
      return parseFloat(overrides[item.code] || "0");
    }
    return item.annualized_value;
  };

  // Compute projected revenue for % column
  const projRevenue = showRevenuePct
    ? parseFloat(overrides["ce01_ricavi_vendite"] || "0")
    : 0;

  // Helper: get projected value for a CE code (override if editable, annualized otherwise)
  const pv = (code: string): number =>
    EDITABLE_CE_CODES.includes(code)
      ? parseFloat(overrides[code] || "0")
      : (items.find((i) => i.code === code)?.annualized_value ?? 0);

  // Compute projected subtotals from overrides
  const projVP = VP_CODES.reduce((acc, c) => acc + pv(c), 0);
  const PROJ_COST_CODES_ALL = ["ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
    "ce08_costi_personale", "ce09_ammortamenti", "ce10_var_rimanenze_mat_prime",
    "ce11_accantonamenti", "ce11b_altri_accantonamenti", "ce12_oneri_diversi"];
  const projCP = PROJ_COST_CODES_ALL.reduce((acc, c) => acc + pv(c), 0);
  const projEbitda = projVP - (projCP - pv("ce09_ammortamenti"));
  const projEbit = projVP - projCP;

  const projFin = ["ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari", "ce16_utili_perdite_cambi"].reduce((acc, c) => acc + pv(c), 0)
    - pv("ce15_oneri_finanziari");
  // ce17 is an aggregate (rivalutazioni - svalutazioni); derive from its sub-fields so overrides apply
  const projRettifiche = pv("ce17a_rivalutazioni") - pv("ce17b_svalutazioni");
  const projStraord = pv("ce18_proventi_straordinari") - pv("ce19_oneri_straordinari");
  const projPBT = projEbit + projFin + projRettifiche + projStraord;
  const projNetProfit = projPBT - pv("ce20_imposte");

  const colSpan = showRevenuePct ? 2 : 1;

  return (
    <Table>
      <TableHeader>
        {/* Row 1: Category labels */}
        <TableRow className="border-b-0">
          <TableHead rowSpan={2} className="align-bottom">Voce</TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-muted-foreground text-xs font-normal">
            Storico
          </TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-xs font-normal">
            Infrannuale
          </TableHead>
          <TableHead colSpan={colSpan} className="text-center pb-0 text-xs font-normal">
            Proiezione
          </TableHead>
          <TableHead className="text-center pb-0 text-muted-foreground text-xs font-normal">
            Proiezione / Storico
          </TableHead>
        </TableRow>
        {/* Row 2: Dates */}
        <TableRow>
          <TableHead className="text-right text-xs font-semibold">{refDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          <TableHead className="text-right text-xs font-semibold">{partialDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          <TableHead className="text-right text-xs font-semibold">{projDate}</TableHead>
          {showRevenuePct && <TableHead className="text-right text-xs text-muted-foreground w-14">%</TableHead>}
          <TableHead className="text-right text-xs font-semibold">delta %</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items
          .filter(
            (item) =>
              ALWAYS_SHOW_CODES.has(item.code) ||
              item.partial_value !== 0 ||
              item.reference_value !== 0 ||
              item.prior_value !== 0
          )
          .map((item) => {
            const isHeader = item.code.startsWith("_hdr_");
            const isSubtotal = ["_totale_vp", "_totale_cp", "_totale_fin", "_totale_straord",
              "_ebitda", "_ebit", "_profit_before_tax", "_net_profit"].includes(item.code);
            const isPctRow = item.code === "_ebitda_pct";
            const isEditable = EDITABLE_CE_CODES.includes(item.code);
            const isDetail = item.code in DETAIL_PARENTS;

            // Section headers
            if (isHeader) {
              const totalCols = 1 + colSpan + colSpan + colSpan + 1;
              return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={totalCols} className="text-sm font-bold py-2">
                    {item.label}
                  </TableCell>
                </TableRow>
              );
            }

            // Projected value: from overrides for editable, computed for synthetic rows
            let projValue: number;
            if (item.code === "_totale_vp") projValue = projVP;
            else if (item.code === "_totale_cp") projValue = projCP;
            else if (item.code === "_ebitda") projValue = projEbitda;
            else if (item.code === "_ebit") projValue = projEbit;
            else if (item.code === "_totale_fin") projValue = projFin;
            else if (item.code === "_totale_straord") projValue = projStraord;
            else if (item.code === "_profit_before_tax") projValue = projPBT;
            else if (item.code === "_net_profit") projValue = projNetProfit;
            else projValue = getProjectedValue(item);

            const delta = item.reference_value !== 0
              ? ((projValue - item.reference_value) / Math.abs(item.reference_value)) * 100
              : 0;
            const isPositive = delta > 1;
            const isNegative = delta < -1;

            return (
              <TableRow
                key={item.code}
                className={cn(
                  isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10",
                )}
              >
                <TableCell className={cn(
                  "text-sm",
                  isSubtotal ? "font-semibold" : isDetail ? "pl-6 text-muted-foreground font-normal" : "font-medium",
                )}>
                  {item.label}
                </TableCell>
                {/* Reference (historical) */}
                <TableCell className="text-right text-sm text-muted-foreground">
                  {isPctRow ? formatPct(item.reference_value) : formatEuro(item.reference_value)}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.reference_value, refRevenue))}
                  </TableCell>
                )}
                {/* Partial (infrannuale) */}
                <TableCell className="text-right text-sm">
                  {isPctRow ? formatPct(item.partial_value) : formatEuro(item.partial_value)}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(item.partial_value, partialRevenue))}
                  </TableCell>
                )}
                {/* Projection (editable for CE items, computed for totals) */}
                <TableCell className="text-right text-sm">
                  {isEditable ? (
                    <Input
                      type="text"
                      inputMode="numeric"
                      className="w-32 ml-auto text-right h-8 text-sm"
                      value={formatInputNumber(overrides[item.code] || "")}
                      onChange={(e) => onOverrideChange(item.code, parseInputNumber(e.target.value))}
                    />
                  ) : isPctRow ? (
                    formatPct(projValue)
                  ) : (
                    <span className="font-medium">{formatEuro(projValue)}</span>
                  )}
                </TableCell>
                {showRevenuePct && (
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {!isPctRow && formatPct(pctOnRevenue(projValue, projRevenue))}
                  </TableCell>
                )}
                {/* Delta % */}
                <TableCell className="text-right text-sm">
                  {isPctRow ? (
                    <span className="text-muted-foreground">-</span>
                  ) : (
                    <span
                      className={
                        isPositive
                          ? "text-green-600 dark:text-green-400"
                          : isNegative
                          ? "text-red-600 dark:text-red-400"
                          : "text-muted-foreground"
                      }
                    >
                      {delta > 0 ? "+" : ""}{formatPct(delta)}
                    </span>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
      </TableBody>
    </Table>
  );
}

function ExtraAccountingAlerts({
  alerts,
  onChange,
}: {
  alerts: Record<string, boolean>;
  onChange: (alerts: Record<string, boolean>) => void;
}) {
  const activeCount = Object.values(alerts).filter(Boolean).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Segnali Extracontabili</CardTitle>
        <CardDescription>
          Indicatori di allerta ai sensi del D.Lgs. 14/2019 (Codice della Crisi).
          Selezionare le condizioni riscontrate.
          {activeCount > 0 && (
            <span className="ml-2 text-red-600 dark:text-red-400 font-medium">
              {activeCount} segnale{activeCount > 1 ? "i" : ""} attivo{activeCount > 1 ? "i" : ""}
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {EXTRA_ALERT_DEFS.map((def, idx) => (
            <div key={def.key} className="flex items-start gap-3">
              <Checkbox
                id={`alert-${def.key}`}
                checked={!!alerts[def.key]}
                onCheckedChange={(checked) =>
                  onChange({ ...alerts, [def.key]: !!checked })
                }
                className="mt-0.5"
              />
              <label
                htmlFor={`alert-${def.key}`}
                className="text-sm leading-relaxed cursor-pointer"
              >
                <span className="font-medium text-muted-foreground">{idx + 1}.</span>{" "}
                {def.label}
              </label>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// Indicatori Table Component
function IndicatoriTable({
  comparison,
  forecastBs,
  forecastIs,
  extraAlerts,
  showRating = true,
  hideProiezione = false,
}: {
  comparison: IntraYearComparison;
  forecastBs: Record<string, number>;
  forecastIs: Record<string, number>;
  extraAlerts: Record<string, boolean>;
  showRating?: boolean;
  hideProiezione?: boolean;
}) {
  // Build data maps from comparison
  const storicoBs: Record<string, number> = {};
  const storicoIs: Record<string, number> = {};
  for (const item of comparison.balance_items) {
    storicoBs[item.code] = item.reference_value;
  }
  for (const item of comparison.income_items) {
    storicoIs[item.code] = item.reference_value;
  }

  // Infrannuale: BS point-in-time, IS annualized
  const infraBs: Record<string, number> = {};
  const infraIs: Record<string, number> = {};
  const annFactor = 12 / comparison.period_months;
  for (const item of comparison.balance_items) {
    infraBs[item.code] = item.partial_value;
  }
  for (const item of comparison.income_items) {
    infraIs[item.code] = item.partial_value * annFactor;
  }

  const storicoInd = computeIndicators(storicoBs, storicoIs);
  const infraInd = computeIndicators(infraBs, infraIs);

  // Check if projection data exists (forecastBs/Is are {} when forecast_years is empty)
  const hasProiezione = Object.keys(forecastBs).length > 0 && Object.keys(forecastIs).length > 0;
  const proiezioneInd = hasProiezione ? computeIndicators(forecastBs, forecastIs) : null;

  const formatIndicatorValue = (value: number, format: "euro" | "pct" | "ratio") => {
    if (format === "euro") return formatEuro(value);
    if (format === "pct") return formatPct(value);
    return `${value.toFixed(2)}x`;
  };

  // Compute scores for each column
  const storicoScores = INDICATOR_DEFS.map((d) => scoreIndicator(d.key, storicoInd));
  const infraScores = INDICATOR_DEFS.map((d) => scoreIndicator(d.key, infraInd));
  const proiezioneScores = proiezioneInd
    ? INDICATOR_DEFS.map((d) => scoreIndicator(d.key, proiezioneInd))
    : null;

  const alertCount = Object.values(extraAlerts).filter(Boolean).length;

  // Crisis ratings: storico uses 0 alerts (historical), infra+proiezione include current alerts
  const storicoRating = computeCrisisRating(storicoScores, 0);
  const infraRating = computeCrisisRating(infraScores, alertCount);
  const proiezioneRating = proiezioneScores
    ? computeCrisisRating(proiezioneScores, alertCount)
    : null;

  const oltreCount = (scores: number[]) => scores.filter((s) => s < 0.33).length;
  const indicatorChartData = [
    { periodo: `Storico ${comparison.reference_year}`, ...storicoInd },
    { periodo: `Infrann. ${comparison.period_months}M`, ...infraInd },
    ...(!hideProiezione && proiezioneInd
      ? [{ periodo: `Proiezione ${comparison.partial_year}`, ...proiezioneInd }]
      : []),
  ];

  return (
    <div className="space-y-4">
      {/* Overall Rating Cards - only shown after "Calcola Rating" */}
      {showRating && (
        <div className={cn("grid gap-4", hideProiezione ? "grid-cols-2" : "grid-cols-3")}>
          {[
            { label: `Storico ${comparison.reference_year}`, rating: storicoRating, oltre: oltreCount(storicoScores), alerts: 0 },
            { label: `Infrann. ${comparison.period_months}M ${comparison.partial_year}`, rating: infraRating, oltre: oltreCount(infraScores), alerts: alertCount },
            ...(!hideProiezione ? [{
              label: `Proiezione ${comparison.partial_year}`,
              rating: proiezioneRating,
              oltre: proiezioneScores ? oltreCount(proiezioneScores) : null,
              alerts: alertCount,
            }] : []),
          ].map((col) => (
            <div key={col.label} className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <p className="text-xs text-muted-foreground">{col.label}</p>
                {col.rating ? (
                  <p className={cn("text-2xl font-bold", col.rating.color)}>
                    {col.rating.code}
                  </p>
                ) : (
                  <p className="text-2xl font-bold text-muted-foreground">—</p>
                )}
              </div>
              <div className="text-right">
                {col.rating ? (
                  <>
                    <p className={cn("text-sm font-medium", col.rating.color)}>
                      {col.rating.label}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {col.oltre}/14 oltre{col.alerts > 0 ? ` + ${col.alerts} segn.` : ""}
                    </p>
                  </>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Genera proiezione
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Incidenza economica sui ricavi</CardTitle>
            <CardDescription>EBITDA, materie prime e servizi in percentuale dei ricavi.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={economicIncidenceChartConfig} className="h-[260px] w-full">
              <RechartsBarChart data={indicatorChartData}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="periodo" tickLine={false} axisLine={false} />
                <YAxis tickFormatter={(value) => `${value}%`} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="ebitda_margin" fill="var(--color-ebitda_margin)" radius={3} />
                <Bar dataKey="materials_revenue" fill="var(--color-materials_revenue)" radius={3} />
                <Bar dataKey="services_revenue" fill="var(--color-services_revenue)" radius={3} />
              </RechartsBarChart>
            </ChartContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Equilibrio finanziario e strutturale</CardTitle>
            <CardDescription>Margine di tesoreria, margine di struttura e PFN.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={financialMarginsChartConfig} className="h-[260px] w-full">
              <RechartsBarChart data={indicatorChartData}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="periodo" tickLine={false} axisLine={false} />
                <YAxis tickFormatter={(value) => new Intl.NumberFormat("it-IT", { notation: "compact" }).format(value)} />
                <ChartTooltip
                  content={<ChartTooltipContent formatter={(value) => formatEuro(Number(value))} />}
                />
                <Bar dataKey="mt" fill="var(--color-mt)" radius={3} />
                <Bar dataKey="ms" fill="var(--color-ms)" radius={3} />
                <Bar dataKey="pfn" fill="var(--color-pfn)" radius={3} />
              </RechartsBarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>

      {/* Indicator Detail Table */}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Indicatore</TableHead>
            <TableHead className="text-right">
              Storico {comparison.reference_year}
            </TableHead>
            <TableHead className="text-right">
              Infrann. {comparison.period_months}M {comparison.partial_year}
            </TableHead>
            {!hideProiezione && (
              <TableHead className="text-right">
                Proiezione {comparison.partial_year}
              </TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {INDICATOR_DEFS.map((def, idx) => {
            const sv = storicoInd[def.key];
            const iv = infraInd[def.key];
            const ss = storicoScores[idx];
            const is_ = infraScores[idx];

            return (
              <TableRow key={def.key}>
                <TableCell className="font-medium">{def.label}</TableCell>
                <TableCell className="text-right">
                  <span className="inline-flex items-center gap-2">
                    <span className="text-muted-foreground">
                      {formatIndicatorValue(sv, def.format)}
                    </span>
                    {showRating && <span className={cn("inline-block h-2.5 w-2.5 rounded-full", scoreDotColor(ss))} />}
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  <span className="inline-flex items-center gap-2">
                    <span>{formatIndicatorValue(iv, def.format)}</span>
                    {showRating && <span className={cn("inline-block h-2.5 w-2.5 rounded-full", scoreDotColor(is_))} />}
                  </span>
                </TableCell>
                {!hideProiezione && (
                  <TableCell className="text-right">
                    {proiezioneInd && proiezioneScores ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="font-medium">
                          {formatIndicatorValue(proiezioneInd[def.key], def.format)}
                        </span>
                        {showRating && <span className={cn("inline-block h-2.5 w-2.5 rounded-full", scoreDotColor(proiezioneScores[idx]))} />}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// Print-ready view for PDF generation via Playwright
function StampaContent({
  comparison,
  overrides,
  projectedBS,
  forecastBs,
  forecastIs,
  extraAlerts,
  companyName,
  fiscalYear,
  periodMonths,
  companyId,
  scenarioId,
  onBeforePromote,
}: {
  comparison: IntraYearComparison;
  overrides: Record<string, string>;
  projectedBS: IntraYearComparisonItem[];
  forecastBs: Record<string, number>;
  forecastIs: Record<string, number>;
  extraAlerts: Record<string, boolean>;
  companyName: string;
  fiscalYear: number;
  periodMonths: number;
  companyId?: number;
  scenarioId?: number;
  onBeforePromote?: () => Promise<void>;
}) {
  const router = useRouter();
  const { refreshCompanies, refreshYears } = useApp();
  const { logoUrl, userName } = useAuth();
  const { updatePratica } = usePratica();
  const [promoting, setPromoting] = useState(false);
  const [aiComments, setAiComments] = useState<InfrannualeAIComments>({});
  const [aiCommentsLoading, setAiCommentsLoading] = useState(false);
  const refYear = comparison.reference_year;
  const partialYear = comparison.partial_year;
  const annFactor = 12 / periodMonths;

  // Load stored AI comments on mount / scenario change
  useEffect(() => {
    if (!companyId || !scenarioId) return;
    let cancelled = false;
    getInfrannualeAIComments(companyId, scenarioId)
      .then((data) => { if (!cancelled) setAiComments(data); })
      .catch(() => { if (!cancelled) setAiComments({}); });
    return () => { cancelled = true; };
  }, [companyId, scenarioId]);

  const handleCommentChange = (key: keyof InfrannualeAIComments, value: string) => {
    setAiComments((prev) => ({ ...prev, [key]: value }));
  };
  const handleCommentBlur = async () => {
    if (!companyId || !scenarioId) return;
    try {
      await saveInfrannualeAIComments(companyId, scenarioId, aiComments);
    } catch {
      toast.error("Errore nel salvataggio del commento");
    }
  };

  // --- P&L data ---
  const incomeItems = buildIncomeItemsWithEbitda(comparison.income_items, periodMonths);
  const projCEVal = (code: string) => parseFloat(overrides[code] || "0");

  // Helper: get projected value for a CE code
  const spv = (code: string): number =>
    EDITABLE_CE_CODES.includes(code)
      ? projCEVal(code)
      : (comparison.income_items.find(i => i.code === code)?.annualized_value ?? 0);

  const projVP = VP_CODES.reduce((acc, c) => acc + spv(c), 0);
  const STAMPA_COST_CODES = ["ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
    "ce08_costi_personale", "ce09_ammortamenti", "ce10_var_rimanenze_mat_prime",
    "ce11_accantonamenti", "ce12_oneri_diversi"];
  const projCP = STAMPA_COST_CODES.reduce((acc, c) => acc + spv(c), 0);
  const projEbitda = projVP - (projCP - spv("ce09_ammortamenti"));
  const projEbit = projVP - projCP;
  const projRevenue = projCEVal("ce01_ricavi_vendite");

  const projFin = ["ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari", "ce16_utili_perdite_cambi"].reduce((acc, c) => acc + spv(c), 0)
    - spv("ce15_oneri_finanziari");
  const projRettifiche = spv("ce17_rettifiche_attivita_fin");
  const projStraord = spv("ce18_proventi_straordinari") - spv("ce19_oneri_straordinari");
  const projPBT = projEbit + projFin + projRettifiche + projStraord;
  const projNetProfit = projPBT - spv("ce20_imposte");

  const getProjectedCE = (item: IntraYearComparisonItem): number => {
    if (item.code === "_totale_vp") return projVP;
    if (item.code === "_totale_cp") return projCP;
    if (item.code === "_ebitda") return projEbitda;
    if (item.code === "_ebit") return projEbit;
    if (item.code === "_totale_fin") return projFin;
    if (item.code === "_totale_straord") return projStraord;
    if (item.code === "_profit_before_tax") return projPBT;
    if (item.code === "_net_profit") return projNetProfit;
    if (EDITABLE_CE_CODES.includes(item.code)) return projCEVal(item.code);
    return item.annualized_value;
  };

  // --- BS data ---
  const balanceItems = buildBalanceItemsWithTotals(comparison.balance_items);
  const projBSMap = new Map(projectedBS.map(i => [i.code, i.annualized_value]));

  // --- Indicators ---
  const storicoBs: Record<string, number> = {};
  const storicoIs: Record<string, number> = {};
  for (const item of comparison.balance_items) storicoBs[item.code] = item.reference_value;
  for (const item of comparison.income_items) storicoIs[item.code] = item.reference_value;

  const infraBs: Record<string, number> = {};
  const infraIs: Record<string, number> = {};
  for (const item of comparison.balance_items) infraBs[item.code] = item.partial_value;
  for (const item of comparison.income_items) infraIs[item.code] = item.partial_value * annFactor;

  const storicoInd = computeIndicators(storicoBs, storicoIs);
  const infraInd = computeIndicators(infraBs, infraIs);
  const proiezioneInd = computeIndicators(forecastBs, forecastIs);

  const storicoScores = INDICATOR_DEFS.map(d => scoreIndicator(d.key, storicoInd));
  const infraScores = INDICATOR_DEFS.map(d => scoreIndicator(d.key, infraInd));
  const proiezioneScores = INDICATOR_DEFS.map(d => scoreIndicator(d.key, proiezioneInd));

  const alertCount = Object.values(extraAlerts).filter(Boolean).length;
  const storicoRating = computeCrisisRating(storicoScores, 0);
  const infraRating = computeCrisisRating(infraScores, alertCount);
  const proiezioneRating = computeCrisisRating(proiezioneScores, alertCount);

  const oltreCount = (scores: number[]) => scores.filter(s => s < 0.33).length;

  const formatInd = (value: number, format: "euro" | "pct" | "ratio") => {
    if (format === "euro") return formatEuro(value);
    if (format === "pct") return formatPct(value);
    return `${value.toFixed(2)}x`;
  };

  // Helper: delta % between two values
  const deltaFmt = (proj: number, ref: number) => {
    if (ref === 0) return <span className="text-muted-foreground">-</span>;
    const d = ((proj - ref) / Math.abs(ref)) * 100;
    return (
      <span className={d > 1 ? "text-green-600 dark:text-green-400" : d < -1 ? "text-red-600 dark:text-red-400" : "text-muted-foreground"}>
        {d > 0 ? "+" : ""}{formatPct(d)}
      </span>
    );
  };

  // Filter for visible rows
  const visibleIncome = incomeItems.filter(item => ALWAYS_SHOW_CODES.has(item.code) || item.partial_value !== 0 || item.reference_value !== 0);
  const visibleBalance = balanceItems.filter(item => ALWAYS_SHOW_CODES.has(item.code) || item.partial_value !== 0 || item.reference_value !== 0);

  // Build context payload for the AI generator
  const buildAICtx = (): Record<string, unknown> => {
    const income_map: Record<string, { reference_value: number; partial_value: number; annualized_value: number; projected_value: number }> = {};
    for (const it of incomeItems) {
      income_map[it.code] = {
        reference_value: it.reference_value ?? 0,
        partial_value: it.partial_value ?? 0,
        annualized_value: it.annualized_value ?? 0,
        projected_value: getProjectedCE(it),
      };
    }
    const balance_map: Record<string, { reference_value: number; partial_value: number; projected_value: number }> = {};
    for (const it of balanceItems) {
      balance_map[it.code] = {
        reference_value: it.reference_value ?? 0,
        partial_value: it.partial_value ?? 0,
        projected_value: projBSMap.get(it.code) ?? 0,
      };
    }
    const indicatorsRow = (ind: ReturnType<typeof computeIndicators>) => ({
      DSCR: ind.dscr.toFixed(2),
      EBITDA_margin_pct: ind.ebitda_margin.toFixed(1),
      current_ratio: ind.current_ratio.toFixed(2),
      ROI_pct: ind.roi.toFixed(1),
      ROE_pct: ind.roe.toFixed(1),
      ROS_pct: ind.ros.toFixed(1),
      indipendenza_fin_pct: ind.indipendenza.toFixed(1),
      PFN_EBITDA: ind.pfn_ebitda.toFixed(2),
      OF_MOL_pct: ind.of_mol.toFixed(1),
    });
    const ratingRow = (rating: ReturnType<typeof computeCrisisRating>, scores: number[], alerts: number) => ({
      code: rating.code,
      label: rating.label,
      oltre_count: scores.filter((s) => s < 0.33).length,
      alerts,
    });
    return {
      scenario: { name: "Infrannuale", company_name: companyName },
      reference_year: refYear,
      partial_year: partialYear,
      period_months: periodMonths,
      income_map,
      balance_map,
      indicators: {
        Storico: indicatorsRow(storicoInd),
        Infrannuale: indicatorsRow(infraInd),
        Proiezione: indicatorsRow(proiezioneInd),
      },
      ratings: {
        Storico: ratingRow(storicoRating, storicoScores, 0),
        Infrannuale: ratingRow(infraRating, infraScores, alertCount),
        Proiezione: ratingRow(proiezioneRating, proiezioneScores, alertCount),
      },
    };
  };

  const handleGenerateAIComments = async () => {
    if (!companyId || !scenarioId) return;
    setAiCommentsLoading(true);
    try {
      const data = await generateInfrannualeAIComments(companyId, scenarioId, buildAICtx());
      if (Object.keys(data).length === 0) {
        toast.info("Nessun commento generato (chiave API mancante?)");
      } else {
        setAiComments(data);
        toast.success("Commenti AI generati");
      }
    } catch {
      toast.error("Errore nella generazione dei commenti AI");
    } finally {
      setAiCommentsLoading(false);
    }
  };

  const CommentBlock = ({ k, placeholder }: { k: keyof InfrannualeAIComments; placeholder: string }) => {
    const value = aiComments[k] ?? "";
    // Hide empty blocks when printing to keep the PDF clean
    return (
      <div className={cn("rounded-md border border-border/60 bg-muted/20 p-3 my-2 print:my-1 print:p-2", !value && "print:hidden")}>
        {/* Screen: editable textarea */}
        <Textarea
          value={value}
          onChange={(e) => handleCommentChange(k, e.target.value)}
          onBlur={handleCommentBlur}
          placeholder={placeholder}
          className="min-h-[60px] resize-y text-sm bg-transparent border-0 focus-visible:ring-1 print:hidden"
        />
        {/* Print: plain text (no textarea chrome, no resize handle) */}
        {value && (
          <p className="hidden print:block text-xs leading-relaxed whitespace-pre-wrap m-0">{value}</p>
        )}
      </div>
    );
  };

  const handlePromote = useCallback(async () => {
    if (!companyId || !scenarioId) return;
    setPromoting(true);
    try {
      const isAnnual = periodMonths === 12;
      let baseYear: number;
      if (isAnnual) {
        // L'anno importato è già un FinancialYear completo: riscriverlo
        // con una copia ricalcolata dal motore sarebbe un rischio inutile.
        baseYear = fiscalYear;
      } else {
        if (onBeforePromote) await onBeforePromote();
        await promoteProjection(companyId, scenarioId);
        baseYear = fiscalYear;
      }

      // Riuso, non duplicazione: doppio click o ritorno sui propri passi
      // non devono generare due scenari budget per lo stesso anno base.
      const existing = await getBudgetScenarios(companyId);
      const reusable = existing.find(
        (s) => s.scenario_type !== "infrannuale" && s.base_year === baseYear,
      );
      const budget =
        reusable ??
        (await createBudgetScenario(companyId, {
          company_id: companyId,
          name: `Budget ${baseYear + 1}–${baseYear + 3}`,
          base_year: baseYear,
          scenario_type: "budget",
        }));

      updatePratica({ budgetScenarioId: budget.id });
      await refreshCompanies();
      await refreshYears();
      toast.success(
        reusable
          ? "Scenario budget esistente riaperto"
          : "Scenario budget creato",
      );
      router.push("/budget");
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, "Errore nel passaggio al budget"));
    } finally {
      setPromoting(false);
    }
  }, [
    companyId,
    scenarioId,
    periodMonths,
    fiscalYear,
    onBeforePromote,
    updatePratica,
    refreshCompanies,
    refreshYears,
    router,
  ]);

  // Il bottone era reso solo dentro `{companyId && scenarioId && (…)}`
  // (app/pratica/page.tsx:5595): la condizione si conserva come label null.
  // `companyId`/`scenarioId` sono tipati `number | undefined` (mai `null`,
  // vedi le prop qui sopra), quindi il confronto usa `!= null` — che copre
  // sia `undefined` sia `null` — invece di `!== null` come nella bozza del
  // brief, che con `undefined` risulterebbe sempre vera.
  usePrimaryAction({
    label: companyId != null && scenarioId != null ? "Prosegui al Budget" : null,
    onClick: handlePromote,
    disabled: promoting,
    reason: promoting ? "Creazione dello scenario budget in corso" : null,
  });

  return (
    <div id="stampa-content" className="space-y-8 print:space-y-3 bg-white dark:bg-slate-950 -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8 -mt-8 pt-8 pb-8">
      {/* Action buttons */}
      <div className="flex justify-end gap-2 print:hidden">
        {companyId && scenarioId && (
          <Button variant="outline" onClick={handleGenerateAIComments} disabled={aiCommentsLoading}>
            {aiCommentsLoading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4 mr-2" />
            )}
            Genera commenti AI
          </Button>
        )}
        <Button onClick={() => window.print()} variant="outline">
          <Printer className="h-4 w-4 mr-2" />
          Stampa PDF
        </Button>
      </div>

      {/* Header */}
      <div className="relative print:mb-4">
        {/* Upper-left: consulting firm branding */}
        {(logoUrl || userName) && (
          <div className="absolute left-0 top-0 flex items-center gap-2 max-w-[45%]">
            {logoUrl && (
              <img
                src={logoUrl}
                alt="Logo"
                className="h-10 w-auto object-contain print:h-8"
              />
            )}
            {userName && (
              <span className="text-xs font-medium text-muted-foreground leading-tight">
                {userName}
              </span>
            )}
          </div>
        )}

        {/* Centered title block */}
        <div className="text-center space-y-1 pt-12 print:pt-10">
          <h1 className="text-3xl font-bold print:text-2xl">
            Analisi Infrannuale / Consuntivo {periodMonths === 12 ? "" : `${periodMonths}M `}{partialYear}{periodMonths !== 12 ? ` — Proiezione 12M ${partialYear}` : ""}
          </h1>
          <p className="text-lg font-semibold print:text-base">{companyName}</p>
          <p className="text-xs text-muted-foreground">
            Anno di riferimento: {refYear} | Data: {new Date().toLocaleDateString("it-IT")}
          </p>
        </div>
      </div>

      {/* Overall AI commentary — rendered before the first table, editable */}
      <CommentBlock
        k="overall"
        placeholder="Commento complessivo sull'analisi infrannuale (clicca 'Genera commenti AI' o scrivi manualmente)..."
      />

      {/* 1. CE CONFRONTO: Storico | Infrannuale | Infrann./Storico */}
      <div>
        <h2 className="text-base font-semibold mb-2">
          Conto Economico — Confronto {periodMonths}M {partialYear} vs 12M {refYear}
        </h2>
        <Table className="table-fixed print-custom-cols">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[55%] print:w-[44%]">Voce</TableHead>
              <TableHead className="text-right text-xs leading-tight">Storico<br />{refYear}</TableHead>
              <TableHead className="text-right text-xs leading-tight">Infrannuale<br />{periodMonths}M</TableHead>
              <TableHead className="text-right text-xs leading-tight">Infrannuale/<br />Storico</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleIncome.map(item => {
              const isHeader = item.code.startsWith("_hdr_");
              const isSubtotal = ["_totale_vp", "_totale_cp", "_totale_fin", "_totale_straord",
                "_ebitda", "_ebit", "_profit_before_tax", "_net_profit"].includes(item.code);
              if (isHeader) return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={4} className="text-xs font-bold py-1.5 print:py-0.5 print:text-[9px]">{item.label}</TableCell>
                </TableRow>
              );
              return (
                <TableRow key={item.code} className={cn(isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10")}>
                  <TableCell className={cn("text-sm", isSubtotal ? "font-semibold text-sm" : "font-normal text-xs")}>{item.label}</TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {formatEuro(item.reference_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {formatEuro(item.partial_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {deltaFmt(item.partial_value, item.reference_value)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <CommentBlock k="ce_confronto" placeholder="Commento su Conto Economico — Confronto..." />

      {/* 2. SP CONFRONTO: Storico | Infrannuale | Infrann./Storico */}
      <div>
        <h2 className="text-base font-semibold mb-2">
          Stato Patrimoniale — Confronto
        </h2>
        <Table className="table-fixed print-custom-cols">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[55%] print:w-[44%]">Voce</TableHead>
              <TableHead className="text-right text-xs leading-tight">Storico<br />{refYear}</TableHead>
              <TableHead className="text-right text-xs leading-tight">Infrannuale<br />{periodMonths}M</TableHead>
              <TableHead className="text-right text-xs leading-tight">Infrannuale/<br />Storico</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleBalance.map(item => {
              const isHeader = item.code.startsWith("_hdr_");
              const isSubtotal = ["_totale_attivo", "_totale_passivo",
                "_totale_immob", "_totale_circ", "_totale_pn", "_totale_debiti", "_differenza"].includes(item.code);
              if (isHeader) return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={4} className="text-xs font-bold py-1.5 print:py-0.5 print:text-[9px]">{item.label}</TableCell>
                </TableRow>
              );
              return (
                <TableRow key={item.code} className={cn(isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10")}>
                  <TableCell className={cn("text-sm", isSubtotal ? "font-semibold text-sm" : "font-normal text-xs")}>{item.label}</TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {formatEuro(item.reference_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {formatEuro(item.partial_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {deltaFmt(item.partial_value, item.reference_value)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <CommentBlock k="sp_confronto" placeholder="Commento su Stato Patrimoniale — Confronto..." />

      {/* 3. CE PROIEZIONE: Storico | Infrannuale | Proiezione | Proiez./Storico (hidden when 12M) */}
      {periodMonths !== 12 && (
      <div>
        <h2 className="text-base font-semibold mb-2">
          Conto Economico — Proiezione {partialYear}
        </h2>
        <Table className="table-fixed print-custom-cols">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[55%] print:w-[44%]">Voce</TableHead>
              <TableHead className="text-right text-xs leading-tight">Storico<br />{refYear}</TableHead>
              <TableHead className="text-right text-xs leading-tight">Infrannuale<br />{periodMonths}M</TableHead>
              <TableHead className="text-right text-xs leading-tight">Proiezione<br />{partialYear}</TableHead>
              <TableHead className="text-right text-xs leading-tight">Proiezione/<br />Storico</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleIncome.map(item => {
              const isHeader = item.code.startsWith("_hdr_");
              const isSubtotal = ["_totale_vp", "_totale_cp", "_totale_fin", "_totale_straord",
                "_ebitda", "_ebit", "_profit_before_tax", "_net_profit"].includes(item.code);
              const projValue = getProjectedCE(item);
              if (isHeader) return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={5} className="text-xs font-bold py-1.5 print:py-0.5 print:text-[9px]">{item.label}</TableCell>
                </TableRow>
              );
              return (
                <TableRow key={item.code} className={cn(isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10")}>
                  <TableCell className={cn(isSubtotal ? "font-semibold text-sm" : "font-normal text-xs")}>{item.label}</TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {formatEuro(item.reference_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {formatEuro(item.partial_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs font-medium">
                    {formatEuro(projValue)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {deltaFmt(projValue, item.reference_value)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      )}

      {periodMonths !== 12 && <CommentBlock k="ce_proiezione" placeholder="Commento su Conto Economico — Proiezione..." />}

      {/* 4. SP PROIEZIONE: Storico | Infrannuale | Proiezione | Proiez./Storico (hidden when 12M) */}
      {periodMonths !== 12 && (
      <div>
        <h2 className="text-base font-semibold mb-2">
          Stato Patrimoniale — Proiezione {partialYear}
        </h2>
        <Table className="table-fixed print-custom-cols">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[55%] print:w-[44%]">Voce</TableHead>
              <TableHead className="text-right text-xs leading-tight">Storico<br />{refYear}</TableHead>
              <TableHead className="text-right text-xs leading-tight">Infrannuale<br />{periodMonths}M</TableHead>
              <TableHead className="text-right text-xs leading-tight">Proiezione<br />{partialYear}</TableHead>
              <TableHead className="text-right text-xs leading-tight">Proiezione/<br />Storico</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleBalance.map(item => {
              const isHeader = item.code.startsWith("_hdr_");
              const isSubtotal = ["_totale_attivo", "_totale_passivo",
                "_totale_immob", "_totale_circ", "_totale_pn", "_totale_debiti", "_differenza"].includes(item.code);
              const projVal = projBSMap.get(item.code) ?? NaN;
              if (isHeader) return (
                <TableRow key={item.code} className="bg-muted hover:bg-muted">
                  <TableCell colSpan={5} className="text-xs font-bold py-1.5 print:py-0.5 print:text-[9px]">{item.label}</TableCell>
                </TableRow>
              );
              return (
                <TableRow key={item.code} className={cn(isSubtotal && "bg-primary/10 font-semibold hover:bg-primary/10")}>
                  <TableCell className={cn(isSubtotal ? "font-semibold text-sm" : "font-normal text-xs")}>{item.label}</TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {formatEuro(item.reference_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {formatEuro(item.partial_value)}
                  </TableCell>
                  <TableCell className="text-right text-xs font-medium">
                    {isNaN(projVal) ? <span className="text-muted-foreground">-</span> : formatEuro(projVal)}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {isNaN(projVal) ? (
                      <span className="text-muted-foreground">-</span>
                    ) : (
                      deltaFmt(projVal, item.reference_value)
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      )}

      {periodMonths !== 12 && <CommentBlock k="sp_proiezione" placeholder="Commento su Stato Patrimoniale — Proiezione..." />}

      {/* 5. INDICATORI DELLA CRISI D'IMPRESA */}
      <div>
        <h2 className="text-base font-semibold mb-2">Indicatori della Crisi d&apos;Impresa</h2>

        {/* Rating cards */}
        <div className={cn("grid gap-4 mb-4", periodMonths === 12 ? "grid-cols-2" : "grid-cols-3")}>
          {[
            { label: `Storico ${refYear}`, rating: storicoRating, oltre: oltreCount(storicoScores), alerts: 0 },
            { label: `Infrann. ${periodMonths}M ${partialYear}`, rating: infraRating, oltre: oltreCount(infraScores), alerts: alertCount },
            ...(periodMonths !== 12 ? [{ label: `Proiezione ${partialYear}`, rating: proiezioneRating, oltre: oltreCount(proiezioneScores), alerts: alertCount }] : []),
          ].map(col => (
            <div key={col.label} className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <p className="text-xs text-muted-foreground">{col.label}</p>
                <p className={cn("text-2xl font-bold", col.rating.color)}>{col.rating.code}</p>
              </div>
              <div className="text-right">
                <p className={cn("text-sm font-medium", col.rating.color)}>{col.rating.label}</p>
                <p className="text-xs text-muted-foreground">
                  {col.oltre}/14 oltre{col.alerts > 0 ? ` + ${col.alerts} segn.` : ""}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Indicator detail table */}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Indicatore</TableHead>
              <TableHead className="text-right">Storico {refYear}</TableHead>
              <TableHead className="text-right">Infrann. {periodMonths}M</TableHead>
              {periodMonths !== 12 && <TableHead className="text-right">Proiezione {partialYear}</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {INDICATOR_DEFS.map((def, idx) => (
              <TableRow key={def.key}>
                <TableCell className="font-medium">{def.label}</TableCell>
                <TableCell className="text-right">
                  <span className="inline-flex items-center gap-2">
                    <span className="text-muted-foreground">{formatInd(storicoInd[def.key], def.format)}</span>
                    <span className={cn("inline-block h-2.5 w-2.5 rounded-full print:h-2 print:w-2", scoreDotColor(storicoScores[idx]))} />
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  <span className="inline-flex items-center gap-2">
                    <span>{formatInd(infraInd[def.key], def.format)}</span>
                    <span className={cn("inline-block h-2.5 w-2.5 rounded-full print:h-2 print:w-2", scoreDotColor(infraScores[idx]))} />
                  </span>
                </TableCell>
                {periodMonths !== 12 && (
                  <TableCell className="text-right">
                    <span className="inline-flex items-center gap-2">
                      <span className="font-medium">{formatInd(proiezioneInd[def.key], def.format)}</span>
                      <span className={cn("inline-block h-2.5 w-2.5 rounded-full print:h-2 print:w-2", scoreDotColor(proiezioneScores[idx]))} />
                    </span>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <CommentBlock k="indicatori" placeholder="Commento sugli indicatori della crisi d'impresa..." />

      {/* 6. SEGNALI EXTRACONTABILI */}
      <div>
        <h2 className="text-base font-semibold mb-2">
          Segnali Extracontabili
          {alertCount > 0 && (
            <span className="ml-2 text-sm font-normal text-red-600 dark:text-red-400">
              ({alertCount} segnale{alertCount > 1 ? "i" : ""} attivo{alertCount > 1 ? "i" : ""})
            </span>
          )}
        </h2>
        <div className="rounded-lg border border-border p-4 print:p-2 space-y-2 print:space-y-0.5">
          {EXTRA_ALERT_DEFS.map((def, idx) => {
            const isActive = !!extraAlerts[def.key];
            return (
              <div key={def.key} className="flex items-start gap-2 text-sm print:text-[10px] print:leading-tight">
                <span className={cn(
                  "mt-0.5 inline-block h-4 w-4 print:h-3 print:w-3 shrink-0 rounded border text-center text-xs print:text-[8px] leading-4 print:leading-3",
                  isActive
                    ? "bg-red-600 border-red-600 text-white dark:bg-red-500 dark:border-red-500"
                    : "border-border text-transparent"
                )}>
                  {isActive ? "✓" : ""}
                </span>
                <span className={isActive ? "font-medium" : "text-muted-foreground"}>
                  <span className="font-medium">{idx + 1}.</span> {def.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
