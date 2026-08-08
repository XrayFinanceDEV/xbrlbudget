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
import { usePratica } from "@/contexts/PraticaContext";
import { useApp } from "@/contexts/AppContext";
import { createCompany, getCompany, updateCompany } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import type { Company } from "@/types/api";

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
 *
 * Seeding e modalità (nuova/modifica) derivano SEMPRE da `pratica.companyId`,
 * mai da `AppContext.selectedCompanyId`: quest'ultimo ha un fallback "seleziona
 * la prima azienda" (vedi AppContext.loadCompanies) pensato per le pagine
 * ordinarie, che una pratica nuova (companyId ancora null) deve poter
 * ignorare. Usarlo qui apriva il form in modalità MODIFICA su un'azienda
 * esistente a caso — "Salva e prosegui" la rinominava silenziosamente.
 */
export function AnagraficheStep({ onReady }: { onReady: (companyId: number) => void }) {
  const { pratica } = usePratica();
  const { refreshCompanies } = useApp();
  const praticaCompanyId = pratica?.companyId ?? null;

  const [company, setCompany] = useState<Company | null>(null);
  const [name, setName] = useState("");
  const [taxId, setTaxId] = useState("");
  const [sector, setSector] = useState(1);
  const [saving, setSaving] = useState(false);

  const isNew = praticaCompanyId === null;

  // Carica l'azienda della pratica (se ne ha già una assegnata) per
  // pre-compilare il form. Indipendente dall'elenco aziende di AppContext.
  useEffect(() => {
    if (praticaCompanyId === null) {
      setCompany(null);
      return;
    }
    let cancelled = false;
    getCompany(praticaCompanyId)
      .then((c) => {
        if (!cancelled) setCompany(c);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          toast.error(getErrorMessage(err, "Errore nel caricamento dell'azienda"));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [praticaCompanyId]);

  // Semina il form UNA SOLA VOLTA per azienda. `company` cambia identità ogni
  // volta che questo effetto lo ricarica — e un refreshCompanies() altrove
  // potrebbe far ripartire un giro — quindi ri-seminare a ogni cambio di
  // riferimento cancellerebbe quello che l'utente sta scrivendo.
  const seededFor = useRef<number | null>(null);
  useEffect(() => {
    // Nessuna azienda nella pratica: è il form di creazione, niente da seminare.
    if (praticaCompanyId === null) {
      seededFor.current = null;
      return;
    }
    // La company può non essere ancora arrivata, o essere quella di un
    // companyId precedente mentre il fetch per quello nuovo è in corso:
    // aspetta che coincidano prima di seminare.
    if (!company || company.id !== praticaCompanyId) return;
    if (seededFor.current === praticaCompanyId) return;
    seededFor.current = praticaCompanyId;
    setName(company.name);
    setTaxId(company.tax_id ?? "");
    setSector(company.sector);
  }, [praticaCompanyId, company]);

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error("Il nome dell'azienda è obbligatorio");
      return;
    }
    setSaving(true);
    try {
      let companyId = praticaCompanyId;
      if (isNew) {
        const created = await createCompany({
          name: name.trim(),
          tax_id: taxId.trim() || undefined,
          sector,
        });
        companyId = created.id;
      } else {
        await updateCompany(praticaCompanyId!, {
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
          <Button
            onClick={handleSave}
            // In EDIT mode (praticaCompanyId set) the form must not be
            // submittable until the seed effect above has landed — otherwise
            // a click in that window sends sector=1 (the still-default local
            // state) and silently resets the company's Altman/FGPMI sector
            // (FINDING 6, 2026-08-08 final review).
            disabled={saving || (praticaCompanyId !== null && seededFor.current !== praticaCompanyId)}
          >
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
            Salva e prosegui <ArrowRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
