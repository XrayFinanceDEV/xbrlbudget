from decimal import Decimal

import fitz
import pytest

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
    # Due sole righe descritte a destra: e' l'intestazione in minuscolo a confermare il confine.
    righe, colonne = _leggi(tmp_path, _contrapposte(codici=False, descritte_destra=2))
    assert confine_dei_lati(righe, colonne) is None
    testata = [(40, 120, "Attività"), (310, 120, "Passività")]
    righe, colonne = _leggi(tmp_path, _contrapposte(codici=False, testata=testata, descritte_destra=2))
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


def test_schema_con_descrizioni_che_sforano_non_e_contrapposto(tmp_path):
    # Una descrizione lunga scorre sotto la prima colonna fino all'importo della seconda: le sue ultime
    # parole non sono un lato destro, e lo spazio fra due di esse non e' un varco fra sezioni.
    voci = []
    for k, (a, b) in enumerate(zip(_SINISTRA, _DESTRA)):
        y = 140 + k * 14
        voci += [(50, y, f"VOCE {k + 1}"), (430, y, _fmt(a)), (540, y, _fmt(b))]
    # Stessa voce su quattro righe: lo spazio dopo «oltre» cade appena a destra della prima colonna, nello
    # stesso punto su tutte, e «l'esercizio» resta a sinistra dell'importo della seconda.
    prima = "Crediti verso altri soggetti diversi da clienti controllate e collegate esigibili entro e oltre"
    x = 432 - fitz.get_text_length(prima, fontsize=9.0)
    for k in range(4):
        y = 140 + (8 + k) * 14
        voci += [(x, y, prima + " l'esercizio"), (540, y, _fmt(_DESTRA[k]))]
    righe, colonne = _leggi(tmp_path, voci)
    assert any(p.testo == "l'esercizio" and p.x0 > 430 for r in righe for p in r.parole)
    assert confine_dei_lati(righe, colonne) is None


def _testata(x_destra, y, testo):
    return (x_destra - fitz.get_text_length(testo, fontsize=9.0), y, testo)


def _contrapposte_datate(date_sx, date_dx):
    """Contrapposte con una o due colonne per lato e la data stampata sopra ciascuna."""
    bordi_sx, bordi_dx = ([280], [560]) if len(date_sx) == 1 else ([200, 280], [480, 560])
    voci = [_testata(x, 120, d) for x, d in zip(bordi_sx + bordi_dx, date_sx + date_dx) if d]
    for k, (a, b) in enumerate(zip(_SINISTRA, _DESTRA)):
        y = 140 + k * 14
        voci += [(40, y, f"Cliente {k + 1}"), (310, y, f"Fornitore {k + 1}")]
        voci += [(x, y, _fmt(v)) for x, v in zip(bordi_sx, (a, b))]
        voci += [(x, y, _fmt(v)) for x, v in zip(bordi_dx, (b, a))]
    return voci


@pytest.mark.parametrize("date_sx, date_dx, attese", [
    (["31/12/2025"], ["31/12/2025"], [True, True]),
    (["2025", "2024"], ["2025", "2024"], [True, False, True, False]),
    ([None], [None], [True, True]),
], ids=["stessa_data_sui_due_lati", "due_esercizi_per_lato", "una_colonna_senza_data_per_lato"])
def test_corrente_per_lato(tmp_path, date_sx, date_dx, attese):
    righe, colonne = _leggi(tmp_path, _contrapposte_datate(date_sx, date_dx))
    confine = confine_dei_lati(righe, colonne)
    assert confine is not None
    colonne = assegna_lati(colonne, confine)
    assert [c.corrente for c in colonne] == attese
    assert all(c.ruolo == "esercizio" for c in colonne)


def test_senza_confine_corrente_resta_quello_del_documento(tmp_path):
    righe, colonne = _leggi(tmp_path, [_testata(430, 120, "31/12/2025"), _testata(540, 120, "31/12/2024")]
                            + [v for k, (a, b) in enumerate(zip(_SINISTRA, _DESTRA))
                               for v in ((50, 140 + k * 14, f"VOCE {k + 1}"), (430, 140 + k * 14, _fmt(a)),
                                         (540, 140 + k * 14, _fmt(b)))])
    assert [c.corrente for c in assegna_lati(colonne, None)] == [True, False]


def test_varco_di_un_punto(tmp_path):
    # Come budget_435 (importo fino a 296, descrizione da 297): un varco piu' stretto di uno spazio. Qui 1,5 pt,
    # perche' sotto PyMuPDF fonde le due parole del PDF sintetico in una sola.
    voci = []
    for k, (a, b) in enumerate(zip(_SINISTRA, _DESTRA)):
        y = 140 + k * 14
        voci += [(40, y, f"Cliente {k + 1}"), (296, y, _fmt(a)), (297.5, y, f"Fornitore {k + 1}"), (560, y, _fmt(b))]
    righe, colonne = _leggi(tmp_path, voci)
    confine = confine_dei_lati(righe, colonne)
    assert confine is not None and 296 < confine < 297.5
