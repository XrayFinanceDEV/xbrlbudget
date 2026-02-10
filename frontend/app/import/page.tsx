"use client";

import { useState } from "react";
import { useApp } from "@/contexts/AppContext";
import { importXBRL, importCSV, importPDF, type XBRLImportResult, type CSVImportResult, type PDFImportResult } from "@/lib/api";
import { toast } from "sonner";
import { Upload, FileText, Info, AlertTriangle, CheckCircle2, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader } from "@/components/page-header";

const SECTOR_OPTIONS: Record<number, string> = {
  1: "Industria, Alberghi (Proprietari), Agricoltura, Pesca",
  2: "Commercio",
  3: "Servizi (diversi da Autotrasporti) e Alberghi (Locatari)",
  4: "Autotrasporti",
  5: "Immobiliare",
  6: "Edilizia",
};

type ImportMode = "update" | "create";

export default function ImportPage() {
  const { selectedCompanyId, setSelectedCompanyId } = useApp();

  const [importMode, setImportMode] = useState<ImportMode>("create");
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
    const file = e.target.files?.[0] || null;
    setSelectedFile(file);
    setError(null);
    setXbrlResult(null);
    setCsvResult(null);
    setPdfResult(null);
  };

  const resetFileInput = () => {
    const fileInput = document.getElementById("file-upload") as HTMLInputElement;
    if (fileInput) fileInput.value = "";
  };

  const handleXBRLImport = async () => {
    if (!selectedFile) { setError("Seleziona un file prima di procedere"); return; }
    if (importMode === "update" && !selectedCompanyId) { setError("Devi selezionare un'azienda per aggiornarla"); return; }

    setLoading(true); setError(null); setXbrlResult(null);
    try {
      const companyId = importMode === "create" ? null : selectedCompanyId;
      const result = await importXBRL(selectedFile, companyId, importMode === "create", importMode === "create" ? selectedSector : undefined);
      setXbrlResult(result);
      setSelectedCompanyId(result.company_id);
      setSelectedFile(null);
      resetFileInput();
      toast.success("Importazione XBRL completata!");
    } catch (err: any) {
      console.error("Import error:", err);
      setError(err.response?.data?.detail?.error || err.message || "Errore durante l'importazione");
    } finally { setLoading(false); }
  };

  const handleCSVImport = async () => {
    if (!selectedFile) { setError("Seleziona un file prima di procedere"); return; }
    if (!selectedCompanyId) { setError("Devi selezionare un'azienda prima di importare CSV"); return; }

    setLoading(true); setError(null); setCsvResult(null);
    try {
      const result = await importCSV(selectedFile, selectedCompanyId, year1, year2);
      setCsvResult(result);
      setSelectedFile(null);
      resetFileInput();
      toast.success("Importazione CSV completata!");
    } catch (err: any) {
      console.error("Import error:", err);
      setError(err.response?.data?.detail?.error || err.message || "Errore durante l'importazione");
    } finally { setLoading(false); }
  };

  const handlePDFImport = async () => {
    if (!selectedFile) { setError("Seleziona un file prima di procedere"); return; }
    if (!fiscalYear) { setError("Specificare l'anno fiscale del bilancio"); return; }
    if (importMode === "update" && !selectedCompanyId) { setError("Devi selezionare un'azienda per aggiornarla"); return; }
    if (importMode === "create" && !companyName) { setError("Specificare il nome dell'azienda per la creazione"); return; }

    setLoading(true); setError(null); setPdfResult(null);
    try {
      const companyId = importMode === "create" ? null : selectedCompanyId;
      const result = await importPDF(selectedFile, fiscalYear, importMode === "create" ? companyName : undefined, companyId, importMode === "create", importMode === "create" ? selectedSector : undefined);
      setPdfResult(result);
      setSelectedCompanyId(result.company_id);
      setSelectedFile(null);
      resetFileInput();
      toast.success("Estrazione PDF completata!");
    } catch (err: any) {
      console.error("Import error:", err);
      setError(err.response?.data?.detail?.error || err.message || "Errore durante l'importazione");
    } finally { setLoading(false); }
  };

  const ImportModeRadio = () => (
    <div>
      <Label className="mb-3 block">Modalità Importazione</Label>
      <RadioGroup value={importMode} onValueChange={(v) => setImportMode(v as ImportMode)} className="space-y-2">
        <div className="flex items-center space-x-2">
          <RadioGroupItem value="update" id="mode-update" />
          <Label htmlFor="mode-update" className="font-normal">Aggiorna azienda esistente</Label>
        </div>
        <div className="flex items-center space-x-2">
          <RadioGroupItem value="create" id="mode-create" />
          <Label htmlFor="mode-create" className="font-normal">Crea nuova azienda</Label>
        </div>
      </RadioGroup>
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <PageHeader
        title="Importazione Dati"
        description="Importa bilanci da file XBRL, CSV o PDF"
        icon={<Upload className="h-6 w-6" />}
      />

      <Tabs defaultValue="xbrl" onValueChange={() => clearResults()}>
        <TabsList className="mb-6">
          <TabsTrigger value="xbrl">XBRL (formato italiano)</TabsTrigger>
          <TabsTrigger value="csv">CSV (da TEBE)</TabsTrigger>
          <TabsTrigger value="pdf">PDF (IV CEE - Docling AI)</TabsTrigger>
        </TabsList>

        {/* XBRL Import */}
        <TabsContent value="xbrl">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Importazione XBRL
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <Alert>
                <Info className="h-4 w-4" />
                <AlertTitle>Formato supportato: File XBRL secondo tassonomia italiana (OIC)</AlertTitle>
                <AlertDescription>
                  <ul className="mt-2 text-sm space-y-1">
                    <li>Versioni: 2018-11-04, 2017-07-06, 2016-11-14, 2015-12-14, 2014-11-17, 2011-01-04</li>
                    <li>Schemi: Ordinario, Abbreviato, Micro (rilevamento automatico)</li>
                    <li>L&apos;azienda verrà creata automaticamente se non esiste</li>
                  </ul>
                </AlertDescription>
              </Alert>

              <div>
                <Label htmlFor="file-upload">Carica file XBRL</Label>
                <Input id="file-upload" type="file" accept=".xbrl,.xml" onChange={handleFileChange} className="mt-1" />
                {selectedFile && <p className="mt-2 text-sm text-muted-foreground">File: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(2)} KB)</p>}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <ImportModeRadio />
                <div>
                  {importMode === "create" ? (
                    <Alert><Info className="h-4 w-4" /><AlertDescription>Se esiste già un&apos;azienda con la stessa P.IVA, verrà aggiornata.</AlertDescription></Alert>
                  ) : selectedCompanyId ? (
                    <Alert><Info className="h-4 w-4" /><AlertDescription>I dati dell&apos;azienda selezionata verranno aggiornati</AlertDescription></Alert>
                  ) : (
                    <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>Nessuna azienda selezionata!</AlertDescription></Alert>
                  )}
                </div>
              </div>

              {importMode === "create" && (
                <div>
                  <Label>Settore *</Label>
                  <Select value={selectedSector.toString()} onValueChange={(v) => setSelectedSector(parseInt(v))}>
                    <SelectTrigger className="mt-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(SECTOR_OPTIONS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>{value}. {label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              <Button onClick={handleXBRLImport} disabled={loading || !selectedFile || (importMode === "update" && !selectedCompanyId)} className="w-full" size="lg">
                {loading ? "Importazione in corso..." : "Importa XBRL"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* CSV Import */}
        <TabsContent value="csv">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Importazione CSV
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <Alert>
                <Info className="h-4 w-4" />
                <AlertTitle>Formato supportato: CSV esportato da conversione TEBE</AlertTitle>
                <AlertDescription>
                  <ul className="mt-2 text-sm space-y-1">
                    <li>Delimitatore: punto e virgola (;)</li>
                    <li>Codifica: UTF-8</li>
                    <li>Richiede un&apos;azienda già creata</li>
                  </ul>
                </AlertDescription>
              </Alert>

              {!selectedCompanyId && (
                <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>Seleziona o crea un&apos;azienda prima di importare CSV</AlertDescription></Alert>
              )}

              <div>
                <Label htmlFor="file-upload">Carica file CSV</Label>
                <Input id="file-upload" type="file" accept=".csv" onChange={handleFileChange} disabled={!selectedCompanyId} className="mt-1" />
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

              <Button onClick={handleCSVImport} disabled={loading || !selectedFile || !selectedCompanyId} className="w-full" size="lg">
                {loading ? "Importazione in corso..." : "Importa CSV"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* PDF Import */}
        <TabsContent value="pdf">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bot className="h-5 w-5" />
                Importazione PDF (IV CEE)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <Alert>
                <Bot className="h-4 w-4" />
                <AlertTitle>Estrazione AI-powered con Docling</AlertTitle>
                <AlertDescription>
                  <ul className="mt-2 text-sm space-y-1">
                    <li>Formati: Bilancio Micro, Abbreviato, Ordinario</li>
                    <li>Estrazione automatica di Stato Patrimoniale e Conto Economico</li>
                    <li>Tempo di elaborazione: 3-10 secondi per PDF</li>
                  </ul>
                </AlertDescription>
              </Alert>

              <div>
                <Label htmlFor="file-upload">Carica file PDF</Label>
                <Input id="file-upload" type="file" accept=".pdf" onChange={handleFileChange} className="mt-1" />
                {selectedFile && <p className="mt-2 text-sm text-muted-foreground">File: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(2)} KB)</p>}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <ImportModeRadio />
                <div>
                  <Label>Anno Fiscale *</Label>
                  <Input type="number" value={fiscalYear} onChange={(e) => setFiscalYear(parseInt(e.target.value))} min={2000} max={2100} placeholder="es. 2024" className="mt-1" />
                </div>
              </div>

              {importMode === "create" && (
                <>
                  <div>
                    <Label>Nome Azienda *</Label>
                    <Input type="text" value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="es. ROSSI S.R.L." className="mt-1" />
                    <p className="mt-1 text-xs text-muted-foreground">Il nome può essere estratto dal PDF, ma è consigliabile fornirlo manualmente</p>
                  </div>
                  <div>
                    <Label>Settore *</Label>
                    <Select value={selectedSector.toString()} onValueChange={(v) => setSelectedSector(parseInt(v))}>
                      <SelectTrigger className="mt-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(SECTOR_OPTIONS).map(([value, label]) => (
                          <SelectItem key={value} value={value}>{value}. {label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </>
              )}

              {importMode === "update" && !selectedCompanyId && (
                <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>Seleziona un&apos;azienda dalla barra in alto</AlertDescription></Alert>
              )}

              <Button
                onClick={handlePDFImport}
                disabled={loading || !selectedFile || !fiscalYear || (importMode === "update" && !selectedCompanyId) || (importMode === "create" && !companyName)}
                className="w-full" size="lg"
              >
                {loading ? "Elaborazione con Docling AI..." : "Importa PDF"}
              </Button>

              {loading && <p className="text-sm text-muted-foreground text-center">Estrazione in corso... L&apos;elaborazione può richiedere 5-40 secondi</p>}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Error */}
      {error && (
        <Alert variant="destructive" className="mt-6">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* XBRL Results */}
      {xbrlResult && (
        <Card className="mt-6 border-green-200 dark:border-green-800">
          <CardHeader>
            <CardTitle className="text-green-700 dark:text-green-400 flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5" />
              Importazione completata! {xbrlResult.company_created ? "Nuova azienda creata." : "Azienda aggiornata."}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <Card><CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-1">Azienda</p>
                <p className="text-lg font-semibold">{xbrlResult.company_name}</p>
                <p className="text-sm text-muted-foreground mt-2">P.IVA: {xbrlResult.tax_id}</p>
              </CardContent></Card>
              <Card><CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-1">Tassonomia</p>
                <p className="text-lg font-semibold">{xbrlResult.taxonomy_version}</p>
                <p className="text-sm text-muted-foreground mt-2">Contesti: {xbrlResult.contexts_found}</p>
              </CardContent></Card>
              <Card><CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-1">Anni Importati</p>
                <p className="text-lg font-semibold">{xbrlResult.years_imported}</p>
                <p className="text-sm text-muted-foreground mt-2">Anni: {xbrlResult.years.join(", ")}</p>
              </CardContent></Card>
            </div>

            {/* Reconciliation Info (simplified) */}
            {xbrlResult.reconciliation_info && (
              <div className="mt-4 space-y-3">
                {Object.entries(xbrlResult.reconciliation_info).map(([year, info]) => {
                  const hasAdjustments = info.reconciliation_adjustments && Object.keys(info.reconciliation_adjustments).length > 0;
                  if (!hasAdjustments) return null;
                  const { riserve, ...actualAdjustments } = info.reconciliation_adjustments || {};
                  const hasActualAdjustments = Object.keys(actualAdjustments).length > 0;

                  return (
                    <div key={year}>
                      {hasActualAdjustments && (
                        <Alert>
                          <Info className="h-4 w-4" />
                          <AlertTitle>Riconciliazione Anno {year}</AlertTitle>
                          <AlertDescription>
                            <p className="mb-2">Il sistema utilizza i totali aggregati ufficiali dal file XBRL.</p>
                            {Object.entries(actualAdjustments).map(([category, adj]) => (
                              <div key={category} className="bg-muted rounded-md p-3 mb-2 text-sm">
                                <p className="font-semibold mb-1">{category === 'crediti' ? 'CREDITI' : category === 'debiti' ? 'DEBITI' : 'RISERVE'}</p>
                                <div className="flex justify-between"><span>Totale XBRL:</span><span className="font-medium">{'\u20AC'}{adj.xbrl_total.toLocaleString('it-IT', { minimumFractionDigits: 2 })}</span></div>
                                {adj.imported_sum !== 0 && <div className="flex justify-between"><span>Voci importate:</span><span>{'\u20AC'}{adj.imported_sum.toLocaleString('it-IT', { minimumFractionDigits: 2 })}</span></div>}
                                <p className="text-xs text-muted-foreground mt-1">Campo: <code>{adj.applied_to}</code></p>
                              </div>
                            ))}
                          </AlertDescription>
                        </Alert>
                      )}
                      {riserve && (
                        <Alert>
                          <CheckCircle2 className="h-4 w-4" />
                          <AlertTitle>Calcolo Riserve Anno {year}</AlertTitle>
                          <AlertDescription>
                            <div className="bg-muted rounded-md p-3 text-sm">
                              <div className="flex justify-between"><span>Patrimonio Netto (XBRL):</span><span className="font-medium">{'\u20AC'}{riserve.xbrl_total.toLocaleString('it-IT', { minimumFractionDigits: 2 })}</span></div>
                              <div className="flex justify-between text-muted-foreground"><span className="pl-4">- Capitale + Utile:</span><span>-{'\u20AC'}{riserve.imported_sum.toLocaleString('it-IT', { minimumFractionDigits: 2 })}</span></div>
                              <div className="flex justify-between border-t pt-1 mt-1 font-semibold"><span>= Riserve:</span><span>{'\u20AC'}{riserve.adjustment.toLocaleString('it-IT', { minimumFractionDigits: 2 })}</span></div>
                            </div>
                          </AlertDescription>
                        </Alert>
                      )}
                    </div>
                  );
                })}

                {Object.values(xbrlResult.reconciliation_info).every(info => {
                  if (!info.reconciliation_adjustments) return true;
                  const { riserve, ...actualAdjustments } = info.reconciliation_adjustments;
                  return Object.keys(actualAdjustments).length === 0;
                }) && (
                  <Alert>
                    <CheckCircle2 className="h-4 w-4" />
                    <AlertTitle>Importazione Perfetta - Approccio VBA</AlertTitle>
                    <AlertDescription>Nessun aggiustamento necessario! I totali aggregati XBRL sono stati importati direttamente.</AlertDescription>
                  </Alert>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* CSV Results */}
      {csvResult && (
        <Card className="mt-6 border-green-200 dark:border-green-800">
          <CardHeader>
            <CardTitle className="text-green-700 dark:text-green-400 flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5" />
              Importazione completata!
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card><CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-1">Tipo Bilancio</p>
                <p className="text-lg font-semibold">{csvResult.balance_sheet_type}</p>
                <p className="text-sm text-muted-foreground mt-2">Anni: {csvResult.years.join(", ")}</p>
              </CardContent></Card>
              <Card><CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-1">Righe Processate</p>
                <p className="text-lg font-semibold">{csvResult.rows_processed}</p>
                <p className="text-sm text-muted-foreground mt-2">Campi SP: {csvResult.balance_sheet_fields_imported}</p>
              </CardContent></Card>
              <Card><CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-1">Campi CE</p>
                <p className="text-lg font-semibold">{csvResult.income_statement_fields_imported}</p>
              </CardContent></Card>
            </div>
          </CardContent>
        </Card>
      )}

      {/* PDF Results */}
      {pdfResult && (
        <Card className="mt-6 border-green-200 dark:border-green-800">
          <CardHeader>
            <CardTitle className="text-green-700 dark:text-green-400 flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5" />
              Estrazione PDF completata!
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <Card><CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-1">Azienda</p>
                <p className="text-lg font-semibold">{pdfResult.company_name}</p>
                <p className="text-sm text-muted-foreground mt-2">Anno Fiscale: {pdfResult.fiscal_year}</p>
              </CardContent></Card>
              <Card><CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-1">Formato Rilevato</p>
                <p className="text-lg font-semibold capitalize">{pdfResult.format}</p>
                <p className="text-sm text-muted-foreground mt-2">Confidence: {(pdfResult.confidence_score * 100).toFixed(0)}%</p>
              </CardContent></Card>
              <Card><CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-1">Tempo Elaborazione</p>
                <p className="text-lg font-semibold">{pdfResult.extraction_time_seconds.toFixed(1)}s</p>
                <p className="text-sm text-muted-foreground mt-2">Record: SP: {pdfResult.balance_sheet_id}, CE: {pdfResult.income_statement_id}</p>
              </CardContent></Card>
            </div>

            {pdfResult.warnings && pdfResult.warnings.length > 0 && (
              <Alert variant="destructive" className="mb-4">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Avvisi</AlertTitle>
                <AlertDescription>
                  <ul className="text-sm space-y-1">{pdfResult.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
                </AlertDescription>
              </Alert>
            )}

            <Alert>
              <CheckCircle2 className="h-4 w-4" />
              <AlertDescription>
                <strong>{pdfResult.message}</strong>
                <br /><span className="text-sm">Puoi ora visualizzare i dati nelle sezioni Analisi e Forecast</span>
              </AlertDescription>
            </Alert>
          </CardContent>
        </Card>
      )}

      {/* Guide */}
      <Card className="mt-6">
        <CardContent className="pt-6">
          <details>
            <summary className="cursor-pointer font-semibold text-foreground flex items-center gap-2">
              <Info className="h-4 w-4" />
              Guida all&apos;Importazione
            </summary>
            <div className="mt-4 space-y-4 text-sm text-muted-foreground">
              <div>
                <h4 className="font-semibold text-foreground mb-2">XBRL Import (Approccio VBA)</h4>
                <ol className="list-decimal list-inside space-y-1">
                  <li>Seleziona un file XBRL (.xbrl o .xml) scaricato dal Registro Imprese</li>
                  <li>Il sistema riconoscerà automaticamente la versione della tassonomia</li>
                  <li>I totali aggregati ufficiali vengono estratti direttamente</li>
                  <li>L&apos;azienda verrà creata automaticamente con i dati dal file</li>
                  <li>Verranno importati tutti gli anni presenti nel file</li>
                </ol>
              </div>
              <div>
                <h4 className="font-semibold text-foreground mb-2">CSV Import</h4>
                <ol className="list-decimal list-inside space-y-1">
                  <li>Esporta il bilancio da TEBE in formato CSV</li>
                  <li>Crea prima l&apos;azienda (o usa XBRL import)</li>
                  <li>Seleziona l&apos;azienda, carica il file CSV e specifica gli anni</li>
                </ol>
              </div>
            </div>
          </details>
        </CardContent>
      </Card>
    </div>
  );
}
