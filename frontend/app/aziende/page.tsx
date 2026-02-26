"use client";

import { useState } from "react";
import { useApp } from "@/contexts/AppContext";
import {
  getCompanies,
  createCompany,
  updateCompany,
  deleteCompany,
  getCompanyYears,
  getBudgetScenarios,
} from "@/lib/api";
import type { Company, BudgetScenario } from "@/types/api";
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
  Calendar,
  FileSpreadsheet,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/page-header";
import { useEffect } from "react";

const SECTOR_OPTIONS: Record<number, string> = {
  1: "Industria, Alberghi (Proprietari), Agricoltura, Pesca",
  2: "Commercio",
  3: "Servizi (diversi da Autotrasporti) e Alberghi (Locatari)",
  4: "Autotrasporti",
  5: "Immobiliare",
  6: "Edilizia",
};

interface CompanyDetail {
  years: number[];
  scenarios: BudgetScenario[];
}

export default function AziendePage() {
  const {
    companies,
    selectedCompanyId,
    setSelectedCompanyId,
    refreshCompanies,
  } = useApp();

  const [companyDetails, setCompanyDetails] = useState<
    Record<number, CompanyDetail>
  >({});
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  // Create form state
  const [newName, setNewName] = useState("");
  const [newTaxId, setNewTaxId] = useState("");
  const [newSector, setNewSector] = useState(1);

  // Edit form state
  const [editName, setEditName] = useState("");
  const [editTaxId, setEditTaxId] = useState("");
  const [editSector, setEditSector] = useState(1);

  const [saving, setSaving] = useState(false);

  // Refresh companies list on mount and when page regains focus
  useEffect(() => {
    refreshCompanies();

    const handleFocus = () => refreshCompanies();
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [refreshCompanies]);

  // Load details for all companies
  useEffect(() => {
    if (companies.length === 0) return;

    const loadDetails = async () => {
      setLoadingDetails(true);
      const details: Record<number, CompanyDetail> = {};
      await Promise.all(
        companies.map(async (company) => {
          try {
            const [years, scenarios] = await Promise.all([
              getCompanyYears(company.id),
              getBudgetScenarios(company.id),
            ]);
            details[company.id] = { years, scenarios };
          } catch {
            details[company.id] = { years: [], scenarios: [] };
          }
        })
      );
      setCompanyDetails(details);
      setLoadingDetails(false);
    };
    loadDetails();
  }, [companies]);

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
      await refreshCompanies();
      setSelectedCompanyId(company.id);
      setShowCreateForm(false);
      setNewName("");
      setNewTaxId("");
      setNewSector(1);
      toast.success("Azienda creata con successo");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Errore durante la creazione";
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleStartEdit = (company: Company) => {
    setEditingId(company.id);
    setEditName(company.name);
    setEditTaxId(company.tax_id || "");
    setEditSector(company.sector);
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
      await refreshCompanies();
      setEditingId(null);
      toast.success("Azienda aggiornata");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Errore durante l'aggiornamento";
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteCompany(id);
      if (selectedCompanyId === id) {
        setSelectedCompanyId(null);
      }
      await refreshCompanies();
      toast.success("Azienda eliminata");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Errore durante l'eliminazione";
      toast.error(message);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <PageHeader
        title="Aziende"
        description="Gestione anagrafica aziende"
        icon={<Building2 className="h-6 w-6" />}
      >
        <Button onClick={() => setShowCreateForm(!showCreateForm)}>
          <Plus className="h-4 w-4 mr-1" />
          Nuova Azienda
        </Button>
      </PageHeader>

      {/* Create Form */}
      {showCreateForm && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">Nuova Azienda</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div className="space-y-1">
                <Label>Nome *</Label>
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="es. ROSSI S.R.L."
                />
              </div>
              <div className="space-y-1">
                <Label>Partita IVA</Label>
                <Input
                  value={newTaxId}
                  onChange={(e) => setNewTaxId(e.target.value)}
                  placeholder="es. 12345678901"
                />
              </div>
              <div className="space-y-1">
                <Label>Settore *</Label>
                <Select
                  value={newSector.toString()}
                  onValueChange={(v) => setNewSector(parseInt(v))}
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
              <div className="flex gap-2">
                <Button onClick={handleCreate} disabled={saving}>
                  {saving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Check className="h-4 w-4" />
                  )}
                  Crea
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setShowCreateForm(false)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Companies Table */}
      <Card>
        <CardContent className="p-0">
          {companies.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              Nessuna azienda presente. Crea la prima azienda o importa un file
              XBRL/PDF.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10"></TableHead>
                  <TableHead>Azienda</TableHead>
                  <TableHead>P.IVA</TableHead>
                  <TableHead>Settore</TableHead>
                  <TableHead className="text-center">Anni</TableHead>
                  <TableHead className="text-center">Scenari</TableHead>
                  <TableHead className="text-right">Azioni</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {companies.map((company) => {
                  const detail = companyDetails[company.id];
                  const isSelected = selectedCompanyId === company.id;
                  const isEditing = editingId === company.id;

                  if (isEditing) {
                    return (
                      <TableRow key={company.id}>
                        <TableCell></TableCell>
                        <TableCell>
                          <Input
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            className="h-8"
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            value={editTaxId}
                            onChange={(e) => setEditTaxId(e.target.value)}
                            className="h-8"
                          />
                        </TableCell>
                        <TableCell>
                          <Select
                            value={editSector.toString()}
                            onValueChange={(v) => setEditSector(parseInt(v))}
                          >
                            <SelectTrigger className="h-8">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {Object.entries(SECTOR_OPTIONS).map(
                                ([value, label]) => (
                                  <SelectItem key={value} value={value}>
                                    {value}. {label}
                                  </SelectItem>
                                )
                              )}
                            </SelectContent>
                          </Select>
                        </TableCell>
                        <TableCell></TableCell>
                        <TableCell></TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button
                              size="sm"
                              variant="default"
                              onClick={handleSaveEdit}
                              disabled={saving}
                            >
                              {saving ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <Check className="h-3 w-3" />
                              )}
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setEditingId(null)}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  }

                  return (
                    <TableRow
                      key={company.id}
                      className={
                        isSelected
                          ? "bg-primary/5 hover:bg-primary/10"
                          : "cursor-pointer"
                      }
                      onClick={() => setSelectedCompanyId(company.id)}
                    >
                      <TableCell className="text-center">
                        {isSelected && (
                          <Check className="h-4 w-4 text-primary mx-auto" />
                        )}
                      </TableCell>
                      <TableCell className="font-medium">
                        {company.name}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {company.tax_id || "\u2014"}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">
                          {getSectorName(company.sector)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        {loadingDetails ? (
                          <Loader2 className="h-3 w-3 animate-spin mx-auto" />
                        ) : detail?.years.length ? (
                          <span className="flex items-center justify-center gap-1 text-sm text-muted-foreground">
                            <Calendar className="h-3 w-3" />
                            {detail.years.join(", ")}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">{"\u2014"}</span>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        {loadingDetails ? (
                          <Loader2 className="h-3 w-3 animate-spin mx-auto" />
                        ) : detail?.scenarios.length ? (
                          <span className="flex items-center justify-center gap-1 text-sm text-muted-foreground">
                            <FileSpreadsheet className="h-3 w-3" />
                            {detail.scenarios.length}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">{"\u2014"}</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div
                          className="flex justify-end gap-1"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleStartEdit(company)}
                          >
                            <Pencil className="h-3 w-3" />
                          </Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button size="sm" variant="ghost">
                                <Trash2 className="h-3 w-3 text-destructive" />
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>
                                  Elimina azienda
                                </AlertDialogTitle>
                                <AlertDialogDescription>
                                  Eliminare &quot;{company.name}&quot; e tutti i
                                  dati associati (bilanci, scenari, previsioni)?
                                  Questa azione non può essere annullata.
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>Annulla</AlertDialogCancel>
                                <AlertDialogAction
                                  onClick={() => handleDelete(company.id)}
                                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                                >
                                  Elimina
                                </AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
