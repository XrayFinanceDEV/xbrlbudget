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

from calculations.projection_common import base_bank_debt as _debito_bancario_base
from calculations.projection_common import pregresso_opening_masses as _masse_pregresso

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


def _con_tributari_pregressi(bs: Dict[str, Decimal], breve: Decimal, lungo: Decimal) -> Dict[str, Decimal]:
    """Il fixture con debiti TRIBUTARI pregressi non tondi, a breve e oltre.

    Perche' esiste (Task 4 del followup). Nessun fixture di sopra ha mai un
    euro di `sp16e`/`sp17e` in apertura: la massa di `debiti_tributari`
    (`pregresso_opening_masses`) e' sempre zero, quindi un banco senza questo
    fixture non potrebbe MAI vedere una divergenza sul solo pezzo che un piano
    del pregresso aggiunge alla posizione tributaria — il RATEIZZATO
    (`validate_pregresso`, ramo `debiti_tributari`: `saldo + rateizzato =
    opening`, e il piano delle rate scadenzia il solo rateizzato). Stessa
    tecnica di `_con_banca_pregressa`: la cassa riassorbe la differenza, cosi'
    il fixture resta in pareggio e con i dettagli dei debiti esatti.
    """
    out = dict(bs)
    out["sp16e_debiti_tributari_breve"] = breve
    out["sp16_debiti_breve"] = D(str(bs.get("sp16_debiti_breve", 0))) + breve
    out["sp17e_debiti_tributari_lungo"] = lungo
    out["sp17_debiti_lungo"] = D(str(bs.get("sp17_debiti_lungo", 0))) + lungo
    out["sp09_disponibilita_liquide"] = (
        D(str(bs.get("sp09_disponibilita_liquide", 0))) + breve + lungo
    )
    return out


TRIBUTARI_BS = _con_tributari_pregressi(BASE_BS, D("9876.54"), D("3210.98"))


def _con_altri_debiti_pregressi(bs: Dict[str, Decimal], breve: Decimal, lungo: Decimal) -> Dict[str, Decimal]:
    """Il fixture con `altri_debiti` pregressi non tondi, a breve e oltre.

    Perche' esiste (giro 2, rilievo I-3 della revisione di `6e5c0f7`). Il ramo
    nuovo del normalizzatore — nessun campo operativo del gruppo `sp16` e'
    libero, quindi l'aggregato segue la somma delle righe e la cassa si muove
    del centesimo — lo raggiunge solo chi FORZA il secchio `sp16g`, cioe' un
    piano `altri_debiti` (o un'indicizzazione di `sp16g`). Ma la massa di
    `altri_debiti` e' `sp16g + sp17g`, e su OGNI fixture di sopra e' zero:
    `validate_pregresso` imporrebbe un piano a zero rate, e un piano a zero
    rate non produce alcun residuo da posare. Il banco era quindi cieco sul
    ramo per costruzione, non per sfortuna (e' il rilievo I-3 punto 2). Stessa
    tecnica dei due fixture precedenti: la cassa riassorbe la differenza, cosi'
    il pareggio e l'identita' aggregato/details restano esatti.
    """
    out = dict(bs)
    out["sp16g_altri_debiti_breve"] = breve
    out["sp16_debiti_breve"] = D(str(bs.get("sp16_debiti_breve", 0))) + breve
    out["sp17g_altri_debiti_lungo"] = lungo
    out["sp17_debiti_lungo"] = D(str(bs.get("sp17_debiti_lungo", 0))) + lungo
    out["sp09_disponibilita_liquide"] = (
        D(str(bs.get("sp09_disponibilita_liquide", 0))) + breve + lungo
    )
    return out


ALTRI_BS = _con_altri_debiti_pregressi(BASE_BS, D("23456.79"), D("12345.67"))

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
    ("tributari", TRIBUTARI_BS, BASE_CE, D("1")),
    ("altri", ALTRI_BS, BASE_CE, D("1")),
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


def profilo_finanziamento_misto(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Un contratto MISTO: `amount` (nuovo) e `opening_residual` (pregresso)
    valorizzati insieme sulla STESSA riga di `financing_loans` — come lo
    produce `FinancingLoansGrid.tsx` quando l'utente riempie entrambe le
    caselle sulla stessa riga (Task 16, giro di correzione 1, Ruling 45).

    Prima di questa correzione il motore trattava il contratto intero come
    pregresso e la sua quota nuova consumava il breve pregresso — esattamente
    il Ruling 40, ma per un contratto che l'utente ha scritto come uno solo.
    Nessun profilo di sopra mette `amount` e `opening_residual` sulla stessa
    riga: `profilo_finanziamento_e_rimborso` usa la legacy `financing_amount`
    (un prestito sempre e solo nuovo) accanto a un `existing_debt_repayment_years`
    che scadenzia l'ESPOSIZIONE AGGREGATA, non un contratto per riga.

    Il primo contratto (pregresso puro, durata lunga) e i due `opening_residual`
    sono SEGNAPOSTO a "0": `costruisci_griglia` li riempie dopo, col debito
    bancario REALE del fixture che consuma questo profilo — un residuo diverso
    dal debito base fa fallire la validazione di `assemble_financing` — e con
    una ripartizione pensata per cadere nella stessa zona di confine della
    sonda P8 della revisione (vedi il commento sul posto).
    """
    if anno_idx == 0:
        return {
            "financing_loans": [
                {
                    "name": "Debito bancario pregresso",
                    "amount": 0, "opening_residual": "0",
                    "duration_years": "6", "interest_rate": _pct(rng, 2, 6),
                },
                {
                    "name": "Mutuo misto",
                    "amount": _eur(rng, 15000, 25000), "opening_residual": "0",
                    "duration_years": "2", "interest_rate": _pct(rng, 2, 6),
                },
            ],
        }
    return {}


def profilo_pregresso(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Un piano di scadenziamento del pregresso (`BudgetAssumptions.pregresso`,
    kernel `runoff_schedule`), su crediti commerciali, debiti fornitori e la
    quota RATEIZZATA dei debiti tributari (Task 4 del followup: nessun
    profilo di sopra passa mai `pregresso`, quindi il banco non aveva mai
    visto una divergenza sul kernel del runoff, ne' sull'interazione fra un
    piano e la posizione tributaria a saldo+acconto).

    Vale solo sul primo anno di piano — `pregresso` vive sulla riga del primo
    anno (spec §3.1) — gli anni dopo non aggiungono ipotesi. Le FRAZIONI sono
    generate qui, deterministiche dal seed; `costruisci_griglia` le converte
    nell'importo reale sulla massa di apertura del fixture che consuma questo
    profilo (`pregresso_opening_masses`, la stessa funzione del motore): il
    profilo non conosce il fixture, e l'`opening` del piano deve coincidere al
    centesimo con quella del bilancio base o `validate_pregresso` lo rifiuta.
    Un saldo la cui massa e' zero sul fixture (i tributari, ovunque tranne
    `tributari`/`banca` — vedi `_con_tributari_pregressi`) resta fuori dal
    piano: scadenziare un euro che non c'e' alzerebbe un errore, non un
    piano a zero.
    """
    if anno_idx != 0:
        return {}
    return {
        "_pregresso_chiavi": ("crediti_commerciali", "debiti_fornitori", "debiti_tributari"),
        "_pregresso_frazioni": {
            "crediti_commerciali": [round(rng.uniform(0.15, 0.35), 4), round(rng.uniform(0.15, 0.35), 4)],
            "debiti_fornitori": [round(rng.uniform(0.15, 0.35), 4), round(rng.uniform(0.15, 0.35), 4)],
            "debiti_tributari_rateizzato_pct": round(rng.uniform(0.3, 0.6), 4),
            "debiti_tributari_amounts": [round(rng.uniform(0.2, 0.4), 4), round(rng.uniform(0.2, 0.4), 4)],
        },
        "existing_debt_repayment_years": _anni_frazionari(rng, 3, 6),
    }


def profilo_pregresso_tributari_mezzo_cent(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Rateizzato tributario con rate a MEZZO centesimo e nessun override.

    Perche' esiste (giro 2, rilievo I-a della revisione di `f330730`).
    `_realign_sp_declarations` confrontava il persistito con una somma NON
    quantizzata: con un `residual_short` sotto il centesimo la condizione
    diventava vera ANCHE SENZA NESSUN OVERRIDE, e il motore riscriveva
    `details['imposte'].generated_debt` lontano da qualunque confronto — la
    revisione lo misura su 32 scenari su 96 della SUA batteria (rate a mezzo
    centesimo, `dump_batteria.py`, fuori griglia). Finche' `PROFILI` non ha
    una rata sotto il centesimo il banco non ha nessuna possibilita' di vederlo.

    CHE VEDA POI — misura, e non e' quella che ci si aspetterebbe. Su questa
    griglia (5 anni, `b08a9a6` contro il giro 2) il profilo da solo non muove
    NESSUNA CELLA: la cella forzata e' la somma delle due parti, quindi la
    coda di mezzo centesimo resta confinata nei `details`, che il confronto del
    banco non guarda (confronta prospetti, non dichiarazioni). La firma con cui
    la revisione l'aveva vista (`sp06g` −0,01, cassa +0,01) e' di un altro
    contesto: li' la cella NON era forzata e il riallineamento riscriveva il
    `generated` di una riga mai toccata. Per quella prova serve un test che
    guardi i `details`, e infatti c'e': `test_a_senza_override_il_riallineamento_non_cambia_niente`
    confronta lo stesso scenario col riallineatore acceso e spento (ed e' rosso
    su `b08a9a6`). Questo profilo resta: se un domani la coda frazionaria
    trovasse la strada per una cella, qui si vedrebbe.

    Misura di QUESTO profilo (driver del banco, griglia a 5 anni, `0207c93`
    contro `b08a9a6`, fixture `tributari` — l'unico con massa tributaria):
    `details['imposte'].generated_debt` 2027 passa da `0` a `0.005` su una
    cella NON forzata (rata 1626.405, `residual_short` 1197.855: e' li' il mezzo
    centesimo), e il 2028 porta `sp06g` da `0.00` a `-0.01` con la cassa di
    `+0,01` — la firma che la revisione descrive. Nelle stesse righe compare
    anche `sp16c` -> `sp16g`: quello e' I3, che su `0207c93` non era ancora
    arrivato. Nota: la griglia estrae da UN rng per fixture, quindi le cifre
    dipendono da `--anni`; qui sono quelle di `--anni 5`.

    Solo tributari, e nessun `existing_debt_repayment_years`: cio' che si
    misura e' l'IDENTITA' senza override, non un'altra interazione. Le
    percentuali di `profilo_crescita` ci stanno pero' perche' e' LI' che le
    righe dello stato patrimoniale prendono code frazionarie: senza, la sola
    coda del piano finisce assorbita dalla quantizzazione della riga.
    """
    valori = profilo_crescita(rng, anno_idx)
    if anno_idx != 0:
        return valori
    valori.update({
        "_pregresso_chiavi": ("debiti_tributari",),
        "_pregresso_mezzo_cent": True,
        "_pregresso_frazioni": {
            "debiti_tributari_rateizzato_pct": round(rng.uniform(0.35, 0.55), 4),
            "debiti_tributari_amounts": [round(rng.uniform(0.15, 0.3), 4),
                                         round(rng.uniform(0.15, 0.3), 4)],
        },
    })
    return valori


def profilo_mezzo_cent_con_override(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Rate a mezzo centesimo PLUS una cella tributaria breve forzate, insieme.

    Perche' esiste (giro 2, rilievo I-a della revisione di `f330730`). Il
    profilo sopra, da solo, NON puo' far vedere la firma: il ramo incriminato
    del riallineatore (`if res != declared_res`) si apre solo quando la riga e'
    FORZATA, e `profilo_pregresso_tributari_mezzo_cent` di forzature non ne ha
    nessuna — «Solo tributari, e nessun existing_debt_repayment_years: cio' che
    si misura e' l'IDENTITA' senza override», dice il suo docstring. Misurato:
    la griglia con quel solo profilo da' 0 divergenze fra `b08a9a6` e questa
    versione, su 5 anni e tutte e otto le fixture.

    Qui la combinazione che la griglia non aveva c'e': la rata sotto il
    centesimo E l'override sulla cella contabile della stessa riga, e il numero
    e' preso di peso da `profilo_override_ce_sp` (40000.33). L'affermazione che
    questo profilo porta in dote e' pero' NEGATIVA, e va detta chiara perche' il
    banco non la vedra' mai: la correzione I-a non muove nessuna CELLA (la
    somma delle due parti e' la cella forzata, prima e dopo), sposta solo il
    `generated_debt` dichiarato nei `details`, che il confronto del banco non
    guarda. La prova che il difetto e' chiuso sta dunque nel test di proprieta'
    `test_a_senza_override_il_riallineamento_non_cambia_niente`, non qui; questo
    profilo esiste per non perdere la combinazione.
    """
    valori = profilo_pregresso_tributari_mezzo_cent(rng, anno_idx)
    if anno_idx != 0:
        return valori
    valori["sp_overrides"] = {"sp16e_debiti_tributari_breve": _eur(rng, 40000, 40001)}
    return valori


def profilo_pregresso_altri(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Piano `altri_debiti` a mezzo centesimo: il secchio `sp16g`/`sp17g` e'
    forzato, quindi NEL GRUPPO DEBITI non resta nessun operativo libero.

    Perche' esiste (giro 2, rilievo I-3 punto 2 della revisione di `6e5c0f7`).
    Il ramo in cui l'aggregato `sp16`/`sp17` segue la somma delle righe (e la
    cassa si muove dello stesso centesimo) non e' raggiunto da NESSUN profilo:
    `PROFILI` non aveva alcun piano `altri_debiti`, e `rimborso_indicizzazione`
    che `sp16g` lo indicizza pure, ma su tutta la griglia non posa NULLA (misura
    sotto). Il piano va pero' su un fixture la cui massa di `altri_debiti` e'
    diversa da zero — `altri`, vedi `_con_altri_debiti_pregressi` — perche'
    `validate_pregresso` impone che l'`opening` dichiarato sia quello del
    bilancio base: sugli altri fixture questo profilo resta un `pregresso` vuoto.

    Misura della griglia a 5 anni su `b08a9a6`, posature che nominano un
    aggregato: `pregresso_altri` 1 anno su 37, e nessuno dei 13 profili
    precedenti ne posa una su 494 anni (`rimborso_indicizzazione` compresa: 0
    su 40, che sono le `I16`/`I17` della revisione — «il residuo e' zero su
    tutta la griglia»).
    """
    valori = profilo_crescita(rng, anno_idx)
    if anno_idx != 0:
        return valori
    valori.update({
        "_pregresso_chiavi": ("altri_debiti",),
        "_pregresso_mezzo_cent": True,
        "_pregresso_frazioni": {
            "altri_debiti": [round(rng.uniform(0.15, 0.3), 4), round(rng.uniform(0.15, 0.3), 4)],
        },
    })
    return valori


def profilo_override_aggregato(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Un `sp_overrides` SOLO sull'aggregato `sp16_debiti_breve`, senza piano.

    Perche' esiste (giro 2, rilievi I-1 e I-3 della revisione di `6e5c0f7`).
    E' l'unica ipotesi con cui il normalizzatore incontra UN FORZATO
    SULL'AGGREGATO: con un dettaglio forzato, `_apply_sp_overrides`
    ricostruisce comunque l'aggregato dalla somma e il residuo torna un
    arrotondamento. L'importo qui e' il segnaposto "0": lo sostituisce
    `costruisci_griglia` dopo il ciclo degli anni, sul `sp16_debiti_breve` REALE
    del fixture + 15.000,37 (stessa tecnica di `profilo_finanziamento_misto`):
    un totale forzato lontano da quello naturale farebbe scattare il cancello
    del fabbisogno su meta' degli scenari, e il banco misurerebbe l'errore al
    posto del centesimo.

    Senza piano per scelta: con un piano `altri_debiti` addosso, da questo giro
    in poi questo override si RIFIUTA (I-1), e la griglia smetterebbe di
    mostrare dove la massa va a posarsi. Il rifiuto lo provano i test in
    `tests/test_forecast_residuo_quadratura_sp16.py`.
    """
    return {
        "sp_overrides": {"sp16_debiti_breve": "0"},
    }


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
    "finanziamento_misto": profilo_finanziamento_misto,
    "pregresso": profilo_pregresso,
    "pregresso_tributari_mezzo_cent": profilo_pregresso_tributari_mezzo_cent,
    "pregresso_altri": profilo_pregresso_altri,
    "override_aggregato": profilo_override_aggregato,
    # In CODA, dopo `override_aggregato`: l'ordine di `PROFILI` e' anche quello
    # con cui lo STESSO rng di fixture estrae, e infilarsi in mezzo ricadrebbe su
    # tutti i profili successivi (numero registrato del commit 1 e cifra della
    # firma I-a incluse). Un profilo nuovo si aggiunge in fondo, sempre.
    "pregresso_mezzo_cent_con_override": profilo_mezzo_cent_con_override,
}


def _piano_pregresso(masse: Dict[str, Decimal], frazioni: Dict[str, Any], num_anni: int,
                     chiavi, mezzo_cent: bool = False) -> Dict[str, Any]:
    """Le FRAZIONI del profilo diventano gli IMPORTI del fixture che le consuma.

    `validate_pregresso` impone che l'`opening` di ogni saldo coincida al
    centesimo con la massa del bilancio base, e il profilo non conosce il
    fixture: il piano si costruisce qui, con la stessa funzione del motore
    (`pregresso_opening_masses`). Un saldo la cui massa e' zero su questo
    fixture resta fuori dal piano — scadenziare un euro che non c'e' alza un
    errore, non un piano a zero.

    Con `mezzo_cent` ogni rata guadagna MEZZO centesimo: e' la coda che la
    quantizzazione della riga deve spezzare, e senza di essa un `residual_short`
    frazionario sotto il centesimo non lo produce NULLA (rilievo I-a).
    Il mezzo centesimo si aggiunge solo finche' rientra nel residuo, perche'
    `validate_runoff` rifiuta un piano che eccede la massa.
    """
    mezzo = D("0.005") if mezzo_cent else D("0")

    def _rate(opening: Decimal, quote) -> List[str]:
        importi: List[str] = []
        residuo = opening
        for q in quote[:num_anni]:
            imp = min(residuo, (opening * D(str(q))).quantize(CENT))
            if imp + mezzo <= residuo:
                imp += mezzo
            importi.append(str(imp))
            residuo -= imp
        return importi

    piano: Dict[str, Any] = {}
    for chiave in chiavi:
        if chiave == "debiti_tributari":
            opening = masse[chiave]
            if opening <= 0:
                continue
            rateizzato = (
                opening * D(str(frazioni["debiti_tributari_rateizzato_pct"]))
            ).quantize(CENT)
            piano[chiave] = {
                "opening": str(opening), "saldo": str(opening - rateizzato),
                "rateizzato": str(rateizzato),
                "amounts": _rate(rateizzato, frazioni["debiti_tributari_amounts"]),
            }
        else:
            opening = masse[chiave]
            if opening <= 0:
                continue
            piano[chiave] = {"opening": str(opening), "amounts": _rate(opening, frazioni[chiave])}
    return piano


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
                valori = profilo(rng, i)
                if profilo_nome == "finanziamento_misto" and i == 0:
                    # `assemble_financing` alza un ValueError se la somma dei
                    # `opening_residual` dichiarati non coincide col debito
                    # bancario dell'anno base (Decimal, entro 0,01): il profilo
                    # non conosce il fixture che lo consuma, quindi i due
                    # residui si allineano QUI, dopo la generazione, sul debito
                    # bancario REALE — calcolato con la stessa funzione del
                    # motore (`base_bank_debt`), non a occhio.
                    #
                    # La ripartizione non e' meta'/meta': e' la stessa zona di
                    # confine della sonda P8 della revisione (rilievo 1). Con
                    # `amount` fra 15.000 e 25.000 e il contratto pregresso
                    # puro che tiene il 60% del breve (durata lunga, rata
                    # annua bassa), la rata pregressa del misto DA SOLA resta
                    # sempre sotto il breve, e quella COMBINATA (+ l'importo
                    # nuovo) lo supera sempre — la prova e' nel commento sopra
                    # `profilo_finanziamento_misto`. Cosi' la cella si muove
                    # per QUALUNQUE estrazione casuale dell'importo, non solo
                    # per un seme fortunato.
                    debito_base = _debito_bancario_base(lambda f: D(bs.get(f, "0")))
                    breve = D(bs.get("sp16a_debiti_banche_breve", "0"))
                    if debito_base <= 0:
                        residuo_puro, residuo_misto = D("0"), D("0")
                    elif breve <= 0:
                        residuo_puro, residuo_misto = D("0"), debito_base
                    else:
                        residuo_misto = min(breve * D("0.6"), debito_base).quantize(CENT)
                        residuo_puro = (debito_base - residuo_misto).quantize(CENT)
                    loans = valori["financing_loans"]
                    loans[0]["opening_residual"] = str(residuo_puro)
                    loans[1]["opening_residual"] = str(residuo_misto)
                if profilo_nome.startswith("pregresso") and i == 0:
                    # L'`opening` di un saldo scadenziato deve coincidere al
                    # centesimo con la sua massa di apertura sul bilancio base
                    # (`validate_pregresso`), e il profilo non conosce il
                    # fixture che lo consuma: il piano vero si costruisce QUI,
                    # con la stessa funzione del motore
                    # (`pregresso_opening_masses`), non a occhio. Un saldo la
                    # cui massa e' zero su questo fixture (i tributari, che ce
                    # l'hanno solo su `tributari` — vedi
                    # `_con_tributari_pregressi` — e gli `altri_debiti`, solo su
                    # `altri`) resta fuori dal piano.
                    masse = _masse_pregresso(lambda f: D(bs.get(f, "0")))
                    valori["pregresso"] = _piano_pregresso(
                        masse, valori.pop("_pregresso_frazioni"), num_anni,
                        valori.pop("_pregresso_chiavi"),
                        bool(valori.pop("_pregresso_mezzo_cent", False)),
                    )
                anni_def.append({"anno": 2026 + 1 + i, "valori": valori})
            if profilo_nome == "override_aggregato":
                # Il segnaposto "0" del profilo diventa il totale FORZATO del
                # fixture: un `sp16` imposto lontano dal suo valore naturale
                # farebbe scattare il cancello del fabbisogno su meta' degli
                # scenari, e il banco misurerebbe l'errore al posto del
                # centesimo (stessa tecnica dei residui misti sopra — il
                # profilo non conosce il fixture che lo consuma).
                for a in anni_def:
                    a["valori"]["sp_overrides"]["sp16_debiti_breve"] = str(
                        D(bs["sp16_debiti_breve"]) + D("15000.37"))
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
    # Il numero PRIMA della stringa: il driver serializza ogni `Decimal` come
    # stringa (`_serializza`), quindi uno zero arriva qui come "0.00". Con il
    # controllo sulla lunghezza per primo, una chiave nuova dichiarata a zero
    # contava come divergenza, contro cio' che questa funzione dichiara — e'
    # successo con `details.prestiti_nuovi_quota_breve` del Task 17, segnalata a
    # 0,00 su ogni scenario senza prestito.
    if _e_numero(v):
        return D(str(v)) == 0
    if isinstance(v, (list, dict, str)):
        return len(v) == 0
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
    if a is None or b is None:
        # `None` e' un valore DICHIARATO (vedi il commento su `_ASSENTE` sopra),
        # mai equivalente a zero: l'equivalenza «vuoto = zero» vale SOLO fra
        # chiave ASSENTE e zero (ramo sopra), non fra `None` e zero. Prima di
        # questa restrizione (F4, giro di correzione 1 del Task 17) un campo
        # dichiarato `None` su una versione (es. `ce05_fixed` quando "la
        # scomposizione non esiste") e diverso da zero sull'altra si nascondeva
        # dietro l'equivalenza con lo zero, invece di comparire come divergenza.
        return a is None and b is None
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
