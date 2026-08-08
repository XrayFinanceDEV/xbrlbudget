"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { usePratica } from "@/contexts/PraticaContext";
import {
  getCompaniesWithScenarios,
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
  const { setStartupMode, setSelectedCompanyId, refreshCompanies } = useApp();
  const { startPratica } = usePratica();

  const [companies, setCompanies] = useState<CompanyWithScenarios[]>([]);
  const [loading, setLoading] = useState(true);
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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getCompaniesWithScenarios();
      setCompanies(data);
    } catch (err) {
      console.error("Error loading companies:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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
      await Promise.all([load(), refreshCompanies()]);
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
      await Promise.all([load(), refreshCompanies()]);
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
      await Promise.all([load(), refreshCompanies()]);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Errore durante l'eliminazione");
    }
  };

  // Riprendi una pratica: popola il context, poi apri il posto giusto.
  // Uno scenario budget legacy non ha una fase ANALISI ricostruibile: si apre
  // direttamente sul budget, con gli step di analisi disabilitati.
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
      {loading ? (
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
                      <div className="flex gap-1">
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
                      Nessuna pratica. Importa un bilancio o avvia una nuova pratica.
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
