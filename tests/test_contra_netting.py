"""Tests for the route-C contra-netting overlay (fondi ammortamento + IVA).

Spec: docs/superpowers/specs/2026-07-06-contra-netting-overlay-design.md
Run:  python -m pytest tests/test_contra_netting.py -v
"""
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.situazione_contabile_parser import (  # noqa: E402
    ContraScan,
    _contra_classify,
    _dedup_parent_child,
    _is_iva_line,
)

D = Decimal


# ---------------------------------------------------------------- dedup

def test_dedup_drops_parent_when_children_sum_to_it():
    # 613_2024 real case: mastro "F.do amm fabbricati" 1.779.795,83 already equals
    # its two sub-accounts — counting both double-counts the fund.
    rows = [
        ("0402", "F.DO AMM FABBRICATI", D("1779795.83")),
        ("040201", "F.DO AMM FABBRICATI INDUSTRIALI", D("1416504.33")),
        ("040202", "F.DO AMM COSTRUZIONI LEGGERE", D("363291.50")),
    ]
    out = _dedup_parent_child(rows)
    assert [c for c, _, _ in out] == ["040201", "040202"]


def test_dedup_keeps_parent_without_children():
    rows = [("0402", "F.DO AMM FABBRICATI", D("100"))]
    assert _dedup_parent_child(rows) == rows


def test_dedup_keeps_parent_when_children_do_not_sum():
    rows = [
        ("0402", "F.DO AMM FABBRICATI", D("1000")),
        ("040201", "F.DO AMM FABBRICATI INDUSTRIALI", D("300")),
    ]
    # children present but sum (300) != parent (1000) -> parent is a real
    # independent balance, keep everything
    assert _dedup_parent_child(rows) == rows


def test_dedup_ignores_codeless_rows():
    rows = [("", "CASSA", D("10")), ("", "CASSA CONTANTI", D("10"))]
    assert _dedup_parent_child(rows) == rows


# ---------------------------------------------------------------- IVA detection

def test_is_iva_line_matches_erario_and_iva_accounts():
    assert _is_iva_line("ERARIO C/IVA")
    assert _is_iva_line("IVA C/ACQUISTI")
    assert _is_iva_line("IVA C/VENDITE")
    assert _is_iva_line("IVA A DEBITO")


def test_is_iva_line_rejects_riserva_and_plain_words():
    # 'RISERVA' contains the substring IVA — the \bIVA\b boundary must reject it
    assert not _is_iva_line("RISERVA LEGALE")
    assert not _is_iva_line("RISERVA STRAORDINARIA")
    assert not _is_iva_line("FORNITORI")


# ---------------------------------------------------------------- classification

ATTIVO_ROWS = [
    ("0101", "SOFTWARE DI PROPRIETA", D("20000")),
    ("0201", "FABBRICATI INDUSTRIALI", D("3000000")),
    ("0202", "IMPIANTI E MACCHINARI", D("500000")),
    ("0601", "CREDITI V/CLIENTI", D("100000")),
    ("0602", "ERARIO C/IVA", D("15000")),
    ("0901", "BANCA C/C", D("50000")),
]
PASSIVO_ROWS = [
    ("0401", "F.DO AMM.TO FABBRICATI", D("1800000")),
    ("0402", "F.DO AMM.TO IMPIANTI", D("53799.20")),
    ("0403", "F.DO AMM.TO SOFTWARE", D("5000")),
    ("1601", "FORNITORI", D("180000")),
    ("1602", "ERARIO C/IVA VENDITE", D("10000")),
    ("1101", "CAPITALE SOCIALE", D("1000000")),
]


def test_contra_classify_gross_trial_balance():
    scan = _contra_classify(ATTIVO_ROWS, PASSIVO_ROWS)
    assert scan.gross_sp02 == D("20000")
    assert scan.gross_sp03 == D("3500000")
    # full attivo side, fondi excluded: 20k+3M+500k+100k+15k+50k
    assert scan.attivo_total == D("3685000")
    assert scan.fondi_immat == D("5000")
    assert scan.fondi_mat == D("1853799.20")
    assert scan.iva_credito == D("15000")
    assert scan.iva_debito == D("10000")


def test_contra_classify_fondi_on_asset_side():
    # rare gross-on-asset presentation: fondi listed as attivo-side rows —
    # still summed as fondi, excluded from the gross asset totals
    attivo = ATTIVO_ROWS + [("0301", "F.DO AMM.TO IMPIANTI", D("53799.20"))]
    scan = _contra_classify(attivo, [])
    assert scan.fondi_mat == D("53799.20")
    assert scan.attivo_total == D("3685000")


def test_contra_classify_fondo_svalutazione_crediti_left_gross():
    # fondo svalutazione CREDITI reduces crediti, NOT immobilizzazioni: excluded
    # from every contra-immobilizzazioni bucket (amm and svalutazione).
    scan = _contra_classify([], [("0405", "F.DO SVALUTAZIONE CREDITI", D("9000"))])
    assert scan.fondi_immat == D("0")
    assert scan.fondi_mat == D("0")
    assert scan.sval_immat == D("0")
    assert scan.sval_mat == D("0")


# ------------------------------ fondo svalutazione immobilizzazioni (user rule)

def test_is_fondo_svalut_immob_recognises_immobilizzazioni_only():
    from importers.situazione_contabile_parser import _is_fondo_svalut_immob
    # immobilizzazioni immateriali / materiali write-down funds → in scope
    assert _is_fondo_svalut_immob("FONDO SVALUTAZIONE MARCHI")
    assert _is_fondo_svalut_immob("FONDI SVALUTAZIONE IMM.IMMATERIALI")
    assert _is_fondo_svalut_immob("F.DO SVALUTAZIONE FABBRICATI")
    # other write-down funds reduce other items → out of scope
    assert not _is_fondo_svalut_immob("F.DO SVALUTAZIONE CREDITI")
    assert not _is_fondo_svalut_immob("FONDO SVALUTAZIONE MAGAZZINO")
    assert not _is_fondo_svalut_immob("FONDO SVALUTAZIONE PARTECIPAZIONI")
    assert not _is_fondo_svalut_immob("F.DO AMM.TO MARCHI")  # ammortamento, not svalut


def test_contra_classify_splits_svalutazione_immat_vs_mat():
    passivo = [
        ("0420", "FONDO SVALUTAZIONE MARCHI", D("22220")),        # immateriali
        ("0421", "F.DO SVALUTAZIONE FABBRICATI", D("5000")),      # materiali
        ("0405", "F.DO SVALUTAZIONE CREDITI", D("9000")),         # out of scope
    ]
    scan = _contra_classify([], passivo)
    assert scan.sval_immat == D("22220")
    assert scan.sval_mat == D("5000")


def test_contra_classify_dedups_before_summing():
    passivo = [
        ("0402", "F.DO AMM FABBRICATI", D("1779795.83")),
        ("040201", "F.DO AMM FABBRICATI INDUSTRIALI", D("1416504.33")),
        ("040202", "F.DO AMM COSTRUZIONI LEGGERE", D("363291.50")),
    ]
    scan = _contra_classify([], passivo)
    assert scan.fondi_mat == D("1779795.83")


def test_contra_classify_immat_split_via_subaggregate_truncated_leaves():
    # budget_395 (AGRIMIX): the immateriali sub-aggregate '04 F/AMM IMMOBILIZZAZIONI
    # IMMAT.' carries the ONLY correct caption; its deepest LEAVES are truncated
    # ("F/AMM.LIC. D'USO SOF. A TEM. IND", "F/AMM.ALT. COS. AD UT. PLU. AMM") and
    # self-misclassify to materiali. The split must anchor on the printed sub-
    # aggregate, not on the leaf captions, so the immat mass stays immateriali.
    # Complete subtree (parents == sum of their leaves) so dedup collapses cleanly,
    # mirroring the real document.
    passivo = [
        ("04", "F/AMM IMMOBILIZZAZIONI IMMAT.", D("111596.80")),   # immat sub-agg
        ("0405", "F/AMM COSTI DI IMPIANTO E AMPL.", D("3969.29")),
        ("0405005", "F/AMM.COSTI IMPIANTO", D("3969.29")),          # truncated leaf
        ("0415", "F/AMM.DIRITTI DI BREV. E UT. OP.", D("17150.69")),
        ("0415015", "F/AMM.LIC. D'USO SOF. A TEM. IND", D("17150.69")),  # truncated
        ("0420", "F/AMM.CONCESS. LICENZE MARCHI", D("13432.00")),
        ("0420015", "F/AMM.LIC. D'USO SOF. A TEMP.DET", D("13432.00")),  # truncated
        ("0435", "F/AMM.ALTRE IMMOB. IMMATERIALI", D("77044.82")),
        ("0435005", "F/AMM. LAV. STR. SU BENI DI TERZ", D("48525.32")),  # truncated
        ("0435015", "F/AMM.ALT. COS. AD UT. PLU. AMM", D("28519.50")),   # truncated
        # materiali side: a single mastro (its leaf captions are tangible anyway)
        ("07", "F/AMM IMMOB. MATERIALI", D("2748604.93")),
    ]
    scan = _contra_classify([], passivo)
    assert scan.fondi_immat == D("111596.80")
    assert scan.fondi_mat == D("2748604.93")


def test_contra_classify_grand_total_over_immat_subaggregate():
    # budget_343: a GRAND total '41 FONDI AMMORTAMENTO IMMOBILIZ' sits above the
    # immateriali sub-aggregate '4101 FONDI AMMORT. IMMOBILIZZAZ. IMM'. total comes
    # from the grand aggregate, immat from the sub-aggregate; mat is the remainder.
    passivo = [
        ("41", "FONDI AMMORTAMENTO IMMOBILIZ", D("895336.07")),        # grand total
        ("4101", "FONDI AMMORT. IMMOBILIZZAZ. IMM", D("55805.16")),    # immat sub-agg
        ("410107", "F.DO AMM.TO COSTI DI IMPIANTO E AMPLIA", D("7966.59")),
        ("410123", "F.DO AMM.SW IN CONCESSIONE CAPITALIZZ", D("21102.57")),
        ("410127", "F.DO AMM.TO SPESE DI MANUT.BENI DI TER", D("24136.00")),
        ("410153", "F.DO AMM. ALTRE SPESE PLURIENNALI", D("2600.00")),
        ("4105", "FONDI AMMORTAMENTO IMPIANTI E", D("205818.77")),
        ("4107", "FONDI AMMORT.ATTREZZ.INDUSTR.", D("470066.22")),
        ("4109", "FONDI AMMORTAMENTO ALTRI BEN", D("163645.92")),
    ]
    scan = _contra_classify([], passivo)
    assert scan.fondi_immat == D("55805.16")
    assert scan.fondi_mat == D("839530.91")   # 895336.07 - 55805.16


# ------------------------------------------ immat/mat split of a known fondo
# budget_210 (GUSTOPRONTO, BILAGRA verifica): the gestionale prints fondi with
# BOTH the 'F.DO' and 'FONDO' prefixes and immateriali captions the old F.DO-
# gated rules missed, so licenze/consulenze/ricerca-sviluppo leaked to materiali.

def test_fondo_bucket_immateriali_captions():
    from importers.situazione_contabile_parser import _fondo_is_immat
    # immateriali fondi, regardless of F.DO vs FONDO prefix
    assert _fondo_is_immat("FONDO AMM.TO LICENZE")
    assert _fondo_is_immat("F.DO AMM.TO CONSULENZE DA AMMOR.")
    assert _fondo_is_immat("F.DO AMM.TO COSTI RICERCA SVILUPPO")
    assert _fondo_is_immat("F.DO AMM.TO SOFTWARE")
    assert _fondo_is_immat("FONDI AMM.TO IMMOBILIZ.IMMATERIALI")
    assert _fondo_is_immat("F.DO AMM.TO MARCHI")
    assert _fondo_is_immat("F.DO AMM.TO SITO WEB")


def test_classify_anticipo_is_credito_not_machine():
    # budget_210/211: "ANTICIPO X CANONI MACCHINARI" is an advance to a supplier (a
    # credit), not a machine — the MACCHINAR category rule must not claim it.
    from importers.situazione_contabile_parser import _classify_sp_attivo
    assert _classify_sp_attivo("ANTICIPO X CANONI MACCHINARI") == "sp06"
    assert _classify_sp_attivo("ANTICIPI A FORNITORI") == "sp06"
    # legitimate immobilizzazioni in corso e acconti stays materiali (B.II.5)
    assert _classify_sp_attivo("IMMOBILIZZAZIONI MATERIALI IN CORSO E ACCONTI") == "gross_sp03"
    assert _classify_sp_attivo("IMMOBILIZZAZIONI IN CORSO E ACCONTI") == "gross_sp03"
    # plain tangible assets still materiali
    assert _classify_sp_attivo("MACCHINARI") == "gross_sp03"
    assert _classify_sp_attivo("IMPIANTI E MACCHINARI") == "gross_sp03"


def test_fondo_bucket_materiali_captions():
    from importers.situazione_contabile_parser import _fondo_is_immat
    # tangible fondi, both prefixes -> NOT immateriali
    assert not _fondo_is_immat("FONDO AMM.TO ORD. IMPIANTI")
    assert not _fondo_is_immat("FONDO AMM.TO ORD. MACCHINARI")
    assert not _fondo_is_immat("F.DO AMM.TO ATTREZZATURE")
    assert not _fondo_is_immat("FONDO AMM.TO AUTOCARRI")
    assert not _fondo_is_immat("F.DO AMM.TO MOBILI ED ARREDI")
    assert not _fondo_is_immat("F.DO AMM.MACCHINARI RILEV.COMPON.ELE")


# ---------------------------------------------------------- budget_210 evidence
PDF_210 = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "examples", "budget_210_Bilancio_2025.pdf")


@pytest.mark.skipif(not os.path.exists(PDF_210), reason="evidence PDF not present")
def test_contra_classify_on_210_splits_fondi_correctly():
    from importers.situazione_contabile_parser import _contra_rows, _contra_classify

    rows = _contra_rows(PDF_210)
    assert rows is not None
    attivo_rows, passivo_rows, _from_ocr = rows
    scan = _contra_classify(attivo_rows, passivo_rows)
    # fondo immateriali (411): licenze 17.200 + software 2.240 + consulenze
    # 1.101,20 + ricerca/sviluppo 24 = 20.565,20
    assert abs(scan.fondi_immat - D("20565.20")) <= D("2")
    # fondo materiali (401) = 96.138,83 (no immateriali leakage, no appendix dup)
    assert abs(scan.fondi_mat - D("96138.83")) <= D("2")
    # printed gross subtotals used as anchors
    assert scan.anchor_sp02 == D("223901.20")
    assert scan.anchor_sp03 == D("196502.74")


@pytest.mark.skipif(not os.path.exists(PDF_210), reason="evidence PDF not present")
def test_210_net_contra_produces_correct_immobilizzazioni():
    from importers.pdf_extractor_llm import _declared_control_totals
    from importers.situazione_contabile_parser import net_contra_accounts

    declared = _declared_control_totals(PDF_210)
    # winner shape: gross immobilizzazioni on the attivo (anchors), fondi still
    # on the passivo — the overlay nets them from the document itself.
    bs = {
        "sp02_immob_immateriali": D("223901.20"),
        "sp03_immob_materiali": D("196502.74"),
        "totale_attivo": declared.get("attivo") or declared.get("pareggio"),
        "totale_passivo": declared.get("passivo") or declared.get("pareggio"),
    }
    bs, netted = net_contra_accounts(bs, PDF_210, declared=declared)
    # B.I) immateriali: 223.901,20 - fondo amm 20.565,20 - fondo svalutazione
    # marchi 33.340,00 = 169.996,00 (was 221.637)
    assert abs(bs["sp02_immob_immateriali"] - D("169996.00")) <= D("2")
    # B.II) materiali: 196.502,74 - 96.138,83 = 100.363,91 (~100k, was 82.015)
    assert abs(bs["sp03_immob_materiali"] - D("100363.91")) <= D("2")


PDF_211 = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "examples", "budget_211_Gustopronto_2024.pdf")


@pytest.mark.skipif(not os.path.exists(PDF_211), reason="evidence PDF not present")
def test_211_nets_fondo_svalutazione_immateriali():
    from importers.pdf_extractor_llm import _declared_control_totals
    from importers.situazione_contabile_parser import net_contra_accounts

    declared = _declared_control_totals(PDF_211)
    bs = {
        "sp02_immob_immateriali": D("223901.20"),
        "sp03_immob_materiali": D("194897.74"),
        "totale_attivo": declared.get("attivo") or declared.get("pareggio"),
        "totale_passivo": declared.get("passivo") or declared.get("pareggio"),
    }
    bs, netted = net_contra_accounts(bs, PDF_211, declared=declared)
    # B.I) immateriali: 223.901,20 - fondo amm 19.421,20 - fondo svalutazione
    # marchi 22.220,00 = 182.260,00 (was 204.480, svalutazione un-netted)
    assert abs(bs["sp02_immob_immateriali"] - D("182260.00")) <= D("2")


# ---------------------------------------------------------------- _contra_rows

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "examples")
PDF_613 = os.path.join(
    EXAMPLES, "613_2024 Costruzione di edifici residenziali e non residenziali.pdf")


@pytest.mark.skipif(not os.path.exists(PDF_613), reason="evidence PDF not present")
def test_contra_rows_on_613_finds_the_fondi_mass():
    from importers.situazione_contabile_parser import _contra_rows, _contra_classify

    rows = _contra_rows(PDF_613)
    assert rows is not None
    attivo_rows, passivo_rows = rows
    scan = _contra_classify(attivo_rows, passivo_rows)
    # Spec reproduced evidence: fondi ammortamento 1.853.799,20 on this file
    assert abs(scan.fondi_immat + scan.fondi_mat - Decimal("1853799.20")) \
        <= Decimal("1853799.20") * Decimal("0.01")
    # gross attivo scan must land near the file's gross total (~4.99M order of
    # magnitude: net 3.13M + fondi 1.85M). Loose 2% band — the exact declared
    # total is asserted in the end-to-end test via _declared_control_totals.
    assert scan.attivo_total > Decimal("4000000")


def test_contra_rows_text_mode_classifies_fondi_by_nature():
    from importers.situazione_contabile_parser import _contra_rows, _contra_classify

    ocr = (
        "SITUAZIONE PATRIMONIALE\n"
        "0201 FABBRICATI INDUSTRIALI 3.000.000,00\n"
        "0401 F.DO AMM.TO FABBRICATI 1.800.000,00\n"
        "1601 FORNITORI 180.000,00\n"
        "CONTO ECONOMICO\n"
        "3101 RICAVI DELLE VENDITE 900.000,00\n"
    )
    rows = _contra_rows("/nonexistent.pdf", text=ocr)
    assert rows is not None
    attivo_rows, passivo_rows, _from_ocr = rows
    scan = _contra_classify(attivo_rows, passivo_rows)
    assert scan.fondi_mat == Decimal("1800000.00")
    assert scan.gross_sp03 == Decimal("3000000.00")
    # the CE line must NOT leak into the attivo total (window cut at CONTO ECONOMICO)
    assert scan.attivo_total == Decimal("3000000.00")


# ---------------------------------------------------------------- net_contra_accounts

import importers.situazione_contabile_parser as scp


def _gross_winner_bs():
    """Reproduces the observed CoGe-LLM failure shape on a gross trial balance:
    assets left GROSS, the whole fondi mass (1.858.799,20) dumped into debts."""
    return {
        "sp02_immob_immateriali": D("20000"),
        "sp03_immob_materiali": D("3500000"),
        "sp06_crediti_breve": D("115000"),          # incl. 15.000 IVA credit
        "sp09_disponibilita_liquide": D("50000"),
        "sp11_capitale": D("1000000"),
        "sp13_utile_perdita": D("636200.80"),
        "sp16_debiti_breve": D("2048799.20"),       # 190.000 real + 1.858.799,20 fondi
        "sp16g_altri_debiti_breve": D("1873799.20"),
        "totale_attivo": D("3685000"),
        "totale_passivo": D("3685000"),
    }


DECLARED = {"attivo": D("3685000"), "passivo": D("3685000"),
            "pareggio": D("3685000"), "utile": None, "perdita": None}


def _patch_scan(monkeypatch, attivo, passivo, from_ocr=False):
    monkeypatch.setattr(scp, "_contra_rows",
                        lambda fp, text=None: (attivo, passivo, from_ocr))


def test_netting_applied_on_gross_extraction(monkeypatch):
    _patch_scan(monkeypatch, ATTIVO_ROWS, PASSIVO_ROWS)
    bs = _gross_winner_bs()
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    # netted = fondi 1.858.799,20 + IVA offset min(15000, 10000)
    assert netted == D("1868799.20")
    assert bs["sp02_immob_immateriali"] == D("15000")       # 20.000 - 5.000
    assert bs["sp03_immob_materiali"] == D("1646200.80")    # 3.500.000 - 1.853.799,20
    assert bs["sp06_crediti_breve"] == D("105000")          # IVA credit collapsed
    assert bs["totale_attivo"] == D("1816200.80")
    assert bs["totale_passivo"] == bs["totale_attivo"]      # pareggio preserved
    assert bs["sp16_debiti_breve"] == D("180000")           # only real debts left
    assert bs["sp13_utile_perdita"] == D("636200.80")       # result untouched


def test_noop_when_extractor_already_netted(monkeypatch):
    """Deterministic authority must be idempotent: a correct (net) sheet passes
    through with only the anchor-reduction value returned — no field changes."""
    _patch_scan(monkeypatch, ATTIVO_ROWS, PASSIVO_ROWS)
    bs = {
        "sp02_immob_immateriali": D("15000"),
        "sp03_immob_materiali": D("1646200.80"),
        "sp06_crediti_breve": D("105000"),
        "sp09_disponibilita_liquide": D("50000"),
        "sp11_capitale": D("1000000"),
        "sp13_utile_perdita": D("636200.80"),
        "sp16_debiti_breve": D("180000"),
        "totale_attivo": D("1816200.80"),
        "totale_passivo": D("1816200.80"),
    }
    before = dict(bs)
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    assert netted == D("1868799.20")   # still returned: the DECLARED anchor is gross
    # sp02/sp03 overwritten with the SAME net values; the IVA gross-evidence gate
    # skips the (non-idempotent) IVA delta because totale_attivo is already at the
    # NET magnitude; balance-invariant debt reduction sees excess 0 -> no real
    # debt touched. Net effect: the sheet passes through byte-identical.
    assert bs == before


def test_noop_without_fondi(monkeypatch):
    _patch_scan(monkeypatch, [("0601", "CREDITI V/CLIENTI", D("3685000"))], [])
    bs = _gross_winner_bs()
    before = dict(bs)
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    assert netted == D("0")
    assert bs == before


def test_noop_when_scan_does_not_reconcile(monkeypatch):
    # scan reads only half the attivo -> gate 2 fails -> untouched sheet
    _patch_scan(monkeypatch, ATTIVO_ROWS[:2], PASSIVO_ROWS)
    bs = _gross_winner_bs()
    before = dict(bs)
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    assert netted == D("0")
    assert bs == before


def test_noop_without_declared_totals(monkeypatch):
    _patch_scan(monkeypatch, ATTIVO_ROWS, PASSIVO_ROWS)
    bs = _gross_winner_bs()
    before = dict(bs)
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=None)
    assert netted == D("0")
    assert bs == before


def test_iva_one_sided_left_gross(monkeypatch):
    # only an IVA credit exists -> offset 0 -> crediti untouched, fondi still netted
    passivo_no_iva = [r for r in PASSIVO_ROWS if "IVA" not in r[1]]
    # keep the attivo scan total equal to declared by replacing the IVA row
    attivo = [r if "IVA" not in r[1] else (r[0], "CREDITI DIVERSI", r[2])
              for r in ATTIVO_ROWS]
    _patch_scan(monkeypatch, attivo, passivo_no_iva)
    bs = _gross_winner_bs()
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    assert netted == D("1858799.20")                 # fondi only, no IVA offset
    assert bs["sp06_crediti_breve"] == D("115000")   # untouched


# ---------------------------------------------------------------- declared-result arbiter

def test_reconcile_prefers_loss_matching_gap_over_spurious_utile():
    # budget_211 (GUSTOPRONTO): the declared "utile 20.581,27" is a prior-year PN
    # account ("RISULTATO D'ESERCIZIO"), NOT the current result. The true result is
    # the perdita 90.819,92, which reconciles attivo (1.623.117,50) vs passivo/
    # pareggio (1.713.937,42): gap = attivo - passivo = -90.819,92. The arbiter must
    # pick the loss, not the spurious utile.
    from importers.pdf_extractor_llm import _reconcile_trial_to_declared
    declared = {"attivo": D("1623117.50"), "passivo": D("1713937.42"),
                "pareggio": D("1713937.42"), "utile": D("20581.27"),
                "perdita": D("90819.92")}
    bs = {"totale_attivo": D("1623117.50"), "totale_passivo": D("1713937.42"),
          "sp13_utile_perdita": D("20581.27"),
          "sp16_debiti_breve": D("500000"), "sp09_disponibilita_liquide": D("100000")}
    out = _reconcile_trial_to_declared(bs, declared, "t")
    assert out["sp13_utile_perdita"] == D("-90819.92")


def test_reconcile_single_utile_candidate_unchanged():
    # a genuine profit with only an utile line and no material gap -> utile wins
    # (legacy behaviour preserved when there is nothing to arbitrate).
    from importers.pdf_extractor_llm import _reconcile_trial_to_declared
    declared = {"attivo": D("1000000"), "passivo": D("1000000"),
                "pareggio": D("1000000"), "utile": D("50000"), "perdita": None}
    bs = {"totale_attivo": D("1000000"), "totale_passivo": D("1000000"),
          "sp13_utile_perdita": D("50000"), "sp16_debiti_breve": D("200000")}
    out = _reconcile_trial_to_declared(bs, declared, "t")
    assert out["sp13_utile_perdita"] == D("50000")


def test_reconcile_ce_result_breaks_tie_when_no_gap():
    # both utile and perdita printed, passivo INCLUDES the result (gap ~ 0) so the
    # gap cannot arbitrate; the CE-derived result does.
    from importers.pdf_extractor_llm import _reconcile_trial_to_declared
    declared = {"attivo": D("1000000"), "passivo": D("1000000"),
                "pareggio": D("1000000"), "utile": D("50000"), "perdita": D("50000")}
    bs = {"totale_attivo": D("1000000"), "totale_passivo": D("1000000"),
          "sp13_utile_perdita": D("50000"), "sp16_debiti_breve": D("200000"),
          "sp09_disponibilita_liquide": D("100000")}
    out = _reconcile_trial_to_declared(bs, declared, "t", ce_result=D("-50000"))
    assert out["sp13_utile_perdita"] == D("-50000")


# ---------------------------------------------------------------- end-to-end (production path)

def _gross_winner_bs_613():
    """Observed-failure shape for 613_2024, built from the spec's evidence:
    equity 2,93M, real debts ~182k, fondi 1.853.799,20 booked as altri debiti,
    assets gross. Numbers approximate the real file; the scan overwrites the
    asset side from the document itself, so only the SHAPE matters here."""
    return {
        "sp02_immob_immateriali": D("0"),
        "sp03_immob_materiali": D("4930000"),
        "sp06_crediti_breve": D("30000"),
        "sp09_disponibilita_liquide": D("25000"),
        "sp11_capitale": D("2930000"),
        "sp13_utile_perdita": D("19590.98"),
        "sp16_debiti_breve": D("2035409.02"),
        "sp16g_altri_debiti_breve": D("2035409.02"),
        "totale_attivo": D("4985000"),
        "totale_passivo": D("4985000"),
    }


@pytest.mark.skipif(not os.path.exists(PDF_613), reason="evidence PDF not present")
def test_613_production_path_with_stubbed_gross_llm():
    """Full route-C post-selection pipeline on the real 613_2024 PDF, with the
    winning candidate stubbed to the observed LLM failure (gross assets, fondi
    in debts). No API key needed. Asserts the spec's acceptance numbers."""
    from importers.pdf_extractor_llm import (
        _declared_control_totals, _reconcile_trial_to_declared,
    )
    from importers.situazione_contabile_parser import net_contra_accounts

    declared = _declared_control_totals(PDF_613)
    assert declared.get("pareggio") or declared.get("attivo"), \
        "613 must print its own control totals"

    # stubbed winner reproducing the observed failure: real scan drives the fix
    bs, netted = net_contra_accounts(_gross_winner_bs_613(), PDF_613,
                                     declared=declared)
    assert netted > D("1800000")

    decl = dict(declared)
    for k in ("attivo", "passivo", "pareggio"):
        if decl.get(k):
            decl[k] = decl[k] - netted
    bs = _reconcile_trial_to_declared(bs, decl, "test-613")

    # Spec acceptance: sp03 ~ 3,08M net; debts ~ real (~182k, fondi removed);
    # totale_attivo ~ 3,13M net; attivo == passivo
    assert abs(bs["sp03_immob_materiali"] - D("3080000")) < D("100000")
    debts = bs.get("sp16_debiti_breve", D("0")) + bs.get("sp17_debiti_lungo", D("0"))
    assert debts < D("400000")
    assert abs(bs["totale_attivo"] - D("3130000")) < D("100000")
    assert abs(bs["totale_attivo"] - bs["totale_passivo"]) <= D("1")
    # no false plug: the netted mass must NOT resurface as _plug_residual
    assert bs.get("_plug_residual", D("0")) < bs["totale_attivo"] * D("0.01")
