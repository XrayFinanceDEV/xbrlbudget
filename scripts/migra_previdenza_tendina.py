"""Migrazione una tantum: la casella dei previdenziali diventa la tendina (A06).

Spec: fix rilievi AMBIENTA, lotto 3 (wizard), 2026-09-26, §3 A06.

Fino a questo lotto il motore leggeva `previdenza_scales_with_personnel`: acceso, faceva
scalare `sp16f`/`sp17f` col costo del personale, ignorando qualunque chiave `sp_indexing`
su quelle due voci (\"governata dall'interruttore previdenza/personale\"). Ora il motore
non legge piu' l'interruttore: l'unico modo di agganciare `sp16f`/`sp17f` al personale e'
`sp_indexing: {"sp16f": "personale", "sp17f": "personale"}`, come per le altre undici voci
minori indicizzabili.

Per ogni riga di ipotesi col flag acceso, questo script scrive `sp_indexing["sp16f"] =
sp_indexing["sp17f"] = "personale"` (anche quando la voce aveva gia' un altro driver: prima
vinceva la casella, e la migrazione lo dichiara nella riga stampata) e spegne il flag. I
numeri non cambiano: la tendina "personale" da' esattamente cio' che dava l'interruttore
(misurato — vedi il rapporto del task — anche con un piano pregresso su
`debiti_previdenziali`, perche' `validate_pregresso` impone che quel piano copra l'intero
saldo base, e allora il generato e' zero in entrambe le forme).

Uso (dalla radice del repo, col venv del backend):
    python -m scripts.migra_previdenza_tendina [percorso.db]           # prova, non scrive
    python -m scripts.migra_previdenza_tendina [percorso.db] --apply   # scrive
Fare un backup del database prima di `--apply`.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from database.models import BudgetAssumptions


@dataclass
class Modifica:
    scenario_id: int
    nome: str
    anno: int
    indicizzazione_prima: Optional[Dict[str, str]]
    indicizzazione_dopo: Dict[str, str]


def pianifica(db: Session) -> List[Modifica]:
    out: List[Modifica] = []
    righe = (
        db.query(BudgetAssumptions)
        .filter(BudgetAssumptions.previdenza_scales_with_personnel.is_(True))
        .all()
    )
    for r in righe:
        prima = r.sp_indexing if isinstance(r.sp_indexing, dict) else None
        dopo = dict(prima or {})
        dopo["sp16f"] = "personale"
        dopo["sp17f"] = "personale"
        nome = r.scenario.name if r.scenario is not None else "?"
        out.append(Modifica(r.scenario_id, nome, r.forecast_year, prima, dopo))
    return out


def applica(db: Session, modifiche: List[Modifica]) -> None:
    for m in modifiche:
        r = (
            db.query(BudgetAssumptions)
            .filter(
                BudgetAssumptions.scenario_id == m.scenario_id,
                BudgetAssumptions.forecast_year == m.anno,
            )
            .one()
        )
        r.sp_indexing = m.indicizzazione_dopo
        r.previdenza_scales_with_personnel = False
    db.commit()


def migra(db: Session, apply: bool) -> List[Modifica]:
    """Pianifica, e se `apply` scrive. Idempotente: una riga gia' migrata (flag spento) non
    e' piu' fra le righe pianificate alla corsa successiva."""
    modifiche = pianifica(db)
    if apply:
        applica(db, modifiche)
    return modifiche


def main(argv: List[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    percorso = args[0] if args else "financial_analysis.db"
    engine = create_engine(f"sqlite:///{percorso}")
    with sessionmaker(bind=engine)() as db:
        modifiche = migra(db, apply="--apply" in argv)
        for m in modifiche:
            print(
                f"scenario {m.scenario_id} «{m.nome}» {m.anno}: sp_indexing "
                f"{m.indicizzazione_prima} → {m.indicizzazione_dopo}, flag spento"
            )
        print(f"{len(modifiche)} righe di ipotesi da aggiornare")
        if "--apply" in argv:
            print("applicato")
        else:
            print("prova: nulla scritto (--apply per scrivere)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
