"""Gruppo DATI (v4 pagine 3-6, solo workflow infrannuale): bilancio infrannuale
e fonti, rettifiche apportate, dall'infrannuale alla chiusura, indicatori
dell'infrannuale. Non implementato in questa fase (fondazione M2-02D): registro
vuoto, nessuna pagina compare finché un agente successivo non lo popola.

Vincolo del proprietario da rispettare quando queste pagine verranno scritte
(`m2-02d.md`): pagina «rettifiche» = 4 KPI + grafico prima/dopo + UNA tabella di
9 righe sugli aggregati (Ricavi, Costi operativi, EBITDA, Ammortamenti, EBIT,
Oneri finanziari, Risultato ante imposte, Imposte, Risultato netto) con colonne
Prima · Rettifiche · Dopo — niente contropartite, niente periodi di confronto.

Nota per chi implementa: il Prima/Dopo di quei 9 aggregati esiste già, senza
calcolo, come le colonne `observed`/`adjusted` di `detailed_statements[0]`
(`basis="observed"` e `basis="adjusted"` per lo stesso anno) — ma SOLO per il
workflow infrannuale; per bilancio/startup quella coppia non è nel modello v2
(solo `adjustments.entries`, senza aggregati). Vedi la ricevuta di fondazione.
"""
from __future__ import annotations

from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2

GROUP = "dati"


def build(report: FinalReportModelV2) -> list[dict[str, Any]]:
    return []
