"""Tests for the internal-contradiction diagnosis on over-aggregated summaries.

Context (2026-07-16 audit): budget_137 (LUGS "versione definitiva") prints the same
macro figures as budget_133/135, but with Debiti inflated from 2.688.470,08 to
3.995.536,14 so that the two printed sides tie. The tie makes it escape the
"Totale Attivo != Totale Passivo" source check, and it used to fall through to the
generic "riepilogo aggregato per macro-voci" message -- which hides the real defect:
the document contradicts itself.

    Attivo components 4.168.990,10 vs printed TOTALE ATTIVO 4.079.635,72 -> 89.354,38
    CE  -66.900,08 + -138.687,60 = -205.587,68 vs printed -266.938,57 ->  61.350,89

This diagnosis reads only the amounts the document itself prints; it never changes an
accounting value.

Run: python -m pytest tests/test_summary_internal_contradiction.py -v
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# The real budget_137 text layer (Test/successSecondo/budget_137_Bilancio_LUGS_2025_DEFINITIVO.pdf)
LUGS_137 = """BILANCIO D'ESERCIZIO 2025
Schema IV Direttiva CEE (art. 2424 e 2425 c.c.) - versione definitiva
STATO PATRIMONIALE - ATTIVO
Voce
Importo
Immobilizzazioni
2.406.946,04
Attivo circolante
1.695.431,51
Ratei e risconti attivi
66.612,55
TOTALE ATTIVO
4.079.635,72
STATO PATRIMONIALE - PASSIVO (CORRETTO)
Voce
Importo
Patrimonio netto (inclusa perdita)
-58.481,84
Fondi rischi
14.962,00
TFR
123.583,51
Debiti
3.995.536,14
Ratei e risconti passivi
4.035,91
TOTALE PASSIVO
4.079.635,72
CONTO ECONOMICO
Voce
Importo
Valore produzione
2.025.192,55
Costi produzione
2.092.092,63
Differenza A-B
-66.900,08
Gestione finanziaria
-138.687,60
RISULTATO NETTO
-266.938,57
NOTA TECNICA
Il bilancio è stato riclassificato secondo IV direttiva CEE. Il risultato d'esercizio è correttamente
incluso nel patrimonio netto, garantendo la perfetta quadratura tra attivo e passivo.
"""

# The real budget_150 text layer (Test/successSecondo/budget_150_Bilancio_FINALE_CEE_SRL_2025.pdf):
# also an over-aggregated summary, but it prints no Attivo total and its CE reconciles
# through imposte. Nothing here contradicts anything -> must keep the "formato non
# supportato" diagnosis.
FINALE_CEE_150 = """BILANCIO DI ESERCIZIO - FORMA ABBREVIATA
(art. 2435-bis c.c.)
Esercizio chiuso al 31/12/2025
STATO PATRIMONIALE
ATTIVO
B) Immobilizzazioni: 554.824,39 €
C) Attivo circolante: 967.451,22 €
D) Ratei e risconti: 3.744,82 €
PASSIVO
A) Patrimonio netto (incluso utile): 663197.53 €
C) Trattamento di fine rapporto: 81.864,67 €
D) Debiti (inclusi tributari): 780958.23 €
CONTO ECONOMICO
A) Valore della produzione: 1.559.119,25 €
B) Costi della produzione: 1.472.044,65 €
Differenza A-B: 87.074,60 €
Risultato ante imposte: 52.586,15 €
Imposte sul reddito:
- IRES: 16843.36 €
- IRAP: 13468.30 €
UTILE NETTO DI ESERCIZIO: 22274.49 €
"""


def test_137_reports_both_printed_contradictions():
    from importers.pdf_importer import _summary_internal_contradiction

    message = _summary_internal_contradiction(LUGS_137)

    assert message is not None
    # The two scarti are read from the document, not recomputed from our own mapping.
    assert "61.350,89" in message
    assert "89.354,38" in message
    assert "internamente incoerente" in message
    assert "Correggere il documento contabile originale." in message


def test_150_has_no_printed_contradiction():
    """No Attivo total to contradict, and the CE closes through imposte."""
    from importers.pdf_importer import _summary_internal_contradiction

    assert _summary_internal_contradiction(FINALE_CEE_150) is None


def test_consistent_summary_is_not_flagged():
    """Same shape as 137 but the printed components do add up: stay silent."""
    from importers.pdf_importer import _summary_internal_contradiction

    consistent = LUGS_137.replace("4.079.635,72", "4.168.990,10").replace(
        "RISULTATO NETTO\n-266.938,57", "RISULTATO NETTO\n-205.587,68"
    )
    assert _summary_internal_contradiction(consistent) is None


def test_empty_and_garbage_text_are_safe():
    from importers.pdf_importer import _summary_internal_contradiction

    assert _summary_internal_contradiction("") is None
    assert _summary_internal_contradiction("nessun bilancio qui") is None


def test_diagnosis_does_not_mutate_or_infer_values():
    """The helper is a pure reader: it reports gaps, never a corrected figure."""
    from importers.pdf_importer import _summary_internal_contradiction

    message = _summary_internal_contradiction(LUGS_137)
    # It must not publish a "fixed" total that the document does not print.
    assert "4.168.990,10" not in message
    assert "205.587,68" not in message
