#!/usr/bin/env python3
"""Banco di sensibilita' delle ipotesi del previsionale: una ipotesi alla volta.

Che cosa fa
-----------
Parte da una **linea di base neutra** (ogni ipotesi al proprio default di schema,
nessun override, nessun piano di rimborso), calcola il previsionale, poi muove
**un campo alla volta** e ricalcola. Per ogni campo dichiara:

- se il motore si e' fermato, e con quale messaggio;
- se qualche **invariante** che reggeva sulla linea di base ha smesso di reggere;
- se il campo e' risultato **inerte**, cioe' non ha mosso un solo centesimo;
- quali voci di CE e SP si sono mosse, e di quanto.

Non scrive nulla: usa `compute_forecast`, che e' il calcolo puro senza
persistenza, e costruisce le righe di ipotesi come oggetti staccati dalla
sessione. Il database viene solo letto.

Perche' esiste
--------------
Le regole del motore sono molte e falliscono in silenzio: un debito che non si
scarica, un credito che non si incassa, giorni medi incoerenti col circolante
producono un bilancio che **quadra lo stesso**. Nessun cancello li vede. Questo
banco li misura e li dichiara.

Uso
---
    backend/venv/bin/python scripts/sensibilita_ipotesi.py --scenario 6
    backend/venv/bin/python scripts/sensibilita_ipotesi.py --scenario 16 --anni 3 \
        --solo 'dso|dio|dpo|repayment' --log /tmp/banco.log

Uscita: un registro leggibile su stdout e, con `--log`, anche su file; `--json`
aggiunge il dettaglio macchina-leggibile. Il codice di uscita e' 1 se almeno un
invariante e' stato violato **da una perturbazione** (le violazioni gia'
presenti sulla linea di base sono segnalate ma non fanno fallire: sono un
difetto dei dati o del motore, non della sensibilita').
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calculations.ce_result import calculate_ce_result           # noqa: E402
from calculations.forecast_engine import (                        # noqa: E402
    ForecastComputation,
    ForecastEngine,
    load_forecast_source,
)
from calculations.projection_common import base_bank_debt         # noqa: E402
from database.db import SessionLocal                              # noqa: E402
from database.models import BudgetAssumptions, BudgetScenario     # noqa: E402

D = Decimal
ZERO = D("0")
CENT = D("0.01")
DAYS = D("360")

# Le colonne che non sono ipotesi: identita' della riga e marcatempo.
NON_IPOTESI = {"id", "scenario_id", "forecast_year", "created_at", "updated_at"}

ATTIVO = [
    "sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
    "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve",
    "sp07_crediti_lungo", "sp08_attivita_finanziarie",
    "sp09_disponibilita_liquide", "sp10_ratei_risconti_attivi",
]
PASSIVO = [
    "sp11_capitale", "sp12_riserve", "sp13_utile_perdita", "sp14_fondi_rischi",
    "sp15_tfr", "sp16_debiti_breve", "sp17_debiti_lungo",
    "sp18_ratei_risconti_passivi",
]

# Aggregati riconciliati: l'aggregato deve valere la somma dei propri dettagli.
# `ce17` e' deliberatamente fuori: il canone e' `ce17a - ce17b`, non una somma.
AGGREGATI: Dict[str, List[str]] = {
    "sp04_immob_finanziarie": [
        "sp04a_partecipazioni", "sp04b_crediti_immob_breve",
        "sp04c_crediti_immob_lungo", "sp04d_altri_titoli",
        "sp04e_strumenti_derivati_attivi",
    ],
    "sp05_rimanenze": [
        "sp05a_materie_prime", "sp05b_prodotti_in_corso",
        "sp05c_lavori_in_corso", "sp05d_prodotti_finiti", "sp05e_acconti",
    ],
    "sp06_crediti_breve": [
        "sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve",
        "sp06c_crediti_collegate_breve", "sp06d_crediti_controllanti_breve",
        "sp06e_crediti_tributari_breve", "sp06f_imposte_anticipate_breve",
        "sp06g_crediti_altri_breve",
    ],
    "sp07_crediti_lungo": [
        "sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo",
        "sp07c_crediti_collegate_lungo", "sp07d_crediti_controllanti_lungo",
        "sp07e_crediti_tributari_lungo", "sp07f_imposte_anticipate_lungo",
        "sp07g_crediti_altri_lungo",
    ],
    "sp12_riserve": [
        "sp12a_riserva_sovrapprezzo", "sp12b_riserve_rivalutazione",
        "sp12c_riserva_legale", "sp12d_riserve_statutarie",
        "sp12e_altre_riserve", "sp12f_riserva_copertura_flussi",
        "sp12g_utili_perdite_portati", "sp12h_riserva_neg_azioni_proprie",
    ],
    "sp14_fondi_rischi": [
        "sp14a_fondi_trattamento_quiescenza", "sp14b_fondi_imposte",
        "sp14c_strumenti_derivati_passivi", "sp14d_altri_fondi",
    ],
    "sp16_debiti_breve": [
        "sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve",
        "sp16c_debiti_obbligazioni_breve", "sp16d_debiti_fornitori_breve",
        "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve",
        "sp16g_altri_debiti_breve",
    ],
    "sp17_debiti_lungo": [
        "sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo",
        "sp17c_debiti_obbligazioni_lungo", "sp17d_debiti_fornitori_lungo",
        "sp17e_debiti_tributari_lungo", "sp17f_debiti_previdenza_lungo",
        "sp17g_altri_debiti_lungo",
    ],
    "ce08_costi_personale": [
        "ce08a_tfr_accrual", "ce08b_salari_stipendi", "ce08c_oneri_sociali",
        "ce08d_altri_costi_personale",
    ],
    "ce09_ammortamenti": [
        "ce09a_ammort_immateriali", "ce09b_ammort_materiali",
        "ce09c_svalutazioni", "ce09d_svalutazione_crediti",
    ],
}

BANCHE = ["sp16a_debiti_banche_breve", "sp17a_debiti_banche_lungo"]


# --------------------------------------------------------------------------- #
# Linea di base
# --------------------------------------------------------------------------- #

def _default_di_schema(colonna) -> Any:
    """Il default che il DB applicherebbe all'INSERT.

    Un oggetto ORM staccato **non** riceve i default di colonna: quelli scattano
    alla scrittura. Costruire la linea di base senza questo passaggio darebbe
    `None` su campi `nullable=False` e farebbe esplodere il motore su un
    `None / 100` — un errore che non dice nulla sulle ipotesi.
    """
    if colonna.default is None:
        return None
    grezzo = colonna.default.arg
    if isinstance(grezzo, bool):        # prima di int: bool E' un int
        return grezzo
    if isinstance(grezzo, (int, float)):
        return D(str(grezzo))
    return grezzo


def linea_di_base(scenario: BudgetScenario, anni: Sequence[int]) -> List[BudgetAssumptions]:
    """Una riga per anno, ogni ipotesi al default, aliquota 27,9.

    27,9 (IRES + IRAP) e non il 24 dello schema: 24 e' il default Pydantic che
    nessuna schermata invia. Partire dal 24 misurerebbe un prodotto che non
    esiste. Resta comunque un ripiego: il motore preferisce l'aliquota effettiva
    dell'anno base quando e' derivabile.
    """
    righe = []
    for anno in anni:
        riga = BudgetAssumptions()
        riga.scenario_id = scenario.id
        riga.forecast_year = anno
        for colonna in BudgetAssumptions.__table__.columns:
            if colonna.name in NON_IPOTESI:
                continue
            setattr(riga, colonna.name, _default_di_schema(colonna))
        riga.tax_rate = D("27.9")
        righe.append(riga)
    return righe


def clona(righe: Sequence[BudgetAssumptions], scenario_id: int) -> List[BudgetAssumptions]:
    copie = []
    for riga in righe:
        copia = BudgetAssumptions()
        copia.scenario_id = scenario_id
        copia.forecast_year = riga.forecast_year
        for colonna in BudgetAssumptions.__table__.columns:
            if colonna.name in NON_IPOTESI:
                continue
            valore = getattr(riga, colonna.name)
            if isinstance(valore, (list, dict)):
                valore = json.loads(json.dumps(valore, default=str))
            setattr(copia, colonna.name, valore)
        copie.append(copia)
    return copie


# --------------------------------------------------------------------------- #
# Invarianti
# --------------------------------------------------------------------------- #

class Rilievo:
    def __init__(self, codice: str, gravita: str, anno: Optional[int], testo: str):
        self.codice = codice
        self.gravita = gravita          # 'rotto' | 'sospetto'
        self.anno = anno
        self.testo = testo

    @property
    def chiave(self) -> str:
        return f"{self.codice}@{self.anno}"

    def __str__(self) -> str:
        dove = f"{self.anno}" if self.anno is not None else "—"
        return f"[{self.codice} {dove}] {self.testo}"


def _n(d: Dict[str, Any], chiave: str) -> Decimal:
    valore = d.get(chiave)
    if valore is None:
        return ZERO
    return valore if isinstance(valore, Decimal) else D(str(valore))


def _somma(d: Dict[str, Any], chiavi: Sequence[str]) -> Decimal:
    return sum((_n(d, k) for k in chiavi), ZERO)


def _eur(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "·").replace(".", ",").replace("·", ".") + " €"


def invarianti(calcolo: ForecastComputation, sorgente) -> List[Rilievo]:
    """Le regole che devono reggere su ogni anno prodotto, quali che siano le ipotesi."""
    rilievi: List[Rilievo] = []
    debito_banche_apertura = base_bank_debt(
        lambda campo: getattr(sorgente.base_bs, campo, None) or ZERO
    )
    precedente_bs: Optional[Dict[str, Any]] = None
    precedente_utile = ZERO
    banche_precedenti = debito_banche_apertura

    for risultato in calcolo.years:
        anno = risultato.year
        bs, inc, dettagli = risultato.balance_sheet, risultato.income_statement, risultato.details

        # Q1 — il pareggio contabile.
        attivo, passivo = _somma(bs, ATTIVO), _somma(bs, PASSIVO)
        if abs(attivo - passivo) > CENT:
            rilievi.append(Rilievo("Q1", "rotto", anno,
                f"attivo {_eur(attivo)} != passivo {_eur(passivo)} "
                f"(scarto {_eur(attivo - passivo)})"))

        # Q2 — il risultato del CE deve stare in sp13.
        ce = calculate_ce_result(inc)
        if abs(ce.net_profit - _n(bs, "sp13_utile_perdita")) > CENT:
            rilievi.append(Rilievo("Q2", "rotto", anno,
                f"utile di CE {_eur(ce.net_profit)} != sp13 "
                f"{_eur(_n(bs, 'sp13_utile_perdita'))}"))

        # Q3 — MOL = RO + ammortamenti (identita' OIC, non un'opinione).
        if abs(ce.ebitda - (ce.ebit + _n(inc, "ce09_ammortamenti"))) > CENT:
            rilievi.append(Rilievo("Q3", "rotto", anno,
                f"MOL {_eur(ce.ebitda)} != RO {_eur(ce.ebit)} + ammortamenti "
                f"{_eur(_n(inc, 'ce09_ammortamenti'))}"))

        # Q4 — la cassa e' il plug e plugga solo verso l'alto: negativa non esiste.
        cassa = _n(bs, "sp09_disponibilita_liquide")
        if cassa < -CENT:
            rilievi.append(Rilievo("Q4", "rotto", anno,
                f"cassa negativa {_eur(cassa)}: il plug e' solo verso l'alto, "
                f"un fabbisogno scoperto deve fermare il motore"))

        # A* — ogni aggregato riconciliato vale la somma dei suoi dettagli.
        for aggregato, dettagli_voci in AGGREGATI.items():
            fonte = bs if aggregato.startswith("sp") else inc
            totale, parti = _n(fonte, aggregato), _somma(fonte, dettagli_voci)
            if abs(totale - parti) > CENT:
                rilievi.append(Rilievo("A1", "rotto", anno,
                    f"{aggregato} {_eur(totale)} != somma dei dettagli {_eur(parti)} "
                    f"(scarto {_eur(totale - parti)})"))

        # C* — il circolante deve discendere dai giorni medi che il motore dichiara.
        ricavi = _n(inc, "ce01_ricavi_vendite")
        acquisti = _n(inc, "ce05_materie_prime") + _n(inc, "ce06_servizi")
        dso, dio, dpo = (dettagli.get(k) for k in ("dso_applied", "dio_applied", "dpo_applied"))

        if dso is not None:
            crediti_commerciali = (
                _n(bs, "sp06_crediti_breve")
                - _n(bs, "sp06e_crediti_tributari_breve")
                - _n(bs, "sp06f_imposte_anticipate_breve")
            )
            atteso = ricavi * D(str(dso)) / DAYS
            if abs(crediti_commerciali - atteso) > CENT:
                rilievi.append(Rilievo("C1", "rotto", anno,
                    f"crediti commerciali {_eur(crediti_commerciali)} != ricavi × DSO/360 "
                    f"{_eur(atteso)}"))
        if dio is not None:
            atteso = ricavi * D(str(dio)) / DAYS
            if abs(_n(bs, "sp05_rimanenze") - atteso) > CENT:
                rilievi.append(Rilievo("C2", "rotto", anno,
                    f"rimanenze {_eur(_n(bs, 'sp05_rimanenze'))} != ricavi × DIO/360 "
                    f"{_eur(atteso)}"))
        if dpo is not None:
            atteso = acquisti * D(str(dpo)) / DAYS
            if abs(_n(bs, "sp16d_debiti_fornitori_breve") - atteso) > CENT:
                rilievi.append(Rilievo("C3", "rotto", anno,
                    f"debiti fornitori {_eur(_n(bs, 'sp16d_debiti_fornitori_breve'))} != "
                    f"acquisti × DPO/360 {_eur(atteso)}"))

        # G1 — giorni medi fuori scala. Non e' una rottura del motore: e'
        # un'incoerenza fra i giorni medi e il circolante che l'utente legge.
        for nome, valore in (("DSO", dso), ("DIO", dio), ("DPO", dpo)):
            if valore is None:
                continue
            giorni = D(str(valore))
            if giorni < 0 or giorni > D("365"):
                rilievi.append(Rilievo("G1", "sospetto", anno,
                    f"{nome} = {giorni:,.0f} giorni: fuori da ogni scala reale. "
                    f"E' il numero che il passo «giorni medi» mostra come automatico"))

        # D1/D2 — il debito bancario si scarica, e non cresce da solo.
        banche = _somma(bs, BANCHE)
        if banche - banche_precedenti > CENT:
            rilievi.append(Rilievo("D2", "sospetto", anno,
                f"debito bancario cresciuto da {_eur(banche_precedenti)} a {_eur(banche)} "
                f"senza un finanziamento nuovo fra le ipotesi"))
        banche_precedenti = banche

        # P1 — il patrimonio netto rotola: capitale + riserve dell'anno N devono
        # valere capitale + riserve + utile dell'anno N-1 (nessun dividendo fra
        # le ipotesi, nessuna delibera).
        if precedente_bs is not None:
            netto_atteso = (
                _somma(precedente_bs, ["sp11_capitale", "sp12_riserve"]) + precedente_utile
            )
            netto = _somma(bs, ["sp11_capitale", "sp12_riserve"])
            if abs(netto - netto_atteso) > CENT:
                rilievi.append(Rilievo("P1", "rotto", anno,
                    f"capitale+riserve {_eur(netto)} != quelli dell'anno prima piu' il suo "
                    f"utile {_eur(netto_atteso)} (scarto {_eur(netto - netto_atteso)})"))
        precedente_bs, precedente_utile = bs, _n(bs, "sp13_utile_perdita")

    return rilievi


# --------------------------------------------------------------------------- #
# Perche' un campo e' inerte
# --------------------------------------------------------------------------- #
#
# «Inerte» da solo non e' un rilievo: un `sp14_growth_pct` non muove nulla se
# l'azienda non ha fondi rischi, ed e' giusto cosi'. Le tre spiegazioni qui
# sotto separano i tre casi, perche' solo il terzo e' un difetto.

# Il campo fa crescere una voce precisa: se quella voce e' zero nell'anno base,
# una percentuale su zero e' zero.
VOCE_PILOTATA = {
    "sp01_growth_pct": "sp01_crediti_soci",
    "sp04_growth_pct": "sp04_immob_finanziarie",
    "sp06e_growth_pct": "sp06e_crediti_tributari_breve",
    "sp06f_growth_pct": "sp06f_imposte_anticipate_breve",
    "sp08_growth_pct": "sp08_attivita_finanziarie",
    "sp10_growth_pct": "sp10_ratei_risconti_attivi",
    "sp14_growth_pct": "sp14_fondi_rischi",
    "sp16e_growth_pct": "sp16e_debiti_tributari_breve",
    "sp16f_growth_pct": "sp16f_debiti_previdenza_breve",
    "sp16g_growth_pct": "sp16g_altri_debiti_breve",
    "sp17d_growth_pct": "sp17d_debiti_fornitori_lungo",
    "sp17e_growth_pct": "sp17e_debiti_tributari_lungo",
    "sp17f_growth_pct": "sp17f_debiti_previdenza_lungo",
    "sp17g_growth_pct": "sp17g_altri_debiti_lungo",
    "sp18_growth_pct": "sp18_ratei_risconti_passivi",
    "receivables_long_growth_pct": "sp07_crediti_lungo",
    "altri_finanz_repayment_years": "sp16b_debiti_altri_finanz_breve",
    # Voci di CE: una percentuale sui servizi non muove nulla in un'azienda che
    # non ne ha. Capita davvero (AIC SRL 2025 ha ce06 = 0).
    "variable_services_growth_pct": "ce06_servizi",
    "fixed_services_growth_pct": "ce06_servizi",
    "fixed_services_percentage": "ce06_servizi",
    "variable_materials_growth_pct": "ce05_materie_prime",
    "fixed_materials_growth_pct": "ce05_materie_prime",
    "fixed_materials_percentage": "ce05_materie_prime",
    "personnel_growth_pct": "ce08_costi_personale",
    # Non ce08: la quota TFR e' derivata da ce08b e limitata dal residuo, quindi
    # un'azienda con ce08 == ce08b non ha alcuna quota da sospendere.
    "tfr_accrual_suspended": "ce08a_tfr_accrual",
    "rent_growth_pct": "ce07_godimento_beni",
    "previdenza_scales_with_personnel": "sp16f_debiti_previdenza_breve",
    # Il debito bancario di apertura non e' una colonna sola: e' la somma delle
    # banche piu' gli scarti aggregato/dettaglio, come lo calcola il motore.
    "existing_debt_repayment_years": "@banche",
    "cash_sweep_enabled": "@banche",
    "cash_sweep_min_cash": "@banche",
}

# Il campo ha bisogno che un altro sia acceso. Il banco riprova accendendolo:
# se allora si muove, non e' un difetto ma un accoppiamento, e va detto cosi'.
ACCOPPIAMENTI = {
    "depreciation_rate": {"tangible_investments": D("100000")},
    "depreciation_rate_intangible": {"intangible_investments": D("100000")},
    "financing_amount": {"financing_duration_years": D("5"),
                         "financing_interest_rate": D("4")},
    "financing_duration_years": {"financing_amount": D("100000"),
                                 "financing_interest_rate": D("4")},
    "financing_interest_rate": {"financing_amount": D("100000"),
                                "financing_duration_years": D("5")},
    "cash_sweep_min_cash": {"cash_sweep_enabled": True},
    "previdenza_scales_with_personnel": {"personnel_growth_pct": D("10")},
    "tfr_accrual_suspended": {"personnel_growth_pct": D("10")},
}

# Il motore non legge proprio la colonna: e' documentato, e va confermato, non
# scoperto ogni volta.
NON_LETTI = {
    "receivables_short_growth_pct": "colonna morta: il circolante a breve passa dal DSO",
    "payables_short_growth_pct": "colonna morta: i debiti commerciali passano dal DPO",
    "interest_rate_receivables": "colonna morta: nessun punto di lettura nel motore",
    "interest_rate_payables": "colonna morta: nessun punto di lettura nel motore",
    "tax_rate": "ripiego: il motore preferisce l'aliquota effettiva dell'anno base "
                "quando e' derivabile (CLAUDE.md)",
}


# --------------------------------------------------------------------------- #
# Perturbazioni
# --------------------------------------------------------------------------- #

CE_OVERRIDE = re.compile(r"^(ce\d+[a-z]?)_override$")


def voce_di_ce(codice: str, chiavi: Sequence[str]) -> Optional[str]:
    for chiave in chiavi:
        if chiave.startswith(codice + "_"):
            return chiave
    return None


def perturbazioni(colonna, base_inc: Dict[str, Any], base_bs: Dict[str, Any]
                  ) -> List[Tuple[str, Any]]:
    """(etichetta, valore) per un campo. Elenco vuoto = campo non perturbabile qui."""
    nome = str(colonna.name)
    tipo = str(colonna.type)

    corrispondenza = CE_OVERRIDE.match(nome)
    if corrispondenza:
        chiave = voce_di_ce(corrispondenza.group(1), list(base_inc.keys()))
        if chiave is None:
            return []
        corrente = _n(base_inc, chiave)
        valore = (corrente * D("1.10")).quantize(CENT) if corrente != 0 else D("10000.00")
        return [(f"{chiave} forzato a {_eur(valore)}", valore)]

    if nome == "sp_overrides":
        corrente = _n(base_bs, "sp10_ratei_risconti_attivi")
        valore = (corrente * D("1.10")).quantize(CENT) if corrente != 0 else D("10000.00")
        return [(f"sp10 forzato a {_eur(valore)}",
                 {"sp10_ratei_risconti_attivi": str(valore)})]

    if nome == "financing_loans":
        return [("un mutuo dettagliato da 100.000 € su 5 anni al 4%", [{
            "amount": "100000", "duration_years": "5", "interest_rate": "4",
            "grace_years": "0", "balloon_pct": "0",
        }])]

    if nome == "tax_temporary_differences":
        return [("una differenza temporanea deducibile da 50.000 €", [{
            "opening_amount": "0", "additions": "50000", "reversals": "0",
            "kind": "deductible", "maturity": "short",
        }])]

    if tipo.startswith("BOOLEAN"):
        return [("acceso", True)]

    if nome.endswith("_days"):
        return [("90 giorni", D("90"))]
    if nome.endswith("repayment_years"):
        return [("rimborso in 5 anni", D("5"))]
    if nome.endswith("_percentage"):
        return [("quota al 60%", D("60"))]
    if nome in ("depreciation_rate", "depreciation_rate_intangible"):
        return [("aliquota al 25%", D("25"))]
    if nome == "tax_rate":
        return [("aliquota al 40%", D("40"))]
    if nome == "financing_duration_years":
        return [("durata 5 anni", D("5"))]
    if nome == "financing_interest_rate":
        return [("tasso al 4%", D("4"))]
    if nome == "cash_sweep_min_cash":
        return [("cassa minima 50.000 €", D("50000"))]
    if nome.endswith("_growth_pct") or nome.endswith("_rate"):
        return [("+10%", D("10")), ("−10%", D("-10"))]
    if tipo.startswith("NUMERIC(15"):
        return [("100.000 €", D("100000"))]
    return [("+10", D("10"))]


def spiega_inerzia(nome, etichetta, valore, base_righe, base_bs_anno_base,
                   sorgente, motore, base) -> Tuple[str, str]:
    """(categoria, spiegazione) per un campo che non ha mosso nulla.

    Categorie: `atteso` (colonna che il motore non legge, documentato),
    `base-zero` (percentuale su una voce che nell'anno base vale zero),
    `accoppiato` (inerte da solo, vivo con il proprio interruttore acceso),
    `ignorato` (nessuna delle tre: il valore dell'utente sparisce e basta).
    Solo `ignorato` e' un rilievo.
    """
    if nome in NON_LETTI:
        return "atteso", NON_LETTI[nome]

    pilotata = VOCE_PILOTATA.get(nome)
    if pilotata is not None:
        if pilotata == "@banche":
            valore_base = base_bank_debt(
                lambda campo: getattr(sorgente.base_bs, campo, None) or ZERO)
            etichetta_voce = "il debito bancario dell'anno base"
        else:
            fonte = sorgente.base_bs if pilotata.startswith("sp") else sorgente.base_inc
            valore_base = getattr(fonte, pilotata, None) or ZERO
            etichetta_voce = pilotata
        if abs(D(str(valore_base))) <= CENT:
            return "base-zero", f"{etichetta_voce} vale zero nell'anno base"

    compagni = ACCOPPIAMENTI.get(nome)
    if compagni:
        righe = clona(base_righe, sorgente.scenario.id)
        for riga in righe:
            setattr(riga, nome, valore)
            for campo, valore_compagno in compagni.items():
                setattr(riga, campo, valore_compagno)
        prova = motore.compute_forecast(sorgente, righe, stop_on_error=False)
        descrizione = ", ".join(f"{k}={v}" for k, v in compagni.items())
        if prova.error:
            return "accoppiato", (f"da solo inerte; con {descrizione} il motore si ferma: "
                                  f"{prova.error.message}")
        # Confronto contro la stessa combinazione SENZA il campo sotto esame,
        # altrimenti si misurerebbe l'effetto del compagno, non del campo.
        righe_senza = clona(base_righe, sorgente.scenario.id)
        for riga in righe_senza:
            for campo, valore_compagno in compagni.items():
                setattr(riga, campo, valore_compagno)
        senza = motore.compute_forecast(sorgente, righe_senza, stop_on_error=False)
        if senza.error:
            return "accoppiato", (f"da solo inerte; con {descrizione} il confronto non e' "
                                  f"costruibile ({senza.error.message})")
        if scostamenti(senza, prova):
            return "accoppiato", f"da solo inerte, vivo con {descrizione}"
        return "ignorato", (f"inerte anche con {descrizione}: nessuna combinazione provata "
                            f"lo fa mordere")

    return "ignorato", "nessuna spiegazione nota: il valore inserito non produce effetti"


# --------------------------------------------------------------------------- #
# Confronto
# --------------------------------------------------------------------------- #

def scostamenti(base: ForecastComputation, prova: ForecastComputation
                ) -> List[Tuple[int, str, Decimal, Decimal]]:
    """(anno, voce, prima, dopo) per ogni valore mosso di piu' di un centesimo."""
    mosse = []
    for riga_base, riga_prova in zip(base.years, prova.years):
        for prospetto in ("income_statement", "balance_sheet"):
            prima, dopo = getattr(riga_base, prospetto), getattr(riga_prova, prospetto)
            for chiave in sorted(prima):
                a, b = _n(prima, chiave), _n(dopo, chiave)
                if abs(a - b) > CENT:
                    mosse.append((riga_base.year, chiave, a, b))
        for chiave in ("dso_applied", "dio_applied", "dpo_applied",
                       "ce05_fixed", "ce05_variable", "ce06_fixed", "ce06_variable"):
            a, b = riga_base.details.get(chiave), riga_prova.details.get(chiave)
            if a is None and b is None:
                continue
            if a is None or b is None or abs(D(str(a)) - D(str(b))) > CENT:
                mosse.append((riga_base.year, chiave,
                              ZERO if a is None else D(str(a)),
                              ZERO if b is None else D(str(b))))
    return mosse


# --------------------------------------------------------------------------- #
# Programma
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", type=int, required=True,
                        help="id dello scenario budget da cui prendere anno base e azienda")
    parser.add_argument("--anni", type=int, default=3, help="anni di piano (default 3)")
    parser.add_argument("--solo", default=None,
                        help="espressione regolare sui nomi dei campi, per restringere")
    parser.add_argument("--log", type=Path, default=None, help="file su cui scrivere il registro")
    parser.add_argument("--json", type=Path, default=None, help="dettaglio macchina-leggibile")
    parser.add_argument("--mosse", type=int, default=6,
                        help="quante voci mosse elencare per campo (default 6)")
    argomenti = parser.parse_args()

    db = SessionLocal()
    registro = Registro(argomenti.log)
    macchina: Dict[str, Any] = {"scenario": argomenti.scenario, "campi": {}}
    try:
        sorgente = load_forecast_source(db, argomenti.scenario)
        motore = ForecastEngine(db)
        anno_base = sorgente.scenario.base_year
        anni = [anno_base + i for i in range(1, argomenti.anni + 1)]

        registro("=" * 78)
        registro(f"BANCO DI SENSIBILITA' — scenario {argomenti.scenario} "
                 f"«{sorgente.scenario.name}», anno base {anno_base}, "
                 f"piano {anni[0]}–{anni[-1]}")
        registro("=" * 78)
        registro("Linea di base: ogni ipotesi al default di schema, aliquota 27,9, "
                 "nessun override,")
        registro("nessun piano di rimborso, nessun finanziamento. Il DB viene solo letto.")
        registro()

        base_righe = linea_di_base(sorgente.scenario, anni)
        base = motore.compute_forecast(sorgente, base_righe, stop_on_error=False)
        if base.error:
            registro(f"LA LINEA DI BASE NON SI CALCOLA: {base.error.message} "
                     f"(anno {base.error.year})")
            registro("Senza linea di base non c'e' sensibilita' da misurare.")
            registro.salva()
            return 2

        rilievi_base = invarianti(base, sorgente)
        registro(f"Linea di base calcolata: {len(base.years)} anni.")
        if rilievi_base:
            registro(f"ATTENZIONE — {len(rilievi_base)} invarianti gia' non reggono "
                     f"SULLA LINEA DI BASE:")
            for rilievo in rilievi_base:
                registro(f"    {rilievo}")
            registro("  Questi non dipendono dalle ipotesi: sono un difetto del motore o "
                     "dei dati dell'anno base.")
            registro("  Vengono esclusi dal conteggio delle perturbazioni, che misurano "
                     "solo cio' che PEGGIORA.")
        else:
            registro("Tutti gli invarianti reggono sulla linea di base.")
        registro()

        gia_rotti = {r.chiave for r in rilievi_base}
        base_inc = base.years[0].income_statement
        base_bs = base.years[0].balance_sheet

        filtro = re.compile(argomenti.solo) if argomenti.solo else None
        colonne = [c for c in BudgetAssumptions.__table__.columns
                   if c.name not in NON_IPOTESI
                   and (filtro is None or filtro.search(str(c.name)))]

        registro("-" * 78)
        registro(f"UNA IPOTESI ALLA VOLTA — {len(colonne)} campi")
        registro("-" * 78)

        inerti: List[str] = []
        fermati: List[Tuple[str, str]] = []
        peggiorati: List[Tuple[str, List[Rilievo]]] = []

        for colonna in colonne:
            nome = str(colonna.name)
            for etichetta, valore in perturbazioni(colonna, base_inc, base_bs):
                righe = clona(base_righe, sorgente.scenario.id)
                for riga in righe:
                    setattr(riga, nome, valore)

                prova = motore.compute_forecast(sorgente, righe, stop_on_error=False)
                voce: Dict[str, Any] = {"perturbazione": etichetta}

                if prova.error:
                    registro(f"\n{nome} — {etichetta}")
                    registro(f"  MOTORE FERMO nel {prova.error.year}: {prova.error.message}")
                    fermati.append((nome, prova.error.message))
                    voce["errore"] = prova.error.message
                    macchina["campi"].setdefault(nome, []).append(voce)
                    continue

                mosse = scostamenti(base, prova)
                nuovi = [r for r in invarianti(prova, sorgente) if r.chiave not in gia_rotti]
                voce["voci_mosse"] = len(mosse)
                voce["invarianti_nuovi"] = [str(r) for r in nuovi]

                if not mosse and not nuovi:
                    categoria, spiegazione = spiega_inerzia(
                        nome, etichetta, valore, base_righe, sorgente.base_bs,
                        sorgente, motore, base)
                    inerti.append((categoria, f"{nome} ({etichetta})", spiegazione))
                    voce["inerte"] = categoria
                    voce["spiegazione"] = spiegazione
                    if categoria == "ignorato":
                        registro(f"\n{nome} — {etichetta}")
                        registro(f"  IGNORATO: {spiegazione}")
                    macchina["campi"].setdefault(nome, []).append(voce)
                    continue

                registro(f"\n{nome} — {etichetta}")
                if nuovi:
                    rotti = [r for r in nuovi if r.gravita == "rotto"]
                    if rotti:
                        peggiorati.append((nome, rotti))
                    for rilievo in nuovi:
                        marchio = "INVARIANTE ROTTO" if rilievo.gravita == "rotto" else "sospetto"
                        registro(f"  {marchio}: {rilievo}")
                registro(f"  {len(mosse)} voci mosse"
                         + (f", le prime {argomenti.mosse}:" if len(mosse) > argomenti.mosse
                            else (":" if mosse else "")))
                for anno, chiave, prima, dopo in mosse[:argomenti.mosse]:
                    registro(f"      {anno}  {chiave:38} {prima:>18,.2f} → {dopo:>18,.2f}")
                macchina["campi"].setdefault(nome, []).append(voce)

        registro()
        registro("=" * 78)
        registro("RIEPILOGO")
        registro("=" * 78)

        if peggiorati:
            registro(f"\nINVARIANTI ROTTI DA UNA PERTURBAZIONE — {len(peggiorati)} campi:")
            for nome, rotti in peggiorati:
                registro(f"  {nome}:")
                for rilievo in rotti:
                    registro(f"      {rilievo}")
        else:
            registro("\nNessuna perturbazione ha rotto un invariante che reggeva.")

        if fermati:
            registro(f"\nIL MOTORE SI E' FERMATO su {len(fermati)} campi "
                     f"(puo' essere corretto: un fabbisogno scoperto DEVE fermarlo):")
            for nome, messaggio in fermati:
                registro(f"  {nome}: {messaggio}")

        ignorati = [i for i in inerti if i[0] == "ignorato"]
        if ignorati:
            registro(f"\nCAMPI IGNORATI — {len(ignorati)}: il valore dell'utente sparisce "
                     f"senza un errore.")
            registro("Questo e' il rilievo vero fra gli inerti: la casella si compila e "
                     "non succede nulla.")
            for _, nome, spiegazione in ignorati:
                registro(f"  {nome}")
                registro(f"      {spiegazione}")

        altri = [i for i in inerti if i[0] != "ignorato"]
        if altri:
            registro(f"\nINERTI CON UNA RAGIONE — {len(altri)}, elencati per non "
                     f"confonderli con i precedenti:")
            for categoria, nome, spiegazione in sorted(altri):
                registro(f"  [{categoria}] {nome}")
                registro(f"      {spiegazione}")

        if rilievi_base:
            registro(f"\nGIA' ROTTI SULLA LINEA DI BASE — {len(rilievi_base)}, "
                     f"riportati qui perche' non spariscano nel rumore:")
            for rilievo in rilievi_base:
                registro(f"  {rilievo}")

        registro.salva()
        if argomenti.json:
            argomenti.json.write_text(json.dumps(macchina, indent=2, ensure_ascii=False,
                                                 default=str), encoding="utf-8")
        return 1 if (peggiorati or ignorati) else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
