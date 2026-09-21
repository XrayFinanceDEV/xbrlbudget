"""Indicatori della crisi d'impresa dell'infrannuale (`GET .../infrannuale/crisi`)."""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel


class DefinizioneIndicatore(BaseModel):
    chiave: str
    etichetta: str
    formato: Literal["euro", "pct", "ratio"]
    # False per `of_revenue`: resa in tabella, fuori dal punteggio di crisi.
    nel_punteggio: bool


class RatingCrisi(BaseModel):
    codice: str
    etichetta: str
    livello: Literal["verde", "giallo", "arancio", "rosso"]
    oltre: int
    segnali: int


class ColonnaCrisi(BaseModel):
    chiave: Literal["storico", "infrannuale", "proiezione"]
    anno: int
    period_months: int
    # L'insieme completo con le chiavi del client, grezzi `_` compresi: i
    # grafici li leggono per non disegnare un rapporto che non esiste.
    indicatori: Dict[str, float]
    punteggi: Dict[str, float]
    # Con i segnali extracontabili SALVATI (lo storico non ne ha mai).
    rating: RatingCrisi
    # Indice = numero di segnali attivi, 0..7: lo schermo sceglie il rating
    # dal conteggio che ha in pagina, anche prima di salvarlo, senza tenere
    # una seconda copia delle bande.
    rating_per_segnali: List[RatingCrisi]


class CrisiInfrannuale(BaseModel):
    reference_year: int
    partial_year: int
    period_months: int
    segnali_attivi: int
    definizioni: List[DefinizioneIndicatore]
    storico: ColonnaCrisi
    infrannuale: ColonnaCrisi
    # None su un periodo gia' di 12 mesi o senza proiezione generata.
    proiezione: Optional[ColonnaCrisi] = None
