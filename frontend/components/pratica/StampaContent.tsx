"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { useAuth } from "@/contexts/AuthContext";
import { usePratica } from "@/contexts/PraticaContext";
import { usePrimaryAction } from "@/contexts/PraticaActionContext";
import { useInvalidateAnalysis } from "@/hooks/use-queries";
import { useInfrannualeDownload } from "@/hooks/use-infrannuale-download";
import { useFileDownload } from "@/hooks/use-file-download";
import { downloadReportDocx } from "@/lib/api";
import { rigeneraBudgetRiusato } from "@/lib/budget-rigenera-riuso";
import {
  bulkUpsertAssumptions,
  createBudgetScenario,
  getBalanceSheet,
  getBudgetAssumptions,
  promoteProjection,
} from "@/lib/api";
import type { CrisiInfrannuale, IntraYearComparison, IntraYearComparisonItem } from "@/types/api";
import { toast } from "sonner";
import { FileText, Loader2, Printer } from "lucide-react";
import { cn, getErrorMessage } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatEuro, formatPct, deltaPct } from "@/lib/pratica-format";
import { ALWAYS_SHOW_CODES, VP_CODES, EXTRA_ALERT_DEFS } from "@/lib/pratica-codes";
import { ceDerivatiDaForecast, valoreCeProiettato } from "@/lib/pratica-ce-proiettato";
import {
  INDICATOR_DEFS,
  scoreDotColor,
  type SerieIndicatori,
} from "@/lib/pratica-indicators";
import { RATING_COLOR, vistaColonna } from "@/lib/pratica-crisi";
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
  forecastIs,
  crisi,
  crisiError,
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
  forecastIs: Record<string, number>;
  crisi: CrisiInfrannuale | null;
  crisiError: unknown;
  extraAlerts: Record<string, boolean>;
  companyName: string;
  fiscalYear: number;
  periodMonths: number;
  companyId?: number;
  scenarioId?: number;
  onBeforePromote?: () => Promise<void>;
}) {
  const router = useRouter();
  const invalidateAnalysis = useInvalidateAnalysis();
  const { refreshCompanies, refreshYears } = useApp();
  const { logoUrl, userName } = useAuth();
  const { updatePratica } = usePratica();
  const [promoting, setPromoting] = useState(false);
  const refYear = comparison.reference_year;
  const partialYear = comparison.partial_year;

  // Il documento che si consegna e' il report infrannuale generato dal server
  // (`POST .../infrannuale/pdf`, ReportLab), non la stampa del browser di
  // questa pagina, che resta come anteprima a schermo. Il PDF ha testi a
  // regole e porta i commenti nel testo.
  const { download: downloadPdf, downloading: downloadingPdf } = useInfrannualeDownload();
  const handleDownloadPdf = async () => {
    if (!companyId || !scenarioId) return;
    await downloadPdf(companyId, scenarioId);
  };
  // Lo stesso report in Word, per correggere i testi prima di consegnarlo.
  const { download: downloadFile, downloading: downloadingWord } = useFileDownload();
  const handleDownloadWord = async () => {
    if (!companyId || !scenarioId) return;
    await downloadFile(() => downloadReportDocx(companyId, scenarioId, "infrannuale"),
      "Impossibile scaricare il Word del report");
  };

  // --- P&L data ---
  const incomeItems = buildIncomeItemsWithEbitda(comparison.income_items, periodMonths);
  const projCEVal = (code: string) => parseFloat(overrides[code] || "0");

  // Stessa regola della tab Proiezione, da un modulo solo: override se la riga
  // è modificabile, valore dedotto dal motore per le variazioni di magazzino,
  // annualizzazione per il resto. Le due grafie separate di prima erano due modi
  // di far dire alla Stampa un numero diverso dalla Proiezione.
  const ceDerivati = ceDerivatiDaForecast(forecastIs);
  const spv = (code: string): number =>
    valoreCeProiettato(code, {
      overrides,
      derivati: ceDerivati,
      annualizzato: (c) => comparison.income_items.find(i => i.code === c)?.annualized_value ?? 0,
    });

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
    return spv(item.code);
  };

  // --- BS data ---
  const balanceItems = buildBalanceItemsWithTotals(comparison.balance_items);
  const projBSMap = new Map(projectedBS.map(i => [i.code, i.annualized_value]));

  // --- Indicators: calcolati dal server (`GET .../infrannuale/crisi`) ---
  // Il rating di infrannuale e proiezione segue i segnali spuntati in pagina,
  // anche non ancora salvati (`vistaColonna`); lo storico non ne ha mai.
  const alertCount = Object.values(extraAlerts).filter(Boolean).length;
  const storicoVista = vistaColonna(crisi?.storico ?? null, 0);
  const infraVista = vistaColonna(crisi?.infrannuale ?? null, alertCount);
  const proiezioneVista = periodMonths === 12 ? null : vistaColonna(crisi?.proiezione ?? null, alertCount);

  // Le etichette sono di questa vista: in Stampa la colonna porta anche
  // l'anno ("Infrann. 9M 2026"), nella tab Indicatori no.
  const serieGrafici: SerieIndicatori[] = [
    { periodo: `Storico ${refYear}`, indicatori: storicoVista?.indicatori ?? null },
    { periodo: `Infrann. ${periodMonths}M ${partialYear}`, indicatori: infraVista?.indicatori ?? null },
    { periodo: `Proiezione ${partialYear}`, indicatori: proiezioneVista?.indicatori ?? null },
  ];

  const formatInd = (value: number, format: "euro" | "pct" | "ratio") => {
    if (format === "euro") return formatEuro(value);
    if (format === "pct") return formatPct(value);
    return `${value.toFixed(2)}x`;
  };

  // Helper: delta % between two values
  const deltaFmt = (proj: number, ref: number) => {
    const d = deltaPct(proj, ref);
    if (d === null) return <span className="text-muted-foreground">-</span>;
    return (
      <span className={d > 1 ? "text-green-600 dark:text-green-400" : d < -1 ? "text-red-600 dark:text-red-400" : "text-muted-foreground"}>
        {d > 0 ? "+" : ""}{formatPct(d)}
      </span>
    );
  };

  // Filter for visible rows
  const visibleIncome = incomeItems.filter(item => ALWAYS_SHOW_CODES.has(item.code) || item.partial_value !== 0 || item.reference_value !== 0);
  const visibleBalance = balanceItems.filter(item => ALWAYS_SHOW_CODES.has(item.code) || item.partial_value !== 0 || item.reference_value !== 0);

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

      // The server derives provenance and returns only an exact active reuse;
      // a generic client-side base-year lookup would cross workflow lineages.
      const budget = await createBudgetScenario(companyId, {
        company_id: companyId,
        name: `Budget ${baseYear + 1}–${baseYear + 3}`,
        base_year: baseYear,
        scenario_type: "budget",
        reuse_existing: true,
      });

      updatePratica({ budgetScenarioId: budget.id });
      // Uno scenario riusato era calcolato sul vecchio anno base, che il
      // promote ha appena riscritto: si rigenera con le ipotesi salvate
      // (lib/budget-rigenera-riuso.ts). Un rifiuto non ferma il passaggio:
      // l'utente arriva sul wizard col messaggio del motore.
      const rigenerato = await rigeneraBudgetRiusato(budget.id, {
        getAssumptions: () => getBudgetAssumptions(companyId, budget.id),
        getBaseBalanceSheet: () => getBalanceSheet(companyId, baseYear),
        bulkSave: (rows) => bulkUpsertAssumptions(companyId, budget.id, { assumptions: rows, auto_generate: true }),
      }).catch((err: unknown) => ({ ok: false, message: getErrorMessage(err, "Ricalcolo del previsionale non riuscito") }));
      invalidateAnalysis(companyId, budget.id);
      await refreshCompanies();
      await refreshYears();
      if (rigenerato === null) toast.success("Scenario budget pronto");
      else if (rigenerato.ok) toast.success(rigenerato.message);
      else toast.error(`Scenario budget pronto, ma il previsionale non è stato ricalcolato: ${rigenerato.message}`);
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
    invalidateAnalysis,
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
    <div id="stampa-content" className="space-y-8 print:space-y-3 bg-white dark:bg-background -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8 -mt-8 pt-8 pb-8">
      {/* Action buttons */}
      <div className="flex justify-end gap-2 print:hidden">
        {companyId && scenarioId && (
          <Button onClick={() => void handleDownloadPdf()} variant="outline" disabled={downloadingPdf || downloadingWord}>
            {downloadingPdf ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Printer className="h-4 w-4 mr-2" />
            )}
            Scarica PDF
          </Button>
        )}
        {companyId && scenarioId && (
          <Button onClick={() => void handleDownloadWord()} variant="outline" disabled={downloadingPdf || downloadingWord}>
            {downloadingWord ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <FileText className="h-4 w-4 mr-2" />
            )}
            Scarica Word
          </Button>
        )}
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

        {!storicoVista || !infraVista ? (
          <p className={cn("text-sm", crisiError ? "text-destructive" : "text-muted-foreground")}>
            {crisiError
              ? `Indicatori non disponibili: ${getErrorMessage(crisiError)}`
              : "Calcolo degli indicatori..."}
          </p>
        ) : (<>
        {/* Rating cards */}
        <div className={cn("grid gap-4 mb-4 stampa-blocco", periodMonths === 12 ? "grid-cols-2" : "grid-cols-3")}>
          {[
            { label: `Storico ${refYear}`, vista: storicoVista },
            { label: `Infrann. ${periodMonths}M ${partialYear}`, vista: infraVista },
            ...(periodMonths !== 12 ? [{ label: `Proiezione ${partialYear}`, vista: proiezioneVista }] : []),
          ].map(col => (
            <div key={col.label} className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <p className="text-xs text-muted-foreground">{col.label}</p>
                <p className={cn("text-2xl font-bold", col.vista ? RATING_COLOR[col.vista.rating.livello] : "text-muted-foreground")}>
                  {col.vista?.rating.codice ?? "—"}
                </p>
              </div>
              <div className="text-right">
                {col.vista ? (
                  <>
                    <p className={cn("text-sm font-medium", RATING_COLOR[col.vista.rating.livello])}>{col.vista.rating.etichetta}</p>
                    <p className="text-xs text-muted-foreground">
                      {col.vista.rating.oltre}/14 oltre{col.vista.rating.segnali > 0 ? ` + ${col.vista.rating.segnali} segn.` : ""}
                    </p>
                  </>
                ) : (
                  <p className="text-xs text-muted-foreground">Proiezione non generata</p>
                )}
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
            {INDICATOR_DEFS.map((def) => (
              <TableRow key={def.key}>
                <TableCell className="font-medium">{def.label}</TableCell>
                <TableCell className="text-right">
                  <span className="inline-flex items-center gap-2">
                    <span className="text-muted-foreground">{formatInd(storicoVista.indicatori[def.key], def.format)}</span>
                    <span className={cn("inline-block h-2.5 w-2.5 rounded-full print:h-2 print:w-2", scoreDotColor(storicoVista.punteggi[def.key]))} />
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  <span className="inline-flex items-center gap-2">
                    <span>{formatInd(infraVista.indicatori[def.key], def.format)}</span>
                    <span className={cn("inline-block h-2.5 w-2.5 rounded-full print:h-2 print:w-2", scoreDotColor(infraVista.punteggi[def.key]))} />
                  </span>
                </TableCell>
                {periodMonths !== 12 && (
                  <TableCell className="text-right">
                    {proiezioneVista ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="font-medium">{formatInd(proiezioneVista.indicatori[def.key], def.format)}</span>
                        <span className={cn("inline-block h-2.5 w-2.5 rounded-full print:h-2 print:w-2", scoreDotColor(proiezioneVista.punteggi[def.key]))} />
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
        </>)}
      </div>


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
