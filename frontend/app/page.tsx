"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { usePratica } from "@/contexts/PraticaContext";
import {
  createCompany,
  updateCompany,
  deleteCompany,
} from "@/lib/api";
import type { CompanyWithScenarios, ScenarioSummary } from "@/types/api";
import { getSectorName } from "@/lib/formatters";
import { toast } from "sonner";
import {
  Building2,
  Plus,
  Pencil,
  Trash2,
  Check,
  X,
  Loader2,
  CalendarRange,
  Rocket,
  ArrowRight,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
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
import { PageHeader } from "@/components/page-header";

const SECTOR_OPTIONS: Record<number, string> = {
  1: "Industria, Alberghi (Proprietari), Agricoltura, Pesca",
  2: "Commercio",
  3: "Servizi (diversi da Autotrasporti) e Alberghi (Locatari)",
  4: "Autotrasporti",
  5: "Immobiliare",
  6: "Edilizia",
};

export default function Home() {
  const router = useRouter();
  // L'elenco aziende arriva SOLO da AppContext: è già protetto dall'attesa
  // dell'autenticazione (`authLoadingRef` in `loadCompanies`) e include gli
  // scenari. Un fetch proprio qui è ciò che produceva la corsa col token
  // dell'iframe — la home partiva senza `Authorization`, l'interceptor
  // chiedeva un token nuovo al parent, e niente rilanciava questo caricamento.
  const {
    companies,
    companiesLoaded,
    companiesError,
    setStartupMode,
    setSelectedCompanyId,
    refreshCompanies,
  } = useApp();
  const { startPratica } = usePratica();

  const [showNewPratica, setShowNewPratica] = useState(false);

  // Create-company form
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newTaxId, setNewTaxId] = useState("");
  const [newSector, setNewSector] = useState(1);
  const [saving, setSaving] = useState(false);

  // Edit-company form
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editTaxId, setEditTaxId] = useState("");
  const [editSector, setEditSector] = useState(1);

  // Landing on the home page always exits startup mode.
  useEffect(() => {
    setStartupMode(false);
  }, [setStartupMode]);

  // Rinfresca l'elenco ATTERRANDO sulla home.
  //
  // Non è un secondo percorso di caricamento — è lo stesso `loadCompanies` del
  // context, con la sua guardia su `authLoading`: la corsa nasceva da un fetch
  // PROPRIO, non guardato e mai rilanciato all'arrivo del token.
  //
  // Senza questa riga la home mostra dati fermi al primo caricamento della
  // sessione: `loadCompanies` è `useCallback(…, [])` e `authLoading` si
  // stabilizza una volta sola, quindi l'effetto del context scatta UNA volta
  // per sessione. Chi avvia una pratica, la fa creare uno scenario e poi esce
  // dal percorso ritrovava la propria scheda azienda senza «Riprendi» — la
  // pratica appena creata semplicemente non c'era, fino a un ricaricamento a
  // mano. Vale anche per il badge «in corso»/«bozza», che legge `has_forecast`.
  useEffect(() => {
    refreshCompanies();
  }, [refreshCompanies]);

  const handleCreate = async () => {
    if (!newName.trim()) {
      toast.error("Il nome dell'azienda è obbligatorio");
      return;
    }
    setSaving(true);
    try {
      const company = await createCompany({
        name: newName.trim(),
        tax_id: newTaxId.trim() || undefined,
        sector: newSector,
      });
      setSelectedCompanyId(company.id);
      setShowCreateForm(false);
      setNewName("");
      setNewTaxId("");
      setNewSector(1);
      toast.success("Azienda creata con successo");
      await refreshCompanies();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Errore durante la creazione");
    } finally {
      setSaving(false);
    }
  };

  const handleStartEdit = (c: CompanyWithScenarios) => {
    setEditingId(c.id);
    setEditName(c.name);
    setEditTaxId(c.tax_id || "");
    setEditSector(c.sector);
  };

  const handleSaveEdit = async () => {
    if (!editingId || !editName.trim()) return;
    setSaving(true);
    try {
      await updateCompany(editingId, {
        name: editName.trim(),
        tax_id: editTaxId.trim() || undefined,
        sector: editSector,
      });
      setEditingId(null);
      toast.success("Azienda aggiornata");
      await refreshCompanies();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Errore durante l'aggiornamento");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteCompany(id);
      setSelectedCompanyId(null);
      toast.success("Azienda eliminata");
      await refreshCompanies();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Errore durante l'eliminazione");
    }
  };

  // Avvia una pratica SU un'azienda che esiste già.
  //
  // Senza questo, un'azienda creata da "Nuova azienda" (o importata e poi
  // rimasta senza scenari) era irraggiungibile: le due card di "Nuova pratica"
  // partono per forza da `companyId: null`, AnagraficheStep con companyId null
  // è un form di CREAZIONE (ne avrebbe creata una seconda) e lo step Import è
  // bloccato finché `pratica.companyId` è null. L'unico bottone sulla scheda
  // azienda era "Riprendi", che esiste solo per gli scenari già creati.
  // AnagraficheStep dice "la scelta è già avvenuta sulla home": questo è il
  // punto in cui avviene.
  const startForCompany = (companyId: number) => {
    setStartupMode(false);
    setSelectedCompanyId(companyId);
    startPratica({
      workflow: "bilancio",
      companyId,
      analysisStep: "anagrafiche",
    });
    router.push("/pratica");
  };

  // Riprendi una pratica: popola il context, poi apri il posto giusto.
  // Uno scenario budget legacy non ha una fase ANALISI ricostruibile (nessun
  // infrannualeScenarioId, quindi nessun rettifiche_log da riaprire): si apre
  // direttamente sul budget, e lo stepper nasconde del tutto la fase Analisi
  // invece di mostrarla abilitata-ma-rotta (vedi pratica-steps.ts,
  // isLegacyBudgetResume). Nota: il gate rettifiche NON si propaga a nessuno
  // dei 6 step PREVISIONALE per questo percorso — vedi CLAUDE.md.
  const resume = (companyId: number, s: ScenarioSummary) => {
    setSelectedCompanyId(companyId);
    const isInfra = s.scenario_type === "infrannuale";
    startPratica({
      workflow: "bilancio",
      companyId,
      fiscalYear: isInfra ? s.base_year + 1 : s.base_year,
      periodMonths: isInfra ? s.period_months ?? 12 : 12,
      infrannualeScenarioId: isInfra ? s.id : null,
      budgetScenarioId: isInfra ? null : s.id,
      analysisStep: isInfra ? "rettifiche" : "anagrafiche",
    });
    router.push(isInfra ? "/pratica" : "/budget");
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <PageHeader
        title="Aziende & Pratiche"
        description="Le tue aziende e le relative pratiche di budget e infrannuale"
        icon={<Building2 className="h-6 w-6" />}
      >
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowCreateForm((v) => !v)}>
            <Plus className="h-4 w-4 mr-1" /> Nuova azienda
          </Button>
          <Button onClick={() => setShowNewPratica((v) => !v)}>
            <Plus className="h-4 w-4 mr-1" /> Nuova pratica
          </Button>
        </div>
      </PageHeader>

      {showNewPratica && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <Card className="cursor-pointer transition-colors hover:border-primary/50"
            onClick={() => {
              setStartupMode(false);
              // Riparte da una selezione pulita: senza questo l'auto-selezione di
              // AppContext (companies[0]) fa aprire Anagrafiche come EDIT di
              // un'azienda a caso invece che come nuova pratica.
              setSelectedCompanyId(null);
              // companyId resta null: l'azienda si sceglie o si crea nello step Anagrafiche.
              startPratica({ workflow: "bilancio", companyId: null, analysisStep: "anagrafiche" });
              router.push("/pratica");
            }}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <CalendarRange className="h-5 w-5 text-primary" /> Da bilancio
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Bilancio ufficiale o bilancio di verifica infrannuale. Import, rettifiche,
              confronto e budget in un unico percorso.
              <Button variant="outline" size="sm" className="mt-3 w-full">
                Avvia percorso <ArrowRight className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
          <Card className="cursor-pointer transition-colors hover:border-primary/50"
            onClick={() => {
              setStartupMode(true);
              setSelectedCompanyId(null);
              startPratica({ workflow: "startup", companyId: null, analysisStep: "anagrafiche" });
              router.push("/budget");
            }}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Rocket className="h-5 w-5 text-primary" /> Startup
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Business plan senza bilancio storico.
              <Button variant="outline" size="sm" className="mt-3 w-full">
                Crea business plan <ArrowRight className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Create-company form */}
      {showCreateForm && (
        <Card className="mb-6">
          <CardHeader><CardTitle className="text-base">Nuova Azienda</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div className="space-y-1">
                <Label>Nome *</Label>
                <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="es. ROSSI S.R.L." />
              </div>
              <div className="space-y-1">
                <Label>Partita IVA</Label>
                <Input value={newTaxId} onChange={(e) => setNewTaxId(e.target.value)} placeholder="es. 12345678901" />
              </div>
              <div className="space-y-1">
                <Label>Settore *</Label>
                <Select value={newSector.toString()} onValueChange={(v) => setNewSector(parseInt(v))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(SECTOR_OPTIONS).map(([value, label]) => (
                      <SelectItem key={value} value={value}>{value}. {label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex gap-2">
                <Button onClick={handleCreate} disabled={saving}>
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Crea
                </Button>
                <Button variant="outline" onClick={() => setShowCreateForm(false)}><X className="h-4 w-4" /></Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Companies + pratiche */}
      {/*
        Errore onesto, ma NON al posto dei dati che ci sono già.
        `companiesError` racconta l'ULTIMO caricamento: un refresh fallito dopo
        una cancellazione (rete instabile) lascia `companies` valido e pieno, e
        sostituirlo con la schermata d'errore farebbe sparire all'utente le
        aziende che possiede. Qui l'errore è una fascia SOPRA l'elenco; prende
        tutta la pagina solo quando non c'è nulla da mostrare.
      */}
      {companiesError && companies.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-yellow-500/40 bg-yellow-50 p-3 text-sm text-yellow-800 dark:bg-yellow-950/20 dark:text-yellow-300">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="flex-1">
            {companiesError} — l&apos;elenco qui sotto potrebbe non essere aggiornato.
          </span>
          <Button variant="outline" size="sm" onClick={() => refreshCompanies()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Riprova
          </Button>
        </div>
      )}

      {companiesError && companies.length === 0 ? (
        // Nessun dato da salvare: l'errore prende la pagina. «Nessuna azienda
        // presente» resta sotto, per il solo caso vero — caricamento riuscito
        // e zero aziende.
        <div className="py-12 text-center space-y-4">
          <p className="text-muted-foreground">{companiesError}</p>
          <Button variant="outline" onClick={() => refreshCompanies()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Riprova
          </Button>
        </div>
      ) : !companiesLoaded ? (
        <div className="py-12 text-center text-muted-foreground">
          <Loader2 className="h-8 w-8 animate-spin mx-auto" />
        </div>
      ) : companies.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground">
          Nessuna azienda presente. Crea la prima azienda o avvia una nuova pratica.
        </div>
      ) : (
        <div className="space-y-4">
          {companies.map((company) => {
            const isEditing = editingId === company.id;
            return (
              <Card key={company.id}>
                <CardHeader className="pb-3">
                  {isEditing ? (
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
                      <div className="space-y-1">
                        <Label>Nome</Label>
                        <Input value={editName} onChange={(e) => setEditName(e.target.value)} className="h-8" />
                      </div>
                      <div className="space-y-1">
                        <Label>P.IVA</Label>
                        <Input value={editTaxId} onChange={(e) => setEditTaxId(e.target.value)} className="h-8" />
                      </div>
                      <div className="space-y-1">
                        <Label>Settore</Label>
                        <Select value={editSector.toString()} onValueChange={(v) => setEditSector(parseInt(v))}>
                          <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {Object.entries(SECTOR_OPTIONS).map(([value, label]) => (
                              <SelectItem key={value} value={value}>{value}. {label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex gap-1">
                        <Button size="sm" onClick={handleSaveEdit} disabled={saving}>
                          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setEditingId(null)}><X className="h-3 w-3" /></Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between gap-3">
                      <CardTitle className="flex items-center gap-3 text-base">
                        {company.name}
                        <Badge variant="secondary">{getSectorName(company.sector)}</Badge>
                        {company.tax_id && <span className="text-xs font-normal text-muted-foreground">P.IVA {company.tax_id}</span>}
                      </CardTitle>
                      <div className="flex items-center gap-1">
                        <Button size="sm" variant="outline" onClick={() => startForCompany(company.id)}>
                          <Plus className="h-3 w-3 mr-1" /> Nuova pratica
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => handleStartEdit(company)}>
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button size="sm" variant="ghost"><Trash2 className="h-3 w-3 text-destructive" /></Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Elimina azienda</AlertDialogTitle>
                              <AlertDialogDescription>
                                Eliminare &quot;{company.name}&quot; e tutti i dati associati
                                (bilanci, scenari, previsioni)? Questa azione non può essere annullata.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Annulla</AlertDialogCancel>
                              <AlertDialogAction onClick={() => handleDelete(company.id)}
                                className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                                Elimina
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    </div>
                  )}
                </CardHeader>
                <CardContent className="pt-0">
                  {company.scenarios.length === 0 ? (
                    <p className="text-sm text-muted-foreground border-t border-dashed border-border pt-3">
                      Nessuna pratica. Usa &quot;Nuova pratica&quot; qui sopra per importare un
                      bilancio di questa azienda.
                    </p>
                  ) : (
                    company.scenarios.map((s) => (
                      <div key={s.id} className="flex items-center gap-3 border-t border-dashed border-border py-2 text-sm">
                        <Badge variant={s.has_forecast ? "default" : "secondary"}>
                          {s.has_forecast ? "in corso" : "bozza"}
                        </Badge>
                        <span className="font-medium">{s.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {s.scenario_type === "infrannuale"
                            ? `Infrannuale ${s.period_months ?? ""}M`
                            : "Budget"} · base {s.base_year}
                        </span>
                        <span className="flex-1" />
                        <Button size="sm" variant="outline" onClick={() => resume(company.id, s)}>
                          Riprendi <ArrowRight className="h-4 w-4" />
                        </Button>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
