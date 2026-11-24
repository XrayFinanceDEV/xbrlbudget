"""Scrittura di stato patrimoniale e conto economico; diagnosi del lettore nel report.

Spostato da importers/pdf_importer.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import logging
import os
from database.models import BalanceSheet, IncomeStatement
from datetime import datetime
from decimal import Decimal
from typing import Dict
from importers.import_pdf.verdetti import (
    _TOL_QUADRATURA,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_importer")


def _create_balance_sheet(db, financial_year_id: int, data: Dict[str, Decimal]) -> 'BalanceSheet':
    """Create a lossless BalanceSheet record from every ORM ``sp*`` column.

    The previous hand-written constructor silently dropped entire detail families
    (sp01, sp02, sp03, sp05 and sp14).  Deriving the field registry from the model
    makes a newly supported IV-CEE field persist automatically and keeps all import
    routes aligned with the database schema.
    """
    fields = (c.name for c in BalanceSheet.__table__.columns if c.name.startswith('sp'))
    values = {field: data.get(field, Decimal('0')) for field in fields}
    bs = BalanceSheet(financial_year_id=financial_year_id, **values)
    db.add(bs)
    db.flush()
    return bs

def _create_income_statement(db, financial_year_id: int, data: Dict[str, Decimal]) -> 'IncomeStatement':
    """Create a lossless IncomeStatement record from every ORM ``ce*`` column."""
    fields = (c.name for c in IncomeStatement.__table__.columns if c.name.startswith('ce'))
    values = {field: data.get(field, Decimal('0')) for field in fields}
    inc = IncomeStatement(financial_year_id=financial_year_id, **values)
    db.add(inc)
    db.flush()
    return inc

def _lettore_diagnosi_import(file_path, extraction_context, fiscal_year, qd, unbalanced_reason, snello_report):
    """La diagnosi del lettore di righe per questo import: ``(diagnosi | None, frasi)``. Non solleva mai.

    Spenta con ``LETTORE_DIAGNOSI=0|false|no`` (nessuna chiave). Le frasi vanno all'utente solo se l'import
    stesso dichiara che qualcosa non torna; altrimenti la diagnosi resta in ``validation_report``."""
    if os.environ.get("LETTORE_DIAGNOSI", "1").strip().lower() in ("0", "false", "no", "off"):
        return None, []
    try:
        from importers.lettore.diagnosi import diagnosi_pdf, frasi_per_utente
        anno = fiscal_year or datetime.now().year
        diagnosi = diagnosi_pdf(file_path, extraction_context, anno_corrente=anno, anno_precedente=anno - 1)
    except Exception as exc:  # noqa: BLE001 - il lettore non ferma mai un import
        logger.warning(f"Lettore di righe non eseguito: {exc}")
        try:
            from importers.lettore.diagnosi import diagnosi_vuota
            return diagnosi_vuota("errore", f"{type(exc).__name__}: {exc}"[:300]), []
        except Exception:  # noqa: BLE001 - nemmeno l'import del lettore deve fermare l'import
            return {"esito": "errore", "motivo": f"{type(exc).__name__}: {exc}"[:300], "ingresso": "pdf", "tipo": "",
                    "contrapposto": False, "colonne": [], "blocchi_aperti": [], "avvisi": [], "secondi": 0.0}, []
    try:
        sezioni = set()
        if abs(qd.sbilancio) > _TOL_QUADRATURA:
            sezioni.add("SP")
        if not qd.utile_match:
            sezioni.add("CE")
        if (snello_report or {}).get("esito") in ("squadrato", "tappo"):
            sezioni.add("SP")
        if unbalanced_reason and not sezioni:
            sezioni = {"SP", "CE"}
        frasi = frasi_per_utente(diagnosi, sezioni, anno_precedente=anno - 1) if sezioni else []
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Frasi del lettore non prodotte: {exc}")
        frasi = []
    return diagnosi, frasi
