"""collect_source_rows: la sezione (SP o CE) di ogni riga su una situazione a sezioni
contrapposte (lotto week-43, ABCLOG 1450 e Panificio 1432).

- 1450: la pagina 2 continua lo stato patrimoniale senza titolo; le parole «COSTI» e
  «RICAVI» dentro i conti («crediti per costi anticipati», «debiti per ricavi anticipati»)
  la classificavano conto economico, e mezzo passivo spariva nel CE.
- 1432: la pagina 2 continua lo stato patrimoniale in alto e apre il conto economico a meta'
  pagina; le righe sopra il titolo prendevano il verdetto della pagina (CE).

Regola: le righe sopra il titolo di una pagina, e una pagina senza titolo, restano nella
sezione della pagina prima, finche' quella non si e' chiusa col suo totale stampato in fondo.
PDF sintetici (fitz), mai i file del corpus.
"""
import fitz

from importers.detail_enrichment import collect_source_rows


def _testata(page, titolo, sinistra="ATTIVITA'", destra="PASSIVITA'"):
    if titolo:
        page.insert_text((230, 40), titolo, fontsize=11)
    page.insert_text((60, 60), sinistra, fontsize=9)
    page.insert_text((340, 60), destra, fontsize=9)


def _conto(page, y, sx=None, dx=None):
    for x, voce in ((40, sx), (320, dx)):
        if voce:
            codice, descrizione, importo = voce
            page.insert_text((x, y), codice, fontsize=8)
            page.insert_text((x + 40, y), descrizione, fontsize=8)
            page.insert_text((x + 200, y), importo, fontsize=8)


def _pdf(tmp_path, titolo_ce_a_meta_pagina=False):
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    _testata(p1, "Stato Patrimoniale")
    for k in range(8):
        _conto(p1, 90 + 14 * k, (f"1{k}", f"CREDITI DIVERSI {k}", "1.000,00"),
               (f"5{k}", f"DEBITI DIVERSI {k}", "1.000,00"))
    p2 = doc.new_page(width=595, height=842)
    # pagina di continuazione: nessun titolo e nessuna intestazione Attivita'/Passivita'
    _conto(p2, 90, ("21", "CREDITI PER COSTI ANTICIPATI", "500,00"),
           ("61", "DEBITI PER RICAVI ANTICIPATI", "500,00"))
    for k in range(6):
        _conto(p2, 104 + 14 * k, (f"2{k+2}", f"ALTRI CREDITI {k}", "100,00"),
               (f"6{k+2}", f"ALTRI DEBITI {k}", "100,00"))
    if titolo_ce_a_meta_pagina:
        p2.insert_text((230, 400), "Conto Economico", fontsize=11)
        p2.insert_text((60, 420), "COSTI", fontsize=9)
        p2.insert_text((340, 420), "RICAVI", fontsize=9)
        for k in range(6):
            _conto(p2, 440 + 14 * k, (f"7{k}", f"ACQUISTI {k}", "200,00"),
                   (f"8{k}", f"VENDITE {k}", "300,00"))
    else:
        _conto(p2, 200, ("", "Totale a pareggio", "9.100,00"), ("", "Totale a pareggio", "9.100,00"))
        p3 = doc.new_page(width=595, height=842)
        _testata(p3, "Conto Economico", "COSTI", "RICAVI")
        for k in range(6):
            _conto(p3, 90 + 14 * k, (f"7{k}", f"ACQUISTI {k}", "200,00"),
                   (f"8{k}", f"VENDITE {k}", "300,00"))
    percorso = str(tmp_path / "contrapposte.pdf")
    doc.save(percorso)
    doc.close()
    return percorso


def _sezioni(righe, pagina):
    return {r.text.split()[1] if len(r.text.split()) > 1 else r.text: r.statement
            for r in righe if r.page == pagina and r.amounts}


def test_la_pagina_senza_titolo_continua_lo_stato_patrimoniale(tmp_path):
    righe = collect_source_rows(_pdf(tmp_path))
    pagina2 = [r for r in righe if r.page == 2 and r.amounts and "CREDITI" in r.text.upper()
               or r.page == 2 and "DEBITI" in r.text.upper()]
    assert pagina2 and all(r.statement == "bs" for r in pagina2), \
        [(r.text, r.statement) for r in pagina2]
    pagina3 = [r for r in righe if r.page == 3 and r.amounts]
    assert pagina3 and all(r.statement == "ce" for r in pagina3)


def test_le_righe_sopra_il_titolo_del_ce_restano_nello_stato_patrimoniale(tmp_path):
    righe = collect_source_rows(_pdf(tmp_path, titolo_ce_a_meta_pagina=True))
    sopra = [r for r in righe if r.page == 2 and r.amounts
             and ("CREDITI" in r.text.upper() or "DEBITI" in r.text.upper())]
    sotto = [r for r in righe if r.page == 2 and r.amounts
             and ("ACQUISTI" in r.text.upper() or "VENDITE" in r.text.upper())]
    assert sopra and all(r.statement == "bs" for r in sopra), [(r.text, r.statement) for r in sopra]
    assert sotto and all(r.statement == "ce" for r in sotto)


def test_una_pagina_che_chiude_col_risultato_e_il_pareggio_apre_la_sezione_dopo(tmp_path):
    """budget_702/703: la pagina 1 chiude lo SP con «Perdita Esercizio» e una riga di soli
    importi uguali (il pareggio senza didascalia); la pagina 2, senza titolo, e' conto
    economico e la decidono le sue colonne «COSTI | RICAVI»."""
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    _testata(p1, "Stato Patrimoniale")
    for k in range(6):
        _conto(p1, 90 + 14 * k, (f"1{k}", f"CREDITI DIVERSI {k}", "1.000,00"),
               (f"5{k}", f"DEBITI DIVERSI {k}", "1.000,00"))
    _conto(p1, 200, None, ("", "Perdita Esercizio", "15,00"))
    p1.insert_text((240, 214), "6.015,00", fontsize=8)
    p1.insert_text((520, 214), "6.015,00", fontsize=8)
    p2 = doc.new_page(width=595, height=842)
    _testata(p2, None, "COSTI", "RICAVI")
    for k in range(6):
        _conto(p2, 90 + 14 * k, (f"7{k}", f"ACQUISTI {k}", "200,00"),
               (f"8{k}", f"VENDITE {k}", "300,00"))
    percorso = str(tmp_path / "chiusa.pdf")
    doc.save(percorso)
    doc.close()
    righe = [r for r in collect_source_rows(percorso) if r.page == 2 and r.amounts]
    assert righe and all(r.statement == "ce" for r in righe), [(r.text, r.statement) for r in righe]


def test_una_pagina_che_chiude_coi_totali_dell_altra_sezione_decide_da_se(tmp_path):
    """budget_615 (AGO): l'ultima pagina, senza titolo, chiude con «TOTALE COSTI ... TOTALE
    RICAVI» e «UTILE D'ESERCIZIO»: e' conto economico anche se la pagina prima era letta come SP."""
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    _testata(p1, "Stato Patrimoniale")
    for k in range(6):
        _conto(p1, 90 + 14 * k, (f"1{k}", f"CREDITI DIVERSI {k}", "1.000,00"),
               (f"5{k}", f"DEBITI DIVERSI {k}", "1.000,00"))
    p2 = doc.new_page(width=595, height=842)
    for k in range(6):
        _conto(p2, 90 + 14 * k, (f"7{k}", f"ACQUISTI {k}", "200,00"),
               (f"8{k}", f"VENDITE {k}", "300,00"))
    _conto(p2, 200, ("", "TOTALE COSTI", "1.200,00"), ("", "TOTALE RICAVI", "1.800,00"))
    percorso = str(tmp_path / "chiusura_ce.pdf")
    doc.save(percorso)
    doc.close()
    righe = [r for r in collect_source_rows(percorso) if r.page == 2 and r.amounts]
    assert righe and all(r.statement == "ce" for r in righe), [(r.text, r.statement) for r in righe]
