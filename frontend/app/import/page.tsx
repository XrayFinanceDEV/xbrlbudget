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
      setError("Devi selezionare un'azienda per aggiornarla");
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
      setError("Devi selezionare un'azienda prima di importare CSV");
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
            <h3 className="font-semibold text-blue-900 mb-2">Formato supportato: File XBRL secondo tassonomia italiana (OIC)</h3>
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• Versioni supportate: 2018-11-04, 2017-07-06, 2016-11-14, 2015-12-14, 2014-11-17, 2011-01-04</li>
              <li>• L'azienda verrà creata automaticamente se non esiste</li>
              <li>• Dati estratti: Stato Patrimoniale, Conto Economico, dati anagrafici</li>
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
                    💡 Se esiste già un'azienda con la stessa P.IVA, verrà aggiornata. Altrimenti ne verrà creata una nuova.
                  </p>
                </div>
              ) : selectedCompanyId ? (
                <div className="bg-blue-50 border border-blue-200 rounded-md p-3">
                  <p className="text-sm text-blue-800">
                    💡 I dati dell'azienda selezionata verranno aggiornati
                  </p>
                </div>
              ) : (
                <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3">
                  <p className="text-sm text-yellow-800">
                    ⚠️ Nessuna azienda selezionata! Seleziona un'azienda o cambia modalità
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
              <li>• Richiede un'azienda già creata</li>
            </ul>
          </div>

          {!selectedCompanyId && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4 mb-6">
              <p className="text-sm text-yellow-800">
                ⚠️ Seleziona o crea un'azienda prima di importare CSV
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
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
            📖 Guida all'Importazione
          </summary>
          <div className="mt-4 space-y-4 text-sm text-gray-700">
            <div>
              <h4 className="font-semibold mb-2">XBRL Import</h4>
              <ol className="list-decimal list-inside space-y-1">
                <li>Seleziona un file XBRL (.xbrl o .xml) scaricato dal Registro Imprese</li>
                <li>Il sistema riconoscerà automaticamente la versione della tassonomia</li>
                <li>L'azienda verrà creata automaticamente con i dati dal file</li>
                <li>Verranno importati tutti gli anni presenti nel file</li>
              </ol>
            </div>
            <div>
              <h4 className="font-semibold mb-2">CSV Import</h4>
              <ol className="list-decimal list-inside space-y-1">
                <li>Esporta il bilancio da TEBE in formato CSV</li>
                <li>Crea prima l'azienda (o usa XBRL import)</li>
                <li>Seleziona l'azienda nel menù in alto</li>
                <li>Carica il file CSV e specifica gli anni</li>
                <li>Il sistema importerà automaticamente SP e CE</li>
              </ol>
            </div>
            <div>
              <h4 className="font-semibold mb-2">Formato Dati</h4>
              <ul className="list-disc list-inside space-y-1">
                <li><strong>Stato Patrimoniale:</strong> Tutte le voci attivo e passivo</li>
                <li><strong>Conto Economico:</strong> Valore della produzione e costi</li>
                <li><strong>Metadati:</strong> Ragione sociale, P.IVA, settore</li>
              </ul>
            </div>
          </div>
        </details>
      </div>
    </div>
  );
}
