"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { deleteCompany, updateCompany } from "@/lib/api";
import type { Company } from "@/types/api";
import { toast } from "sonner";
import { Building2, Upload, Trash2, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { PageHeader } from "@/components/page-header";

const SECTOR_NAMES: Record<number, string> = {
  1: "Industria",
  2: "Commercio",
  3: "Servizi",
  4: "Autotrasporti",
  5: "Immobiliare",
  6: "Edilizia",
};

const SECTOR_OPTIONS: Record<number, string> = {
  1: "Industria, Alberghi (Proprietari), Agricoltura, Pesca",
  2: "Commercio",
  3: "Servizi (diversi da Autotrasporti) e Alberghi (Locatari)",
  4: "Autotrasporti",
  5: "Immobiliare",
  6: "Edilizia",
};

export default function Home() {
  const { companies, setSelectedCompanyId, refreshCompanies } = useApp();
  const router = useRouter();
  const [deleting, setDeleting] = useState<number | null>(null);
  const [updatingSector, setUpdatingSector] = useState<number | null>(null);

  const handleSelectCompany = (companyId: number) => {
    setSelectedCompanyId(companyId);
    router.push("/analysis");
  };

  const handleSectorChange = async (company: Company, newSector: number) => {
    if (newSector === company.sector) return;
    setUpdatingSector(company.id);
    try {
      await updateCompany(company.id, { sector: newSector });
      await refreshCompanies();
      toast.success(`Settore di "${company.name}" aggiornato a ${SECTOR_NAMES[newSector]}`);
    } catch (error) {
      console.error("Error updating sector:", error);
      toast.error("Errore durante l'aggiornamento del settore");
    } finally {
      setUpdatingSector(null);
    }
  };

  const handleDeleteCompany = async (company: Company) => {
    setDeleting(company.id);
    try {
      await deleteCompany(company.id);
      await refreshCompanies();
      toast.success(`Azienda "${company.name}" eliminata`);
    } catch (error) {
      console.error("Error deleting company:", error);
      toast.error("Errore durante l'eliminazione dell'azienda");
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <PageHeader
        title="Aziende"
        description="Seleziona un'azienda per visualizzare l'analisi o elimina aziende non necessarie."
        icon={<Building2 className="h-6 w-6" />}
      />

      {companies.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Building2 className="h-16 w-16 mx-auto text-muted-foreground mb-4" />
            <h2 className="text-xl font-semibold mb-2">
              Nessuna azienda disponibile
            </h2>
            <p className="text-muted-foreground mb-6">
              Importa dati da XBRL, CSV o PDF per iniziare l&apos;analisi finanziaria.
            </p>
            <Button onClick={() => router.push("/import")}>
              <Upload className="h-4 w-4 mr-2" />
              Vai a Importazione
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[60px]">ID</TableHead>
                <TableHead>Nome Azienda</TableHead>
                <TableHead>Partita IVA</TableHead>
                <TableHead>Settore</TableHead>
                <TableHead className="text-right">Azioni</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {companies.map((company) => (
                <TableRow
                  key={company.id}
                  className="cursor-pointer"
                  onClick={() => handleSelectCompany(company.id)}
                >
                  <TableCell className="font-medium">{company.id}</TableCell>
                  <TableCell className="font-medium">{company.name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {company.tax_id || "\u2014"}
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Select
                      value={company.sector.toString()}
                      onValueChange={(v) => handleSectorChange(company, parseInt(v))}
                      disabled={updatingSector === company.id}
                    >
                      <SelectTrigger className="w-[180px] h-8 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(SECTOR_OPTIONS).map(([value, label]) => (
                          <SelectItem key={value} value={value}>{value}. {label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSelectCompany(company.id);
                        }}
                      >
                        <ExternalLink className="h-4 w-4 mr-1" />
                        Seleziona
                      </Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive hover:text-destructive"
                            onClick={(e) => e.stopPropagation()}
                            disabled={deleting === company.id}
                          >
                            <Trash2 className="h-4 w-4 mr-1" />
                            {deleting === company.id ? "Eliminazione..." : "Elimina"}
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent onClick={(e) => e.stopPropagation()}>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Conferma eliminazione</AlertDialogTitle>
                            <AlertDialogDescription>
                              Sei sicuro di voler eliminare &quot;{company.name}&quot;? Questa azione
                              è irreversibile.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Annulla</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={() => handleDeleteCompany(company)}
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
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
