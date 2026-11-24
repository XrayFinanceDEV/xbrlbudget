"""I totali di controllo stampati dal documento e la riconciliazione del bilancio di verifica con essi.

Spostato da importers/pdf_extractor_llm.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import re
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from importers.estrazione_llm.modelli import (
    _parse_it_number,
)
from importers.estrazione_llm.colonne import (
    _GEOMETRIC_NUMBER_RE,
)
from importers.estrazione_llm.pagine import (
    _extract_full_text,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_extractor_llm")


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

# Italian-number control token: decimal cents or whole euros with at least one
# thousands separator.  Legal IV-CEE statements commonly print rounded totals as
# ``6.474.612`` (budget_328); accepting only comma-decimal amounts made both source
# side controls disappear.  Plain unseparated integers stay excluded so years and
# item numbers in the 80-character label window cannot become accounting totals.
_DECL_NUM_RE = re.compile(
    r"-?(?:\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+,\d{2})"
)

def _valore_in_colonna(numeri: list, colonna: Optional[Dict[str, int]]) -> Optional[Decimal]:
    """Sceglie, fra i numeri trovati dopo un marcatore, quello della colonna che ``colonna``
    indica (stessa regola di risoluzione di ``import_snello.righe.saldo()``: ``{"n": totale
    colonne, "k": indice della colonna saldo}``). Se il conteggio dei numeri trovati non
    coincide con ``n`` e ``k`` non e' il primo o l'ultimo, la colonna non si identifica con
    certezza su QUESTA occorrenza: nessun valore, mai un ripiego sul primo trovato (Task 21,
    ruling: "se la colonna non si identifica con certezza il totale stampato non entra")."""
    if not colonna or not numeri:
        return None
    n, k = colonna.get("n"), colonna.get("k")
    if n is None or k is None:
        return None
    if len(numeri) == n:
        return numeri[k]
    if k == n - 1:
        return numeri[-1]
    if k == 0:
        return numeri[0]
    return None

def _declared_control_totals(file_path: str, text: Optional[str] = None,
                             colonna: Optional[Dict[str, int]] = None) -> Dict[str, Optional[Decimal]]:
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

    ``colonna`` (Task 21, import_snello "conti" only): when a control-total line prints
    SEVERAL amounts per side (e.g. "Saldo non rettificato | Rettifiche | Saldo finale"),
    the default behaviour below (unchanged, every existing caller) keeps taking the FIRST
    number after the marker. Passing ``colonna`` (``{"n": ..., "k": ...}``, same shape as
    ``import_snello.righe.regola_colonna()``) instead picks the column the caller has
    identified as the balance; an occurrence whose column cannot be resolved with
    certainty contributes nothing (never a fallback to the first number).

    """
    out: Dict[str, Optional[Decimal]] = {
        "attivo": None, "passivo": None, "pareggio": None, "utile": None, "perdita": None,
        "costi": None, "ricavi": None,
    }
    # `text` lets the caller supply already-extracted text (e.g. OCR of a scanned PDF,
    # where _extract_full_text would return nothing, or a position-ordered reading - Task 22
    # G3, fix round 2: il chiamante snello (``import_snello.verifica.totali_stampati``) prova
    # QUESTA funzione due volte, una col testo di sempre, una con
    # ``_extract_full_text(..., forza_ordinamento=True)``, e sceglie la prima lettura coerente
    # (attivo=passivo entro soglia) - mai una fusione delle due fonti qui dentro). Fall back to
    # reading the file.
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

    def _largest_after(markers, hays=None, colonna=None, sottototali=()) -> Optional[Decimal]:
        """Largest Italian-number amount occurring within ~80 chars after any marker.
        `hays` = [(text, is_nospaces), ...]; defaults to the full normal + no-spaces
        text. The no-spaces flag decides which form of the marker to search.

        Without ``colonna`` (every existing caller): exactly the old behaviour, only the
        FIRST parseable number after the marker enters the largest-across-occurrences
        comparison. With ``colonna``: every number in the window is collected first, and
        ``_valore_in_colonna`` picks the one the caller's column rule identifies - an
        occurrence whose count of numbers doesn't resolve contributes nothing.

        ``sottototali``: continuations that turn the marker into the caption of a SUB-total
        («totale attivo» dentro «Totale attivo circolante (C)»): that occurrence is not the
        total and contributes nothing. Sul layout con gli importi PRIMA dell'etichetta
        (budget_1753) il primo numero dopo «Totale attivo circolante» era la percentuale di
        scostamento della riga seguente, e quei centesimi passavano per il totale attivo."""
        best: Optional[Decimal] = None
        for hay, is_nos in (hays or ((low, False), (nos, True))):
            seguiti = tuple(s.replace(" ", "") for s in sottototali) if is_nos else sottototali
            for mk in markers:
                pat = re.escape(mk.replace(" ", "")) if is_nos else re.escape(mk)
                for hit in re.finditer(pat, hay):
                    if seguiti and hay[hit.end(): hit.end() + 40].lstrip(" \t").startswith(seguiti):
                        continue
                    window = hay[hit.end(): hit.end() + 80]
                    if colonna is not None:
                        # Le colonne di UN rigo di controllo stanno tutte sulla sua stessa
                        # riga stampata: senza questo taglio, un'etichetta corta lascia la
                        # finestra di 80 caratteri sconfinare nella riga stampata SUCCESSIVA
                        # (un altro totale, altri importi), e la colonna scelta finirebbe
                        # per leggere un numero che non e' nemmeno di questo rigo. Il
                        # comportamento di sempre (colonna=None, un numero solo) non aveva
                        # questo rischio - ne' questo taglio, per non toccarlo.
                        window = window.split("\n", 1)[0]
                    numeri = []
                    for nm in _DECL_NUM_RE.finditer(window):
                        try:
                            numeri.append(Decimal(nm.group(0).replace(".", "").replace(",", ".")))
                        except Exception:
                            continue
                        if colonna is None:
                            break  # comportamento di sempre: solo il primo numero dopo il marcatore
                    v = _valore_in_colonna(numeri, colonna) if colonna else (numeri[0] if numeri else None)
                    if v is None:
                        continue
                    av = abs(v)
                    if av > 0 and (best is None or av > best):
                        best = av
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
    out["pareggio"] = (_largest_after(_pareggio_markers, hays=_sp_hays, colonna=colonna)
                       or _largest_after(_pareggio_markers, colonna=colonna))
    # I nomi dei sotto-totali che cominciano come il totale di lato: schema di legge
    # («Totale attivo circolante») e prospetti riclassificati («attivo corrente/immobilizzato»,
    # «passivo consolidato», «passività a breve»). Un'occorrenza seguita da uno di questi non
    # e' il totale dello stato patrimoniale.
    _sottototali_di_lato = (
        "circolante", "corrent", "non corrent", "immobilizzat", "fiss", "finanziari",
        "consolidat", "a breve", "a medio", "a lungo", "di breve", "di medio", "di lungo",
    )
    out["attivo"] = _largest_after([
        "totale attivo", "totale attivita", "totale dell'attivo",
        "totale stato patrimoniale attivo", "totale stato patrimoniale - attivo",
    ], colonna=colonna, sottototali=_sottototali_di_lato)
    out["passivo"] = _largest_after([
        "totale passivo", "totale passivita", "totale a pareggio passivo",
        "totale passivo e patrimonio netto", "totale passivita e netto",
        "totale stato patrimoniale passivo", "totale stato patrimoniale - passivo",
    ], colonna=colonna, sottototali=_sottototali_di_lato)

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
        # la stessa intestazione con i suoi importi sulla STESSA riga, come la ricompone il testo
        # per posizione senza le colonne di differenza (BILAQ: "2 Stato patrimoniale attivo
        # 1.250.311,33 1.314.938,83"): solo intestazione (col codice di riga davanti) e importi
        stessa_riga = re.compile(
            rf"(?im)^\s*(?:\d+\s+)?stato\s+patrimoniale\s+(?:-\s*)?{side}[ \t]+"
            rf"({_DECL_NUM_RE.pattern})(?:[ \t]+{_DECL_NUM_RE.pattern})*[ \t]*$"
        )
        values = []
        for match in [*pattern.finditer(low), *stessa_riga.finditer(low)]:
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
    ], colonna=colonna)
    out["perdita"] = _largest_after([
        "perdita d'esercizio", "perdita dell'esercizio", "perdita di esercizio",
        "perdita del periodo", "perdita in corso di formazione",
    ], colonna=colonna)

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
