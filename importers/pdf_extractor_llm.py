"""
PDF Balance Sheet Extractor using PyMuPDF + Claude Haiku 4.5.

Fast alternative to Docling: PyMuPDF extracts text from relevant pages (~100ms),
then Claude Haiku parses IV CEE fields via structured output (~3-5s).
Total: ~5s at ~$0.01/PDF vs Docling's ~133s.
"""

import base64
import json
import os
import logging
import re
import tempfile
import time
from decimal import Decimal
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

import fitz  # PyMuPDF
import pydantic
import anthropic

from config import PDF_LLM_MODEL, PDF_LLM_MAX_TOKENS
from calculations.ce_result import calculate_ce_result

logger = logging.getLogger(__name__)


class PDFImportError(Exception):
    """Exception raised when PDF import fails."""
    pass


# ---------------------------------------------------------------------------
# Pydantic models for structured extraction
# ---------------------------------------------------------------------------

def _coerce_number(v):
    """Coerce an LLM-returned amount to float, tolerating Italian/mangled formats.

    Claude sometimes serialises a numeric field as a STRING using Italian
    thousands/decimal separators ("8.144.680,93") or a mangled hybrid where the
    decimal comma was already turned into a dot but the thousands dots were left
    in ("8.144.680.93"). Plain pydantic float-parsing rejects both, which made a
    whole BalanceSheetExtraction fail validation and the extractor return nothing
    (budget_405). Normalise here so one oddly-formatted field never sinks the
    whole extraction.

    Rules (no comma vs comma):
      - comma present  -> Italian: drop '.', then ',' -> '.'   ("1.234,56" -> 1234.56)
      - >1 dot, no comma -> last 2-digit group is the decimal, others thousands
                            ("8.144.680.93" -> 8144680.93; "1.234.567" -> 1234567)
      - <=1 dot         -> leave as-is (normal float / int)
    Trailing '-' and parentheses denote negatives.
    """
    if v is None or isinstance(v, (int, float, dict, list)):
        return v
    s = str(v).strip()
    if not s:
        return 0
    neg = s.endswith('-') or (s.startswith('(') and s.endswith(')'))
    s = s.strip('()').rstrip('-').strip().replace(' ', '').replace(' ', '')
    if not s:
        return 0
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif s.count('.') > 1:
        head, _, tail = s.rpartition('.')
        s = (head.replace('.', '') + '.' + tail) if len(tail) == 2 else s.replace('.', '')
    try:
        f = float(s)
    except ValueError:
        return 0
    return -f if neg else f


class _ItalianNumberModel(pydantic.BaseModel):
    """Base model whose float fields tolerate Italian/mangled numeric strings."""

    @pydantic.field_validator('*', mode='before')
    @classmethod
    def _coerce_italian_numbers(cls, v):
        return _coerce_number(v)


class BalanceSheetExtraction(_ItalianNumberModel):
    """IV CEE Stato Patrimoniale fields (single year)."""
    sp01_crediti_soci: float = pydantic.Field(0, description="A) Crediti verso soci per versamenti ancora dovuti")
    sp02_immob_immateriali: float = pydantic.Field(0, description="B.I) Immobilizzazioni immateriali")
    sp03_immob_materiali: float = pydantic.Field(0, description="B.II) Immobilizzazioni materiali")
    sp04_immob_finanziarie: float = pydantic.Field(0, description="B.III) Immobilizzazioni finanziarie")
    sp05_rimanenze: float = pydantic.Field(0, description="C.I) Rimanenze")
    sp06_crediti_breve: float = pydantic.Field(0, description="C.II) Crediti esigibili entro l'esercizio successivo")
    sp07_crediti_lungo: float = pydantic.Field(0, description="C.II) Crediti esigibili oltre l'esercizio successivo")
    # Debtor-type breakdown for C.II Crediti per OIC art. 2424 (entro/oltre per group).
    # Must sum to sp06_crediti_breve and sp07_crediti_lungo respectively.
    sp06a_crediti_clienti_breve: float = pydantic.Field(0, description="C.II.1) Crediti verso clienti — entro l'esercizio")
    sp07a_crediti_clienti_lungo: float = pydantic.Field(0, description="C.II.1) Crediti verso clienti — oltre l'esercizio")
    sp06b_crediti_controllate_breve: float = pydantic.Field(0, description="C.II.2) Crediti verso imprese controllate — entro l'esercizio")
    sp07b_crediti_controllate_lungo: float = pydantic.Field(0, description="C.II.2) Crediti verso imprese controllate — oltre l'esercizio")
    sp06c_crediti_collegate_breve: float = pydantic.Field(0, description="C.II.3) Crediti verso imprese collegate — entro l'esercizio")
    sp07c_crediti_collegate_lungo: float = pydantic.Field(0, description="C.II.3) Crediti verso imprese collegate — oltre l'esercizio")
    sp06d_crediti_controllanti_breve: float = pydantic.Field(0, description="C.II.4) Crediti verso controllanti — entro l'esercizio")
    sp07d_crediti_controllanti_lungo: float = pydantic.Field(0, description="C.II.4) Crediti verso controllanti — oltre l'esercizio")
    sp06e_crediti_tributari_breve: float = pydantic.Field(0, description="C.II.5-bis) Crediti tributari — entro l'esercizio")
    sp07e_crediti_tributari_lungo: float = pydantic.Field(0, description="C.II.5-bis) Crediti tributari — oltre l'esercizio")
    sp06f_imposte_anticipate_breve: float = pydantic.Field(0, description="C.II.5-ter) Imposte anticipate — entro l'esercizio")
    sp07f_imposte_anticipate_lungo: float = pydantic.Field(0, description="C.II.5-ter) Imposte anticipate — oltre l'esercizio")
    sp06g_crediti_altri_breve: float = pydantic.Field(0, description="C.II.5-quater) Crediti verso altri — entro l'esercizio")
    sp07g_crediti_altri_lungo: float = pydantic.Field(0, description="C.II.5-quater) Crediti verso altri — oltre l'esercizio")
    sp08_attivita_finanziarie: float = pydantic.Field(0, description="C.III) Attivita finanziarie che non costituiscono immobilizzazioni")
    sp09_disponibilita_liquide: float = pydantic.Field(0, description="C.IV) Disponibilita liquide")
    sp10_ratei_risconti_attivi: float = pydantic.Field(0, description="D) Ratei e risconti attivi")
    sp11_capitale: float = pydantic.Field(0, description="A.I) Capitale sociale")
    sp12_riserve: float = pydantic.Field(0, description="Sum of all reserves (II-VIII): sovrapprezzo, rivalutazione, legale, statutarie, altre, copertura flussi, utili portati, azioni proprie")
    sp13_utile_perdita: float = pydantic.Field(0, description="A.IX) Utile (perdita) dell'esercizio")
    sp14_fondi_rischi: float = pydantic.Field(0, description="B) Fondi per rischi e oneri")
    sp15_tfr: float = pydantic.Field(0, description="C) Trattamento di fine rapporto di lavoro subordinato")
    sp16_debiti_breve: float = pydantic.Field(0, description="D) Debiti esigibili entro l'esercizio successivo")
    sp17_debiti_lungo: float = pydantic.Field(0, description="D) Debiti esigibili oltre l'esercizio successivo")
    # Creditor-type breakdown per OIC art. 2424 (entro/oltre per group).
    # Must sum to sp16_debiti_breve and sp17_debiti_lungo respectively.
    sp16a_debiti_banche_breve: float = pydantic.Field(0, description="D.4) Debiti verso banche — entro l'esercizio")
    sp17a_debiti_banche_lungo: float = pydantic.Field(0, description="D.4) Debiti verso banche — oltre l'esercizio")
    sp16b_debiti_altri_finanz_breve: float = pydantic.Field(0, description="D.3)+D.5) Debiti verso soci per finanziamenti + verso altri finanziatori — entro l'esercizio")
    sp17b_debiti_altri_finanz_lungo: float = pydantic.Field(0, description="D.3)+D.5) Debiti verso soci per finanziamenti + verso altri finanziatori — oltre l'esercizio")
    sp16c_debiti_obbligazioni_breve: float = pydantic.Field(0, description="D.1)+D.2)+D.8) Obbligazioni + obbligazioni convertibili + debiti rappresentati da titoli di credito — entro l'esercizio")
    sp17c_debiti_obbligazioni_lungo: float = pydantic.Field(0, description="D.1)+D.2)+D.8) Obbligazioni + obbligazioni convertibili + debiti rappresentati da titoli di credito — oltre l'esercizio")
    sp16d_debiti_fornitori_breve: float = pydantic.Field(0, description="D.7) Debiti verso fornitori — entro l'esercizio")
    sp17d_debiti_fornitori_lungo: float = pydantic.Field(0, description="D.7) Debiti verso fornitori — oltre l'esercizio")
    sp16e_debiti_tributari_breve: float = pydantic.Field(0, description="D.12) Debiti tributari — entro l'esercizio")
    sp17e_debiti_tributari_lungo: float = pydantic.Field(0, description="D.12) Debiti tributari — oltre l'esercizio")
    sp16f_debiti_previdenza_breve: float = pydantic.Field(0, description="D.13) Debiti verso istituti di previdenza e di sicurezza sociale — entro l'esercizio")
    sp17f_debiti_previdenza_lungo: float = pydantic.Field(0, description="D.13) Debiti verso istituti di previdenza e di sicurezza sociale — oltre l'esercizio")
    sp16g_altri_debiti_breve: float = pydantic.Field(0, description="D.6)+D.9-11bis)+D.14) Acconti + verso controllate/collegate/controllanti + altri debiti — entro l'esercizio")
    sp17g_altri_debiti_lungo: float = pydantic.Field(0, description="D.6)+D.9-11bis)+D.14) Acconti + verso controllate/collegate/controllanti + altri debiti — oltre l'esercizio")
    sp18_ratei_risconti_passivi: float = pydantic.Field(0, description="E) Ratei e risconti passivi")
    totale_attivo: float = pydantic.Field(0, description="Totale attivo (total assets)")
    totale_passivo: float = pydantic.Field(0, description="Totale passivo (total equity + liabilities)")
    totale_debiti: float = pydantic.Field(0, description="Totale debiti (D) — the explicit 'Totale debiti' line from the PDF, sum of all debt categories (both entro and oltre). Used for validation.")
    totale_crediti: float = pydantic.Field(0, description="Totale crediti (C.II) — the explicit 'Totale crediti' line from the PDF, sum of all C.II debtor categories (both entro and oltre). Used for validation.")


class IncomeStatementExtraction(_ItalianNumberModel):
    """IV CEE Conto Economico fields."""
    ce01_ricavi_vendite: float = pydantic.Field(0, description="A.1) Ricavi delle vendite e delle prestazioni")
    ce02_variazioni_rimanenze: float = pydantic.Field(0, description="A.2) Variazioni delle rimanenze di prodotti in corso di lavorazione, semilavorati e finiti")
    ce03_lavori_interni: float = pydantic.Field(0, description="A.4) Incrementi di immobilizzazioni per lavori interni")
    ce04_altri_ricavi: float = pydantic.Field(0, description="A.5) Altri ricavi e proventi")
    ce05_materie_prime: float = pydantic.Field(0, description="B.6) Per materie prime, sussidiarie, di consumo e di merci")
    ce06_servizi: float = pydantic.Field(0, description="B.7) Per servizi")
    ce07_godimento_beni: float = pydantic.Field(0, description="B.8) Per godimento di beni di terzi")
    ce08_costi_personale: float = pydantic.Field(0, description="B.9) Totale costi per il personale")
    ce08a_tfr_accrual: float = pydantic.Field(0, description="B.9c) Trattamento di fine rapporto (sub-item of personnel costs)")
    ce09_ammortamenti: float = pydantic.Field(0, description="B.10) Totale ammortamenti e svalutazioni")
    ce09a_ammort_immateriali: float = pydantic.Field(0, description="B.10a) Ammortamento delle immobilizzazioni immateriali")
    ce09b_ammort_materiali: float = pydantic.Field(0, description="B.10b) Ammortamento delle immobilizzazioni materiali")
    ce09c_svalutazioni: float = pydantic.Field(0, description="B.10c) Altre svalutazioni delle immobilizzazioni")
    ce09d_svalutazione_crediti: float = pydantic.Field(0, description="B.10d) Svalutazioni dei crediti compresi nell'attivo circolante")
    ce10_var_rimanenze_mat_prime: float = pydantic.Field(0, description="B.11) Variazioni delle rimanenze di materie prime, sussidiarie, di consumo e merci")
    ce11_accantonamenti: float = pydantic.Field(0, description="B.12) Accantonamenti per rischi")
    ce11b_altri_accantonamenti: float = pydantic.Field(0, description="B.13) Altri accantonamenti")
    ce12_oneri_diversi: float = pydantic.Field(0, description="B.14) Oneri diversi di gestione")
    ce13_proventi_partecipazioni: float = pydantic.Field(0, description="C.15) Proventi da partecipazioni")
    ce14_altri_proventi_finanziari: float = pydantic.Field(0, description="C.16) Altri proventi finanziari")
    ce15_oneri_finanziari: float = pydantic.Field(0, description="C.17) Interessi e altri oneri finanziari")
    ce16_utili_perdite_cambi: float = pydantic.Field(0, description="C.17-bis) Utili e perdite su cambi")
    ce17_rettifiche_attivita_fin: float = pydantic.Field(0, description="D) Totale delle rettifiche di valore di attivita e passivita finanziarie")
    ce18_proventi_straordinari: float = pydantic.Field(0, description="E.20) Proventi straordinari")
    ce19_oneri_straordinari: float = pydantic.Field(0, description="E.21) Oneri straordinari")
    ce20_imposte: float = pydantic.Field(0, description="22) Imposte sul reddito dell'esercizio")


class TwoYearBalanceSheetExtraction(pydantic.BaseModel):
    """IV CEE Stato Patrimoniale — both columns (current year + prior year)."""
    current_year: BalanceSheetExtraction = pydantic.Field(description="Current year values (leftmost/first column)")
    prior_year: BalanceSheetExtraction = pydantic.Field(description="Prior year values (rightmost/second column)")


class TwoYearIncomeStatementExtraction(pydantic.BaseModel):
    """IV CEE Conto Economico — both columns (current year + prior year)."""
    current_year: IncomeStatementExtraction = pydantic.Field(description="Current year values (leftmost/first column)")
    prior_year: IncomeStatementExtraction = pydantic.Field(description="Prior year values (rightmost/second column)")


# ---------------------------------------------------------------------------
# PyMuPDF page detection — range-based IV CEE section finding
# ---------------------------------------------------------------------------

# SP (Stato Patrimoniale) anchors
SP_START_KEYWORDS = ["stato patrimoniale", "attivo"]  # both must appear on start page
# SP end: the closing "Totale ... passivo/passività" line. Gestionali word it many ways
# ("Totale passivo", "Totale passività", "Totale STATO PATRIMONIALE passivo",
# "Totale passivo e patrimonio netto", ...). A plain "totale passivo" substring misses
# the variants with words in between (e.g. budget_352 "TOTALE STATO PATRIMONIALE PASSIVO"),
# which truncated the SP window before the passivo pages and broke the balance. Keep this
# list broad; _find_end scans from sp_start forward so the first SP-closing total wins.
SP_END_KEYWORDS = [
    "totale passivo",
    "totale passività",
    "totale stato patrimoniale passivo",
    "totale dello stato patrimoniale passivo",
    "totale passivo e patrimonio netto",
    "totale passivo e netto",
    "totale passività e patrimonio netto",
    "totale passività e netto",
]

# CE (Conto Economico) anchors
CE_START_KEYWORDS = ["conto economico", "valore della produzione"]  # both must appear
# CE end: "21) Utile (perdita) dell'esercizio" or nearby.
# NOTE: "utile (perdita) dell'esercizio" also appears in SP equity (item IX),
# so we search from ce_start+1 to skip the SP overlap page.
# We use two tiers: first look for the definitive item 21 line,
# then fall back to "totale delle imposte" which is 1 line before item 21.
CE_END_KEYWORDS_PRIMARY = [
    "21) utile (perdita) dell'esercizio",       # item 21 with number prefix
    "21) utile(perdita) dell'esercizio",        # variant without space
]
CE_END_KEYWORDS_FALLBACK = [
    "totale delle imposte sul reddito",         # item 20 total — last line before result
    "utile (perdita) dell'esercizio",           # without prefix (searched from ce_start+1)
    "risultato dell'esercizio",
]

# Fallback: single-keyword detection if range-based fails
SP_FALLBACK_KEYWORDS = [
    "totale attivo", "totale passivo",
    "attivo circolante",      # always present on BS asset pages
    "patrimonio netto",       # always present on BS liability pages
]
CE_FALLBACK_KEYWORDS = ["totale valore della produzione", "differenza tra valore e costi", "differ. tra valore e costi"]


_DETACHED_AMOUNT_RE = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$|^-?\d+,\d{2}$")


def _detached_value_page_texts(doc: fitz.Document) -> Dict[int, str]:
    """Rejoin labels and amounts split across two physical page layers.

    A few accounting exports print ``N`` normal pages whose amount cells are all
    ``0,00``, followed by ``N`` headerless pages containing the real amount column.
    Each value keeps the exact vertical coordinate of its placeholder.  Plain text
    extraction therefore sends only zeroes to the LLM even though the visible PDF is
    complete (budget_355/356).

    Return synthetic text for the first half only when the geometry proves this
    layout: an even page count, amount-only second half, at least 30 matches, >=95%
    one-to-one Y coverage, and materially non-zero values.  No accounting value is
    inferred; every replacement comes from one uniquely aligned source cell.
    """
    page_count = len(doc)
    if page_count < 4 or page_count % 2:
        return {}
    half = page_count // 2
    page_words = [page.get_text("words", sort=True) for page in doc]

    value_word_count = sum(len(words) for words in page_words[half:])
    alpha_value_words = sum(
        1
        for words in page_words[half:]
        for word in words
        if re.search(r"[A-Za-zÀ-ÿ]", str(word[4]))
    )
    if value_word_count == 0 or alpha_value_words > max(5, int(value_word_count * 0.02)):
        return {}

    replacements_by_page: Dict[int, Dict[int, str]] = {}
    matched = 0
    placeholder_count = 0
    value_count = 0
    source_mass = Decimal("0")

    for page_index in range(half):
        labels = page_words[page_index]
        values = page_words[page_index + half]
        placeholders = [
            (idx, word)
            for idx, word in enumerate(labels)
            if _DETACHED_AMOUNT_RE.fullmatch(str(word[4]).strip())
        ]
        source_values = [
            word for word in values
            if _DETACHED_AMOUNT_RE.fullmatch(str(word[4]).strip())
        ]
        if not placeholders or not source_values:
            return {}

        placeholder_count += len(placeholders)
        value_count += len(source_values)
        available = set(range(len(placeholders)))
        page_replacements: Dict[int, str] = {}
        for value in source_values:
            candidates = [
                pos for pos in available
                if abs(float(placeholders[pos][1][1]) - float(value[1])) <= 1.0
            ]
            if not candidates:
                continue
            best = min(
                candidates,
                key=lambda pos: abs(float(placeholders[pos][1][1]) - float(value[1])),
            )
            available.remove(best)
            word_index = placeholders[best][0]
            token = str(value[4]).strip()
            page_replacements[word_index] = token
            matched += 1
            parsed = _parse_it_number(token)
            if parsed is not None:
                source_mass += abs(parsed)
        replacements_by_page[page_index] = page_replacements

    coverage = Decimal(matched) / Decimal(max(placeholder_count, value_count, 1))
    if matched < 30 or coverage < Decimal("0.95") or source_mass < Decimal("1000"):
        return {}

    def _render_page(words, replacements: Dict[int, str]) -> str:
        positioned = []
        for idx, word in enumerate(words):
            positioned.append((float(word[1]), float(word[0]), replacements.get(idx, str(word[4]))))
        positioned.sort(key=lambda item: (item[0], item[1]))
        lines: List[str] = []
        current: List[Tuple[float, str]] = []
        line_y: Optional[float] = None
        for y, x, token in positioned:
            if line_y is None or abs(y - line_y) <= 1.0:
                current.append((x, token))
                if line_y is None:
                    line_y = y
                continue
            lines.append(" ".join(text for _, text in sorted(current)))
            current = [(x, token)]
            line_y = y
        if current:
            lines.append(" ".join(text for _, text in sorted(current)))
        return "\n".join(lines)

    logger.warning(
        "Detached amount pages detected: %s/%s cells matched (%.1f%%); "
        "rejoining %s page pairs from source coordinates",
        matched, max(placeholder_count, value_count), float(coverage * 100), half,
    )
    return {
        page_index: _render_page(page_words[page_index], replacements_by_page[page_index])
        for page_index in range(half)
    }


_GEOMETRIC_NUMBER_RE = re.compile(
    r"^\(?-?\d{1,3}(?:\.\d{3})*(?:,\d{2})?\)?-?$"
)


def _comparative_column_words(words) -> List[Tuple]:
    """Return the left-to-right current/prior header words for a table page."""
    for pattern in (r"\d{2}/\d{2}/20\d{2}", r"20\d{2}"):
        candidates = sorted(
            (
                word for word in words
                if re.fullmatch(pattern, str(word[4]).strip())
            ),
            key=lambda word: (float(word[1]), float(word[0])),
        )
        pairs = []
        for first in candidates:
            same_line = sorted(
                (
                    other for other in candidates
                    if other is not first
                    and abs(float(other[1]) - float(first[1])) <= 1
                    and float(other[0]) > float(first[0]) + 25
                ),
                key=lambda word: float(word[0]),
            )
            if same_line:
                pairs.append((first, same_line[0]))
        if pairs:
            # Prefer the financial-statement table on the right over small note
            # tables whose date columns begin near the left margin.
            return list(max(pairs, key=lambda pair: float(pair[0][0])))
    return []


# Intestazioni di colonna scritte a PAROLE, non a date. Il "bilancio riclassificato
# UE" non data le colonne: l'unica data stampata e' il periodo ("dal 01/01/2026 al
# 30/06/2026"), che il riconoscimento per data scambia per una coppia di colonne
# affiancate a meta' pagina. Le vere colonne sono intestate
# ``Importo corrente | Importo comparato | Scostamento | %`` e sono allineate a
# DESTRA sul bordo della propria intestazione: l'ancora e' quindi il bordo destro
# (``word[2]``), non il centro.
_CURRENT_COLUMN_HEADERS = ('corrente',)
_PRIOR_COLUMN_HEADERS = ('comparato', 'precedente', 'confronto')
# Colonne di ANALISI, non contabili: vanno riconosciute per non essere scambiate
# per la colonna del comparato (su una riga a corrente vuoto lo scostamento e la
# percentuale sono gli unici altri numeri stampati, e senza queste ancore il
# confronto "piu' vicino fra due" li attribuirebbe all'anno precedente).
_ANALYSIS_COLUMN_HEADERS = ('scostamento', 'scost.', 'differenza', 'variazione', '%')


class _ColumnAnchors(NamedTuple):
    """Ancore orizzontali delle colonne numeriche di un prospetto comparato.

    ``right_edge`` distingue le due grafie: le colonne intestate a parole sono
    allineate al bordo destro dell'intestazione, quelle intestate a date si
    riconoscono dal centro (comportamento storico, lasciato invariato).
    """

    current: float
    prior: float
    others: Tuple[float, ...]
    right_edge: bool


def _text_line_groups(words) -> List[List[Tuple]]:
    """Raggruppa le parole per riga fisica (stessa baseline entro 1pt)."""
    groups: List[List[Tuple]] = []
    for word in sorted(words, key=lambda item: (float(item[1]), float(item[0]))):
        if not groups or abs(float(word[1]) - float(groups[-1][0][1])) > 1.0:
            groups.append([word])
        else:
            groups[-1].append(word)
    return groups


# Quanto puo' discostarsi il valore ESTRATTO dall'importo stampato nella cella del
# comparato perche' i due si riconoscano come lo stesso numero. Non e' una
# tolleranza contabile: e' un controllo di IDENTITA', il cinturino di sicurezza che
# impedisce di azzerare un campo diverso da quello che ha preso il comparato. Chi
# decide che il valore corrente e' zero e' la geometria (la cella e' vuota), non
# questa soglia. Un euro perche' l'estrazione LLM non e' deterministica e a volte
# restituisce l'importo troncato ai centesimi (90.603,75 -> 90603): a cento
# centesimi di distanza si parla ancora dello stesso importo, a un euro di distanza
# non esiste un'altra voce di bilancio con cui confonderlo.
_PRIOR_CELL_MATCH_TOL = Decimal('1')


def _row_code_words(labels) -> List[str]:
    """Il codice di voce di una riga di prospetto: la PRIMA parola dell'etichetta.

    Prendere tutte le parole del margine sinistro sembra piu' generoso ed e'
    invece una trappola: nell'etichetta "D) Ratei e risconti" la congiunzione
    ``e`` supera un confronto ``^E[.)]?$`` insensibile alle maiuscole, e la voce
    dell'ATTIVO si spaccia per la ``E)`` del passivo. Il codice, quando c'e', sta
    sempre in testa alla riga.
    """
    ordered = sorted(labels, key=lambda word: float(word[0]))
    if not ordered or float(ordered[0][0]) >= 130:
        return []
    return [str(ordered[0][4]).strip()]


def _labelled_column_anchors(words) -> Optional[_ColumnAnchors]:
    """Ancore lette da un'intestazione ``corrente | comparato | ...`` stampata."""
    for line in _text_line_groups(words):
        current_word = prior_word = None
        for word in sorted(line, key=lambda item: float(item[0])):
            if float(word[0]) < 250:
                continue  # colonne numeriche: mai a ridosso del margine sinistro
            token = str(word[4]).strip().casefold().strip(':')
            if current_word is None:
                if token in _CURRENT_COLUMN_HEADERS:
                    current_word = word
            elif prior_word is None and token in _PRIOR_COLUMN_HEADERS:
                prior_word = word
        if current_word is None or prior_word is None:
            continue
        current_x = float(current_word[2])
        prior_x = float(prior_word[2])
        if prior_x - current_x < 25:
            continue
        others = tuple(
            float(word[2]) for word in line
            if float(word[0]) > prior_x
            and str(word[4]).strip().casefold() in _ANALYSIS_COLUMN_HEADERS
        )
        return _ColumnAnchors(current_x, prior_x, others, True)
    return None


def _page_column_anchors(
    words, document_centers: Optional[Tuple[float, float]] = None
) -> Optional[_ColumnAnchors]:
    """Ancore di colonna della pagina: prima le intestazioni a parole, poi le date."""
    labelled = _labelled_column_anchors(words)
    if labelled is not None:
        return labelled
    date_words = _comparative_column_words(words)
    if len(date_words) >= 2:
        current_x = (float(date_words[0][0]) + float(date_words[0][2])) / 2
        prior_x = (float(date_words[1][0]) + float(date_words[1][2])) / 2
    elif document_centers is not None:
        current_x, prior_x = document_centers
    else:
        return None
    if prior_x - current_x < 25:
        return None
    return _ColumnAnchors(current_x, prior_x, (), False)


def _column_of(word, anchors: _ColumnAnchors) -> str:
    """``'current'`` / ``'prior'`` / ``'other'``: colonna piu' vicina all'importo."""
    x = float(word[2]) if anchors.right_edge else (float(word[0]) + float(word[2])) / 2
    best_name = 'current'
    best_distance = abs(x - anchors.current)
    candidates = [('prior', anchors.prior)]
    candidates.extend(('other', anchor) for anchor in anchors.others)
    for name, anchor in candidates:
        distance = abs(x - anchor)
        if distance < best_distance:
            best_name, best_distance = name, distance
    return best_name


def _split_current_prior(numbers, anchors: _ColumnAnchors) -> Tuple[List, List]:
    current_numbers, prior_numbers = [], []
    for word in numbers:
        column = _column_of(word, anchors)
        if column == 'current':
            current_numbers.append(word)
        elif column == 'prior':
            prior_numbers.append(word)
    return current_numbers, prior_numbers


def _document_comparative_centers(doc: fitz.Document) -> Optional[Tuple[float, float]]:
    pairs = []
    for page in doc:
        headers = _comparative_column_words(page.get_text('words', sort=True))
        if len(headers) < 2:
            continue
        centers = tuple((float(word[0]) + float(word[2])) / 2 for word in headers)
        if centers[0] > 350 and centers[1] - centers[0] >= 25:
            pairs.append(centers)
    return max(pairs, key=lambda pair: pair[0]) if pairs else None


def _filter_difference_columns(page: fitz.Page) -> Optional[str]:
    """Return row-wise text without DIFFERENZA/SCOST. analysis columns.

    Some ERP exports have four numeric columns (current year, prior year,
    difference, percentage).  The two-year prompt otherwise interprets the
    repeated difference as another accounting value (budget_314).  Geometry is
    unambiguous: retain both ``ESERCIZIO`` columns and drop only words at or to the
    right of the printed ``DIFFERENZA`` header.
    """
    words = page.get_text('words', sort=True)
    difference_headers = [
        word for word in words if str(word[4]).strip().casefold().startswith('differenza')
    ]
    has_deviation = any(
        str(word[4]).strip().casefold().startswith('scost') for word in words
    )
    years = {
        str(word[4]).strip() for word in words
        if re.fullmatch(r"20\d{2}", str(word[4]).strip())
    }
    if not difference_headers or not has_deviation or len(years) < 2:
        return None
    cutoff_x = min(float(word[0]) for word in difference_headers) - 2
    kept = [word for word in words if float(word[0]) < cutoff_x]
    positioned = sorted(kept, key=lambda word: (float(word[1]), float(word[0])))
    lines: List[str] = []
    current: List[Tuple[float, str]] = []
    line_y: Optional[float] = None
    for word in positioned:
        y, x, token = float(word[1]), float(word[0]), str(word[4])
        if line_y is None or abs(y - line_y) <= 1.0:
            current.append((x, token))
            if line_y is None:
                line_y = y
            continue
        lines.append(' '.join(text for _, text in sorted(current)))
        current = [(x, token)]
        line_y = y
    if current:
        lines.append(' '.join(text for _, text in sorted(current)))
    logger.warning(
        "Filtered DIFFERENZA/SCOST. columns at x>=%.1f from source page %s",
        cutoff_x, page.number + 1,
    )
    return '\n'.join(lines)


# Ordine di lettura: minimo di blocchi sotto il quale la statistica non e'
# significativa, e quota di inversioni verticali oltre la quale lo stream e'
# considerato fuori ordine (un salto all'indietro isolato e' normale: colonne
# affiancate, note a pie' di pagina, intestazioni ripetute).
_SCRAMBLED_MIN_BLOCKS = 6
_SCRAMBLED_INVERSION_PCT = 0.25
_SCRAMBLED_LINE_TOL = 1.0


def _stream_order_is_scrambled(page: fitz.Page) -> bool:
    """True quando il content-stream emette il testo fuori dall'ordine di lettura.

    ``page.get_text()`` segue l'ordine in cui il generatore ha SCRITTO il testo,
    non quello in cui il documento si LEGGE. Alcuni export disegnano il prospetto
    dal basso verso l'alto, o disegnano la seconda colonna importi come blocco
    staccato: le etichette si legano allora agli importi della colonna sbagliata
    e l'anno precedente viene importato come anno corrente (il "Bilancio
    riclassificato / Fascicolo" leggeva la colonna 2024 come 2025, e attribuiva
    gli oneri finanziari «altri» alla voce D.18 Rivalutazioni che li precede
    nello stream, gonfiando l'utile CE).

    Il criterio e' geometrico e deterministico: si contano i salti verticali
    all'indietro fra blocchi consecutivi nell'ordine di stream.
    """
    try:
        blocks = [b for b in page.get_text("blocks") if str(b[4]).strip()]
    except Exception:  # pagina illeggibile: nessuna diagnosi, nessun cambiamento
        return False
    if len(blocks) < _SCRAMBLED_MIN_BLOCKS:
        return False
    tops = [float(b[1]) for b in blocks]
    inversions = sum(
        1 for previous, current in zip(tops, tops[1:])
        if current < previous - _SCRAMBLED_LINE_TOL
    )
    return inversions > len(tops) * _SCRAMBLED_INVERSION_PCT


def reading_order_text(page: fitz.Page) -> str:
    """Testo della pagina nell'ordine in cui e' STAMPATA.

    Restituisce il testo grezzo (byte-identico a ``page.get_text()``) quando lo
    stream e' gia' in ordine — cosi' i PDF ben formati, su cui i prompt sono
    tarati, non cambiano di un carattere — e passa all'ordinamento per
    coordinate solo sulle pagine dimostrabilmente scomposte.
    """
    raw = page.get_text()
    if not _stream_order_is_scrambled(page):
        return raw
    ordered = page.get_text(sort=True)
    # Riordinare e' SPOSTARE, non riscrivere: se le parole in uscita non sono
    # piu' quelle della pagina, l'ordinamento ha fatto danni e vale meno dello
    # stream grezzo. Succede sulle stampe che disegnano la sottolineatura come
    # glifi `_` su una baseline di pochi punti piu' in basso (situazioni
    # contabili AGO): l'ordinamento salda la riga di underscore all'importo che
    # la precede — `1.468.999,24______________` — e quell'importo smette di
    # essere un numero per chiunque lo legga, LLM compreso.
    if sorted(ordered.split()) != sorted(raw.split()):
        logger.warning(
            "Riordino per coordinate scartato a pagina %s: cambierebbe le parole "
            "della pagina (importi saldati alla sottolineatura); si tiene il "
            "content-stream grezzo", page.number + 1,
        )
        return raw
    logger.warning(
        "Content-stream fuori ordine di lettura a pagina %s: testo riordinato "
        "per coordinate (altrimenti etichette e importi si legano alla colonna "
        "sbagliata)", page.number + 1,
    )
    return ordered


# Voci di CE la cui cella dell'anno corrente puo' restare VUOTA su un prospetto
# comparato: la riga stampa allora tre numeri invece di quattro (comparato,
# scostamento, %) e la lettura lineare prende il primo, cioe' l'anno precedente.
# Ogni voce porta i propri importi sulla stessa baseline dell'etichetta, quindi si
# legge per riga fisica; il codice di voce stampato e le parole obbligatorie
# rendono il riconoscimento inequivocabile.
#   - ce03: A.4 "Incrementi di immobilizzazioni per lavori interni"
#   - ce09d: B.10.d "Svalutazioni dei crediti compresi nell'attivo circolante"
#   - ce20: 20) "Imposte sul reddito dell'esercizio" (anche quando la voce non ha
#     il dettaglio 20.a/20.b su cui lavora il passo per segmenti piu' sotto)
_BLANK_CURRENT_CE_ROWS = {
    'ce03_lavori_interni': (
        re.compile(r"^(?:A\.?)?4\)[,]?$", re.I),
        ('incrementi', 'immobilizzazioni', 'lavori', 'interni'),
    ),
    'ce09d_svalutazione_crediti': (
        re.compile(r"^(?:B\.?)?(?:10\.?)?d\)[,]?$", re.I),
        ('svalutazioni', 'crediti'),
    ),
    'ce20_imposte': (
        re.compile(r"^(?:20|22)\)[,]?$"),
        ('imposte', 'reddito'),
    ),
}


def _clear_blank_current_rows(
    words,
    anchors: _ColumnAnchors,
    specs: Dict[str, Tuple[re.Pattern, Tuple[str, ...]]],
    current: Dict[str, Decimal],
    prior: Dict[str, Decimal],
) -> List[Tuple[str, str]]:
    """Azzera i campi la cui riga stampa un importo SOLO nella colonna comparato.

    Nessun valore viene dedotto: si legge la geometria della riga, e si agisce solo
    quando la cella dell'anno corrente e' dimostrabilmente vuota e quella del
    comparato contiene l'importo che l'estrattore ha attribuito all'anno corrente.
    """
    cleared: List[Tuple[str, str]] = []
    for line in _text_line_groups(words):
        labels = [word for word in line if float(word[0]) < 350]
        label_text = ' '.join(str(word[4]).casefold() for word in labels)
        codes = _row_code_words(labels)
        if not codes:
            continue
        numbers = [
            word for word in line
            if float(word[0]) > 350
            and _GEOMETRIC_NUMBER_RE.fullmatch(str(word[4]).strip())
        ]
        if not numbers:
            continue
        for field, (code_re, required_words) in specs.items():
            if not all(token in label_text for token in required_words):
                continue
            if not any(code_re.fullmatch(code) for code in codes):
                continue
            current_numbers, prior_numbers = _split_current_prior(numbers, anchors)
            if current_numbers or not prior_numbers:
                continue
            parsed = [_parse_it_number(str(word[4])) for word in prior_numbers]
            parsed = [value for value in parsed if value is not None]
            if not parsed or any(value != parsed[0] for value in parsed[1:]):
                continue
            extracted = current.get(field, Decimal('0'))
            if (
                parsed[0] == 0
                or extracted == 0
                or abs(abs(extracted) - abs(parsed[0])) > _PRIOR_CELL_MATCH_TOL
            ):
                continue
            current[field] = Decimal('0')
            if prior:
                prior[field] = parsed[0]
            cleared.append((field, str(parsed[0])))
    return cleared


def _reconcile_blank_current_ce_cells(
    file_path: str,
    current_ce: Dict[str, Decimal],
    prior_ce: Optional[Dict[str, Decimal]] = None,
) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Clear CE values copied from a prior-year-only visual cell.

    PyMuPDF's linear text loses empty table cells.  On comparative statements this
    can make a lone prior-year amount look like the current value (budget_391 A.2,
    budget_328/144 B.11).  Use the printed date-column X coordinates and the legal
    item row bounds to act only when the current cell is geometrically empty and the
    prior cell contains an explicit amount.
    """
    current = dict(current_ce)
    prior = dict(prior_ce or {})
    try:
        doc = fitz.open(file_path)
    except Exception:
        return current, prior

    target_specs = {
        'ce02_variazioni_rimanenze': (
            re.compile(r"^2\)[,]?$"),
            ('variazioni', 'rimanenze', 'prodotti'),
        ),
        'ce10_var_rimanenze_mat_prime': (
            re.compile(r"^11\)[,]?$"),
            ('variazioni', 'rimanenze', 'materie'),
        ),
        'ce11_accantonamenti': (
            re.compile(r"^(?:B\.)?12\)[,]?$", re.I),
            ('accanton', 'rischi'),
        ),
        'ce15_oneri_finanziari': (
            re.compile(r"^17\)[,]?$"),
            ('interessi', 'oneri', 'finanziari'),
        ),
        'ce20_imposte': (
            re.compile(r"^(?:20|22)\)[,]?$"),
            ('imposte', 'reddito'),
        ),
    }
    cleared: List[Tuple[str, str]] = []
    document_centers = _document_comparative_centers(doc)
    try:
        for page in doc:
            words = page.get_text('words', sort=True)
            anchors = _page_column_anchors(words, document_centers)
            if anchors is None:
                continue
            cleared.extend(
                _clear_blank_current_rows(
                    words, anchors, _BLANK_CURRENT_CE_ROWS, current, prior
                )
            )

            item_words = sorted(
                (
                    word for word in words
                    if float(word[0]) < 125
                    and re.fullmatch(
                        r"(?:B\.)?\d+\)[,]?",
                        str(word[4]).strip(),
                        re.I,
                    )
                ),
                key=lambda word: float(word[1]),
            )
            for position, item_word in enumerate(item_words):
                start_y = float(item_word[1]) - 1
                next_item = next(
                    (
                        candidate for candidate in item_words[position + 1:]
                        if float(candidate[1]) > float(item_word[1]) + 2
                    ),
                    None,
                )
                next_y = (
                    float(next_item[1]) - 1
                    if next_item is not None
                    else float(item_word[3]) + 35
                )
                segment = [
                    word for word in words
                    if start_y <= float(word[1]) < next_y
                ]
                segment_text = ' '.join(str(word[4]).lower() for word in segment)
                for field, (code_re, required_words) in target_specs.items():
                    if not code_re.fullmatch(str(item_word[4]).strip()):
                        continue
                    if not all(token in segment_text for token in required_words):
                        continue
                    numbers = [
                        word for word in segment
                        if float(word[0]) > 350
                        and _GEOMETRIC_NUMBER_RE.fullmatch(str(word[4]).strip())
                    ]
                    if field == 'ce20_imposte':
                        # Item 20 often has a detailed 20.a/20.b breakdown below it.
                        # The top-level amount on the code baseline is the only value
                        # that proves whether the current aggregate cell is blank.
                        same_row = [
                            word for word in numbers
                            if abs(float(word[1]) - float(item_word[1])) <= 1
                        ]
                        if same_row:
                            numbers = same_row
                    elif field == 'ce15_oneri_finanziari':
                        # The 17) label can be followed by a detail line, its subtotal,
                        # and then the unrelated C total.  Prefer the explicit subtotal
                        # row so values from C cannot be mistaken for this item.
                        line_groups: List[List[Tuple]] = []
                        for word in sorted(
                            segment, key=lambda item: (float(item[1]), float(item[0]))
                        ):
                            if (
                                not line_groups
                                or abs(float(word[1]) - float(line_groups[-1][0][1])) > 1
                            ):
                                line_groups.append([word])
                            else:
                                line_groups[-1].append(word)
                        subtotal_numbers: List[Tuple] = []
                        for line in line_groups:
                            line_text = ' '.join(
                                str(word[4]).casefold() for word in line
                            )
                            if all(
                                token in line_text
                                for token in ('totale', 'interessi', 'oneri', 'finanziari')
                            ):
                                subtotal_numbers = [
                                    word for word in line
                                    if float(word[0]) > 350
                                    and _GEOMETRIC_NUMBER_RE.fullmatch(
                                        str(word[4]).strip()
                                    )
                                ]
                                break
                        if subtotal_numbers:
                            numbers = subtotal_numbers
                    current_numbers, prior_numbers = _split_current_prior(
                        numbers, anchors
                    )
                    if current_numbers or not prior_numbers:
                        continue
                    # Repeated rendering of the same row is harmless; all observed
                    # prior values must agree before the current field is cleared.
                    parsed = [_parse_it_number(str(word[4])) for word in prior_numbers]
                    parsed = [value for value in parsed if value is not None]
                    if not parsed or any(value != parsed[0] for value in parsed[1:]):
                        continue
                    extracted = current.get(field, Decimal('0'))
                    if (
                        parsed[0] == 0
                        or extracted == 0
                        or abs(abs(extracted) - abs(parsed[0])) > _PRIOR_CELL_MATCH_TOL
                    ):
                        continue
                    current[field] = Decimal('0')
                    if prior:
                        prior[field] = parsed[0]
                    cleared.append((field, str(parsed[0])))
    finally:
        doc.close()

    if cleared:
        logger.warning(
            "CE column geometry: cleared prior-only cells from current year: %s",
            cleared,
        )
    return current, prior


def _reconcile_blank_current_sp_cells(
    file_path: str,
    current_bs: Dict[str, Decimal],
    prior_bs: Optional[Dict[str, Decimal]] = None,
) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Clear selected SP fields proven to exist only in the prior column.

    This is the balance-sheet counterpart of
    :func:`_reconcile_blank_current_ce_cells`.  The target labels are deliberately
    narrow and legally unambiguous; values are never derived from the balance gap.
    """
    current = dict(current_bs)
    prior = dict(prior_bs or {})
    specs = {
        'sp02_immob_immateriali': (('immobilizzazioni', 'immateriali'), re.compile(r"^I[.)]?$", re.I)),
        'sp14_fondi_rischi': (('fondi', 'rischi', 'oneri'), re.compile(r"^B[.)]?$", re.I)),
        'sp18_ratei_risconti_passivi': (('ratei', 'risconti'), re.compile(r"^E[.)]?$", re.I)),
    }
    try:
        doc = fitz.open(file_path)
    except Exception:
        return current, prior
    cleared: List[Tuple[str, str]] = []
    try:
        selected_sp_pages, _ = find_section_pages(file_path)
    except Exception:
        selected_sp_pages = set()
    document_centers = _document_comparative_centers(doc)
    try:
        for page in doc:
            if selected_sp_pages and page.number not in selected_sp_pages:
                continue
            words = page.get_text('words', sort=True)
            # Some statement pages repeat the two numeric columns but not the
            # date header.  Reuse only a document-level pair proven by another
            # page of the same comparative statement (budget_282/336/397).
            anchors = _page_column_anchors(words, document_centers)
            if anchors is None:
                continue

            for line in _text_line_groups(words):
                labels = [word for word in line if float(word[0]) < 350]
                label_text = ' '.join(str(word[4]).casefold() for word in labels)
                codes = _row_code_words(labels)
                for field, (required, code_re) in specs.items():
                    if not all(token in label_text for token in required):
                        continue
                    if not any(code_re.fullmatch(code) for code in codes):
                        continue
                    numbers = [
                        word for word in line
                        if float(word[0]) > 350
                        and _GEOMETRIC_NUMBER_RE.fullmatch(str(word[4]).strip())
                    ]
                    current_numbers, prior_numbers = _split_current_prior(
                        numbers, anchors
                    )
                    if current_numbers or not prior_numbers:
                        continue
                    parsed = [_parse_it_number(str(word[4])) for word in prior_numbers]
                    parsed = [value for value in parsed if value is not None]
                    if not parsed or any(value != parsed[0] for value in parsed[1:]):
                        continue
                    extracted = current.get(field, Decimal('0'))
                    if (
                        parsed[0] == 0
                        or extracted == 0
                        or abs(abs(extracted) - abs(parsed[0])) > _PRIOR_CELL_MATCH_TOL
                    ):
                        continue
                    current[field] = Decimal('0')
                    if prior:
                        prior[field] = parsed[0]
                    cleared.append((field, str(parsed[0])))
    finally:
        doc.close()
    if cleared:
        logger.warning(
            "SP column geometry: cleared prior-only cells from current year: %s",
            cleared,
        )
    return current, prior


# Voci di SP che l'estrattore lineare puo' perdere per intero pur essendo
# STAMPATE, e che si rileggono dalla riga di prospetto senza dedurre nulla.
# ``E) Ratei e risconti`` del passivo e' l'unica registrata perche' e' l'unica
# provata: sul bilancio riclassificato UE di AMB AMBIENTA sp18 usciva 0 contro
# 178.663,25 stampati, mentre il ``D)`` dell'attivo arrivava regolarmente in sp10.
# La lettera di voce distingue i due lati (art. 2424: D attivo, E passivo), le due
# parole obbligatorie distinguono la voce di legge dai suoi conti di dettaglio
# ("RATEI PASSIVI", "RISCONTI PASSIVI", che ne portano una sola).
_MISSING_SP_ROWS = {
    'sp18_ratei_risconti_passivi': (
        re.compile(r"^E[.)]?$", re.I),
        ('ratei', 'risconti'),
    ),
}


def _recover_printed_sp_rows(
    file_path: str, current_bs: Dict[str, Decimal]
) -> Dict[str, Decimal]:
    """Rilegge dalla fonte una voce di SP stampata che l'estrazione ha perso.

    E' un RIPIEGO, non un tappo: l'importo esiste, e' stampato nella colonna
    dell'anno corrente della propria riga di prospetto e viene letto li'. Nessun
    valore viene mai ricavato da un divario di quadratura, e la voce viene toccata
    solo quando l'estrazione la dichiara a zero: un importo gia' estratto, anche
    diverso, resta com'e' (e il divario lo dichiara `_unclassified_mass`).
    """
    current = dict(current_bs)
    try:
        doc = fitz.open(file_path)
    except Exception:
        return current
    try:
        selected_sp_pages, _ = find_section_pages(file_path)
    except Exception:
        selected_sp_pages = set()
    recovered: List[Tuple[str, str]] = []
    document_centers = _document_comparative_centers(doc)
    try:
        for page in doc:
            if selected_sp_pages and page.number not in selected_sp_pages:
                continue
            words = page.get_text('words', sort=True)
            anchors = _page_column_anchors(words, document_centers)
            for line in _text_line_groups(words):
                labels = [word for word in line if float(word[0]) < 350]
                label_text = ' '.join(str(word[4]).casefold() for word in labels)
                codes = _row_code_words(labels)
                if not codes:
                    continue
                numbers = [
                    word for word in line
                    if float(word[0]) > 350
                    and _GEOMETRIC_NUMBER_RE.fullmatch(str(word[4]).strip())
                ]
                if not numbers:
                    continue
                for field, (code_re, required_words) in _MISSING_SP_ROWS.items():
                    if current.get(field, Decimal('0')) != 0:
                        continue
                    if not all(token in label_text for token in required_words):
                        continue
                    if not any(code_re.fullmatch(code) for code in codes):
                        continue
                    if anchors is not None:
                        candidates, _ = _split_current_prior(numbers, anchors)
                    else:
                        # Colonna unica: la riga porta un solo importo, che e'
                        # quello dell'anno stampato. Piu' di uno senza ancore di
                        # colonna e' ambiguo e non si tocca nulla.
                        candidates = list(numbers)
                    parsed = [_parse_it_number(str(word[4])) for word in candidates]
                    parsed = [value for value in parsed if value is not None]
                    if not parsed or any(value != parsed[0] for value in parsed[1:]):
                        continue
                    if parsed[0] == 0:
                        continue
                    current[field] = parsed[0]
                    recovered.append((field, str(parsed[0])))
    finally:
        doc.close()
    if recovered:
        logger.warning(
            "SP source recovery: voci stampate assenti dall'estrazione, rilette "
            "dalla riga di prospetto: %s", recovered,
        )
    return current


# D) Debiti dell'art. 2424: numero di voce di legge -> (sotto-campo entro,
# sotto-campo oltre). I numeri di voce sono statutari e identici su ogni
# bilancio italiano, quindi la mappa e' un dato di legge, non un'euristica.
# Le voci senza un sotto-campo proprio (6 acconti, 8 titoli di credito, 9-11-bis
# gruppo, 14 altri debiti) finiscono nel secchio generico: mai sull'aggregato,
# perche' `projection_common.base_bank_debt` assegna alle BANCHE qualunque
# scarto fra sp16/sp17 e la somma dei loro dettagli, e il residuo diventa debito
# bancario fantasma con tanto di piano di rimborso.
_DEBT_ITEM_FIELDS = {
    '1': ('sp16c_debiti_obbligazioni_breve', 'sp17c_debiti_obbligazioni_lungo'),
    '2': ('sp16c_debiti_obbligazioni_breve', 'sp17c_debiti_obbligazioni_lungo'),
    '3': ('sp16b_debiti_altri_finanz_breve', 'sp17b_debiti_altri_finanz_lungo'),
    '4': ('sp16a_debiti_banche_breve', 'sp17a_debiti_banche_lungo'),
    '5': ('sp16b_debiti_altri_finanz_breve', 'sp17b_debiti_altri_finanz_lungo'),
    '7': ('sp16d_debiti_fornitori_breve', 'sp17d_debiti_fornitori_lungo'),
    '12': ('sp16e_debiti_tributari_breve', 'sp17e_debiti_tributari_lungo'),
    '13': ('sp16f_debiti_previdenza_breve', 'sp17f_debiti_previdenza_lungo'),
}
_DEBT_GENERIC_FIELDS = ('sp16g_altri_debiti_breve', 'sp17g_altri_debiti_lungo')
_DEBT_DETAIL_FIELDS = tuple(sorted({
    field
    for pair in list(_DEBT_ITEM_FIELDS.values()) + [_DEBT_GENERIC_FIELDS]
    for field in pair
}))
_DEBT_SECTION_CODE_RE = re.compile(r"^D[.)]?[,]?$", re.I)
_SECTION_CODE_RE = re.compile(r"^[A-Z][.)]?[,]?$", re.I)
_DEBT_ITEM_CODE_RE = re.compile(
    r"^(\d+(?:-(?:bis|ter|quater|quinquies))?)\)[,]?$", re.I
)


def _row_current_amount(line, anchors: _ColumnAnchors) -> Optional[Decimal]:
    """L'importo della colonna dell'anno CORRENTE di una riga di prospetto.

    ``None`` quando la riga non ne porta uno, o quando le celle attribuite a
    quella colonna non concordano: un'ambiguita' non si risolve scegliendo.
    """
    numbers = [
        word for word in line
        if float(word[0]) > 350
        and _GEOMETRIC_NUMBER_RE.fullmatch(str(word[4]).strip())
    ]
    if not numbers:
        return None
    current_numbers, _ = _split_current_prior(numbers, anchors)
    parsed = [_parse_it_number(str(word[4])) for word in current_numbers]
    parsed = [value for value in parsed if value is not None]
    if not parsed or any(value != parsed[0] for value in parsed[1:]):
        return None
    return parsed[0]


def _split_printed_debt_maturities(
    file_path: str, current_bs: Dict[str, Decimal]
) -> Dict[str, Decimal]:
    """Rilegge la ripartizione entro/oltre del D) Debiti dove il documento la stampa.

    Il totale dei debiti puo' quadrare mentre la RIPARTIZIONE e' sbagliata:
    ``sp16`` e ``sp17`` stanno entrambi nel passivo, quindi nessuna quadratura
    vede lo spostamento. Lo vedono CCN, current ratio e il circolante di Altman
    — e spostare debito dal breve al lungo fa risultare gli indici di liquidita'
    MIGLIORI del vero. E' un errore che attraversa un confine di KPI.

    Il blocco pero' si auto-valida: le righe ``- entro`` / ``- oltre`` stampate
    cross-footano al ``D) Debiti`` stampato. Questa lettura ha quindi il proprio
    totale di controllo e non deve fidarsi dell'estrazione LLM. E' un RIPIEGO
    lecito, non un plug: la massa e' stampata e letta nella propria riga, e
    senza il cross-foot non si tocca nulla — resta allora la regola prudenziale,
    debito senza scadenza dichiarata a breve.
    """
    current = dict(current_bs)
    try:
        doc = fitz.open(file_path)
    except Exception:
        return current
    try:
        selected_sp_pages, _ = find_section_pages(file_path)
    except Exception:
        selected_sp_pages = set()
    document_centers = _document_comparative_centers(doc)
    printed_total: Optional[Decimal] = None
    per_field: Dict[str, Decimal] = {}
    entro_total = oltre_total = Decimal('0')
    item: Optional[str] = None
    in_debiti = closed = False
    try:
        for page in doc:
            if closed:
                break
            if selected_sp_pages and page.number not in selected_sp_pages:
                continue
            words = page.get_text('words', sort=True)
            anchors = _page_column_anchors(words, document_centers)
            if anchors is None:
                continue
            for line in _text_line_groups(words):
                labels = [word for word in line if float(word[0]) < 350]
                label_text = ' '.join(str(word[4]).casefold() for word in labels)
                codes = _row_code_words(labels)
                code = codes[0] if codes else ''
                amount = _row_current_amount(line, anchors)
                if not in_debiti:
                    # La lettera di voce distingue i due lati (art. 2424: D
                    # attivo = ratei e risconti, D passivo = debiti), e la
                    # parola "debiti" distingue l'una dall'altra.
                    if (
                        _DEBT_SECTION_CODE_RE.fullmatch(code)
                        and 'debiti' in label_text
                        and 'ratei' not in label_text
                        and amount is not None
                    ):
                        in_debiti, printed_total = True, amount
                    continue
                if _SECTION_CODE_RE.fullmatch(code) and code[0].upper() != 'D':
                    # La lettera di voce successiva chiude la sezione. Le
                    # scadenze dei CREDITI stanno fuori di qui, e restano fuori.
                    closed = True
                    break
                item_match = _DEBT_ITEM_CODE_RE.fullmatch(code)
                if item_match:
                    item = item_match.group(1).casefold()
                    continue
                if item is None or amount is None:
                    continue
                if 'esercizio successivo' not in label_text:
                    continue
                if 'entro' in label_text:
                    index = 0
                elif 'oltre' in label_text:
                    index = 1
                else:
                    continue
                field = _DEBT_ITEM_FIELDS.get(item, _DEBT_GENERIC_FIELDS)[index]
                per_field[field] = per_field.get(field, Decimal('0')) + amount
                if index == 0:
                    entro_total += amount
                else:
                    oltre_total += amount
    finally:
        doc.close()

    if printed_total is None or not per_field:
        return current
    if abs(entro_total + oltre_total - printed_total) > Decimal('0.01'):
        logger.warning(
            "Scadenze D) Debiti ignorate: le righe entro/oltre stampate sommano "
            "%s contro %s del totale stampato. Senza cross-foot questa lettura "
            "non ha un totale di controllo, e una ripartizione senza prova "
            "sarebbe inventata: si tiene quella dell'estrazione.",
            entro_total + oltre_total, printed_total,
        )
        return current

    for field in _DEBT_DETAIL_FIELDS:
        current[field] = per_field.get(field, Decimal('0'))
    current['sp16_debiti_breve'] = entro_total
    current['sp17_debiti_lungo'] = oltre_total
    logger.warning(
        "Scadenze D) Debiti rilette dalle righe stampate (cross-foot %s sul "
        "totale stampato): sp16=%s, sp17=%s",
        printed_total, entro_total, oltre_total,
    )
    return current


# Le quattro voci di legge che il layout riclassificato stampa con il proprio
# dettaglio, e i sotto-campi dell'art. 2424 in cui va ciascun numero di voce.
# Il numero di voce e' statutario; a distinguere i due `I.` (Immobilizzazioni
# Immateriali e Rimanenze) e' l'ETICHETTA, mai il solo numero romano — e
# "materiali" e' una sottostringa di "immateriali", quindi nemmeno la sola
# parola basta: serve la coppia (numero romano, parole obbligatorie).
_FIXED_ASSET_SECTIONS = (
    (
        'sp02_immob_immateriali',
        re.compile(r"^I[.)]?[,]?$"),
        ('immobilizzazioni', 'immateriali'),
        {
            '1': 'sp02a_costi_impianto', '2': 'sp02b_costi_sviluppo',
            '3': 'sp02c_brevetti', '4': 'sp02d_concessioni',
            '5': 'sp02e_avviamento', '6': 'sp02f_immob_in_corso',
            '7': 'sp02g_altre_immob_imm',
        },
        'sp02g_altre_immob_imm',
    ),
    (
        'sp03_immob_materiali',
        re.compile(r"^II[.)]?[,]?$"),
        ('immobilizzazioni', 'materiali'),
        {
            '1': 'sp03a_terreni_fabbricati', '2': 'sp03b_impianti_macchinari',
            '3': 'sp03c_attrezzature', '4': 'sp03d_altri_beni',
            '5': 'sp03e_immob_in_corso',
        },
        'sp03d_altri_beni',
    ),
    (
        'sp04_immob_finanziarie',
        re.compile(r"^III[.)]?[,]?$"),
        ('immobilizzazioni', 'finanziarie'),
        # B.III.2 «crediti» ha entro/oltre e il documento non li separa a
        # questo livello: vanno all'OLTRE. E' il verso prudenziale per un
        # credito — l'opposto di quello dei debiti — perche' anticiparne
        # l'incasso abbellirebbe la liquidita' invece di peggiorarla.
        {
            '1': 'sp04a_partecipazioni', '2': 'sp04c_crediti_immob_lungo',
            '3': 'sp04d_altri_titoli', '4': 'sp04e_strumenti_derivati_attivi',
        },
        'sp04d_altri_titoli',
    ),
    (
        'sp05_rimanenze',
        re.compile(r"^I[.)]?[,]?$"),
        ('rimanenze',),
        {
            '1': 'sp05a_materie_prime', '2': 'sp05b_prodotti_in_corso',
            '3': 'sp05c_lavori_in_corso', '4': 'sp05d_prodotti_finiti',
            '5': 'sp05e_acconti',
        },
        'sp05e_acconti',
    ),
)
_ROMAN_CODE_RE = re.compile(r"^(?:I{1,3}|IV|VI{0,3}|IX|X)[.)]?[,]?$")
_STATUTORY_ITEM_CODE_RE = re.compile(
    r"^(\d+(?:-(?:bis|ter|quater|quinquies))?)\)[,]?$", re.I
)


def _recover_printed_fixed_asset_details(
    file_path: str, current_bs: Dict[str, Decimal]
) -> Dict[str, Decimal]:
    """Rilegge i sotto-campi di immobilizzazioni e rimanenze dove sono STAMPATI.

    Sullo schema di legge puro le immobilizzazioni sono nette per definizione e
    non c'e' nulla da spacchettare; questo layout invece stampa la gerarchia
    completa, con il costo storico e il fondo ammortamento di ciascun cespite e
    con la riga di voce di legge GIA' NETTA (``4) Concessioni…`` vale 48.618,07,
    cioe' 61.605,00 meno 12.986,93). Si legge quella riga, e non i conti
    sottostanti: si sommano i mastri OPPURE le foglie, mai entrambi.

    Senza i sotto-campi ``hierarchy_consistent`` fallisce anche su
    un'estrazione pulita, quindi ``semantic_valid`` e ``forecastable`` restano
    falsi e la proiezione non parte.

    Il controllo e' il totale che il documento stampa per la voce: i dettagli
    letti devono cross-footare a quello. Senza, non si scrive nulla —
    ``sp02``/``sp03``/``sp04`` sono ``TIER0_FIELDS`` e non sono mai una
    destinazione di ripiego: il buco si colma leggendo i dettagli, non
    redistribuendo l'aggregato.
    """
    current = dict(current_bs)
    try:
        doc = fitz.open(file_path)
    except Exception:
        return current
    try:
        selected_sp_pages, _ = find_section_pages(file_path)
    except Exception:
        selected_sp_pages = set()
    document_centers = _document_comparative_centers(doc)
    # Una voce per volta: aggregato -> (totale stampato, {campo: importo}).
    letti: Dict[str, Tuple[Decimal, Dict[str, Decimal]]] = {}
    sezione: Optional[Tuple[str, Dict[str, str], str]] = None
    printed_total = Decimal('0')
    voci: Dict[str, Decimal] = {}

    def _chiudi():
        if sezione is not None and voci:
            letti[sezione[0]] = (printed_total, dict(voci))

    try:
        for page in doc:
            if selected_sp_pages and page.number not in selected_sp_pages:
                continue
            words = page.get_text('words', sort=True)
            anchors = _page_column_anchors(words, document_centers)
            if anchors is None:
                continue
            for line in _text_line_groups(words):
                labels = [word for word in line if float(word[0]) < 350]
                label_text = ' '.join(str(word[4]).casefold() for word in labels)
                codes = _row_code_words(labels)
                code = codes[0] if codes else ''
                amount = _row_current_amount(line, anchors)

                aperta = None
                for aggregate, roman_re, required, fields, generic in _FIXED_ASSET_SECTIONS:
                    if not roman_re.fullmatch(code):
                        continue
                    if not all(token in label_text for token in required):
                        continue
                    if aggregate == 'sp03_immob_materiali' and 'immateriali' in label_text:
                        continue
                    aperta = (aggregate, fields, generic, amount)
                    break
                if aperta is not None:
                    _chiudi()
                    sezione = aperta[:3]
                    printed_total = aperta[3] if aperta[3] is not None else Decimal('0')
                    voci = {}
                    continue

                if sezione is None:
                    continue
                # Un altro numero romano o una lettera di voce chiudono il blocco.
                if _ROMAN_CODE_RE.fullmatch(code) or _SECTION_CODE_RE.fullmatch(code):
                    _chiudi()
                    sezione, voci, printed_total = None, {}, Decimal('0')
                    continue
                item_match = _STATUTORY_ITEM_CODE_RE.fullmatch(code)
                if item_match is None or amount is None:
                    # "Costo storico", "Fondo ammortamento" e le righe di conto
                    # sono la stessa massa vista a un altro livello: entrano nel
                    # totale della voce, non accanto ad esso.
                    continue
                field = sezione[1].get(item_match.group(1).casefold(), sezione[2])
                voci[field] = voci.get(field, Decimal('0')) + amount
        _chiudi()
    finally:
        doc.close()

    recovered: List[Tuple[str, str]] = []
    for aggregate, (total, fields) in letti.items():
        somma = sum(fields.values(), Decimal('0'))
        if total <= 0 or abs(somma - total) > Decimal('0.01'):
            logger.warning(
                "Dettaglio di %s ignorato: le voci stampate sommano %s contro %s "
                "del totale di voce stampato. Senza cross-foot mancherebbe il "
                "controllo, e un TIER0 non si riempie per differenza.",
                aggregate, somma, total,
            )
            continue
        if any(current.get(field, Decimal('0')) != 0 for field in fields):
            # Un dettaglio gia' estratto non si sovrascrive: il divario lo
            # dichiara `_unclassified_mass`, non lo corregge questa funzione.
            continue
        for field, value in fields.items():
            current[field] = value
            recovered.append((field, str(value)))
        current[aggregate] = total
    if recovered:
        logger.warning(
            "SP source recovery: sotto-campi di immobilizzazioni/rimanenze riletti "
            "dalle righe di voce stampate: %s", recovered,
        )
    return current


def find_section_pages(file_path: str) -> Tuple[Set[int], Set[int]]:
    """
    Scan PDF pages with PyMuPDF to find SP and CE sections using
    range-based detection (start anchor → end anchor).

    IV CEE structure:
      SP starts: "Stato patrimoniale" + "Attivo" on same page
      SP ends:   "Totale passivo"
      CE starts: "Conto economico" + "Valore della produzione" on same page
      CE ends:   "Totale delle imposte sul reddito" or "21) Utile (perdita)"

    Returns:
        (sp_pages, ce_pages) - sets of zero-based page indices
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise PDFImportError(f"Cannot open PDF file: {e}")

    total_pages = len(doc)
    logger.info(f"PDF has {total_pages} pages")

    # Scan all pages and cache lowercased text.
    # Collapse spaced-out text (e.g. "S T A T O" → "STATO") for keyword matching
    # (Dylog format uses spaced headers).
    def _normalize_for_search(text: str) -> str:
        lowered = text.lower()
        lowered = re.sub(r'\b(\w) (?=\w\b)', r'\1', lowered)  # "s t a t o" → "stato"
        # Collapse a spaced dash used as a label separator so section-total
        # keywords match regardless of it: "totale stato patrimoniale - passivo"
        # → "totale stato patrimoniale passivo" (some gestionali print the
        # closing total with a " - PASSIVO" suffix; without this the SP_END
        # anchor is missed and the CE bleeds into the SP page range). Only the
        # spaced form is touched, so account codes like "d-bis" are preserved.
        lowered = re.sub(r' [-–—] ', ' ', lowered)
        lowered = re.sub(r' {2,}', ' ', lowered)               # collapse multi-spaces
        return lowered

    page_texts = []
    for page_num in range(total_pages):
        page_texts.append(_normalize_for_search(doc[page_num].get_text()))
    doc.close()

    def _find_start(start_kws, after_page=0):
        """Find first page where ALL start keywords are present."""
        for i in range(after_page, total_pages):
            if all(kw in page_texts[i] for kw in start_kws):
                return i
        return None

    def _find_end(end_kws, from_page):
        """Find first page (from from_page onward) where ANY end keyword is present."""
        for i in range(from_page, total_pages):
            if any(kw in page_texts[i] for kw in end_kws):
                return i
        return None

    # --- SP range ---
    sp_start = _find_start(SP_START_KEYWORDS)
    # Relaxed SP start (sezioni contrapposte / "dettaglio voci"): some layouts have a
    # "Stato patrimoniale" header but no plain "Attivo" token (they use ATTIVITA' /
    # column headers), so the strict two-keyword match fails and the SP section text
    # never reaches the LLM (empty BS — budget_249/188). Fall back to the
    # "stato patrimoniale" header alone, on the FIRST page that has it and is not a CE
    # page (avoid matching a running "...Conto Economico a Sezioni Contrapposte" header).
    # "situazione patrimoniale" is the SP header used by some trial-balance / "bilancio
    # di verifica" printouts that have no "Stato patrimoniale"/"Attivo" tokens at all.
    _SP_HEADER_VARIANTS = ('stato patrimoniale', 'situazione patrimoniale')
    if sp_start is None:
        for i in range(total_pages):
            t = page_texts[i]
            if any(h in t for h in _SP_HEADER_VARIANTS) and 'conto economico' not in t:
                sp_start = i
                break
        # If every page carries a combined SP+CE running header, accept the first
        # SP-header page regardless (better than the first-6-pages last resort).
        if sp_start is None:
            for i in range(total_pages):
                if any(h in page_texts[i] for h in _SP_HEADER_VARIANTS):
                    sp_start = i
                    break
    sp_end = None
    if sp_start is not None:
        sp_end = _find_end(SP_END_KEYWORDS, sp_start)
        if sp_end is None:
            # Nessun "Totale passivo" stampato. Il default storico (sp_start + 2)
            # e' una TAGLIA, non un'ancora: su un prospetto piu' lungo di tre
            # pagine chiude la sezione patrimoniale a meta' del passivo e la coda
            # non arriva mai al prompt. Sul bilancio riclassificato UE di AMB
            # AMBIENTA (che i totali di sezione li stampa nell'intestazione, non
            # in coda) "E) Ratei e risconti" 178.663,25 sta a pagina 4 e spariva:
            # sp18 restava 0 mentre il "D) Ratei e risconti" dell'attivo, a
            # pagina 2, arrivava regolarmente in sp10.
            # L'ancora onesta e' il documento stesso: la sezione patrimoniale
            # finisce dove comincia quella economica. La pagina che apre il CE e'
            # INCLUSA perche' su questi layout porta ancora le ultime righe del
            # passivo (ed e' la stessa condivisione che il ramo `ce_start`
            # qui sotto gia' ammette nel verso opposto).
            ce_header_page = _find_start(CE_START_KEYWORDS, after_page=sp_start + 1)
            if ce_header_page is not None and ce_header_page > sp_start:
                logger.warning(
                    "Nessun totale di chiusura del passivo stampato: la sezione SP "
                    "si chiude alla pagina che apre il CE (%s) invece che a %s",
                    ce_header_page + 1, min(sp_start + 2, total_pages - 1) + 1,
                )
                sp_end = ce_header_page
            else:
                sp_end = min(sp_start + 2, total_pages - 1)

    # --- CE range ---
    # CE start: search after SP start to avoid re-matching the SP header page.
    # Strategy: try strict match first (both "conto economico" + "valore della produzione"),
    # then try "valore della produzione" alone after SP end (Dylog format puts VP on last
    # SP page without a "conto economico" header until a later page).
    ce_after = (sp_start + 1) if sp_start is not None else 0
    # Compact filings can start the CE on the very page that closes the SP.  Prefer
    # that source page before searching later pages; otherwise a second statement
    # quoted inside the Nota Integrativa can be selected (budget_336).
    ce_start = (
        sp_end
        if sp_end is not None
        and all(keyword in page_texts[sp_end] for keyword in CE_START_KEYWORDS)
        else _find_start(CE_START_KEYWORDS, after_page=ce_after)
    )
    # If CE start not found after SP, try from the beginning (SP may not exist)
    if ce_start is None and ce_after > 0:
        ce_start = _find_start(CE_START_KEYWORDS)
    # Relaxed: try "valore della produzione" alone after SP end (Dylog)
    if ce_start is None and sp_end is not None:
        ce_start = _find_start(["valore della produzione"], after_page=sp_end)

    # Relaxed (sezioni contrapposte / "dettaglio voci" CE): some layouts have NO
    # "valore della produzione" line at all — the CE is presented as two columns
    # (RICAVI / COSTI) under a "Conto economico" header. Detect the CE section by the
    # ricavi+costi column markers on a page after the SP section, so the CE text
    # actually reaches the LLM (otherwise CE comes back all zeros — budget_188/338/135).
    def _has_ce_columns(page_text: str) -> bool:
        has_rev = ('ricavi' in page_text or 'ricavo' in page_text)
        has_cost = ('costi' in page_text or 'costo' in page_text)
        # require a CE section header on the page to avoid matching SP pages that
        # merely mention "costi"/"ricavi" in a line description
        has_ce_header = 'conto economico' in page_text
        return has_rev and has_cost and has_ce_header

    if ce_start is None:
        search_from = (sp_end + 1) if sp_end is not None else (
            (sp_start + 1) if sp_start is not None else 0
        )
        for i in range(search_from, total_pages):
            if _has_ce_columns(page_texts[i]):
                ce_start = i
                break
        # If nothing after SP end, retry across the whole document (CE may share a page
        # with the SP tail in very compact statements)
        if ce_start is None:
            for i in range(total_pages):
                if _has_ce_columns(page_texts[i]):
                    ce_start = i
                    break

    ce_end = None
    if ce_start is not None:
        # Search from ce_start+1 to skip "utile (perdita)" in SP equity on the same page.
        # Try primary (item 21 with prefix) first, then fall back to imposte/generic.
        ce_end = _find_end(CE_END_KEYWORDS_PRIMARY, ce_start + 1)
        if ce_end is None:
            ce_end = _find_end(CE_END_KEYWORDS_FALLBACK, ce_start + 1)
        if ce_end is None:
            ce_end = min(ce_start + 3, total_pages - 1)

    # Build page sets from ranges
    def _range_to_set(start, end):
        if start is None or end is None:
            return set()
        return set(range(start, end + 1))

    sp_pages = _range_to_set(sp_start, sp_end)
    ce_pages = _range_to_set(ce_start, ce_end)

    # Zeroed-leading-section guard (draft "provvisorio" PDFs — budget_355/356):
    # some exports render the IV-CEE schema (labels + SP/CE headers) with every amount
    # at "0,00" up front, then put the REAL figures on later pages with no section
    # header. The header-based detection locks onto the zero copy and the LLM only ever
    # sees zeros (→ empty BS, "does not balance"). This is SAFE to correct because it
    # only fires when the selected SP pages carry a negligible amount mass compared with
    # the largest data page in the document (a normal IV-CEE statement never satisfies
    # that — its SP pages hold real totals): we slide the SP/CE windows forward, by the
    # same offset, onto the first later page that begins a substantial data block.
    def _page_amount_mass(text: str) -> float:
        s = 0.0
        # Cerved statements often print rounded totals as Italian integers
        # (``469.102``), with no decimal comma.  Ignoring those values made a real
        # SP page look empty and could relocate the section into the notes
        # (budget_272).  The boundaries deliberately exclude dates and fractions.
        amount_re = re.compile(
            r'(?<![\d/])(?:-?\d[\d.]*,\d{2}|-?\d{1,3}(?:\.\d{3})+)(?![\d/])'
        )
        for tok in amount_re.findall(text):
            try:
                s += abs(float(tok.replace('.', '').replace(',', '.')))
            except ValueError:
                continue
        return s

    page_mass = [_page_amount_mass(t) for t in page_texts]
    doc_max_mass = max(page_mass) if page_mass else 0.0
    sp_mass = sum(page_mass[p] for p in sp_pages)
    selected_sp_text = ' '.join(page_texts[p] for p in sorted(sp_pages))
    selected_sp_has_controls = (
        'totale attivo' in selected_sp_text
        and 'totale passivo' in selected_sp_text
    )
    if (
        sp_pages
        and not selected_sp_has_controls
        and doc_max_mass > 0
        and sp_mass < 0.02 * doc_max_mass
    ):
        # Only relocate to a GENUINE second copy of the statement that re-states the SP
        # header AND carries real amounts. We deliberately do NOT relocate to a headerless
        # number-only data block (e.g. a coordinate-split account dump like budget_355):
        # the IV-CEE LLM cannot map those columns, so masking them as a "result" would be
        # worse than failing honestly. Such files must fall through to the honest
        # "does not balance" error / a dedicated deterministic parser.
        second_start = next(
            (i for i in range(max(sp_pages) + 1, total_pages)
             if all(kw in page_texts[i] for kw in SP_START_KEYWORDS)
             and page_mass[i] >= 0.20 * doc_max_mass),
            None,
        )
        if second_start is not None:
            delta = second_start - min(sp_pages)
            shifted_sp = {min(p + delta, total_pages - 1) for p in sp_pages}
            shifted_ce = {min(p + delta, total_pages - 1) for p in ce_pages}
            logger.warning(
                f"Zeroed leading section detected (sp_mass={sp_mass:.0f} vs "
                f"doc_max={doc_max_mass:.0f}); a real second copy starts at page "
                f"{second_start}; shifting SP/CE windows by {delta} pages "
                f"(SP {sorted(sp_pages)}->{sorted(shifted_sp)})"
            )
            sp_pages = shifted_sp
            ce_pages = shifted_ce or ce_pages

    # Fallback: if range-based detection fails, try single-keyword matching + ±1 expansion
    if not sp_pages or not ce_pages:
        logger.warning("Range-based detection incomplete, falling back to keyword matching")

        def _find_by_keywords(keywords):
            pages = set()
            for i, text in enumerate(page_texts):
                if any(kw in text for kw in keywords):
                    pages.add(i)
            return pages

        def _expand(pages):
            expanded = set()
            for p in pages:
                if p - 1 >= 0:
                    expanded.add(p - 1)
                expanded.add(p)
                if p + 1 < total_pages:
                    expanded.add(p + 1)
            return expanded

        if not sp_pages:
            sp_pages = _expand(_find_by_keywords(SP_FALLBACK_KEYWORDS))
        if not ce_pages:
            ce_pages = _expand(_find_by_keywords(CE_FALLBACK_KEYWORDS))

    # Last resort: first 6 pages
    if not sp_pages and not ce_pages:
        logger.warning("No SP/CE sections found, using first 6 pages as fallback")
        fallback = set(range(min(6, total_pages)))
        sp_pages = fallback
        ce_pages = fallback

    if not sp_pages:
        sp_pages = ce_pages
    if not ce_pages:
        ce_pages = sp_pages

    logger.info(f"SP pages: {sorted(sp_pages)}, CE pages: {sorted(ce_pages)}")
    return sp_pages, ce_pages


# ---------------------------------------------------------------------------
# Zucchetti IV Direttiva pre-filter
# ---------------------------------------------------------------------------

# Zucchetti account detail line: "100220 000 - description"
_ZUCCHETTI_ACCOUNT_RE = re.compile(r'^\s*\d{6}\s+\d{3}\s+-\s+')

# Bare numeric value: "(1.234)", "1.234.567", "0", "(0)" — with optional parens
_BARE_NUMBER_RE = re.compile(
    r'^\s*\(?\d[\d.]*\)?\s*$'
)

# Footer block lines (multi-line footer split across lines)
_ZUCCHETTI_FOOTER_WORDS = re.compile(
    r'^\s*(administrator|Data:|Ora:|Utente:|Pag\.|AGO\s*-|di\s*$|\d{2}-\d{2}-\d{4}$|\d{2}:\d{2}$|\d{2}\.\d{2}\.\d{2}$)',
    re.IGNORECASE
)

# Repeated page headers / metadata (appear at top of every page)
_ZUCCHETTI_PAGE_HEADER_RE = re.compile(
    r'^\s*(BILANCIO SCHEMA XBRL|Esercizio$|Dal$|Al$|'
    r'\d{4}/\d|Registrazioni fino al|'
    r'Schema$|Esteso$|Versione tassonomia|\d{8}$|'
    r'Regime Contabile|Tipo Reddito|Partita IVA|Codice Fiscale|'
    r'Impresa$|Ordinario$|Abbreviato$|'
    r'\d{2}-\d{2}-\d{4}$|\d{11}$|'  # dates and P.IVA/CF numbers
    r'Differenza arrotondamento unit)',
    re.IGNORECASE
)


def _is_zucchetti_format(text: str) -> bool:
    """Detect Zucchetti format by presence of account detail lines."""
    matches = sum(1 for line in text.splitlines()
                  if _ZUCCHETTI_ACCOUNT_RE.match(line))
    return matches >= 5


def _preprocess_zucchetti(text: str) -> str:
    """Strip Zucchetti detail account lines and their preceding values.

    Zucchetti layout puts the value on the line BEFORE the account detail:
        82.818                          ← value (to remove)
        100815 000 - impianti specifici ← account detail (to remove)
        ...
        Totale 2) impianti e macchinario  ← structural (to keep)
        146.992                            ← total value (to keep)

    Pass 1: mark indices of account lines and their preceding value lines.
    Pass 2: remove marked lines + footer/header noise.
    """
    if not _is_zucchetti_format(text):
        return text

    lines = text.splitlines()

    # Pass 1: find lines to remove (account details + their preceding values)
    remove = set()
    for i, line in enumerate(lines):
        if _ZUCCHETTI_ACCOUNT_RE.match(line):
            remove.add(i)
            # Also remove preceding bare-number line(s)
            j = i - 1
            while j >= 0 and _BARE_NUMBER_RE.match(lines[j]):
                remove.add(j)
                j -= 1

    # Pass 2: also mark footer block lines for removal.
    # Footer pattern spans multiple lines; mark the full block by scanning for
    # known trigger words and eating surrounding bare-number lines (page numbers).
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _ZUCCHETTI_FOOTER_WORDS.match(stripped):
            remove.add(i)
            # Eat adjacent bare single/double-digit lines (page num, total pages)
            for j in (i - 1, i + 1):
                if 0 <= j < len(lines) and re.match(r'^\s*\d{1,2}\s*$', lines[j]):
                    remove.add(j)

    # Pass 3: filter remaining lines, dropping repeated page headers
    # Track company name to allow first occurrence but skip repeats
    company_name = None
    seen_section_header = False
    section_header_count = 0
    filtered = []
    for i, line in enumerate(lines):
        if i in remove:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if _ZUCCHETTI_PAGE_HEADER_RE.match(stripped):
            continue
        # Track section headers (STATO PATRIMONIALE / CONTO ECONOMICO)
        is_section = stripped.startswith('STATO PATRIMONIALE') or stripped.startswith('CONTO ECONOMICO')
        if is_section:
            section_header_count += 1
            if not seen_section_header:
                seen_section_header = True
            elif section_header_count > 1:
                continue  # skip repeated section headers from later pages
        # Keep company name only on first occurrence
        if company_name is None and not seen_section_header:
            if not _BARE_NUMBER_RE.match(stripped):
                company_name = stripped
                filtered.append(line)
                continue
        elif stripped == company_name:
            continue  # skip repeated company name
        filtered.append(line)

    result = '\n'.join(filtered)
    logger.info(f"Zucchetti pre-filter: {len(text)} -> {len(result)} chars")
    return result


# ---------------------------------------------------------------------------
# Datev Koinos IV Direttiva pre-filter
# ---------------------------------------------------------------------------

# Datev Koinos account detail: standalone 5-11 digit code on its own line
_DATEV_ACCOUNT_CODE_STANDALONE_RE = re.compile(r'^\s*\d{5,11}\s*$')

# Datev Koinos account detail: code + description on same line (longer codes)
# e.g. "06015101010 Impianti generici" or "10030100910 IVA in compensazione..."
_DATEV_ACCOUNT_CODE_INLINE_RE = re.compile(r'^\s*\d{7,11}\s+\S')

# Standalone A/P/C/R flag (single letter on its own line)
_DATEV_FLAG_RE = re.compile(r'^\s*[APCR]\s*$')

# Footer: "Bilancio micro-imprese" or "Pagina X di Y"
_DATEV_FOOTER_RE = re.compile(
    r'^\s*(Bilancio micro-imprese|Pagina \d+ di \d+)',
    re.IGNORECASE
)

# Bare Italian-format number: "554,68", "24.383,23", "-13.541,08", "(1.234,56)", "0,00", "0"
_DATEV_BARE_NUMBER_RE = re.compile(
    r'^\s*[-\(]?\d[\d.]*(?:,\d{2})?\)?\s*$'
)

# Bare date on its own line (DD/MM/YYYY or DD.MM.YYYY)
_DATEV_BARE_DATE_RE = re.compile(r'^\s*\d{2}[/\.]\d{2}[/\.]\d{4}\s*$')


def _is_datev_koinos_format(text: str) -> bool:
    """Detect Datev Koinos format by account codes + A/P/C/R flag lines."""
    lines = text.splitlines()
    standalone = sum(1 for l in lines if _DATEV_ACCOUNT_CODE_STANDALONE_RE.match(l))
    inline = sum(1 for l in lines if _DATEV_ACCOUNT_CODE_INLINE_RE.match(l))
    flag_count = sum(1 for l in lines if _DATEV_FLAG_RE.match(l))
    # Need account codes (either type) AND standalone flags
    return (standalone + inline) >= 5 and flag_count >= 5


def _preprocess_datev_koinos(text: str) -> str:
    """Strip Datev Koinos account detail noise.

    Datev Koinos layout (after PyMuPDF extraction) has two variants:

    Variant A — short codes (5-7 digits) are standalone:
        54.164,31             ← subtotal value (KEEP)
        050101010             ← account code (remove)
        Spese di costituzione ← account description (remove)
        A                     ← flag (remove)
        67.705,39             ← detail value (remove)

    Variant B — long codes (7-11 digits) are inline with description:
        06015101010 Impianti generici  ← code+description (remove)
        A                              ← flag (remove)
        37.793,41                      ← detail value (remove)

    Both variants: after removing detail blocks, keep structural labels
    and subtotal values.
    """
    if not _is_datev_koinos_format(text):
        return text

    lines = text.splitlines()
    remove = set()

    for i, line in enumerate(lines):
        # Variant B: inline code+description (e.g. "06015101010 Impianti generici")
        if _DATEV_ACCOUNT_CODE_INLINE_RE.match(line):
            remove.add(i)
            # Next lines: flag (A/P/C/R), then value
            j = i + 1
            while j < len(lines) and j <= i + 2:
                s = lines[j].strip()
                if not s:
                    j += 1
                    continue
                if _DATEV_FLAG_RE.match(lines[j]):
                    remove.add(j)
                    if j + 1 < len(lines) and _DATEV_BARE_NUMBER_RE.match(lines[j + 1]):
                        remove.add(j + 1)
                    break
                j += 1
            continue

        # Variant A: standalone code (e.g. "050101010")
        if _DATEV_ACCOUNT_CODE_STANDALONE_RE.match(line):
            remove.add(i)
            # Remove following lines: description, flag, value
            j = i + 1
            while j < len(lines) and j <= i + 3:
                s = lines[j].strip()
                if not s:
                    j += 1
                    continue
                if _DATEV_FLAG_RE.match(lines[j]):
                    remove.add(j)
                    if j + 1 < len(lines) and _DATEV_BARE_NUMBER_RE.match(lines[j + 1]):
                        remove.add(j + 1)
                    break
                # Description line between code and flag — remove it
                # But don't eat structural lines (IV CEE labels)
                if re.match(r'^\s*\d+\)', s) or re.match(r'^\s*[A-E]\)', s) or 'Totale' in s:
                    break
                remove.add(j)
                j += 1

    # Also remove footers and bare dates
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _DATEV_FOOTER_RE.match(stripped):
            remove.add(i)
        if _DATEV_BARE_DATE_RE.match(stripped):
            remove.add(i)

    filtered = [line for i, line in enumerate(lines) if i not in remove and line.strip()]
    result = '\n'.join(filtered)
    logger.info(f"Datev Koinos pre-filter: {len(text)} -> {len(result)} chars")
    return result


# ---------------------------------------------------------------------------
# "Stampa dettaglio voci" pre-filter (accounting software detail report)
# ---------------------------------------------------------------------------

# Account code lines: "67.01.01.01", "84.01.01", "55.01.07" etc.
_STAMPA_DETAIL_ACCOUNT_RE = re.compile(
    r'^\s*\d{2}\.\d{2}\.\d{2}(?:\.\d{2})?\s*$'
)

# Detail value lines ending with D (Dare/debit) or A (Avere/credit)
_STAMPA_DETAIL_VALUE_RE = re.compile(
    r'^\s*[\d.,]+\s+[DA]\s*$'
)

# Page header pattern for this format
_STAMPA_PAGE_HEADER_RE = re.compile(
    r'^\s*(Data di stampa|Pagina|Dati generali|Sede legale:|Codice fiscale:|'
    r'Partita IVA:|Stampa dettaglio voci)\s*$',
    re.IGNORECASE
)

# "% Reddito" column header
_STAMPA_PERCENT_RE = re.compile(r'^\s*\d{1,3}\s{3,}$')


def _is_stampa_dettaglio_format(text: str) -> bool:
    """Detect 'Stampa dettaglio voci' format by account codes + D/A suffixes."""
    lines = text.splitlines()
    account_codes = sum(1 for l in lines if _STAMPA_DETAIL_ACCOUNT_RE.match(l))
    da_values = sum(1 for l in lines if _STAMPA_DETAIL_VALUE_RE.match(l))
    return account_codes >= 5 and da_values >= 5


def _preprocess_stampa_dettaglio(text: str) -> str:
    """Strip account-level detail from 'Stampa dettaglio voci' format.

    This format has IV CEE section headers (3.B.9, 1.C.2, etc.) with
    account-level details underneath. We keep section headers and totals,
    removing individual account lines and their D/A-suffixed values.

    Also removes repeated page headers and metadata.
    """
    if not _is_stampa_dettaglio_format(text):
        return text

    lines = text.splitlines()
    remove = set()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Remove account code lines (e.g., "67.01.01.01")
        if _STAMPA_DETAIL_ACCOUNT_RE.match(stripped):
            remove.add(i)
            # Also remove following description and value lines
            j = i + 1
            while j < len(lines) and j <= i + 3:
                s = lines[j].strip()
                if not s:
                    j += 1
                    continue
                if _STAMPA_DETAIL_VALUE_RE.match(s):
                    remove.add(j)
                    break
                # Description line between code and value
                if not s[0].isdigit() or '.' not in s[:5]:
                    remove.add(j)
                else:
                    break
                j += 1
            continue

        # Remove D/A value lines that weren't caught above
        if _STAMPA_DETAIL_VALUE_RE.match(stripped):
            remove.add(i)
            continue

        # Remove page headers
        if _STAMPA_PAGE_HEADER_RE.match(stripped):
            remove.add(i)
            continue

        # Remove "% Reddito" percentage values (e.g., "100   ", "80   ", "75   ")
        if _STAMPA_PERCENT_RE.match(stripped):
            remove.add(i)
            continue

    filtered = [line for i, line in enumerate(lines) if i not in remove and line.strip()]
    result = '\n'.join(filtered)
    logger.info(f"Stampa dettaglio pre-filter: {len(text)} -> {len(result)} chars")
    return result


def _strip_separator_noise(text: str) -> str:
    """Remove separator lines (-----, =====) and repeated page headers.

    Applies to Dylog and similar ERP printouts that insert ASCII separators
    and repeated header/footer lines on every page.
    """
    lines = text.splitlines()
    # Detect: if fewer than 5 separator lines, skip (probably not noisy)
    sep_count = sum(1 for l in lines if re.match(r'^\s*[-=]{5,}\s*$', l.strip()))
    if sep_count < 5:
        return text

    # Dylog repeated page header pattern
    _dylog_header_re = re.compile(
        r'^\s*(DATA\s*:|PAGINA Nr|Stampato con tecnologia|FISCOLASER|'
        r'DESCRIZIONE VOCE|ESER\.\s+\d)',
        re.IGNORECASE
    )

    filtered = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Remove separator lines
        if re.match(r'^[-=]{5,}$', stripped):
            continue
        # Remove repeated page headers
        if _dylog_header_re.match(stripped):
            continue
        # Remove bare page numbers (single digit on a line)
        if re.match(r'^\d{1,2}$', stripped):
            continue
        # Remove bare dates like 01/12/2025 on their own line
        if re.match(r'^\d{2}/\d{2}/\d{4}$', stripped):
            continue
        filtered.append(line)

    result = '\n'.join(filtered)
    logger.info(f"Separator noise filter: {len(text)} -> {len(result)} chars ({sep_count} separators removed)")
    return result


def extract_relevant_pages(file_path: str) -> Tuple[str, str]:
    """
    Open PDF with PyMuPDF, detect SP and CE pages by keywords,
    and return extracted text for each section.

    Returns:
        (sp_text, ce_text) - text from balance sheet and income statement pages
    """
    sp_pages, ce_pages = find_section_pages(file_path)

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise PDFImportError(f"Cannot open PDF file: {e}")

    detached_texts = _detached_value_page_texts(doc)
    def _page_text(page_index: int) -> str:
        if page_index in detached_texts:
            return detached_texts[page_index]
        page = doc[page_index]
        return _filter_difference_columns(page) or reading_order_text(page)

    sp_text = "\n".join(
        _page_text(p) for p in sorted(sp_pages)
    )
    ce_text = "\n".join(
        _page_text(p) for p in sorted(ce_pages)
    )
    doc.close()

    # Pre-filter ERP account detail lines (no-op for standard PDFs)
    sp_text = _preprocess_stampa_dettaglio(sp_text)
    ce_text = _preprocess_stampa_dettaglio(ce_text)
    sp_text = _preprocess_zucchetti(sp_text)
    ce_text = _preprocess_zucchetti(ce_text)
    sp_text = _preprocess_datev_koinos(sp_text)
    ce_text = _preprocess_datev_koinos(ce_text)

    # Strip separator lines and repeated headers (Dylog, etc.)
    sp_text = _strip_separator_noise(sp_text)
    ce_text = _strip_separator_noise(ce_text)

    logger.info(
        f"SP text: {len(sp_text)} chars, CE text: {len(ce_text)} chars"
    )
    return sp_text, ce_text


def build_subpdf(file_path: str, pages: Set[int]) -> str:
    """
    Build a smaller PDF containing only the specified pages using PyMuPDF.

    Args:
        file_path: Path to the original PDF
        pages: Set of zero-based page indices to include

    Returns:
        Path to the temporary sub-PDF file (caller must clean up)
    """
    try:
        src = fitz.open(file_path)
    except Exception as e:
        raise PDFImportError(f"Cannot open PDF file: {e}")

    dst = fitz.open()  # new empty PDF
    sorted_pages = sorted(pages)
    for p in sorted_pages:
        if p < len(src):
            dst.insert_pdf(src, from_page=p, to_page=p)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    dst.save(tmp.name)
    dst.close()
    src.close()

    logger.info(
        f"Built sub-PDF: {len(sorted_pages)} pages ({sorted_pages}) -> {tmp.name}"
    )
    return tmp.name


# ---------------------------------------------------------------------------
# Claude Haiku structured extraction
# ---------------------------------------------------------------------------

SP_SYSTEM_PROMPT = """You are an expert Italian accountant specializing in Bilancio IV CEE (Schema di Bilancio art. 2424 Codice Civile).

Extract the Stato Patrimoniale (balance sheet) values from the text below.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimal separators (1.234.567 = 1234567)
- Parentheses mean negative: (347.117) = -347117
- Trailing minus means negative: 347.117- = -347117
- Dash or empty = 0
- Return plain numbers without any formatting (no dots, no commas)
- All values in full euros (not thousands)

EXTRACTION RULES:
- Extract values EXACTLY as they appear: parentheses = negative, plain numbers = positive
- Do NOT flip signs - preserve the original sign from the PDF (e.g., losses, negative reserves)

CREDITI (in ATTIVO section, BEFORE "Totale attivo"):
- ONLY the C.II) Crediti of "Attivo circolante" go here. NEVER include B.III.2 "Crediti" (immobilized
  financial receivables): those belong to sp04_immob_finanziarie. Counting a B.III.2 credito here too
  double-counts it (it is already inside Immobilizzazioni) and unbalances the sheet by that amount.
- sp06_crediti_breve = SUM of ALL "esigibili entro l'esercizio successivo" amounts across the C.II crediti categories (verso clienti, tributari, verso altri, etc.)
  PLUS "imposte anticipate" (deferred tax assets) if shown as a separate line within C.II crediti
- sp07_crediti_lungo = SUM of ALL "esigibili oltre l'esercizio successivo" amounts across the C.II crediti categories (Attivo circolante only)
- CRITICAL: sp06 + sp07 MUST equal "Totale crediti" of C.II (Attivo circolante). If they don't, add the difference to sp06.
  Common cause: "imposte anticipate" is a separate line within crediti that must be included in sp06.
- If crediti are not split by maturity, put the TOTAL Crediti in sp06_crediti_breve and sp07=0

CREDITI — DEBTOR-TYPE BREAKDOWN (split each group into entro + oltre):
- For each C.II) Crediti sub-item, separate "entro l'esercizio successivo" (sp06*) from "oltre l'esercizio successivo" (sp07*).
- Map each OIC item to its bucket:
  * C.II.1 Crediti verso clienti             -> sp06a / sp07a
  * C.II.2 Crediti verso imprese controllate -> sp06b / sp07b
  * C.II.3 Crediti verso imprese collegate   -> sp06c / sp07c
  * C.II.4 Crediti verso controllanti + C.II.5 Crediti verso imprese sottoposte al controllo delle controllanti -> sp06d / sp07d
  * C.II.5-bis Crediti tributari             -> sp06e / sp07e
  * C.II.5-ter Imposte anticipate            -> sp06f / sp07f
  * C.II.5-quater Crediti verso altri        -> sp06g / sp07g
- CRITICAL: sp06a+sp06b+sp06c+sp06d+sp06e+sp06f+sp06g MUST equal sp06_crediti_breve.
- CRITICAL: sp07a+sp07b+sp07c+sp07d+sp07e+sp07f+sp07g MUST equal sp07_crediti_lungo.
- If a group is missing in the PDF, leave it at 0.
- If the PDF shows only "Totale crediti" without a breakdown, put everything in sp06g_crediti_altri_breve (or sp07g_crediti_altri_lungo for long-term) to match the aggregate — do NOT invent sub-totals.
- IMPORTANT: Do NOT confuse C.II Crediti (operating receivables in "Attivo circolante") with B.III.2 Crediti (immobilized financial receivables). Only extract C.II values here.

DEBITI (in PASSIVO section, AFTER "Totale attivo"):
- IMPORTANT: "entro/oltre" in the PASSIVO section refers to DEBTS, not credits
- First find TOTALE Debiti (D) — the sum of all debt categories. Put this exact line's value into `totale_debiti`.
- sp17_debiti_lungo: look for ALL "di cui esigibili oltre l'esercizio successivo" sub-lines
  under individual debt items (e.g., under "Debiti verso fornitori", under "Altri debiti", etc.)
  and SUM them. These "di cui" lines are indented sub-totals showing the long-term portion.
- sp16_debiti_breve = TOTALE Debiti (D) minus sp17_debiti_lungo
- CRITICAL: sp16 + sp17 MUST equal TOTALE Debiti (D). If they don't, recalculate sp16 as the difference.
- If debiti are not split by maturity at all, put TOTALE Debiti in sp16_debiti_breve and sp17=0

DEBITI — CREDITOR-TYPE BREAKDOWN (split each group into entro + oltre):
- For each debt item, separate "entro l'esercizio successivo" (sp16*) from "oltre l'esercizio successivo" (sp17*).
- Map each OIC item to its bucket:
  * D.4 Debiti verso banche                                    -> sp16a / sp17a
  * D.3 verso soci per finanziamenti + D.5 verso altri finanziatori -> sp16b / sp17b
  * D.1 Obbligazioni + D.2 Obbligazioni convertibili + D.8 rappresentati da titoli -> sp16c / sp17c
  * D.7 Debiti verso fornitori                                 -> sp16d / sp17d
  * D.12 Debiti tributari                                      -> sp16e / sp17e
  * D.13 Debiti verso istituti di previdenza/sicurezza sociale -> sp16f / sp17f
  * D.6 Acconti + D.9/10/11/11bis verso controllate/collegate/controllanti + D.14 Altri debiti -> sp16g / sp17g
- CRITICAL: sp16a+sp16b+sp16c+sp16d+sp16e+sp16f+sp16g MUST equal sp16_debiti_breve.
- CRITICAL: sp17a+sp17b+sp17c+sp17d+sp17e+sp17f+sp17g MUST equal sp17_debiti_lungo.
- If a group is missing in the PDF, leave it at 0.
- If the PDF shows only the "Totale debiti" without a breakdown, put everything in sp16g_altri_debiti_breve (or sp17g_altri_debiti_lungo for long-term) to match the aggregate — do NOT invent sub-totals.

PATRIMONIO NETTO:
- sp11_capitale is ONLY "I - Capitale" (share capital). Do NOT include it in sp12_riserve
- sp12_riserve = sum of ONLY items II through VIII: sovrapprezzo azioni (II), riserve di rivalutazione (III), riserva legale (IV), riserve statutarie (V), altre riserve (VI), riserva per operazioni di copertura (VII), utili (perdite) portati a nuovo (VIII), riserva negativa azioni proprie
- IMPORTANT: Verify that sp11_capitale + sp12_riserve + sp13_utile_perdita = "Totale patrimonio netto"

TOTALS:
- Extract totale_attivo and totale_passivo for validation
- totale_passivo = Totale patrimonio netto + fondi rischi + TFR + debiti + ratei passivi

Extract the CURRENT YEAR values (the first/leftmost value column, not the prior year)."""

SP_BOTH_YEARS_SYSTEM_PROMPT = """You are an expert Italian accountant specializing in Bilancio IV CEE (Schema di Bilancio art. 2424 Codice Civile).

Extract the Stato Patrimoniale (balance sheet) values from the text below.
The document has TWO value columns: current year (left) and prior year (right).
Extract BOTH columns into current_year and prior_year.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimal separators (1.234.567 = 1234567)
- Parentheses mean negative: (347.117) = -347117
- Trailing minus means negative: 347.117- = -347117
- Dash or empty = 0
- Return plain numbers without any formatting (no dots, no commas)
- All values in full euros (not thousands)

EXTRACTION RULES:
- Extract values EXACTLY as they appear: parentheses = negative, plain numbers = positive
- Do NOT flip signs - preserve the original sign from the PDF (e.g., losses, negative reserves)

CREDITI (in ATTIVO section, BEFORE "Totale attivo"):
- ONLY the C.II) Crediti of "Attivo circolante" go here. NEVER include B.III.2 "Crediti" (immobilized
  financial receivables): those belong to sp04_immob_finanziarie. Counting a B.III.2 credito here too
  double-counts it (it is already inside Immobilizzazioni) and unbalances the sheet by that amount.
- sp06_crediti_breve = SUM of ALL "esigibili entro l'esercizio successivo" amounts across the C.II crediti categories (verso clienti, tributari, verso altri, etc.)
  PLUS "imposte anticipate" (deferred tax assets) if shown as a separate line within C.II crediti
- sp07_crediti_lungo = SUM of ALL "esigibili oltre l'esercizio successivo" amounts across the C.II crediti categories (Attivo circolante only)
- CRITICAL: sp06 + sp07 MUST equal "Totale crediti" of C.II (Attivo circolante). If they don't, add the difference to sp06.
  Common cause: "imposte anticipate" is a separate line within crediti that must be included in sp06.
- If crediti are not split by maturity, put the TOTAL Crediti in sp06_crediti_breve and sp07=0

CREDITI — DEBTOR-TYPE BREAKDOWN (split each group into entro + oltre):
- For each C.II) Crediti sub-item, separate "entro l'esercizio successivo" (sp06*) from "oltre l'esercizio successivo" (sp07*).
- Map each OIC item to its bucket:
  * C.II.1 Crediti verso clienti             -> sp06a / sp07a
  * C.II.2 Crediti verso imprese controllate -> sp06b / sp07b
  * C.II.3 Crediti verso imprese collegate   -> sp06c / sp07c
  * C.II.4 Crediti verso controllanti + C.II.5 Crediti verso imprese sottoposte al controllo delle controllanti -> sp06d / sp07d
  * C.II.5-bis Crediti tributari             -> sp06e / sp07e
  * C.II.5-ter Imposte anticipate            -> sp06f / sp07f
  * C.II.5-quater Crediti verso altri        -> sp06g / sp07g
- CRITICAL: sp06a+sp06b+sp06c+sp06d+sp06e+sp06f+sp06g MUST equal sp06_crediti_breve.
- CRITICAL: sp07a+sp07b+sp07c+sp07d+sp07e+sp07f+sp07g MUST equal sp07_crediti_lungo.
- If a group is missing in the PDF, leave it at 0.
- If the PDF shows only "Totale crediti" without a breakdown, put everything in sp06g_crediti_altri_breve (or sp07g_crediti_altri_lungo for long-term) to match the aggregate — do NOT invent sub-totals.
- IMPORTANT: Do NOT confuse C.II Crediti (operating receivables in "Attivo circolante") with B.III.2 Crediti (immobilized financial receivables). Only extract C.II values here.

DEBITI (in PASSIVO section, AFTER "Totale attivo"):
- IMPORTANT: "entro/oltre" in the PASSIVO section refers to DEBTS, not credits
- First find TOTALE Debiti (D) — the sum of all debt categories. Put this exact line's value into `totale_debiti`.
- sp17_debiti_lungo: look for ALL "di cui esigibili oltre l'esercizio successivo" sub-lines
  under individual debt items (e.g., under "Debiti verso fornitori", under "Altri debiti", etc.)
  and SUM them. These "di cui" lines are indented sub-totals showing the long-term portion.
- sp16_debiti_breve = TOTALE Debiti (D) minus sp17_debiti_lungo
- CRITICAL: sp16 + sp17 MUST equal TOTALE Debiti (D). If they don't, recalculate sp16 as the difference.
- If debiti are not split by maturity at all, put TOTALE Debiti in sp16_debiti_breve and sp17=0

DEBITI — CREDITOR-TYPE BREAKDOWN (split each group into entro + oltre):
- For each debt item, separate "entro l'esercizio successivo" (sp16*) from "oltre l'esercizio successivo" (sp17*).
- Map each OIC item to its bucket:
  * D.4 Debiti verso banche                                    -> sp16a / sp17a
  * D.3 verso soci per finanziamenti + D.5 verso altri finanziatori -> sp16b / sp17b
  * D.1 Obbligazioni + D.2 Obbligazioni convertibili + D.8 rappresentati da titoli -> sp16c / sp17c
  * D.7 Debiti verso fornitori                                 -> sp16d / sp17d
  * D.12 Debiti tributari                                      -> sp16e / sp17e
  * D.13 Debiti verso istituti di previdenza/sicurezza sociale -> sp16f / sp17f
  * D.6 Acconti + D.9/10/11/11bis verso controllate/collegate/controllanti + D.14 Altri debiti -> sp16g / sp17g
- CRITICAL: sp16a+sp16b+sp16c+sp16d+sp16e+sp16f+sp16g MUST equal sp16_debiti_breve.
- CRITICAL: sp17a+sp17b+sp17c+sp17d+sp17e+sp17f+sp17g MUST equal sp17_debiti_lungo.
- If a group is missing in the PDF, leave it at 0.
- If the PDF shows only the "Totale debiti" without a breakdown, put everything in sp16g_altri_debiti_breve (or sp17g_altri_debiti_lungo for long-term) to match the aggregate — do NOT invent sub-totals.

PATRIMONIO NETTO:
- sp11_capitale is ONLY "I - Capitale" (share capital). Do NOT include it in sp12_riserve
- sp12_riserve = sum of ONLY items II through VIII: sovrapprezzo azioni (II), riserve di rivalutazione (III), riserva legale (IV), riserve statutarie (V), altre riserve (VI), riserva per operazioni di copertura (VII), utili (perdite) portati a nuovo (VIII), riserva negativa azioni proprie
- IMPORTANT: Verify that sp11_capitale + sp12_riserve + sp13_utile_perdita = "Totale patrimonio netto"

TOTALS:
- Extract totale_attivo and totale_passivo for validation
- totale_passivo = Totale patrimonio netto + fondi rischi + TFR + debiti + ratei passivi

Extract BOTH columns: current_year (left column) and prior_year (right column)."""

CE_SYSTEM_PROMPT = """You are an expert Italian accountant specializing in Bilancio IV CEE (Schema di Conto Economico art. 2425 Codice Civile).

Extract the Conto Economico (income statement) values from the text below.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimal separators (1.234.567 = 1234567)
- Parentheses mean negative: (347.117) = -347117
- Trailing minus means negative: 347.117- = -347117
- Dash or empty = 0
- Return plain numbers without any formatting (no dots, no commas)
- All values in full euros (not thousands)

EXTRACTION RULES:
- Extract values EXACTLY as they appear: parentheses = negative, plain numbers = positive
- Do NOT flip signs - preserve the original sign from the PDF
- ce08_costi_personale = Total personnel costs. Use "Totale costi per il personale" if present, otherwise "9) per il personale". If the "9)" line shows a dash but sub-items (a/b/c/d/e) and a "Totale" line exist, use the Totale value.
- ce08a_tfr_accrual = sub-item "c) trattamento di fine rapporto" under personnel costs (item 9c)
- ce09_ammortamenti = Total depreciation/amortization. Use "Totale ammortamenti e svalutazioni" if present, otherwise "10) ammortamenti e svalutazioni". If the "10)" line shows a dash but sub-items and a "Totale" line exist, use the Totale value.
- Extract sub-items ce09a (10a), ce09b (10b), ce09c (10c), ce09d (10d) if available
- IMPORTANT: ce02_variazioni_rimanenze (item 2) and ce10_var_rimanenze_mat_prime (item 11) are DIFFERENT items. Do NOT confuse them:
  - ce02 = item 2) "Variazioni delle rimanenze di PRODOTTI in corso di lavorazione, semilavorati e finiti" (under A) Valore della produzione)
  - ce10 = item 11) "Variazioni delle rimanenze di MATERIE PRIME, sussidiarie, di consumo e merci" (under B) Costi della produzione)
  - If only one "variazioni rimanenze" item exists and it's under B) Costi, it's ce10. Set ce02 to 0.
- ce04_altri_ricavi = item 5) "Altri ricavi e proventi" — use the TOTAL including sub-items (contributi in conto esercizio + altri). Use "Totale altri ricavi e proventi" if present.
- ce10_var_rimanenze_mat_prime = item 11) variazioni delle rimanenze di materie prime (under B costs, NOT item 2)
- ce11_accantonamenti = item 12) accantonamenti per rischi
- ce11b_altri_accantonamenti = item 13) altri accantonamenti
- ce15_oneri_finanziari = item 17) interessi e altri oneri finanziari (total)
- Items 2) and 3) may be merged; if so put the combined value in ce02_variazioni_rimanenze

SEZIONI CONTRAPPOSTE / "DETTAGLIO VOCI" LAYOUTS (CRITICAL — do NOT return zeros):
- Some statements do NOT have a classic single-column Conto Economico. Instead they
  present the income statement as TWO SIDE-BY-SIDE SECTIONS: "RICAVI" (revenues, one side)
  and "COSTI" (costs, the other side), often under a "Conto Economico" header, with
  account-level detail lines (e.g. "06.01.01.01.001 Vendita beni ..." or "07.01.01.01.004 Merci").
- You MUST still extract the CE values from these layouts. Treat the RICAVI side as the
  revenue items (A) and the COSTI side as the cost items (B):
  * Sum all "Vendita / Ricavi delle vendite e prestazioni" account lines into ce01_ricavi_vendite.
  * Sum "Altri ricavi e proventi / contributi / sopravvenienze attive" into ce04_altri_ricavi.
  * Map purchases of goods/raw materials ("Acquisti", "Merci", "Materie prime") to ce05_materie_prime.
  * Map "per servizi" costs to ce06_servizi; "godimento beni di terzi"/affitti to ce07_godimento_beni.
  * Map personnel ("Salari", "Stipendi", "Oneri sociali", "TFR") to ce08_costi_personale.
  * Map "Ammortamenti"/"Svalutazioni" to ce09_ammortamenti.
  * Map "Oneri diversi di gestione"/"sopravvenienze passive" to ce12_oneri_diversi.
  * Map "Interessi"/"oneri finanziari" to ce15_oneri_finanziari; financial income to ce14.
  * Map "Imposte sul reddito"/"IRES"/"IRAP" to ce20_imposte.
- If only account-level lines are present (no IV CEE subtotals), AGGREGATE the relevant
  detail lines yourself into the matching ce* field. NEVER leave the whole CE at zero when
  revenue and cost lines are clearly present in the text.

Extract the CURRENT YEAR values (the first/leftmost value column, not the prior year)."""

CE_BOTH_YEARS_SYSTEM_PROMPT = """You are an expert Italian accountant specializing in Bilancio IV CEE (Schema di Conto Economico art. 2425 Codice Civile).

Extract the Conto Economico (income statement) values from the text below.
The document has TWO value columns: current year (left) and prior year (right).
Extract BOTH columns into current_year and prior_year.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimal separators (1.234.567 = 1234567)
- Parentheses mean negative: (347.117) = -347117
- Trailing minus means negative: 347.117- = -347117
- Dash or empty = 0
- Return plain numbers without any formatting (no dots, no commas)
- All values in full euros (not thousands)

EXTRACTION RULES:
- Extract values EXACTLY as they appear: parentheses = negative, plain numbers = positive
- Do NOT flip signs - preserve the original sign from the PDF
- ce08_costi_personale = Total personnel costs. Use "Totale costi per il personale" if present, otherwise "9) per il personale". If the "9)" line shows a dash but sub-items (a/b/c/d/e) and a "Totale" line exist, use the Totale value.
- ce08a_tfr_accrual = sub-item "c) trattamento di fine rapporto" under personnel costs (item 9c)
- ce09_ammortamenti = Total depreciation/amortization. Use "Totale ammortamenti e svalutazioni" if present, otherwise "10) ammortamenti e svalutazioni". If the "10)" line shows a dash but sub-items and a "Totale" line exist, use the Totale value.
- Extract sub-items ce09a (10a), ce09b (10b), ce09c (10c), ce09d (10d) if available
- IMPORTANT: ce02_variazioni_rimanenze (item 2) and ce10_var_rimanenze_mat_prime (item 11) are DIFFERENT items. Do NOT confuse them:
  - ce02 = item 2) "Variazioni delle rimanenze di PRODOTTI in corso di lavorazione, semilavorati e finiti" (under A) Valore della produzione)
  - ce10 = item 11) "Variazioni delle rimanenze di MATERIE PRIME, sussidiarie, di consumo e merci" (under B) Costi della produzione)
  - If only one "variazioni rimanenze" item exists and it's under B) Costi, it's ce10. Set ce02 to 0.
- ce04_altri_ricavi = item 5) "Altri ricavi e proventi" — use the TOTAL including sub-items (contributi in conto esercizio + altri). Use "Totale altri ricavi e proventi" if present.
- ce10_var_rimanenze_mat_prime = item 11) variazioni delle rimanenze di materie prime (under B costs, NOT item 2)
- ce11_accantonamenti = item 12) accantonamenti per rischi
- ce11b_altri_accantonamenti = item 13) altri accantonamenti
- ce15_oneri_finanziari = item 17) interessi e altri oneri finanziari (total)
- Items 2) and 3) may be merged; if so put the combined value in ce02_variazioni_rimanenze

SEZIONI CONTRAPPOSTE / "DETTAGLIO VOCI" LAYOUTS (CRITICAL — do NOT return zeros):
- Some statements do NOT have a classic single-column Conto Economico. Instead they
  present the income statement as TWO SIDE-BY-SIDE SECTIONS: "RICAVI" (revenues, one side)
  and "COSTI" (costs, the other side), often under a "Conto Economico" header, with
  account-level detail lines (e.g. "06.01.01.01.001 Vendita beni ..." or "07.01.01.01.004 Merci").
- You MUST still extract the CE values from these layouts. Treat the RICAVI side as the
  revenue items (A) and the COSTI side as the cost items (B):
  * Sum all "Vendita / Ricavi delle vendite e prestazioni" account lines into ce01_ricavi_vendite.
  * Sum "Altri ricavi e proventi / contributi / sopravvenienze attive" into ce04_altri_ricavi.
  * Map purchases of goods/raw materials ("Acquisti", "Merci", "Materie prime") to ce05_materie_prime.
  * Map "per servizi" costs to ce06_servizi; "godimento beni di terzi"/affitti to ce07_godimento_beni.
  * Map personnel ("Salari", "Stipendi", "Oneri sociali", "TFR") to ce08_costi_personale.
  * Map "Ammortamenti"/"Svalutazioni" to ce09_ammortamenti.
  * Map "Oneri diversi di gestione"/"sopravvenienze passive" to ce12_oneri_diversi.
  * Map "Interessi"/"oneri finanziari" to ce15_oneri_finanziari; financial income to ce14.
  * Map "Imposte sul reddito"/"IRES"/"IRAP" to ce20_imposte.
- If only account-level lines are present (no IV CEE subtotals), AGGREGATE the relevant
  detail lines yourself into the matching ce* field. NEVER leave the whole CE at zero when
  revenue and cost lines are clearly present in the text. This applies to BOTH year columns
  when two columns are present; if there is only ONE value column, fill current_year only
  and leave prior_year at 0.

Extract BOTH columns: current_year (left column) and prior_year (right column)."""


def _build_tool_schema(model: type[pydantic.BaseModel], tool_name: str) -> dict:
    """Build an Anthropic tool definition from a Pydantic model."""
    schema = model.model_json_schema()
    # Remove title/description that Pydantic adds at the top level
    schema.pop("title", None)
    schema.pop("description", None)
    return {
        "name": tool_name,
        "description": f"Record the extracted {tool_name} values",
        "input_schema": schema,
    }


def _extract_with_llm(
    client: anthropic.Anthropic,
    text: str,
    system_prompt: str,
    output_model: type[pydantic.BaseModel],
    section_name: str,
    tool_name: str,
    max_retries: int = 2,
) -> pydantic.BaseModel:
    """Call Claude Haiku with tool-use for structured extraction."""
    logger.info(f"Calling Claude Haiku for {section_name} extraction ({len(text)} chars)...")

    tool = _build_tool_schema(output_model, tool_name)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.messages.create(
                model=PDF_LLM_MODEL,
                max_tokens=PDF_LLM_MAX_TOKENS,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Extract the {section_name} values from this Italian balance sheet text. "
                        f"Use the {tool_name} tool to record your results.\n\n{text}"
                    ),
                }],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
            )

            # Find the tool_use block
            for block in response.content:
                if block.type == "tool_use":
                    result = output_model.model_validate(block.input)
                    logger.info(f"{section_name} extraction complete")
                    return result

            raise PDFImportError(f"No tool_use block in {section_name} response")

        except anthropic.InternalServerError as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(f"API 500 error, retrying in {wait}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise

    raise last_error  # unreachable but satisfies type checker


# ---------------------------------------------------------------------------
# Vision-based extraction (fallback for image-only PDFs)
# ---------------------------------------------------------------------------

def _render_pdf_pages_as_images(file_path: str, pages: Optional[Set[int]] = None, dpi: int = 200) -> List[str]:
    """Render PDF pages as base64-encoded PNG images using PyMuPDF.

    Args:
        file_path: Path to the PDF
        pages: Set of zero-based page indices (None = all pages)
        dpi: Resolution for rendering

    Returns:
        List of base64-encoded PNG strings
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise PDFImportError(f"Cannot open PDF file: {e}")

    if pages is None:
        pages = set(range(len(doc)))

    images = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for p in sorted(pages):
        if p < len(doc):
            pix = doc[p].get_pixmap(matrix=matrix)
            images.append(base64.standard_b64encode(pix.tobytes("png")).decode("ascii"))

    doc.close()
    logger.info(f"Rendered {len(images)} PDF pages as images ({dpi} dpi)")
    return images


def _extract_with_llm_vision(
    client: anthropic.Anthropic,
    images: List[str],
    system_prompt: str,
    output_model: type[pydantic.BaseModel],
    section_name: str,
    tool_name: str,
    max_retries: int = 2,
) -> pydantic.BaseModel:
    """Call Claude with vision (page images) for structured extraction."""
    logger.info(f"Calling Claude (vision) for {section_name} extraction ({len(images)} images)...")

    tool = _build_tool_schema(output_model, tool_name)

    # Build content blocks: images + text instruction
    content: List[dict] = []
    for img_b64 in images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
        })
    content.append({
        "type": "text",
        "text": (
            f"Extract the {section_name} values from these Italian balance sheet pages. "
            f"Use the {tool_name} tool to record your results."
        ),
    })

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.messages.create(
                model=PDF_LLM_MODEL,
                max_tokens=PDF_LLM_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": content}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
            )

            for block in response.content:
                if block.type == "tool_use":
                    result = output_model.model_validate(block.input)
                    logger.info(f"{section_name} vision extraction complete")
                    return result

            raise PDFImportError(f"No tool_use block in {section_name} vision response")

        except anthropic.InternalServerError as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(f"API 500 error, retrying in {wait}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise

    raise last_error  # unreachable but satisfies type checker


def _is_image_pdf(file_path: str) -> bool:
    """Check if a PDF contains no extractable text (image-only)."""
    try:
        doc = fitz.open(file_path)
        total_chars = sum(len(doc[p].get_text().strip()) for p in range(len(doc)))
        doc.close()
        return total_chars < 50  # threshold: fewer than 50 chars = image-based
    except Exception:
        return False


def _text_layer_is_garbled(text: str) -> bool:
    """Detect a CORRUPTED (not merely absent) text layer — broken ToUnicode font maps.

    Signature: the printed glyphs are fine but the extracted text splits amounts
    around the decimal comma ("3.239 , 12", "315.121, 19") and garbles letters
    ("roNDO AMM.TO", "IMMOBILIZZAZIONI IIa(ATERIALI" — budget_337). Feeding that
    text to the LLM yields stochastic garbage; the images are clean, so such a file
    must take the VISION path like a scan.

    Calibrated on the full corpus (2026-07-15): budget_337 scores 60.7% broken
    amounts, every other file < 5% — threshold 30% with a >= 10 absolute floor so
    a couple of odd lines on a clean file can never trigger it.
    """
    if not text:
        return False
    broken = len(re.findall(r'\d\s+,\s*\d{2}\b', text))
    if broken < 10:
        return False
    wellformed = len(re.findall(r'\d,\d{2}\b', text))
    total = broken + wellformed
    return total > 0 and (broken / total) > 0.30


def ocr_pdf_sample_text(file_path: str, max_pages: int = 6) -> str:
    """OCR the first pages of a scanned (image-only) PDF into plain text.

    Scanned bilanci carry NO extractable text, so `bilancio_classifier.classify_bilancio`
    (which works on text markers) sees an empty string and routes the file to
    ROUTE_UNSUPPORTED — even though the route-C / IV-CEE extractors are already vision
    capable. This helper renders the first pages and asks Claude to transcribe them to
    plain text, so the SAME text-based router can decide the macro-area/route for a scan.

    It deliberately returns FREE TEXT (no tool schema): we only need routing markers
    ("BILANCIO DI VERIFICA", "STATO PATRIMONIALE", account codes, ...), not structured
    values — the chosen extractor re-reads the images itself for the real figures.

    Requires ANTHROPIC_API_KEY. Returns "" on any failure (caller decides how to surface).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    try:
        client = anthropic.Anthropic(api_key=api_key)
        pages = set(range(max_pages))
        images = _render_pdf_pages_as_images(file_path, pages=pages, dpi=200)
        if not images:
            return ""
        content: List[dict] = []
        for img_b64 in images:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
            })
        content.append({
            "type": "text",
            "text": (
                "Trascrivi FEDELMENTE tutto il testo visibile in queste pagine di un "
                "documento contabile italiano scansionato. Mantieni intestazioni, nomi "
                "delle voci, codici conto e numeri cosi' come appaiono, riga per riga. "
                "Non interpretare, non riassumere, non aggiungere commenti: solo il testo "
                "grezzo (plain text)."
            ),
        })
        response = client.messages.create(
            model=PDF_LLM_MODEL,
            max_tokens=PDF_LLM_MAX_TOKENS,
            messages=[{"role": "user", "content": content}],
        )
        parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        ocr_text = "\n".join(parts).strip()
        logger.info(f"OCR routing pass: recovered {len(ocr_text)} chars from {len(images)} scanned pages")
        return ocr_text
    except Exception as e:
        logger.warning(f"OCR routing pass failed ({type(e).__name__}: {e})")
        return ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model_to_decimal_dict(model: pydantic.BaseModel) -> Dict[str, Decimal]:
    """Convert a Pydantic model with float fields to Dict[str, Decimal]."""
    result = {}
    for field_name, value in model:
        result[field_name] = Decimal(str(value))
    return result


_CREDIT_BREVE_SOURCE_FIELDS = (
    'sp06a_crediti_clienti_breve',
    'sp06b_crediti_controllate_breve',
    'sp06c_crediti_collegate_breve',
    'sp06d_crediti_controllanti_breve',
    'sp06e_crediti_tributari_breve',
    'sp06f_imposte_anticipate_breve',
    'sp06g_crediti_altri_breve',
)
_CREDIT_LUNGO_SOURCE_FIELDS = (
    'sp07a_crediti_clienti_lungo',
    'sp07b_crediti_controllate_lungo',
    'sp07c_crediti_collegate_lungo',
    'sp07d_crediti_controllanti_lungo',
    'sp07e_crediti_tributari_lungo',
    'sp07f_imposte_anticipate_lungo',
    'sp07g_crediti_altri_lungo',
)


def _reconcile_credit_aggregates_from_source(
    balance_sheet_data: Dict[str, Decimal], label: str
) -> Dict[str, Decimal]:
    """Rebuild credit aggregates only from corroborated rows in the source.

    The LLM can extract every typed C.II row correctly but make a small arithmetic
    error in ``sp06_crediti_breve``.  The strict balance gate then rejects an exact
    statement (budget_594 differs by EUR 22).

    Unlike the historical balance-gap correction, this function never infers an
    amount from total assets and never creates a plug.  It changes the aggregates
    only when the extracted short/long details add up to the PDF's explicit
    ``totale_crediti`` control row.
    """
    result = dict(balance_sheet_data)
    declared_total = result.get('totale_crediti', Decimal('0'))
    if declared_total <= 0:
        return result

    short_total = sum(
        (result.get(key, Decimal('0')) for key in _CREDIT_BREVE_SOURCE_FIELDS),
        Decimal('0'),
    )
    long_total = sum(
        (result.get(key, Decimal('0')) for key in _CREDIT_LUNGO_SOURCE_FIELDS),
        Decimal('0'),
    )
    detail_total = short_total + long_total
    old_short = result.get('sp06_crediti_breve', Decimal('0'))
    old_long = result.get('sp07_crediti_lungo', Decimal('0'))

    # One euro absorbs harmless display rounding without accepting a partial
    # breakdown as proof of an aggregate. Preserve an aggregate that already
    # agrees with the printed total: legal detail rows can differ by one euro due
    # to independent display rounding (budget_394).
    if (
        detail_total <= 0
        or abs(old_short + old_long - declared_total) <= Decimal('1')
    ):
        return result

    if abs(detail_total - declared_total) <= Decimal('1'):
        new_short, new_long = short_total, long_total
    else:
        # Some legal layouts print a maturity subtotal that excludes a separate
        # typed row (typically "imposte anticipate") and then print the complete
        # C.II total.  Accept the omitted amount only when that exact residual is
        # independently present in one maturity-specific detail bucket.
        residual = declared_total - old_short - old_long
        short_match = short_total != 0 and abs(residual - short_total) <= Decimal('1')
        long_match = long_total != 0 and abs(residual - long_total) <= Decimal('1')
        if short_match == long_match:  # neither match, or ambiguous
            return result
        if short_match:
            new_short, new_long = old_short + residual, old_long
        else:
            new_short, new_long = old_short, old_long + residual

    if abs(old_short - new_short) > Decimal('0.01') or abs(old_long - new_long) > Decimal('0.01'):
        logger.warning(
            f"[{label}] Crediti source-backed: dettagli C.II={detail_total} "
            f"confermano totale_crediti={declared_total}; "
            f"sp06 {old_short}->{new_short}, sp07 {old_long}->{new_long}"
        )
        result['sp06_crediti_breve'] = new_short
        result['sp07_crediti_lungo'] = new_long
    return result


# Core cost fields that must always be positive (the model subtracts them).
# Some PDFs (e.g. Zucchetti, "bilancio riclassificato") show costs as negative.
_POSITIVE_COST_FIELDS = {
    'ce05_materie_prime', 'ce06_servizi', 'ce07_godimento_beni',
    'ce08_costi_personale', 'ce08a_tfr_accrual',
    'ce09_ammortamenti', 'ce09a_ammort_immateriali', 'ce09b_ammort_materiali',
    'ce09c_svalutazioni', 'ce09d_svalutazione_crediti',
    'ce11_accantonamenti', 'ce11b_altri_accantonamenti',
    'ce12_oneri_diversi',
    'ce15_oneri_finanziari',
    'ce19_oneri_straordinari',
}

# Ambiguous fields handled explicitly in _normalize_ce_signs Pass 2 when the PDF uses
# the "all costs as negative" convention:
#   ce10_var_rimanenze_mat_prime — a variation that can be a cost OR a credit; it must
#     be NEGATED (not abs'd) so an inventory-increase credit shown as +X becomes -X.
#   ce20_imposte — effectively always an expense; flipped to positive only when negative.


def _normalize_ce_signs(income_data: Dict[str, Decimal]) -> Dict[str, Decimal]:
    """Ensure cost fields are stored as positive values.

    The model formulas explicitly subtract costs (e.g. EBIT = VP - COPRO),
    so ce05-ce12, ce15, ce19, ce20 must be positive.  Some PDFs show costs
    in parentheses and the LLM correctly extracts them as negative — this
    function flips those to positive.

    When the PDF uses "all costs as negative" convention (detected by ≥3
    core cost fields being negative), also flip ce10 and ce20.
    """
    # Pass 1: flip core cost fields and count how many were negative
    flipped = []
    for field in _POSITIVE_COST_FIELDS:
        val = income_data.get(field, Decimal('0'))
        if val < 0:
            income_data[field] = abs(val)
            flipped.append(field)

    # Pass 2: if many core fields were negative, the PDF uses "costs as negative"
    # convention — handle the ambiguous fields.
    if len(flipped) >= 3:
        # ce10 (variazioni rimanenze materie prime) is NOT a pure cost: an inventory
        # INCREASE is a credit that REDUCES COPRO and is printed with the opposite
        # sign of the surrounding cost block (i.e. a plain positive number, while the
        # real costs are in parentheses). The correct transform is therefore to NEGATE
        # it — the very same flip applied to every cost line — so a +X credit becomes
        # -X in the positive-cost model and a real cost shown as -X becomes +X. Using
        # abs() (the old behaviour) left a +X credit untouched and inflated COPRO by 2X,
        # breaking the CE cross-foot (e.g. ALMA item 11 = +7.831 → CE off by 15.662).
        ce10 = income_data.get('ce10_var_rimanenze_mat_prime', Decimal('0'))
        if ce10 != 0:
            income_data['ce10_var_rimanenze_mat_prime'] = -ce10
            flipped.append('ce10_var_rimanenze_mat_prime')
        # ce20 (imposte) is effectively always an expense in these layouts; flip the
        # parenthesised (negative) presentation to positive, leave an already-positive
        # value alone (its own cross-check in _validate_ce_imposte guards edge cases).
        ce20 = income_data.get('ce20_imposte', Decimal('0'))
        if ce20 < 0:
            income_data['ce20_imposte'] = abs(ce20)
            flipped.append('ce20_imposte')

    if flipped:
        logger.info(f"CE sign normalization: flipped {len(flipped)} fields to positive: {flipped}")
    return income_data


_CE09_DETAIL_FIELDS = (
    'ce09a_ammort_immateriali',
    'ce09b_ammort_materiali',
    'ce09c_svalutazioni',
    'ce09d_svalutazione_crediti',
)


def _reconcile_ce09_from_source_details(
    income_data: Dict[str, Decimal],
    balance_sheet_data: Dict[str, Decimal],
    label: str,
) -> Dict[str, Decimal]:
    """Select the exhaustive B.10 detail sum when SP independently confirms it.

    The model occasionally scales one B.10 sub-row while computing the aggregate
    (budget_413: 1,254 becomes 1,254,000) even though every extracted a/b/c/d row is
    correct.  The four legal detail fields are exhaustive, but a partially printed
    statement can omit one.  Therefore the roll-up is accepted only when replacing
    ``ce09`` makes the reconstructed CE result agree with the independently printed
    SP result; otherwise the source aggregate is left untouched for review.
    """
    result = dict(income_data)
    detail_total = sum(
        (result.get(field, Decimal('0')) for field in _CE09_DETAIL_FIELDS),
        Decimal('0'),
    )
    aggregate = result.get('ce09_ammortamenti', Decimal('0'))
    if detail_total <= 0 or abs(aggregate - detail_total) <= Decimal('0.01'):
        return result

    sp_result = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
    current_result = calculate_ce_result(result).net_profit
    candidate = dict(result)
    candidate['ce09_ammortamenti'] = detail_total
    candidate_result = calculate_ce_result(candidate).net_profit
    tolerance = max(Decimal('2'), abs(sp_result) * Decimal('0.001'))
    if (
        abs(candidate_result - sp_result) <= tolerance
        and abs(candidate_result - sp_result) + Decimal('0.01')
        < abs(current_result - sp_result)
    ):
        logger.warning(
            f"[{label}] B.10 source-backed: ce09 {aggregate}->{detail_total}; "
            f"dettagli a/b/c/d e risultato SP {sp_result} confermano il roll-up"
        )
        candidate['_ce09_source_reconciled'] = aggregate - detail_total
        return candidate
    return result


def _reconcile_isolated_ce_cost_signs(
    income_data: Dict[str, Decimal],
    raw_income_data: Dict[str, Decimal],
    balance_sheet_data: Dict[str, Decimal],
    label: str,
) -> Dict[str, Decimal]:
    """Preserve isolated negative cost rows when the SP result confirms them.

    Three or more negative cost rows signal a presentation convention and are
    normalized to positive magnitudes.  One or two negative rows can instead be a
    real reversal (budget_253 B.14 = -1,239).  Try only the explicitly negative
    source signs and retain a candidate solely when its CE result cross-foots to the
    independently extracted SP result.
    """
    negative_fields = [
        field for field in _POSITIVE_COST_FIELDS
        if raw_income_data.get(field, Decimal('0')) < 0
    ]
    if not negative_fields or len(negative_fields) >= 3:
        return dict(income_data)

    sp_result = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
    tolerance = max(Decimal('2'), abs(sp_result) * Decimal('0.001'))
    baseline_gap = abs(calculate_ce_result(income_data).net_profit - sp_result)
    candidates = []
    subsets = [[field] for field in negative_fields]
    if len(negative_fields) == 2:
        subsets.append(negative_fields)
    for fields in subsets:
        trial = dict(income_data)
        for field in fields:
            trial[field] = raw_income_data[field]
        gap = abs(calculate_ce_result(trial).net_profit - sp_result)
        if gap <= tolerance and gap + Decimal('0.01') < baseline_gap:
            candidates.append((gap, tuple(sorted(fields)), trial))
    if not candidates:
        return dict(income_data)

    gap, fields, best = min(candidates, key=lambda item: (item[0], len(item[1]), item[1]))
    logger.warning(
        f"[{label}] segni CE source-backed: mantenuti negativi {list(fields)}; "
        f"risultato CE riconciliato a sp13={sp_result} (scarto {gap})"
    )
    return best


def _reconcile_global_ce_thousand_scale(
    income_data: Dict[str, Decimal],
    balance_sheet_data: Dict[str, Decimal],
    label: str,
) -> Dict[str, Decimal]:
    """Correct a whole CE column parsed at 1000x only with SP corroboration.

    A mangled value such as ``542.218.750`` can represent ``542.218,750`` after
    the decimal comma was converted to a dot.  It is indistinguishable from an
    integer in isolation.  When at least three CE fields share the scale error,
    dividing the complete CE by 1000 is accepted only if the resulting net profit
    matches the independently extracted SP result (budget_305).
    """
    result = dict(income_data)
    ce_fields = [
        field for field, value in result.items()
        if field.startswith('ce') and isinstance(value, Decimal) and value != 0
    ]
    if len(ce_fields) < 3:
        return result
    sp_result = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
    baseline_result = calculate_ce_result(result).net_profit
    baseline_gap = abs(baseline_result - sp_result)
    if baseline_gap <= max(Decimal('2'), abs(sp_result) * Decimal('0.001')):
        return result

    candidate = dict(result)
    for field in ce_fields:
        candidate[field] = result[field] / Decimal('1000')
    candidate_result = calculate_ce_result(candidate).net_profit
    tolerance = max(Decimal('2'), abs(sp_result) * Decimal('0.001'))
    # Require a characteristic three-order-of-magnitude mismatch, not merely a
    # somewhat better result, before treating the punctuation as a scale error.
    magnitude_floor = max(Decimal('100000'), abs(sp_result) * Decimal('100'))
    if baseline_gap >= magnitude_floor and abs(candidate_result - sp_result) <= tolerance:
        logger.warning(
            f"[{label}] scala CE source-backed: colonna /1000; risultato "
            f"{baseline_result}->{candidate_result}, confermato da sp13={sp_result}"
        )
        candidate['_ce_scale_reconciled'] = Decimal('1000')
        return candidate
    return result


# ---------------------------------------------------------------------------
# Deterministic IV-CEE detail-line reconciler (clean legal statements)
# ---------------------------------------------------------------------------
# A fully-printed IV-CEE bilancio (Micro/Abbreviato/Ordinario) lists every legal
# sub-line verbatim — including the patrimonio-netto reserve detail (II..X) and the
# personnel split (B.9 a/b/c/e). The LLM extractor only captures the AGGREGATES
# (sp12_riserve, ce08_costi_personale), so the sub-fields come back 0 and, worse, a
# NEGATIVE reserve line (VIII - utili (perdite) portati a nuovo) is dropped from the
# aggregate — which inflates equity and gets masked into cash by the balance reconcile
# (and _validate_equity refuses the correct fix because it yields "negative reserves").
# These helpers read the explicit lines deterministically and, gated on the printed
# control total (anti-masking), fill the sub-fields and fix the aggregate. Text-path
# only (the lines are unambiguous in PyMuPDF text); the vision path keeps LLM behaviour.

def _parse_it_number(tok: str) -> Optional[Decimal]:
    """Parse one Italian-formatted amount token. Parentheses or trailing '-' = negative."""
    tok = tok.strip()
    if not tok:
        return None
    neg = False
    if tok.startswith('(') and tok.endswith(')'):
        neg = True
        tok = tok[1:-1].strip()
    if tok.endswith('-'):
        neg = True
        tok = tok[:-1].strip()
    if tok.startswith('-'):
        neg = True
        tok = tok[1:].strip()
    t = tok.replace('.', '').replace(',', '.')
    if not re.fullmatch(r'\d+(?:\.\d+)?', t):
        return None
    v = Decimal(t)
    return -v if neg else v


_DETAIL_TOKEN_RE = re.compile(r'\(?-?[\d.,]+\)?-?')


def _values_for_label(lines, idx: int, label_end: int):
    """Collect up to 2 numeric values for a matched label: first any numbers on the
    SAME line after the label, then numbers on following (blank-skipped) lines, stopping
    at the first non-blank non-numeric line. Handles both the 'label\\ncur\\nprior'
    column layout (PyMuPDF cell-per-line) and the 'label cur prior' single-line layout."""
    nums = []
    tail = lines[idx][label_end:]
    for t in _DETAIL_TOKEN_RE.findall(tail):
        v = _parse_it_number(t)
        if v is not None:
            nums.append(v)
    j = idx + 1
    skipped_total = False
    while len(nums) < 2 and j < len(lines):
        s = lines[j].strip()
        if not s:
            j += 1
            continue
        v = _parse_it_number(s)
        if v is None:
            # In detail / Zucchetti layouts the voce value can sit AFTER an interposed
            # "Totale <voce>" line (the pre-filter reorders the detail block so the
            # numbers land below the "Totale" structural line). Skip ONE such line
            # before giving up, so the voce total stays reachable (e.g. budget_331:
            # "VIII - Utili portati" \n "Totale VIII - Utili portati" \n "(1.520)").
            if not nums and not skipped_total and s[:6].lower() == 'totale':
                skipped_total = True
                j += 1
                continue
            break
        nums.append(v)
        j += 1
    return nums


def _scan_labeled(text: str, specs):
    """specs: list of (compiled regex anchored at line start, key). Returns
    {key: [vals...]} for the FIRST line matching each spec, in document order."""
    lines = text.split('\n')
    out = {}
    for i, line in enumerate(lines):
        for rx, key in specs:
            if key in out:
                continue
            m = rx.match(line)
            if m:
                vals = _values_for_label(lines, i, m.end())
                if vals:
                    out[key] = vals
                break
    return out


# Roman-numeral PN reserve lines (art. 2424 A.II..A.X). The numeral is followed by a
# separator (dash OR ')') OR just whitespace — `(?:\s*[-–)]\s*|\s+)` — so layouts that
# print "IV   Riserva legale" with NO separator (budget_315) are matched too. The required
# whitespace still disambiguates 'V'/'VI'/'VII'/'VIII' ('VII ...' cannot match the 'VI'
# spec because the char after 'VI' is 'I', not whitespace). An optional 'A.' letter prefix
# is allowed for gestionali that print the legal path-code ('A.VIII) Utili...' — budget_340/341).
_PN_DETAIL_SPECS = [
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*II(?:\s*[-–)]\s*|\s+)Riserva da soprapprezzo', re.I), 'sp12a_riserva_sovrapprezzo'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*III(?:\s*[-–)]\s*|\s+)Riserve di rivalutazione', re.I), 'sp12b_riserve_rivalutazione'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*IV(?:\s*[-–)]\s*|\s+)Riserva legale', re.I), 'sp12c_riserva_legale'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*V(?:\s*[-–)]\s*|\s+)Riserve statutarie', re.I), 'sp12d_riserve_statutarie'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*(?:VI|VII)(?:\s*[-–)]\s*|\s+)Altre riserve', re.I), 'sp12e_altre_riserve'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*VII(?:\s*[-–)]\s*|\s+)Ris\w*\.?\s+per\s+operaz', re.I), 'sp12f_riserva_copertura_flussi'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*VIII(?:\s*[-–)]\s*|\s+)Util.*portat', re.I), 'sp12g_utili_perdite_portati'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*X(?:\s*[-–)]\s*|\s+)Riserva negativa per azioni proprie', re.I), 'sp12h_riserva_neg_azioni_proprie'),
]
# Declared PN control total. Besides the canonical "Totale patrimonio netto", accept
# the gestionale variants "A TOTALE PATRIMONIO NETTO" (budget_341) and the section
# header "A) Patrimonio netto" that itself carries the subtotal (budget_340).
_PN_TOTAL_SPECS = [
    (re.compile(r'^\s*Totale patrimonio netto', re.I), 'pn_total'),
    (re.compile(r'^\s*[A-Z]\s+Totale patrimonio netto', re.I), 'pn_total'),
    (re.compile(r'^\s*[A-Z][.\)]\s*Patrimonio netto\b', re.I), 'pn_total'),
]

# Personnel split (B.9 a/b/c/e). The SPECIFIC single-letter lines only: the combined
# "c), d), e) trattamento ..." header starts "c)," so it cannot match 'c)\s*trattamento'.
_PERS_DETAIL_SPECS = [
    (re.compile(r'^\s*a\)\s*salari', re.I), 'ce08b_salari_stipendi'),
    (re.compile(r'^\s*b\)\s*oneri sociali', re.I), 'ce08c_oneri_sociali'),
    # CE cost line "c) trattamento di fine rapporto" — NOT the SP fund line
    # "C) Trattamento di fine rapporto di lavoro subordinato" (sp15, = 11.561) that
    # bleeds into the CE text window: the lookahead rejects the "...di lavoro" variant.
    (re.compile(r'^\s*c\)\s*trattamento di fine rapporto(?!\s+di\s+lavoro)', re.I), 'ce08a_tfr_accrual'),
    (re.compile(r'^\s*e\)\s*altri costi', re.I), 'ce08d_altri_costi_personale'),
]
_PERS_TOTAL_SPECS = [(re.compile(r'^\s*Totale costi per il personale', re.I), 'pers_total')]


def _reconcile_pn_detail(bs: Dict[str, Decimal], sp_text: str, label: str,
                         column: int = 0) -> Dict[str, Decimal]:
    """Fill sp12a..h from the explicit PN reserve lines and set sp12_riserve to their
    algebraic sum. Applied ONLY when sp11 + Σsp12* + sp13 reconciles to the printed
    'Totale patrimonio netto' (anti-masking). Recovers the dropped NEGATIVE reserve
    (utili/(perdite) portati a nuovo) that otherwise inflates equity → masked into cash."""
    if not sp_text:
        return bs
    found = _scan_labeled(sp_text, _PN_DETAIL_SPECS)
    subs = {k: v[column] for k, v in found.items() if column < len(v)}
    if not subs:
        return bs
    new_sp12 = sum(subs.values())
    sp11 = bs.get('sp11_capitale', Decimal('0'))
    sp13 = bs.get('sp13_utile_perdita', Decimal('0'))
    pn_tot = _scan_labeled(sp_text, _PN_TOTAL_SPECS).get('pn_total')
    declared_pn = pn_tot[column] if pn_tot and column < len(pn_tot) else None
    if declared_pn is None:
        return bs  # no control total to anchor on -> stay conservative
    tol = max(Decimal('2'), abs(declared_pn) * Decimal('0.005'))
    if abs(sp11 + new_sp12 + sp13 - declared_pn) > tol:
        logger.info(f"[{label}] PN detail: Σsp12*={new_sp12} + sp11 + sp13 does not "
                    f"reconcile to declared PN {declared_pn}; skipping detail fill")
        return bs
    for k, v in subs.items():
        bs[k] = v
    bs['sp12_riserve'] = new_sp12
    logger.info(f"[{label}] PN detail reconciled: sp12_riserve -> {new_sp12} "
                f"(legale={subs.get('sp12c_riserva_legale')}, "
                f"altre={subs.get('sp12e_altre_riserve')}, "
                f"utili a nuovo={subs.get('sp12g_utili_perdite_portati')})")
    return bs


def _reconcile_personale_detail(ce: Dict[str, Decimal], ce_text: str, label: str,
                                column: int = 0) -> Dict[str, Decimal]:
    """Fill ce08a/b/c/d from the explicit B.9 a/b/c/e personnel lines, gated on the
    printed 'Totale costi per il personale'. Fixes the salari/oneri split the LLM merges
    into ce08b (e.g. salari 214.698 + oneri 60.346 reported as salari 275.044)."""
    if not ce_text:
        return ce
    found = _scan_labeled(ce_text, _PERS_DETAIL_SPECS)
    subs = {k: v[column] for k, v in found.items() if column < len(v)}
    if not subs:
        return ce
    s = sum(subs.values())
    tot = _scan_labeled(ce_text, _PERS_TOTAL_SPECS).get('pers_total')
    declared = (tot[column] if tot and column < len(tot)
                else ce.get('ce08_costi_personale', Decimal('0')))
    if declared is None or declared <= 0:
        return ce
    tol = max(Decimal('2'), abs(declared) * Decimal('0.02'))
    if abs(s - declared) > tol:
        logger.info(f"[{label}] personale detail: Σsub={s} != declared total {declared}; skipping")
        return ce
    for k, v in subs.items():
        ce[k] = v
    ce['ce08_costi_personale'] = declared  # authoritative total (also fixes an LLM merge)
    logger.info(f"[{label}] personale split reconciled: salari={subs.get('ce08b_salari_stipendi')}, "
                f"oneri={subs.get('ce08c_oneri_sociali')}, tfr={subs.get('ce08a_tfr_accrual')}, "
                f"altri={subs.get('ce08d_altri_costi_personale')}")
    return ce


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def extract_pdf_with_llm(
    file_path: str, force_llm: bool = False
) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """
    Extract balance sheet and income statement from PDF using PyMuPDF + Claude Haiku 4.5.

    For "Situazione Contabile" (trial balance) PDFs with XX/YY/ZZZ account codes,
    uses a deterministic parser instead of the LLM — UNLESS force_llm=True, which skips
    the trial-balance re-routing. The caller in pdf_importer uses this when the
    deterministic parser already ran and yielded an empty extraction (a mis-detected
    bilancio, e.g. budget_313/314): without force_llm the LLM path would re-detect the
    trial-balance format and bounce straight back to the same empty deterministic parser,
    defeating the fallback.

    Requires ANTHROPIC_API_KEY environment variable (unless situazione contabile).

    Args:
        file_path: Path to the PDF file

    Returns:
        (balance_sheet_data, income_data) - dictionaries with Decimal values

    Raises:
        PDFImportError: If extraction fails
    """
    # Check for Situazione Contabile format (trial balance with XX/YY/ZZZ codes)
    # Route to deterministic parser — bypasses LLM entirely
    try:
        doc = fitz.open(file_path)
        sample_text = ""
        for page in doc:
            sample_text += page.get_text()
            if len(sample_text) > 5000:
                break
        doc.close()
    except Exception:
        sample_text = ""

    from importers.situazione_contabile_parser import is_situazione_contabile, extract_situazione_contabile
    if not force_llm and is_situazione_contabile(sample_text):
        logger.info("Situazione contabile (trial balance) format detected, using deterministic parser")
        balance_sheet_data, income_data = extract_situazione_contabile(file_path)
        # Skip LLM validators (_validate_crediti/_validate_debiti/_validate_equity)
        # as they rely on full column names and are designed to fix LLM errors.
        # The deterministic parser produces correct values directly.
        return balance_sheet_data, income_data

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise PDFImportError("ANTHROPIC_API_KEY environment variable not set")

    try:
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        raise PDFImportError(f"Failed to initialize Anthropic client: {e}")

    # Step 1: Check if PDF is image-based (no extractable text)
    use_vision = _is_image_pdf(file_path)

    if use_vision:
        logger.info("Image-based PDF detected, using vision extraction")
        all_images = _render_pdf_pages_as_images(file_path)

        # Step 2v: Extract balance sheet via vision
        try:
            sp_result = _extract_with_llm_vision(
                client, all_images, SP_SYSTEM_PROMPT,
                BalanceSheetExtraction, "Stato Patrimoniale",
                tool_name="balance_sheet",
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during SP vision extraction: {e}")

        # Step 3v: Extract income statement via vision
        try:
            ce_result = _extract_with_llm_vision(
                client, all_images, CE_SYSTEM_PROMPT,
                IncomeStatementExtraction, "Conto Economico",
                tool_name="income_statement",
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during CE vision extraction: {e}")
    else:
        # Step 1b: Extract relevant page text with PyMuPDF
        sp_text, ce_text = extract_relevant_pages(file_path)

        if not sp_text.strip():
            raise PDFImportError("No text extracted from balance sheet pages")

        # Step 2: Extract balance sheet via Claude Haiku
        try:
            sp_result = _extract_with_llm(
                client, sp_text, SP_SYSTEM_PROMPT,
                BalanceSheetExtraction, "Stato Patrimoniale",
                tool_name="balance_sheet",
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during SP extraction: {e}")

        # Step 3: Extract income statement via Claude Haiku
        try:
            ce_result = _extract_with_llm(
                client, ce_text, CE_SYSTEM_PROMPT,
                IncomeStatementExtraction, "Conto Economico",
                tool_name="income_statement",
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during CE extraction: {e}")

    # Step 4: Convert to Decimal dicts and normalize signs
    balance_sheet_data = _reconcile_credit_aggregates_from_source(
        _model_to_decimal_dict(sp_result), "single"
    )
    balance_sheet_data, _ = _reconcile_blank_current_sp_cells(
        file_path, balance_sheet_data
    )
    balance_sheet_data = _recover_printed_sp_rows(file_path, balance_sheet_data)
    balance_sheet_data = _split_printed_debt_maturities(
        file_path, balance_sheet_data
    )
    balance_sheet_data = _recover_printed_fixed_asset_details(
        file_path, balance_sheet_data
    )
    raw_income_data = _model_to_decimal_dict(ce_result)
    income_data = _normalize_ce_signs(dict(raw_income_data))
    income_data, _ = _reconcile_blank_current_ce_cells(file_path, income_data)

    # Log key values for verification
    logger.info(f"SP totale_attivo = {balance_sheet_data.get('totale_attivo')}")
    logger.info(f"SP totale_passivo = {balance_sheet_data.get('totale_passivo')}")
    logger.info(f"CE ce01_ricavi_vendite = {income_data.get('ce01_ricavi_vendite')}")

    # Step 5: ``totale_passivo`` is control metadata and can legitimately exclude
    # the year's result on this layout.  Do not infer crediti, debiti or reserves
    # from a balance gap: those values must remain tied to source rows.
    balance_sheet_data = _reconcile_utile_in_passivo(balance_sheet_data, "single")

    # Step 6: CE sign/column conflicts are validation errors.  Never flip ce10 or
    # derive taxes from sp13 solely to make the two statements agree.

    # Step 7: Deterministic detail-line fill for clean IV-CEE statements (text path only):
    # PN reserve sub-fields (recovers dropped NEGATIVE reserves → keeps cash correct) +
    # personnel salari/oneri split. No-op on layouts without the explicit legal lines.
    if not use_vision:
        balance_sheet_data = _reconcile_pn_detail(balance_sheet_data, sp_text, "single")
        income_data = _reconcile_personale_detail(income_data, ce_text, "single")
    income_data = _reconcile_global_ce_thousand_scale(
        income_data, balance_sheet_data, "single"
    )
    income_data = _reconcile_isolated_ce_cost_signs(
        income_data, raw_income_data, balance_sheet_data, "single"
    )
    income_data = _reconcile_ce09_from_source_details(
        income_data, balance_sheet_data, "single"
    )

    # Un estrattore dichiara SEMPRE le proprie chiavi diagnostiche, anche a zero:
    # a valle una chiave assente vale zero, quindi tacere equivale a dichiararsi
    # pulito. Le rotte A/B non scrivevano `_unclassified_mass` affatto.
    try:
        from importers.iv_cee_hierarchy import declare_unclassified_mass
        balance_sheet_data.update(
            declare_unclassified_mass(
                balance_sheet_data, _declared_control_totals(file_path), "ivcee-single"
            )
        )
    except Exception as _declare_err:  # pragma: no cover - diagnostica, mai bloccante
        # Anche fallendo si dichiara. Una chiave ASSENTE a valle vale zero, cioe'
        # «pulito»: tacere qui rimetterebbe in piedi proprio il difetto che questa
        # dichiarazione esiste per togliere. Zero con `_measured` a zero significa
        # invece «non lo so», che e' la verita' quando la misura non e' riuscita.
        balance_sheet_data.setdefault('_unclassified_mass', Decimal('0'))
        balance_sheet_data.setdefault('_unclassified_mass_measured', Decimal('0'))
        logger.warning(
            f"Massa non classificata non dichiarata: {_declare_err}"
        )


    return balance_sheet_data, income_data


# ---------------------------------------------------------------------------
# Trial-balance (situazione contabile / sezioni contrapposte) CoGe extraction
# ---------------------------------------------------------------------------
# Macro-area C documents are NOT legal IV-CEE statements: they are flat lists of
# general-ledger accounts (conti di contabilita' generale, "CoGe") with Dare/Avere
# or Saldo balances and NO art.2424/2425 schema. The IV-CEE prompts above read the
# legal schema and misfire on these. These dedicated prompts teach the model the
# trial-balance sign convention (Dare=asset/cost, Avere=liability/equity/revenue),
# contra-account netting (fondi ammortamento / svalutazione), and that the year's
# result is the Attivo-vs-Passivo gap — so the LLM actually reads the CoGe list.

TRIAL_BALANCE_SP_SYSTEM_PROMPT = """You are an expert Italian accountant reading a TRIAL BALANCE (bilancio di verifica / situazione contabile / saldi di contabilita' generale).

This is NOT a legal IV-CEE statement. It is a flat list of general-ledger accounts (conti CoGe), each with a code and one or two amount columns. Your job: classify the PATRIMONIAL accounts (assets, liabilities, equity) into the IV-CEE Stato Patrimoniale fields (sp01-sp18). IGNORE economic accounts (costi/ricavi) here — they belong to the income statement.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimals (1.234.567,89 = 1234567.89)
- Parentheses or a trailing minus mean negative
- Return plain numbers without formatting (no dots, no commas), in full euros

TRIAL-BALANCE LAYOUTS (handle all):
- Two columns "Dare" (debit) and "Avere" (credit): each account has a balance on ONE side; use that side's amount.
- A single "Saldo" column, sometimes with a D/A flag or a sign: the flag/sign tells the side.
- The COLUMN is ground truth for the side. Do NOT move an account to the other side based on its name.

SIGN / SIDE CONVENTION:
- ATTIVO (assets) accounts normally carry a DARE (debit) balance: cassa, banche c/c attive, crediti verso clienti, immobilizzazioni (immateriali/materiali/finanziarie), rimanenze/magazzino, ratei e risconti attivi, crediti tributari/erario c/, crediti v/altri.
- PASSIVO + PATRIMONIO NETTO accounts normally carry an AVERE (credit) balance: debiti verso fornitori, banche c/c passive (scoperti), capitale sociale, riserve, fondo rischi, fondo TFR, debiti tributari, debiti v/istituti previdenziali, ratei e risconti passivi.
- Report every sp* field as a POSITIVE magnitude on its natural side.

CONTRA ACCOUNTS — NET THEM, never put in passivo:
- "Fondo ammortamento ..." (any: immobilizzazioni immateriali/materiali) is an AVERE account that REDUCES the related asset. Subtract it from the gross asset so sp02/sp03 are reported NET of their fondi ammortamento.
- "Fondo svalutazione crediti" reduces crediti: report sp06/sp07 NET of it.
- Do NOT classify these fondi as fondi rischi (sp14) or debiti.
- CRITICAL — DO NOT CONFUSE the FONDO with the YEAR'S EXPENSE. Two kinds of
  "ammortamento" accounts exist and only ONE nets the assets:
  * FONDO ammortamento (patrimonial, ACCUMULATED depreciation): named "FONDO
    AMM.TO ..." / "F.DO AMM ..." / "F/AMM ..." and listed AMONG THE PATRIMONIAL
    accounts (Stato Patrimoniale / Attivita'-Passivita' section). These NET the
    assets. The Fondo prefix may be OCR-garbled ("roNDO AMM.TO", "FONDa"): an
    account containing AMM that sits among the SP accounts is a fondo even with a
    corrupted prefix.
  * The YEAR'S depreciation EXPENSE: named "AMM.TO ..." / "AMMORTAMENTO ..." /
    "QUOTA AMMORTAMENTO ..." WITHOUT the Fondo prefix and listed among the COSTI
    of the CONTO ECONOMICO section. This is an economic account: NEVER subtract it
    from sp02/sp03 — doing so double-counts (the expense already reduced the
    year's result) and fabricates a wrong net book value.
  The reliable discriminator is the SECTION the account appears in (SP vs CE
  costs), not the exact spelling. If an asset has no patrimonial FONDO account,
  its net value IS the gross value.

MAPPING (description -> field), report NET magnitudes:
- sp01_crediti_soci: crediti verso soci per versamenti dovuti
- sp02_immob_immateriali: immobilizzazioni immateriali (avviamento, software, costi pluriennali) NET of fondo amm.to immateriali
- sp03_immob_materiali: immobilizzazioni materiali (terreni, fabbricati, impianti, macchinari, attrezzature, automezzi, mobili) NET of fondo amm.to materiali
- sp04_immob_finanziarie: partecipazioni, crediti immobilizzati, titoli immobilizzati
- sp05_rimanenze: rimanenze / magazzino (materie prime, prodotti, merci, lavori in corso)
- sp06_crediti_breve: crediti dell'attivo circolante esigibili ENTRO l'esercizio (clienti, tributari, v/altri) NET of fondo svalutazione
- sp07_crediti_lungo: crediti dell'attivo circolante esigibili OLTRE l'esercizio
- sp08_attivita_finanziarie: attivita' finanziarie non immobilizzate (titoli, partecipazioni non durevoli)
- sp09_disponibilita_liquide: cassa, denaro, banche e poste c/c ATTIVI (saldo Dare)
- sp10_ratei_risconti_attivi: ratei e risconti attivi
- sp11_capitale: capitale sociale
- sp12_riserve: TUTTE le riserve (sovrapprezzo, rivalutazione, legale, statutarie, straordinaria, altre) + utili/(perdite) portati a nuovo. Do NOT include the current-year result here.
- sp13_utile_perdita: the CURRENT YEAR result — see RESULT rule below
- sp14_fondi_rischi: fondi per rischi e oneri (NOT fondi ammortamento)
- sp15_tfr: fondo trattamento di fine rapporto (TFR)
- sp16_debiti_breve: debiti esigibili ENTRO l'esercizio (fornitori, banche c/c passive, tributari, previdenziali, v/altri)
- sp17_debiti_lungo: debiti esigibili OLTRE l'esercizio (mutui, finanziamenti a lungo)
- sp18_ratei_risconti_passivi: ratei e risconti passivi

CREDITOR / DEBTOR BREAKDOWN — PRESERVE THE SOURCE'S DETAIL DEPTH:
- A trial balance names each account by type (es. "DEBITI V/FORNITORI", "ERARIO C/IVA",
  "INPS C/CONTRIBUTI", "MUTUO BANCA..."). When the type is determinable from the
  description, you MUST fill the matching typed sub-field — do NOT collapse everything
  into the aggregate. The sub-fields must sum to the aggregate:
  * crediti: sp06a/sp07a clienti, sp06e/sp07e tributari (erario, IVA, ritenute),
    sp06f imposte anticipate, sp06g/sp07g altri
  * debiti: sp16a/sp17a banche, sp16b/sp17b altri finanziatori, sp16c/sp17c obbligazioni,
    sp16d/sp17d fornitori, sp16e/sp17e tributari, sp16f/sp17f previdenza, sp16g/sp17g altri
- RECOGNISE THE DEBT TYPE FROM THE ITALIAN DESCRIPTION (do NOT default to 'altri'):
  * banche (sp16a/sp17a): any "Banca"/"Banco"/name ending in -banca (EmilBanca), "Banco BPM",
    "BPER Banca"; a "c/c" or "c.c." account standing on the PASSIVO / Avere side is a bank
    OVERDRAFT (fido) = debito verso banche, NOT cash; also "mutuo", "finanziamento bancario",
    "anticipo fatture", "anticipi su crediti", "anticipi s.b.f.", "SBF", "scoperto di c/c".
  * fornitori (sp16d/sp17d): "fornitori", "debiti commerciali", "fatture da ricevere" / "FDR",
    "note credito da ricevere".
  * tributari (sp16e/sp17e): "erario", "erariali", "IVA", "imposte", "ritenute", "F24".
  * previdenza (sp16f/sp17f): "INPS", "INAIL", "enti previdenziali", "ENPALS", "INARCASSA".
  * altri finanziatori (sp16b/sp17b): "altri finanziatori", "factor"; "soci c/finanziamento"
    and "soci c/c" are altri finanziatori (D.3/D.5), NOT bank c/c.
- Only leave a sub-field at 0 when no account of that type exists. Put a debt/credit
  whose type you genuinely cannot tell into the 'altri' bucket (sp16g / sp06g), never
  silently into the bare aggregate.

RESULT OF THE YEAR (sp13) — THE BALANCING RULE:
- A trial balance usually has NO "utile d'esercizio" account: the profit/loss is implicit.
- Compute sp13 so that the sheet balances: sp13 = totale_attivo - (sp11 + sp12 + sp14 + sp15 + sp16 + sp17 + sp18).
- A POSITIVE sp13 = utile; a NEGATIVE sp13 = perdita. Keep the sign.
- Only if the trial balance EXPLICITLY shows a separate "Utile/Perdita d'esercizio" account, use that value and verify it equals the gap.

COMPLETENESS — THE MOST IMPORTANT RULE (do not drop accounts):
- EVERY patrimonial account line in the trial balance must be classified into exactly one sp field. Do not skip lines, do not stop early on long lists, scan ALL pages.
- The trial balance prints its OWN control total ("TOTALE A PAREGGIO", "TOTALE ATTIVITA'", "TOTALE PASSIVITA'"). Your sum of the asset accounts MUST reconcile to the declared "TOTALE ATTIVITA'" (GROSS, i.e. before you net the fondi). If your running asset total is materially below the printed total, you have MISSED accounts — go back and find them before answering. The single most common error is dropping a whole block of debiti (fornitori, banche, tributari, previdenziali) or a large immobilizzazioni mastro.
- MASTRO + DOTTED CHILDREN layout: some trial balances print each voce as a level-1 "mastro" WITH its subtotal (e.g. "102 IMMOBILIZZAZIONI IMMATERIALI 2.429.051"), immediately followed by indented dotted children ("102.00002 Software 12.000"). Book the MASTRO SUBTOTAL ONCE. Do NOT also add its children (double-count) and do NOT add only the children while skipping the mastro (drops the rounding/other lines). One amount per voce.

TOTALS:
- totale_attivo = sum of sp01..sp10 (all NET of contra accounts)
- totale_passivo = sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18
- totale_attivo MUST equal totale_passivo (sp13 absorbs the difference). Set both fields.
- Leave totale_debiti and totale_crediti at 0 unless the trial balance prints an explicit "Totale debiti"/"Totale crediti" line."""

TRIAL_BALANCE_CE_SYSTEM_PROMPT = """You are an expert Italian accountant reading a TRIAL BALANCE (bilancio di verifica / situazione contabile / saldi di contabilita' generale).

This is NOT a legal IV-CEE statement. It is a flat list of general-ledger accounts (conti CoGe). Your job: classify the ECONOMIC accounts (costi e ricavi) into the IV-CEE Conto Economico fields (ce01-ce20). IGNORE patrimonial accounts (assets, liabilities, equity) here.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimals (1.234.567,89 = 1234567.89)
- Parentheses or a trailing minus mean negative
- Return plain numbers without formatting, in full euros
- Report ALL COSTS as POSITIVE magnitudes (the model subtracts them). Report revenues as positive.

TRIAL-BALANCE SIGN CONVENTION:
- RICAVI / PROVENTI (revenue) accounts carry an AVERE (credit) balance.
- COSTI / ONERI (cost) accounts carry a DARE (debit) balance.
- Use the account's balance magnitude; the side identifies whether it is a revenue or a cost.

MAPPING (description -> field):
RICAVI (A — valore della produzione):
- ce01_ricavi_vendite: ricavi delle vendite e delle prestazioni (vendite merci/prodotti/servizi)
- ce02_variazioni_rimanenze: variazioni rimanenze di prodotti/semilavorati/lavori in corso
- ce03_lavori_interni: incrementi di immobilizzazioni per lavori interni
- ce04_altri_ricavi: altri ricavi e proventi, contributi in conto esercizio, sopravvenienze attive, rimborsi
COSTI (B — costi della produzione), all positive:
- ce05_materie_prime: acquisti di materie prime, sussidiarie, di consumo e merci
- ce06_servizi: costi per servizi (consulenze, utenze, trasporti, provvigioni, manutenzioni, compensi)
- ce07_godimento_beni: godimento beni di terzi (affitti, leasing, noleggi, royalties)
- ce08_costi_personale: TOTALE costi del personale (salari, stipendi, oneri sociali, TFR, altri)
- ce08a_tfr_accrual: quota TFR dell'esercizio (sub-item of ce08)
- ce09_ammortamenti: ammortamenti e svalutazioni (amm.to immateriali + materiali + svalutazioni crediti)
- ce10_var_rimanenze_mat_prime: variazioni rimanenze di materie prime/merci (segno: incremento rimanenze RIDUCE i costi)
- ce11_accantonamenti: accantonamenti per rischi
- ce11b_altri_accantonamenti: altri accantonamenti
- ce12_oneri_diversi: oneri diversi di gestione (imposte indirette, IMU, bolli, sopravvenienze passive, perdite su crediti)
AREA FINANZIARIA (C):
- ce13_proventi_partecipazioni: proventi da partecipazioni
- ce14_altri_proventi_finanziari: interessi attivi e altri proventi finanziari
- ce15_oneri_finanziari: interessi passivi e altri oneri finanziari (positive)
- ce16_utili_perdite_cambi: utili/perdite su cambi
RETTIFICHE (D) / STRAORDINARI (E) / IMPOSTE:
- ce17_rettifiche_attivita_fin: rivalutazioni/svalutazioni di attivita' finanziarie (net)
- ce18_proventi_straordinari: proventi straordinari
- ce19_oneri_straordinari: oneri straordinari (positive)
- ce20_imposte: imposte sul reddito dell'esercizio (IRES + IRAP) (positive)

RULES:
- AGGREGATE all account lines that map to the same ce* field (a trial balance has many detail accounts per IV-CEE item).
- NEVER leave the whole CE at zero when revenue and cost accounts are clearly present.
- Leave a field at 0 if no matching account exists.
- Extract the CURRENT YEAR values only."""


def _extract_full_text(file_path: str, max_pages: int = 60) -> str:
    """Return the concatenated text of (up to max_pages) PDF pages.

    Trial balances have no IV-CEE section headers to anchor on, so the whole
    account list is sent to the LLM rather than a detected SP/CE window.
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise PDFImportError(f"Cannot open PDF file: {e}")
    detached_texts = _detached_value_page_texts(doc)
    effective_pages = (len(doc) // 2) if detached_texts else len(doc)
    parts = []
    for i, page in enumerate(doc):
        if i >= effective_pages:
            break
        if i >= max_pages:
            break
        parts.append(
            detached_texts.get(i)
            or _filter_difference_columns(page)
            or reading_order_text(page)
        )
    doc.close()
    return "\n".join(parts)


# Completeness retry for the CoGe SP pass: the LLM stochastically drops accounts on
# long trial-balance lists. Re-run up to N times and keep the lowest-residual draw; stop
# early once a draw's estimated residual is under _COGE_SP_CLEAN_PCT of total assets.
_COGE_SP_MAX_ATTEMPTS = 3
_COGE_SP_CLEAN_PCT = Decimal("0.02")  # 2% of totale_attivo = "clean enough", stop retrying


def extract_trial_balance_with_llm(
    file_path: str,
    ocr_text: Optional[str] = None,
) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Extract a macro-area C trial balance (situazione contabile / CoGe accounts)
    with a dedicated LLM pass that understands Dare/Avere account balances.

    Unlike extract_pdf_with_llm (which reads the legal IV-CEE schema), this sends
    the FULL trial-balance text and uses CoGe-specific prompts to classify
    general-ledger accounts into sp01-sp18 / ce01-ce20, netting contra accounts
    and deriving the year's result as the Attivo-vs-Passivo gap.

    Returns:
        (balance_sheet_data, income_data) - dicts with full DB field names + Decimal values.

    Raises:
        PDFImportError: if the API key is missing or extraction fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise PDFImportError("ANTHROPIC_API_KEY environment variable not set")

    try:
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        raise PDFImportError(f"Failed to initialize Anthropic client: {e}")

    # Scanned PDF already OCR'd by the caller: prefer the TEXT path over vision. Vision
    # mis-parses Italian number formatting on noisy scans (reads "50.704,41" as
    # 5.070.441, inflating values ~100x and dumping the gap into sp13); the linear OCR
    # text keeps the decimal comma, so numbers come out right.
    use_ocr = bool(ocr_text and ocr_text.strip())
    text_garbled = False
    if use_ocr:
        is_image = False
        images = None
        full_text = ocr_text
    else:
        is_image = _is_image_pdf(file_path)
        images = _render_pdf_pages_as_images(file_path) if is_image else None
        full_text = None
        if not is_image:
            full_text = _extract_full_text(file_path)
            if not full_text.strip():
                raise PDFImportError("No text extracted from trial-balance PDF")
            # A PRESENT-but-CORRUPTED text layer (broken ToUnicode font map —
            # budget_337) makes the text path stochastic. Switching to vision was
            # TRIED (2026-07-15) and is NOT better on these dense layouts (drops
            # whole blocks, misreads small print); the file is flagged as garbled
            # by pdf_importer instead, so the user knows every value needs review.
            if _text_layer_is_garbled(full_text):
                text_garbled = True
                logger.warning("Trial-balance text layer is GARBLED (broken font "
                               "map) — extraction unreliable, declared totals ignored")

    # Declared control totals (TOTALE A PAREGGIO / ATTIVO / explicit Utile-Perdita) read
    # deterministically from the printed footer — used BOTH as a hint to the LLM AND as
    # the post-pass reconciliation anchor. On a scanned PDF read them from the OCR text.
    # On a GARBLED text layer the declared totals are misreads (a CE-section total can
    # land in 'perdita' and flip the result sign) — do not read them at all.
    try:
        declared = ({} if text_garbled else
                    _declared_control_totals(file_path, text=full_text if use_ocr else None))
    except Exception:
        declared = {}
    # Inject the declared totals as a completeness anchor in the SP system prompt.
    sp_prompt = TRIAL_BALANCE_SP_SYSTEM_PROMPT
    _anchor = declared.get("attivo") or declared.get("pareggio") if declared else None
    if _anchor:
        sp_prompt = (TRIAL_BALANCE_SP_SYSTEM_PROMPT
                     + f"\n\nDOCUMENT CONTROL TOTAL: the printed TOTALE ATTIVITA' / A PAREGGIO of "
                       f"THIS document is approximately {_anchor:,.0f} euro (gross). Your classified "
                       f"asset accounts (before netting fondi) must reconcile to this figure — if your "
                       f"sum is materially lower, you have dropped accounts: re-scan all pages.")

    def _extract_ce():
        if is_image:
            return _extract_with_llm_vision(
                client, images, TRIAL_BALANCE_CE_SYSTEM_PROMPT,
                IncomeStatementExtraction, "Situazione Contabile (CE)", tool_name="income_statement")
        return _extract_with_llm(
            client, full_text, TRIAL_BALANCE_CE_SYSTEM_PROMPT,
            IncomeStatementExtraction, "Situazione Contabile (CE)", tool_name="income_statement")

    def _extract_sp_once():
        if is_image:
            res = _extract_with_llm_vision(
                client, images, sp_prompt,
                BalanceSheetExtraction, "Situazione Contabile (SP)", tool_name="balance_sheet")
        else:
            res = _extract_with_llm(
                client, full_text, sp_prompt,
                BalanceSheetExtraction, "Situazione Contabile (SP)", tool_name="balance_sheet")
        bs = _model_to_decimal_dict(res)
        bs = _balance_trial_via_result(bs, "coge")
        try:
            bs = _reconcile_trial_to_declared(bs, declared, "coge")
        except Exception as _rec_err:
            logger.warning(f"[coge] declared-total reconciliation skipped: {_rec_err}")
        return bs

    # COMPLETENESS RETRY: the LLM stochastically drops accounts on long lists (proven by
    # byte-identical files extracting one complete / one short). Run the SP pass up to
    # _COGE_SP_MAX_ATTEMPTS times and keep the draw with the SMALLEST post-reconcile
    # _plug_residual (least estimated mass). Stop early once a draw is materially clean.
    best_bs = None
    best_resid = None
    for attempt in range(_COGE_SP_MAX_ATTEMPTS):
        bs = _extract_sp_once()
        resid = bs.get("_plug_residual", Decimal("0"))
        att = bs.get("totale_attivo", Decimal("0")) or Decimal("1")
        if best_bs is None or resid < best_resid:
            best_bs, best_resid = bs, resid
        logger.info(f"[CoGe] SP attempt {attempt + 1}/{_COGE_SP_MAX_ATTEMPTS}: "
                    f"totale_attivo={bs.get('totale_attivo')} plug_residual={resid}")
        if resid <= max(Decimal("1"), att * _COGE_SP_CLEAN_PCT):
            break  # clean enough, no need to retry

    balance_sheet_data = best_bs
    income_data = _normalize_ce_signs(_model_to_decimal_dict(_extract_ce()))

    logger.info(f"[CoGe] SP totale_attivo = {balance_sheet_data.get('totale_attivo')} "
                f"(plug_residual={best_resid})")

    # CE is left exactly as extracted; canonical validation happens downstream.

    return balance_sheet_data, income_data


# Asset-side sp fields used to recompute totale_attivo for the trial-balance identity.
_TB_ASSET_KEYS = [
    'sp01_crediti_soci', 'sp02_immob_immateriali', 'sp03_immob_materiali',
    'sp04_immob_finanziarie', 'sp05_rimanenze', 'sp06_crediti_breve',
    'sp07_crediti_lungo', 'sp08_attivita_finanziarie',
    'sp09_disponibilita_liquide', 'sp10_ratei_risconti_attivi',
]
# Passivo/PN fields EXCLUDING sp13 (the result, which absorbs the balancing gap).
_TB_PASSIVO_KEYS_NO_RESULT = [
    'sp11_capitale', 'sp12_riserve', 'sp14_fondi_rischi', 'sp15_tfr',
    'sp16_debiti_breve', 'sp17_debiti_lungo', 'sp18_ratei_risconti_passivi',
]


def _balance_trial_via_result(balance_sheet_data: Dict[str, Decimal], label: str) -> Dict[str, Decimal]:
    """Expose the balancing-result candidate without writing it into ``sp13``.

    The double-entry gap is useful evidence only when extraction coverage is known.
    Treating it as the actual result made every omitted liability look like profit.
    The explicit result and the independently reconstructed CE must confirm this
    candidate before an import can be accepted.
    """
    result = dict(balance_sheet_data)
    att = sum(balance_sheet_data.get(k, Decimal('0')) for k in _TB_ASSET_KEYS)
    pas_no_result = sum(balance_sheet_data.get(k, Decimal('0')) for k in _TB_PASSIVO_KEYS_NO_RESULT)
    candidate = att - pas_no_result
    current_sp13 = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
    result['totale_attivo'] = att
    result['totale_passivo'] = pas_no_result + current_sp13
    result['_derived_result_candidate'] = candidate
    difference = candidate - current_sp13
    if abs(difference) > Decimal('0.01'):
        result['_unexplained_result_difference'] = difference
        result['_plug_residual'] = max(
            abs(result.get('_plug_residual', Decimal('0'))), abs(difference)
        )
        logger.warning(
            f"[{label}] risultato implicito {candidate:,.2f} non confermato: sp13 "
            f"estratto {current_sp13:,.2f}; nessun valore è stato modificato"
        )
    return result


# Italian-number control token: decimal cents or whole euros with at least one
# thousands separator.  Legal IV-CEE statements commonly print rounded totals as
# ``6.474.612`` (budget_328); accepting only comma-decimal amounts made both source
# side controls disappear.  Plain unseparated integers stay excluded so years and
# item numbers in the 80-character label window cannot become accounting totals.
_DECL_NUM_RE = re.compile(
    r"-?(?:\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+,\d{2})"
)


def _declared_control_totals(file_path: str, text: Optional[str] = None) -> Dict[str, Optional[Decimal]]:
    """Read a trial balance's OWN declared control totals from the printed footer.

    GENERAL anti-masking anchor (level L2): every situazione contabile / bilancio di
    verifica prints its own control totals — "TOTALE A PAREGGIO", "TOTALE ATTIVO/
    ATTIVITA'", "TOTALE PASSIVO/PASSIVITA'", and (usually) an explicit
    "UTILE/PERDITA D'ESERCIZIO" (also "del periodo" / "in corso di formazione").
    These are GROUND TRUTH for the magnitude of the sheet. Returned so the extractor
    can reconcile its classified sums to them instead of silently forcing balance.

    Robust to letter-spaced headers ("T O T A L E   A T T I V O") via a no-spaces
    variant of the text, and to Italian number formatting. Returns the LARGEST amount
    found per label (detail lines repeat small partials; the control total is the max).
    All keys may be None when the document does not print that line.
    """
    out: Dict[str, Optional[Decimal]] = {
        "attivo": None, "passivo": None, "pareggio": None, "utile": None, "perdita": None,
        "costi": None, "ricavi": None,
    }
    # `text` lets the caller supply already-extracted text (e.g. OCR of a scanned PDF,
    # where _extract_full_text would return nothing). Fall back to reading the file.
    if text is None:
        try:
            text = _extract_full_text(file_path)
        except Exception:
            return out
    low = text.lower()
    # Strip accents so markers without accents ("totale attivita") match accented text
    # ("Totale attività") — common in trial-balance footers.
    import unicodedata
    low = "".join(c for c in unicodedata.normalize("NFKD", low) if not unicodedata.combining(c))
    nos = re.sub(r"[ \t]+", "", low)  # collapse intra-line spacing (keep newlines)

    def _largest_after(markers, hays=None) -> Optional[Decimal]:
        """Largest Italian-number amount occurring within ~80 chars after any marker.
        `hays` = [(text, is_nospaces), ...]; defaults to the full normal + no-spaces
        text. The no-spaces flag decides which form of the marker to search."""
        best: Optional[Decimal] = None
        for hay, is_nos in (hays or ((low, False), (nos, True))):
            for mk in markers:
                pat = re.escape(mk.replace(" ", "")) if is_nos else re.escape(mk)
                for hit in re.finditer(pat, hay):
                    window = hay[hit.end(): hit.end() + 80]
                    for nm in _DECL_NUM_RE.finditer(window):
                        try:
                            v = Decimal(nm.group(0).replace(".", "").replace(",", "."))
                        except Exception:
                            continue
                        av = abs(v)
                        if av > 0 and (best is None or av > best):
                            best = av
                        break  # first number after the marker is the total
        return best

    # "Totale a pareggio" (and its synonym "totale a quadratura") is printed for BOTH
    # the SP and the CE section of a trial balance. Largest-wins assumed the SP figure
    # is always the bigger one — FALSE on low-margin/high-turnover companies where the
    # CE total EXCEEDS the SP total (budget_337: CE 372.733,17 > SP 315.121,19), which
    # anchored the whole declared-reconcile to the CE figure. Scope the pareggio search
    # to the text BEFORE the "CONTO ECONOMICO" header (the SP section); fall back to
    # the full text when no CE header exists or the scoped search finds nothing.
    _ce_pos_low = low.find("conto economico")
    _ce_pos_nos = nos.find("contoeconomico")
    _sp_hays = ((low[:_ce_pos_low] if _ce_pos_low > 0 else low, False),
                (nos[:_ce_pos_nos] if _ce_pos_nos > 0 else nos, True))
    _pareggio_markers = ["totale a pareggio", "totale a quadratura"]
    out["pareggio"] = (_largest_after(_pareggio_markers, hays=_sp_hays)
                       or _largest_after(_pareggio_markers))
    out["attivo"] = _largest_after([
        "totale attivo", "totale attivita", "totale dell'attivo",
        "totale stato patrimoniale attivo", "totale stato patrimoniale - attivo",
    ])
    out["passivo"] = _largest_after([
        "totale passivo", "totale passivita", "totale a pareggio passivo",
        "totale passivo e patrimonio netto", "totale passivita e netto",
        "totale stato patrimoniale passivo", "totale stato patrimoniale - passivo",
    ])

    # Some detailed reclassified exports print the top-level section total directly
    # below ``Stato patrimoniale attivo/passivo`` without the word ``Totale``
    # (BILAQ-001).  Accept that value only when it is the *immediate next non-empty
    # line*: this deliberately does not treat the first detail amount below a plain
    # section header as a control total.
    def _section_heading_total(side: str) -> Optional[Decimal]:
        pattern = re.compile(
            rf"(?im)^\s*stato\s+patrimoniale\s+(?:-\s*)?{side}\s*$"
            rf"[ \t]*\r?\n[ \t]*({_DECL_NUM_RE.pattern})[ \t]*$"
        )
        values = []
        for match in pattern.finditer(low):
            try:
                values.append(abs(Decimal(
                    match.group(1).replace(".", "").replace(",", ".")
                )))
            except Exception:
                continue
        return max(values) if values else None

    if out["attivo"] is None:
        out["attivo"] = _section_heading_total("attivo")
    if out["passivo"] is None:
        out["passivo"] = _section_heading_total("passivo")
    out["utile"] = _largest_after([
        "utile d'esercizio", "utile dell'esercizio", "utile di esercizio",
        "utile del periodo", "utile in corso di formazione", "utile (perdita) dell'esercizio",
        "risultato d'esercizio", "risultato dell'esercizio",
    ])
    out["perdita"] = _largest_after([
        "perdita d'esercizio", "perdita dell'esercizio", "perdita di esercizio",
        "perdita del periodo", "perdita in corso di formazione",
    ])

    # Ancore della sezione economica. Servono al riscatto vision, che misura un CE
    # ricostruito contro il totale che il documento stampa: senza queste il CE non ha
    # alcun controllo indipendente (lo SP ha pareggio/attivo/passivo, il CE nulla).
    # "Totale costi della produzione (B)" e "Totale valore della produzione (A)" sono
    # SUBTOTALI di sezione dello schema IV-CEE, non i totali di colonna di una situazione
    # contabile: neutralizzali prima di cercare, o su un bilancio ordinario (che un totale
    # costi complessivo non lo stampa affatto) l'ancora tornerebbe sbagliata invece che None.
    _CE_SUBTOTAL_CAPTIONS = ("totale costi della produzione", "totale valore della produzione")
    _ce_low, _ce_nos = low, nos
    for _cap in _CE_SUBTOTAL_CAPTIONS:
        _ce_low = _ce_low.replace(_cap, "@")
        _ce_nos = _ce_nos.replace(_cap.replace(" ", ""), "@")
    _ce_hays = ((_ce_low, False), (_ce_nos, True))
    out["costi"] = _largest_after([
        "totale costi", "totale dei costi", "totale costi e oneri",
        "totale a pareggio costi",
    ], hays=_ce_hays)
    out["ricavi"] = _largest_after([
        "totale ricavi", "totale dei ricavi", "totale ricavi e proventi",
        "totale a pareggio ricavi",
    ], hays=_ce_hays)

    # In two-column trial balances PyMuPDF can emit the right-hand amount before
    # the left-hand label in linear text, so the after-label scan above sees no
    # result even though both are visibly on the same row (budget_188).  Geometry
    # is used only as a fallback and only for the explicit current-result label;
    # retained earnings ("utili portati a nuovo") are deliberately excluded.
    if out["utile"] is None or out["perdita"] is None:
        try:
            with fitz.open(file_path) as document:
                row_candidates = {"utile": [], "perdita": []}
                for page in document:
                    rows: List[List[Tuple]] = []
                    positioned_words = []
                    for word in page.get_text('words', sort=True):
                        rect = fitz.Rect(word[:4]) * page.rotation_matrix
                        positioned_words.append(
                            (rect.x0, rect.y0, rect.x1, rect.y1, word[4])
                        )
                    for word in sorted(
                        positioned_words,
                        key=lambda item: (float(item[1]), float(item[0])),
                    ):
                        if (
                            not rows
                            or abs(float(word[1]) - float(rows[-1][0][1])) > 2.0
                        ):
                            rows.append([word])
                        else:
                            rows[-1].append(word)
                    for row in rows:
                        caption = ' '.join(str(word[4]).casefold() for word in row)
                        caption = ''.join(
                            char for char in unicodedata.normalize('NFKD', caption)
                            if not unicodedata.combining(char)
                        )
                        if not any(term in caption for term in ('esercizio', 'periodo')):
                            continue
                        if (
                            'portat' in caption
                            or 'precedent' in caption
                            or 'utile/perdita' in caption
                        ):
                            continue
                        kind = (
                            'perdita' if 'perdita' in caption
                            else 'utile' if 'utile' in caption
                            else None
                        )
                        if kind is None:
                            continue
                        values = [
                            _parse_it_number(str(word[4])) for word in row
                            if _GEOMETRIC_NUMBER_RE.fullmatch(str(word[4]).strip())
                        ]
                        values = [abs(value) for value in values if value not in (None, 0)]
                        unique_values = set(values)
                        # A comparative result row can carry current and prior
                        # amounts.  Without a proven current-column anchor choosing
                        # either would be unsafe (budget_131), so geometry is accepted
                        # only when the row states one unambiguous amount.
                        if len(unique_values) == 1:
                            row_candidates[kind].append(unique_values.pop())
                for kind in ('utile', 'perdita'):
                    candidates = row_candidates[kind]
                    if (
                        len(candidates) >= 2
                        and all(value == candidates[0] for value in candidates[1:])
                    ):
                        # Require the same explicit result on at least two source
                        # rows/pages.  This rejects isolated prior-year result rows
                        # in comparative trial balances while retaining budget_188,
                        # whose current result is printed twice.
                        out[kind] = candidates[0]
        except Exception:
            pass
    return out


def _reconcile_trial_to_declared(balance_sheet_data: Dict[str, Decimal],
                                 declared: Dict[str, Optional[Decimal]],
                                 label: str,
                                 ce_result: Optional[Decimal] = None) -> Dict[str, Decimal]:
    """Compare extracted trial-balance controls without changing accounting fields.

    Older versions converted a result mismatch into short debt or cash and replaced
    ``sp13``.  The function now retains only diagnostic metadata: declared totals are
    independent evidence, never a licence to manufacture the missing side.
    """
    result = dict(balance_sheet_data)
    att = balance_sheet_data.get('totale_attivo', Decimal('0'))
    if att <= 0:
        return result
    tol = max(Decimal('50'), abs(att) * Decimal('0.005'))

    # signed declared result. A trial balance can print BOTH an "utile" and a
    # "perdita" line — or a spurious "RISULTATO D'ESERCIZIO" (a PRIOR-year PN
    # account) that _declared_control_totals reads as 'utile' (budget_211). Blindly
    # preferring utile then books the wrong sign. Arbitrate with the accounting gap:
    # when passivo EXCLUDES the result, attivo - passivo == the signed current
    # result (= ricavi - costi by double entry), so the declared value CLOSEST to
    # that gap is the true one. The CE-derived result is a fallback arbiter when the
    # gap is unavailable (passivo already includes the result → gap ~ 0). With no
    # anchor at all, preserve the legacy order (utile before perdita).
    candidates = []  # (signed_value, source)
    if declared.get('utile') is not None:
        candidates.append((declared['utile'], 'utile'))
    if declared.get('perdita') is not None:
        candidates.append((-declared['perdita'], 'perdita'))
    gap: Optional[Decimal] = None
    if declared.get('attivo') is not None and declared.get('passivo') is not None:
        _g = declared['attivo'] - declared['passivo']
        if abs(_g) > tol:
            gap = _g
    # _net_profit_from_ce returns Decimal('0') (never None) on an empty/zero CE, so
    # treat a 0 ce_result as "no anchor": otherwise a 0 anchor with candidates that
    # straddle zero (utile +U / perdita -P) would pick the SMALLER-magnitude one and
    # move mass. Falling through to `candidates[0]` preserves the legacy order.
    anchor = gap if gap is not None else (ce_result or None)
    decl_result: Optional[Decimal] = None
    if len(candidates) > 1 and anchor is not None:
        decl_result = min(candidates, key=lambda c: abs(c[0] - anchor))[0]
    elif candidates:
        decl_result = candidates[0][0]  # single candidate, or no anchor: legacy order
    elif gap is not None:
        decl_result = gap

    sp13 = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))

    # Recover an omitted SP result only when the source supplies three independent
    # and concordant facts: an explicit printed utile/perdita row, the CE result,
    # and the SP side gap before the result.  This is not a balancing plug: the
    # exact source value is restored to its legal field, and any unrelated residual
    # remains blocking.
    if sp13 == 0 and decl_result is not None and ce_result not in (None, 0):
        passivo_no_result = sum(
            balance_sheet_data.get(key, Decimal('0'))
            for key in _TB_PASSIVO_KEYS_NO_RESULT
        )
        source_gap = att - passivo_no_result
        source_tol = Decimal('2')
        if (
            abs(source_gap - decl_result) <= source_tol
            and abs(ce_result - decl_result) <= source_tol
        ):
            prior_residual = abs(result.get('_plug_residual', Decimal('0')))
            result['sp13_utile_perdita'] = decl_result
            result['totale_passivo'] = passivo_no_result + decl_result
            result['_source_result_reconciled'] = decl_result
            if abs(prior_residual - abs(decl_result)) <= source_tol:
                result['_plug_residual'] = Decimal('0')
            sp13 = decl_result
            logger.warning(
                "[%s] restored explicit source result %s after SP gap and CE "
                "independently confirmed it", label, decl_result,
            )

    # 1) Result difference: expose it, do not put it in sp16/sp09/sp13.
    if decl_result is not None and abs(sp13 - decl_result) > tol:
        residual = sp13 - decl_result
        result['_declared_result_difference'] = residual
        result['_plug_residual'] = max(
            abs(result.get('_plug_residual', Decimal('0'))), abs(residual)
        )
        _flag_unbalanced(
            label,
            f"sp13 derivato {sp13} != risultato dichiarato {decl_result}: ~{abs(residual)} "
            f"di massa o risultato non spiegato; nessuna voce è stata modificata",
            residual,
        )
        return result

    # 2) total-coverage fallback (flag only — side unknown, no mass moved)
    control = declared.get('attivo') or declared.get('passivo')
    if control and att + tol < control:
        gap = control - att
        result['_declared_total_difference'] = gap
        result['_plug_residual'] = max(
            abs(result.get('_plug_residual', Decimal('0'))), abs(gap))
        _flag_unbalanced(
            label,
            f"attivo estratto {att} < totale dichiarato {control}: ~{gap} di conti non "
            f"classificati (estrazione incompleta) — verificare in Rettifiche",
            gap,
        )
    return result


# Anti-masking guard: a plug correction is rejected (and surfaced as a warning)
# when it would drive a field negative, or when its magnitude exceeds this fraction
# of total assets (a correction that large is almost certainly a structural
# extraction error, not a roundable discrepancy — better to flag than to hide).
_PLUG_CAP_FRACTION = Decimal('0.05')


def _plug_cap(balance_sheet_data: Dict[str, Decimal]) -> Decimal:
    """Absolute cap on a single plug correction = 5% of totale_attivo (fallback to
    totale_passivo, then a flat floor) so the cap is meaningful even when one total
    is missing."""
    base = abs(balance_sheet_data.get('totale_attivo', Decimal('0')))
    if base == 0:
        base = abs(balance_sheet_data.get('totale_passivo', Decimal('0')))
    cap = base * _PLUG_CAP_FRACTION
    # never below a flat floor so tiny statements still get a sane allowance
    return max(cap, Decimal('5000'))


def _flag_unbalanced(label: str, reason: str, diff: Decimal) -> None:
    """Emit an explicit, visible imbalance warning so a rejected/insufficient plug
    surfaces as an error instead of being silently masked.

    Kept log-only (does not mutate the data dict) so the Dict[str, Decimal] contract
    consumed by the mapper / harness stays intact."""
    logger.warning(f"BILANCIO NON QUADRATO [{label}]: {reason} (diff={diff})")


def _reconcile_utile_in_passivo(balance_sheet_data: Dict[str, Decimal], label: str) -> Dict[str, Decimal]:
    """Add the result of the year (sp13) into totale_passivo when the layout reports
    'Totale Passivo' NET of the result.

    In "sezioni contrapposte" / "dettaglio voci" layouts the bottom of the liabilities
    column shows a 'Totale Passivo' that excludes the 'Utile/Perdita d'esercizio' line
    (the result sits on its own line, often next to 'Totale a pareggio'). The tell-tale
    sign is that the balance gap equals exactly the result:

        totale_attivo - totale_passivo == sp13_utile_perdita   (within tolerance)

    When detected, fold sp13 into totale_passivo so the downstream debt/equity
    validators derive the correct aggregates instead of cannibalising the reserves
    (budget_188 diff 133.744=utile; budget_249 diff 56.999=utile; budget_338 diff
    80.228≈utile; budget_213 perdita 90.819).
    """
    tot_attivo = balance_sheet_data.get('totale_attivo', Decimal('0'))
    tot_passivo = balance_sheet_data.get('totale_passivo', Decimal('0'))
    sp13 = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))

    if tot_attivo == 0 or tot_passivo == 0 or sp13 == 0:
        return balance_sheet_data

    gap = tot_attivo - tot_passivo
    # gap must match the result (same sign and magnitude) within a small tolerance.
    # Use a relative tolerance too, to absorb rounding on large statements.
    tol = max(Decimal('1'), abs(tot_attivo) * Decimal('0.0005'))
    if abs(gap - sp13) <= tol and abs(gap) > Decimal('1'):
        new_passivo = tot_passivo + sp13
        logger.warning(
            f"[{label}] Totale Passivo appears NET of result: "
            f"totale_attivo={tot_attivo}, totale_passivo={tot_passivo}, "
            f"gap={gap} ≈ utile(sp13)={sp13}. Folding result into totale_passivo "
            f"({tot_passivo} -> {new_passivo})."
        )
        balance_sheet_data['totale_passivo'] = new_passivo

    return balance_sheet_data


def _fit_breakdown_to_aggregate(balance_sheet_data: Dict[str, Decimal], aggregate: str,
                                groups: list, altri_key: str, label: str) -> None:
    """Reconcile a balance-relevant aggregate (sp06/sp07/sp16/sp17) DOWN to its typed
    sub-items when those sub-items overshoot it.

    The aggregate is anchored to the declared totals (totale_attivo / totale_debiti) and
    is what feeds the balance check, so it must NOT be inflated to a double-counted
    breakdown sum (that masks an asset/liability over-count and breaks the balance — see
    budget_208). Instead keep the aggregate fixed, zero the "altri" plug, and scale the
    remaining typed sub-items proportionally so they sum back to the aggregate. The detail
    is only a Rettifiche starting point; the aggregate stays correct.
    """
    total = balance_sheet_data.get(aggregate, Decimal('0'))
    others = [g for g in groups if g != altri_key]
    others_sum = sum(balance_sheet_data.get(g, Decimal('0')) for g in others)
    balance_sheet_data[altri_key] = Decimal('0')
    if others_sum > 0 and total > 0:
        scale = total / others_sum
        for g in others:
            balance_sheet_data[g] = balance_sheet_data.get(g, Decimal('0')) * scale
    elif total <= 0:
        for g in others:
            balance_sheet_data[g] = Decimal('0')
    _flag_unbalanced(
        label,
        f"breakdown {aggregate}: typed sub-items ({others_sum}) overshoot aggregate "
        f"({total}); kept aggregate and scaled sub-items down (no asset/liability inflation)",
        others_sum - total,
    )


def _validate_crediti(balance_sheet_data: Dict[str, Decimal], label: str) -> Dict[str, Decimal]:
    """Validate crediti: sp06 + sp07 must not exceed the crediti implied by totale_attivo.

    If totale_attivo is available, crediti = totale_attivo - (sp01..sp05 + sp08 + sp09 + sp10).
    If sp06 + sp07 overshoots, the LLM likely put total crediti in sp06 instead of just entro.
    Fix: sp06 = total_crediti - sp07.
    """
    tot_attivo = balance_sheet_data.get('totale_attivo', Decimal('0'))
    if tot_attivo == 0:
        return balance_sheet_data

    sp01 = balance_sheet_data.get('sp01_crediti_soci', Decimal('0'))
    sp02 = balance_sheet_data.get('sp02_immob_immateriali', Decimal('0'))
    sp03 = balance_sheet_data.get('sp03_immob_materiali', Decimal('0'))
    sp04 = balance_sheet_data.get('sp04_immob_finanziarie', Decimal('0'))
    sp05 = balance_sheet_data.get('sp05_rimanenze', Decimal('0'))
    sp06 = balance_sheet_data.get('sp06_crediti_breve', Decimal('0'))
    sp07 = balance_sheet_data.get('sp07_crediti_lungo', Decimal('0'))
    sp08 = balance_sheet_data.get('sp08_attivita_finanziarie', Decimal('0'))
    sp09 = balance_sheet_data.get('sp09_disponibilita_liquide', Decimal('0'))
    sp10 = balance_sheet_data.get('sp10_ratei_risconti_attivi', Decimal('0'))

    non_crediti = sp01 + sp02 + sp03 + sp04 + sp05 + sp08 + sp09 + sp10
    expected_crediti = tot_attivo - non_crediti
    actual_crediti = sp06 + sp07

    diff = actual_crediti - expected_crediti
    cap = _plug_cap(balance_sheet_data)

    def _apply_sp06(new_sp06: Decimal, kind: str) -> None:
        """Apply the sp06 plug only if it passes the anti-masking guards
        (non-negative result + magnitude under cap); otherwise flag the imbalance."""
        change = abs(new_sp06 - sp06)
        if new_sp06 < 0:
            _flag_unbalanced(label, f"crediti {kind}: refusing sp06 plug -> {new_sp06} (negative)", diff)
            return
        if change > cap:
            _flag_unbalanced(
                label,
                f"crediti {kind}: sp06 plug {sp06} -> {new_sp06} exceeds cap {cap}; not applied",
                diff,
            )
            return
        logger.warning(
            f"[{label}] Crediti {kind}: sp06+sp07={actual_crediti} but expected={expected_crediti} "
            f"(diff={diff}). Correcting sp06 from {sp06} to {new_sp06}"
        )
        balance_sheet_data['sp06_crediti_breve'] = new_sp06

    if diff > Decimal('1') and sp07 > 0 and abs(diff - sp07) <= Decimal('1'):
        # Classic double-count: LLM put total crediti in sp06, then also added sp07
        _apply_sp06(expected_crediti - sp07, "double-count")
    elif diff > Decimal('1'):
        # General overshoot — correct sp06
        _apply_sp06(expected_crediti - sp07, "overshoot")
    elif diff < Decimal('-1'):
        # Undershoot — LLM likely missed "imposte anticipate" or other crediti items
        _apply_sp06(expected_crediti - sp07, "undershoot (likely imposte anticipate)")

    # Reconcile debtor-type breakdown against the aggregates.
    # Residual (aggregate − sum of a..g) plugs into the "altri" bucket (g), so
    # sum of detail always matches sp06_crediti_breve / sp07_crediti_lungo and
    # the Rettifiche journal has a meaningful starting point.
    _CREDIT_BREVE_GROUPS = ['sp06a_crediti_clienti_breve', 'sp06b_crediti_controllate_breve',
                            'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve',
                            'sp06e_crediti_tributari_breve', 'sp06f_imposte_anticipate_breve',
                            'sp06g_crediti_altri_breve']
    _CREDIT_LUNGO_GROUPS = ['sp07a_crediti_clienti_lungo', 'sp07b_crediti_controllate_lungo',
                            'sp07c_crediti_collegate_lungo', 'sp07d_crediti_controllanti_lungo',
                            'sp07e_crediti_tributari_lungo', 'sp07f_imposte_anticipate_lungo',
                            'sp07g_crediti_altri_lungo']
    for aggregate, groups, altri_key in (
        ('sp06_crediti_breve', _CREDIT_BREVE_GROUPS, 'sp06g_crediti_altri_breve'),
        ('sp07_crediti_lungo', _CREDIT_LUNGO_GROUPS, 'sp07g_crediti_altri_lungo'),
    ):
        total = balance_sheet_data.get(aggregate, Decimal('0'))
        breakdown_sum = sum(balance_sheet_data.get(g, Decimal('0')) for g in groups)
        residual = total - breakdown_sum
        if abs(residual) > Decimal('1'):
            current_altri = balance_sheet_data.get(altri_key, Decimal('0'))
            new_altri = current_altri + residual
            # Anti-masking guard: never let the "altri" bucket go negative. A negative
            # residual means the typed sub-totals exceed the aggregate; lift the
            # aggregate to the breakdown sum instead of fabricating a negative credit.
            if new_altri < 0:
                # Sub-items overshoot the aggregate: keep the (declared-total-anchored)
                # aggregate and scale the breakdown down — never inflate assets.
                _fit_breakdown_to_aggregate(balance_sheet_data, aggregate, groups, altri_key, label)
            else:
                logger.info(
                    f"[{label}] Credit breakdown residual for {aggregate}: "
                    f"aggregate={total}, breakdown_sum={breakdown_sum}, plugging {residual} into {altri_key}"
                )
                balance_sheet_data[altri_key] = new_altri

    return balance_sheet_data


def _validate_debiti(balance_sheet_data: Dict[str, Decimal], label: str) -> Dict[str, Decimal]:
    """Validate and auto-correct debt split: sp16 + sp17 must equal total debiti.

    Uses the explicit `totale_debiti` field from the PDF when present (most reliable).
    Falls back to inference from totale_passivo - (patrimonio_netto + fondi + tfr + ratei)
    when the explicit value is missing.
    """
    sp16 = balance_sheet_data.get('sp16_debiti_breve', Decimal('0'))
    sp17 = balance_sheet_data.get('sp17_debiti_lungo', Decimal('0'))
    explicit_total = balance_sheet_data.get('totale_debiti', Decimal('0'))

    if explicit_total > 0:
        total_debiti = explicit_total
        source = "explicit"
    else:
        tot_passivo = balance_sheet_data.get('totale_passivo', Decimal('0'))
        if tot_passivo == 0:
            return balance_sheet_data
        sp11 = balance_sheet_data.get('sp11_capitale', Decimal('0'))
        sp12 = balance_sheet_data.get('sp12_riserve', Decimal('0'))
        sp13 = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
        sp14 = balance_sheet_data.get('sp14_fondi_rischi', Decimal('0'))
        sp15 = balance_sheet_data.get('sp15_tfr', Decimal('0'))
        sp18 = balance_sheet_data.get('sp18_ratei_risconti_passivi', Decimal('0'))
        total_debiti = tot_passivo - (sp11 + sp12 + sp13) - sp14 - sp15 - sp18
        source = "inferred"

    debt_sum = sp16 + sp17
    diff = abs(debt_sum - total_debiti)
    cap = _plug_cap(balance_sheet_data)

    if diff > Decimal('1') and total_debiti > 0:
        new_sp16 = total_debiti - sp17
        if new_sp16 >= 0:
            # Cap guard: a sp16 plug larger than 5% of total assets is almost
            # certainly a structural error (e.g. inferred total_debiti was wrong
            # because totale_passivo was net of the result). Flag instead of mask.
            if source == "inferred" and abs(new_sp16 - sp16) > cap:
                _flag_unbalanced(
                    label,
                    f"debiti (inferred): sp16 plug {sp16} -> {new_sp16} exceeds cap {cap}; not applied",
                    diff,
                )
            else:
                logger.warning(
                    f"[{label}] Debt mismatch ({source}): sp16+sp17={debt_sum} but total debiti={total_debiti} "
                    f"(diff={diff}). Correcting sp16 from {sp16} to {new_sp16}"
                )
                balance_sheet_data['sp16_debiti_breve'] = new_sp16
        else:
            # sp17 exceeds total debiti — correct sp17 instead
            logger.warning(
                f"[{label}] Debt mismatch ({source}): sp17={sp17} > total debiti={total_debiti}. "
                f"Correcting sp17 to {total_debiti} and sp16 to 0"
            )
            balance_sheet_data['sp17_debiti_lungo'] = total_debiti
            balance_sheet_data['sp16_debiti_breve'] = Decimal('0')

    # Reconcile creditor-type breakdown against the aggregates.
    # Any residual (aggregate − sum of a..g) is plugged into the "altri" bucket (g)
    # so the Rettifiche journal always has a meaningful starting point and sums
    # back to sp16_debiti_breve / sp17_debiti_lungo.
    _DEBT_BREVE_GROUPS = ['sp16a_debiti_banche_breve', 'sp16b_debiti_altri_finanz_breve',
                          'sp16c_debiti_obbligazioni_breve', 'sp16d_debiti_fornitori_breve',
                          'sp16e_debiti_tributari_breve', 'sp16f_debiti_previdenza_breve',
                          'sp16g_altri_debiti_breve']
    _DEBT_LUNGO_GROUPS = ['sp17a_debiti_banche_lungo', 'sp17b_debiti_altri_finanz_lungo',
                          'sp17c_debiti_obbligazioni_lungo', 'sp17d_debiti_fornitori_lungo',
                          'sp17e_debiti_tributari_lungo', 'sp17f_debiti_previdenza_lungo',
                          'sp17g_altri_debiti_lungo']
    for aggregate, groups, altri_key in (
        ('sp16_debiti_breve', _DEBT_BREVE_GROUPS, 'sp16g_altri_debiti_breve'),
        ('sp17_debiti_lungo', _DEBT_LUNGO_GROUPS, 'sp17g_altri_debiti_lungo'),
    ):
        total = balance_sheet_data.get(aggregate, Decimal('0'))
        breakdown_sum = sum(balance_sheet_data.get(g, Decimal('0')) for g in groups)
        residual = total - breakdown_sum
        if abs(residual) > Decimal('1'):
            current_altri = balance_sheet_data.get(altri_key, Decimal('0'))
            new_altri = current_altri + residual
            # Anti-masking guard: never let the "altri" bucket go negative. A negative
            # residual means the LLM's typed sub-totals already EXCEED the aggregate
            # (the breakdown, not the bucket, is wrong) — plugging it would produce an
            # impossible negative debt (budget_213/249 sp16g/sp17g went negative).
            # In that case lift the aggregate to the breakdown sum instead and flag.
            if new_altri < 0:
                # Sub-items overshoot the aggregate: keep the (declared-total-anchored)
                # aggregate and scale the breakdown down — never inflate liabilities.
                _fit_breakdown_to_aggregate(balance_sheet_data, aggregate, groups, altri_key, label)
            else:
                logger.info(
                    f"[{label}] Debt breakdown residual for {aggregate}: "
                    f"aggregate={total}, breakdown_sum={breakdown_sum}, plugging {residual} into {altri_key}"
                )
                balance_sheet_data[altri_key] = new_altri

    return balance_sheet_data


def _validate_equity(balance_sheet_data: Dict[str, Decimal], label: str) -> Dict[str, Decimal]:
    """Validate and auto-correct equity consistency for a single year."""
    sp11 = balance_sheet_data.get('sp11_capitale', Decimal('0'))
    sp12 = balance_sheet_data.get('sp12_riserve', Decimal('0'))
    sp13 = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
    computed_equity = sp11 + sp12 + sp13
    tot_passivo = balance_sheet_data.get('totale_passivo', Decimal('0'))
    liabilities = (
        balance_sheet_data.get('sp14_fondi_rischi', Decimal('0')) +
        balance_sheet_data.get('sp15_tfr', Decimal('0')) +
        balance_sheet_data.get('sp16_debiti_breve', Decimal('0')) +
        balance_sheet_data.get('sp17_debiti_lungo', Decimal('0')) +
        balance_sheet_data.get('sp18_ratei_risconti_passivi', Decimal('0'))
    )
    expected_equity = tot_passivo - liabilities
    equity_diff = abs(computed_equity - expected_equity)
    if equity_diff > Decimal('1'):
        new_sp12 = expected_equity - sp11 - sp13
        change = abs(new_sp12 - sp12)
        # Anti-masking guards on the reserves tap:
        #  * never let reserves go negative (impossible total reserves);
        #  * never absorb an EGREGIOUS discrepancy into reserves — that signals the
        #    imbalance is structural (wrong debiti, totale_passivo net of the result,
        #    missing liabilities) and must surface rather than hide in sp12
        #    (budget_158/238 inflated reserves by >1 mln).
        # The equity cap is intentionally LOOSER than the crediti/debiti cap: moderate
        # reserve corrections on small companies are legitimate (a €40k plug on a €350k
        # statement is normal rounding/sub-item absorption — budget_275). We only reject
        # plugs that are BOTH a large fraction of assets AND large in absolute terms.
        equity_cap = max(_plug_cap(balance_sheet_data) * Decimal('3'), Decimal('150000'))

        # Balance-validated override: when BOTH declared totals are present and equal AND the
        # asset side already reconstructs totale_attivo, the imbalance lives ENTIRELY in the
        # equity composition — the LLM mis-extracted reserves (common with NEGATIVE equity:
        # budget_297 prior 2024 had PN −75.414, riserve extracted as 1.152.513 vs the 152.023
        # that makes both sides reconcile). The corrected sp12 then makes the whole statement
        # tie out to the declared totals, so it is a legitimate fix, not masking — apply it even
        # past the cap. Structural imbalances (asset side NOT reconstructing the total, or the
        # two declared totals disagreeing) do not qualify and still surface.
        tot_attivo = balance_sheet_data.get('totale_attivo', Decimal('0'))
        _ATT_KEYS = ['sp01_crediti_soci', 'sp02_immob_immateriali', 'sp03_immob_materiali',
                     'sp04_immob_finanziarie', 'sp05_rimanenze', 'sp06_crediti_breve',
                     'sp07_crediti_lungo', 'sp08_attivita_finanziarie',
                     'sp09_disponibilita_liquide', 'sp10_ratei_risconti_attivi']
        att_sum = sum(balance_sheet_data.get(k, Decimal('0')) for k in _ATT_KEYS)
        balance_validated = (
            tot_passivo > 0 and tot_attivo > 0
            and abs(tot_attivo - tot_passivo) <= Decimal('1')
            and abs(att_sum - tot_attivo) <= Decimal('1')
            and new_sp12 >= 0
        )

        if new_sp12 < 0:
            _flag_unbalanced(
                label,
                f"equity: refusing sp12 plug {sp12} -> {new_sp12} (negative reserves)",
                equity_diff,
            )
        elif change > equity_cap and not balance_validated:
            _flag_unbalanced(
                label,
                f"equity: sp12 plug {sp12} -> {new_sp12} exceeds cap {equity_cap}; not applied "
                f"(structural imbalance, not a reserve error)",
                equity_diff,
            )
        else:
            extra = " [balance-validated: asset side ties to declared total]" if (
                change > equity_cap and balance_validated) else ""
            logger.warning(
                f"[{label}] Equity mismatch: sp11+sp12+sp13={computed_equity} but "
                f"totale_passivo-liabilities={expected_equity} (diff={equity_diff}). "
                f"Correcting sp12_riserve from {sp12} to {new_sp12}{extra}"
            )
            balance_sheet_data['sp12_riserve'] = new_sp12
    return balance_sheet_data


def _ce_risultato_ante(ce_data: Dict[str, Decimal]) -> Decimal:
    """Compatibility wrapper around the canonical pre-tax CE formula."""
    return calculate_ce_result(ce_data).profit_before_tax


def _validate_ce10_against_bs(
    ce_data: Dict[str, Decimal],
    bs_data: Dict[str, Decimal],
    label: str,
) -> Dict[str, Decimal]:
    """Reconcile ce10 (variazioni rimanenze materie prime) against the BS utile anchor.

    item 11 is a VARIATION, not a pure cost: a cost when inventory falls (positive in
    the model), a CREDIT when inventory rises (negative). The LLM mis-handles it in two
    recurring ways that throw the whole CE off while the balance-sheet utile (sp13) —
    independently pinned by a balancing BS — stays correct:

      * WRONG SIGN (convention): the residual gap equals -2*ce10 → flip the sign.
        (e.g. ALMA budget_271: +7.831 credit stored as a cost → CE off by 2*7.831.)
      * SPURIOUS VALUE (mis-attributed prior-year/blank column): the residual gap
        equals -ce10 → the current-year item 11 is really 0 and the LLM grabbed an
        adjacent column. (e.g. ELLE ERRE budget_144/328: item 11 prints "(300.567)"
        in the prior column; the PDF's own "Totale costi"/"A-B" totals imply ce10=0,
        and the booked utile only reconciles at ce10=0.)

    Both are exact-coincidence detectors (tol €2), so an unrelated extraction error
    never triggers a spurious correction, and they are mutually exclusive for ce10≠0.
    Gated on a BALANCING BS so sp13 is a trustworthy anchor.
    """
    ce10 = ce_data.get('ce10_var_rimanenze_mat_prime', Decimal('0'))
    sp13 = bs_data.get('sp13_utile_perdita', Decimal('0'))
    if ce10 == 0 or sp13 == 0:
        return ce_data

    # sp13 is only a reliable anchor when the BS actually balances.
    tot_att = bs_data.get('totale_attivo', Decimal('0'))
    tot_pas = bs_data.get('totale_passivo', Decimal('0'))
    if tot_att == 0 or abs(tot_att - tot_pas) > Decimal('2'):
        return ce_data

    utile_ce = _ce_risultato_ante(ce_data) - ce_data.get('ce20_imposte', Decimal('0'))
    gap = utile_ce - sp13
    tol = Decimal('2')  # whole-euro reports; allow minor rounding
    if abs(gap) <= tol:
        return ce_data

    # Flipping ce10 shifts COPRO by -2*ce10 (utile_ce by +2*ce10); zeroing it shifts
    # COPRO by +ce10 (utile_ce by -ce10).
    if abs(gap + 2 * ce10) <= tol:
        ce_data['ce10_var_rimanenze_mat_prime'] = -ce10
        logger.warning(
            f"[{label}] ce10 sign correction: {ce10} -> {-ce10} reconciles CE utile "
            f"({utile_ce}) with BS sp13 ({sp13}); residual gap was {gap}."
        )
    elif abs(gap + ce10) <= tol:
        ce_data['ce10_var_rimanenze_mat_prime'] = Decimal('0')
        logger.warning(
            f"[{label}] ce10 spurious-value correction: {ce10} -> 0 reconciles CE utile "
            f"({utile_ce}) with BS sp13 ({sp13}); residual gap was {gap} "
            f"(likely a mis-attributed prior-year column)."
        )
    return ce_data


def _validate_ce_imposte(
    ce_data: Dict[str, Decimal],
    bs_data: Dict[str, Decimal],
    label: str,
) -> Dict[str, Decimal]:
    """Cross-check ce20_imposte against BS utile and CE risultato ante imposte.

    In multi-column PDFs (e.g. "Stampa dettaglio voci"), when a year has zero
    imposte the LLM may pick up the other year's value.  Fix by computing:
      expected_imposte = risultato_ante_imposte - utile_from_BS
    """
    sp13 = bs_data.get('sp13_utile_perdita', Decimal('0'))
    # Compute risultato ante imposte from CE fields
    risultato_ante = _ce_risultato_ante(ce_data)
    expected_imposte = risultato_ante - sp13

    ce20 = ce_data.get('ce20_imposte', Decimal('0'))
    diff = abs(ce20 - expected_imposte)

    # Only overwrite the extracted imposte when we are confident the LLM picked up
    # the WRONG value (typically the other year's column on multi-year layouts).
    # Guards against the failure mode where a miscomputed VdP (e.g. ce03 lavori
    # interni excluded) produces a bogus expected_imposte that clobbers a correctly
    # extracted ce20 (budget_256 GHEDA: real 117.892 was being forced to 28.421).
    #
    # Preconditions for a correction:
    #   - sp13 must be a real BS anchor (non-zero); without it expected_imposte is
    #     meaningless and we must not touch the extracted value.
    #   - expected_imposte must be non-negative (negative => our CE reconstruction
    #     is off, not the imposte) and smaller in magnitude than the extracted ce20
    #     (the classic "wrong column was larger" case).
    #   - the extracted ce20 must NOT already reconcile the BS utile: if
    #     |risultato_ante - ce20 - sp13| <= 1 then PBT - imposte == utile_BS already,
    #     so the extracted imposte is internally consistent and must be kept.
    reconciles_bs = abs(risultato_ante - ce20 - sp13) <= Decimal('1')

    # Case 0 — imposte line entirely MISSING. The LLM sometimes drops the
    # "20) Imposte sul reddito" value (returns ce20≈0) on layouts where the line is
    # present but visually detached from its amount. The BS utile anchor then implies
    # a real positive tax (PBT > utile_BS). Fill it in so the CE bottom line reconciles
    # to sp13. Tightly guarded so a correctly-extracted imposte is never touched:
    #   - ce20 must be ~0 (nothing to clobber — distinct from the GHEDA "wrong column"
    #     case where ce20 is a real non-zero value handled below);
    #   - PBT (risultato_ante) must be positive and the implied tax a plausible
    #     fraction of it (0 < imposte < PBT), i.e. not a tax credit nor larger than
    #     the pre-tax profit (which would mean the gap is some other CE error, e.g.
    #     a fabricated cost like budget_328's ce10 — left untouched on purpose).
    if (
        diff > Decimal('1')
        and sp13 != 0
        and abs(ce20) <= Decimal('1')
        and risultato_ante > 0
        and Decimal('0') < expected_imposte < risultato_ante
        and not reconciles_bs
    ):
        logger.warning(
            f"[{label}] ce20_imposte missing (extracted={ce20}); filling from BS anchor: "
            f"risultato_ante {risultato_ante} - utile_BS {sp13} = {expected_imposte}."
        )
        ce_data['ce20_imposte'] = expected_imposte
        return ce_data

    if (
        diff > Decimal('1')
        and sp13 != 0
        and expected_imposte >= 0
        and abs(expected_imposte) < abs(ce20) + Decimal('1')
        and not reconciles_bs
    ):
        logger.warning(
            f"[{label}] ce20_imposte cross-check: extracted={ce20}, "
            f"expected (risultato_ante {risultato_ante} - utile_BS {sp13})={expected_imposte}. "
            f"Correcting."
        )
        ce_data['ce20_imposte'] = max(expected_imposte, Decimal('0'))
    elif diff > Decimal('1'):
        logger.info(
            f"[{label}] ce20_imposte cross-check skipped (extracted={ce20}, "
            f"expected={expected_imposte}, sp13={sp13}, reconciles_bs={reconciles_bs}): "
            f"keeping extracted value."
        )

    return ce_data


def _prior_column_is_absent(
    current_bs: Dict[str, Decimal],
    current_ce: Dict[str, Decimal],
    prior_bs: Dict[str, Decimal],
    prior_ce: Dict[str, Decimal],
) -> bool:
    """Detect a MONOCOLUMN (single-year) PDF where the LLM fabricated a prior year.

    On a one-column statement there is no prior column to read, so the model tends to
    either (a) clone the current values into prior, or (b) leave prior almost empty
    apart from an orphan figure it carried over. Both produce a bogus prior year that
    the downstream "prior all zeros" guard in pdf_importer does NOT catch (because the
    clone isn't zero). We detect the physical absence here and let the caller drop it.

    Heuristics (any one is sufficient):
      * Prior balance-sheet aggregates are a near-exact clone of current (same totale
        attivo + same key items) AND prior CE has no revenue — i.e. the BS was copied
        but there was never a second CE column. Clone of a real two-year statement
        would have *different* totals, so equality is the tell.
      * Prior has no meaningful activity at all (no totale_attivo and no CE revenue)
        beyond a stray orphan value.
    """
    def _g(d: Dict[str, Decimal], k: str) -> Decimal:
        return d.get(k, Decimal('0'))

    cur_attivo = _g(current_bs, 'totale_attivo')
    pri_attivo = _g(prior_bs, 'totale_attivo')
    cur_ricavi = _g(current_ce, 'ce01_ricavi_vendite')
    pri_ricavi = _g(prior_ce, 'ce01_ricavi_vendite')

    # Key BS items to compare for clone detection
    _KEY_BS = ['totale_attivo', 'totale_passivo', 'sp03_immob_materiali',
               'sp06_crediti_breve', 'sp09_disponibilita_liquide',
               'sp11_capitale', 'sp16_debiti_breve']

    def _near(a: Decimal, b: Decimal) -> bool:
        if a == 0 and b == 0:
            return True
        scale = max(abs(a), abs(b), Decimal('1'))
        return abs(a - b) <= scale * Decimal('0.001')

    bs_is_clone = (
        cur_attivo != 0
        and all(_near(_g(current_bs, k), _g(prior_bs, k)) for k in _KEY_BS)
    )

    # Prior CE essentially empty (no revenue) while current has revenue
    prior_ce_empty = (pri_ricavi == 0 and cur_ricavi != 0)

    if bs_is_clone and prior_ce_empty:
        return True

    # Prior has no real substance at all (everything zero apart from possible orphan)
    prior_no_activity = (pri_attivo == 0 and pri_ricavi == 0)
    current_has_activity = (cur_attivo != 0 or cur_ricavi != 0)
    if prior_no_activity and current_has_activity:
        return True

    return False


def extract_pdf_both_years_with_llm(
    file_path: str,
) -> Tuple[Dict[str, Decimal], Dict[str, Decimal], Dict[str, Decimal], Dict[str, Decimal]]:
    """
    Extract balance sheet and income statement for BOTH years from a PDF.

    Same 2 API calls as single-year extraction, but with richer output models
    that capture both the current-year and prior-year columns.

    Args:
        file_path: Path to the PDF file

    Returns:
        (current_bs, current_ce, prior_bs, prior_ce) — all Dict[str, Decimal]

    Raises:
        PDFImportError: If extraction fails
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise PDFImportError("ANTHROPIC_API_KEY environment variable not set")

    try:
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        raise PDFImportError(f"Failed to initialize Anthropic client: {e}")

    # Step 1: Check if PDF is image-based (no extractable text)
    use_vision = _is_image_pdf(file_path)

    if use_vision:
        logger.info("Image-based PDF detected, using vision extraction (both years)")
        all_images = _render_pdf_pages_as_images(file_path)

        # Step 2v: Extract balance sheet (both years) via vision
        try:
            sp_result = _extract_with_llm_vision(
                client, all_images, SP_BOTH_YEARS_SYSTEM_PROMPT,
                TwoYearBalanceSheetExtraction, "Stato Patrimoniale (both years)",
                tool_name="balance_sheet_both_years",
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during SP vision extraction: {e}")

        # Step 3v: Extract income statement (both years) via vision
        try:
            ce_result = _extract_with_llm_vision(
                client, all_images, CE_BOTH_YEARS_SYSTEM_PROMPT,
                TwoYearIncomeStatementExtraction, "Conto Economico (both years)",
                tool_name="income_statement_both_years",
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during CE vision extraction: {e}")
    else:
        # Step 1b: Extract relevant page text with PyMuPDF
        sp_text, ce_text = extract_relevant_pages(file_path)

        if not sp_text.strip():
            raise PDFImportError("No text extracted from balance sheet pages")

        # Step 2: Extract balance sheet (both years) via Claude Haiku
        try:
            sp_result = _extract_with_llm(
                client, sp_text, SP_BOTH_YEARS_SYSTEM_PROMPT,
                TwoYearBalanceSheetExtraction, "Stato Patrimoniale (both years)",
                tool_name="balance_sheet_both_years",
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during SP extraction: {e}")

        # Step 3: Extract income statement (both years) via Claude Haiku
        try:
            ce_result = _extract_with_llm(
                client, ce_text, CE_BOTH_YEARS_SYSTEM_PROMPT,
                TwoYearIncomeStatementExtraction, "Conto Economico (both years)",
                tool_name="income_statement_both_years",
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during CE extraction: {e}")

    # Step 4: Convert to Decimal dicts and normalize signs
    current_bs = _reconcile_credit_aggregates_from_source(
        _model_to_decimal_dict(sp_result.current_year), "current"
    )
    prior_bs = _reconcile_credit_aggregates_from_source(
        _model_to_decimal_dict(sp_result.prior_year), "prior"
    )
    current_bs, prior_bs = _reconcile_blank_current_sp_cells(
        file_path, current_bs, prior_bs
    )
    current_bs = _recover_printed_sp_rows(file_path, current_bs)
    current_bs = _split_printed_debt_maturities(file_path, current_bs)
    current_bs = _recover_printed_fixed_asset_details(file_path, current_bs)
    raw_current_ce = _model_to_decimal_dict(ce_result.current_year)
    raw_prior_ce = _model_to_decimal_dict(ce_result.prior_year)
    current_ce = _normalize_ce_signs(dict(raw_current_ce))
    prior_ce = _normalize_ce_signs(dict(raw_prior_ce))
    current_ce, prior_ce = _reconcile_blank_current_ce_cells(
        file_path, current_ce, prior_ce
    )

    # Log key values
    logger.info(f"[current] SP totale_attivo={current_bs.get('totale_attivo')}, CE ricavi={current_ce.get('ce01_ricavi_vendite')}")
    logger.info(f"[prior]   SP totale_attivo={prior_bs.get('totale_attivo')}, CE ricavi={prior_ce.get('ce01_ricavi_vendite')}")

    # Step 4b: Drop a fabricated prior year on MONOCOLUMN PDFs. When the source has a
    # single value column, the LLM clones current into prior (or leaves an orphan), and
    # the downstream "prior all zeros" guard can't catch a non-zero clone. Returning
    # empty prior dicts here signals the importer to skip the prior year entirely
    # (budget_315 BERTELLI provvisorio: prior was a clone of 2025 with CE all-zero and
    # an orphan sp13).
    if _prior_column_is_absent(current_bs, current_ce, prior_bs, prior_ce):
        logger.warning(
            "Prior-year column appears ABSENT (monocolumn PDF / fabricated prior): "
            "discarding prior_bs and prior_ce."
        )
        # Empty the prior but DO NOT return early: the current column still needs the
        # Step 5-7 validators + detail reconciler (so a monocolumn provvisorio like
        # budget_315 gets its dropped "VIII Utili portati a nuovo" reserve recovered).
        # Steps below no-op on the now-empty prior dicts.
        prior_bs, prior_ce = {}, {}

    # Step 4c: ZEROED CURRENT COLUMN (draft / opening exports). Some "provvisorio" PDFs
    # render the current-year column entirely at 0,00 while the only real figures sit in
    # the prior column (budget_314: "BILANCIO AL 31/12/2025" with the 2025 column all zero
    # and every amount in 2024). The current extraction is then empty (totale_attivo ~ 0)
    # and the file would import as VUOTO. Promote the valued prior column to current and
    # drop the (now redundant) prior, so the real data is imported instead of nothing.
    # Symmetric to Step 4b and mutually exclusive with it (that path requires the current
    # column to HAVE activity), so the two can never both fire.
    _cur_attivo = current_bs.get('totale_attivo', Decimal('0'))
    _cur_ricavi = current_ce.get('ce01_ricavi_vendite', Decimal('0'))
    _pri_attivo = prior_bs.get('totale_attivo', Decimal('0'))
    if (abs(_cur_attivo) < Decimal('1') and abs(_cur_ricavi) < Decimal('1')
            and abs(_pri_attivo) >= Decimal('1')):
        logger.warning(
            f"Current-year column is ZEROED (draft/opening export) while prior is valued "
            f"(attivo {_pri_attivo}): promoting prior column to current."
        )
        current_bs, current_ce = prior_bs, prior_ce
        prior_bs, prior_ce = {}, {}

    # Step 5: control-total normalization only.  Aggregates and accounting fields
    # are not inferred from the balance difference.
    current_bs = _reconcile_utile_in_passivo(current_bs, "current")
    prior_bs = _reconcile_utile_in_passivo(prior_bs, "prior")

    # Step 6: leave ce10 and taxes as extracted.  Cross-statement disagreement is
    # reported, never corrected by replacing a source value.

    # Step 7: Deterministic detail-line fill per column (text path only). The dual layout
    # prints both years side by side ('label\\ncur\\nprior'), so column 0 = current,
    # column 1 = prior — fixing the SAME dropped-negative-reserve / merged-personale bug
    # on BOTH years so the Confronto (comparison) columns line up.
    if not use_vision:
        current_bs = _reconcile_pn_detail(current_bs, sp_text, "current", column=0)
        prior_bs = _reconcile_pn_detail(prior_bs, sp_text, "prior", column=1)
        current_ce = _reconcile_personale_detail(current_ce, ce_text, "current", column=0)
        prior_ce = _reconcile_personale_detail(prior_ce, ce_text, "prior", column=1)
    current_ce = _reconcile_global_ce_thousand_scale(current_ce, current_bs, "current")
    if prior_bs and prior_ce:
        prior_ce = _reconcile_global_ce_thousand_scale(prior_ce, prior_bs, "prior")
    current_ce = _reconcile_isolated_ce_cost_signs(
        current_ce, raw_current_ce, current_bs, "current"
    )
    if prior_bs and prior_ce:
        prior_ce = _reconcile_isolated_ce_cost_signs(
            prior_ce, raw_prior_ce, prior_bs, "prior"
        )
    current_ce = _reconcile_ce09_from_source_details(current_ce, current_bs, "current")
    if prior_bs and prior_ce:
        prior_ce = _reconcile_ce09_from_source_details(prior_ce, prior_bs, "prior")

    # Un estrattore dichiara SEMPRE le proprie chiavi diagnostiche, anche a zero:
    # a valle una chiave assente vale zero, quindi tacere equivale a dichiararsi
    # pulito. Le rotte A/B non scrivevano `_unclassified_mass` affatto.
    try:
        from importers.iv_cee_hierarchy import declare_unclassified_mass
        current_bs.update(
            declare_unclassified_mass(
                current_bs, _declared_control_totals(file_path), "ivcee-current"
            )
        )
    except Exception as _declare_err:  # pragma: no cover - diagnostica, mai bloccante
        # Anche fallendo si dichiara. Una chiave ASSENTE a valle vale zero, cioe'
        # «pulito»: tacere qui rimetterebbe in piedi proprio il difetto che questa
        # dichiarazione esiste per togliere. Zero con `_measured` a zero significa
        # invece «non lo so», che e' la verita' quando la misura non e' riuscita.
        current_bs.setdefault('_unclassified_mass', Decimal('0'))
        current_bs.setdefault('_unclassified_mass_measured', Decimal('0'))
        logger.warning(
            f"Massa non classificata non dichiarata: {_declare_err}"
        )


    return current_bs, current_ce, prior_bs, prior_ce
