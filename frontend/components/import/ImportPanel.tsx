"use client";

// Single import surface reused by /import and (Phase A) the Pratica shell.
// - periodMonths set (1-11): partial-year import → threads period_months into
//   PDF/XBRL, hides the CSV tab (partial year is PDF/XBRL only).
// - fixedCompanyId set: locks to that company (update mode), hides the mode chooser.
// - onSuccess(result): called after any successful import (in addition to toasts).
import { useState } from "react";
import { useApp } from "@/contexts/AppContext";
import {
  importXBRL,
  importCSV,
  importPDF,
  type XBRLImportResult,
  type CSVImportResult,
  type PDFImportResult,
} from "@/lib/api";
import { toast } from "sonner";
import { FileText, Info, AlertTriangle, CheckCircle2, Bot } from "lucide-react";
import { getErrorMessage } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export type ImportResult = XBRLImportResult | CSVImportResult | PDFImportResult;

const SECTOR_OPTIONS: Record<number, string> = {
  1: "Industria, Alberghi (Proprietari), Agricoltura, Pesca",
  2: "Commercio",
  3: "Servizi (diversi da Autotrasporti) e Alberghi (Locatari)",
  4: "Autotrasporti",
  5: "Immobiliare",
  6: "Edilizia",
};

type ImportMode = "update" | "create";

export function ImportPanel({
  periodMonths = null,
  fixedCompanyId = null,
  onSuccess,
}: {
  periodMonths?: number | null;
  fixedCompanyId?: number | null;
  onSuccess?: (result: ImportResult) => void;
}) {
  const { selectedCompanyId, setSelectedCompanyId } = useApp();

  // When the company is fixed (wizard/pratica), we always update that company.
  const lockedCompany = fixedCompanyId !== null;
  const [importMode, setImportMode] = useState<ImportMode>(lockedCompany ? "update" : "create");
  const effectiveMode: ImportMode = lockedCompany ? "update" : importMode;
  const effectiveCompanyId = fixedCompanyId ?? selectedCompanyId;

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [year1, setYear1] = useState<number>(2024);
  const [year2, setYear2] = useState<number>(2023);
  const [fiscalYear, setFiscalYear] = useState<number>(2024);
  const [companyName, setCompanyName] = useState<string>("");
  const [selectedSector, setSelectedSector] = useState<number>(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [xbrlResult, setXbrlResult] = useState<XBRLImportResult | null>(null);
  const [csvResult, setCsvResult] = useState<CSVImportResult | null>(null);
  const [pdfResult, setPdfResult] = useState<PDFImportResult | null>(null);

  const clearResults = () => {
    setSelectedFile(null);
    setError(null);
    setXbrlResult(null);
    setCsvResult(null);
    setPdfResult(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSelectedFile(e.target.files?.[0] || null);
    setError(null);
    setXbrlResult(null);
    setCsvResult(null);
    setPdfResult(null);
  };

  const resetFileInput = () => {
    const fileInput = document.getElementById("import-panel-file") as HTMLInputElement;
    if (fileInput) fileInput.value = "";
  };

  const handleXBRLImport = async () => {
    if (!selectedFile) { setError("Seleziona un file prima di procedere"); return; }
    if (effectiveMode === "update" && !effectiveCompanyId) { setError("Devi selezionare un'azienda per aggiornarla"); return; }
    setLoading(true); setError(null); setXbrlResult(null);
    try {
      const companyId = effectiveMode === "create" ? null : effectiveCompanyId;
      const result = await importXBRL(selectedFile, companyId, effectiveMode === "create",
        effectiveMode === "create" ? selectedSector : undefined, periodMonths ?? undefined);
      setXbrlResult(result);
      setSelectedCompanyId(result.company_id);
      setSelectedFile(null);
      resetFileInput();
      toast.success("Importazione XBRL completata!");
      onSuccess?.(result);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Errore durante l'importazione"));
    } finally { setLoading(false); }
  };

  const handleCSVImport = async () => {
    if (!selectedFile) { setError("Seleziona un file prima di procedere"); return; }
    if (!effectiveCompanyId) { setError("Devi selezionare un'azienda prima di importare CSV"); return; }
    setLoading(true); setError(null); setCsvResult(null);
    try {
      const result = await importCSV(selectedFile, effectiveCompanyId, year1, year2);
      setCsvResult(result);
      setSelectedFile(null);
      resetFileInput();
      toast.success("Importazione CSV completata!");
      onSuccess?.(result);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Errore durante l'importazione"));
    } finally { setLoading(false); }
  };

  const handlePDFImport = async () => {
    if (!selectedFile) { setError("Seleziona un file prima di procedere"); return; }
    if (!fiscalYear) { setError("Specificare l'anno fiscale del bilancio"); return; }
    if (effectiveMode === "update" && !effectiveCompanyId) { setError("Devi selezionare un'azienda per aggiornarla"); return; }
    if (effectiveMode === "create" && !companyName) { setError("Specificare il nome dell'azienda per la creazione"); return; }
    setLoading(true); setError(null); setPdfResult(null);
    try {
      const companyId = effectiveMode === "create" ? null : effectiveCompanyId;
      const result = await importPDF(selectedFile, fiscalYear,
        effectiveMode === "create" ? companyName : undefined, companyId,
        effectiveMode === "create", effectiveMode === "create" ? selectedSector : undefined,
        periodMonths ?? undefined);
      setPdfResult(result);
      setSelectedCompanyId(result.company_id);
      setSelectedFile(null);
      resetFileInput();
      toast.success("Estrazione PDF completata!");
      onSuccess?.(result);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Errore durante l'importazione"));
    } finally { setLoading(false); }
  };

  const ImportModeRadio = () => (
    <div>
      <Label className="mb-3 block">Modalità Importazione</Label>
      <RadioGroup value={effectiveMode} onValueChange={(v) => setImportMode(v as ImportMode)} className="space-y-2">
        <div className="flex items-center space-x-2">
          <RadioGroupItem value="update" id="ip-mode-update" />
          <Label htmlFor="ip-mode-update" className="font-normal">Aggiorna azienda esistente</Label>
        </div>
        <div className="flex items-center space-x-2">
          <RadioGroupItem value="create" id="ip-mode-create" />
          <Label htmlFor="ip-mode-create" className="font-normal">Crea nuova azienda</Label>
        </div>
      </RadioGroup>
    </div>
  );

  const sectorSelect = (
    <div>
      <Label>Settore *</Label>
      <Select value={selectedSector.toString()} onValueChange={(v) => setSelectedSector(parseInt(v))}>
        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
        <SelectContent>
          {Object.entries(SECTOR_OPTIONS).map(([value, label]) => (
            <SelectItem key={value} value={value}>{value}. {label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );

  return (
    <div>
      <Tabs defaultValue="pdf" onValueChange={() => clearResults()}>
        <TabsList className="mb-6">
          <TabsTrigger value="pdf">PDF (IV CEE - AI)</TabsTrigger>
          <TabsTrigger value="xbrl">XBRL (formato italiano)</TabsTrigger>
          {periodMonths === null && <TabsTrigger value="csv">CSV (da TEBE)</TabsTrigger>}
        </TabsList>

        {/* PDF Import */}
        <TabsContent value="pdf">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Bot className="h-5 w-5" /> Importazione PDF (IV CEE)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <Alert>
                <Bot className="h-4 w-4" />
                <AlertTitle>Estrazione AI-powered</AlertTitle>
                <AlertDescription>
                  <ul className="mt-2 text-sm space-y-1">
                    <li>Formati: Bilancio Micro, Abbreviato, Ordinario, Situazione contabile</li>
                    <li>Estrazione automatica di Stato Patrimoniale e Conto Economico</li>
                  </ul>
                </AlertDescription>
              </Alert>

              <div>
                <Label htmlFor="import-panel-file">Carica file PDF</Label>
                <Input id="import-panel-file" type="file" accept=".pdf" onChange={handleFileChange} className="mt-1" />
                {selectedFile && <p className="mt-2 text-sm text-muted-foreground">File: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(2)} KB)</p>}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {!lockedCompany && <ImportModeRadio />}
                <div>
                  <Label>Anno Fiscale *</Label>
                  <Input type="number" value={fiscalYear} onChange={(e) => setFiscalYear(parseInt(e.target.value))} min={2000} max={2100} placeholder="es. 2024" className="mt-1" />
                </div>
              </div>

              {effectiveMode === "create" && (
                <>
                  <div>
                    <Label>Nome Azienda *</Label>
                    <Input type="text" value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="es. ROSSI S.R.L." className="mt-1" />
                  </div>
                  {sectorSelect}
                </>
              )}

              {effectiveMode === "update" && !effectiveCompanyId && (
                <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>Seleziona un&apos;azienda</AlertDescription></Alert>
              )}

              <Button onClick={handlePDFImport}
                disabled={loading || !selectedFile || !fiscalYear || (effectiveMode === "update" && !effectiveCompanyId) || (effectiveMode === "create" && !companyName)}
                className="w-full" size="lg">
                {loading ? "Elaborazione con AI..." : "Importa PDF"}
              </Button>
              {loading && <p className="text-sm text-muted-foreground text-center">Estrazione in corso... può richiedere 5-40 secondi</p>}
            </CardContent>
          </Card>
        </TabsContent>

        {/* XBRL Import */}
        <TabsContent value="xbrl">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><FileText className="h-5 w-5" /> Importazione XBRL</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <Alert>
                <Info className="h-4 w-4" />
                <AlertTitle>File XBRL secondo tassonomia italiana (OIC)</AlertTitle>
                <AlertDescription>
                  <ul className="mt-2 text-sm space-y-1">
                    <li>Versioni 2011–2018, schemi Ordinario/Abbreviato/Micro (auto)</li>
                    <li>L&apos;azienda verrà creata automaticamente se non esiste</li>
                  </ul>
                </AlertDescription>
              </Alert>

              <div>
                <Label htmlFor="import-panel-file">Carica file XBRL</Label>
                <Input id="import-panel-file" type="file" accept=".xbrl,.XBRL,.xml,.XML" onChange={handleFileChange} className="mt-1" />
                {selectedFile && <p className="mt-2 text-sm text-muted-foreground">File: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(2)} KB)</p>}
              </div>

              {!lockedCompany && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <ImportModeRadio />
                  <div />
                </div>
              )}
              {effectiveMode === "create" && sectorSelect}

              <Button onClick={handleXBRLImport}
                disabled={loading || !selectedFile || (effectiveMode === "update" && !effectiveCompanyId)}
                className="w-full" size="lg">
                {loading ? "Importazione in corso..." : "Importa XBRL"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* CSV Import (full-year only) */}
        {periodMonths === null && (
          <TabsContent value="csv">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><FileText className="h-5 w-5" /> Importazione CSV</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <Alert>
                  <Info className="h-4 w-4" />
                  <AlertTitle>CSV esportato da conversione TEBE</AlertTitle>
                  <AlertDescription>Delimitatore «;», UTF-8. Richiede un&apos;azienda già creata.</AlertDescription>
                </Alert>

                {!effectiveCompanyId && (
                  <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>Seleziona o crea un&apos;azienda prima di importare CSV</AlertDescription></Alert>
                )}

                <div>
                  <Label htmlFor="import-panel-file">Carica file CSV</Label>
                  <Input id="import-panel-file" type="file" accept=".csv" onChange={handleFileChange} disabled={!effectiveCompanyId} className="mt-1" />
                  {selectedFile && <p className="mt-2 text-sm text-muted-foreground">File: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(2)} KB)</p>}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <Label>Anno Corrente</Label>
                    <Input type="number" value={year1} onChange={(e) => setYear1(parseInt(e.target.value))} min={2000} max={2100} className="mt-1" />
                  </div>
                  <div>
                    <Label>Anno Precedente</Label>
                    <Input type="number" value={year2} onChange={(e) => setYear2(parseInt(e.target.value))} min={2000} max={2100} className="mt-1" />
                  </div>
                </div>

                <Button onClick={handleCSVImport} disabled={loading || !selectedFile || !effectiveCompanyId} className="w-full" size="lg">
                  {loading ? "Importazione in corso..." : "Importa CSV"}
                </Button>
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>

      {error && (
        <Alert variant="destructive" className="mt-6">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {(xbrlResult || csvResult || pdfResult) && (
        <Alert className="mt-4 border-green-200 dark:border-green-800">
          <CheckCircle2 className="h-4 w-4" />
          <AlertTitle className="text-green-700 dark:text-green-400">
            {pdfResult ? "Estrazione PDF completata!" : "Importazione completata!"}
          </AlertTitle>
          <AlertDescription>
            {pdfResult && <span>{pdfResult.company_name} · anno {pdfResult.fiscal_year} · formato {pdfResult.format}</span>}
            {xbrlResult && <span>{xbrlResult.company_name} · anni {xbrlResult.years.join(", ")}</span>}
            {csvResult && <span>Anni {csvResult.years.join(", ")} · {csvResult.rows_processed} righe</span>}
            {pdfResult?.warnings && pdfResult.warnings.length > 0 && (
              <ul className="mt-2 text-sm text-destructive space-y-1">
                {pdfResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            )}
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
