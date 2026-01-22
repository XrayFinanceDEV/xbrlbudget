"use client";

import { useState } from "react";
import { useApp } from "@/contexts/AppContext";
import { importXBRL, importCSV, type XBRLImportResult, type CSVImportResult } from "@/lib/api";

type ImportType = "xbrl" | "csv";
type ImportMode = "update" | "create";

export default function ImportPage() {
  const { selectedCompanyId, setSelectedCompanyId } = useApp();

  const [importType, setImportType] = useState<ImportType>("xbrl");
  const [importMode, setImportMode] = useState<ImportMode>("create");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [year1, setYear1] = useState<number>(2024);
  const [year2, setYear2] = useState<number>(2023);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [xbrlResult, setXbrlResult] = useState<XBRLImportResult | null>(null);
  const [csvResult, setCsvResult] = useState<CSVImportResult | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setSelectedFile(file);
    setError(null);
    setXbrlResult(null);
    setCsvResult(null);
  };

  const handleXBRLImport = async () => {
    if (!selectedFile) {
      setError("Seleziona un file prima di procedere");
      return;
    }

    if (importMode === "update" && !selectedCompanyId) {
      setError("Devi selezionare un&apos;azienda per aggiornarla");
      return;
    }

    setLoading(true);
    setError(null);
    setXbrlResult(null);

    try {
      const companyId = importMode === "create" ? null : selectedCompanyId;
      const result = await importXBRL(selectedFile, companyId, importMode === "create");

      setXbrlResult(result);
      setSelectedCompanyId(result.company_id);
      setSelectedFile(null);

      // Reset file input
      const fileInput = document.getElementById("file-upload") as HTMLInputElement;
      if (fileInput) fileInput.value = "";
    } catch (err: any) {
      console.error("Import error:", err);
      setError(err.response?.data?.detail?.error || err.message || "Errore durante l'importazione");
    } finally {
      setLoading(false);
    }
  };

  const handleCSVImport = async () => {
    if (!selectedFile) {
      setError("Seleziona un file prima di procedere");
      return;
    }

    if (!selectedCompanyId) {
      setError("Devi selezionare un&apos;azienda prima di importare CSV");
      return;
    }

    setLoading(true);
    setError(null);
    setCsvResult(null);

    try {
      const result = await importCSV(selectedFile, selectedCompanyId, year1, year2);

      setCsvResult(result);
      setSelectedFile(null);

      // Reset file input
      const fileInput = document.getElementById("file-upload") as HTMLInputElement;
      if (fileInput) fileInput.value = "";
    } catch (err: any) {
      console.error("Import error:", err);
      setError(err.response?.data?.detail?.error || err.message || "Errore durante l'importazione");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">📥 Importazione Dati</h1>
      <p className="text-gray-600 mb-6">Importa bilanci da file XBRL o CSV</p>

      {/* Import Type Selection */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-3">Tipo di File</label>
        <div className="flex gap-4">
          <button
            onClick={() => {
              setImportType("xbrl");
              setSelectedFile(null);
              setError(null);
              setXbrlResult(null);
              setCsvResult(null);
            }}
            className={`px-6 py-2 rounded-md font-medium transition-colors ${
              importType === "xbrl"
                ? "bg-blue-600 text-white"
                : "bg-gray-200 text-gray-700 hover:bg-gray-300"
            }`}
          >
            XBRL (formato italiano)
          </button>
          <button
            onClick={() => {
              setImportType("csv");
              setSelectedFile(null);
              setError(null);
              setXbrlResult(null);
              setCsvResult(null);
            }}
            className={`px-6 py-2 rounded-md font-medium transition-colors ${
              importType === "csv"
                ? "bg-blue-600 text-white"
                : "bg-gray-200 text-gray-700 hover:bg-gray-300"
            }`}
          >
            CSV (da conversione TEBE)
          </button>
        </div>
      </div>

      {/* XBRL Import Section */}
      {importType === "xbrl" && (
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">📄 Importazione XBRL</h2>

          <div className="bg-blue-50 border border-blue-200 rounded-md p-4 mb-6">
            <h3 className="font-semibold text-blue-900 mb-2">📋 Formato supportato: File XBRL secondo tassonomia italiana (OIC)</h3>
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• Versioni supportate: 2018-11-04, 2017-07-06, 2016-11-14, 2015-12-14, 2014-11-17, 2011-01-04</li>
              <li>• Schemi: Ordinario, Abbreviato, Micro (rilevamento automatico)</li>
              <li>• L&apos;azienda verrà creata automaticamente se non esiste</li>
              <li>• Dati estratti: Stato Patrimoniale, Conto Economico, dati anagrafici</li>
            </ul>
          </div>

          <div className="bg-green-50 border border-green-200 rounded-md p-4 mb-6">
            <h3 className="font-semibold text-green-900 mb-2">✅ Approccio VBA - Totali Aggregati</h3>
            <p className="text-sm text-green-800 mb-2">
              Il sistema utilizza i <strong>totali aggregati ufficiali</strong> del file XBRL (es. TotaleCrediti, TotaleDebiti, TotaleRimanenze)
              invece di mappare centinaia di voci individuali.
            </p>
            <ul className="text-sm text-green-800 space-y-1">
              <li>• <strong>Garanzia di accuratezza:</strong> Corrispondenza perfetta con i totali XBRL ufficiali (0 € di differenza)</li>
              <li>• <strong>Completezza automatica:</strong> Tutte le sotto-voci vengono catturate nei totali, anche quelle non mappate singolarmente</li>
              <li>• <strong>Robustezza:</strong> Funziona con tutti i tipi di schema (Ordinario/Abbreviato/Micro)</li>
            </ul>
          </div>

          {/* File Upload */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Carica file XBRL
            </label>
            <input
              id="file-upload"
              type="file"
              accept=".xbrl,.xml"
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none"
            />
            {selectedFile && (
              <p className="mt-2 text-sm text-gray-600">
                File selezionato: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(2)} KB)
              </p>
            )}
          </div>

          {/* Import Mode Selection */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-3">
                Modalità Importazione
              </label>
              <div className="space-y-2">
                <label className="flex items-center">
                  <input
                    type="radio"
                    value="update"
                    checked={importMode === "update"}
                    onChange={(e) => setImportMode(e.target.value as ImportMode)}
                    className="mr-2"
                  />
                  <span className="text-sm">Aggiorna azienda esistente</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="radio"
                    value="create"
                    checked={importMode === "create"}
                    onChange={(e) => setImportMode(e.target.value as ImportMode)}
                    className="mr-2"
                  />
                  <span className="text-sm">Crea nuova azienda</span>
                </label>
              </div>
            </div>

            <div>
              {importMode === "create" ? (
                <div className="bg-blue-50 border border-blue-200 rounded-md p-3">
                  <p className="text-sm text-blue-800">
                    💡 Se esiste già un&apos;azienda con la stessa P.IVA, verrà aggiornata. Altrimenti ne verrà creata una nuova.
                  </p>
                </div>
              ) : selectedCompanyId ? (
                <div className="bg-blue-50 border border-blue-200 rounded-md p-3">
                  <p className="text-sm text-blue-800">
                    💡 I dati dell&apos;azienda selezionata verranno aggiornati
                  </p>
                </div>
              ) : (
                <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3">
                  <p className="text-sm text-yellow-800">
                    ⚠️ Nessuna azienda selezionata! Seleziona un&apos;azienda o cambia modalità
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Import Button */}
          <button
            onClick={handleXBRLImport}
            disabled={loading || !selectedFile || (importMode === "update" && !selectedCompanyId)}
            className="w-full bg-blue-600 text-white py-3 px-4 rounded-md font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Importazione in corso..." : "🚀 Importa XBRL"}
          </button>
        </div>
      )}

      {/* CSV Import Section */}
      {importType === "csv" && (
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">📄 Importazione CSV</h2>

          <div className="bg-blue-50 border border-blue-200 rounded-md p-4 mb-6">
            <h3 className="font-semibold text-blue-900 mb-2">Formato supportato: CSV esportato da conversione TEBE</h3>
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• Delimitatore: punto e virgola (;)</li>
              <li>• Codifica: UTF-8</li>
              <li>• Formato: Descrizione; Anno1; Anno2; Tag; Unità</li>
              <li>• Richiede un&apos;azienda già creata</li>
            </ul>
          </div>

          {!selectedCompanyId && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4 mb-6">
              <p className="text-sm text-yellow-800">
                ⚠️ Seleziona o crea un&apos;azienda prima di importare CSV
              </p>
            </div>
          )}

          {/* File Upload */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Carica file CSV
            </label>
            <input
              id="file-upload"
              type="file"
              accept=".csv"
              onChange={handleFileChange}
              disabled={!selectedCompanyId}
              className="block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none disabled:bg-gray-200 disabled:cursor-not-allowed"
            />
            {selectedFile && (
              <p className="mt-2 text-sm text-gray-600">
                File selezionato: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(2)} KB)
              </p>
            )}
          </div>

          {/* Year Selection */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Anno Corrente
              </label>
              <input
                type="number"
                value={year1}
                onChange={(e) => setYear1(parseInt(e.target.value))}
                min={2000}
                max={2100}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Anno Precedente
              </label>
              <input
                type="number"
                value={year2}
                onChange={(e) => setYear2(parseInt(e.target.value))}
                min={2000}
                max={2100}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Import Button */}
          <button
            onClick={handleCSVImport}
            disabled={loading || !selectedFile || !selectedCompanyId}
            className="w-full bg-blue-600 text-white py-3 px-4 rounded-md font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Importazione in corso..." : "🚀 Importa CSV"}
          </button>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="mt-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          ❌ {error}
        </div>
      )}

      {/* XBRL Success Results */}
      {xbrlResult && (
        <div className="mt-6 bg-green-50 border border-green-200 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-green-900 mb-4">
            ✅ Importazione completata! {xbrlResult.company_created ? "Nuova azienda creata." : "Azienda esistente aggiornata."}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div className="bg-white rounded-md p-4">
              <p className="text-sm text-gray-600 mb-1">Azienda</p>
              <p className="text-lg font-semibold text-gray-900">{xbrlResult.company_name}</p>
              <p className="text-sm text-gray-600 mt-2">P.IVA</p>
              <p className="text-md font-medium text-gray-900">{xbrlResult.tax_id}</p>
            </div>
            <div className="bg-white rounded-md p-4">
              <p className="text-sm text-gray-600 mb-1">Tassonomia</p>
              <p className="text-lg font-semibold text-gray-900">{xbrlResult.taxonomy_version}</p>
              <p className="text-sm text-gray-600 mt-2">Contesti</p>
              <p className="text-md font-medium text-gray-900">{xbrlResult.contexts_found}</p>
            </div>
            <div className="bg-white rounded-md p-4">
              <p className="text-sm text-gray-600 mb-1">Anni Importati</p>
              <p className="text-lg font-semibold text-gray-900">{xbrlResult.years_imported}</p>
              <p className="text-sm text-gray-600 mt-2">Anni</p>
              <p className="text-md font-medium text-gray-900">{xbrlResult.years.join(", ")}</p>
            </div>
          </div>

          {/* Reconciliation Info */}
          {xbrlResult.reconciliation_info && (
            <div className="mt-4">
              {Object.entries(xbrlResult.reconciliation_info).map(([year, info]) => {
                const hasAdjustments = info.reconciliation_adjustments &&
                  Object.keys(info.reconciliation_adjustments).length > 0;

                if (!hasAdjustments) return null;

                // Separate reserves from actual adjustments
                const { riserve, ...actualAdjustments } = info.reconciliation_adjustments || {};
                const hasActualAdjustments = Object.keys(actualAdjustments).length > 0;

                return (
                  <div key={year}>
                    {/* Show actual reconciliation adjustments (credits/debts) */}
                    {hasActualAdjustments && (
                      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-3">
                        <h4 className="font-semibold text-blue-900 mb-3">
                          🔧 Riconciliazione Anno {year}
                        </h4>
                        <p className="text-sm text-blue-800 mb-3">
                          Con l&apos;approccio VBA, il sistema utilizza i totali aggregati ufficiali dal file XBRL.
                          Eventuali aggiustamenti vengono applicati solo se necessario per bilanciare perfettamente lo Stato Patrimoniale:
                        </p>
                        {Object.entries(actualAdjustments).map(([category, adj]) => (
                      <div key={category} className="bg-white rounded-md p-3 mb-2">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <p className="font-semibold text-gray-900 mb-2">
                              {category === 'crediti' ? '📊 CREDITI' : category === 'debiti' ? '📊 DEBITI' : '💰 RISERVE'}
                            </p>
                            <div className="text-sm text-gray-700 space-y-1">
                              <div className="flex justify-between">
                                <span>Totale XBRL ufficiale:</span>
                                <span className="font-medium">€{adj.xbrl_total.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                              </div>
                              {adj.imported_sum === 0 && category !== 'riserve' ? (
                                <div className="bg-blue-50 rounded p-2 my-1">
                                  <p className="text-xs text-blue-800">
                                    <strong>✓ Approccio VBA:</strong> Nessuna voce dettagliata trovata nel file XBRL.
                                    Il sistema utilizza il totale aggregato ufficiale <code className="font-mono">Totale{category === 'crediti' ? 'Crediti' : 'Debiti'}</code> direttamente.
                                  </p>
                                </div>
                              ) : (
                                <div className="flex justify-between">
                                  <span>Voci dettagliate importate:</span>
                                  <span className="font-medium">€{adj.imported_sum.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                                </div>
                              )}
                              <div className="flex justify-between border-t border-gray-300 pt-1 mt-1">
                                <span className="font-semibold">
                                  {category === 'riserve'
                                    ? 'Riserve calcolate (Patrimonio - Capitale - Utile):'
                                    : adj.imported_sum === 0
                                    ? `Totale applicato a ${category === 'crediti' ? 'CREDITI' : 'DEBITI'}:`
                                    : `${adj.adjustment > 0 ? 'Aggiunto a' : 'Sottratto da'} ${category === 'crediti' ? 'ALTRI CREDITI' : 'ALTRI DEBITI'}:`
                                  }
                                </span>
                                <span className={`font-bold ${category === 'riserve' ? 'text-green-600' : adj.imported_sum === 0 ? 'text-green-600' : adj.adjustment >= 0 ? 'text-blue-600' : 'text-red-600'}`}>
                                  {category === 'riserve' || adj.imported_sum === 0 ? '' : adj.adjustment >= 0 ? '+' : ''}€{(adj.imported_sum === 0 ? adj.xbrl_total : adj.adjustment).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                        <div className="mt-2 text-xs text-gray-600 bg-gray-50 rounded px-2 py-1">
                          💡 Campo tecnico: <code className="font-mono">{adj.applied_to}</code>
                        </div>
                      </div>
                    ))}
                        <div className="mt-3 text-xs text-blue-700 bg-blue-100 rounded-md p-2">
                          <p className="mb-1">
                            <strong>ℹ️ Approccio VBA - Totali Aggregati:</strong>
                          </p>
                          <p>
                            Il sistema utilizza i totali ufficiali XBRL (TotaleCrediti, TotaleDebiti) che includono
                            tutte le sotto-voci, anche quelle non mappate (es. imposte anticipate, debiti verso controllate).
                          </p>
                        </div>
                      </div>
                    )}

                    {/* Show reserves calculation separately (not as an adjustment) */}
                    {riserve && (
                      <div className="bg-green-50 border border-green-300 rounded-lg p-4 mb-3">
                        <h4 className="font-semibold text-green-900 mb-3">
                          💰 Calcolo Riserve Anno {year}
                        </h4>
                        <p className="text-sm text-green-800 mb-3">
                          Le riserve sono calcolate automaticamente come residuo del Patrimonio Netto.
                          Questo è il metodo standard per l&apos;accounting italiano:
                        </p>
                        <div className="bg-white rounded-md p-3">
                          <div className="text-sm text-gray-700 space-y-1">
                            <div className="flex justify-between">
                              <span>Patrimonio Netto Totale (XBRL):</span>
                              <span className="font-medium">€{riserve.xbrl_total.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            </div>
                            <div className="flex justify-between text-gray-600">
                              <span className="pl-4">- Capitale + Utile (importati):</span>
                              <span>-€{riserve.imported_sum.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            </div>
                            <div className="flex justify-between border-t-2 border-green-300 pt-2 mt-2">
                              <span className="font-semibold text-green-900">= Riserve (calcolate):</span>
                              <span className="font-bold text-green-600">€{riserve.adjustment.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            </div>
                          </div>
                          <div className="mt-3 text-xs text-gray-600 bg-gray-50 rounded px-2 py-1">
                            ℹ️ Include: riserva legale, riserva sovrapprezzo azioni, altre riserve, utili/perdite portati a nuovo
                          </div>
                          <div className="mt-2 text-xs text-gray-600 bg-gray-50 rounded px-2 py-1">
                            💡 Campo tecnico: <code className="font-mono">{riserve.applied_to}</code>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Show if NO adjustments were needed (excluding reserves which are always calculated) */}
              {Object.values(xbrlResult.reconciliation_info).every(info => {
                if (!info.reconciliation_adjustments) return true;
                const { riserve, ...actualAdjustments } = info.reconciliation_adjustments;
                return Object.keys(actualAdjustments).length === 0;
              }) && (
                <div className="bg-green-100 border border-green-300 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <div className="text-3xl">✅</div>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-green-900 mb-2">
                        Importazione Perfetta - Approccio VBA
                      </p>
                      <p className="text-sm text-green-800 mb-2">
                        <strong>Nessun aggiustamento necessario!</strong> I totali aggregati XBRL (TotaleCrediti, TotaleDebiti, TotaleRimanenze, ecc.)
                        sono stati importati direttamente dal file.
                      </p>
                      <div className="bg-white rounded-md p-3 mt-2">
                        <p className="text-xs text-gray-700 mb-1">
                          <strong>Cosa significa?</strong>
                        </p>
                        <ul className="text-xs text-gray-600 space-y-1">
                          <li>• Lo Stato Patrimoniale è perfettamente bilanciato (Attivo = Passivo)</li>
                          <li>• Tutti i valori corrispondono esattamente ai totali ufficiali del Registro Imprese</li>
                          <li>• Anche le voci non mappate individualmente sono incluse nei totali aggregati</li>
                          <li>• I calcoli degli indici finanziari si baseranno su dati certificati</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* CSV Success Results */}
      {csvResult && (
        <div className="mt-6 bg-green-50 border border-green-200 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-green-900 mb-4">
            ✅ Importazione completata con successo!
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white rounded-md p-4">
              <p className="text-sm text-gray-600 mb-1">Tipo Bilancio</p>
              <p className="text-lg font-semibold text-gray-900">{csvResult.balance_sheet_type}</p>
              <p className="text-sm text-gray-600 mt-2">Anni</p>
              <p className="text-md font-medium text-gray-900">{csvResult.years.join(", ")}</p>
            </div>
            <div className="bg-white rounded-md p-4">
              <p className="text-sm text-gray-600 mb-1">Righe Processate</p>
              <p className="text-lg font-semibold text-gray-900">{csvResult.rows_processed}</p>
              <p className="text-sm text-gray-600 mt-2">Campi SP</p>
              <p className="text-md font-medium text-gray-900">{csvResult.balance_sheet_fields_imported}</p>
            </div>
            <div className="bg-white rounded-md p-4">
              <p className="text-sm text-gray-600 mb-1">Campi CE</p>
              <p className="text-lg font-semibold text-gray-900">{csvResult.income_statement_fields_imported}</p>
            </div>
          </div>
        </div>
      )}

      {/* Quick Guide */}
      <div className="mt-6 bg-white shadow rounded-lg p-6">
        <details>
          <summary className="cursor-pointer font-semibold text-gray-900">
            📖 Guida all&apos;Importazione
          </summary>
          <div className="mt-4 space-y-4 text-sm text-gray-700">
            <div>
              <h4 className="font-semibold mb-2">XBRL Import (Approccio VBA)</h4>
              <ol className="list-decimal list-inside space-y-1">
                <li>Seleziona un file XBRL (.xbrl o .xml) scaricato dal Registro Imprese</li>
                <li>Il sistema riconoscerà automaticamente la versione della tassonomia</li>
                <li>I <strong>totali aggregati ufficiali</strong> vengono estratti direttamente (TotaleCrediti, TotaleDebiti, ecc.)</li>
                <li>L&apos;azienda verrà creata automaticamente con i dati dal file</li>
                <li>Verranno importati tutti gli anni presenti nel file</li>
                <li>Lo Stato Patrimoniale sarà sempre perfettamente bilanciato (0 € di differenza)</li>
              </ol>
              <div className="mt-3 bg-blue-50 border border-blue-200 rounded-md p-3">
                <p className="text-xs text-blue-800">
                  <strong>💡 Approccio VBA:</strong> Anziché mappare centinaia di voci individuali (es. CreditiVersoClienti, CreditiTributari),
                  il sistema utilizza i totali aggregati del file XBRL. Questo garantisce che <strong>tutte le sotto-voci</strong> vengano
                  automaticamente incluse, anche quelle non mappate esplicitamente (es. imposte anticipate, crediti diversi).
                </p>
              </div>
            </div>
            <div>
              <h4 className="font-semibold mb-2">CSV Import</h4>
              <ol className="list-decimal list-inside space-y-1">
                <li>Esporta il bilancio da TEBE in formato CSV</li>
                <li>Crea prima l&apos;azienda (o usa XBRL import)</li>
                <li>Seleziona l&apos;azienda nel menù in alto</li>
                <li>Carica il file CSV e specifica gli anni</li>
                <li>Il sistema importerà automaticamente SP e CE</li>
              </ol>
            </div>
            <div>
              <h4 className="font-semibold mb-2">Formato Dati Importati</h4>
              <ul className="list-disc list-inside space-y-1">
                <li><strong>Stato Patrimoniale:</strong> Immobilizzazioni, Attivo Circolante, Patrimonio Netto, Debiti (da totali aggregati)</li>
                <li><strong>Conto Economico:</strong> Valore della produzione, Costi, Risultato operativo</li>
                <li><strong>Metadati:</strong> Ragione sociale, P.IVA, settore</li>
              </ul>
            </div>
            <div className="bg-gray-50 border border-gray-300 rounded-md p-4">
              <h4 className="font-semibold mb-2 text-gray-900">🎯 Vantaggi Approccio VBA</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <p className="text-xs font-semibold text-gray-800 mb-1">✓ Completezza Garantita</p>
                  <p className="text-xs text-gray-600">
                    Cattura automaticamente tutte le sotto-voci, anche quelle non mappate singolarmente
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-800 mb-1">✓ Accuratezza al 100%</p>
                  <p className="text-xs text-gray-600">
                    I totali corrispondono esattamente ai valori ufficiali del Registro Imprese
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-800 mb-1">✓ Compatibilità Universale</p>
                  <p className="text-xs text-gray-600">
                    Funziona con tutti gli schemi (Ordinario, Abbreviato, Micro)
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-800 mb-1">✓ Semplicità</p>
                  <p className="text-xs text-gray-600">
                    Meno mappings da mantenere, risultati più affidabili
                  </p>
                </div>
              </div>
            </div>
          </div>
        </details>
      </div>
    </div>
  );
}
