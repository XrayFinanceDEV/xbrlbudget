"""extract_contrapposte_best_effort: l'estrazione generica a sezioni contrapposte.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import re
from decimal import Decimal
from typing import Dict, List, Tuple
from importers.situazione_contabile.regole import (
    _ATTIVO_KEYS, _CE_SUBFIELD_PARENT, _DEBT_FIELD, _PASSIVO_KEYS, _classify_ce_costi, _classify_ce_ricavi,
    _kw_any, _natura_unanime,
)
from importers.situazione_contabile.best_effort import (
    ReconstructedRow, _be_amount, _be_collect_side_facts, _be_collect_side_legacy,
    _be_page_needs_coordinate_repair, _be_reclassify, _be_repair_parent_codes, _be_split, _be_split_codeless,
)
from importers.situazione_contabile.mastri_gerarchici import (
    _hier_prior_caption_senza_importo, _hier_prior_result, _is_prior_result_caption,
)
from importers.situazione_contabile.ricostruzione import (
    _hier_reconstruct,
)
from importers.situazione_contabile.classificatori import (
    _be_split_sp_ce_page, _descrizione_di_conto, classify_attivo, classify_costi, classify_page_section,
    classify_passivo, classify_ricavi,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.situazione_contabile_parser")


def extract_contrapposte_best_effort(file_path: str) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Best-effort extraction of a 2-column contrapposte trial balance.

    Declared totals are controls only.  Any residual from imperfect parsing is
    exposed as diagnostic metadata and the classified sides are left unchanged:
    a missing source row must never become cash or debt just to make the import
    balance.
    """
    doc = fitz.open(file_path)
    full = ""
    # Capture per-page (words, is_sp, is_ce, up, width) so the column collection can
    # be re-run in a code-less second pass without re-opening the PDF.
    pages_data: List[tuple] = []

    previous = None
    closed = False       # la sezione della pagina prima ha gia' stampato i suoi totali
    totals_seen = 0
    for page in doc:
        ptext = page.get_text()
        full += ptext + "\n"
        up = ptext.upper()
        verdict = classify_page_section(ptext)
        if verdict is None:
            continue
        # Pagina di continuazione senza intestazione di sezione (M.C.T. 30/06/2026: la
        # pagina 2 riprende l'attivo e il passivo della 1 con il solo titolo del
        # documento): e' della sezione della pagina prima, se quella era una sola e non
        # aveva ancora chiuso coi totali di entrambi i lati o col pareggio. Dopo la
        # chiusura una pagina senza sezione e' un allegato ("Dettaglio ratei, risconti e
        # competenze", budget_210), e resta fuori.
        if verdict == (False, False) and previous in ((True, False), (False, True)) \
                and not closed:
            verdict = previous
        if verdict != previous:
            closed, totals_seen = False, 0
        previous = verdict
        flat_up = re.sub(r'\s+', '', up)
        totals_seen += len(re.findall(r'(?m)^\s*TOTALI\b', up))
        closed = closed or ('PAREGGIO' in flat_up or 'QUADRATURA' in flat_up
                            or ('TOTALEATTIV' in flat_up and 'TOTALEPASSIV' in flat_up)
                            or ('TOTALECOST' in flat_up and 'TOTALERICAV' in flat_up)
                            or totals_seen >= 2)
        is_sp, is_ce = verdict
        words = page.get_text('words')
        if not words:
            continue
        if verdict == (True, False):
            parti = _be_split_sp_ce_page(words)
            if parti is not None:
                sp_w, ce_w = parti
                _txt = lambda ws: ' '.join(w[4] for w in sorted(
                    ws, key=lambda w: (round((w[1] + w[3]) / 2), w[0]))).upper()
                pages_data.append((sp_w, True, False, _txt(sp_w), page.rect.width))
                pages_data.append((ce_w, False, True, _txt(ce_w), page.rect.width))
                # la pagina dopo, se senza intestazione, continua il conto economico
                previous, closed, totals_seen = (False, True), False, 0
                continue
        pages_data.append((words, is_sp, is_ce, up, page.rect.width))

    doc.close()
    use_garbled_reconstruction = any(
        _be_page_needs_coordinate_repair(words)
        for words, _is_sp, _is_ce, _up, _width in pages_data)

    def _collect_all(codeless: bool):
        """Collect attivo/passivo/costi/ricavi rows across all pages. In code-less
        mode each rowless-code row gets a globally-unique, fixed-width synthetic code
        (~NNNNNN) so it is its own non-prefixing root in _be_reclassify."""
        att_facts: List[ReconstructedRow] = []
        pas_facts: List[ReconstructedRow] = []
        cos_facts: List[ReconstructedRow] = []
        ric_facts: List[ReconstructedRow] = []
        ctr = [0]

        def _uniq(side_rows):
            res = []
            for c, d, a in side_rows:
                if c == '':
                    c = f"~{ctr[0]:06d}"
                    ctr[0] += 1
                res.append((c, d, a))
            return res

        def _ce_side_scores(rows):
            return (
                sum(1 for _c, desc, _a in rows if _classify_ce_costi(desc)),
                sum(1 for _c, desc, _a in rows if _classify_ce_ricavi(desc)),
            )

        def _ce_columns_are_swapped(left_rows, right_rows):
            """Choose COSTI/RICAVI from accounting captions, not header text order.

            PyMuPDF's linear text order does not necessarily match physical column
            order (budget_405 prints the words ``RICAVI COSTI`` but costs are on the
            left).  Scoring the already separated row descriptions is stable also on
            continuation pages where one physical column is empty.
            """
            left_cost, left_revenue = _ce_side_scores(left_rows)
            right_cost, right_revenue = _ce_side_scores(right_rows)
            direct = left_cost + right_revenue
            swapped = right_cost + left_revenue
            return swapped > direct

        if not use_garbled_reconstruction:
            att: List[Tuple[str, str, Decimal]] = []
            pas: List[Tuple[str, str, Decimal]] = []
            cos: List[Tuple[str, str, Decimal]] = []
            ric: List[Tuple[str, str, Decimal]] = []
            for page_number, (words, is_sp, is_ce, up, width) in enumerate(pages_data, 1):
                split = _be_split(words)
                if split is None and codeless:
                    split = _be_split_codeless(words)
                if split is None:
                    split = width / 2

                def _best_side(lo, hi):
                    legacy = _be_collect_side_legacy(
                        words, lo, hi, codeless=codeless)
                    coordinate = [
                        fact.legacy() for fact in _be_repair_parent_codes(
                            _be_collect_side_facts(
                                words, lo, hi, codeless=codeless,
                                page=page_number)
                        )
                    ]
                    # Coordinate clustering is a recovery path for baseline jitter;
                    # retain the proven legacy rows unless it recovers more physical
                    # facts from the same side.
                    return coordinate if len(coordinate) > len(legacy) else legacy

                left = _uniq(_best_side(-1e9, split))
                right = _uniq(_best_side(split, 1e9))
                if is_sp and not is_ce:
                    att += left
                    pas += right
                elif is_ce and not is_sp:
                    if _ce_columns_are_swapped(left, right):
                        cos += right
                        ric += left
                    else:
                        cos += left
                        ric += right
            return att, pas, cos, ric

        for page_number, (words, is_sp, is_ce, up, width) in enumerate(pages_data, 1):
            split = _be_split(words)
            if split is None and codeless:
                split = _be_split_codeless(words)
            if split is None:
                split = width / 2
            left = _be_collect_side_facts(
                words, -1e9, split, codeless=codeless, page=page_number)
            right = _be_collect_side_facts(
                words, split, 1e9, codeless=codeless, page=page_number)
            if is_sp and not is_ce:
                att_facts += left
                pas_facts += right
            elif is_ce and not is_sp:
                if _ce_columns_are_swapped(
                        [f.legacy() for f in left], [f.legacy() for f in right]):
                    cos_facts += right
                    ric_facts += left
                else:
                    cos_facts += left
                    ric_facts += right

        # Re-run hierarchy repair after concatenating pages: one account family
        # may start at the foot of page N and print its subtotal on page N+1.
        def _project(facts):
            return _uniq([f.legacy() for f in _be_repair_parent_codes(facts)])

        return (_project(att_facts), _project(pas_facts),
                _project(cos_facts), _project(ric_facts))

    attivo, passivo, costi, ricavi = _collect_all(codeless=False)
    # Code-less second pass: a clean two-column trial balance whose rows carry NO
    # account code (description+amount only, e.g. budget_367) collects zero rows in
    # the code-required pass. Retry code-less ONLY when the normal pass found nothing,
    # so coded files (the entire passing corpus) are never affected.
    if not attivo and not passivo:
        attivo, passivo, costi, ricavi = _collect_all(codeless=True)

    # Control rows are collected separately and never enter account
    # reclassification.  Their side / page coordinates make them safer than a
    # substring search over a corrupted linear text layer.
    controls: List[Tuple[str, str, ReconstructedRow]] = []
    for page_number, (words, is_sp, is_ce, _up, width) in enumerate(pages_data, 1):
        split = _be_split(words) or width / 2
        section = 'sp' if is_sp and not is_ce else ('ce' if is_ce and not is_sp else '')
        if not section:
            continue
        for side, lo, hi in (('left', -1e9, split), ('right', split, 1e9)):
            for fact in _be_collect_side_facts(
                    words, lo, hi, codeless=True, page=page_number,
                    include_controls=True):
                if fact.control:
                    controls.append((section, side, fact))

    # A contrapposte trial balance must have a balance-sheet side. Documents that
    # are economic-only (e.g. "PROSPETTO ECONOMICO per competenza" with just a
    # COSTI/RICAVI + fiscal-reconciliation table and no Stato Patrimoniale, budget_196)
    # collect zero attivo/passivo rows: refuse to fabricate a balance sheet by plugging
    # the pareggio into sp09/sp16 — raise so the caller can fall back to LLM extraction.
    if not attivo and not passivo:
        raise ValueError(
            "contrapposte best-effort: nessuno Stato Patrimoniale rilevato "
            "(documento solo economico?) — impossibile estrarre un bilancio deterministico"
        )

    Z = Decimal('0')
    bs: Dict[str, Decimal] = {}
    ce: Dict[str, Decimal] = {}

    def add(d, k, v):
        d[k] = d.get(k, Z) + v

    cl_pas = classify_passivo
    cl_cos, cl_ric = classify_costi, classify_ricavi

    # The current-year result is a pareggio item (utile booked on the passivo
    # side, perdita on the attivo side). Strip it from both columns so it is not
    # double-counted as a credit/asset; its signed value becomes sp13.
    result = [Z]
    # Ogni conto di risultato tolto, col segno: se poi non coincide col risultato del
    # periodo e' l'utile (o la perdita) dell'anno prima non ancora destinato.
    booked_results: List[Decimal] = []

    def _strip_result(side):
        keep = []
        for c, d, a in side:
            # "Utile/Perdita in corso di formazione" e' il risultato del periodo nelle
            # situazioni infrannuali (budget_367): stesso conto dell'utile d'esercizio.
            if (('ESERCIZ' in d or 'CORSO DI FORMAZIONE' in d)
                    and ('UTILE' in d or 'PERDITA' in d or 'RISULTAT' in d)
                    and not _kw_any(d, ['PORTAT', 'PORTATE', 'NUOVO', 'PRECEDENT'])):
                result[0] += (-a if 'PERDITA' in d else a)
                booked_results.append(-a if 'PERDITA' in d else a)
                continue
            keep.append((c, d, a))
        return keep

    attivo = _strip_result(attivo)
    passivo = _strip_result(passivo)

    # Cespite e fondo stampati in coppia, il fondo dall'altra parte con la stessa
    # descrizione ("CONTENITORI" / "F.DO AMM.TO CONTENITORI", budget_435): la riga
    # d'attivo e' l'immobilizzazione del fondo, anche quando la descrizione da sola non
    # dice cespite (contenitori, disaggi, manutenzioni da ammortizzare finivano nei
    # crediti, e il fondo nettava un'immobilizzazione che non c'era).
    fondi_di: Dict[str, str] = {}
    for _c, d, _a in passivo:
        tag, _spec = cl_pas(d)
        if tag in ('depr_sp02', 'depr_sp03'):
            resto = re.sub(r'^(?:F\.?\s?DO|FONDO)\s+AMM\S*\s+(?:(?:DI|DEL|DELLE|DEGLI|SU)\s+)?',
                           '', _descrizione_di_conto(d)).strip()
            if resto and resto != _descrizione_di_conto(d):
                fondi_di[resto] = tag.replace('depr_', '')

    def cl_att(d, _cl=classify_attivo):
        field, specific = _cl(d)
        if field in ('sp02', 'sp03', 'sp04') or not fondi_di:
            return field, specific
        nd = _descrizione_di_conto(d)
        for resto, campo in fondi_di.items():
            if nd == resto or nd.startswith(resto + ' '):
                return campo, True
        return field, specific

    # --- Attivo (gross assets; fondi netted from passivo side) ---
    for field, amt in _be_reclassify(attivo, cl_att):
        add(bs, field, amt)

    # --- Passivo (equity / debts / contra-asset funds) ---
    # Track the contra-asset mass netted off the asset side. When fondi ammortamento /
    # svalutazione crediti are listed as separate PASSIVO accounts (GROSS presentation),
    # the declared TOTALE ATTIVO / pareggio is GROSS. Netting them off the assets while
    # anchoring the plug to that gross total opens a hole == the fondi magnitude, swept
    # into sp09/sp16 — the dominant cause of "QUADRATURA MASCHERATA" on gross-presentation
    # trial balances (budget_395/405/343/348/342). We accumulate the netted mass and
    # reduce iv_total by it below so the IV-CEE NET total matches the netted sums (plug ~ 0).
    # No-op when fondi sit on the asset side (e.g. AITEC) → netted_contra stays 0.
    netted_contra = Z
    for tag, amt in _be_reclassify(passivo, cl_pas):
        if tag in ('depr_sp02', 'depr_sp03', 'depr_sp04'):
            add(bs, tag.replace('depr_', ''), -amt)        # net fondi off the asset
            netted_contra += amt
        elif tag == 'deduct_crediti':
            add(bs, 'sp06', -amt)
            netted_contra += amt
        elif tag in ('sp11', 'sp12', 'sp14', 'sp15', 'sp18'):
            add(bs, tag, amt)
        elif len(tag) == 5 and tag.startswith('sp16') and tag[4] in 'abcdefg':
            # Typed debt: keep the aggregate sp16 (pareggio unchanged) AND emit the typed
            # sub-field under its full DB name so it survives _map_sc_keys and shows up split.
            add(bs, 'sp16', amt)
            add(bs, _DEBT_FIELD['breve'][tag[4]], amt)
        else:                                              # any unexpected tag → aggregate
            add(bs, 'sp16', amt)

    # --- CE ---
    # Personale (ce08a-d) and ammortamenti (ce09a-d) are detail ("di cui") lines:
    # the EBIT/profit formula reads only the aggregates ce08/ce09, so each sub-field
    # is rolled into its parent aggregate AND stored under its full DB key (mirrors
    # build_iv_cee). _be_reclassify emits a node at exactly one level (parent OR
    # children, never both), so this never double-counts. _CE_SUBFIELD_PARENT is a
    # module-level constant (defined next to _CE_HIER_SUBPARENT) so build_ce_from_vision
    # reads the same single definition.
    def ce_add(tag, amt):
        if tag == 'ce01_return':
            add(ce, 'ce01', -amt)
        elif tag == 'ce10_close':
            add(ce, 'ce10', -amt)
        elif tag == 'ce02_open':
            add(ce, 'ce02', -amt)
        elif tag == 'ce13_cost':
            add(ce, 'ce15', amt)
        elif tag in _CE_SUBFIELD_PARENT:
            detail, parent = _CE_SUBFIELD_PARENT[tag]
            add(ce, parent, amt)      # aggregate read by the EBIT/profit formula
            add(ce, detail, amt)      # "di cui" detail (full DB key, survives _map_sc_keys)
        elif tag == '_ce_da_dettagliare':
            ce.setdefault(tag, []).append(amt)      # un albero, non un importo
        else:
            add(ce, tag, amt)
    for tag, amt in _be_reclassify(costi, cl_cos,
                                   _natura_unanime(d for _c, d, _a in ricavi)):
        ce_add(tag, amt)
    for tag, amt in _be_reclassify(ricavi, cl_ric,
                                   _natura_unanime(d for _c, d, _a in costi)):
        ce_add(tag, amt)

    # --- Declared totals & current-year result ---
    # Some gestionali letter-space the column headers ("TOTALE  A T T I V I T�"),
    # which defeats a contiguous-substring search; fall back to a whitespace-stripped
    # copy so the needle still matches.
    up1 = re.sub(r'\s+', ' ', full.upper())
    flat1 = re.sub(r'\s+', '', full.upper())

    def _find_total(spaced, flat):
        if spaced in up1:
            return _be_amount(up1.split(spaced, 1)[1][:40])
        if flat in flat1:
            return _be_amount(flat1.split(flat, 1)[1][:40])
        return None

    def _control_exact(section, side, caption):
        matches = [fact.amount for sec, sd, fact in controls
                   if sec == section and sd == side
                   and re.sub(r'[^A-Z]', '', fact.description) == caption]
        return matches[-1] if len(matches) == 1 else None

    def _control_amount(section, side, *needles):
        matches = [fact.amount for sec, sd, fact in controls
                   if sec == section and (side is None or sd == side)
                   and all(needle in fact.description for needle in needles)]
        return max(matches) if matches else None

    # Coordinate facts first; legacy linear-text lookup remains as a fallback for
    # layouts whose footer is not physically aligned with either data column.
    # Un totale stampato con l'importo PRIMA della didascalia ("1.406.600,60 Totale
    # Attivita': *** 1.352.014,11 Totale Passivita':", STB 30/06/2026) inganna il testo
    # lineare, che dopo "TOTALE ATTIV" trova l'importo della passivita': differenza zero,
    # utile zero. Quando entrambi i totali sono letti per coordinate, ciascuno sulla
    # propria riga e dal proprio lato, valgono quelli.
    ctl_att = _control_amount('sp', 'left', 'TOTALE', 'ATTIV')
    ctl_pas = _control_amount('sp', 'right', 'TOTALE', 'PASSIV')
    by_coordinates = use_garbled_reconstruction or (
        ctl_att is not None and ctl_pas is not None)
    tot_att = ((ctl_att if by_coordinates else None)
               or _find_total('TOTALE ATTIV', 'TOTALEATTIV'))
    tot_pas = ((ctl_pas if by_coordinates else None)
               or _find_total('TOTALE PASSIV', 'TOTALEPASSIV'))
    # "Totali" senza dire di che lato (M.C.T. 30/06/2026): lo dice la colonna.
    if tot_att is None and tot_pas is None:
        tot_att = _control_amount('sp', 'left', 'TOTALI')
        tot_pas = _control_amount('sp', 'right', 'TOTALI')
    # "TOTALE" e basta, uno per colonna (Napolitano 30/09/2026, ATTIVITA'/PASSIVITA' solo
    # nell'intestazione): anche qui lo dice la colonna, ma solo la riga che e' esattamente
    # "TOTALE" - mai un "Totale clienti" o un altro subtotale.
    if tot_att is None and tot_pas is None:
        tot_att = _control_exact('sp', 'left', 'TOTALE')
        tot_pas = _control_exact('sp', 'right', 'TOTALE')
    # Il pareggio dello stato patrimoniale, mai quello del conto economico: con le
    # pagine di CE in fondo "TOTALE A PAREGGIO" trovava il pareggio dei componenti di
    # reddito (1.809.957,59 invece dei 1.119.893,69 dei totali dello SP, budget_435).
    sp_up = re.sub(r'\s+', ' ', ' '.join(
        up for _w, is_sp, is_ce, up, _width in pages_data if is_sp and not is_ce))
    pareggio = ((_control_amount('sp', None, 'TOTALE', 'PAREGGIO')
                 if use_garbled_reconstruction else None)
                or (_be_amount(sp_up.split('TOTALE A PAREGGIO', 1)[1][:40])
                    if 'TOTALE A PAREGGIO' in sp_up else None)
                or (_find_total('TOTALE A PAREGGIO', 'TOTALEAPAREGGIO')
                    if not sp_up else None))

    # Risultato degli esercizi precedenti non ancora destinato, stampato SENZA codice
    # SOTTO "Totale passivita'" ("Eccedenza esercizio precedente", "Utile esercizio
    # precedente": Unicarton 31/08/2026). E' patrimonio netto, e sta fuori dai totali
    # stampati: la differenza Totale attivita' - Totale passivita' lo contiene, e senza
    # toglierlo diventerebbe utile del periodo (sp13 241.711,59 invece di 68.247,80).
    # Solo sotto il totale: una riga sopra e' gia' dentro il totale passivita'.
    prior_footer = Z
    prior_caption_senza_importo = False
    for page_number, (words, is_sp, is_ce, _up, width) in enumerate(pages_data, 1):
        if not (is_sp and not is_ce):
            continue
        tot_y = [fact.y for sec, _sd, fact in controls
                 if sec == 'sp' and fact.page == page_number
                 and 'TOTALE' in fact.description and 'PASSIV' in fact.description]
        if not tot_y:
            continue
        below = [w for w in words if w[1] > max(tot_y)]
        split = _be_split(words) or width / 2
        prior_footer += _hier_prior_result(below, split, 1e9)
        prior_footer -= _hier_prior_result(below, -1e9, split)
        prior_caption_senza_importo |= _hier_prior_caption_senza_importo(below)
    if prior_footer:
        add(bs, 'sp12', prior_footer)
        add(bs, 'sp12g_utili_perdite_portati', prior_footer)
        bs['_prior_result_footer'] = prior_footer
        logger.info(f"contrapposte: risultato esercizi precedenti {prior_footer} "
                    "sotto i totali -> sp12g, tolto dalla differenza dei totali")

    explicit_results = []
    for sec, _side, fact in controls:
        if sec != 'sp' or 'ESERCIZ' not in fact.description:
            continue
        if _is_prior_result_caption(fact.description):
            continue
        if 'UTILE' in fact.description:
            explicit_results.append(fact.amount)
        elif 'PERDIT' in fact.description:
            explicit_results.append(-fact.amount)
    explicit_result = explicit_results[-1] if explicit_results else None
    total_gap = (tot_att - tot_pas - prior_footer
                 if tot_att is not None and tot_pas is not None else None)
    ce_cost_total = (_control_amount('ce', 'left', 'TOTALE', 'COST')
                     or _control_exact('ce', 'left', 'TOTALE'))
    ce_revenue_total = (_control_amount('ce', 'right', 'TOTALE', 'RICAV')
                        or _control_exact('ce', 'right', 'TOTALE'))
    ce_control_result = (ce_revenue_total - ce_cost_total
                         if ce_cost_total is not None and ce_revenue_total is not None
                         else None)

    # Il risultato precedente con la didascalia stampata ma l'importo perso (budget_1410,
    # MinerU: «Eccedenza esercizio precedente» senza cella). Decisione del proprietario,
    # 2026-10-28: l'utile del periodo e' quello del CE verificato dai suoi totali stampati
    # (ricavi - costi), e il resto della differenza dei totali SP e' il risultato precedente,
    # ricostruito e dichiarato (_prior_result_ricostruito), mai messo in sp13.
    if (not prior_footer and prior_caption_senza_importo and total_gap is not None
            and ce_control_result is not None
            and abs(total_gap - ce_control_result) > Decimal('0.05')):
        ricostruito = total_gap - ce_control_result
        add(bs, 'sp12', ricostruito)
        add(bs, 'sp12g_utili_perdite_portati', ricostruito)
        bs['_prior_result_footer'] = ricostruito
        bs['_prior_result_ricostruito'] = ricostruito
        prior_footer = ricostruito
        total_gap = ce_control_result
        logger.warning(f"contrapposte: risultato esercizi precedenti {ricostruito} "
                       "ricostruito dai totali stampati (didascalia senza importo)")

    independent_results = [v for v in (explicit_result, total_gap, ce_control_result)
                           if v is not None]
    result_controls_agree = (len(independent_results) >= 2
                             and max(independent_results) - min(independent_results)
                             <= Decimal('0.05'))
    if use_garbled_reconstruction and result_controls_agree:
        utile = independent_results[0]
    elif (total_gap is not None and abs(total_gap) <= Decimal('0.05')
          and booked_results and result[0]):
        # Totali stampati uguali: il conto di risultato e' gia' dentro il totale del
        # passivo, e la differenza dei totali (zero) non e' l'utile (budget_435).
        utile = result[0]
    elif total_gap is not None:
        utile = total_gap
    else:
        utile = result[0]                                  # booked account fallback
    bs['sp13'] = utile

    # Conti "Utile (perdita) d'esercizio" letti fra i conti dello stato patrimoniale:
    # quelli tolti come risultato e quelli col codice che il raccoglitore scarta come
    # righe di totale (AITEC 30/06/2026: mastro 309 e sottoconto 309.00001, 269.255,83
    # ciascuno). Diversi dal risultato del periodo sono il risultato dell'anno prima non
    # ancora destinato; se stiano dentro il totale passivita' lo decide il totale
    # stampato, sotto, e solo al centesimo (STB 30/06/2026 ne ha uno nei conti d'ordine,
    # fuori dai totali).
    prior_candidates = list(booked_results)
    for sec, side, fact in controls:
        d = fact.description
        if (sec == 'sp' and fact.code and 'ESERCIZ' in d
                and any(k in d for k in ('UTILE', 'PERDIT', 'RISULTAT'))
                and not _kw_any(d, ['PORTAT', 'NUOVO', 'PRECEDENT', 'TOTALE'])):
            perdita = side == 'left' or ('PERDITA' in d and 'UTILE' not in d)
            prior_candidates.append(-fact.amount if perdita else fact.amount)
    prior_candidates = sorted({b for b in prior_candidates
                               if abs(b - utile) > Decimal('0.05')
                               and (ce_control_result is None
                                    or abs(b - ce_control_result) > Decimal('0.05'))})

    # A fondo ammortamento can never exceed its own gross asset, so a negative net
    # immobilizzazione is always a misclassification (fondo netted off the wrong /
    # a missing gross asset — budget_365/435). Clamp at 0: a negative asset is never
    # a valid IV-CEE value; the residual then surfaces honestly in the plug below.
    for _immk in ('sp02', 'sp03', 'sp04'):
        if bs.get(_immk, Z) < Z:
            bs[_immk] = Z

    # Trial-balance pareggio total; the IV-CEE total removes the perdita that is
    # parked on the attivo side as a balancing item.
    tb_total = pareggio
    if tb_total is None and tot_att is not None and tot_pas is not None:
        tb_total = max(tot_att, tot_pas)
    if tb_total is None:
        tb_total = tot_att or tot_pas

    if tb_total:
        # tb_total (pareggio / TOTALE ATTIVO) is GROSS when contra-asset funds sit on the
        # passivo side; subtract the netted contra mass so the IV-CEE NET total matches the
        # netted asset/passivo sums (plug ~ 0 instead of ~ fondi). No-op when netted_contra=0.
        iv_total = tb_total - (abs(utile) if utile < 0 else Z) - netted_contra
        att_sum = sum((bs.get(k, Z) for k in _ATTIVO_KEYS), Z)
        res_a = iv_total - att_sum
        pas_sum = sum((bs.get(k, Z) for k in _PASSIVO_KEYS), Z)
        res_p = iv_total - pas_sum
        if abs(res_p) > Decimal('0.05'):
            chiude = [b for b in prior_candidates if abs(res_p - b) <= Decimal('0.05')]
            if chiude:
                b = chiude[0]
                add(bs, 'sp12', b)
                add(bs, 'sp12g_utili_perdite_portati', b)
                bs['_prior_result_booked'] = b
                pas_sum += b
                res_p = iv_total - pas_sum
                logger.info(f"contrapposte: conto di risultato {b} diverso dal risultato "
                            f"del periodo {utile} e dentro il totale passivita' -> sp12g")
        # Keep the statement exactly as classified.  ``iv_total`` is independent
        # evidence from the source, not permission to manufacture the missing side.
        bs['totale_attivo'] = att_sum
        bs['totale_passivo'] = pas_sum
        bs['_declared_net_total'] = iv_total
        bs['_unexplained_asset_difference'] = res_a
        bs['_unexplained_liability_difference'] = res_p
        worst = max(abs(res_a), abs(res_p))
        # Expose the plug magnitude so the shared quadratura engine can tell a real
        # balance from one that only ties because the residual was swept into
        # sp09/sp16. Survives _map_sc_keys (has '_') and is ignored by the BS builder.
        bs['_plug_residual'] = worst
        # A geometrically reconstructed statement is authoritative only when
        # independent source controls agree and both net sides reconcile without
        # a compensating accounting entry.  This flag merely prevents a later
        # declared-total mutator from undoing that source-backed result.
        if (use_garbled_reconstruction and result_controls_agree
                and worst <= Decimal('0.05')):
            bs['_plug_residual'] = Z
            bs['_skip_declared_reconcile'] = True
        if worst > Decimal('1'):
            logger.warning(
                f"BILANCIO NON QUADRATO (contrapposte best-effort): residuo attivo={res_a}, "
                f"passivo={res_p}; nessun plug applicato — verificare in Rettifiche"
            )
    else:
        # No reliable declared total (e.g. code-less footer): retain both classified
        # sides and expose their difference.  Anchoring the shorter side to the larger
        # one used to invent cash/debt and turn incomplete extraction into a false OK.
        att_sum = sum((bs.get(k, Z) for k in _ATTIVO_KEYS), Z)
        pas_sum = sum((bs.get(k, Z) for k in _PASSIVO_KEYS), Z)
        bs['totale_attivo'] = att_sum
        bs['totale_passivo'] = pas_sum
        bs['_plug_residual'] = abs(att_sum - pas_sum)
        if abs(att_sum - pas_sum) > Decimal('1'):
            logger.warning(
                f"BILANCIO NON QUADRATO (contrapposte best-effort): totali dichiarati non "
                f"trovati, differenza non spiegata {abs(att_sum - pas_sum)}; "
                f"nessun plug applicato — verificare in Rettifiche"
            )

    # Rescue: a MASKED result on a dotted hierarchical ('4 sezioni') layout is the
    # truncated-deep-code collision described above. Retry via the level-1 mastri
    # reconstruction and keep it ONLY when it reconciles (self-validated inside
    # _hier_reconstruct) — so a file the best-effort already balances is untouched.
    plug_now = bs.get('_plug_residual', Z)
    total_now = bs.get('totale_attivo', Z) or Z
    # Anche senza codici a punti (budget_703: mastri a 2 cifre, conti a 3 che non ne portano
    # il prefisso): i mastri si riconoscono dalla somma dei loro conti e la ricostruzione si
    # tiene solo se si verifica da sola sul totale stampato e sul risultato del CE.
    if plug_now > max(Decimal('1'), Decimal('0.01') * total_now):
        try:
            rescued = _hier_reconstruct(pages_data, full)
        except Exception as he:
            logger.warning(f"Hierarchical reconstruct failed: {type(he).__name__}: {he}")
            rescued = None
        if rescued is not None:
            logger.info("Hierarchical mastri reconstruction reconciled — using it over the masked best-effort")
            return rescued

    return bs, ce
