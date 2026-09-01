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
import {
  ingressoNuovaPratica,
  ingressoRiprendi,
  type IngressoPratica,
  type WorkflowPratica,
} from "@/lib/pratica-ingresso";
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
  ChevronDown,
  ChevronRight,
  MoreHorizontal,
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
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

/**
 * Le DUE voci del tipo di pratica, in linea.
 *
 * Un solo componente per i due punti in cui una pratica nasce — sotto la riga
 * di un'azienda e subito dopo «Nuova azienda» — perché la regola è una sola: il
 * tipo si chiede sempre DOPO aver chiesto la pratica, mai prima. Erano due card
 * a tutta larghezza, ed erano il terzo modo di iniziare: quello che entrava con
 * `companyId: null`.
 */
function SceltaTipoPratica({
  onScegli,
  onAnnulla,
}: {
  onScegli: (workflow: WorkflowPratica) => void;
  onAnnulla?: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-dashed border-border py-3">
      <span className="text-sm text-muted-foreground">Che tipo di pratica?</span>
      <Button size="sm" variant="outline" onClick={() => onScegli("bilancio")}>
        <CalendarRange className="h-4 w-4 mr-1" /> Da bilancio
      </Button>
      <Button size="sm" variant="outline" onClick={() => onScegli("startup")}>
        <Rocket className="h-4 w-4 mr-1" /> Startup
      </Button>
      {onAnnulla && (
        <Button size="sm" variant="ghost" onClick={onAnnulla}>
          <X className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}

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

  // Tendina: una sola azienda aperta per volta.
  const [openCompanyId, setOpenCompanyId] = useState<number | null>(null);
  // Quale «Nuova pratica» sta chiedendo il tipo.
  const [chooserCompanyId, setChooserCompanyId] = useState<number | null>(null);

  // Create-company form
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newTaxId, setNewTaxId] = useState("");
  const [newSector, setNewSector] = useState(1);
  const [saving, setSaving] = useState(false);
  // L'azienda appena creata, in attesa che si scelga il tipo della sua prima
  // pratica: nessuno crea un'azienda per guardarla.
  const [createdCompanyId, setCreatedCompanyId] = useState<number | null>(null);

  // Edit-company form
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editTaxId, setEditTaxId] = useState("");
  const [editSector, setEditSector] = useState(1);
  const [deletingId, setDeletingId] = useState<number | null>(null);

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

  /**
   * L'unico punto in cui si entra nel percorso.
   *
   * `setSelectedCompanyId` riceve sempre un id vero: non c'è più un ramo che
   * azzera la selezione per difendersi dall'auto-selezione di `AppContext`
   * (`companies[0]` quando non c'è né selezione né pratica attiva). Quella
   * regola resta dov'è, ma qui non ha più nulla da disfare — l'azienda è
   * decisa prima di partire, in tutti e tre gli ingressi.
   */
  const entra = (ingresso: IngressoPratica) => {
    setStartupMode(ingresso.startupMode);
    setSelectedCompanyId(ingresso.pratica.companyId);
    startPratica(ingresso.pratica);
    router.push(ingresso.route);
  };

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
      setNewName("");
      setNewTaxId("");
      setNewSector(1);
      // Creata: ora si chiede il tipo, con le STESSE due voci della tendina, e
      // si entra. La schermata non torna indietro.
      setCreatedCompanyId(company.id);
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

  const nuovaPratica = (companyId: number, workflow: WorkflowPratica) => {
    setChooserCompanyId(null);
    setCreatedCompanyId(null);
    setShowCreateForm(false);
    entra(ingressoNuovaPratica(companyId, workflow));
  };

  const riprendi = (companyId: number, s: ScenarioSummary) => {
    entra(ingressoRiprendi(companyId, s));
  };

  const daEliminare = companies.find((c) => c.id === deletingId) ?? null;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <PageHeader
        title="Aziende & Pratiche"
        description="Le tue pratiche, raggruppate per azienda"
        icon={<Building2 className="h-6 w-6" />}
      >
        {/*
          Una sola azione in testata. «Nuova pratica» qui non esiste più: era
          il terzo modo di iniziare, entrava con `companyId: null`, e da lì
          Anagrafiche è un form di sola creazione — è così che nasceva
          l'azienda doppia. Una pratica si chiede solo DENTRO un'azienda.
        */}
        <Button onClick={() => { setShowCreateForm((v) => !v); setCreatedCompanyId(null); }}>
          <Plus className="h-4 w-4 mr-1" /> Nuova azienda
        </Button>
      </PageHeader>

      {/* Create-company form */}
      {showCreateForm && (
        <Card className="mb-6">
          <CardHeader><CardTitle className="text-base">Nuova Azienda</CardTitle></CardHeader>
          <CardContent>
            {createdCompanyId === null ? (
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
            ) : (
              // Creata: si entra subito nella sua prima pratica. Il tipo si
              // chiede anche qui, e non si dà per scontato l'import: una
              // startup è per definizione il caso in cui un bilancio storico
              // NON esiste, ed è proprio quando si crea un'azienda nuova.
              <SceltaTipoPratica
                onScegli={(workflow) => nuovaPratica(createdCompanyId, workflow)}
                onAnnulla={() => { setCreatedCompanyId(null); setShowCreateForm(false); }}
              />
            )}
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
          Nessuna azienda presente. Crea la prima azienda per iniziare.
        </div>
      ) : (
        <div className="space-y-3">
          {companies.map((company) => {
            const isEditing = editingId === company.id;
            const isOpen = openCompanyId === company.id;
            const pratiche = company.scenarios;
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
                      {/*
                        La riga INTERA apre e chiude il gruppo: il bersaglio è
                        tutta la riga, non la sola freccia.
                      */}
                      <button
                        type="button"
                        className="flex flex-1 items-center gap-3 text-left"
                        onClick={() => setOpenCompanyId(isOpen ? null : company.id)}
                        aria-expanded={isOpen}
                      >
                        {isOpen
                          ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                          : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
                        <CardTitle className="flex flex-wrap items-center gap-3 text-base">
                          {company.name}
                          <Badge variant="secondary">{getSectorName(company.sector)}</Badge>
                          {company.tax_id && (
                            <span className="text-xs font-normal text-muted-foreground">
                              P.IVA {company.tax_id}
                            </span>
                          )}
                        </CardTitle>
                        <span className="text-xs text-muted-foreground">
                          {pratiche.length === 0
                            ? "nessuna pratica"
                            : `${pratiche.length} ${pratiche.length === 1 ? "pratica" : "pratiche"}`}
                        </span>
                      </button>
                      {/*
                        Manutenzione, non un modo di iniziare un lavoro: dietro
                        un ⋯ non compete con «Riprendi» e «Nuova pratica».
                        Resta però RAGGIUNGIBILE su ogni azienda, gruppi vuoti
                        compresi — `deleteCompany` è chiamata da questo solo
                        punto in tutta l'app, e con un tetto di 50 aziende
                        un'azienda invisibile e ineliminabile occuperebbe una
                        casella per sempre.
                      */}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button size="sm" variant="ghost" aria-label={`Azioni su ${company.name}`}>
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleStartEdit(company)}>
                            <Pencil className="h-4 w-4 mr-2" /> Rinomina
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            className="text-destructive focus:text-destructive"
                            onClick={() => setDeletingId(company.id)}
                          >
                            <Trash2 className="h-4 w-4 mr-2" /> Elimina
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  )}
                </CardHeader>

                {isOpen && !isEditing && (
                  <CardContent className="pt-0">
                    {pratiche.map((s) => (
                      <div key={s.id} className="flex flex-wrap items-center gap-3 border-t border-dashed border-border py-2 text-sm">
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
                        <Button size="sm" variant="outline" onClick={() => riprendi(company.id, s)}>
                          Riprendi <ArrowRight className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                    {chooserCompanyId === company.id ? (
                      <SceltaTipoPratica
                        onScegli={(workflow) => nuovaPratica(company.id, workflow)}
                        onAnnulla={() => setChooserCompanyId(null)}
                      />
                    ) : (
                      <div className="border-t border-dashed border-border pt-3">
                        <Button size="sm" variant="outline" onClick={() => setChooserCompanyId(company.id)}>
                          <Plus className="h-4 w-4 mr-1" /> Nuova pratica
                        </Button>
                      </div>
                    )}
                  </CardContent>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {/*
        Un solo dialogo per tutte le righe, guidato da `deletingId`: il menù ⋯
        si chiude quando lo si sceglie, e un AlertDialog annidato dentro un
        DropdownMenuItem sparirebbe con lui prima di comparire.

        Il testo NON si abbrevia: la cancellazione è in cascata
        (`cascade="all, delete-orphan"` su ogni relazione sotto Company), e
        deve nominare per esteso ciò che porta via.
      */}
      <AlertDialog open={daEliminare !== null} onOpenChange={(open) => !open && setDeletingId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Elimina azienda</AlertDialogTitle>
            <AlertDialogDescription>
              Eliminare &quot;{daEliminare?.name}&quot; e tutti i dati associati
              (bilanci, scenari, previsioni)? Questa azione non può essere annullata.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annulla</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => { if (deletingId !== null) handleDelete(deletingId); setDeletingId(null); }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              Elimina
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
