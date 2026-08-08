"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, Building2, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApp } from "@/contexts/AppContext";
import { createCompany, updateCompany } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";

const SECTOR_OPTIONS: Record<number, string> = {
  1: "Industria, Alberghi (Proprietari), Agricoltura, Pesca",
  2: "Commercio",
  3: "Servizi (diversi da Autotrasporti) e Alberghi (Locatari)",
  4: "Autotrasporti",
  5: "Immobiliare",
  6: "Edilizia",
};

/**
 * Primo step del percorso da bilancio: i dati dell'azienda della pratica.
 * Non è un elenco aziende — la scelta è già avvenuta sulla home.
 */
export function AnagraficheStep({ onReady }: { onReady: (companyId: number) => void }) {
  const { selectedCompany, selectedCompanyId, setSelectedCompanyId, refreshCompanies } = useApp();

  const [name, setName] = useState("");
  const [taxId, setTaxId] = useState("");
  const [sector, setSector] = useState(1);
  const [saving, setSaving] = useState(false);

  // Semina il form UNA SOLA VOLTA per azienda. `selectedCompany` cambia identità
  // a ogni refreshCompanies() — e il wizard lo richiama a ogni focus della
  // finestra — quindi ri-seminare a ogni cambio di riferimento cancellerebbe
  // quello che l'utente sta scrivendo.
  const seededFor = useRef<number | null>(null);
  useEffect(() => {
    // Nessuna azienda selezionata: è il form di creazione, niente da seminare.
    if (selectedCompanyId === null) {
      seededFor.current = null;
      return;
    }
    // L'elenco aziende può non essere ancora arrivato: aspetta il prossimo giro.
    if (!selectedCompany) return;
    if (seededFor.current === selectedCompanyId) return;
    seededFor.current = selectedCompanyId;
    setName(selectedCompany.name);
    setTaxId(selectedCompany.tax_id ?? "");
    setSector(selectedCompany.sector);
  }, [selectedCompanyId, selectedCompany]);

  const isNew = selectedCompanyId === null;

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error("Il nome dell'azienda è obbligatorio");
      return;
    }
    setSaving(true);
    try {
      let companyId = selectedCompanyId;
      if (isNew) {
        const company = await createCompany({
          name: name.trim(),
          tax_id: taxId.trim() || undefined,
          sector,
        });
        companyId = company.id;
        setSelectedCompanyId(company.id);
      } else {
        await updateCompany(selectedCompanyId!, {
          name: name.trim(),
          tax_id: taxId.trim() || undefined,
          sector,
        });
      }
      await refreshCompanies();
      toast.success(isNew ? "Azienda creata" : "Anagrafica aggiornata");
      if (companyId !== null) onReady(companyId);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, "Errore nel salvataggio dell'anagrafica"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Building2 className="h-5 w-5" /> Anagrafica azienda
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-1">
            <Label htmlFor="anag-nome">Nome *</Label>
            <Input
              id="anag-nome"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="es. ROSSI S.R.L."
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="anag-piva">Partita IVA</Label>
            <Input
              id="anag-piva"
              value={taxId}
              onChange={(e) => setTaxId(e.target.value)}
              placeholder="es. 12345678901"
            />
          </div>
          <div className="space-y-1">
            <Label>Settore *</Label>
            <Select value={sector.toString()} onValueChange={(v) => setSector(parseInt(v))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(SECTOR_OPTIONS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>{value}. {label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
            Salva e prosegui <ArrowRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
