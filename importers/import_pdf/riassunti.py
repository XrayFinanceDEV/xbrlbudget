"""Riconoscere un riepilogo di poche macro-voci (export xlsx) che non e' un bilancio.

Spostato da importers/pdf_importer.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import re
from decimal import Decimal
from typing import Optional


def _is_aggregated_summary(text: str) -> bool:
    """True when the document carries NO legal IV-CEE substructure — only top-level
    macro-voci (e.g. "Immobilizzazioni: 2.406.946", "B) Patrimonio netto: ..."), with
    no roman-numeral sub-items, no "esigibili entro/oltre l'esercizio", and no account
    codes. These are over-aggregated riepiloghi (often AI-generated, e.g. the LUGS /
    FINALE_CEE test fixtures) that are NOT an importable art. 2424/2425 schema — so the
    import should say "formato non supportato" rather than the cryptic "does not balance".

    Used ONLY at the validate_balance failure point (a file that already balances never
    reaches it), so this can never reclassify a correctly-imported bilancio. Gestionali
    with a real (even abbreviated) schema always carry roman numerals / "esigibili" /
    account codes, so they keep the "BILANCIO NON QUADRATO" honest-fail path.
    """
    if not text:
        return False
    # Roman-numeral legal items II..X, optionally prefixed by the section letter (A.II, B) II).
    romans = re.findall(
        r'(?im)^\s*(?:[A-D][.\)]\s*)?(?:II|III|IV|VIII|VII|VI|IX|V|X)\b', text)
    has_esigibili = bool(re.search(r'esigibili\s+(?:entro|oltre)', text, re.I))
    has_codes = bool(re.search(r'(?m)^\s*\d{4,}\b', text))
    # Codici puntati alfanumerici seguiti dalla descrizione («10.05.3K - CONCESSIONI», «20.30.CL -
    # DEBITI VS.ALTRI FINANZIATORI»): sono conti di un gestionale, non macro-voci. Senza, una
    # situazione contabile vera finiva fra i riepiloghi e veniva rifiutata (budget_1776/1786).
    if not has_codes:
        has_codes = len(re.findall(
            r'(?m)^\s*\d{2,3}\.\d{2,3}(?:\.[0-9A-Z]{1,12})?\s+-\s+\S', text)) >= 5
    return len(romans) < 3 and not has_esigibili and not has_codes

# Italian-formatted amount: 1.234.567,89 / -58.481,84 / 258,31
_IT_AMOUNT_RE = re.compile(r'-?\d{1,3}(?:\.\d{3})*,\d{2}\b')

def _euro_it(value: Decimal) -> str:
    return f"{value:,.2f}".replace(',', '#').replace('.', ',').replace('#', '.')

def _label_amount_pairs(text: str) -> list:
    """(label, amount) for every printed amount, tolerating the two layouts these
    summaries use: "Immobilizzazioni: 2.406.946,04" and a label whose amount sits on
    the following line (PyMuPDF splits two-column tables that way)."""
    pairs = []
    pending_label = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _IT_AMOUNT_RE.search(line)
        if not match:
            pending_label = line
            continue
        label = line[:match.start()].strip(' :.\t-–') or (pending_label or '')
        pairs.append((label, Decimal(
            match.group().replace('.', '').replace(',', '.'))))
        pending_label = None
    return pairs

def _section(text: str, start_pattern: str, end_pattern: str) -> Optional[str]:
    start = re.search(start_pattern, text, re.I | re.M)
    if not start:
        return None
    rest = text[start.end():]
    end = re.search(end_pattern, rest, re.I | re.M)
    return rest[:end.start()] if end else rest

def _summary_internal_contradiction(text: str) -> Optional[str]:
    """Diagnosis for an over-aggregated summary that contradicts its OWN printed
    figures — the components it lists do not rebuild the totals it prints.

    budget_137 is the motivating case: it carries the budget_133/135 macro figures with
    Debiti inflated (2.688.470,08 -> 3.995.536,14) so the two sides tie, which lets it
    slip past the "Totale Attivo != Totale Passivo" source check. The tie is cosmetic:
    the Attivo components sum 89.354,38 above the printed total, and the CE components
    land 61.350,89 away from the printed result. Saying "riepilogo aggregato" there
    hides a document that is arithmetically self-contradictory.

    Reads only amounts the document prints, and reports the gaps. It never infers a
    corrected figure and never touches an accounting value. Returns None when the
    printed figures are consistent or too sparse to judge — silence is the safe answer,
    the caller still rejects the file for its own reasons.
    """
    if not text:
        return None
    faults = []

    # --- CE: does "Differenza A-B" + "Gestione finanziaria" reach the printed result?
    ce_text = _section(text, r'^.*CONTO\s+ECONOMICO.*$', r'^\s*NOT[AE]\b')
    if ce_text and not re.search(r'\b(IRES|IRAP|imposte)\b', ce_text, re.I):
        # Imposte would sit between the two, so only judge a CE that prints none.
        ce_pairs = _label_amount_pairs(ce_text)

        def _find(pattern):
            for label, amount in ce_pairs:
                if re.search(pattern, label, re.I):
                    return amount
            return None

        differenza = _find(r'^differenza\b')
        finanziaria = _find(r'gestione\s+finanziaria')
        risultato = _find(r"^(risultato\s+netto|utile\s+netto|"
                          r"perdita\s+(?:d')?esercizio)")
        if differenza is not None and finanziaria is not None and risultato is not None:
            gap = abs(differenza + finanziaria - risultato)
            if gap > Decimal('2'):
                faults.append(
                    "le componenti del Conto Economico non ricostruiscono il "
                    f"risultato netto dichiarato (scarto €{_euro_it(gap)})"
                )

    # --- Attivo: do the listed components add up to the printed total?
    attivo_text = _section(
        text,
        r'^.*STATO\s+PATRIMONIALE\s*[-–]?\s*ATTIVO.*$',
        r'^.*(?:STATO\s+PATRIMONIALE\s*[-–]?\s*)?PASSIVO.*$',
    )
    if attivo_text:
        declared = None
        components = Decimal('0')
        for label, amount in _label_amount_pairs(attivo_text):
            if re.match(r'^totale\s+attivo\b', label, re.I):
                declared = amount
            elif not re.match(r'^totale\b', label, re.I):
                # Subtotals ("Totale immobilizzazioni") would double-count the leaves.
                components += amount
        if declared is not None and declared != 0:
            gap = abs(components - declared)
            if gap > Decimal('2'):
                faults.append(
                    "le componenti dell'Attivo non coincidono con il totale "
                    f"stampato (scarto €{_euro_it(gap)})"
                )

    if not faults:
        return None
    return (
        "Il documento sorgente è internamente incoerente: "
        + " e ".join(faults)
        + ". Correggere il documento contabile originale."
    )
