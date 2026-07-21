"""Deterministic fallback for clean IV-CEE legal statements.

This parser deliberately covers only the regular, source-backed layout where:

* ``Stato patrimoniale attivo`` and ``Stato patrimoniale passivo`` are printed;
* current/prior date columns have stable PDF coordinates, or the statement has one
  explicit value column;
* every IV-CEE section closes with its own displayed subtotal; and
* ``Totale attivo`` and ``Totale passivo`` are both explicit.

It never fills a balance difference.  A column is returned only when the printed
immobilizzazioni, attivo-circolante, patrimonio-netto and debiti cross-foots all
reconcile to the two displayed side totals.  Otherwise the parser returns ``None``
and the caller retains the normal extraction/review path.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

import fitz


_AMOUNT_RE = re.compile(r"^\(?-?\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?\)?-?$")
_DATE_RE = re.compile(r"\d{2}/\d{2}/20\d{2}")
_TOL = Decimal("2")


def _amount(token: str) -> Optional[Decimal]:
    token = token.strip()
    if not token or not _AMOUNT_RE.fullmatch(token):
        return None
    negative = (
        (token.startswith("(") and token.endswith(")"))
        or token.startswith("-")
        or token.endswith("-")
    )
    compact = token.strip("()").strip("-").replace(".", "").replace(",", ".")
    if not compact:
        return None
    try:
        value = Decimal(compact)
    except Exception:
        return None
    return -value if negative else value


def _normalise(value: str) -> str:
    value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", value).strip()


@dataclass(frozen=True)
class _Row:
    page: int
    y: float
    label: str
    values: Tuple[Optional[Decimal], Optional[Decimal]]

    def value(self, column: int) -> Optional[Decimal]:
        return self.values[column]


def _column_centres(document: fitz.Document) -> Optional[Tuple[float, float]]:
    candidates: List[Tuple[float, float]] = []
    for page in document:
        date_words = [
            word
            for word in page.get_text("words", sort=True)
            if _DATE_RE.fullmatch(str(word[4]).strip())
        ]
        for first in date_words:
            peers = [
                second
                for second in date_words
                if float(second[0]) > float(first[0]) + 25
                and abs(float(second[1]) - float(first[1])) <= 1.5
            ]
            if not peers:
                continue
            second = min(peers, key=lambda word: float(word[0]))
            centres = (
                (float(first[0]) + float(first[2])) / 2,
                (float(second[0]) + float(second[2])) / 2,
            )
            if centres[0] > 300 and centres[1] - centres[0] >= 25:
                candidates.append(centres)
    return max(candidates, key=lambda pair: pair[0]) if candidates else None


def has_comparative_ivcee_columns(file_path: str) -> bool:
    """Return ``True`` only when two side-by-side date columns are proven.

    Infrannual legal statements are often intentionally monocolumn.  Callers use this
    source-layout check to avoid forcing those files through the two-year LLM prompt.
    """
    try:
        document = fitz.open(file_path)
    except Exception:
        return False
    try:
        return _column_centres(document) is not None
    finally:
        document.close()


def _physical_rows(document: fitz.Document, centres: Tuple[float, float]) -> List[_Row]:
    current_x, prior_x = centres
    column_cutoff = (current_x + prior_x) / 2
    rows: List[_Row] = []
    for page in document:
        groups: List[List[Tuple]] = []
        for word in sorted(
            page.get_text("words", sort=True),
            key=lambda item: (float(item[1]), float(item[0])),
        ):
            if not groups or abs(float(word[1]) - float(groups[-1][0][1])) > 1.5:
                groups.append([word])
            else:
                groups[-1].append(word)

        for group in groups:
            values: List[Optional[Decimal]] = [None, None]
            label_words: List[Tuple] = []
            for word in sorted(group, key=lambda item: float(item[0])):
                token = str(word[4]).strip()
                parsed = _amount(token)
                centre_x = (float(word[0]) + float(word[2])) / 2
                column = 0 if centre_x < column_cutoff else 1
                # A legal amount is right-aligned to one of the two proven date
                # columns.  Continuation pages may shift the current column left
                # while retaining the same right edge for the prior column; the
                # left/right ordering remains invariant. Numeric item labels
                # (``1)``, ``5 bis``) sit well left of x=300.
                if parsed is not None and centre_x > 300:
                    values[column] = parsed
                else:
                    label_words.append(word)
            label = _normalise(" ".join(str(word[4]) for word in label_words))
            rows.append(
                _Row(
                    page=page.number,
                    y=float(group[0][1]),
                    label=label,
                    values=(values[0], values[1]),
                )
            )
    return rows


def _single_column_rows(document: fitz.Document) -> List[_Row]:
    """Read a clean one-value-column legal table from its physical PDF rows."""
    rows: List[_Row] = []
    for page in document:
        groups: List[List[Tuple]] = []
        for word in sorted(
            page.get_text("words", sort=True),
            key=lambda item: (float(item[1]), float(item[0])),
        ):
            if not groups or abs(float(word[1]) - float(groups[-1][0][1])) > 1.5:
                groups.append([word])
            else:
                groups[-1].append(word)

        for group in groups:
            value: Optional[Decimal] = None
            label_words: List[Tuple] = []
            for word in sorted(group, key=lambda item: float(item[0])):
                token = str(word[4]).strip()
                parsed = _amount(token)
                centre_x = (float(word[0]) + float(word[2])) / 2
                if parsed is not None and centre_x > 300:
                    value = parsed
                else:
                    label_words.append(word)
            rows.append(
                _Row(
                    page=page.number,
                    y=float(group[0][1]),
                    label=_normalise(" ".join(str(word[4]) for word in label_words)),
                    values=(value, None),
                )
            )
    return rows


def _find(
    rows: Sequence[_Row],
    *terms: str,
    start: int = 0,
    end: Optional[int] = None,
) -> int:
    normalised_terms = tuple(_normalise(term) for term in terms)
    for index in range(start, len(rows) if end is None else end):
        if all(term in rows[index].label for term in normalised_terms):
            return index
    raise ValueError(f"IV-CEE source label not found: {terms}")


def _find_re(
    rows: Sequence[_Row],
    pattern: str,
    start: int = 0,
    end: Optional[int] = None,
) -> int:
    regex = re.compile(pattern)
    for index in range(start, len(rows) if end is None else end):
        if regex.match(rows[index].label):
            return index
    raise ValueError(f"IV-CEE source label not found: {pattern}")


def _value_at(rows: Sequence[_Row], index: int, column: int) -> Decimal:
    value = rows[index].value(column)
    if value is None:
        raise ValueError(f"IV-CEE source amount missing at {rows[index].label!r}")
    return value


def _last_unlabelled(
    rows: Sequence[_Row], start: int, end: int, column: int
) -> Decimal:
    candidates = [
        row.value(column)
        for row in rows[start + 1:end]
        if not row.label and row.value(column) is not None
    ]
    if not candidates:
        raise ValueError("IV-CEE source subtotal missing")
    return candidates[-1]  # printed closing subtotal for the legal section


def _block_value(
    rows: Sequence[_Row], start: int, end: int, column: int
) -> Decimal:
    """Displayed item value: closing subtotal, direct row value, or explicit blank."""
    candidates = [
        row.value(column)
        for row in rows[start + 1:end]
        if not row.label and row.value(column) is not None
    ]
    if candidates:
        return candidates[-1]
    return rows[start].value(column) or Decimal("0")


def _sum_maturity(
    rows: Sequence[_Row], start: int, end: int, column: int, maturity: str
) -> Decimal:
    marker = _normalise(maturity)
    return sum(
        (
            row.value(column)
            for row in rows[start + 1:end]
            if marker in row.label and row.value(column) is not None
        ),
        Decimal("0"),
    )


def _close(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= _TOL


def _parse_column(rows: Sequence[_Row], column: int) -> Optional[Dict[str, Decimal]]:
    """Return one source column only after every independent cross-foot passes."""
    try:
        sp_att = _find(rows, "stato patrimoniale attivo")
        sp_pas = _find(rows, "stato patrimoniale passivo", start=sp_att + 1)
        total_pas_i = _find(rows, "totale passivo", start=sp_pas + 1)
        asset_rows = rows[sp_att:sp_pas]
        pass_rows = rows[sp_pas:total_pas_i + 1]

        # --- Attivo ---------------------------------------------------------
        b_imm = _find(asset_rows, "b) immobilizzazioni")
        imm_i = _find(asset_rows, "i. immateriali", start=b_imm + 1)
        imm_ii = _find(asset_rows, "ii. materiali", start=imm_i + 1)
        imm_iii = _find(asset_rows, "iii. finanziarie", start=imm_ii + 1)
        total_imm_i = _find(asset_rows, "totale immobilizzazioni", start=imm_iii + 1)

        c_att = _find(asset_rows, "c) attivo circolante", start=total_imm_i + 1)
        rim_i = _find(asset_rows, "i. rimanenze", start=c_att + 1)
        cred_i = _find(asset_rows, "ii. crediti", start=rim_i + 1)
        fin_i = _find(asset_rows, "iii. attivita finanziarie", start=cred_i + 1)
        liq_i = _find(asset_rows, "iv. disponibilita liquide", start=fin_i + 1)
        total_c_i = _find(asset_rows, "totale attivo circolante", start=liq_i + 1)
        ratei_att_i = _find(asset_rows, "d) ratei e risconti", start=total_c_i + 1)
        total_att_i = _find(asset_rows, "totale attivo", start=ratei_att_i + 1)

        sp01_i = _find(asset_rows, "a) crediti verso soci", start=0, end=b_imm)
        sp01 = asset_rows[sp01_i].value(column) or Decimal("0")
        sp02 = _last_unlabelled(asset_rows, imm_i, imm_ii, column)
        sp03 = _last_unlabelled(asset_rows, imm_ii, imm_iii, column)
        sp04 = _last_unlabelled(asset_rows, imm_iii, total_imm_i, column)
        total_imm = _value_at(asset_rows, total_imm_i, column)

        sp05 = _last_unlabelled(asset_rows, rim_i, cred_i, column)
        sp06 = _sum_maturity(asset_rows, cred_i, fin_i, column, "- entro l'esercizio")
        sp07 = _sum_maturity(asset_rows, cred_i, fin_i, column, "- oltre l'esercizio")
        total_crediti = _last_unlabelled(asset_rows, cred_i, fin_i, column)
        sp08 = _last_unlabelled(asset_rows, fin_i, liq_i, column)
        sp09 = _last_unlabelled(asset_rows, liq_i, total_c_i, column)
        total_c = _value_at(asset_rows, total_c_i, column)
        sp10 = _value_at(asset_rows, ratei_att_i, column)
        total_att = _value_at(asset_rows, total_att_i, column)

        # --- Passivo --------------------------------------------------------
        pn_i = _find(pass_rows, "a) patrimonio netto")
        capitale_i = _find(pass_rows, "i. capitale", start=pn_i + 1)
        utile_i = _find(pass_rows, "ix. utile", start=capitale_i + 1)
        try:
            perdita_i = _find(pass_rows, "ix. perdita", start=utile_i + 1)
        except ValueError:
            perdita_i = -1
        total_pn_i = _find(pass_rows, "totale patrimonio netto", start=utile_i + 1)
        fondi_i = _find(pass_rows, "totale fondi per rischi e oneri", start=total_pn_i + 1)
        tfr_i = _find(pass_rows, "c) trattamento di fine rapporto", start=fondi_i + 1)
        debiti_i = _find(pass_rows, "d) debiti", start=tfr_i + 1)
        ratei_pas_i = _find(pass_rows, "e) ratei e risconti", start=debiti_i + 1)
        total_deb_i = _find(pass_rows, "totale debiti", start=debiti_i + 1, end=ratei_pas_i)
        total_pass_i = _find(pass_rows, "totale passivo", start=ratei_pas_i + 1)

        sp11 = _value_at(pass_rows, capitale_i, column)
        utile = pass_rows[utile_i].value(column) or Decimal("0")
        perdita = (
            abs(pass_rows[perdita_i].value(column) or Decimal("0"))
            if perdita_i >= 0
            else Decimal("0")
        )
        sp13 = utile - perdita
        total_pn = _value_at(pass_rows, total_pn_i, column)
        # Source definition A.II..VIII/X: the displayed PN total less the two
        # separately printed legal fields, capitale and current-year result.
        sp12 = total_pn - sp11 - sp13
        sp14 = _value_at(pass_rows, fondi_i, column)
        sp15 = _value_at(pass_rows, tfr_i, column)
        sp16 = _sum_maturity(pass_rows, debiti_i, ratei_pas_i, column, "- entro l'esercizio")
        sp17 = _sum_maturity(pass_rows, debiti_i, ratei_pas_i, column, "- oltre l'esercizio")
        total_deb = _value_at(pass_rows, total_deb_i, column)
        sp18 = _value_at(pass_rows, ratei_pas_i, column)
        total_pass = _value_at(pass_rows, total_pass_i, column)

        # Independent source controls.  No balance difference is allocated.
        checks = (
            _close(sp02 + sp03 + sp04, total_imm),
            _close(sp06 + sp07, total_crediti),
            _close(sp05 + sp06 + sp07 + sp08 + sp09, total_c),
            _close(sp01 + sp02 + sp03 + sp04 + sp05 + sp06 + sp07 + sp08 + sp09 + sp10,
                   total_att),
            _close(sp11 + sp12 + sp13, total_pn),
            _close(sp16 + sp17, total_deb),
            _close(sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18,
                   total_pass),
            _close(total_att, total_pass),
        )
        if not all(checks):
            return None

        return {
            "sp01_crediti_soci": sp01,
            "sp02_immob_immateriali": sp02,
            "sp03_immob_materiali": sp03,
            "sp04_immob_finanziarie": sp04,
            "sp05_rimanenze": sp05,
            "sp06_crediti_breve": sp06,
            "sp07_crediti_lungo": sp07,
            "sp08_attivita_finanziarie": sp08,
            "sp09_disponibilita_liquide": sp09,
            "sp10_ratei_risconti_attivi": sp10,
            "sp11_capitale": sp11,
            "sp12_riserve": sp12,
            "sp13_utile_perdita": sp13,
            "sp14_fondi_rischi": sp14,
            "sp15_tfr": sp15,
            "sp16_debiti_breve": sp16,
            "sp17_debiti_lungo": sp17,
            "sp18_ratei_risconti_passivi": sp18,
            "totale_attivo": total_att,
            "totale_passivo": total_pass,
            "totale_crediti": total_crediti,
            "totale_debiti": total_deb,
            "_source_standard_ivcee": Decimal("1"),
        }
    except (ValueError, IndexError):
        return None


def _direct_value(
    rows: Sequence[_Row], *terms: str, start: int = 0, end: Optional[int] = None
) -> Decimal:
    """Value printed on the same physical row as a compact-statement label."""
    return _value_at(rows, _find(rows, *terms, start=start, end=end), 0)


def _direct_value_re(
    rows: Sequence[_Row], pattern: str, start: int = 0, end: Optional[int] = None
) -> Decimal:
    return _value_at(rows, _find_re(rows, pattern, start=start, end=end), 0)


def _optional_direct_value_re(
    rows: Sequence[_Row], pattern: str, start: int, end: int
) -> Decimal:
    try:
        return _direct_value_re(rows, pattern, start=start, end=end)
    except ValueError:
        return Decimal("0")


def _sum_printed_values(rows: Sequence[_Row], start: int, end: int) -> Decimal:
    return sum(
        (
            row.value(0)
            for row in rows[start:end]
            if row.value(0) is not None and not row.label.startswith("totale ")
        ),
        Decimal("0"),
    )


def _parse_compact_balance(rows: Sequence[_Row]) -> Optional[Dict[str, Decimal]]:
    """Parse a source-cross-footed abbreviated IV-CEE statement with one value column.

    The maturity of a combined ``Debiti (entro/oltre)`` total is not inventable from
    the source.  As in the legacy table mapper, that aggregate is stored in the short-
    term bucket and explicitly marked as source-unsplit for downstream review.
    """
    try:
        sp_att = _find(rows, "stato patrimoniale", "attivo")
        sp_pas = _find(rows, "stato patrimoniale", "passivo", start=sp_att + 1)
        total_pas_i = _find(rows, "totale passivo", start=sp_pas + 1)
        asset_rows = rows[sp_att:sp_pas]
        pass_rows = rows[sp_pas:total_pas_i + 1]

        immat_i = _find(asset_rows, "i - immobilizzazioni immateriali")
        mat_i = _find(asset_rows, "ii - immobilizzazioni materiali", start=immat_i + 1)
        fin_imm_i = _find(asset_rows, "iii - immobilizzazioni finanziarie", start=mat_i + 1)
        total_imm_i = _find(asset_rows, "totale immobilizzazioni (b)", start=fin_imm_i + 1)
        rim_i = _find(asset_rows, "i - rimanenze", start=total_imm_i + 1)
        cred_i = _find(asset_rows, "ii - crediti", start=rim_i + 1)
        fin_att_i = _find(asset_rows, "iii - attivita finanziarie", start=cred_i + 1)
        liq_i = _find(asset_rows, "iv - disponibilita liquide", start=fin_att_i + 1)
        total_c_i = _find(asset_rows, "totale attivo circolante", start=liq_i + 1)

        sp01 = _direct_value(asset_rows, "a) crediti verso soci")
        sp02 = _direct_value(asset_rows, "totale immobilizzazioni immateriali")
        sp03 = _direct_value(asset_rows, "totale immobilizzazioni materiali")
        sp04 = _direct_value(asset_rows, "iii", "immobilizzazioni finanziarie")
        total_imm = _direct_value(asset_rows, "totale immobilizzazioni (b)")
        sp05 = _direct_value(asset_rows, "totale rimanenze")
        sp06 = _direct_value(asset_rows, "totale crediti")
        sp07 = Decimal("0")
        sp08 = _direct_value(asset_rows, "iii", "attivita finanziarie non immobilizzate")
        sp09 = _direct_value(asset_rows, "depositi bancari")
        total_c = _direct_value(asset_rows, "totale attivo circolante")
        sp10 = _direct_value(asset_rows, "d) ratei e risconti attivi")
        total_att = _direct_value_re(asset_rows, r"^totale attivo(?:\s*\(|$)")

        sp02b = _optional_direct_value_re(
            asset_rows, r"^2\) costi di sviluppo", immat_i + 1, mat_i
        )
        sp02c = _optional_direct_value_re(
            asset_rows, r"^3\) diritti di brevetto", immat_i + 1, mat_i
        )
        sp02g = sp02 - sp02b - sp02c
        sp03a = _optional_direct_value_re(
            asset_rows, r"^1\) terreni e fabbricati", mat_i + 1, fin_imm_i
        )
        sp03b = _optional_direct_value_re(
            asset_rows, r"^2\) impianti e macchinario", mat_i + 1, fin_imm_i
        )
        sp03c = _optional_direct_value_re(
            asset_rows, r"^3\) attrezzature", mat_i + 1, fin_imm_i
        )
        sp03d = _optional_direct_value_re(
            asset_rows, r"^4\) altri beni", mat_i + 1, fin_imm_i
        )
        sp03e = sp03 - sp03a - sp03b - sp03c - sp03d
        sp05a = _optional_direct_value_re(
            asset_rows, r"^1\) materie prime", rim_i + 1, cred_i
        )
        sp05b = _optional_direct_value_re(
            asset_rows, r"^2\) prodotti in corso", rim_i + 1, cred_i
        )
        sp05c = _optional_direct_value_re(
            asset_rows, r"^3\) lavori in corso", rim_i + 1, cred_i
        )
        sp05d = _optional_direct_value_re(
            asset_rows, r"^4\) prodotti finiti", rim_i + 1, cred_i
        )
        sp05e = sp05 - sp05a - sp05b - sp05c - sp05d
        sp06a = _optional_direct_value_re(
            asset_rows, r"^1\) verso clienti", cred_i + 1, fin_att_i
        )
        sp06e = _optional_direct_value_re(
            asset_rows, r"^4-bis\) crediti tributari", cred_i + 1, fin_att_i
        )
        sp06g = sp06 - sp06a - sp06e

        pn_i = _find(pass_rows, "a) patrimonio netto")
        capitale_i = _find(pass_rows, "i - capitale", start=pn_i + 1)
        result_i = _find(pass_rows, "ix - utile", start=capitale_i + 1)
        total_pn_i = _find(pass_rows, "totale patrimonio netto", start=result_i + 1)
        fondi_i = _find(pass_rows, "b) fondi per rischi", start=total_pn_i + 1)
        tfr_i = _find(pass_rows, "c) trattamento di fine rapporto", start=fondi_i + 1)
        debiti_i = _find(pass_rows, "d) debiti", start=tfr_i + 1)
        total_deb_i = _find(pass_rows, "totale debiti", start=debiti_i + 1)
        ratei_pas_i = _find(pass_rows, "e) ratei e risconti passivi", start=total_deb_i + 1)
        total_pass_i = _find(pass_rows, "totale passivo", start=ratei_pas_i + 1)

        sp11 = _value_at(pass_rows, capitale_i, 0)
        sp13 = _value_at(pass_rows, result_i, 0)
        total_pn = _value_at(pass_rows, total_pn_i, 0)
        printed_reserves = _sum_printed_values(pass_rows, capitale_i + 1, result_i)
        sp12 = total_pn - sp11 - sp13
        sp14 = _value_at(pass_rows, fondi_i, 0)
        sp15 = _value_at(pass_rows, tfr_i, 0)
        total_deb = _value_at(pass_rows, total_deb_i, 0)
        printed_debts = _sum_printed_values(pass_rows, debiti_i + 1, total_deb_i)
        sp16 = total_deb
        sp17 = Decimal("0")
        sp18 = _value_at(pass_rows, ratei_pas_i, 0)
        total_pass = _value_at(pass_rows, total_pass_i, 0)

        sp12c = _optional_direct_value_re(
            pass_rows, r"^iv\b.*riserva legale", capitale_i + 1, result_i
        )
        sp12e = _optional_direct_value_re(
            pass_rows, r"^(?:vi|vii)\b.*altre riserve", capitale_i + 1, result_i
        )
        sp12g = _optional_direct_value_re(
            pass_rows, r"^viii\b.*utili .*portati", capitale_i + 1, result_i
        )
        sp16a = _optional_direct_value_re(
            pass_rows, r"^4\) debiti verso banche", debiti_i + 1, total_deb_i
        )
        sp16b = _optional_direct_value_re(
            pass_rows, r"^5\) debiti verso altri finanziatori", debiti_i + 1, total_deb_i
        )
        sp16d = _optional_direct_value_re(
            pass_rows, r"^7\) debiti verso fornitori", debiti_i + 1, total_deb_i
        )
        sp16e = _optional_direct_value_re(
            pass_rows, r"^12\) debiti tributari", debiti_i + 1, total_deb_i
        )
        sp16f = _optional_direct_value_re(
            pass_rows, r"^13\) debiti verso istituti", debiti_i + 1, total_deb_i
        )
        sp16g = sp16 - sp16a - sp16b - sp16d - sp16e - sp16f

        checks = (
            _close(sp02 + sp03 + sp04, total_imm),
            _close(sp05 + sp06 + sp07 + sp08 + sp09, total_c),
            _close(
                sp01 + sp02 + sp03 + sp04 + sp05 + sp06 + sp07 + sp08 + sp09 + sp10,
                total_att,
            ),
            _close(printed_reserves, sp12),
            _close(sp11 + sp12 + sp13, total_pn),
            _close(printed_debts, total_deb),
            _close(sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18, total_pass),
            _close(total_att, total_pass),
        )
        if not all(checks):
            return None

        return {
            "sp01_crediti_soci": sp01,
            "sp02_immob_immateriali": sp02,
            "sp02b_costi_sviluppo": sp02b,
            "sp02c_brevetti": sp02c,
            "sp02g_altre_immob_imm": sp02g,
            "sp03_immob_materiali": sp03,
            "sp03a_terreni_fabbricati": sp03a,
            "sp03b_impianti_macchinari": sp03b,
            "sp03c_attrezzature": sp03c,
            "sp03d_altri_beni": sp03d,
            "sp03e_immob_in_corso": sp03e,
            "sp04_immob_finanziarie": sp04,
            "sp05_rimanenze": sp05,
            "sp05a_materie_prime": sp05a,
            "sp05b_prodotti_in_corso": sp05b,
            "sp05c_lavori_in_corso": sp05c,
            "sp05d_prodotti_finiti": sp05d,
            "sp05e_acconti": sp05e,
            "sp06_crediti_breve": sp06,
            "sp06a_crediti_clienti_breve": sp06a,
            "sp06e_crediti_tributari_breve": sp06e,
            "sp06g_crediti_altri_breve": sp06g,
            "sp07_crediti_lungo": sp07,
            "sp08_attivita_finanziarie": sp08,
            "sp09_disponibilita_liquide": sp09,
            "sp10_ratei_risconti_attivi": sp10,
            "sp11_capitale": sp11,
            "sp12_riserve": sp12,
            "sp12c_riserva_legale": sp12c,
            "sp12e_altre_riserve": sp12e,
            "sp12g_utili_perdite_portati": sp12g,
            "sp13_utile_perdita": sp13,
            "sp14_fondi_rischi": sp14,
            "sp15_tfr": sp15,
            "sp16_debiti_breve": sp16,
            "sp16a_debiti_banche_breve": sp16a,
            "sp16b_debiti_altri_finanz_breve": sp16b,
            "sp16d_debiti_fornitori_breve": sp16d,
            "sp16e_debiti_tributari_breve": sp16e,
            "sp16f_debiti_previdenza_breve": sp16f,
            "sp16g_altri_debiti_breve": sp16g,
            "sp17_debiti_lungo": sp17,
            "sp18_ratei_risconti_passivi": sp18,
            "totale_attivo": total_att,
            "totale_passivo": total_pass,
            "totale_crediti": sp06 + sp07,
            "totale_debiti": total_deb,
            "_source_standard_ivcee": Decimal("1"),
            "_source_maturity_unspecified": Decimal("1"),
        }
    except (ValueError, IndexError):
        return None


def _parse_income_column(
    rows: Sequence[_Row], column: int
) -> Optional[Dict[str, Decimal]]:
    """Parse and independently cross-foot one standard legal CE column."""
    try:
        ce_start = _find(rows, "conto economico")
        ce_rows = rows[ce_start:]

        a_i = _find_re(ce_rows, r"^a\) valore della produzione")
        a1 = _find_re(ce_rows, r"^1\) ricavi", start=a_i + 1)
        a2 = _find_re(ce_rows, r"^2\) variazione", start=a1 + 1)
        a3 = _find_re(ce_rows, r"^3\) variazioni dei lavori", start=a2 + 1)
        a4 = _find_re(ce_rows, r"^4\) incrementi", start=a3 + 1)
        a5 = _find_re(ce_rows, r"^5\) altri ricavi", start=a4 + 1)
        total_a = _find(ce_rows, "totale valore della produzione", start=a5 + 1)

        b_i = _find_re(ce_rows, r"^b\) costi della produzione", start=total_a + 1)
        b6 = _find_re(ce_rows, r"^6\) per materie", start=b_i + 1)
        b7 = _find_re(ce_rows, r"^7\) per servizi", start=b6 + 1)
        b8 = _find_re(ce_rows, r"^8\) per godimento", start=b7 + 1)
        b9 = _find_re(ce_rows, r"^9\) per il personale", start=b8 + 1)
        b10 = _find_re(ce_rows, r"^10\) ammortamenti", start=b9 + 1)
        b11 = _find_re(ce_rows, r"^11\) variazioni delle rimanenze", start=b10 + 1)
        b12 = _find_re(ce_rows, r"^12\) accantonamento", start=b11 + 1)
        b13 = _find_re(ce_rows, r"^13\) altri accantonamenti", start=b12 + 1)
        b14 = _find_re(ce_rows, r"^14\) oneri diversi", start=b13 + 1)
        total_b = _find(ce_rows, "totale costi della produzione", start=b14 + 1)
        difference_i = _find(
            ce_rows, "differenza tra valore e costi", start=total_b + 1
        )

        c_i = _find_re(ce_rows, r"^c\) proventi e oneri finanziari", start=difference_i + 1)
        c15 = _find_re(ce_rows, r"^15\) proventi da partecipazioni", start=c_i + 1)
        c16 = _find_re(ce_rows, r"^16\) altri proventi finanziari", start=c15 + 1)
        c17 = _find_re(ce_rows, r"^17\) interessi e altri oneri", start=c16 + 1)
        c17b = _find_re(ce_rows, r"^17 bis\) utili e perdite", start=c17 + 1)
        total_c = _find(ce_rows, "totale proventi e oneri finanziari", start=c17b + 1)

        d_i = _find_re(ce_rows, r"^d\) rettifiche di valore", start=total_c + 1)
        total_d = _find(
            ce_rows,
            "totale rettifiche di valore di attivita e passivita finanziarie",
            start=d_i + 1,
        )
        pretax_i = _find(ce_rows, "risultato prima delle imposte", start=total_d + 1)
        tax_i = _find_re(ce_rows, r"^20\) imposte sul reddito", start=pretax_i + 1)
        result_i = _find_re(ce_rows, r"^21\) utile \(perdita\)", start=tax_i + 1)

        ce01 = _block_value(ce_rows, a1, a2, column)
        ce02 = _block_value(ce_rows, a2, a3, column)
        # A.3 is not represented in the application schema; it must be zero for
        # this strict fallback, otherwise declining is safer than losing a value.
        a3_value = _block_value(ce_rows, a3, a4, column)
        ce03 = _block_value(ce_rows, a4, a5, column)
        ce04 = _block_value(ce_rows, a5, total_a, column)
        declared_a = _value_at(ce_rows, total_a, column)

        ce05 = _block_value(ce_rows, b6, b7, column)
        ce06 = _block_value(ce_rows, b7, b8, column)
        ce07 = _block_value(ce_rows, b8, b9, column)
        ce08 = _block_value(ce_rows, b9, b10, column)
        ce09 = _block_value(ce_rows, b10, b11, column)
        ce10 = _block_value(ce_rows, b11, b12, column)
        ce11 = _block_value(ce_rows, b12, b13, column)
        ce11b = _block_value(ce_rows, b13, b14, column)
        ce12 = _block_value(ce_rows, b14, total_b, column)
        declared_b = _value_at(ce_rows, total_b, column)
        declared_difference = _value_at(ce_rows, difference_i, column)

        ce13 = _block_value(ce_rows, c15, c16, column)
        ce14 = _block_value(ce_rows, c16, c17, column)
        ce15 = _block_value(ce_rows, c17, c17b, column)
        ce16 = _block_value(ce_rows, c17b, total_c, column)
        declared_c = _value_at(ce_rows, total_c, column)
        ce17 = ce_rows[total_d].value(column) or Decimal("0")
        declared_pretax = _value_at(ce_rows, pretax_i, column)
        ce20 = _block_value(ce_rows, tax_i, result_i, column)
        declared_result = _value_at(ce_rows, result_i, column)

        value_production = ce01 + ce02 + ce03 + ce04
        production_costs = (
            ce05 + ce06 + ce07 + ce08 + ce09 + ce10 + ce11 + ce11b + ce12
        )
        financial = ce13 + ce14 - ce15 + ce16
        pretax = value_production - production_costs + financial + ce17
        result = pretax - ce20
        checks = (
            _close(a3_value, Decimal("0")),
            _close(value_production, declared_a),
            _close(production_costs, declared_b),
            _close(value_production - production_costs, declared_difference),
            _close(financial, declared_c),
            _close(pretax, declared_pretax),
            _close(result, declared_result),
        )
        if not all(checks):
            return None

        return {
            "ce01_ricavi_vendite": ce01,
            "ce02_variazioni_rimanenze": ce02,
            "ce03_lavori_interni": ce03,
            "ce04_altri_ricavi": ce04,
            "ce05_materie_prime": ce05,
            "ce06_servizi": ce06,
            "ce07_godimento_beni": ce07,
            "ce08_costi_personale": ce08,
            "ce09_ammortamenti": ce09,
            "ce10_var_rimanenze_mat_prime": ce10,
            "ce11_accantonamenti": ce11,
            "ce11b_altri_accantonamenti": ce11b,
            "ce12_oneri_diversi": ce12,
            "ce13_proventi_partecipazioni": ce13,
            "ce14_altri_proventi_finanziari": ce14,
            "ce15_oneri_finanziari": ce15,
            "ce16_utili_perdite_cambi": ce16,
            "ce17_rettifiche_attivita_fin": ce17,
            "ce18_proventi_straordinari": Decimal("0"),
            "ce19_oneri_straordinari": Decimal("0"),
            "ce20_imposte": ce20,
            "_source_standard_ivcee": Decimal("1"),
        }
    except (ValueError, IndexError):
        return None


def _parse_compact_income(rows: Sequence[_Row]) -> Optional[Dict[str, Decimal]]:
    """Parse and cross-foot a one-column abbreviated IV-CEE income statement."""
    try:
        ce_start = _find(rows, "conto economico")
        ce_rows = rows[ce_start:]

        a_i = _find_re(ce_rows, r"^a\) valore della produzione")
        total_a_i = _find(ce_rows, "totale valore della produzione", start=a_i + 1)
        b_i = _find_re(ce_rows, r"^b\) costi della produzione", start=total_a_i + 1)
        total_b_i = _find(ce_rows, "totale costi della produzione", start=b_i + 1)
        difference_i = _find(ce_rows, "differenza tra valore e costi", start=total_b_i + 1)
        c_i = _find_re(ce_rows, r"^c\) proventi e oneri finanziari", start=difference_i + 1)
        total_c_i = _find(ce_rows, "totale proventi e oneri finanziari", start=c_i + 1)
        d_i = _find_re(ce_rows, r"^d\) rettifiche di valore", start=total_c_i + 1)
        pretax_i = _find(ce_rows, "risultato prima delle imposte", start=d_i + 1)
        tax_i = _find_re(ce_rows, r"^20\) imposte sul reddito", start=pretax_i + 1)
        result_i = _find_re(ce_rows, r"^21\) utile \(perdita\)", start=tax_i + 1)

        ce01 = _optional_direct_value_re(ce_rows, r"^1\) ricavi", a_i + 1, total_a_i)
        ce02 = _optional_direct_value_re(ce_rows, r"^2\) variazione", a_i + 1, total_a_i)
        a3 = _optional_direct_value_re(
            ce_rows, r"^3\) variazioni? dei lavori", a_i + 1, total_a_i
        )
        ce03 = _optional_direct_value_re(ce_rows, r"^4\) incrementi", a_i + 1, total_a_i)
        ce04 = _optional_direct_value_re(ce_rows, r"^5\) altri ricavi", a_i + 1, total_a_i)
        declared_a = _value_at(ce_rows, total_a_i, 0)

        ce05 = _optional_direct_value_re(ce_rows, r"^6\) per materie", b_i + 1, total_b_i)
        ce06 = _optional_direct_value_re(ce_rows, r"^7\) per servizi", b_i + 1, total_b_i)
        ce07 = _optional_direct_value_re(ce_rows, r"^8\) per godimento", b_i + 1, total_b_i)
        b9_i = _find_re(ce_rows, r"^9\) per il personale", start=b_i + 1, end=total_b_i)
        b10_i = _find_re(ce_rows, r"^10\) ammortamenti", start=b9_i + 1, end=total_b_i)
        ce08 = ce_rows[b9_i].value(0)
        if ce08 is None:
            ce08 = _sum_printed_values(ce_rows, b9_i + 1, b10_i)
        ce08b = _optional_direct_value_re(
            ce_rows, r"^a\) salari", b9_i + 1, b10_i
        )
        ce08c = _optional_direct_value_re(
            ce_rows, r"^b\) oneri sociali", b9_i + 1, b10_i
        )
        ce08a = _optional_direct_value_re(
            ce_rows, r"^c\) trattamento di fine rapporto", b9_i + 1, b10_i
        )
        ce08d = _optional_direct_value_re(
            ce_rows, r"^e\) altri costi", b9_i + 1, b10_i
        )
        ce09 = _value_at(ce_rows, b10_i, 0)
        ce10 = _optional_direct_value_re(
            ce_rows, r"^11\) variazione", b10_i + 1, total_b_i
        )
        ce11 = _optional_direct_value_re(
            ce_rows, r"^12\) accantonament", b10_i + 1, total_b_i
        )
        ce11b = _optional_direct_value_re(
            ce_rows, r"^13\) altri accantonamenti", b10_i + 1, total_b_i
        )
        ce12 = _optional_direct_value_re(
            ce_rows, r"^14\) oneri diversi", b10_i + 1, total_b_i
        )
        declared_b = _value_at(ce_rows, total_b_i, 0)
        declared_difference = _value_at(ce_rows, difference_i, 0)

        ce13 = _optional_direct_value_re(
            ce_rows, r"^15\) proventi da partecipazioni", c_i + 1, total_c_i
        )
        ce14 = _optional_direct_value_re(
            ce_rows, r"^16\) altri proventi finanziari", c_i + 1, total_c_i
        )
        source_oneri = _optional_direct_value_re(
            ce_rows, r"^17\) interessi e altri oneri", c_i + 1, total_c_i
        )
        ce15 = abs(source_oneri)
        ce16 = _optional_direct_value_re(
            ce_rows, r"^17 bis\) utili e perdite", c_i + 1, total_c_i
        )
        declared_c = _value_at(ce_rows, total_c_i, 0)
        ce17 = _value_at(ce_rows, d_i, 0)
        declared_pretax = _value_at(ce_rows, pretax_i, 0)
        ce20 = _value_at(ce_rows, tax_i, 0)
        declared_result = _value_at(ce_rows, result_i, 0)

        value_production = ce01 + ce02 + ce03 + ce04
        production_costs = ce05 + ce06 + ce07 + ce08 + ce09 + ce10 + ce11 + ce11b + ce12
        financial = ce13 + ce14 - ce15 + ce16
        pretax = value_production - production_costs + financial + ce17
        result = pretax - ce20
        checks = (
            _close(a3, Decimal("0")),
            _close(value_production, declared_a),
            _close(ce08a + ce08b + ce08c + ce08d, ce08),
            _close(production_costs, declared_b),
            _close(value_production - production_costs, declared_difference),
            _close(financial, declared_c),
            _close(pretax, declared_pretax),
            _close(result, declared_result),
        )
        if not all(checks):
            return None

        return {
            "ce01_ricavi_vendite": ce01,
            "ce02_variazioni_rimanenze": ce02,
            "ce03_lavori_interni": ce03,
            "ce04_altri_ricavi": ce04,
            "ce05_materie_prime": ce05,
            "ce06_servizi": ce06,
            "ce07_godimento_beni": ce07,
            "ce08_costi_personale": ce08,
            "ce08a_tfr_accrual": ce08a,
            "ce08b_salari_stipendi": ce08b,
            "ce08c_oneri_sociali": ce08c,
            "ce08d_altri_costi_personale": ce08d,
            "ce09_ammortamenti": ce09,
            "ce10_var_rimanenze_mat_prime": ce10,
            "ce11_accantonamenti": ce11,
            "ce11b_altri_accantonamenti": ce11b,
            "ce12_oneri_diversi": ce12,
            "ce13_proventi_partecipazioni": ce13,
            "ce14_altri_proventi_finanziari": ce14,
            "ce15_oneri_finanziari": ce15,
            "ce16_utili_perdite_cambi": ce16,
            "ce17_rettifiche_attivita_fin": ce17,
            "ce18_proventi_straordinari": Decimal("0"),
            "ce19_oneri_straordinari": Decimal("0"),
            "ce20_imposte": ce20,
            "_source_standard_ivcee": Decimal("1"),
        }
    except (ValueError, IndexError):
        return None


def extract_standard_ivcee_balances(
    file_path: str,
) -> Tuple[Optional[Dict[str, Decimal]], Optional[Dict[str, Decimal]]]:
    """Return source-validated (current, prior) balance sheets, or ``None``.

    Comparative layouts retain their two-column parser. Clean abbreviated
    monocolumn layouts use a separate strict parser and intentionally return no prior.
    """
    try:
        document = fitz.open(file_path)
    except Exception:
        return None, None
    try:
        text = "\n".join(page.get_text() for page in document).casefold()
        required = (
            "stato patrimoniale",
            "attivo",
            "passivo",
            "totale attivo",
            "totale passivo",
            "conto economico",
        )
        if not all(marker in text for marker in required):
            return None, None
        centres = _column_centres(document)
        if centres is None:
            return _parse_compact_balance(_single_column_rows(document)), None
        rows = _physical_rows(document, centres)
        return _parse_column(rows, 0), _parse_column(rows, 1)
    finally:
        document.close()


def extract_standard_ivcee_income(
    file_path: str,
) -> Tuple[Optional[Dict[str, Decimal]], Optional[Dict[str, Decimal]]]:
    """Return source-validated (current, prior) income statements, or ``None``."""
    try:
        document = fitz.open(file_path)
    except Exception:
        return None, None
    try:
        centres = _column_centres(document)
        if centres is None:
            return _parse_compact_income(_single_column_rows(document)), None
        rows = _physical_rows(document, centres)
        return _parse_income_column(rows, 0), _parse_income_column(rows, 1)
    finally:
        document.close()


def overlay_standard_ivcee_balance(
    extracted: Dict[str, Decimal], source: Optional[Dict[str, Decimal]]
) -> Dict[str, Decimal]:
    """Overlay only source-validated legal aggregates, preserving LLM details."""
    if not source:
        return dict(extracted)
    result = dict(extracted)
    result.update(source)
    return result
