"""collect_source_rows: split di colonna su pagine ruotate e con importi spezzati.

Task 12 (import snello): due bug indipendenti facevano fondere un conto
dell'attivo e uno del passivo in una sola riga su PDF a "sezioni
contrapposte" — (1) l'header fisico Attività/Passività in Title case su una
pagina ruotata 90°, (2) un importo spezzato su più parole PDF che inquina il
riconoscimento dei codici conto e manda fuori strada il gutter-finder.
Tutti i PDF qui sono sintetici (fitz), mai i file reali del corpus.

Fix round 1 (revisione): quattro scoperture reali trovate in review e
riprodotte con PDF sintetici — didascalie corte a due lettere rifiutate dalla
guardia anti-colonna-unica, una colonna comparativa (anno precedente) che
_be_collect_side_facts non sa tenere separata dalla corrente, un codice
gerarchico puntato che perde i punti nella normalizzazione, e una frase di
nota integrativa che il gate case-insensitive dell'header trattava come
un'intestazione fisica.

Fix round 2 (revisione del controller): la guardia del round 1 sulla colonna
comparativa era tarata su UNA riga, non su una colonna — un'unica riga con un
secondo importo (una svista, un totale di controllo duplicato) bastava a far
tornare l'intera pagina al comportamento pre-Task-12. Ora conta il RAPPORTO
per lato: solo quando almeno il 30% delle righe di un lato porta 2+ gruppi
importo quella colonna è davvero comparativa.
"""
import importlib.util
import subprocess
from decimal import Decimal as D
from pathlib import Path

import fitz
import pytest

from importers.detail_enrichment import collect_source_rows

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _load_old_collect_source_rows():
    """The pre-Task-12 collect_source_rows, loaded straight from ffa724f.

    Only importers/detail_enrichment.py's own source at that commit is
    replaced; its internal ``from importers.situazione_contabile_parser
    import (...)`` resolves normally, against the CURRENT (untouched by
    Task 12) module on sys.path.
    """
    source = subprocess.run(
        ["git", "show", "ffa724f:importers/detail_enrichment.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    spec = importlib.util.spec_from_loader("detail_enrichment_ffa724f", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, "detail_enrichment_ffa724f.py", "exec"), module.__dict__)
    return module.collect_source_rows


def _build_short_alnum_captions(path):
    """Same shape as _build_fragmented_amounts, but 2-letter+digit captions
    ("CC1", "FN1"...): only a 2-letter run, never a 3-letter one."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 30), "BILANCIO DI VERIFICA AL 31/12/2025", fontsize=10)

    left_rows = [
        ("101", "CC1", "2.280", "30"),
        ("102", "BC2", "1.100", "45"),
        ("103", "CR1", "9.500", "00"),
        ("104", "MG1", "3.000", "00"),
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
        ("201", "FN1", "5.400,00"),
        ("202", "BN1", "12.000,00"),
        ("203", "DT1", "900,75"),
        ("204", "PN1", "17.250,00"),
    ]
    y = 80
    for code, desc, amt in right_rows:
        page.insert_text((400, y), code, fontsize=10)
        page.insert_text((440, y), desc, fontsize=10)
        page.insert_text((550, y), amt, fontsize=10)
        y += 25

    doc.save(path)
    doc.close()


def _build_comparative_column(path):
    """A left account with a fragmented CURRENT amount and a clean, complete
    PRIOR-year amount further along the same physical row, still on the same
    (future) left side — the shape _be_collect_side_facts cannot represent
    (one amount per row)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 30), "BILANCIO DI VERIFICA AL 31/12/2025", fontsize=10)

    left_rows = [
        ("101", "CASSA", "2.280", "30", "1.900,00"),
        ("102", "BANCA C/C", "1.100", "45", "1.050,00"),
        ("103", "CREDITI CLIENTI", "9.500", "00", "8.000,00"),
        ("104", "MAGAZZINO", "3.000", "00", "2.500,00"),
    ]
    y = 80
    for code, desc, whole, cents, prior in left_rows:
        page.insert_text((50, y), code, fontsize=10)
        page.insert_text((90, y), desc, fontsize=10)
        end_x = 230 + 5.02 * len(whole)
        page.insert_text((230, y), whole, fontsize=10)
        page.insert_text((end_x + 9, y), ",", fontsize=10)
        page.insert_text((end_x + 17, y), cents, fontsize=10)
        page.insert_text((end_x + 60, y), prior, fontsize=10)
        y += 25

    right_rows = [
        ("201", "FORNITORI", "5.400,00"),
        ("202", "BANCHE C/C", "12.000,00"),
        ("203", "DEBITI TRIBUTARI", "900,75"),
        ("204", "PATRIMONIO NETTO", "17.250,00"),
    ]
    y = 80
    for code, desc, amt in right_rows:
        page.insert_text((450, y), code, fontsize=10)
        page.insert_text((490, y), desc, fontsize=10)
        page.insert_text((560, y), amt, fontsize=10)
        y += 25

    doc.save(path)
    doc.close()


def _build_dotted_codes(path):
    """A repair-eligible two-column page (>=3 isolated ',' fragments) whose
    left accounts print a dotted hierarchy code ("01.01", "01.01.001")."""
    doc = fitz.open()
    page = doc.new_page(width=750, height=842)
    page.insert_text((50, 30), "BILANCIO DI VERIFICA AL 31/12/2025", fontsize=10)

    left_rows = [
        ("01.01", "COSTI IMPIANTO", "2.280", "30"),
        ("01.01.001", "COSTI IMPIANTO SPECIFICI", "1.100", "45"),
        ("01.02", "AVVIAMENTO", "9.500", "00"),
        ("01.03", "MAGAZZINO", "3.000", "00"),
    ]
    y = 80
    for code, desc, whole, cents in left_rows:
        page.insert_text((50, y), code, fontsize=10)
        page.insert_text((160, y), desc, fontsize=10)
        end_x = 330 + 5.02 * len(whole)
        page.insert_text((330, y), whole, fontsize=10)
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
        page.insert_text((600, y), code, fontsize=10)
        page.insert_text((640, y), desc, fontsize=10)
        page.insert_text((710, y), amt, fontsize=10)
        y += 25

    doc.save(path)
    doc.close()


def _build_note_prose_sentence(path):
    """A note-integrativa sentence mentioning both words in one long line,
    in the header's own top band, plus ordinary single-column content."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(
        (50, 100),
        "I criteri di valutazione adottati per la redazione delle Attività"
        " e delle Passività sono conformi ai principi contabili nazionali",
        fontsize=9,
    )
    rows = [
        ("101", "CASSA", "1.500,00"),
        ("102", "BANCA C/C", "22.300,50"),
        ("103", "CREDITI CLIENTI", "8.750,25"),
    ]
    y = 300
    for code, desc, amt in rows:
        page.insert_text((50, y), code, fontsize=10)
        page.insert_text((90, y), desc, fontsize=10)
        page.insert_text((230, y), amt, fontsize=10)
        y += 25
    doc.save(path)
    doc.close()


def test_short_two_letter_captions_still_split_correctly(tmp_path):
    path = tmp_path / "short_captions.pdf"
    _build_short_alnum_captions(str(path))

    rows = collect_source_rows(str(path))

    sides = {r.side for r in rows}
    assert sides == {"L", "R"}
    cassa_row = _by_code(rows, "101")
    assert cassa_row.side == "L"
    assert cassa_row.amounts == (D("2280.30"),)
    assert "FN1" not in cassa_row.text
    fornitori_row = _by_code(rows, "201")
    assert fornitori_row.side == "R"
    assert fornitori_row.amounts == (D("5400.00"),)
    assert "CC1" not in fornitori_row.text


def test_comparative_column_falls_back_to_pre_task12_behaviour(tmp_path):
    path = tmp_path / "comparative_column.pdf"
    _build_comparative_column(str(path))

    new_rows = collect_source_rows(str(path))
    old_collect_source_rows = _load_old_collect_source_rows()
    old_rows = old_collect_source_rows(str(path))

    def _shape(rows):
        return [(r.side, r.code, r.text, r.amounts) for r in rows]

    assert _shape(new_rows) == _shape(old_rows)
    # The specific fabrication this ruling forbids: the coordinate-repair
    # reconstruction turning a leaked "1.900,00" into a fake account code
    # "190000". Falling back to the base behaviour must not reintroduce it
    # under a different disguise either.
    assert "190000" not in {r.code for r in new_rows}


def test_dotted_hierarchy_codes_are_kept_as_printed(tmp_path):
    path = tmp_path / "dotted_codes.pdf"
    _build_dotted_codes(str(path))

    rows = collect_source_rows(str(path))

    parent = _by_code(rows, "01.01")
    child = _by_code(rows, "01.01.001")
    assert parent.code == "01.01" and child.code == "01.01.001"
    assert parent.amounts == (D("2280.30"),)
    assert child.amounts == (D("1100.45"),)
    fornitori_row = _by_code(rows, "201")
    assert fornitori_row.side == "R" and fornitori_row.amounts == (D("5400.00"),)


def test_long_note_sentence_does_not_set_two_sides(tmp_path):
    path = tmp_path / "note_prose.pdf"
    _build_note_prose_sentence(str(path))

    rows = collect_source_rows(str(path))

    sides = {r.side for r in rows}
    assert sides == {"T"}
    # No row is tagged with the two-sided ledger kinds ("ledger_final"/
    # "income"): every row's kinds stay whatever a two_sides=False page
    # already produced before this fix.
    assert all(k not in ("ledger_final", "income") for r in rows for k in r.kinds)
    cassa_row = next(r for r in rows if "CASSA" in r.text)
    assert cassa_row.amounts == (D("101"), D("1500.00"))


def _build_isolated_second_amount(path):
    """Ten accounts per side, repair-eligible (>=3 isolated ',' fragments);
    only ONE left row (CASSA) also carries a clean second (comparative)
    amount further along the same row, still within the left side's own
    x-range. 1/10 rows with a second amount is far below the 30% ratio: the
    repair must still apply to the whole page.
    """
    doc = fitz.open()
    page = doc.new_page(width=950, height=842)
    page.insert_text((50, 30), "BILANCIO DI VERIFICA AL 31/12/2025", fontsize=10)

    left_rows = [
        ("101", "CASSA", "2.280", "30", "1.900,00"),
        ("102", "BANCA C/C", "1.100", "45", None),
        ("103", "CREDITI CLIENTI", "9.500", "00", None),
        ("104", "MAGAZZINO", "3.000", "00", None),
        ("105", "CREDITI DIVERSI", "1.200", "00", None),
        ("106", "RATEI ATTIVI", "800", "00", None),
        ("107", "RISCONTI ATTIVI", "600", "00", None),
        ("108", "ALTRI CREDITI", "400", "00", None),
        ("109", "TITOLI", "2.000", "00", None),
        ("110", "PARTECIPAZIONI", "5.000", "00", None),
    ]
    y = 80
    for code, desc, whole, cents, prior in left_rows:
        page.insert_text((50, y), code, fontsize=10)
        page.insert_text((90, y), desc, fontsize=10)
        end_x = 260 + 5.02 * len(whole)
        page.insert_text((260, y), whole, fontsize=10)
        page.insert_text((end_x + 9, y), ",", fontsize=10)
        page.insert_text((end_x + 17, y), cents, fontsize=10)
        if prior:
            page.insert_text((end_x + 60, y), prior, fontsize=10)
        y += 20

    right_rows = [
        ("201", "FORNITORI", "5.400,00"),
        ("202", "BANCHE C/C", "12.000,00"),
        ("203", "DEBITI TRIBUTARI", "900,75"),
        ("204", "PATRIMONIO NETTO", "17.250,00"),
        ("205", "FONDO TFR", "3.100,00"),
        ("206", "DEBITI PREVIDENZIALI", "700,00"),
        ("207", "ALTRI DEBITI", "1.400,00"),
        ("208", "RATEI PASSIVI", "300,00"),
        ("209", "RISCONTI PASSIVI", "250,00"),
        ("210", "RISERVE", "6.000,00"),
    ]
    y = 80
    for code, desc, amt in right_rows:
        page.insert_text((600, y), code, fontsize=10)
        page.insert_text((640, y), desc, fontsize=10)
        page.insert_text((800, y), amt, fontsize=10)
        y += 20

    doc.save(path)
    doc.close()


def test_isolated_second_amount_does_not_block_repair(tmp_path):
    path = tmp_path / "isolated_second_amount.pdf"
    _build_isolated_second_amount(str(path))

    rows = collect_source_rows(str(path))

    sides = {r.side for r in rows}
    assert sides == {"L", "R"}
    # No row fuses text from two DIFFERENT accounts (the original Task-12
    # defect): every row mentions at most one of the declared descriptions.
    labels = ["CASSA", "BANCA C/C", "CREDITI CLIENTI", "MAGAZZINO", "CREDITI DIVERSI",
              "RATEI ATTIVI", "RISCONTI ATTIVI", "ALTRI CREDITI", "TITOLI", "PARTECIPAZIONI",
              "FORNITORI", "DEBITI TRIBUTARI", "PATRIMONIO NETTO", "FONDO TFR",
              "DEBITI PREVIDENZIALI", "ALTRI DEBITI", "RATEI PASSIVI", "RISCONTI PASSIVI",
              "RISERVE"]
    for r in rows:
        hits = [label for label in labels if label in r.text]
        assert len(hits) <= 1, (r.text, hits)
    # The nine untouched rows on each side repair correctly.
    assert _by_code(rows, "102").amounts == (D("1100.45"),)
    assert _by_code(rows, "103").amounts == (D("9500.00"),)
    assert _by_code(rows, "110").amounts == (D("5000.00"),)
    assert _by_code(rows, "201").amounts == (D("5400.00"),)
    assert _by_code(rows, "206").amounts == (D("700.00"),)
    assert _by_code(rows, "210").amounts == (D("6000.00"),)
    # The one row with a genuine second amount still keeps its own identity
    # (code "101", only "CASSA" in its text) — the reconstruction cannot
    # represent two amounts per row, so which of the two it keeps is not
    # asserted here, only that it does not corrupt any other row.
    cassa_row = _by_code(rows, "101")
    assert cassa_row.side == "L" and "CASSA" in cassa_row.text
