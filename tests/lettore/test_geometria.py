import fitz

from importers.lettore.geometria import parole_pagina, righe_fisiche


def _righe(path):
    with fitz.open(str(path)) as doc:
        return righe_fisiche(parole_pagina(doc[0]), 1)


def test_jitter_di_tre_punti_resta_una_riga(tmp_path):
    p = tmp_path / "a.pdf"
    from tests.lettore.pdf_sintetico import scrivi_pdf
    scrivi_pdf(p, [[(50, 100, "CLIENTI"), (400, 102.8, "1.234,56")]])
    righe = _righe(p)
    assert len(righe) == 1
    assert [w.testo for w in righe[0].parole] == ["CLIENTI", "1.234,56"]


def test_due_righe_a_otto_punti_sono_due(tmp_path):
    from tests.lettore.pdf_sintetico import scrivi_pdf
    p = tmp_path / "a.pdf"
    scrivi_pdf(p, [[(50, 100, "CLIENTI"), (50, 108, "BANCA")]])
    assert len(_righe(p)) == 2


def test_bordo_del_bucket_non_spezza(tmp_path):
    from tests.lettore.pdf_sintetico import scrivi_pdf
    p = tmp_path / "a.pdf"
    scrivi_pdf(p, [[(50, 99.9, "CLIENTI"), (400, 100.4, "1.234,56")]])
    assert len(_righe(p)) == 1


def test_pagina_ruotata_di_90_gradi(tmp_path):
    from tests.lettore.pdf_sintetico import scrivi_pdf
    p = tmp_path / "a.pdf"
    scrivi_pdf(p, [[(400, 100, "1.234,56"), (50, 100, "CLIENTI"), (50, 130, "BANCA")]], rotazione=90)
    righe = _righe(p)
    assert len(righe) == 2
    assert [w.testo for w in righe[0].parole] == ["CLIENTI", "1.234,56"]
    assert righe[0].parole[0].x0 < righe[0].parole[1].x0
