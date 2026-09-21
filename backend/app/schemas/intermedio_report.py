"""Modello del report intermedio (infrannuale + indicatori della crisi d'impresa).

Proiezione pura di dati gia' calcolati: bilanci importati, `ForecastYear`
persistito dal motore infrannuale, indicatori della crisi
(`calculations/crisi_impresa.py`) e commenti AI salvati. Il catalogo delle
pagine (`renderers/typst/intermedio_catalog.py`) legge solo questo modello.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel

from app.schemas.crisi import CrisiInfrannuale
from app.schemas.final_report_v2 import DetailedStatement

Colonna = Literal["storico", "infrannuale", "annualizzato", "proiezione"]


class CeAggregati(BaseModel):
    """Conto economico riclassificato di una colonna (`calculate_ce_result`)."""
    ricavi: Decimal
    valore_produzione: Decimal
    costi_operativi: Decimal
    ebitda: Decimal
    ammortamenti: Decimal
    ebit: Decimal
    oneri_finanziari: Decimal
    risultato_ante_imposte: Decimal
    imposte: Decimal
    risultato_netto: Decimal


class SpAggregati(BaseModel):
    """Stato patrimoniale sintetico di una colonna (proprieta' del modello ORM)."""
    immobilizzazioni: Decimal
    attivo_circolante: Decimal
    totale_attivo: Decimal
    patrimonio_netto: Decimal
    debiti_finanziari: Decimal
    debiti_operativi: Decimal
    cassa: Decimal
    ccn: Decimal


class ColonnaCe(BaseModel):
    chiave: Colonna
    etichetta: str
    ce: CeAggregati


class ColonnaSp(BaseModel):
    chiave: Colonna
    etichetta: str
    sp: SpAggregati


class Segnale(BaseModel):
    chiave: str
    etichetta: str
    attivo: bool


class IntermediateReportModel(BaseModel):
    generated_at: datetime
    company_name: str
    reference_year: int
    partial_year: int
    period_months: int
    # Colonne presenti nell'ordine di lettura; la proiezione manca su un
    # periodo di 12 mesi o finche' non e' stata generata.
    ce: List[ColonnaCe]
    sp: List[ColonnaSp]
    crisi: CrisiInfrannuale
    # I prospetti completi della Stampa, con le righe e i subtotali del report
    # finale (`build_detailed_statements`): CE su storico, infrannuale,
    # annualizzato e proiezione; SP su storico, infrannuale e proiezione.
    prospetto_ce: DetailedStatement
    prospetto_sp: DetailedStatement
    # Le sei chiavi di `save_infrannuale_comments`; testo vuoto = non scritto.
    commenti: Dict[str, str]
    commenti_stantii: bool
    # I sette segnali extracontabili, nell'ordine della Stampa, con lo stato salvato.
    segnali: List[Segnale]

    def colonna_ce(self, chiave: Colonna) -> Optional[CeAggregati]:
        return next((c.ce for c in self.ce if c.chiave == chiave), None)

    def colonna_sp(self, chiave: Colonna) -> Optional[SpAggregati]:
        return next((c.sp for c in self.sp if c.chiave == chiave), None)
