"""Verifica "Mastri" con mastri a 3 cifre e conti a 5 (budget_1401, Metaldecor, weekend 10/2026).

Stesso gestionale e stesso tracciato del "Mastri" a 4/8 cifre, con tre differenze: il codice del mastro
e del conto e' piu' corto (il rilevatore e il lettore chiedevano 4 e 8 cifre: il documento non veniva
riconosciuto e l'import cadeva sul modello, 1,1 milioni di scarto), i mastri senza conti hanno un codice
a lettere ("CLIENTI IT": 1.972.445,67 di crediti verso clienti andavano persi), e l'utile d'esercizio e'
GIA' un conto della sezione PASSIVITA' (attivita' = passivita', la DIFFERENZA del riepilogo e' il solo
risultato del conto economico). Inoltre la scadenza la dichiara il mastro ("DEBITI V/FINANZ.ESIG.OLTRE
12M"), non i suoi conti: 905.335,14 di mutui finivano a breve. I documenti stanno nel corpus locale
`Test/`, che non e' nel repository.
"""
import os
from decimal import Decimal

import pytest

_RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PDF_1401 = os.path.join(_RADICE, "Test", "weekend-10-2026", "budget_1401_2025.12.31_BilancioVerifica.pdf")
_PDF_COLOMBO = os.path.join(_RADICE, "Test", "COLOMBO.pdf")


def _esito(pdf):
    from importers.import_snello.deterministico import tentativo
    esito = tentativo(pdf)
    assert esito["adottato"] is True and esito["parser"] == "situazione_contabile_parser"
    assert esito["misura"]["scarto_sp"] == 0 and esito["misura"]["scarto_ce"] == 0
    assert esito["misura"]["scarto_stampati"] == 0
    return esito


@pytest.mark.skipif(not os.path.exists(_PDF_1401), reason="budget_1401 non presente in Test/")
def test_1401_si_legge_a_regole_e_quadra():
    esito = _esito(_PDF_1401)
    bs, ce = esito["bs"], esito["ce"]
    assert bs["sp13_utile_perdita"] == Decimal("4437.33")


@pytest.mark.skipif(not os.path.exists(_PDF_1401), reason="budget_1401 non presente in Test/")
def test_1401_i_clienti_senza_conti_e_i_debiti_oltre_non_si_perdono():
    bs = _esito(_PDF_1401)["bs"]
    assert bs["sp06a_crediti_clienti_breve"] == Decimal("1974344.39")      # CLIENTI IT + CLIENTI EST
    assert bs["sp17a_debiti_banche_lungo"] == Decimal("905335.14")         # mastro OLTRE 12M
    assert bs["sp17_debiti_lungo"] == Decimal("905335.14")
    # anticipi IFIS (1.190.817,02) sotto "DEBITI V/FINANZ.": debito finanziario, non "altri debiti"
    assert bs["sp16a_debiti_banche_breve"] == Decimal("1586872.82")


@pytest.mark.skipif(not os.path.exists(_PDF_COLOMBO), reason="COLOMBO.pdf non presente in Test/")
def test_colombo_il_mastro_oltre_12_mesi_va_a_sp17():
    bs = _esito(_PDF_COLOMBO)["bs"]
    assert bs["sp17a_debiti_banche_lungo"] == Decimal("916470.81")
