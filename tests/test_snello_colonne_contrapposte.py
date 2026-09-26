"""collect_source_rows: split di colonna su pagine ruotate e con importi spezzati.

Task 12 (import snello): due bug indipendenti facevano fondere un conto
dell'attivo e uno del passivo in una sola riga su PDF a "sezioni
contrapposte" — (1) l'header fisico Attività/Passività in Title case su una
pagina ruotata 90°, (2) un importo spezzato su più parole PDF che inquina il
riconoscimento dei codici conto e manda fuori strada il gutter-finder.
Tutti i PDF qui sono sintetici (fitz), mai i file reali del corpus.
"""
from decimal import Decimal as D

import fitz
import pytest

from importers.detail_enrichment import collect_source_rows


def _put_row(page, inv, dx0, dy, tokens, step=45, fontsize=10):
    """Place a logical row's tokens on a page rotated 90°.

    ``dx``/``dy`` are DISPLAYED (post-rotation) coordinates; ``inv`` is the
    inverse of ``page.rotation_matrix``, so a row that reads left-to-right in
    the displayed frame is written as a vertical run of raw glyphs — exactly
    how a genuinely rotated scan's content stream is authored.
    """
    for i, tok in enumerate(tokens):
        raw = fitz.Point(dx0 + i * step, dy) * inv
        page.insert_text((raw.x, raw.y), tok, fontsize=fontsize)


def _build_rotated_titlecase(path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.set_rotation(90)
    inv = ~page.rotation_matrix

    def put(dx, dy, text):
        raw = fitz.Point(dx, dy) * inv
        page.insert_text((raw.x, raw.y), text, fontsize=10)

    put(150, 50, "Attività")
    put(550, 50, "Passività")

    left_rows = [
        ("101", ["CASSA"], "1.500,00"),
        ("102", ["BANCA", "C/C"], "22.300,50"),
        ("103", ["CREDITI", "CLIENTI"], "8.750,25"),
        ("104", ["MAGAZZINO"], "3.000,00"),
    ]
    for i, (code, desc, amt) in enumerate(left_rows):
        _put_row(page, inv, 150, 100 + i * 80, [code, *desc, amt])

    right_rows = [
        ("201", ["FORNITORI"], "5.400,00"),
        ("202", ["BANCHE", "C/C"], "12.000,00"),
        ("203", ["DEBITI", "TRIBUTARI"], "900,75"),
        ("204", ["PATRIMONIO", "NETTO"], "17.250,00"),
    ]
    for i, (code, desc, amt) in enumerate(right_rows):
        _put_row(page, inv, 550, 100 + i * 80, [code, *desc, amt])

    doc.save(path)
    doc.close()


def _build_fragmented_amounts(path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # The text-only trigger of is_contrapposte_file: sufficient by itself to
    # set two_sides=True regardless of the physical layout below.
    page.insert_text((50, 30), "BILANCIO DI VERIFICA AL 31/12/2025", fontsize=10)

    # Left column: every amount is split into three PDF words (integer part,
    # a LONE comma, decimals) — the damaged-text-layer pattern measured on
    # budget_337 (a standalone ',' token, not just one glued to the integer).
    left_rows = [
        ("101", "CASSA", "2.280", "30"),
        ("102", "BANCA C/C", "1.100", "45"),
        ("103", "CREDITI CLIENTI", "9.500", "00"),
        ("104", "MAGAZZINO", "3.000", "00"),
    ]
    y = 80
    for code, desc, whole, cents in left_rows:
        page.insert_text((50, y), code, fontsize=10)
        page.insert_text((90, y), desc, fontsize=10)
        end_x = 230 + 5.02 * len(whole)
        page.insert_text((230, y), whole, fontsize=10)
        page.insert_text((end_x + 9, y), ",", fontsize=10)
        page.insert_text((end_x + 17, y), cents, fontsize=10)
        y += 25

    right_rows = [
        ("201", "FORNITORI", "5.400,00"),
        ("202", "BANCHE C/C", "12.000,00"),
        ("203", "DEBITI TRIBUTARI", "900,75"),
        ("204", "PATRIMONIO NETTO", "17.250,00"),
    ]
    y = 80
    for code, desc, amt in right_rows:
        page.insert_text((400, y), code, fontsize=10)
        page.insert_text((440, y), desc, fontsize=10)
        page.insert_text((550, y), amt, fontsize=10)
        y += 25

    doc.save(path)
    doc.close()


def _build_single_column_ledger(path):
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((40, 30), "BILANCIO DI VERIFICA AL 31/12/2025", fontsize=10)
    page.insert_text((40, 55), "Conto Descrizione Saldo iniziale Dare Avere Saldo finale", fontsize=9)

    rows = [
        ("101001", "CASSA", "1.000", "500", "300", "1.200"),
        ("102003", "BANCA POPOLARE VERONA", "20.000", "3.000", "1.500", "21.500"),
        ("204001", "FORNITORI VARI", "9.000", "1.000", "2.500", "10.500"),
        ("601002", "RIMANENZE MATERIE PRIME", "4.000", "0", "0", "4.000"),
    ]
    y = 90
    for code, desc, c1, c2, c3, c4 in rows:
        page.insert_text((40, y), code, fontsize=9)
        page.insert_text((110, y), desc, fontsize=9)
        page.insert_text((320, y), c1, fontsize=9)
        page.insert_text((420, y), c2, fontsize=9)
        page.insert_text((520, y), c3, fontsize=9)
        # Last column deliberately fragmented, same pattern as budget_337, to
        # force _be_page_needs_coordinate_repair on a genuinely SINGLE-column
        # page (one account per row, several numeric columns).
        page.insert_text((620, y), c4, fontsize=9)
        page.insert_text((654, y), ",", fontsize=9)
        page.insert_text((662, y), "00", fontsize=9)
        y += 25

    doc.save(path)
    doc.close()


def _build_normal_two_column(path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((80, 50), "ATTIVITA'", fontsize=10)
    page.insert_text((400, 50), "PASSIVITA'", fontsize=10)

    left_rows = [
        ("101", "CASSA", "1.500,00"),
        ("102", "BANCA C/C", "22.300,50"),
        ("103", "CREDITI CLIENTI", "8.750,25"),
        ("104", "MAGAZZINO", "3.000,00"),
    ]
    y = 90
    for code, desc, amt in left_rows:
        page.insert_text((50, y), code, fontsize=10)
        page.insert_text((90, y), desc, fontsize=10)
        page.insert_text((230, y), amt, fontsize=10)
        y += 25

    right_rows = [
        ("201", "FORNITORI", "5.400,00"),
        ("202", "BANCHE C/C", "12.000,00"),
        ("203", "DEBITI TRIBUTARI", "900,75"),
        ("204", "PATRIMONIO NETTO", "17.250,00"),
    ]
    y = 90
    for code, desc, amt in right_rows:
        page.insert_text((400, y), code, fontsize=10)
        page.insert_text((440, y), desc, fontsize=10)
        page.insert_text((550, y), amt, fontsize=10)
        y += 25

    doc.save(path)
    doc.close()


def _by_code(rows, code):
    return next(r for r in rows if r.code == code)


def test_rotated_page_titlecase_headers_split_into_left_and_right(tmp_path):
    path = tmp_path / "rotated_titlecase.pdf"
    _build_rotated_titlecase(str(path))

    rows = collect_source_rows(str(path))

    sides = {r.side for r in rows}
    assert sides == {"L", "R"}
    left_codes = {r.code for r in rows if r.side == "L" and r.code}
    right_codes = {r.code for r in rows if r.side == "R" and r.code}
    assert left_codes == {"101", "102", "103", "104"}
    assert right_codes == {"201", "202", "203", "204"}
    # No row carries an account label from both sides.
    fornitori_row = _by_code(rows, "201")
    assert "CASSA" not in fornitori_row.text and "MAGAZZINO" not in fornitori_row.text
    cassa_row = _by_code(rows, "101")
    assert "FORNITORI" not in cassa_row.text
    assert cassa_row.amounts == (D("1500.00"),)
    assert fornitori_row.amounts == (D("5400.00"),)


def test_fragmented_amount_tokens_split_correctly_and_parse_as_one_value(tmp_path):
    path = tmp_path / "fragmented_amounts.pdf"
    _build_fragmented_amounts(str(path))

    rows = collect_source_rows(str(path))

    sides = {r.side for r in rows}
    assert sides == {"L", "R"}
    cassa_row = _by_code(rows, "101")
    assert cassa_row.side == "L"
    assert cassa_row.amounts == (D("2280.30"),)
    assert "FORNITORI" not in cassa_row.text
    fornitori_row = _by_code(rows, "201")
    assert fornitori_row.side == "R"
    assert fornitori_row.amounts == (D("5400.00"),)
    assert "CASSA" not in fornitori_row.text
    # None of the fragment tails ("30", "45", "00", "00") were promoted to
    # their own fake account code.
    assert {"30", "45", "00"} & {r.code for r in rows} == set()


def test_single_column_ledger_with_bilancio_di_verifica_stays_one_band(tmp_path):
    path = tmp_path / "single_column.pdf"
    _build_single_column_ledger(str(path))

    rows = collect_source_rows(str(path))

    sides = {r.side for r in rows}
    assert sides == {"T"}
    cassa_row = _by_code(rows, "101001")
    assert cassa_row.amounts == (D("1200.00"),)
    assert "BANCA POPOLARE VERONA" not in cassa_row.text
    banca_row = _by_code(rows, "102003")
    assert banca_row.amounts == (D("21500.00"),)


def test_ordinary_unrotated_two_column_page_is_unaffected(tmp_path):
    path = tmp_path / "normal.pdf"
    _build_normal_two_column(str(path))

    rows = collect_source_rows(str(path))

    sides = {r.side for r in rows}
    assert sides == {"L", "R"}
    cassa_row = _by_code(rows, "101")
    assert cassa_row.side == "L" and cassa_row.amounts == (D("1500.00"),)
    fornitori_row = _by_code(rows, "201")
    assert fornitori_row.side == "R" and fornitori_row.amounts == (D("5400.00"),)
