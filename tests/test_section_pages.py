"""Tests per l'estrazione di section_pages dal ciclo pagine best-effort.

Spec: docs/superpowers/specs/2026-08-14-riscatto-vision-route-c-design.md §4
Run:  python -m pytest tests/test_section_pages.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.situazione_contabile_parser import (  # noqa: E402
    classify_page_section,
    section_pages,
)


def test_titolo_patrimoniale_da_solo():
    text = "STATO PATRIMONIALE\n01 CASSA 100,00\nTOTALE ATTIVITA' 100,00\n"
    assert classify_page_section(text) == (True, False)


def test_titolo_economico_da_solo():
    text = "CONTO ECONOMICO\n60 ACQUISTI 100,00\nTOTALE COSTI 100,00\n"
    assert classify_page_section(text) == (False, True)


def test_titolo_misto_vince_la_prima_riga_di_titolo():
    # Una sola pagina che nomina entrambe le sezioni: decide la riga di titolo che
    # viene PRIMA nel testo.
    text = "STATO PATRIMONIALE E CONTO ECONOMICO\nCOSTI 1,00\nRICAVI 2,00\n"
    is_sp, is_ce = classify_page_section(text)
    assert is_sp and is_ce


def test_appendice_di_rideterminazione_va_saltata():
    text = ("RIDETERMINAZIONE RISULTATO D'ESERCIZIO\n"
            "VARIAZIONI IN AUMENTO 10,00\nVARIAZIONI IN DIMINUZIONE 5,00\n")
    assert classify_page_section(text) is None


def test_senza_titolo_riconosce_attivita_e_passivita():
    text = "ATTIVITA'\n01 CASSA 100,00\nPASSIVITA'\n20 FORNITORI 100,00\n"
    assert classify_page_section(text) == (True, False)


def test_pagina_senza_marcatori_non_e_ne_sp_ne_ce():
    # Non è None: la pagina esiste ancora, semplicemente non appartiene a nessuna
    # sezione. Questa distinzione è ciò che il ciclo chiamante usa.
    assert classify_page_section("Pagina 3 di 7\n") == (False, False)


REAL_PDF = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "debug",
    "budget_624_2024 Commercio al dettaglio di ferramenta, vernici, vetro piano "
    "e materiale elettrico e termoidraulico .pdf",
)


@pytest.mark.skipif(not os.path.exists(REAL_PDF), reason="PDF di debug non presente")
def test_section_pages_su_pdf_reale():
    pages = section_pages(REAL_PDF)
    assert pages["sp"], "nessuna pagina di stato patrimoniale rilevata"
    assert pages["ce"], "nessuna pagina di conto economico rilevata"
    assert pages["sp"] == sorted(pages["sp"])
    assert pages["ce"] == sorted(pages["ce"])
    # Il CE di 624 sta in coda al documento: l'ultima pagina CE viene dopo la prima SP.
    assert max(pages["ce"]) > min(pages["sp"])
