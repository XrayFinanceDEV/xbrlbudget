from decimal import Decimal

import fitz

from importers.lettore.colonne import colonne_documento
from importers.lettore.geometria import parole_pagina, righe_fisiche
from importers.lettore.lati import assegna_lati, confine_dei_lati
from tests.lettore.pdf_sintetico import scrivi_pdf

_SINISTRA = [Decimal(v) for v in ("1234.56", "500.00", "98765.43", "12.30", "4500.00", "777.77", "80.00", "3.10")]
_DESTRA = [Decimal(v) for v in ("1000.00", "620.50", "90000.00", "15.00", "4100.10", "700.00", "55.55", "9.90")]


def _fmt(v: Decimal) -> str:
    intero, _, dec = f"{v:.2f}".partition(".")
    gruppi = []
    while len(intero) > 3:
        gruppi.insert(0, intero[-3:])
        intero = intero[:-3]
    gruppi.insert(0, intero)
    return f"{'.'.join(gruppi)},{dec}"


def _leggi(tmp_path, voci):
    p = tmp_path / "l.pdf"
    scrivi_pdf(p, [voci])
    with fitz.open(str(p)) as doc:
        righe = []
        for n, pagina in enumerate(doc, start=1):
            righe += righe_fisiche(parole_pagina(pagina), n)
    return righe, colonne_documento(righe)


def _contrapposte(codici: bool, testata=None, descritte_destra=8, nomi=("Cliente", "Fornitore")):
    voci = list(testata or [])
    for k, (a, b) in enumerate(zip(_SINISTRA, _DESTRA)):
        y = 140 + k * 14
        if codici:
            voci += [(40, y, f"0{k + 1}.01"), (80, y, f"{nomi[0]} {k + 1}")]
            if k < descritte_destra:
                voci += [(310, y, f"2{k + 1}.01"), (350, y, f"{nomi[1]} {k + 1}")]
        else:
            voci.append((40, y, f"{nomi[0]} {k + 1}"))
            if k < descritte_destra:
                voci.append((310, y, f"{nomi[1]} {k + 1}"))
        voci += [(280, y, _fmt(a)), (560, y, _fmt(b))]
    return voci


def test_contrapposte_con_codici(tmp_path):
    righe, colonne = _leggi(tmp_path, _contrapposte(codici=True))
    assert len(colonne) == 2
    confine = confine_dei_lati(righe, colonne)
    assert confine is not None and 280 < confine < 310
    assert [c.lato for c in assegna_lati(colonne, confine)] == ["L", "R"]


def test_contrapposte_senza_codici(tmp_path):
    righe, colonne = _leggi(tmp_path, _contrapposte(codici=False))
    confine = confine_dei_lati(righe, colonne)
    assert confine is not None and 280 < confine < 310
    assert [c.lato for c in assegna_lati(colonne, confine)] == ["L", "R"]


def test_schema_a_due_esercizi_non_e_contrapposto(tmp_path):
    voci = []
    for k, (a, b) in enumerate(zip(_SINISTRA, _DESTRA)):
        y = 140 + k * 14
        voci += [(50, y, f"VOCE {k + 1}"), (430, y, _fmt(a)), (540, y, _fmt(b))]
    righe, colonne = _leggi(tmp_path, voci)
    assert len(colonne) == 2
    assert confine_dei_lati(righe, colonne) is None
    assert [c.lato for c in assegna_lati(colonne, None)] == ["U", "U"]


def test_intestazione_minuscola_attivita_passivita(tmp_path):
    testata = [(40, 120, "Attività"), (310, 120, "Passività")]
    righe, colonne = _leggi(tmp_path, _contrapposte(codici=False, testata=testata))
    confine = confine_dei_lati(righe, colonne)
    assert confine is not None and 280 < confine < 310


def test_intestazione_conferma_con_poche_righe(tmp_path):
    # Solo due righe di destra hanno la descrizione (le altre sono importi a capo): da sole non bastano,
    # con «costi … ricavi» sulla stessa riga sopra il varco si'.
    righe, colonne = _leggi(tmp_path, _contrapposte(codici=False, descritte_destra=2))
    assert confine_dei_lati(righe, colonne) is None
    testata = [(40, 120, "costi"), (310, 120, "RICAVI")]
    righe, colonne = _leggi(tmp_path, _contrapposte(codici=False, testata=testata, descritte_destra=2))
    confine = confine_dei_lati(righe, colonne)
    assert confine is not None and 280 < confine < 310


def test_conti_attivo_passivo_sulla_stessa_riga_non_confermano(tmp_path):
    # «Conto attivo … Conto passivo» e' una riga di conti, non l'intestazione dei lati.
    voci = _contrapposte(codici=False, descritte_destra=2, nomi=("Conto attivo", "Conto passivo"))
    righe, colonne = _leggi(tmp_path, voci)
    assert confine_dei_lati(righe, colonne) is None


def test_intestazione_con_anni_conferma(tmp_path):
    testata = [(40, 120, "ATTIVITA'"), (200, 120, "2025"), (310, 120, "PASSIVITA'"), (480, 120, "2025")]
    righe, colonne = _leggi(tmp_path, _contrapposte(codici=False, testata=testata, descritte_destra=2))
    confine = confine_dei_lati(righe, colonne)
    assert confine is not None and 280 < confine < 310


def test_due_esercizi_per_lato(tmp_path):
    # Il confine cade nel varco fra i due gruppi, non fra le due colonne di un lato.
    voci = []
    for k, (a, b) in enumerate(zip(_SINISTRA, _DESTRA)):
        y = 140 + k * 14
        voci += [(40, y, f"Cliente {k + 1}"), (200, y, _fmt(a)), (280, y, _fmt(b)),
                 (310, y, f"Fornitore {k + 1}"), (480, y, _fmt(b)), (560, y, _fmt(a))]
    righe, colonne = _leggi(tmp_path, voci)
    confine = confine_dei_lati(righe, colonne)
    assert confine is not None and 280 < confine < 310
    assert [c.lato for c in assegna_lati(colonne, confine)] == ["L", "L", "R", "R"]
