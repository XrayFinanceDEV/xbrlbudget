"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { useAuth } from "@/contexts/AuthContext";
import { usePratica } from "@/contexts/PraticaContext";
import { usePrimaryAction } from "@/contexts/PraticaActionContext";
import {
  getBudgetScenarios,
  createBudgetScenario,
  promoteProjection,
  getInfrannualeAIComments,
  generateInfrannualeAIComments,
  saveInfrannualeAIComments,
  type InfrannualeAIComments,
} from "@/lib/api";
import type { IntraYearComparison, IntraYearComparisonItem } from "@/types/api";
import { toast } from "sonner";
import { Loader2, Printer, Sparkles } from "lucide-react";
import { cn, getErrorMessage } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatEuro, formatPct } from "@/lib/pratica-format";
import { EDITABLE_CE_CODES, ALWAYS_SHOW_CODES, VP_CODES, EXTRA_ALERT_DEFS } from "@/lib/pratica-codes";
import {
  computeIndicators,
  scoreIndicator,
  INDICATOR_DEFS,
  crisisScores,
  scoreDotColor,
  computeCrisisRating,
  type SerieIndicatori,
} from "@/lib/pratica-indicators";
import { IndicatoriCharts } from "@/components/pratica/IndicatoriCharts";
import {
  buildBalanceItemsWithTotals,
  buildIncomeItemsWithEbitda,
} from "@/lib/pratica-statement-rows";

// Print-ready view for PDF generation via Playwright
export function StampaContent({
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

  // Le etichette sono di questa vista: in Stampa la colonna porta anche
  // l'anno ("Infrann. 9M 2026"), nella tab Indicatori no.
  const serieGrafici: SerieIndicatori[] = [
    { periodo: `Storico ${refYear}`, indicatori: storicoInd },
    { periodo: `Infrann. ${periodMonths}M ${partialYear}`, indicatori: infraInd },
    {
      periodo: `Proiezione ${partialYear}`,
      indicatori: periodMonths === 12 ? null : proiezioneInd,
    },
  ];

  const storicoScores = INDICATOR_DEFS.map(d => scoreIndicator(d.key, storicoInd));
  const infraScores = INDICATOR_DEFS.map(d => scoreIndicator(d.key, infraInd));
  const proiezioneScores = INDICATOR_DEFS.map(d => scoreIndicator(d.key, proiezioneInd));

  const alertCount = Object.values(extraAlerts).filter(Boolean).length;

  // Il punteggio di crisi NON usa tutte le righe rese: le bande di
  // `computeCrisisRating` sono tarate sul numero di indicatori che le
  // alimentano (vedi `CRISIS_SCORING_KEYS`). Gli array qui sopra restano
  // allineati a INDICATOR_DEFS perche' li indicizza il pallino di riga.
  const storicoCrisis = crisisScores(storicoInd);
  const infraCrisis = crisisScores(infraInd);
  const proiezioneCrisis = crisisScores(proiezioneInd);

  const storicoRating = computeCrisisRating(storicoCrisis, 0);
  const infraRating = computeCrisisRating(infraCrisis, alertCount);
  const proiezioneRating = computeCrisisRating(proiezioneCrisis, alertCount);

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
        Storico: ratingRow(storicoRating, storicoCrisis, 0),
        Infrannuale: ratingRow(infraRating, infraCrisis, alertCount),
        Proiezione: ratingRow(proiezioneRating, proiezioneCrisis, alertCount),
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
      <div className={cn("rounded-md border border-border/60 bg-muted/20 p-3 my-2 print:my-1 print:p-2 stampa-commento", !value && "print:hidden")}>
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
      <div className="relative print:mb-4 stampa-blocco">
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
                <TableRow key={item.code} className="bg-muted hover:bg-muted stampa-riga-titolo">
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
                <TableRow key={item.code} className="bg-muted hover:bg-muted stampa-riga-titolo">
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
                <TableRow key={item.code} className="bg-muted hover:bg-muted stampa-riga-titolo">
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
                <TableRow key={item.code} className="bg-muted hover:bg-muted stampa-riga-titolo">
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
      {/* Il blocco NON e' indivisibile, e non deve esserlo: cartellini +
          grafici + tabella misurano piu' di mezza pagina, e vietare il taglio
          sull'intero blocco lo spingeva intero alla pagina dopo — 170pt di
          bianco in fondo alla precedente e una pagina finale con i soli
          segnali extracontabili. A proteggere ci sono i pezzi: `stampa-blocco`
          sui cartellini e sulla griglia dei sei grafici (che quindi non si
          spezza mai a meta' di una riga di riquadri), `break-after: avoid`
          sull'h2, intestazione ripetuta sulla tabella. E' cosi' che il timore
          di #15 — i grafici su una pagina e la tabella da sola sulla dopo —
          resta escluso senza pagarlo con una pagina quasi vuota. */}
      <div>
        <h2 className="text-base font-semibold mb-2">Indicatori della Crisi d&apos;Impresa</h2>

        {/* Rating cards */}
        <div className={cn("grid gap-4 mb-4 stampa-blocco", periodMonths === 12 ? "grid-cols-2" : "grid-cols-3")}>
          {[
            { label: `Storico ${refYear}`, rating: storicoRating, oltre: oltreCount(storicoCrisis), alerts: 0 },
            { label: `Infrann. ${periodMonths}M ${partialYear}`, rating: infraRating, oltre: oltreCount(infraCrisis), alerts: alertCount },
            ...(periodMonths !== 12 ? [{ label: `Proiezione ${partialYear}`, rating: proiezioneRating, oltre: oltreCount(proiezioneCrisis), alerts: alertCount }] : []),
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

        {/* Grafici di sintesi: prima il quadro d'insieme, poi il dettaglio */}
        <div className="mb-4 stampa-blocco">
          <IndicatoriCharts serie={serieGrafici} />
        </div>

        {/* Indicator detail table. `stampa-tabella-indicatori` la tiene
            attaccata alla griglia dei grafici qui sopra: e' il criterio di #15
            («la tabella non finisce da sola su una pagina») reso vincolo
            invece che conseguenza del riempimento. */}
        <Table className="stampa-tabella-indicatori">
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
        <div className="rounded-lg border border-border p-4 print:p-2 space-y-2 print:space-y-0.5 stampa-blocco">
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
