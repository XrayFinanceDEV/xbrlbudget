#!/usr/bin/env python3
"""Banco di parita' del motore di previsione: due versioni, stessa griglia.

Che cosa fa
-----------
Prende **due riferimenti git** (o un riferimento e l'albero di lavoro
corrente), estrae ciascuna versione di `calculations/` + `database/` +
`importers/` + `data/` + `config.py` in una cartella temporanea separata con
`git archive <ref> | tar -x` — **mai un `git checkout`**, che in questo repo
ha gia' divorato lavoro vivo due volte — genera una griglia di scenari
(azienda + anno base + ipotesi) da un seme fisso, e fa girare `compute_forecast`
di ciascuna versione, in un sottoprocesso isolato con `sys.path` puntato SOLO
alla cartella estratta di quella versione, cosi' le due versioni non si
contaminano mai a vicenda (nessun trucco di `sys.modules`, nessun rischio di
importare per sbaglio l'altra copia). Poi confronta **ogni cella**: ogni
colonna `sp*`/`ce*` di ogni anno di ogni scenario, piu' l'intero dizionario
`details` dell'anteprima — un difetto di questo lotto era visibile SOLO li',
senza che un numero a bilancio si muovesse.

Uso
---
    backend/venv/bin/python scripts/parita_motore.py 80887ae bd15e8b
    backend/venv/bin/python scripts/parita_motore.py 80887ae          # vs l'albero di lavoro
    backend/venv/bin/python scripts/parita_motore.py main HEAD --controllo-negativo
    backend/venv/bin/python scripts/parita_motore.py A B --json /tmp/parita.json --log /tmp/parita.log

Il campionamento
-----------------
Le masse dei fixture e le ipotesi generate sono **deliberatamente non
tonde**: una rata che si divide esattamente non mostra un difetto che nasce
dall'arrotondamento. In questo stesso lotto una sonda ha dichiarato «zero
occorrenze» di un difetto presente su 80 scenari su 90, perche' campionava
importi tondi — il difetto nasceva da mezzo centesimo in una rata. Ogni
importo qui e' generato da `random.Random(seed)` con cifre decimali casuali,
mai un multiplo di 100 o di 1000.

Il controllo negativo (`--controllo-negativo`)
-----------------------------------------------
Un banco che non e' mai stato visto fallire non ha provato niente. L'opzione
prende l'esito gia' calcolato della prima versione, aggiunge un centesimo a
una cella nota (`sp09_disponibilita_liquide` del primo anno riuscito del primo
scenario), confronta la copia perturbata con la seconda versione, e dichiara
se il banco l'ha vista. Non tocca il codice sorgente estratto — perturbare
l'ESITO e' equivalente a perturbare la formula che lo produce, senza dover
riscrivere un file sorgente diverso per ogni possibile coppia di riferimenti.

La frase che chi rivede questo banco deve leggere
---------------------------------------------------
    LA PARITA' SI PROVA CONTRO IL CODICE DI PRIMA, NON CONTRO SE' STESSI.

Cioe': la prova che conta non e' "il banco non trova nulla" (puo' voler dire
che il banco e' cieco), e' "il banco trova ESATTAMENTE la differenza nota
quando la differenza nota c'e', e tace quando non c'e'". Il `--controllo-
negativo` automatizza solo meta' di questa prova (che il banco veda un
errore iniettato); l'altra meta' — che trovi il difetto VERO di una coppia
di commit nota — va rifatta a mano ogni volta che si usa questo banco su una
coppia nuova, leggendo l'elenco delle divergenze, non solo il conteggio.

Uscita
------
Un registro leggibile su stdout (e su file con `--log`); `--json` aggiunge il
dettaglio macchina-leggibile. Zero divergenze e' una riga sola. Il codice di
uscita e' 0 (parita' confermata), 1 (divergenze trovate), 2 (errore di
estrazione o di esecuzione), 3 (il controllo negativo richiesto non ha visto
la propria perturbazione: il banco stesso e' da riparare).
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

D = Decimal
CENT = D("0.01")

# --------------------------------------------------------------------------- #
# I fixture di base: presi dal kit di test condiviso quando e' raggiungibile,
# altrimenti una copia locale identica (stessi importi, stesso commento sul
# perche' certi sotto-campi ci sono — vedi tests/e2e_kit.py per l'originale).
# --------------------------------------------------------------------------- #

try:
    from tests.e2e_kit import BASE_BS, BASE_CE, HOLDING_BS, HOLDING_CE  # type: ignore
    _FIXTURE_SOURCE = "tests/e2e_kit.py"
except Exception:  # pragma: no cover - fallback se il kit non e' raggiungibile
    BASE_BS = {
        "sp02_immob_immateriali": D("40000"), "sp03_immob_materiali": D("160000"),
        "sp05_rimanenze": D("50000"), "sp06_crediti_breve": D("120000"),
        "sp09_disponibilita_liquide": D("30000"), "sp11_capitale": D("100000"),
        "sp12_riserve": D("60000"), "sp13_utile_perdita": D("20000"),
        "sp15_tfr": D("30000"), "sp16_debiti_breve": D("140000"),
        "sp17_debiti_lungo": D("50000"), "sp05a_materie_prime": D("50000"),
        "sp06a_crediti_clienti_breve": D("120000"), "sp12e_altre_riserve": D("60000"),
        "sp16d_debiti_fornitori_breve": D("140000"), "sp17a_debiti_banche_lungo": D("50000"),
    }
    BASE_CE = {
        "ce01_ricavi_vendite": D("600000"), "ce05_materie_prime": D("200000"),
        "ce06_servizi": D("150000"), "ce07_godimento_beni": D("10000"),
        "ce08_costi_personale": D("120000"), "ce08a_tfr_accrual": D("8000"),
        "ce09_ammortamenti": D("40000"), "ce12_oneri_diversi": D("5000"),
        "ce15_oneri_finanziari": D("5000"), "ce20_imposte": D("50000"),
        "ce09b_ammort_materiali": D("40000"),
    }
    HOLDING_BS = {
        "sp04_immob_finanziarie": D("350000"), "sp09_disponibilita_liquide": D("50000"),
        "sp11_capitale": D("200000"), "sp12_riserve": D("130000"),
        "sp13_utile_perdita": D("20000"), "sp16_debiti_breve": D("50000"),
        "sp04a_partecipazioni": D("350000"), "sp12e_altre_riserve": D("130000"),
        "sp16d_debiti_fornitori_breve": D("50000"),
    }
    HOLDING_CE = {
        "ce01_ricavi_vendite": D("0"), "ce06_servizi": D("5000"),
        "ce13_proventi_partecipazioni": D("30000"), "ce20_imposte": D("5000"),
    }
    _FIXTURE_SOURCE = "copia locale (tests/e2e_kit.py non raggiungibile)"

def _con_banca_pregressa(bs: Dict[str, Decimal], breve: Decimal, lungo: Decimal) -> Dict[str, Decimal]:
    """Il fixture con debito bancario PREGRESSO non tondo, a breve e oltre.

    Perche' esiste (Task 16). Tutti i fixture di sopra hanno `sp16a` a zero: il
    breve e' spiegato per intero dai fornitori. Un banco cosi' e' cieco sulla rata
    del nuovo finanziamento che consumava il debito bancario pregresso a breve
    (Ruling 40), perche' `min(0, rata)` vale zero su qualunque versione. Il lungo
    pregresso sostituisce quello del kit, e la cassa riassorbe la differenza,
    cosi' che il fixture resti in pareggio e con i dettagli dei debiti esatti.
    """
    out = dict(bs)
    lungo_kit = D(str(bs.get("sp17a_debiti_banche_lungo", 0)))
    out["sp16a_debiti_banche_breve"] = breve
    out["sp16_debiti_breve"] = D(str(bs.get("sp16_debiti_breve", 0))) + breve
    out["sp17a_debiti_banche_lungo"] = lungo
    out["sp17_debiti_lungo"] = D(str(bs.get("sp17_debiti_lungo", 0))) + lungo - lungo_kit
    out["sp09_disponibilita_liquide"] = (
        D(str(bs.get("sp09_disponibilita_liquide", 0))) + breve + lungo - lungo_kit
    )
    return out


BANCA_BS = _con_banca_pregressa(BASE_BS, D("12345.67"), D("23456.79"))

# Scale non tonde: preservano il rapporto di ogni fixture (quindi anche il
# dpo = 3.600 giorni della holding) ma rendono ogni importo frazionario.
# I fixture nuovi vanno IN CODA: ogni fixture ha il proprio generatore, quindi
# quelli di prima restano identici estrazione per estrazione.
FIXTURES: List[Tuple[str, Dict[str, Decimal], Dict[str, Decimal], Decimal]] = [
    ("base", BASE_BS, BASE_CE, D("1")),
    ("base_scala_a", BASE_BS, BASE_CE, D("1.2347")),
    ("base_scala_b", BASE_BS, BASE_CE, D("0.68193")),
    ("holding", HOLDING_BS, HOLDING_CE, D("1")),
    ("holding_scala", HOLDING_BS, HOLDING_CE, D("1.07316")),
    ("banca", BANCA_BS, BASE_CE, D("1")),
]


def _scala(valori: Dict[str, Decimal], fattore: Decimal) -> Dict[str, str]:
    return {k: str((D(str(v)) * fattore).quantize(CENT)) for k, v in valori.items()}


# --------------------------------------------------------------------------- #
# Ipotesi: percentuali, giorni, importi — sempre non tondi.
# --------------------------------------------------------------------------- #

def _pct(rng: random.Random, lo: float, hi: float) -> str:
    return f"{rng.uniform(lo, hi):.3f}"


def _eur(rng: random.Random, lo: float, hi: float) -> str:
    return f"{rng.uniform(lo, hi):.2f}"


def _giorni(rng: random.Random, lo: float, hi: float) -> str:
    return f"{rng.uniform(lo, hi):.2f}"


def _anni_frazionari(rng: random.Random, lo: float, hi: float) -> str:
    return f"{rng.uniform(lo, hi):.2f}"


def profilo_neutro(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Nessuna ipotesi: dso/dio/dpo restano `None`, cioe' dedotti dall'anno
    base. E' il profilo che, sul fixture `holding` (dpo base = 3.600 giorni),
    fa scattare la guardia del Task 14."""
    return {}


def profilo_crescita(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    return {
        "revenue_growth_pct": _pct(rng, -20, 35),
        "other_revenue_growth_pct": _pct(rng, -20, 35),
        "variable_materials_growth_pct": _pct(rng, -15, 25),
        "fixed_materials_growth_pct": _pct(rng, -15, 25),
        "variable_services_growth_pct": _pct(rng, -15, 25),
        "fixed_services_growth_pct": _pct(rng, -15, 25),
        "personnel_growth_pct": _pct(rng, -10, 20),
        "other_costs_growth_pct": _pct(rng, -10, 20),
        "rent_growth_pct": _pct(rng, -10, 20),
        "fixed_materials_percentage": _pct(rng, 10, 70),
        "fixed_services_percentage": _pct(rng, 10, 70),
    }


def profilo_giorni_manuali(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """DSO/DIO/DPO espliciti: bypassano la guardia sul dedotto. Sul fixture
    `holding` NON deve muovere nulla fra le due versioni — e' il contrasto
    che conferma che il difetto del Task 14 sta solo nel ramo dedotto."""
    return {
        "dso_days": _giorni(rng, 20, 120),
        "dio_days": _giorni(rng, 5, 90),
        "dpo_days": _giorni(rng, 20, 150),
    }


def profilo_override_ce_sp(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    return {
        "ce04_override": _eur(rng, 1000, 40000),
        "ce07_override": _eur(rng, 2000, 30000),
        "ce12_override": _eur(rng, 500, 15000),
        "sp_overrides": {
            "sp10_ratei_risconti_attivi": _eur(rng, 200, 9000),
            "sp18_ratei_risconti_passivi": _eur(rng, 200, 9000),
        },
    }


def profilo_finanziamento(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    if anno_idx == 0:
        return {
            "financing_amount": _eur(rng, 50000, 150000),
            "financing_duration_years": "4",
            "financing_interest_rate": _pct(rng, 2, 6),
        }
    return {
        "cash_sweep_enabled": True,
        "cash_sweep_min_cash": _eur(rng, 5000, 40000),
    }


def profilo_fiscale(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    valori: Dict[str, Any] = {
        "tax_rate": _pct(rng, 20, 35),
        "tax_advances_paid": _eur(rng, 1000, 20000),
    }
    if anno_idx == 0:
        valori["tax_temporary_differences"] = [{
            "opening_amount": _eur(rng, 0, 5000),
            "additions": _eur(rng, 1000, 30000),
            "reversals": _eur(rng, 0, 8000),
            "kind": "deductible",
            "maturity": "short",
        }]
    return valori


def profilo_rimborso_indicizzazione(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    valori: Dict[str, Any] = {
        "existing_debt_repayment_years": _anni_frazionari(rng, 2, 7),
        "altri_finanz_repayment_years": _anni_frazionari(rng, 2, 7),
        "previdenza_scales_with_personnel": True,
        "sp_indexing": {"sp16g": "ricavi", "sp17d": "acquisti", "sp16f": "personale"},
    }
    if anno_idx == 1:
        valori["tfr_accrual_suspended"] = True
    return valori


def profilo_misto(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Combina crescita, override e fiscale: stress-test delle interazioni."""
    valori: Dict[str, Any] = {}
    valori.update(profilo_crescita(rng, anno_idx))
    valori.update(profilo_override_ce_sp(rng, anno_idx))
    valori.update(profilo_fiscale(rng, anno_idx))
    valori.update({
        "existing_debt_repayment_years": _anni_frazionari(rng, 3, 6),
    })
    return valori


def profilo_finanziamento_e_rimborso(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Prestito nuovo e piano del pregresso nello stesso scenario, senza cash sweep.

    Il piano dura meno dell'orizzonte: estinto il pregresso, la sua rata fissa
    sull'esposizione dell'anno base scendeva sul prestito nuovo che stava nella
    stessa voce `sp17a` (Task 16). Nessun profilo di sopra combina le due ipotesi.
    Sui fixture senza banca il piano non ha nulla da rimborsare: e' il contrasto
    che deve restare a zero celle.
    """
    valori: Dict[str, Any] = {"existing_debt_repayment_years": _anni_frazionari(rng, 1.2, 1.9)}
    if anno_idx == 0:
        valori.update({
            "financing_amount": _eur(rng, 50000, 150000),
            "financing_duration_years": "4",
            "financing_interest_rate": _pct(rng, 2, 6),
        })
    return valori


# I profili nuovi vanno IN CODA: il generatore di un fixture e' consumato profilo
# dopo profilo, quindi un profilo inserito in mezzo cambierebbe le estrazioni di
# tutti quelli che lo seguono.
PROFILI: Dict[str, Callable[[random.Random, int], Dict[str, Any]]] = {
    "neutro": profilo_neutro,
    "crescita": profilo_crescita,
    "giorni_manuali": profilo_giorni_manuali,
    "override_ce_sp": profilo_override_ce_sp,
    "finanziamento": profilo_finanziamento,
    "fiscale": profilo_fiscale,
    "rimborso_indicizzazione": profilo_rimborso_indicizzazione,
    "misto": profilo_misto,
    "finanziamento_e_rimborso": profilo_finanziamento_e_rimborso,
}


def costruisci_griglia(seed: int, num_anni: int) -> List[Dict[str, Any]]:
    """Griglia riproducibile: stesso seme, stessa griglia, sempre."""
    scenari: List[Dict[str, Any]] = []
    for fixture_nome, bs_base, ce_base, scala in FIXTURES:
        # Un generatore per fixture, non uno globale: la griglia di un fixture
        # non dipende dall'ordine in cui gli altri fixture sono elencati.
        rng = random.Random(f"{seed}:{fixture_nome}")
        bs = _scala(bs_base, scala)
        ce = _scala(ce_base, scala)
        for profilo_nome, profilo in PROFILI.items():
            anni_def = []
            for i in range(num_anni):
                anni_def.append({"anno": 2026 + 1 + i, "valori": profilo(rng, i)})
            scenari.append({
                "id": f"{fixture_nome}__{profilo_nome}",
                "base_year": 2026,
                "bs": bs,
                "ce": ce,
                "anni": anni_def,
            })
    return scenari


# --------------------------------------------------------------------------- #
# Estrazione via `git archive` — mai un `git checkout`.
# --------------------------------------------------------------------------- #

@dataclass
class Sorgente:
    etichetta: str
    root: Path
    e_albero_di_lavoro: bool


def _slug(testo: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in testo)


def estrai_sorgente(ref: Optional[str], tmp_root: Path) -> Sorgente:
    if ref is None:
        return Sorgente("albero di lavoro", REPO_ROOT, True)
    verifica = subprocess.run(
        ["git", "rev-parse", "--verify", ref], cwd=REPO_ROOT,
        capture_output=True, text=True,
    )
    if verifica.returncode != 0:
        raise RuntimeError(f"riferimento git non valido: {ref!r} ({verifica.stderr.strip()})")
    dest = tmp_root / _slug(ref)
    dest.mkdir(parents=True, exist_ok=True)
    comando = f"git archive {ref} | tar -x -C {dest}"
    estrazione = subprocess.run(
        comando, shell=True, cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if estrazione.returncode != 0:
        raise RuntimeError(f"'git archive {ref}' fallito: {estrazione.stderr.strip()}")
    return Sorgente(ref, dest, False)


# --------------------------------------------------------------------------- #
# Il driver: un processo per versione, sys.path puntato SOLO a quella cartella.
# Non importa nulla dello script che lo genera — comunica solo via JSON — cosi'
# le due versioni non condividono mai un modulo Python caricato in memoria.
# --------------------------------------------------------------------------- #

DRIVER = textwrap.dedent('''\
    """Driver isolato del banco di parita' — vedi scripts/parita_motore.py.

    Eseguito con `sys.path` puntato SOLO alla cartella estratta di UNA
    versione: costruisce un database SQLite in memoria, semina i fixture
    ricevuti in JSON, chiama `compute_forecast` (puro, non persiste nulla) e
    scrive l'esito in JSON. Non importa niente dallo strumento che lo lancia.
    """
    import json
    import sys
    from decimal import Decimal

    D = Decimal
    NON_IPOTESI = {"id", "scenario_id", "forecast_year", "created_at", "updated_at"}


    def _default_di_schema(colonna):
        """Il default che il DB applicherebbe all'INSERT — un oggetto ORM
        staccato non lo riceve da solo (vedi scripts/sensibilita_ipotesi.py)."""
        if colonna.default is None:
            return None
        grezzo = colonna.default.arg
        if isinstance(grezzo, bool):
            return grezzo
        if isinstance(grezzo, (int, float)):
            return D(str(grezzo))
        return grezzo


    def _parse(colonna, valore):
        if valore is None:
            return None
        tipo = str(colonna.type)
        if tipo.startswith("BOOLEAN"):
            return bool(valore)
        if tipo.startswith("JSON"):
            return valore
        return D(str(valore))


    def _serializza(valore):
        if isinstance(valore, Decimal):
            return str(valore)
        if isinstance(valore, dict):
            return {k: _serializza(v) for k, v in valore.items()}
        if isinstance(valore, (list, tuple)):
            return [_serializza(v) for v in valore]
        return valore


    def main() -> int:
        root_dir, percorso_input, percorso_output = sys.argv[1:4]
        sys.path.insert(0, root_dir)

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from database.db import Base
        from database.models import (
            Company, FinancialYear, BalanceSheet, IncomeStatement,
            BudgetScenario, BudgetAssumptions,
        )
        from calculations.forecast_engine import ForecastEngine, load_forecast_source

        dati = json.loads(open(percorso_input, encoding="utf-8").read())

        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        motore = ForecastEngine(db)
        colonne_assunzioni = {c.name: c for c in BudgetAssumptions.__table__.columns}

        esiti = {}
        for indice, scenario_def in enumerate(dati["scenari"]):
            sid = scenario_def["id"]
            try:
                company = Company(
                    name=f"parita {sid}", tax_id=f"PARITA{indice:04d}",
                    sector=1, user_id="parita-motore",
                )
                db.add(company)
                db.flush()
                fy = FinancialYear(
                    company_id=company.id, year=scenario_def["base_year"],
                    period_months=None, validation_status="verified", forecastable=True,
                )
                db.add(fy)
                db.flush()
                bs_kwargs = {k: D(v) for k, v in scenario_def["bs"].items()}
                ce_kwargs = {k: D(v) for k, v in scenario_def["ce"].items()}
                db.add(BalanceSheet(financial_year_id=fy.id, **bs_kwargs))
                db.add(IncomeStatement(financial_year_id=fy.id, **ce_kwargs))
                db.commit()

                scenario = BudgetScenario(
                    company_id=company.id, name=f"scenario {sid}",
                    base_year=scenario_def["base_year"], scenario_type="budget",
                )
                db.add(scenario)
                db.commit()

                sorgente = load_forecast_source(db, scenario.id)

                righe = []
                for anno_def in scenario_def["anni"]:
                    riga = BudgetAssumptions()
                    riga.scenario_id = scenario.id
                    riga.forecast_year = anno_def["anno"]
                    valori = anno_def["valori"]
                    for nome, colonna in colonne_assunzioni.items():
                        if nome in NON_IPOTESI:
                            continue
                        if nome in valori:
                            setattr(riga, nome, _parse(colonna, valori[nome]))
                        else:
                            setattr(riga, nome, _default_di_schema(colonna))
                    righe.append(riga)

                risultato = motore.compute_forecast(sorgente, righe, stop_on_error=False)

                voce = {"errore": None, "anni": []}
                if risultato.error:
                    voce["errore"] = {
                        "anno": risultato.error.year, "messaggio": risultato.error.message,
                    }
                for anno_ris in risultato.years:
                    voce["anni"].append({
                        "anno": anno_ris.year,
                        "balance_sheet": _serializza(anno_ris.balance_sheet),
                        "income_statement": _serializza(anno_ris.income_statement),
                        "details": _serializza(anno_ris.details),
                    })
                esiti[sid] = voce
            except Exception as exc:
                # Un fixture non forecastabile e' un ESITO da confrontare (l'altra
                # versione potrebbe accettarlo), non un crash del banco.
                esiti[sid] = {
                    "errore": {"anno": None, "messaggio": f"{type(exc).__name__}: {exc}"},
                    "anni": [],
                }
            finally:
                db.rollback()

        with open(percorso_output, "w", encoding="utf-8") as fh:
            json.dump(esiti, fh, ensure_ascii=False)
        return 0


    if __name__ == "__main__":
        sys.exit(main())
''')


def esegui_driver(python_bin: Path, driver_path: Path, root_dir: Path,
                  input_path: Path, output_path: Path) -> Dict[str, Any]:
    processo = subprocess.run(
        [str(python_bin), str(driver_path), str(root_dir), str(input_path), str(output_path)],
        capture_output=True, text=True,
    )
    if processo.returncode != 0:
        raise RuntimeError(
            f"il driver e' fallito su {root_dir}:\n"
            f"--- stdout ---\n{processo.stdout}\n--- stderr ---\n{processo.stderr}"
        )
    return json.loads(output_path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Confronto
# --------------------------------------------------------------------------- #

@dataclass
class Divergenza:
    scenario: str
    anno: Optional[int]
    campo: str
    valore_a: str
    valore_b: str


GIORNI_APPLICATI = {"dso_applied", "dio_applied", "dpo_applied"}


def _e_numero(v: Any) -> bool:
    if v is None or isinstance(v, bool):
        return False
    if isinstance(v, (int, float, Decimal)):
        return True
    if isinstance(v, str):
        try:
            D(v)
            return True
        except Exception:
            return False
    return False


def _e_vuoto(v: Any) -> bool:
    """Assente, lista/dizionario vuoto, zero o stringa vuota: il 'niente' che
    CLAUDE.md chiama «una chiave assente vale zero». Una chiave diagnostica
    NUOVA, dichiarata sempre ma vuota su ogni scenario che non la tocca (per
    esempio `degenerate_turnover_ratio`), non e' una divergenza reale rispetto
    a una versione che quella chiave non la scriveva proprio — lo sarebbe SOLO
    se comparisse con un contenuto non vuoto."""
    if v is None:
        return True
    if isinstance(v, bool):
        return v is False
    if isinstance(v, (list, dict, str)):
        return len(v) == 0
    if _e_numero(v):
        return D(str(v)) == 0
    return False


# Una chiave ASSENTE non e' una chiave presente con valore `None`. Prima di
# questo sentinella le due cose si confondevano (`dict.get` restituiva `None` in
# entrambi i casi), e il banco non vedeva una chiave nuova dichiarata a `None`:
# e' successo con `fabbisogno_picco_anno`, la sesta chiave del Task 12, mentre
# il rapporto ne contava cinque.
_ASSENTE = object()


def _uguali(campo: str, a: Any, b: Any) -> bool:
    if a is _ASSENTE or b is _ASSENTE:
        if a is b:
            return True
        presente = b if a is _ASSENTE else a
        # Una chiave nuova VUOTA (lista o dizionario vuoti, falso, stringa vuota)
        # resta non una divergenza, come dice `_e_vuoto`; una chiave nuova a
        # `None` si': `None` e' un valore dichiarato, non un'assenza.
        return presente is not None and _e_vuoto(presente)
    if a is None and b is None:
        return True
    if a is None:
        return _e_vuoto(b)
    if b is None:
        return _e_vuoto(a)
    ultimo_pezzo = campo.rsplit(".", 1)[-1]
    if ultimo_pezzo in GIORNI_APPLICATI and _e_numero(a) and _e_numero(b):
        # Giorni DEDOTTI: confrontati con una tolleranza di 6 decimali, non
        # bit-esatta, per non scambiare rumore di rappresentazione per un
        # difetto reale (vedi il docstring del modulo).
        return D(str(a)).quantize(D("0.000001")) == D(str(b)).quantize(D("0.000001"))
    if _e_numero(a) and _e_numero(b):
        return D(str(a)) == D(str(b))
    return a == b


def _fmt(v: Any) -> str:
    if v is _ASSENTE:
        return "(assente)"
    if v is None:
        return "—"
    if _e_numero(v):
        return f"{D(str(v)):,.2f}".replace(",", "·").replace(".", ",").replace("·", ".")
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def confronta_scenario(sid: str, esito_a: Dict[str, Any], esito_b: Dict[str, Any]
                       ) -> Tuple[List[Divergenza], int]:
    """(divergenze, celle confrontate)."""
    divergenze: List[Divergenza] = []
    celle = 0
    errore_a, errore_b = esito_a.get("errore"), esito_b.get("errore")
    celle += 1
    if bool(errore_a) != bool(errore_b):
        divergenze.append(Divergenza(
            sid, None, "@errore",
            _fmt(errore_a and errore_a.get("messaggio")),
            _fmt(errore_b and errore_b.get("messaggio")),
        ))
        return divergenze, celle
    if errore_a and errore_b:
        if errore_a.get("messaggio") != errore_b.get("messaggio") or errore_a.get("anno") != errore_b.get("anno"):
            divergenze.append(Divergenza(
                sid, errore_a.get("anno"), "@errore",
                _fmt(errore_a.get("messaggio")), _fmt(errore_b.get("messaggio")),
            ))
        return divergenze, celle

    anni_a = {a["anno"]: a for a in esito_a["anni"]}
    anni_b = {a["anno"]: a for a in esito_b["anni"]}
    for anno in sorted(set(anni_a) | set(anni_b)):
        ra, rb = anni_a.get(anno), anni_b.get(anno)
        celle += 1
        if ra is None or rb is None:
            divergenze.append(Divergenza(sid, anno, "@anno",
                                         "presente" if ra else "assente",
                                         "presente" if rb else "assente"))
            continue
        for prospetto in ("balance_sheet", "income_statement"):
            chiavi = sorted(set(ra[prospetto]) | set(rb[prospetto]))
            for chiave in chiavi:
                celle += 1
                va, vb = ra[prospetto].get(chiave, _ASSENTE), rb[prospetto].get(chiave, _ASSENTE)
                if not _uguali(f"{prospetto}.{chiave}", va, vb):
                    divergenze.append(Divergenza(sid, anno, f"{prospetto}.{chiave}",
                                                 _fmt(va), _fmt(vb)))
        chiavi_dettagli = sorted(set(ra["details"]) | set(rb["details"]))
        for chiave in chiavi_dettagli:
            celle += 1
            va, vb = ra["details"].get(chiave, _ASSENTE), rb["details"].get(chiave, _ASSENTE)
            if not _uguali(f"details.{chiave}", va, vb):
                divergenze.append(Divergenza(sid, anno, f"details.{chiave}",
                                             _fmt(va), _fmt(vb)))
    return divergenze, celle


def confronta_tutto(risultati_a: Dict[str, Any], risultati_b: Dict[str, Any]
                    ) -> Tuple[List[Divergenza], int]:
    divergenze: List[Divergenza] = []
    celle_totali = 0
    for sid in sorted(set(risultati_a) | set(risultati_b)):
        if sid not in risultati_a or sid not in risultati_b:
            divergenze.append(Divergenza(sid, None, "@scenario",
                                         "presente" if sid in risultati_a else "assente",
                                         "presente" if sid in risultati_b else "assente"))
            continue
        d, c = confronta_scenario(sid, risultati_a[sid], risultati_b[sid])
        divergenze.extend(d)
        celle_totali += c
    return divergenze, celle_totali


# --------------------------------------------------------------------------- #
# Controllo negativo
# --------------------------------------------------------------------------- #

def applica_controllo_negativo(risultati: Dict[str, Any]
                               ) -> Tuple[Dict[str, Any], Optional[Tuple[str, int, str]]]:
    """Copia `risultati` e aggiunge un centesimo a una cella nota. Ritorna la
    copia e la terna (scenario, anno, campo) perturbata, o `None` se la griglia
    non ha nessuna cella adatta (tutti gli scenari sono andati in errore)."""
    copia = json.loads(json.dumps(risultati))
    for sid in sorted(copia):
        esito = copia[sid]
        if esito.get("errore"):
            continue
        for anno_def in esito["anni"]:
            valore = anno_def["balance_sheet"].get("sp09_disponibilita_liquide")
            if valore is not None:
                nuovo = D(valore) + CENT
                anno_def["balance_sheet"]["sp09_disponibilita_liquide"] = str(nuovo)
                return copia, (sid, anno_def["anno"], "balance_sheet.sp09_disponibilita_liquide")
    return copia, None


# --------------------------------------------------------------------------- #
# Registro
# --------------------------------------------------------------------------- #

class Registro:
    def __init__(self, percorso: Optional[Path]):
        self.righe: List[str] = []
        self.percorso = percorso

    def __call__(self, testo: str = "") -> None:
        print(testo)
        self.righe.append(testo)

    def salva(self) -> None:
        if self.percorso:
            self.percorso.write_text("\n".join(self.righe) + "\n", encoding="utf-8")


def _trova_python(venv_hint: Optional[Path]) -> Path:
    candidati = []
    if venv_hint:
        candidati.append(venv_hint)
    candidati.append(REPO_ROOT / "backend" / "venv" / "bin" / "python")
    for c in candidati:
        if c.exists():
            return c
    return Path(sys.executable)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("ref_a", help="primo riferimento git (commit, tag, branch)")
    parser.add_argument("ref_b", nargs="?", default=None,
                        help="secondo riferimento; omesso = albero di lavoro corrente")
    parser.add_argument("--seed", type=int, default=20260910, help="seme della griglia")
    parser.add_argument("--anni", type=int, default=2, help="anni di piano per scenario (default 2)")
    parser.add_argument("--controllo-negativo", action="store_true", dest="controllo_negativo",
                        help="perturba di un centesimo l'esito della prima versione e verifica "
                             "che il confronto lo veda")
    parser.add_argument("--log", type=Path, default=None, help="file su cui scrivere il registro")
    parser.add_argument("--json", type=Path, default=None, help="dettaglio macchina-leggibile")
    parser.add_argument("--max-divergenze", type=int, default=60,
                        help="quante divergenze elencare in dettaglio (default 60)")
    parser.add_argument("--tmp-dir", type=Path, default=None,
                        help="cartella per l'estrazione (default: temporanea, ripulita a fine corsa)")
    argomenti = parser.parse_args()

    registro = Registro(argomenti.log)
    python_bin = _trova_python(None)

    registro("=" * 78)
    registro(f"BANCO DI PARITA' DEL MOTORE — {argomenti.ref_a} vs "
             f"{argomenti.ref_b or 'albero di lavoro'}")
    registro("=" * 78)
    registro(f"Fixture: {_FIXTURE_SOURCE}; seme {argomenti.seed}; {argomenti.anni} anni di piano; "
             f"python: {python_bin}")
    registro()

    proprio_tmp = argomenti.tmp_dir is None
    tmp_root = argomenti.tmp_dir or Path(tempfile.mkdtemp(prefix="parita_motore_"))
    tmp_root.mkdir(parents=True, exist_ok=True)

    try:
        sorgente_a = estrai_sorgente(argomenti.ref_a, tmp_root)
        sorgente_b = estrai_sorgente(argomenti.ref_b, tmp_root)
    except RuntimeError as errore:
        registro(f"ESTRAZIONE FALLITA: {errore}")
        registro.salva()
        return 2

    registro(f"Versione A: {sorgente_a.etichetta}"
             + (" (albero di lavoro, nessuna estrazione)" if sorgente_a.e_albero_di_lavoro
                else f" → {sorgente_a.root}"))
    registro(f"Versione B: {sorgente_b.etichetta}"
             + (" (albero di lavoro, nessuna estrazione)" if sorgente_b.e_albero_di_lavoro
                else f" → {sorgente_b.root}"))
    registro()

    griglia = costruisci_griglia(argomenti.seed, argomenti.anni)
    registro(f"Griglia: {len(griglia)} scenari ({len(FIXTURES)} fixture × {len(PROFILI)} profili "
             f"di ipotesi), {argomenti.anni} anni ciascuno.")
    registro()

    driver_path = tmp_root / "_driver_parita.py"
    driver_path.write_text(DRIVER, encoding="utf-8")
    input_path = tmp_root / "input.json"
    input_path.write_text(json.dumps({"scenari": griglia}, ensure_ascii=False), encoding="utf-8")

    try:
        registro(f"Calcolo su {sorgente_a.etichetta}...")
        output_a = tmp_root / "output_a.json"
        risultati_a = esegui_driver(python_bin, driver_path, sorgente_a.root, input_path, output_a)
        registro(f"Calcolo su {sorgente_b.etichetta}...")
        output_b = tmp_root / "output_b.json"
        risultati_b = esegui_driver(python_bin, driver_path, sorgente_b.root, input_path, output_b)
    except RuntimeError as errore:
        registro(f"ESECUZIONE FALLITA: {errore}")
        registro.salva()
        return 2
    registro()

    divergenze, celle = confronta_tutto(risultati_a, risultati_b)

    registro("-" * 78)
    registro("ESITO")
    registro("-" * 78)
    if not divergenze:
        registro(f"NESSUNA DIVERGENZA — {len(griglia)} scenari, {argomenti.anni} anni ciascuno, "
                 f"{celle} celle confrontate: le due versioni producono lo stesso previsionale "
                 f"su tutta la griglia.")
    else:
        registro(f"{len(divergenze)} DIVERGENZE su {celle} celle confrontate "
                 f"({len(griglia)} scenari, {argomenti.anni} anni ciascuno):")
        registro()
        for divergenza in divergenze[:argomenti.max_divergenze]:
            dove = f"anno {divergenza.anno}" if divergenza.anno is not None else "—"
            registro(f"  [{divergenza.scenario} · {dove}] {divergenza.campo}: "
                     f"{divergenza.valore_a}  →  {divergenza.valore_b}")
        if len(divergenze) > argomenti.max_divergenze:
            registro(f"  ... altre {len(divergenze) - argomenti.max_divergenze} divergenze non "
                     f"mostrate (vedi --max-divergenze o --json)")

    esito_controllo_negativo: Optional[bool] = None
    if argomenti.controllo_negativo:
        registro()
        registro("-" * 78)
        registro("CONTROLLO NEGATIVO")
        registro("-" * 78)
        perturbati, bersaglio = applica_controllo_negativo(risultati_a)
        if bersaglio is None:
            registro("Impossibile: nessuno scenario della versione A ha un anno riuscito con "
                     "sp09_disponibilita_liquide — il controllo negativo non e' costruibile.")
            esito_controllo_negativo = False
        else:
            sid, anno, campo = bersaglio
            divergenze_controllo, _ = confronta_tutto(perturbati, risultati_b)
            visto = any(d.scenario == sid and d.anno == anno and d.campo == campo
                       for d in divergenze_controllo)
            if visto:
                registro(f"SUPERATO: un centesimo iniettato in [{sid} · anno {anno}] {campo} "
                         f"e' stato visto dal confronto.")
                esito_controllo_negativo = True
            else:
                registro(f"FALLITO: un centesimo iniettato in [{sid} · anno {anno}] {campo} "
                         f"NON e' stato visto — il banco e' cieco, va riparato prima di fidarsi "
                         f"di un esito «nessuna divergenza».")
                esito_controllo_negativo = False

    registro()
    registro("=" * 78)
    registro(f"la parita' si prova contro il codice di prima, non contro se' stessi — "
             f"{len(griglia)} scenari, {celle} celle, {len(divergenze)} divergenze"
             + (f", controllo negativo {'superato' if esito_controllo_negativo else 'FALLITO'}"
                if esito_controllo_negativo is not None else ""))
    registro("=" * 78)

    registro.salva()
    if argomenti.json:
        argomenti.json.write_text(json.dumps({
            "ref_a": argomenti.ref_a, "ref_b": argomenti.ref_b, "seed": argomenti.seed,
            "scenari": len(griglia), "celle": celle,
            "divergenze": [d.__dict__ for d in divergenze],
            "controllo_negativo": esito_controllo_negativo,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    if proprio_tmp:
        shutil.rmtree(tmp_root, ignore_errors=True)

    if esito_controllo_negativo is False:
        return 3
    if divergenze:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
