"""Migrazione una tantum per le imposte secondo il commercialista (2026-09-18).

Spec: docs/superpowers/specs/2026-09-18-imposte-commercialista-design.md §3.

Fino a questo lotto il motore budget applicava l'aliquota effettiva dell'anno base
quando era derivabile, e ignorava `tax_rate` (che le schermate mandavano sempre a
27,9). Ora applica `tax_rate` cosi' com'e'. Per non muovere i numeri degli scenari
esistenti, `tax_rate` riceve l'aliquota che il motore applicava gia':

- anno base depositato con effettiva derivabile → quell'effettiva;
- anno base promosso dall'infrannuale → l'aliquota proposta dall'ultimo consuntivo
  depositato (la regola nuova: e' il caso che il commercialista corregge);
- effettiva non derivabile → `tax_rate` invariato (era gia' quello applicato).

Le imposte anticipate non si muovono piu' in CE: `tax_temporary_differences` e
`sp06f_growth_pct` si azzerano. Gli scenari che li avevano CAMBIANO numeri, e lo
script li elenca.

Uso (dalla radice del repo, col venv del backend):
    python -m scripts.migra_imposte_commercialista [percorso.db]           # prova, non scrive
    python -m scripts.migra_imposte_commercialista [percorso.db] --apply   # scrive
Fare un backup del database prima di `--apply`.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.services.aliquota_service import aliquota_proposta
from calculations.projection_common import aliquota_effettiva
from database.models import BudgetAssumptions, BudgetScenario
from database.queries import get_fy_prefer_full

SEI = Decimal("0.000001")


@dataclass
class Modifica:
    scenario_id: int
    nome: str
    anno: int
    tax_rate_prima: Decimal
    tax_rate_dopo: Decimal
    motivo: str
    anticipate_azzerate: bool


def aliquota_da_scrivere(db: Session, scenario: BudgetScenario) -> tuple[Optional[Decimal], str]:
    base = get_fy_prefer_full(db, scenario.company_id, scenario.base_year)
    if base is None or base.income_statement is None:
        return None, "anno base assente: invariata"
    if base.promoted_from_scenario_id is not None:
        rate, anno = aliquota_proposta(db, scenario.company_id, scenario.base_year)
        return rate, f"anno base promosso: consuntivo {anno or 'non derivabile, 27,9'}"
    rate = aliquota_effettiva(base.income_statement)
    if rate is None:
        return None, "effettiva non derivabile: invariata"
    return rate, f"effettiva dell'anno base {scenario.base_year}"


def pianifica(db: Session) -> List[Modifica]:
    out: List[Modifica] = []
    scenari = db.query(BudgetScenario).filter(BudgetScenario.scenario_type == "budget").all()
    for sc in scenari:
        rate, motivo = aliquota_da_scrivere(db, sc)
        righe = db.query(BudgetAssumptions).filter(BudgetAssumptions.scenario_id == sc.id).all()
        for r in righe:
            prima = Decimal(str(r.tax_rate))
            dopo = rate.quantize(SEI) if rate is not None else prima
            anticipate = bool(r.tax_temporary_differences) or r.sp06f_growth_pct is not None
            if dopo != prima.quantize(SEI) or anticipate:
                out.append(Modifica(sc.id, sc.name, r.forecast_year, prima, dopo, motivo, anticipate))
    return out


def applica(db: Session, modifiche: List[Modifica]) -> None:
    for m in modifiche:
        r = (db.query(BudgetAssumptions)
             .filter(BudgetAssumptions.scenario_id == m.scenario_id,
                     BudgetAssumptions.forecast_year == m.anno).one())
        r.tax_rate = m.tax_rate_dopo
        if m.anticipate_azzerate:
            r.tax_temporary_differences = None
            r.sp06f_growth_pct = None
    db.commit()


def main(argv: List[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    percorso = args[0] if args else "financial_analysis.db"
    engine = create_engine(f"sqlite:///{percorso}")
    with sessionmaker(bind=engine)() as db:
        modifiche = pianifica(db)
        for m in modifiche:
            extra = "  + anticipate azzerate (CAMBIA i numeri)" if m.anticipate_azzerate else ""
            print(f"scenario {m.scenario_id} «{m.nome}» {m.anno}: tax_rate {m.tax_rate_prima} → "
                  f"{m.tax_rate_dopo} ({m.motivo}){extra}")
        print(f"{len(modifiche)} righe di ipotesi da aggiornare")
        if "--apply" in argv:
            applica(db, modifiche)
            print("applicato")
        else:
            print("prova: nulla scritto (--apply per scrivere)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
