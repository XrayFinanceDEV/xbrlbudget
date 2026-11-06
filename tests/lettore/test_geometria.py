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


def test_timbro_verticale_non_unisce_le_righe(tmp_path):
    # un timbro scritto in verticale sul margine destro ha parole alte quanto tre righe: non le deve unire
    p = tmp_path / "a.pdf"
    doc = fitz.open()
    pg = doc.new_page(width=595, height=842)
    for k, (nome, importo) in enumerate([("CONTO UNO", "10,00"), ("CONTO DUE", "20,00"), ("CONTO TRE", "30,00")]):
        pg.insert_text((50, 700 + 10 * k), nome, fontsize=9)
        pg.insert_text((250, 700 + 10 * k), importo, fontsize=9)
    pg.insert_text((588, 712), "stampato il 01/01/2026", fontsize=9, rotate=90)
    doc.save(str(p))
    righe = _righe(p)
    assert [[w.testo for w in r.parole] for r in righe] == [["CONTO", "UNO", "10,00"], ["CONTO", "DUE", "20,00"],
                                                             ["CONTO", "TRE", "30,00"]]


def test_timbro_verticale_su_pagina_ruotata_resta_fuori(tmp_path):
    # pagina ruotata: il testo orizzontale a schermo resta, quello verticale a schermo no
    from tests.lettore.pdf_sintetico import scrivi_pdf
    p = tmp_path / "a.pdf"
    scrivi_pdf(p, [[(400, 100, "1.234,56"), (50, 100, "CLIENTI"), (50, 130, "BANCA")]], rotazione=90)
    righe = _righe(p)
    assert [w.testo for r in righe for w in r.parole] == ["CLIENTI", "1.234,56", "BANCA"]
