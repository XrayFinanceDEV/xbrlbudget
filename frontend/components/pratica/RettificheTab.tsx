"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import { toast } from "sonner";
import {
  ArrowRight,
  Check,
  Loader2,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatEuro, formatInputNumber, parseInputNumber } from "@/lib/pratica-format";
import { reconcileSubfields } from "@/lib/pratica-reconcile";
import { ATTIVO_CODES, DETAIL_PARENTS } from "@/lib/pratica-codes";
import { labelOf } from "@/lib/ivcee-catalog";
import {
  type ProposalMode,
  type DoubleEntryProposal,
  PROPOSAL_RULES,
  EDITABLE_RETTIFICHE,
  AUTO_ADJUSTED,
  NON_POSTABLE_FIELDS,
  RETTIFICHE_LABELS,
  allowedCounterpartCategories,
  computeCpDelta,
  COUNTERPART_GROUPS,
  COUNTERPART_OPTIONS,
  RETTIFICHE_BS_ATTIVO,
  RETTIFICHE_BS_PN,
  RETTIFICHE_BS_OTHER_PASSIVO,
  DEBT_GROUPS,
  PASSIVO_TOTAL_FIELDS,
  CE_A,
  CE_B,
  CE_C,
  CE_D,
  CE_E,
  CE_IMPOSTE,
  RETTIFICHE_MAX,
} from "@/lib/pratica-rettifiche-rules";
import type { AdjustableFinancialYear, RettificaEntry } from "@/types/api";

interface RettificheTabProps {
  adjustableData: AdjustableFinancialYear | null;
  referenceYearData: Record<string, number> | null;
  referenceYear: number;
  periodMonths: number;
  fiscalYear: number;
  corrections: Record<string, number>;
  setCorrections: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  loading: boolean;
  saving: boolean;
  adjustmentsApplied: boolean;
  onSave: (finalCorrections?: Record<string, number>, finalLog?: RettificaEntry[]) => Promise<boolean>;
  onReset: () => Promise<boolean>;
  onNext: () => void;
}

export function RettificheTab({
  adjustableData,
  referenceYearData,
  referenceYear,
  periodMonths,
  fiscalYear,
  corrections,
  setCorrections,
  loading,
  saving,
  adjustmentsApplied,
  onSave,
  onReset,
  onNext,
}: RettificheTabProps) {
  // Compute end-of-period date label, e.g. "30/06/2025"
  const periodEndDate = (() => {
    const lastDay = new Date(fiscalYear, periodMonths, 0).getDate();
    const mm = String(periodMonths).padStart(2, "0");
    return `${lastDay}/${mm}/${fiscalYear}`;
  })();

  // Sticky column header bar — appears when the first table header scrolls out of view
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [showStickyHeader, setShowStickyHeader] = useState(false);
  // Per-edit double-entry dialog (single proposal for the in-flight edit)
  const [activeProposal, setActiveProposal] = useState<DoubleEntryProposal | null>(null);
  // Pending (uncommitted) edits: value shown in input but not yet confirmed via dialog
  const [pendingEdits, setPendingEdits] = useState<Record<string, number>>({});
  // Persisted journal of confirmed rettifiche — hydrated from adjustableData
  const [log, setLog] = useState<RettificaEntry[]>(adjustableData?.rettifiche_log ?? []);
  // Summary dialog shown before navigating to Confronto
  const [showSummaryDialog, setShowSummaryDialog] = useState(false);

  // Hydrate log whenever adjustableData changes (e.g. after save or reset)
  useEffect(() => {
    setLog(adjustableData?.rettifiche_log ?? []);
  }, [adjustableData]);

  // The gate's "confirm" marker lives in the same log (so the server persists
  // it and the 20-entry cap logic can see it), but it is not a rettifica the
  // user made — hide it from the journal panel, the Riepilogo dialog and the
  // count against RETTIFICHE_MAX.
  const visibleLog = useMemo(() => log.filter((e) => e.entry_type !== "confirm"), [log]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => setShowStickyHeader(!entry.isIntersecting),
      { threshold: 0 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  if (loading || !adjustableData) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
          <p className="mt-2 text-muted-foreground">Caricamento dati...</p>
        </CardContent>
      </Card>
    );
  }

  const original = {
    ...adjustableData.original_balance_sheet,
    ...adjustableData.original_income_statement,
  } as Record<string, number>;
  // Reconcile debt sub-fields so "Altri debiti" absorbs any gap vs imported aggregate
  reconcileSubfields(original);

  // Handle field changes — only direct edit + conditional sub-field aggregates + sp13 recalc.
  // Double-entry counterparts are proposed via dialog, not auto-applied.
  // IMPORTANT: Only recalculate an aggregate when one of its component fields is edited,
  // to avoid corrupting aggregates when details don't sum to the original total.
  const SP16_DETAILS = [
    "sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve",
    "sp16c_debiti_obbligazioni_breve", "sp16d_debiti_fornitori_breve",
    "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve",
    "sp16g_altri_debiti_breve",
  ];
  const SP17_DETAILS = [
    "sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo",
    "sp17c_debiti_obbligazioni_lungo", "sp17d_debiti_fornitori_lungo",
    "sp17e_debiti_tributari_lungo", "sp17f_debiti_previdenza_lungo",
    "sp17g_altri_debiti_lungo",
  ];
  const SP04_DETAILS = ["sp04a_partecipazioni", "sp04b_crediti_immob_breve", "sp04c_crediti_immob_lungo", "sp04d_altri_titoli", "sp04e_strumenti_derivati_attivi"];
  const SP05_DETAILS = ["sp05a_materie_prime", "sp05b_prodotti_in_corso", "sp05c_lavori_in_corso", "sp05d_prodotti_finiti", "sp05e_acconti"];
  const SP12_DETAILS = ["sp12a_riserva_sovrapprezzo", "sp12b_riserve_rivalutazione", "sp12c_riserva_legale", "sp12d_riserve_statutarie", "sp12e_altre_riserve", "sp12f_riserva_copertura_flussi", "sp12g_utili_perdite_portati", "sp12h_riserva_neg_azioni_proprie"];
  const SP06_DETAILS = [
    "sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve", "sp06c_crediti_collegate_breve",
    "sp06d_crediti_controllanti_breve", "sp06e_crediti_tributari_breve", "sp06f_imposte_anticipate_breve",
    "sp06g_crediti_altri_breve",
  ];
  const SP07_DETAILS = [
    "sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo", "sp07c_crediti_collegate_lungo",
    "sp07d_crediti_controllanti_lungo", "sp07e_crediti_tributari_lungo", "sp07f_imposte_anticipate_lungo",
    "sp07g_crediti_altri_lungo",
  ];
  const CE08_DETAILS = ["ce08b_salari_stipendi", "ce08c_oneri_sociali", "ce08a_tfr_accrual", "ce08d_altri_costi_personale"];
  const CE09_DETAILS = ["ce09a_ammort_immateriali", "ce09b_ammort_materiali", "ce09c_svalutazioni", "ce09d_svalutazione_crediti"];
  const CE17_DETAILS = ["ce17a_rivalutazioni", "ce17b_svalutazioni"];
  // All CE fields that affect the P&L result
  const CE_FIELDS = [
    "ce01_ricavi_vendite", "ce02_variazioni_rimanenze", "ce03_lavori_interni", "ce04_altri_ricavi",
    "ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni", "ce08_costi_personale",
    "ce09_ammortamenti", "ce09a_ammort_immateriali", "ce09b_ammort_materiali", "ce09c_svalutazioni", "ce09d_svalutazione_crediti",
    "ce10_var_rimanenze_mat_prime", "ce11_accantonamenti", "ce11b_altri_accantonamenti", "ce12_oneri_diversi",
    "ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari", "ce15_oneri_finanziari", "ce16_utili_perdite_cambi",
    "ce17_rettifiche_attivita_fin", "ce17a_rivalutazioni", "ce17b_svalutazioni",
    "ce18_proventi_straordinari", "ce19_oneri_straordinari", "ce20_imposte",
  ];

  // Per-edit flow: input onChange updates only pendingEdits (display), onBlur triggers the proposal dialog.
  const onFieldChange = (field: string, newValue: number) => {
    setPendingEdits((prev) => ({ ...prev, [field]: newValue }));
  };
  const commitEdit = (field: string) => {
    const pending = pendingEdits[field];
    if (pending === undefined) return;
    const committed = corrections[field] ?? original[field] ?? 0;
    const editDelta = pending - committed;
    if (Math.abs(editDelta) < 0.01) {
      setPendingEdits((prev) => { const u = { ...prev }; delete u[field]; return u; });
      return;
    }
    // Enforce 20-entry cap before opening dialog
    if (visibleLog.length >= RETTIFICHE_MAX) {
      toast.error(`Massimo ${RETTIFICHE_MAX} rettifiche. Eliminane qualcuna per aggiungerne altre.`);
      setPendingEdits((prev) => { const u = { ...prev }; delete u[field]; return u; });
      return;
    }
    // Find matching PROPOSAL_RULE for default counterpart
    const rule = PROPOSAL_RULES.find((r) => r.editable === field);
    let counterpartField = "";
    let proposedDelta = -editDelta;
    let explanation = "Nessuna regola predefinita — seleziona manualmente la contropartita.";
    let splitAlt: DoubleEntryProposal["splitAlt"] = undefined;
    if (rule) {
      const useNeg = editDelta < 0 && rule.counterpartNeg;
      counterpartField = useNeg ? rule.counterpartNeg! : rule.counterpart;
      const dir = useNeg ? (rule.directionNeg ?? rule.direction) : rule.direction;
      proposedDelta = dir === "same" ? editDelta : -editDelta;
      explanation = useNeg ? (rule.explanationNeg ?? rule.explanation) : rule.explanation;
      const activeSplitAlt = useNeg ? rule.splitAltNeg : rule.splitAlt;
      if (activeSplitAlt) splitAlt = { field: activeSplitAlt.field, label: activeSplitAlt.label, amount: 0 };
    }
    setActiveProposal({
      id: Date.now(),
      mode: "rettifica",
      editedField: field,
      editedLabel: labelOf(field),
      delta: editDelta,
      counterpartField,
      counterpartLabel: labelOf(counterpartField),
      proposedDelta,
      accepted: true,
      explanation,
      splitAlt,
    });
  };

  // Helper: recalculate all sub-field aggregates + sp13 on a corrections snapshot
  const recalcAggregates = (corr: Record<string, number>): Record<string, number> => {
    const u = { ...corr };
    // Delta-based: parent = original_parent + sum(sub_field_deltas)
    const applyDelta = (details: string[], parent: string) => {
      const totalDelta = details.reduce((s, k) => {
        const orig = original[k] ?? 0;
        const curr = u[k] ?? orig;
        return s + (curr - orig);
      }, 0);
      u[parent] = (original[parent] ?? 0) + totalDelta;
    };
    applyDelta(SP04_DETAILS, "sp04_immob_finanziarie");
    applyDelta(SP05_DETAILS, "sp05_rimanenze");
    applyDelta(SP06_DETAILS, "sp06_crediti_breve");
    applyDelta(SP07_DETAILS, "sp07_crediti_lungo");
    applyDelta(SP12_DETAILS, "sp12_riserve");
    applyDelta(CE08_DETAILS, "ce08_costi_personale");
    applyDelta(SP16_DETAILS, "sp16_debiti_breve");
    applyDelta(SP17_DETAILS, "sp17_debiti_lungo");
    applyDelta(CE09_DETAILS, "ce09_ammortamenti");
    // ce17: rivalutazioni - svalutazioni
    const d17a = (u["ce17a_rivalutazioni"] ?? original["ce17a_rivalutazioni"] ?? 0) - (original["ce17a_rivalutazioni"] ?? 0);
    const d17b = (u["ce17b_svalutazioni"] ?? original["ce17b_svalutazioni"] ?? 0) - (original["ce17b_svalutazioni"] ?? 0);
    u["ce17_rettifiche_attivita_fin"] = (original["ce17_rettifiche_attivita_fin"] ?? 0) + d17a - d17b;
    // sp13 from P&L — Risultato calculated first in CE, then set in SP
    const cv = (k: string) => u[k] ?? original[k] ?? 0;
    const vp = cv("ce01_ricavi_vendite") + cv("ce02_variazioni_rimanenze")
      + cv("ce03_lavori_interni") + cv("ce03a_incrementi_immobilizzazioni") + cv("ce04_altri_ricavi");
    const costs = cv("ce05_materie_prime") + cv("ce06_servizi") + cv("ce07_godimento_beni")
      + cv("ce08_costi_personale") + cv("ce09_ammortamenti") + cv("ce10_var_rimanenze_mat_prime")
      + cv("ce11_accantonamenti") + cv("ce11b_altri_accantonamenti") + cv("ce12_oneri_diversi");
    const ebit = vp - costs;
    const fin = cv("ce13_proventi_partecipazioni") + cv("ce14_altri_proventi_finanziari")
      - cv("ce15_oneri_finanziari") + cv("ce16_utili_perdite_cambi");
    const rett = cv("ce17_rettifiche_attivita_fin");
    const str = cv("ce18_proventi_straordinari") - cv("ce19_oneri_straordinari");
    u["sp13_utile_perdita"] = Math.round((ebit + fin + rett + str - cv("ce20_imposte")) * 100) / 100;
    return u;
  };

  // Confirm the active proposal: write the entry to the log, apply deltas to corrections, persist.
  // Le due destinazioni di default per la correzione di quadratura a partita
  // singola: una sul lato attivo, una sul lato passivo (YAGNI: nessun target
  // picker in questo task, quindi solo i due default usati da
  // openSbilancioCorrection). Le etichette vengono da labelOf() — la stessa
  // fonte che il pannello journal e la tabella sopra usano per rendere la
  // voce — cosi' la spiegazione della rettifica non contraddice la
  // didascalia mostrata nella tabella. `side` guida il SEGNO del delta (vedi
  // sotto), non l'indice nell'array: dedurlo dal prefisso del codice
  // funzionerebbe oggi ma si romperebbe al primo campo aggiunto fuori schema.
  const SBILANCIO_TARGETS: { field: string; label: string; side: "attivo" | "passivo" }[] = [
    { field: "sp09_disponibilita_liquide", label: labelOf("sp09_disponibilita_liquide"), side: "attivo" },
    { field: "sp16g_altri_debiti_breve", label: labelOf("sp16g_altri_debiti_breve"), side: "passivo" },
  ];

  // Apre la modalita' "Correggi Import" (partita singola) pre-compilata con lo
  // scarto esatto. L'importo e' un dato, non una scelta: il dialog lo mostra
  // come testo, non come input.
  //
  // Il gap va calcolato sullo stato che esistera' DOPO la conferma, non su
  // quello del render corrente: confirmActiveEdit chiama SEMPRE
  // recalcAggregates, che sovrascrive sp13_utile_perdita con il valore
  // derivato dal CE indipendentemente dal campo corretto qui. Se lo sp13
  // importato differisce da quello ricalcolato dal CE (bilancio con CE/SP
  // scollegati — proprio il caso che questo import ora salva invece di
  // rifiutare), il gap "di rendering" (totalAttivo - totalPassivo) NON e'
  // quello che restera' dopo la conferma: va ricalcolato sullo snapshot
  // passato per recalcAggregates, altrimenti la correzione lascia un
  // residuo pari a (sp13_importato - sp13_CE) invece di azzerare lo scarto.
  //
  // SEGNO. gap = attivo_proiettato - passivo_proiettato.
  //   gap > 0 (l'attivo eccede)  -> ridurre un campo dell'attivo di gap,
  //                                 oppure aumentare un campo del passivo di gap.
  //   gap < 0 (il passivo eccede) -> aumentare un campo dell'attivo di |gap|,
  //                                 oppure ridurre un campo del passivo di |gap|.
  // In entrambi i casi: delta = -gap su un campo dell'attivo, delta = +gap su un
  // campo del passivo.
  const openSbilancioCorrection = () => {
    // Copia: recalcAggregates non deve mutare lo stato "corrections" del render.
    const projected = recalcAggregates({ ...corrections });
    const pv = (k: string) => projected[k] ?? original[k] ?? 0;
    const projAttivo = ATTIVO_CODES.reduce((s, k) => s + pv(k), 0);
    const projPN = pnFields.reduce((s, k) => s + pv(k), 0);
    const projPassivo = projPN + pv("sp14_fondi_rischi") + pv("sp15_tfr")
      + pv("sp16_debiti_breve") + pv("sp17_debiti_lungo") + pv("sp18_ratei_risconti_passivi");
    const gap = Math.round((projAttivo - projPassivo) * 100) / 100;
    if (Math.abs(gap) < 0.01) return;
    // Default: l'attivo eccede -> si toglie dalla cassa; il passivo eccede ->
    // si tolgono altri debiti.
    const target = gap > 0 ? SBILANCIO_TARGETS[0] : SBILANCIO_TARGETS[1];
    const delta = target.side === "attivo" ? -gap : gap;
    setActiveProposal({
      id: Date.now(),
      mode: "correggi_import",
      editedField: target.field,
      editedLabel: target.label,
      delta,
      counterpartField: "",
      counterpartLabel: "",
      proposedDelta: 0,
      accepted: true,
      explanation:
        `Correzione di quadratura: scarto di importazione ${formatEuro(Math.abs(gap))} ` +
        `imputato a ${target.label}`,
    });
  };

  // NOTA (task-13, FIX 4): il log/corrections locali si aggiornano SOLO dopo
  // che onSave ha risolto true. Un save rifiutato dal server (400 — es. la
  // guardia anti-regressione su Attivo/Passivo, CE↔SP o aggregati/dettagli)
  // deve lasciare lo stato del form COM'ERA, non farlo sembrare applicato:
  // il salvataggio ottimistico precedente (setCorrections/setLog PRIMA di
  // onSave, senza controllarne l'esito) faceva vedere una rettifica "in
  // giornale" che sul server non esisteva mai. onSave mostra già l'errore
  // (toast, vedi useRettificheYear.save); qui il proposal resta aperto così
  // l'utente può ritentare o annullare invece di scoprirlo dopo.
  const confirmActiveEdit = async () => {
    if (!activeProposal) return;
    const p = activeProposal;
    // Correggi Import: single-entry, no counterpart required
    if (p.mode === "correggi_import") {
      const updated = { ...corrections };
      updated[p.editedField] = (updated[p.editedField] ?? original[p.editedField] ?? 0) + p.delta;
      const newEntry: RettificaEntry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        edited_field: p.editedField,
        edited_label: p.editedLabel,
        edit_delta: p.delta,
        counterpart_field: "_correzione_import",
        counterpart_label: "Correzione importazione",
        counterpart_delta: 0,
        explanation: p.explanation || "Correzione dato importato",
        created_at: new Date().toISOString(),
      };
      const final = recalcAggregates(updated);
      const newLog = [...log, newEntry];
      if (newLog.filter((e) => e.entry_type !== "confirm").length > RETTIFICHE_MAX) {
        toast.error(`Massimo ${RETTIFICHE_MAX} rettifiche`);
        return;
      }
      const ok = await onSave(final, newLog);
      if (!ok) return;
      setCorrections(final);
      setLog(newLog);
      setPendingEdits((prev) => { const u = { ...prev }; delete u[p.editedField]; return u; });
      setActiveProposal(null);
      return;
    }
    if (!p.counterpartField) {
      toast.error("Seleziona una contropartita");
      return;
    }
    const updated = { ...corrections };
    updated[p.editedField] = (updated[p.editedField] ?? original[p.editedField] ?? 0) + p.delta;
    // Counterpart: handle split if present
    const splitAmount = p.splitAlt && Math.abs(p.splitAlt.amount) > 0.01 ? p.splitAlt.amount : 0;
    const mainAmount = p.proposedDelta - splitAmount;
    updated[p.counterpartField] = (updated[p.counterpartField] ?? original[p.counterpartField] ?? 0) + mainAmount;
    const newEntries: RettificaEntry[] = [{
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      edited_field: p.editedField,
      edited_label: p.editedLabel,
      edit_delta: p.delta,
      counterpart_field: p.counterpartField,
      counterpart_label: p.counterpartLabel,
      counterpart_delta: mainAmount,
      explanation: p.explanation,
      created_at: new Date().toISOString(),
    }];
    if (splitAmount !== 0 && p.splitAlt) {
      updated[p.splitAlt.field] = (updated[p.splitAlt.field] ?? original[p.splitAlt.field] ?? 0) + splitAmount;
      newEntries.push({
        id: `${Date.now() + 1}-${Math.random().toString(36).slice(2, 8)}`,
        edited_field: p.editedField,
        edited_label: p.editedLabel,
        edit_delta: 0, // split row — primary edit already recorded
        counterpart_field: p.splitAlt.field,
        counterpart_label: p.splitAlt.label,
        counterpart_delta: splitAmount,
        explanation: `(split) ${p.explanation}`,
        created_at: new Date().toISOString(),
      });
    }
    const final = recalcAggregates(updated);
    const newLog = [...log, ...newEntries];
    if (newLog.filter((e) => e.entry_type !== "confirm").length > RETTIFICHE_MAX) {
      toast.error(`Massimo ${RETTIFICHE_MAX} rettifiche`);
      return;
    }
    const ok = await onSave(final, newLog);
    if (!ok) return;
    setCorrections(final);
    setLog(newLog);
    setPendingEdits((prev) => { const u = { ...prev }; delete u[p.editedField]; return u; });
    setActiveProposal(null);
  };

  const cancelActiveEdit = () => {
    if (activeProposal) {
      setPendingEdits((prev) => { const u = { ...prev }; delete u[activeProposal.editedField]; return u; });
    }
    setActiveProposal(null);
  };

  // Delete one log entry: reverse its deltas in corrections, remove from log, persist.
  // Same rollback discipline as confirmActiveEdit: commit locally only once
  // the server has actually accepted the reversal.
  const deleteLogEntry = async (entryId: string) => {
    const entry = log.find((e) => e.id === entryId);
    if (!entry) return;
    const updated = { ...corrections };
    updated[entry.edited_field] = (updated[entry.edited_field] ?? original[entry.edited_field] ?? 0) - entry.edit_delta;
    updated[entry.counterpart_field] = (updated[entry.counterpart_field] ?? original[entry.counterpart_field] ?? 0) - entry.counterpart_delta;
    const final = recalcAggregates(updated);
    const newLog = log.filter((e) => e.id !== entryId);
    const ok = await onSave(final, newLog);
    if (!ok) return;
    setCorrections(final);
    setLog(newLog);
  };

  // Compute totals
  const val = (k: string) => corrections[k] ?? original[k] ?? 0;
  const refVal = (k: string) => referenceYearData?.[k] ?? 0;
  const hasRef = !!referenceYearData;
  // Solo le voci di primo livello dell'attivo (le sotto-voci di dettaglio
  // sarebbero contate due volte): ATTIVO_CODES, la stessa lista che usano
  // Confronto e riconciliazione.
  const totalAttivo = ATTIVO_CODES.reduce((s, k) => s + val(k), 0);
  const pnFields = ["sp11_capitale", "sp12_riserve", "sp13_utile_perdita"];
  const totalPN = pnFields.reduce((s, k) => s + val(k), 0);
  const totalPassivo = totalPN + val("sp14_fondi_rischi") + val("sp15_tfr")
    + val("sp16_debiti_breve") + val("sp17_debiti_lungo") + val("sp18_ratei_risconti_passivi");
  const balanceDiff = Math.abs(totalAttivo - totalPassivo);
  const isBalanced = balanceDiff < 1;

  const colCount = hasRef ? 5 : 4;

  const renderSection = (title: string, fields: string[], isCE: boolean = false) => (
    <>
      {title && (
        <TableRow className="bg-muted/50">
          <TableCell colSpan={colCount} className="font-semibold text-sm py-1.5">
            {title}
          </TableCell>
        </TableRow>
      )}
      {fields.map((field) => {
        const origVal = original[field] ?? 0;
        const corrVal = val(field);
        const delta = corrVal - origVal;
        const isEditable = EDITABLE_RETTIFICHE.has(field);
        const isAutoAdj = AUTO_ADJUSTED.has(field);
        const isComputed = field === "sp04_immob_finanziarie" || field === "sp12_riserve" || field === "sp13_utile_perdita" || field === "sp16_debiti_breve" || field === "sp17_debiti_lungo" || field === "ce09_ammortamenti" || field === "ce17_rettifiche_attivita_fin";
        const hasDelta = Math.abs(delta) > 0.01;
        // Rientro (pl-6 + testo attenuato), non etichetta: si legge ancora dai
        // due spazi iniziali di RETTIFICHE_LABELS. DETAIL_PARENTS non e'
        // equivalente — vi compaiono anche sp12a..h e ce17a/b, che questa
        // vista NON rientra — e le etichette del catalogo sono tutte trimmate.
        const isDetail = (RETTIFICHE_LABELS[field] ?? "").startsWith("  ");

        // Show detail rows if parent is non-zero; otherwise skip zero rows unless editable/auto/computed
        const parentField = DETAIL_PARENTS[field];
        const parentNonZero = parentField ? Math.abs(val(parentField)) > 0.01 || Math.abs(original[parentField] ?? 0) > 0.01 : false;
        if (Math.abs(origVal) < 0.01 && Math.abs(corrVal) < 0.01 && !isEditable && !isAutoAdj && !isComputed && !parentNonZero) {
          return null;
        }

        return (
          <TableRow key={field} className={cn(
            hasDelta && "bg-yellow-50/50 dark:bg-yellow-950/10",
            isDetail && "text-muted-foreground"
          )}>
            <TableCell className={cn("text-xs py-1", isDetail ? "pl-6" : "font-medium")}>
              {labelOf(field)}
            </TableCell>
            {hasRef && (
              <TableCell className="text-right text-xs py-1 font-mono tabular-nums text-muted-foreground/50">
                {formatEuro(refVal(field))}
              </TableCell>
            )}
            <TableCell className="text-right text-xs py-1 font-mono tabular-nums text-muted-foreground">
              {formatEuro(origVal)}
            </TableCell>
            <TableCell className={cn(
              "text-right text-xs py-1 font-mono tabular-nums",
              hasDelta ? (delta > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400") : "text-muted-foreground/40"
            )}>
              {hasDelta ? (delta > 0 ? "+" : "") + formatEuro(delta) : "-"}
            </TableCell>
            <TableCell className="text-right py-1">
              {isEditable ? (
                <Input
                  className="h-7 w-32 ml-auto text-right text-xs font-mono tabular-nums"
                  value={formatInputNumber(Math.round(pendingEdits[field] ?? corrVal).toString())}
                  onChange={(e) => {
                    const raw = parseInputNumber(e.target.value);
                    const num = raw === "" || raw === "-" ? 0 : parseInt(raw, 10);
                    if (!isNaN(num)) onFieldChange(field, num);
                  }}
                  onBlur={() => commitEdit(field)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") (e.currentTarget as HTMLInputElement).blur();
                  }}
                />
              ) : (
                <span className={cn(
                  "text-xs font-mono tabular-nums",
                  isComputed && hasDelta ? "font-semibold" : "",
                  isAutoAdj && hasDelta ? "text-blue-600 dark:text-blue-400" : ""
                )}>
                  {formatEuro(corrVal)}
                </span>
              )}
            </TableCell>
          </TableRow>
        );
      })}
    </>
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Rettifiche di Bilancio</CardTitle>
          <CardDescription>
            Modifica le voci editabili per applicare rettifiche contabili. Le contropartite si aggiornano automaticamente in partita doppia.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Balance check */}
          <div className={cn(
            "mb-4 p-3 rounded-lg border text-sm flex items-center justify-between",
            isBalanced
              ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800 text-green-800 dark:text-green-300"
              : "bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800 text-red-800 dark:text-red-300"
          )}>
            <div>
              <span className="font-medium">Verifica quadratura: </span>
              Totale Attivo {formatEuro(totalAttivo)} | Totale Passivo {formatEuro(totalPassivo)}
              {!isBalanced && <span className="ml-2">(diff: {formatEuro(balanceDiff)})</span>}
            </div>
            {isBalanced ? (
              <Check className="h-4 w-4 text-green-600 dark:text-green-400" />
            ) : (
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-xs font-medium">SBILANCIATO</span>
                <Button size="sm" variant="outline" onClick={openSbilancioCorrection}>
                  Chiudi sbilancio
                </Button>
              </div>
            )}
          </div>

          {/* Sentinel: when this scrolls out of view, show the sticky header */}
          <div ref={sentinelRef} />

          {/* Sticky column header bar */}
          {showStickyHeader && (
            <div className="fixed top-0 left-0 right-0 z-50 bg-background/95 backdrop-blur-sm border-b shadow-sm">
              <div className="max-w-screen-xl mx-auto px-4">
                <div className="flex items-center h-9 text-xs font-medium text-muted-foreground">
                  <span className="flex-1">Voce</span>
                  {hasRef && <span className="w-28 text-right">{referenceYear}</span>}
                  <span className="w-28 text-right">{periodEndDate}</span>
                  <span className="w-28 text-right">Rettifica</span>
                  <span className="w-32 text-right">{periodEndDate} Rett.</span>
                </div>
              </div>
            </div>
          )}

          <div className="border rounded-lg overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Voce</TableHead>
                  {hasRef && <TableHead className="text-xs text-right">{referenceYear}</TableHead>}
                  <TableHead className="text-xs text-right">{periodEndDate}</TableHead>
                  <TableHead className="text-xs text-right">Rettifica</TableHead>
                  <TableHead className="text-xs text-right">{periodEndDate} Rett.</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {renderSection("STATO PATRIMONIALE — ATTIVO", RETTIFICHE_BS_ATTIVO)}
                <TableRow className="bg-muted font-semibold">
                  <TableCell className="text-xs py-1.5">TOTALE ATTIVO</TableCell>
                  {hasRef && <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/50">
                    {formatEuro(ATTIVO_CODES.reduce((s, k) => s + refVal(k), 0))}
                  </TableCell>}
                  <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums">
                    {formatEuro(ATTIVO_CODES.reduce((s, k) => s + (original[k] ?? 0), 0))}
                  </TableCell>
                  <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/40">-</TableCell>
                  <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums font-semibold">
                    {formatEuro(totalAttivo)}
                  </TableCell>
                </TableRow>

                {/* PASSIVO — A) Patrimonio Netto */}
                {renderSection("STATO PATRIMONIALE — PASSIVO E NETTO", RETTIFICHE_BS_PN)}
                {renderSection("", RETTIFICHE_BS_OTHER_PASSIVO)}

                {/* D) Debiti — grouped by type with entro/oltre */}
                <TableRow className="bg-muted/50">
                  <TableCell colSpan={colCount} className="font-semibold text-sm py-1.5">
                    D) Debiti
                  </TableCell>
                </TableRow>
                {DEBT_GROUPS.map((group) => {
                  const sumFields = (fields: string[], src: Record<string, number>) =>
                    fields.reduce((s, k) => s + (src[k] ?? 0), 0);
                  const origEntro = sumFields(group.entro, original);
                  const origOltre = sumFields(group.oltre, original);
                  const corrEntro = group.entro.reduce((s, k) => s + val(k), 0);
                  const corrOltre = group.oltre.reduce((s, k) => s + val(k), 0);
                  const origTotal = origEntro + origOltre;
                  const corrTotal = corrEntro + corrOltre;
                  // Group header always shown (OIC art. 2424 structure, matches /forecast/balance).
                  // Sub-rows show only when any year has a non-zero value.

                  const refEntro = hasRef ? group.entro.reduce((s, k) => s + refVal(k), 0) : 0;
                  const refOltre = hasRef ? group.oltre.reduce((s, k) => s + refVal(k), 0) : 0;
                  const isSingleEntro = group.entro.length === 1;
                  const isSingleOltre = group.oltre.length === 1;
                  const entroNonZero = Math.abs(origEntro) > 0.01 || Math.abs(corrEntro) > 0.01 || Math.abs(refEntro) > 0.01;
                  const oltreNonZero = Math.abs(origOltre) > 0.01 || Math.abs(corrOltre) > 0.01 || Math.abs(refOltre) > 0.01;

                  const debtRow = (label: string, key: string, rv: number, origV: number, corrV: number, indent: boolean, editField?: string) => {
                    const delta = corrV - origV;
                    const hasDelta = Math.abs(delta) > 0.01;
                    return (
                      <TableRow key={key} className={cn(hasDelta && "bg-yellow-50/50 dark:bg-yellow-950/10")}>
                        <TableCell className={cn("text-xs py-1", indent ? "pl-8 text-muted-foreground" : "pl-4 font-medium")}>
                          {label}
                        </TableCell>
                        {hasRef && <TableCell className="text-right text-xs py-1 font-mono tabular-nums text-muted-foreground/50">
                          {formatEuro(rv)}
                        </TableCell>}
                        <TableCell className="text-right text-xs py-1 font-mono tabular-nums text-muted-foreground">
                          {formatEuro(origV)}
                        </TableCell>
                        <TableCell className={cn(
                          "text-right text-xs py-1 font-mono tabular-nums",
                          hasDelta ? (delta > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400") : "text-muted-foreground/40"
                        )}>
                          {hasDelta ? (delta > 0 ? "+" : "") + formatEuro(delta) : "-"}
                        </TableCell>
                        <TableCell className="text-right py-1">
                          {editField ? (
                            <Input
                              className="h-7 w-32 ml-auto text-right text-xs font-mono tabular-nums"
                              value={formatInputNumber(Math.round(pendingEdits[editField] ?? corrV).toString())}
                              onChange={(e) => {
                                const raw = parseInputNumber(e.target.value);
                                const num = raw === "" || raw === "-" ? 0 : parseInt(raw, 10);
                                if (!isNaN(num)) onFieldChange(editField, num);
                              }}
                              onBlur={() => commitEdit(editField)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") (e.currentTarget as HTMLInputElement).blur();
                              }}
                            />
                          ) : (
                            <span className={cn("text-xs font-mono tabular-nums", !indent && "font-medium",
                              hasDelta && indent ? "text-blue-600 dark:text-blue-400" : ""
                            )}>
                              {formatEuro(corrV)}
                            </span>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  };

                  // Rettifiche sub-rows always rendered (inputs need to be reachable even
                  // when the creditor group is currently zero, so the user can add a posting).
                  void entroNonZero; void oltreNonZero;
                  return (
                    <React.Fragment key={group.label}>
                      {debtRow(group.label, group.label, refEntro + refOltre, origTotal, corrTotal, false)}
                      {debtRow(labelOf(group.entro[0]), group.label + "_entro", refEntro, origEntro, corrEntro, true,
                        isSingleEntro ? group.entro[0] : undefined)}
                      {debtRow(labelOf(group.oltre[0]), group.label + "_oltre", refOltre, origOltre, corrOltre, true,
                        isSingleOltre ? group.oltre[0] : undefined)}
                    </React.Fragment>
                  );
                })}
                {/* Totale debiti */}
                {(() => {
                  const origDebtTotal = (original["sp16_debiti_breve"] ?? 0) + (original["sp17_debiti_lungo"] ?? 0);
                  const corrDebtTotal = val("sp16_debiti_breve") + val("sp17_debiti_lungo");
                  return (
                    <TableRow className="font-medium">
                      <TableCell className="text-xs py-1.5 pl-4">Totale debiti</TableCell>
                      {hasRef && <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/50">
                        {formatEuro(refVal("sp16_debiti_breve") + refVal("sp17_debiti_lungo"))}
                      </TableCell>}
                      <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground">
                        {formatEuro(origDebtTotal)}
                      </TableCell>
                      <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/40">-</TableCell>
                      <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums font-medium">
                        {formatEuro(corrDebtTotal)}
                      </TableCell>
                    </TableRow>
                  );
                })()}

                {/* E) Ratei e risconti passivi */}
                {renderSection("", ["sp18_ratei_risconti_passivi"])}

                <TableRow className="bg-muted font-semibold">
                  <TableCell className="text-xs py-1.5">TOTALE PASSIVO</TableCell>
                  {hasRef && <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/50">
                    {formatEuro(PASSIVO_TOTAL_FIELDS.reduce((s, k) => s + refVal(k), 0))}
                  </TableCell>}
                  <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums">
                    {formatEuro(PASSIVO_TOTAL_FIELDS.reduce((s, k) => s + (original[k] ?? 0), 0))}
                  </TableCell>
                  <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/40">-</TableCell>
                  <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums font-semibold">
                    {formatEuro(totalPassivo)}
                  </TableCell>
                </TableRow>

              </TableBody>
            </Table>
          </div>

          <div className="border rounded-lg overflow-hidden mt-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Voce</TableHead>
                  {hasRef && <TableHead className="text-xs text-right">{referenceYear}</TableHead>}
                  <TableHead className="text-xs text-right">{periodEndDate}</TableHead>
                  <TableHead className="text-xs text-right">Rettifica</TableHead>
                  <TableHead className="text-xs text-right">{periodEndDate} Rett.</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {/* CE sectioned with subtotals */}
                {(() => {
                  const ceV = (k: string) => corrections[k] ?? original[k] ?? 0;
                  const origV = (k: string) => original[k] ?? 0;

                  const resultRow = (label: string, refValue: number, origVal: number, corrVal: number, bold = false) => {
                    const delta = corrVal - origVal;
                    const hasDelta = Math.abs(delta) > 0.01;
                    return (
                      <TableRow key={label} className={cn(bold && "bg-muted font-semibold")}>
                        <TableCell className={cn("text-xs py-1.5", bold && "font-semibold")}>{label}</TableCell>
                        {hasRef && (
                          <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground/50">
                            {formatEuro(refValue)}
                          </TableCell>
                        )}
                        <TableCell className="text-right text-xs py-1.5 font-mono tabular-nums text-muted-foreground">
                          {formatEuro(origVal)}
                        </TableCell>
                        <TableCell className={cn(
                          "text-right text-xs py-1.5 font-mono tabular-nums",
                          hasDelta ? (delta > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400") : "text-muted-foreground/40"
                        )}>
                          {hasDelta ? (delta > 0 ? "+" : "") + formatEuro(delta) : "-"}
                        </TableCell>
                        <TableCell className={cn("text-right text-xs py-1.5 font-mono tabular-nums", bold && "font-semibold")}>
                          {formatEuro(corrVal)}
                        </TableCell>
                      </TableRow>
                    );
                  };

                  // Compute subtotals
                  const sumF = (keys: string[], fn: (k: string) => number) => keys.reduce((s, k) => s + fn(k), 0);
                  const vp = sumF(CE_A, ceV);
                  const origVp = sumF(CE_A, origV);
                  const refVp = sumF(CE_A, refVal);
                  const costMainKeys = ["ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
                    "ce08_costi_personale", "ce09_ammortamenti", "ce10_var_rimanenze_mat_prime",
                    "ce11_accantonamenti", "ce11b_altri_accantonamenti", "ce12_oneri_diversi"];
                  const costs = sumF(costMainKeys, ceV);
                  const origCosts = sumF(costMainKeys, origV);
                  const refCosts = sumF(costMainKeys, refVal);
                  const ebit = vp - costs;
                  const origEbit = origVp - origCosts;
                  const refEbit = refVp - refCosts;
                  // EBITDA = EBIT + ammortamenti e svalutazioni
                  const ammort = ceV("ce09_ammortamenti");
                  const origAmmort = origV("ce09_ammortamenti");
                  const refAmmort = refVal("ce09_ammortamenti");
                  const ebitda = ebit + ammort;
                  const origEbitda = origEbit + origAmmort;
                  const refEbitda = refEbit + refAmmort;
                  const fin = ceV("ce13_proventi_partecipazioni") + ceV("ce14_altri_proventi_finanziari")
                    - ceV("ce15_oneri_finanziari") + ceV("ce16_utili_perdite_cambi");
                  const origFin = origV("ce13_proventi_partecipazioni") + origV("ce14_altri_proventi_finanziari")
                    - origV("ce15_oneri_finanziari") + origV("ce16_utili_perdite_cambi");
                  const refFinVal = refVal("ce13_proventi_partecipazioni") + refVal("ce14_altri_proventi_finanziari")
                    - refVal("ce15_oneri_finanziari") + refVal("ce16_utili_perdite_cambi");
                  const rett = ceV("ce17_rettifiche_attivita_fin");
                  const origRett = origV("ce17_rettifiche_attivita_fin");
                  const refRett = refVal("ce17_rettifiche_attivita_fin");
                  const straord = ceV("ce18_proventi_straordinari") - ceV("ce19_oneri_straordinari");
                  const origStraord = origV("ce18_proventi_straordinari") - origV("ce19_oneri_straordinari");
                  const refStraord = refVal("ce18_proventi_straordinari") - refVal("ce19_oneri_straordinari");
                  const pbt = ebit + fin + rett + straord;
                  const origPbt = origEbit + origFin + origRett + origStraord;
                  const refPbt = refEbit + refFinVal + refRett + refStraord;
                  const netProfit = pbt - ceV("ce20_imposte");
                  const origNetProfit = origPbt - origV("ce20_imposte");
                  const refNetProfit = refPbt - refVal("ce20_imposte");
                  const sp13 = val("sp13_utile_perdita");
                  const ceSpMatch = Math.abs(netProfit - sp13) < 1;

                  return (
                    <>
                      {renderSection("A) VALORE DELLA PRODUZIONE", CE_A, true)}
                      {resultRow("Totale valore della produzione", refVp, origVp, vp, false)}
                      {renderSection("B) COSTI DELLA PRODUZIONE", CE_B, true)}
                      {resultRow("Totale costi della produzione", refCosts, origCosts, costs, false)}
                      {resultRow("EBITDA (MOL)", refEbitda, origEbitda, ebitda, true)}
                      {resultRow("EBIT (Differenza tra valore e costi della produzione, A - B)", refEbit, origEbit, ebit, true)}
                      {renderSection("C) PROVENTI E ONERI FINANZIARI", CE_C, true)}
                      {resultRow("Totale proventi e oneri finanziari (15 + 16 - 17 +/- 17-bis)", refFinVal, origFin, fin, false)}
                      {renderSection("D) RETTIFICHE DI VALORE DI ATTIVITÀ E PASSIVITÀ FINANZIARIE", CE_D, true)}
                      {renderSection("E) PROVENTI E ONERI STRAORDINARI", CE_E, true)}
                      {resultRow("Risultato prima delle imposte (A - B +/- C +/- D +/- E)", refPbt, origPbt, pbt, true)}
                      {renderSection("", CE_IMPOSTE, true)}
                      {resultRow("21) Utile (perdita) dell'esercizio", refNetProfit, origNetProfit, netProfit, true)}
                      <TableRow className={cn(
                        "border-t-2",
                        ceSpMatch
                          ? "bg-green-50/50 dark:bg-green-950/10"
                          : "bg-red-50/50 dark:bg-red-950/10"
                      )}>
                        <TableCell colSpan={hasRef ? 4 : 3} className="text-xs py-1.5 font-medium">
                          Verifica CE ↔ SP: Utile CE = {formatEuro(netProfit)} | SP13 = {formatEuro(sp13)}
                        </TableCell>
                        <TableCell className={cn(
                          "text-right text-xs py-1.5 font-mono font-semibold",
                          ceSpMatch ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
                        )}>
                          {ceSpMatch ? "OK" : `diff: ${formatEuro(Math.abs(netProfit - sp13))}`}
                        </TableCell>
                      </TableRow>
                    </>
                  );
                })()}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Rettifiche applicate — journal of individual double-entry postings */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center justify-between">
            <span>Rettifiche applicate</span>
            <Badge variant="outline" className="font-mono">
              {visibleLog.length} / {RETTIFICHE_MAX}
            </Badge>
          </CardTitle>
          <CardDescription>
            Elenco delle scritture in partita doppia registrate. Elimina una voce per invertirne gli effetti.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {visibleLog.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground border rounded-lg border-dashed">
              Nessuna rettifica registrata. Modifica un valore nelle tabelle sopra per iniziare.
            </div>
          ) : (
            <div className="space-y-1.5">
              {visibleLog.map((e, i) => (
                <div key={e.id} className="flex items-center gap-2 border rounded-md px-3 py-2 text-xs">
                  <span className="text-muted-foreground w-5">{i + 1}.</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className="font-medium truncate">{e.edited_label.trim()}</span>
                      <span className={cn(
                        "font-mono tabular-nums font-semibold",
                        e.edit_delta > 0 ? "text-green-600 dark:text-green-400" : e.edit_delta < 0 ? "text-red-600 dark:text-red-400" : "text-muted-foreground"
                      )}>
                        {e.edit_delta > 0 ? "+" : ""}{formatEuro(e.edit_delta)}
                      </span>
                      {e.counterpart_field === "_correzione_import" ? (
                        <span className="text-muted-foreground italic text-xs">corr. import</span>
                      ) : (
                        <>
                          <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
                          <span className="text-muted-foreground truncate">{e.counterpart_label.trim()}</span>
                          <span className={cn(
                            "font-mono tabular-nums",
                            e.counterpart_delta > 0 ? "text-green-600 dark:text-green-400" : e.counterpart_delta < 0 ? "text-red-600 dark:text-red-400" : "text-muted-foreground"
                          )}>
                            {e.counterpart_delta > 0 ? "+" : ""}{formatEuro(e.counterpart_delta)}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                    onClick={() => deleteLogEntry(e.id)}
                    disabled={saving}
                    title="Elimina rettifica"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex items-center justify-between">
        <div>
          {adjustmentsApplied && (
            <Button variant="outline" size="sm" onClick={onReset} disabled={saving}>
              <RotateCcw className="h-4 w-4 mr-1.5" />
              Ripristina originale
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {saving && (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Loader2 className="h-3 w-3 animate-spin" /> Salvataggio...
            </span>
          )}
          <Button onClick={() => setShowSummaryDialog(true)}>
            Passa al Confronto <ArrowRight className="h-4 w-4 ml-1.5" />
          </Button>
        </div>
      </div>

      {/* Per-edit double-entry dialog */}
      <Dialog open={!!activeProposal} onOpenChange={(o) => { if (!o) cancelActiveEdit(); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{activeProposal?.mode === "correggi_import" ? "Correggi Importazione" : activeProposal?.mode === "riclassifica" ? "Registra Riclassifica" : "Registra Rettifica"}</DialogTitle>
            <DialogDescription>
              {activeProposal?.mode === "correggi_import"
                ? "Correggi un valore importato in modo errato. Modifica singola senza partita doppia."
                : activeProposal?.mode === "riclassifica"
                ? "Sposta l'importo tra voci dello stesso tipo (SP o CE) senza impatto sul Conto Economico."
                : "Scegli la contropartita per completare la partita doppia, poi conferma per registrare la rettifica."}
            </DialogDescription>
          </DialogHeader>

          {activeProposal && (() => {
            const p = activeProposal;
            const update = (patch: Partial<DoubleEntryProposal>) =>
              setActiveProposal((prev) => prev ? { ...prev, ...patch } : prev);
            const switchMode = (newMode: ProposalMode) => {
              // Reset counterpart selection when switching mode
              update({ mode: newMode, counterpartField: "", counterpartLabel: "", splitAlt: undefined });
            };
            const dirLabel = p.delta > 0 ? "+" : "";
            // For riclassifica, counterpart always moves opposite (one goes up, the other goes down)
            const effectiveDelta = p.mode === "riclassifica" ? -p.delta : p.proposedDelta;
            // Build the counterpart picker (shared by both layouts)
            const counterpartPicker = (onSelect: (field: string) => void) => (
              <Select
                value={p.counterpartField || undefined}
                onValueChange={onSelect}
              >
                <SelectTrigger className="h-7 flex-1 min-w-0 text-xs">
                  <SelectValue placeholder="Seleziona contropartita..." />
                </SelectTrigger>
                <SelectContent className="max-h-80">
                  {(() => {
                    const allowed = allowedCounterpartCategories(p.editedField, p.delta, p.mode);
                    return COUNTERPART_GROUPS.filter((g) => allowed.has(g.category)).map((g) => (
                      <SelectGroup key={g.label}>
                        <SelectLabel className="text-xs">{g.label}</SelectLabel>
                        {COUNTERPART_OPTIONS.filter((o) => o.category === g.category && o.field !== p.editedField).map((o) => (
                          <SelectItem key={o.field} value={o.field} className="text-xs">
                            {/* labelOf, non o.label: il selettore prende l'etichetta
                                autonoma dal catalogo come il resto della scheda.
                                Non si puo' spostare dentro COUNTERPART_OPTIONS —
                                lib/pratica-rettifiche-rules.ts importando il
                                catalogo chiuderebbe un ciclo (il catalogo importa
                                quel modulo) e il caricamento fallirebbe. */}
                            {labelOf(o.field)}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    ));
                  })()}
                </SelectContent>
              </Select>
            );
            return (
              <div className="space-y-3 my-2">
                {/* Mode toggle: Rettifica vs Riclassifica vs Correggi Import */}
                <div className="flex gap-2">
                  <Button
                    variant={p.mode === "rettifica" ? "default" : "outline"}
                    size="sm"
                    className="flex-1"
                    onClick={() => p.mode !== "rettifica" && switchMode("rettifica")}
                  >
                    Rettifica (SP ↔ CE)
                  </Button>
                  <Button
                    variant={p.mode === "riclassifica" ? "default" : "outline"}
                    size="sm"
                    className="flex-1"
                    onClick={() => p.mode !== "riclassifica" && switchMode("riclassifica")}
                  >
                    Riclassifica (stessa sezione)
                  </Button>
                  <Button
                    variant={p.mode === "correggi_import" ? "default" : "outline"}
                    size="sm"
                    className="flex-1"
                    onClick={() => p.mode !== "correggi_import" && switchMode("correggi_import")}
                  >
                    Correggi Import
                  </Button>
                </div>

                <div className="border rounded-lg p-3 bg-card">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="text-sm font-medium">{p.editedLabel}</span>
                    <span className={cn(
                      "text-sm font-mono tabular-nums font-semibold",
                      p.delta > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
                    )}>
                      {dirLabel}{formatEuro(p.delta)}
                    </span>
                  </div>

                  {p.mode === "correggi_import" ? (
                    /* Correggi Import: single-entry correction, no counterpart */
                    <p className="text-xs text-muted-foreground mt-1.5 italic">
                      Correzione singola per errore di importazione. Non richiede contropartita.
                    </p>
                  ) : p.mode === "riclassifica" ? (
                    /* Riclassifica: simple same-side move, always opposite delta, no split */
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      <ArrowRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                      {counterpartPicker((newField) => update({
                        counterpartField: newField,
                        counterpartLabel: labelOf(newField),
                        proposedDelta: -p.delta,
                        explanation: `Riclassifica: ${p.editedLabel} → ${labelOf(newField)}`,
                      }))}
                      <span className={cn(
                        "text-sm font-mono tabular-nums font-semibold w-36 text-right",
                        effectiveDelta > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
                      )}>
                        {effectiveDelta > 0 ? "+" : ""}{formatEuro(effectiveDelta)}
                      </span>
                    </div>
                  ) : p.splitAlt ? (
                    <>
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        <ArrowRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        {counterpartPicker((newField) => update({
                          counterpartField: newField,
                          counterpartLabel: labelOf(newField),
                          proposedDelta: computeCpDelta(p.editedField, newField, p.delta),
                          splitAlt: undefined,
                        }))}
                        <Input
                          className="h-7 w-36 text-right text-xs font-mono tabular-nums"
                          value={formatInputNumber(Math.round(p.proposedDelta - p.splitAlt.amount).toString())}
                          onChange={(e) => {
                            const raw = parseInputNumber(e.target.value);
                            const num = raw === "" || raw === "-" ? 0 : parseInt(raw, 10);
                            if (!isNaN(num) && p.splitAlt) {
                              update({ splitAlt: { ...p.splitAlt, amount: p.proposedDelta - num } });
                            }
                          }}
                        />
                      </div>
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        <ArrowRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="text-sm text-muted-foreground flex-1">{p.splitAlt.label}</span>
                        <Input
                          className="h-7 w-36 text-right text-xs font-mono tabular-nums"
                          value={formatInputNumber(Math.round(p.splitAlt.amount).toString())}
                          onChange={(e) => {
                            const raw = parseInputNumber(e.target.value);
                            const num = raw === "" || raw === "-" ? 0 : parseInt(raw, 10);
                            if (!isNaN(num) && p.splitAlt) {
                              update({ splitAlt: { ...p.splitAlt, amount: num } });
                            }
                          }}
                        />
                      </div>
                      <p className="text-xs text-muted-foreground/60 mt-0.5 ml-6">
                        Totale: {formatEuro(p.proposedDelta)}
                      </p>
                    </>
                  ) : (
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      <ArrowRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                      {counterpartPicker((newField) => update({
                        counterpartField: newField,
                        counterpartLabel: labelOf(newField),
                        proposedDelta: computeCpDelta(p.editedField, newField, p.delta),
                      }))}
                      <Input
                        className="h-7 w-36 text-right text-xs font-mono tabular-nums"
                        value={formatInputNumber(Math.round(p.proposedDelta).toString())}
                        onChange={(e) => {
                          const raw = parseInputNumber(e.target.value);
                          const num = raw === "" || raw === "-" ? 0 : parseInt(raw, 10);
                          if (!isNaN(num)) update({ proposedDelta: num });
                        }}
                      />
                    </div>
                  )}

                  <p className="text-xs text-muted-foreground mt-1 italic">{p.explanation}</p>
                </div>

                <p className="text-xs text-muted-foreground">
                  Rettifiche registrate: {visibleLog.length} / {RETTIFICHE_MAX}
                </p>
              </div>
            );
          })()}

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={cancelActiveEdit} disabled={saving}>
              Annulla
            </Button>
            <Button
              onClick={confirmActiveEdit}
              disabled={saving || (activeProposal?.mode !== "correggi_import" && !activeProposal?.counterpartField)}
            >
              {saving ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Check className="h-4 w-4 mr-1.5" />}
              {activeProposal?.mode === "correggi_import" ? "Applica correzione" : activeProposal?.mode === "riclassifica" ? "Registra riclassifica" : "Registra rettifica"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Summary dialog — shown before navigating to Confronto */}
      <Dialog open={showSummaryDialog} onOpenChange={setShowSummaryDialog}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Riepilogo Rettifiche</DialogTitle>
            <DialogDescription>
              Verifica tutte le modifiche apportate al bilancio originale prima di procedere al confronto.
            </DialogDescription>
          </DialogHeader>

          {(() => {
            // Collect all fields with deltas, grouped by section.
            // `isAggregate` = computed parent field (e.g. sp06_crediti_breve) whose delta
            // comes entirely from sub-field edits; shown in muted gray to avoid the
            // visual impression of a duplicate posting.
            type ChangedField = { field: string; label: string; origVal: number; newVal: number; delta: number; isAggregate: boolean };
            const bsAttivoChanges: ChangedField[] = [];
            const bsPassivoChanges: ChangedField[] = [];
            const ceChanges: ChangedField[] = [];

            const BS_ATTIVO_FIELDS = [
              "sp01_crediti_soci",
              "sp02_immob_immateriali", "sp03_immob_materiali", "sp04_immob_finanziarie",
              "sp05_rimanenze", "sp05a_materie_prime", "sp05b_prodotti_in_corso",
              "sp05c_lavori_in_corso", "sp05d_prodotti_finiti", "sp05e_acconti",
              "sp06_crediti_breve", "sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve",
              "sp06c_crediti_collegate_breve", "sp06d_crediti_controllanti_breve",
              "sp06e_crediti_tributari_breve", "sp06f_imposte_anticipate_breve", "sp06g_crediti_altri_breve",
              "sp07_crediti_lungo", "sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo",
              "sp07c_crediti_collegate_lungo", "sp07d_crediti_controllanti_lungo",
              "sp07e_crediti_tributari_lungo", "sp07f_imposte_anticipate_lungo", "sp07g_crediti_altri_lungo",
              "sp08_attivita_finanziarie", "sp09_disponibilita_liquide", "sp10_ratei_risconti_attivi",
            ];
            const BS_PASSIVO_FIELDS = [
              "sp11_capitale", "sp12_riserve", "sp12g_utili_perdite_portati",
              "sp13_utile_perdita", "sp14_fondi_rischi", "sp15_tfr",
              "sp16_debiti_breve", "sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve",
              "sp16c_debiti_obbligazioni_breve", "sp16d_debiti_fornitori_breve",
              "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve", "sp16g_altri_debiti_breve",
              "sp17_debiti_lungo", "sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo",
              "sp17c_debiti_obbligazioni_lungo", "sp17d_debiti_fornitori_lungo",
              "sp17e_debiti_tributari_lungo", "sp17f_debiti_previdenza_lungo", "sp17g_altri_debiti_lungo",
              "sp18_ratei_risconti_passivi",
            ];
            const CE_SUMMARY_FIELDS = [
              "ce01_ricavi_vendite", "ce02_variazioni_rimanenze", "ce03_lavori_interni", "ce04_altri_ricavi",
              "ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni",
              "ce08_costi_personale", "ce08b_salari_stipendi", "ce08c_oneri_sociali",
              "ce08a_tfr_accrual", "ce08d_altri_costi_personale",
              "ce09_ammortamenti", "ce09a_ammort_immateriali", "ce09b_ammort_materiali",
              "ce09c_svalutazioni", "ce09d_svalutazione_crediti",
              "ce10_var_rimanenze_mat_prime", "ce11_accantonamenti", "ce11b_altri_accantonamenti",
              "ce12_oneri_diversi",
              "ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari",
              "ce15_oneri_finanziari", "ce16_utili_perdite_cambi",
              "ce17_rettifiche_attivita_fin", "ce17a_rivalutazioni", "ce17b_svalutazioni",
              "ce18_proventi_straordinari", "ce19_oneri_straordinari", "ce20_imposte",
            ];

            const collectChanges = (fields: string[], target: ChangedField[]) => {
              for (const f of fields) {
                const origV = original[f] ?? 0;
                const corrV = corrections[f] ?? origV;
                const d = corrV - origV;
                if (Math.abs(d) >= 0.5) {
                  target.push({
                    field: f,
                    label: labelOf(f),
                    origVal: origV,
                    newVal: corrV,
                    delta: d,
                    isAggregate: NON_POSTABLE_FIELDS.has(f),
                  });
                }
              }
            };
            collectChanges(BS_ATTIVO_FIELDS, bsAttivoChanges);
            collectChanges(BS_PASSIVO_FIELDS, bsPassivoChanges);
            collectChanges(CE_SUMMARY_FIELDS, ceChanges);

            const totalChanges = bsAttivoChanges.length + bsPassivoChanges.length + ceChanges.length;

            // Balance check
            const ATTIVO_AGG = ["sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
              "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve",
              "sp07_crediti_lungo", "sp08_attivita_finanziarie", "sp09_disponibilita_liquide", "sp10_ratei_risconti_attivi"];
            const PASSIVO_AGG = ["sp11_capitale", "sp12_riserve", "sp13_utile_perdita",
              "sp14_fondi_rischi", "sp15_tfr", "sp16_debiti_breve", "sp17_debiti_lungo", "sp18_ratei_risconti_passivi"];
            const fv = (k: string) => corrections[k] ?? original[k] ?? 0;
            const tA = ATTIVO_AGG.reduce((s, k) => s + fv(k), 0);
            const tP = PASSIVO_AGG.reduce((s, k) => s + fv(k), 0);
            const balanced = Math.abs(tA - tP) < 1;

            const renderSection = (title: string, changes: ChangedField[]) => {
              if (changes.length === 0) return null;
              return (
                <div key={title}>
                  <h4 className="text-sm font-semibold mb-2 text-muted-foreground">{title}</h4>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-muted/50 text-xs text-muted-foreground">
                          <th className="text-left px-3 py-1.5 font-medium">Voce</th>
                          <th className="text-right px-3 py-1.5 font-medium w-32">Originale</th>
                          <th className="text-right px-3 py-1.5 font-medium w-32">Rettificato</th>
                          <th className="text-right px-3 py-1.5 font-medium w-32">Variazione</th>
                        </tr>
                      </thead>
                      <tbody>
                        {changes.map((c) => (
                          <tr
                            key={c.field}
                            className={cn(
                              "border-t border-border/50",
                              c.isAggregate && "text-muted-foreground/70 italic",
                            )}
                            title={c.isAggregate ? "Totale ricalcolato da sotto-voci (non è una rettifica diretta)" : undefined}
                          >
                            <td className="px-3 py-1.5">{c.label}</td>
                            <td className={cn(
                              "px-3 py-1.5 text-right font-mono tabular-nums",
                              c.isAggregate ? "text-muted-foreground/60" : "text-muted-foreground"
                            )}>
                              {formatEuro(c.origVal)}
                            </td>
                            <td className={cn(
                              "px-3 py-1.5 text-right font-mono tabular-nums",
                              c.isAggregate ? "" : "font-medium"
                            )}>
                              {formatEuro(c.newVal)}
                            </td>
                            <td className={cn(
                              "px-3 py-1.5 text-right font-mono tabular-nums",
                              c.isAggregate
                                ? "text-muted-foreground/70"
                                : cn("font-semibold", c.delta > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400")
                            )}>
                              {c.delta > 0 ? "+" : ""}{formatEuro(c.delta)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            };

            return (
              <div className="space-y-4 my-2">
                {totalChanges === 0 ? (
                  <div className="p-6 text-center text-sm text-muted-foreground border rounded-lg border-dashed">
                    Nessuna rettifica applicata. Il bilancio originale verr&agrave; utilizzato per il confronto.
                  </div>
                ) : (
                  <>
                    {renderSection("Stato Patrimoniale — Attivo", bsAttivoChanges)}
                    {renderSection("Stato Patrimoniale — Passivo e Netto", bsPassivoChanges)}
                    {renderSection("Conto Economico", ceChanges)}
                  </>
                )}

                {/* Balance check */}
                <div className={cn(
                  "p-3 rounded-lg border text-sm",
                  balanced
                    ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800"
                    : "bg-yellow-50 dark:bg-yellow-950/20 border-yellow-200 dark:border-yellow-800"
                )}>
                  <div className="flex items-center justify-between">
                    <div className="space-x-4">
                      <span className="text-muted-foreground">Totale Attivo:</span>
                      <span className="font-mono tabular-nums font-medium">{formatEuro(tA)}</span>
                      <span className="text-muted-foreground ml-4">Totale Passivo:</span>
                      <span className="font-mono tabular-nums font-medium">{formatEuro(tP)}</span>
                    </div>
                    {balanced ? (
                      <span className="text-green-600 dark:text-green-400 font-medium flex items-center gap-1 text-xs">
                        <Check className="h-3.5 w-3.5" /> Quadrato
                      </span>
                    ) : (
                      <span className="text-yellow-600 dark:text-yellow-400 font-medium text-xs">
                        Sbilancio: {formatEuro(tA - tP)}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })()}

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setShowSummaryDialog(false)}>
              Torna alle Rettifiche
            </Button>
            <Button onClick={() => { setShowSummaryDialog(false); onNext(); }}>
              <Check className="h-4 w-4 mr-1.5" />
              Conferma e Prosegui
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

