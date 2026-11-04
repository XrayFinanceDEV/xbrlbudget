from datetime import date
from decimal import Decimal

import fitz

from importers.lettore.colonne import colonne_documento, colonna_di
from importers.lettore.geometria import parole_pagina, righe_fisiche
from tests.lettore.pdf_sintetico import scrivi_pdf

_CORPO = 9.0


def _testata(x_destra, y, testo):
    """Un'intestazione allineata a destra sul bordo `x_destra` (scrivi_pdf allinea solo gli importi)."""
    return (x_destra - fitz.get_text_length(testo, fontsize=_CORPO), y, testo)


def _fmt(v: Decimal, decimali=2) -> str:
    segno = "-" if v < 0 else ""
    intero, _, dec = f"{abs(v):.{decimali}f}".partition(".")
    gruppi = []
    while len(intero) > 3:
        gruppi.insert(0, intero[-3:])
        intero = intero[:-3]
    gruppi.insert(0, intero)
    return f"{segno}{'.'.join(gruppi)},{dec}"


def _colonne(tmp_path, voci):
    p = tmp_path / "c.pdf"
    scrivi_pdf(p, [voci])
    with fitz.open(str(p)) as doc:
        righe = []
        for n, pagina in enumerate(doc, start=1):
            righe += righe_fisiche(parole_pagina(pagina), n)
    return colonne_documento(righe)


def _righe_dati(bordi, valori, y0=140, passo=14):
    voci = []
    for k, riga in enumerate(valori):
        y = y0 + k * passo
        voci.append((50, y, f"VOCE {k + 1}"))
        for x, v in zip(bordi, riga):
            if v is not None:
                voci.append((x, y, v if isinstance(v, str) else _fmt(v)))
    return voci


_A = [Decimal(v) for v in ("1234.56", "500.00", "98765.43", "12.30", "4500.00", "777.77")]
_B = [Decimal(v) for v in ("1000.00", "620.50", "90000.00", "15.00", "4100.10", "700.00")]


def test_due_esercizi_con_date(tmp_path):
    voci = [_testata(430, 120, "31/12/2025"), _testata(540, 120, "31/12/2024")]
    voci += _righe_dati([430, 540], list(zip(_A, _B)))
    cols = _colonne(tmp_path, voci)
    assert [c.ruolo for c in cols] == ["esercizio", "esercizio"]
    assert [c.fine for c in cols] == [date(2025, 12, 31), date(2024, 12, 31)]
    assert [c.mesi for c in cols] == [12, 12]
    assert [c.corrente for c in cols] == [True, False]
    assert all(c.lato == "U" for c in cols)
    assert [c.indice for c in cols] == [0, 1]


def test_anni_nudi_sotto_esercizio(tmp_path):
    bordi = [330, 400, 470, 540]
    voci = [_testata(x, 110, "ESERCIZIO") for x in bordi[:2]]
    voci += [_testata(470, 110, "DIFFERENZA"), _testata(540, 110, "SCOST.")]
    voci += [_testata(330, 122, "2025"), _testata(400, 122, "2024")]
    valori = []
    for a, b in zip(_A, _B):
        pct = ((a - b) / b * 100).quantize(Decimal("0.001"))
        valori.append((a, b, a - b, _fmt(pct, 3)))
    voci += _righe_dati(bordi, valori)
    cols = _colonne(tmp_path, voci)
    assert [c.ruolo for c in cols] == ["esercizio", "esercizio", "differenza", "percentuale"]
    assert cols[0].fine.year == 2025 and cols[1].fine.year == 2024
    assert cols[0].corrente and not cols[1].corrente


def test_differenza_riconosciuta_dai_numeri_senza_intestazione(tmp_path):
    valori = [(a, b, a - b) for a, b in zip(_A[:5], _B[:5])]
    cols = _colonne(tmp_path, _righe_dati([400, 470, 540], valori))
    assert [c.ruolo for c in cols] == ["esercizio", "esercizio", "differenza"]


def test_infrannuale_con_confronto_parziale(tmp_path):
    voci = [_testata(400, 120, "Periodo fino al 30/06/2026"), _testata(560, 120, "infrannuale al 30/06/2025")]
    voci += _righe_dati([400, 560], list(zip(_A, _B)))
    cols = _colonne(tmp_path, voci)
    assert [c.fine for c in cols] == [date(2026, 6, 30), date(2025, 6, 30)]
    assert [c.inizio for c in cols] == [None, None]
    assert [c.mesi for c in cols] == [6, 6]
    assert cols[0].corrente


def test_infrannuale_con_anno_intero(tmp_path):
    voci = [_testata(400, 120, "dal 01/01/2026 al 31/05/2026"),
            _testata(560, 120, "dal 01/01/2025 al 31/12/2025")]
    voci += _righe_dati([400, 560], list(zip(_A, _B)))
    cols = _colonne(tmp_path, voci)
    assert [c.inizio for c in cols] == [date(2026, 1, 1), date(2025, 1, 1)]
    assert [c.fine for c in cols] == [date(2026, 5, 31), date(2025, 12, 31)]
    assert [c.mesi for c in cols] == [5, 12]
    assert [c.ruolo for c in cols] == ["esercizio", "esercizio"]
    assert cols[0].corrente


def test_stesso_anno_mesi_diversi_si_tengono_entrambe(tmp_path):
    voci = [_testata(400, 120, "al 30/06/2025"), _testata(540, 120, "al 31/12/2025")]
    voci += _righe_dati([400, 540], list(zip(_A, _B)))
    cols = _colonne(tmp_path, voci)
    assert [c.ruolo for c in cols] == ["esercizio", "esercizio"]
    assert [c.mesi for c in cols] == [6, 12]
    assert [c.corrente for c in cols] == [False, True]


def test_corrente_a_destra(tmp_path):
    voci = [_testata(430, 120, "2024"), _testata(540, 120, "2025")]
    voci += _righe_dati([430, 540], list(zip(_B, _A)))
    cols = _colonne(tmp_path, voci)
    assert [c.corrente for c in cols] == [False, True]
    assert cols[1].fine.year == 2025


def test_data_lontana_dalle_colonne_e_una_frase(tmp_path):
    voci = [(50, 100, "Bilancio al 31/12/2025")]
    voci += _righe_dati([430, 540], list(zip(_A, _B)))
    cols = _colonne(tmp_path, voci)
    assert [c.fine for c in cols] == [None, None]
    assert [c.corrente for c in cols] == [False, False]


def test_mastri_e_conti_su_colonne_diverse(tmp_path):
    voci = [_testata(540, 110, "31/12/2025")]
    y = 130
    conti = [("100.00", "250.50"), ("40.00", "60.00", "0.10"), ("1000.00", "1.00"), ("7.25", "2.75")]
    for m, figli in enumerate(conti):
        voci += [(50, y, f"MASTRO {m + 1}"), (450, y, _fmt(sum(Decimal(v) for v in figli)))]
        y += 14
        for k, v in enumerate(figli):
            voci += [(70, y, f"CONTO {m + 1}.{k + 1}"), (540, y, _fmt(Decimal(v)))]
            y += 14
    cols = _colonne(tmp_path, voci)
    assert [c.ruolo for c in cols] == ["mastro", "esercizio"]
    assert [c.fine for c in cols] == [date(2025, 12, 31)] * 2
    assert [c.mesi for c in cols] == [12, 12]
    assert [c.corrente for c in cols] == [False, True]


def test_colonne_vicine_senza_somme_non_sono_mastri(tmp_path):
    # importi che si alternano fra due bordi ma non si sommano: restano due colonne-esercizio
    voci, y = [], 130
    for k in range(5):
        voci += [(50, y, f"A {k}"), (450, y, _fmt(Decimal("999.00") + k))]
        voci += [(50, y + 14, f"B {k}"), (540, y + 14, _fmt(Decimal("10.00") + k))]
        y += 28
    cols = _colonne(tmp_path, voci)
    assert [c.ruolo for c in cols] == ["esercizio", "esercizio"]


def test_dare_avere_saldo_dalle_intestazioni(tmp_path):
    bordi = [400, 470, 540]
    voci = [_testata(400, 120, "DARE"), _testata(470, 120, "AVERE"), _testata(540, 120, "SALDO")]
    voci += _righe_dati(bordi, [(a, b, a - b) for a, b in zip(_A, _B)])
    cols = _colonne(tmp_path, voci)
    assert [c.ruolo for c in cols] == ["dare", "avere", "saldo"]


def test_colonna_di_fuori_tolleranza(tmp_path):
    cols = _colonne(tmp_path, _righe_dati([430, 540], list(zip(_A, _B))))
    assert colonna_di(390, cols) is None
    assert colonna_di(500, cols) is None
    assert colonna_di(428, cols) is cols[0]
    assert colonna_di(551, cols) is cols[1]
