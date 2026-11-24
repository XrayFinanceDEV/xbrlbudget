"""build_iv_cee: dalle righe lette ai campi sp/ce.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import re
from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Tuple
from importers.situazione_contabile.comune import (
    Entry,
)
from importers.situazione_contabile.regole import (
    _CE_AMMORTAMENTO_RE, _CE_HIER_SUBPARENT, _CREDIT_FIELD, _DEBT_FIELD, _RISERVA_FIELD, _ce09_dal_dettaglio,
    _classify_ce_costi, _classify_ce_costi_foglia, _classify_ce_ricavi, _classify_sp_attivo,
    _classify_sp_passivo, _credit_type, _debt_type, _kw_any, _kw_match, _natura_unanime,
    _rimanenze_dal_dettaglio, _riserva_type, _sp02_detail_field, _sp03_detail_field, _sp04_detail_field,
    _sp05_detail_field, _sp14_detail_field, _spesa_capitalizzata_orfana,
)


def build_iv_cee(entries: List[Entry], default_ce: bool = False) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Map trial balance entries to IV CEE sp01-sp18 and ce01-ce20 fields.

    When default_ce is True (detail-level trial balances where CE lines rarely
    contain category keywords), unmatched ricavi lines default to ce01 and
    unmatched costi lines to ce12, so the P&L is captured rather than dropped.
    """
    bs: Dict[str, Decimal] = {}
    ce: Dict[str, Decimal] = {}

    # Accumulators
    gross_sp02 = Decimal('0')  # Immob. immateriali (gross)
    gross_sp03 = Decimal('0')  # Immob. materiali (gross)
    depr_sp02 = Decimal('0')   # F/amm immateriali
    depr_sp03 = Decimal('0')   # F/amm materiali
    bank_dare = Decimal('0')
    bank_avere = Decimal('0')
    crediti_deduction = Decimal('0')
    capitale = Decimal('0')
    riserve = Decimal('0')
    utile_esercizio = Decimal('0')
    # conti "Utile/Perdita d'esercizio" dello SP scartati per non contarli due volte col
    # risultato del periodo (livello 4): se non coincidono con lui sono il risultato
    # dell'anno prima non ancora destinato (COLOMBO 2026), che non si perde
    risultati_scartati: List[Decimal] = []
    risultato_periodo_letto = False

    # Debt entro/oltre from detail lines
    debt_bank_entro = Decimal('0')
    debt_bank_oltre = Decimal('0')
    debt_bank_total = Decimal('0')

    # Typed sub-field accumulators (depth preservation). Mirror the EXACT amounts
    # that feed the aggregates, so they're purely additive: sub-fields are emitted
    # at finalization and reconciled to the aggregate, never altering it. Dicts are
    # mutated in place (no nonlocal needed).
    typed_debt_breve = {k: Decimal('0') for k in 'abcdefg'}
    typed_debt_oltre = {k: Decimal('0') for k in 'abcdefg'}
    typed_credit_breve = {k: Decimal('0') for k in 'aefg'}
    typed_credit_deduction = {k: Decimal('0') for k in 'aefg'}
    typed_riserve = {k: Decimal('0') for k in 'abcdeg'}
    # Gross fixed-asset details and their matching depreciation funds.  These
    # remain description-driven: account numbers vary across ERP products.
    typed_fixed_gross: Dict[str, Decimal] = defaultdict(Decimal)
    typed_fixed_depr: Dict[str, Decimal] = defaultdict(Decimal)
    typed_direct_assets: Dict[str, Decimal] = defaultdict(Decimal)
    typed_fondi_rischi: Dict[str, Decimal] = defaultdict(Decimal)
    # Conti d'attivo finiti nel default crediti che si descrivono come spese di
    # manutenzione capitalizzabili: (importo, tipo credito, descrizione).
    sp06_spese_capitalizzabili: List[Tuple[Decimal, str, str]] = []

    # CE sub-items
    ce_tfr_accrual = Decimal('0')
    ce09a = Decimal('0')  # ammort. immateriali
    ce09b = Decimal('0')  # ammort. materiali
    ce09c = Decimal('0')  # altre svalutazioni delle immobilizzazioni
    ce09d = Decimal('0')  # svalutazioni
    ce09_nd = Decimal('0')  # ammortamenti che il documento non ripartisce
    ce10_opening = Decimal('0')
    ce10_closing = Decimal('0')
    ce01_total = Decimal('0')
    ce01_returns = Decimal('0')

    # Track which prefixes have sub2 (level 2) and sub3 (level 1) entries
    has_sub2: set = set()
    has_sub3: set = set()
    for entry in entries:
        if entry.level == 2:
            has_sub2.add((entry.prefix2, entry.section))
        elif entry.level == 1:
            has_sub3.add((entry.prefix2, entry.section))

    # Track which sections expose any subtotal (level 1 or 2). For "flat" trial
    # balances that contain ONLY level-0 detail lines (no XX/YY/*** or XX/**/***
    # subtotals), we must process the detail lines directly, classifying each by
    # description, otherwise the whole section would be dropped.
    sections_with_subtotals: set = set()
    for entry in entries:
        if entry.level in (1, 2) and entry.section:
            sections_with_subtotals.add(entry.section)

    livello_di = {(e.code, e.section): e.level for e in entries}
    ripiego_rimanenze = {
        'costi': _natura_unanime(e.description.upper() for e in entries if e.section == 'ricavi'),
        'ricavi': _natura_unanime(e.description.upper() for e in entries if e.section == 'costi'),
    }

    def _figli_entry(section):
        """figli(codice) per i subtotali XX/**/*** e XX/YY/***: i conti del livello
        subito sotto con la stessa radice di codice (un dettaglio non ne ha)."""
        def figli(code):
            stem = code.split('*')[0]
            if not stem or stem == code:
                return []
            lvl = livello_di.get((code, section), 0)
            cands = [e for e in entries
                     if e.section == section and e.code != code
                     and e.code.startswith(stem) and e.level < lvl]
            if not cands:
                return []
            top = max(e.level for e in cands)
            return [(e.code, e.description.upper(), e.amount) for e in cands if e.level == top]
        return figli

    def _rimanenze_entry(entry, tag, desc_upper, classify):
        """[(campo, importo)] di una categoria di rimanenze, letta dai conti
        (_rimanenze_dal_dettaglio): 'ce10'/'ce10_close' per le materie, 'ce02' col
        segno gia' applicato per i prodotti, la voce propria per un conto che
        rimanenza non e'."""
        out = []
        for t, x in _rimanenze_dal_dettaglio(tag, entry.code, desc_upper, entry.amount,
                                             _figli_entry(entry.section), classify,
                                             ripiego_rimanenze.get(entry.section)):
            if t in ('ce10', 'ce10_close'):
                out.append((t, x))
            elif t == 'ce02_open':
                out.append(('ce02', -x))
            else:
                out.append((_CE_HIER_SUBPARENT.get(t, t), x))
        return out

    def _process_category(entry: Entry) -> None:
        """Process a sub2 or standalone sub3 entry through keyword classification."""
        nonlocal gross_sp02, gross_sp03, depr_sp02, depr_sp03
        nonlocal bank_dare, bank_avere, crediti_deduction, capitale, riserve
        nonlocal debt_bank_total, debt_bank_entro, debt_bank_oltre
        nonlocal ce09a, ce09b, ce09c, ce09d, ce09_nd, ce_tfr_accrual
        nonlocal ce10_opening, ce10_closing, ce01_total, ce01_returns

        desc_upper = entry.description.upper()

        # =================================================================
        # STATO PATRIMONIALE — ATTIVO
        # =================================================================
        if entry.section == 'attivo':
            field = _classify_sp_attivo(desc_upper)
            if field == 'gross_sp02':
                gross_sp02 += entry.amount
                detail = _sp02_detail_field(desc_upper)
                if detail:
                    typed_fixed_gross[detail] += entry.amount
            elif field == 'gross_sp03':
                gross_sp03 += entry.amount
                detail = _sp03_detail_field(desc_upper)
                if detail:
                    typed_fixed_gross[detail] += entry.amount
            elif field == 'gross_sp04':
                bs['sp04'] = bs.get('sp04', Decimal('0')) + entry.amount
                detail = _sp04_detail_field(desc_upper)
                if detail:
                    typed_direct_assets[detail] += entry.amount
            elif field == 'sp05':
                bs['sp05'] = bs.get('sp05', Decimal('0')) + entry.amount
                detail = _sp05_detail_field(desc_upper)
                if detail:
                    typed_direct_assets[detail] += entry.amount
            elif field == 'sp09':
                bank_dare += entry.amount
            else:
                bs[field] = bs.get(field, Decimal('0')) + entry.amount
                # Typed depth: crediti breve by debtor type (clienti/tributari/altri)
                if field == 'sp06':
                    typed_credit_breve[_credit_type(desc_upper)] += entry.amount
                    if _spesa_capitalizzata_orfana(desc_upper):
                        sp06_spese_capitalizzabili.append(
                            (entry.amount, _credit_type(desc_upper), desc_upper))
            return

        # =================================================================
        # STATO PATRIMONIALE — PASSIVO
        # =================================================================
        if entry.section == 'passivo':
            field = _classify_sp_passivo(desc_upper)
            if field == 'depr_sp02':
                depr_sp02 += entry.amount
                detail = _sp02_detail_field(desc_upper)
                if detail:
                    typed_fixed_depr[detail] += entry.amount
            elif field == 'depr_sp03':
                depr_sp03 += entry.amount
                detail = _sp03_detail_field(desc_upper)
                if detail:
                    typed_fixed_depr[detail] += entry.amount
            elif field == 'deduct_crediti':
                crediti_deduction += entry.amount
                typed_credit_deduction[_credit_type(desc_upper)] += entry.amount
            elif field == 'bank_avere':
                bank_avere += entry.amount
            elif field == 'equity_total':
                if entry.level == 2:
                    return  # skip sub2 total (DEPI); AGO emits only level=1
                # Current-year utile/perdita is set from the level-4 pareggio plug;
                # skip parent-level entries to avoid double-counting
                if (_kw_match(desc_upper, ['UTILE', 'ESERCIZ']) or
                        _kw_match(desc_upper, ['PERDITA', 'ESERCIZ'])):
                    if not _kw_any(desc_upper, ['PORTATI', 'PRECEDENT', 'NUOVO']):
                        risultati_scartati.append(
                            -entry.amount if 'PERDITA' in desc_upper and 'UTILE' not in desc_upper
                            else entry.amount)
                        return
                if ((_kw_match(desc_upper, ['CAPITALE'])
                        or re.match(r'^CAP\.\s?SOC', desc_upper))      # "CAP. SOC./PATR.NET." (budget_1343)
                        and 'RISERV' not in desc_upper):
                    capitale += entry.amount
                else:
                    riserve += entry.amount
                    typed_riserve[_riserva_type(desc_upper)] += entry.amount
            elif field == 'debt_bank':
                if entry.level in (0, 1, 2):
                    # Parent/detail (EE)/(OE) routing: AGO suffix convention,
                    # plus DEPI flat-balance ENTRO/OLTRE in the description.
                    # Typed depth: banche/altri-finanz/obbligazioni by description.
                    _dt = _debt_type(desc_upper)
                    if '(OE)' in desc_upper or 'OLTRE' in desc_upper:
                        debt_bank_oltre += entry.amount
                        debt_bank_total += entry.amount
                        typed_debt_oltre[_dt] += entry.amount
                    elif '(EE)' in desc_upper or 'ENTRO' in desc_upper:
                        debt_bank_entro += entry.amount
                        debt_bank_total += entry.amount
                        typed_debt_breve[_dt] += entry.amount
                    else:
                        debt_bank_total += entry.amount
                        typed_debt_breve[_dt] += entry.amount
            elif field == 'sp16':
                # Non-bank debts with (OE) suffix → long-term (sp17).
                # Typed depth: fornitori/tributari/previdenza/altri by description.
                _dt = _debt_type(desc_upper)
                if '(OE)' in desc_upper or 'OLTRE' in desc_upper:
                    bs['sp17'] = bs.get('sp17', Decimal('0')) + entry.amount
                    typed_debt_oltre[_dt] += entry.amount
                else:
                    bs['sp16'] = bs.get('sp16', Decimal('0')) + entry.amount
                    typed_debt_breve[_dt] += entry.amount
            elif field == 'sp14':
                bs['sp14'] = bs.get('sp14', Decimal('0')) + entry.amount
                detail = _sp14_detail_field(desc_upper)
                if detail:
                    typed_fondi_rischi[detail] += entry.amount
            else:
                bs[field] = bs.get(field, Decimal('0')) + entry.amount
            return

        # =================================================================
        # CONTO ECONOMICO — COSTI
        # =================================================================
        if entry.section == 'costi':
            field = _classify_ce_costi(desc_upper)
            if field == 'ce01_return':
                ce01_returns += entry.amount
            elif field in ('ce09a', 'ce09b', 'ce09d') or (
                    field is None and _CE_AMMORTAMENTO_RE.match(desc_upper)):
                # "AMMORTAMENTI E SVALUTAZIONI" o "AMMORTAMENTI" nudo: le sotto-voci le
                # dicono i conti sotto (_ce09_dal_dettaglio), mai la parola SVALUT da
                # sola, e mai il ripiego fra gli oneri diversi (confine dell'EBITDA)
                for t, x in _ce09_dal_dettaglio(entry.code, desc_upper, entry.amount,
                                                _figli_entry(entry.section)):
                    if t == 'ce09a':
                        ce09a += x
                    elif t == 'ce09b':
                        ce09b += x
                    elif t == 'ce09c':
                        ce09c += x
                    elif t == 'ce09d':
                        ce09d += x
                    else:
                        ce09_nd += x
            elif field in ('ce10', 'ce02_open'):
                for t, x in _rimanenze_entry(entry, field, desc_upper, _classify_ce_costi):
                    if t == 'ce10':
                        ce10_opening += x
                    else:
                        ce[t] = ce.get(t, Decimal('0')) + x
            elif field == 'ce08a_tfr':
                ce_tfr_accrual += entry.amount
                ce['ce08'] = ce.get('ce08', Decimal('0')) + entry.amount
            elif field == 'ce08b':
                ce['ce08'] = ce.get('ce08', Decimal('0')) + entry.amount
                ce['ce08b_salari_stipendi'] = ce.get('ce08b_salari_stipendi', Decimal('0')) + entry.amount
            elif field == 'ce08c':
                ce['ce08'] = ce.get('ce08', Decimal('0')) + entry.amount
                ce['ce08c_oneri_sociali'] = ce.get('ce08c_oneri_sociali', Decimal('0')) + entry.amount
            elif field == 'ce08d':
                ce['ce08'] = ce.get('ce08', Decimal('0')) + entry.amount
                ce['ce08d_altri_costi_personale'] = ce.get('ce08d_altri_costi_personale', Decimal('0')) + entry.amount
            elif field == 'ce13_cost':
                ce['ce13'] = ce.get('ce13', Decimal('0')) - entry.amount
            elif field == 'ce16_cost':
                ce['ce16'] = ce.get('ce16', Decimal('0')) - entry.amount
            elif field:
                ce[field] = ce.get(field, Decimal('0')) + entry.amount
            elif default_ce:
                # Detail-level cost line with no keyword match → la parola del conto
                # foglia, altrimenti oneri diversi.
                foglia = _classify_ce_costi_foglia(desc_upper)
                if foglia == 'ce08a_tfr':
                    ce_tfr_accrual += entry.amount
                    ce['ce08'] = ce.get('ce08', Decimal('0')) + entry.amount
                elif foglia == 'ce08b':
                    ce['ce08'] = ce.get('ce08', Decimal('0')) + entry.amount
                    ce['ce08b_salari_stipendi'] = ce.get('ce08b_salari_stipendi', Decimal('0')) + entry.amount
                elif foglia == 'ce08c':
                    ce['ce08'] = ce.get('ce08', Decimal('0')) + entry.amount
                    ce['ce08c_oneri_sociali'] = ce.get('ce08c_oneri_sociali', Decimal('0')) + entry.amount
                else:
                    ce[foglia or 'ce12'] = ce.get(foglia or 'ce12', Decimal('0')) + entry.amount
            return

        # =================================================================
        # CONTO ECONOMICO — RICAVI
        # =================================================================
        if entry.section == 'ricavi':
            field = _classify_ce_ricavi(desc_upper)
            if field == 'ce01':
                ce01_total += entry.amount
            elif field in ('ce10_close', 'ce02'):
                for t, x in _rimanenze_entry(entry, field, desc_upper, _classify_ce_ricavi):
                    if t == 'ce10_close':
                        ce10_closing += x
                    else:
                        ce[t] = ce.get(t, Decimal('0')) + x
            elif field == 'ce20_provento':
                ce['ce20'] = ce.get('ce20', Decimal('0')) - entry.amount
            elif field:
                ce[field] = ce.get(field, Decimal('0')) + entry.amount
            elif default_ce:
                # Detail-level revenue line with no keyword match → ricavi vendite.
                ce01_total += entry.amount
            return

    # Main processing loop
    for entry in entries:
        desc_upper = entry.description.upper()

        # Page headers are not ledger accounts.  Some codeless/stacked exports put
        # the company address or fiscal identifier immediately after a numeric
        # token, so the generic row reader interprets them as a code/description/
        # amount triple (BILANCIO-TEST: ``5034 / VIA ROMA 162`` -> EUR 1.62;
        # budget_435/367: P.IVA -> EUR 19,675,904.96).  Exclude only unmistakable
        # registry metadata; never use the balance gap to compensate it later.
        # Il dato anagrafico apre la riga: "IVA PARTITA IVA FRANCESE" e' un conto (Santini).
        if (
            re.match(r'^(?:VIA|VIALE|V\.LE|PIAZZA|P\.ZZA|CORSO)\b', desc_upper)
            or re.match(r'^\W*(?:CODICE FISCALE|PARTITA IVA)\b', desc_upper)
            or re.match(r'^(?:C\.F\.|P\.IVA|REA)\b', desc_upper)
        ):
            continue

        # Section totals
        if entry.level == 3:
            continue  # ignore trial balance section totals

        if entry.level == 4:
            # UTILE DI ESERCIZIO
            risultato_periodo_letto = True
            if entry.section in ('passivo', 'ricavi'):
                utile_esercizio = entry.amount
            elif entry.section in ('attivo', 'costi'):
                utile_esercizio = -entry.amount
            else:
                utile_esercizio = entry.amount
            continue

        if entry.level >= 5:
            continue

        if not entry.prefix2:
            continue

        # Sub2 entries: always process
        if entry.level == 2:
            _process_category(entry)
            continue

        # Sub3 entries: process only if no sub2 exists for this prefix+section
        if entry.level == 1:
            if (entry.prefix2, entry.section) not in has_sub2:
                _process_category(entry)
                continue
            # Even with sub2 parent, extract equity sub-items and CE TFR
            if entry.section == 'passivo':
                passivo_field = _classify_sp_passivo(desc_upper)
                if passivo_field == 'equity_total':
                    if _kw_match(desc_upper, ['CAPITALE']):
                        capitale += entry.amount
                    else:
                        riserve += entry.amount
                        typed_riserve[_riserva_type(desc_upper)] += entry.amount
                    continue
            if entry.section == 'costi' and ('TFR' in desc_upper or
                    _kw_match(desc_upper, ['TRATTAMENTO', 'FINE', 'RAPPORTO'])):
                ce_tfr_accrual += entry.amount
                continue

        # Flat trial balance: a section with NO subtotals (only level-0 detail).
        # Classify each detail line by description directly.
        if entry.level == 0 and entry.section and entry.section not in sections_with_subtotals:
            _process_category(entry)
            continue

        # Equity exposed only at detail level (level 0) under a level-2 total
        # (XX/****), which is skipped for equity. Extract here when there is a
        # sub2 parent but no intervening level-1 entry for this prefix+section.
        if (entry.level == 0 and entry.section == 'passivo'
                and (entry.prefix2, entry.section) in has_sub2
                and (entry.prefix2, entry.section) not in has_sub3):
            if _classify_sp_passivo(desc_upper) == 'equity_total':
                if (_kw_match(desc_upper, ['UTILE', 'ESERCIZ']) or
                        _kw_match(desc_upper, ['PERDITA', 'ESERCIZ']) or
                        _kw_match(desc_upper, ['RISULTATO', 'ESERCIZ'])):
                    if not _kw_any(desc_upper, ['PORTATI', 'PRECEDENT', 'NUOVO', 'PORTATE']):
                        risultati_scartati.append(
                            -entry.amount if 'PERDITA' in desc_upper and 'UTILE' not in desc_upper
                            else entry.amount)
                        continue
                if _kw_match(desc_upper, ['CAPITALE']):
                    capitale += entry.amount
                else:
                    riserve += entry.amount
                    typed_riserve[_riserva_type(desc_upper)] += entry.amount
                continue

        # Orphan detail lines: a level-0 entry whose prefix has NO subtotal
        # (neither XX/YY/*** nor XX/**/*** nor XX/****) in this section. The
        # parent total would otherwise carry it, so process it directly to
        # avoid dropping it. Guarded by has_sub2/has_sub3 to prevent
        # double-counting where a real subtotal exists.
        if (entry.level == 0
                and (entry.prefix2, entry.section) not in has_sub2
                and (entry.prefix2, entry.section) not in has_sub3):
            if entry.section == 'passivo':
                passivo_field = _classify_sp_passivo(desc_upper)
                if passivo_field == 'equity_total':
                    if (_kw_match(desc_upper, ['UTILE', 'ESERCIZ']) or
                            _kw_match(desc_upper, ['PERDITA', 'ESERCIZ']) or
                            _kw_match(desc_upper, ['RISULTATO', 'ESERCIZ'])):
                        if not _kw_any(desc_upper, ['PORTATI', 'PRECEDENT', 'NUOVO', 'PORTATE']):
                            risultati_scartati.append(
                                -entry.amount if 'PERDITA' in desc_upper and 'UTILE' not in desc_upper
                                else entry.amount)
                            continue
                    if _kw_match(desc_upper, ['CAPITALE']):
                        capitale += entry.amount
                    else:
                        riserve += entry.amount
                        typed_riserve[_riserva_type(desc_upper)] += entry.amount
                    continue
            _process_category(entry)
            continue

        # Detail level: debt entro/oltre classification
        if entry.level == 0 and entry.section == 'passivo':
            # Check if parent is a bank debt category
            if 'ENTRO' in desc_upper:
                debt_bank_entro += entry.amount
            elif 'OLTRE' in desc_upper:
                debt_bank_oltre += entry.amount

    # =====================================================================
    # Build final BS
    # =====================================================================

    # Net gross assets against depreciation. Clamp at 0: a fondo ammortamento can
    # never exceed its own gross asset, so a negative net immobilizzazione is always
    # a misclassification (fondo booked without/over its asset — budget_330/365/435)
    # and a negative asset is never a valid IV-CEE value.
    # Un fondo ammortamento IMMATERIALE senza il suo lordo (depr_sp02 > gross_sp02)
    # e' una contraddizione: il clamp qui sotto lo farebbe sparire in silenzio e lo
    # SP non pareggerebbe piu' della sua eccedenza. Se fra i conti d'attivo finiti
    # nel default crediti ci sono spese di manutenzione (capitalizzate per forza, un
    # costo non sta nello SP), quello e' il lordo del fondo: si sposta da sp06 a
    # sp02. Solo a contraddizione presente, cosi' nessun foglio che oggi netta
    # correttamente cambia.
    if depr_sp02 > gross_sp02 and sp06_spese_capitalizzabili:
        for _amt, _ctype, _d in sp06_spese_capitalizzabili:
            bs['sp06'] = bs.get('sp06', Decimal('0')) - _amt
            typed_credit_breve[_ctype] -= _amt
            gross_sp02 += _amt
            _det = _sp02_detail_field(_d)
            if _det:
                typed_fixed_gross[_det] += _amt
    bs['sp02'] = bs.get('sp02', Decimal('0')) + max(Decimal('0'), gross_sp02 - depr_sp02)
    bs['sp03'] = bs.get('sp03', Decimal('0')) + max(Decimal('0'), gross_sp03 - depr_sp03)

    # Emit only source-supported IV-CEE details.  Each depreciation fund is
    # subtracted from the same semantic asset family; an unknown caption stays
    # visible as a hierarchy difference instead of being invented as "altri".
    for detail, gross in typed_fixed_gross.items():
        bs[detail] = bs.get(detail, Decimal('0')) + max(
            Decimal('0'), gross - typed_fixed_depr.get(detail, Decimal('0'))
        )
    for detail, amount in typed_direct_assets.items():
        bs[detail] = bs.get(detail, Decimal('0')) + amount
    for detail, amount in typed_fondi_rischi.items():
        bs[detail] = bs.get(detail, Decimal('0')) + amount

    # Immobilizzazioni are presented GROSS on these trial balances (fondi
    # ammortamento are separate passivo lines, netted just above), so the document's
    # DECLARED total / pareggio is GROSS. Expose the netted contra mass so the
    # route-C pipeline can reduce the declared anchor before reconciling — otherwise
    # the netted fondi resurface as a FALSE plug (budget_131 Oprandi: net attivo
    # 230.205,93 vs gross pareggio 355.878,76 → spurious 125.672,83 plug). Survives
    # _map_sc_keys (underscore key). Mirrors net_contra_accounts' returned _contra
    # for the best-effort path. Cap the applied fondi at the gross asset present, so
    # the anchor reduction never exceeds the gross immobilizzazioni (a fondo without
    # a matching asset — the clamp case above — must not shrink the declared anchor).
    _netted = min(depr_sp02, gross_sp02) + min(depr_sp03, gross_sp03)

    # Banks
    bs['sp09'] = bs.get('sp09', Decimal('0')) + bank_dare

    # Crediti deduction. Il fondo svalutazione/rischi su crediti e' un contra dei
    # CREDITI esposto sul passivo esattamente come i fondi ammortamento lo sono
    # delle immobilizzazioni: nettarlo abbassa l'attivo senza abbassare il totale
    # DICHIARATO, che resta lordo. Se non entra anche lui nella massa contra,
    # riemerge come plug FALSO di importo pari al fondo (budget_281: 17.768,10 su
    # 1.708.975,05 = 1,04% -> oltre la soglia dell'1% -> QUADRATURA MASCHERATA su
    # un bilancio che invece e' corretto). Stesso cap dei fondi ammortamento: mai
    # oltre i crediti lordi presenti, cosi' un fondo senza il suo credito non
    # puo' restringere l'ancora.
    if crediti_deduction > 0:
        _gross_crediti = bs.get('sp06', Decimal('0'))
        bs['sp06'] = _gross_crediti - crediti_deduction
        _netted += min(crediti_deduction, max(Decimal('0'), _gross_crediti))

    if _netted > 0:
        bs['_netted_contra'] = bs.get('_netted_contra', Decimal('0')) + _netted

    # Il risultato dell'anno prima non destinato (un conto "utile d'esercizio" fra i conti
    # del patrimonio diverso dal risultato del periodo): utili (perdite) portati a nuovo,
    # dichiarato. Quando coincide col risultato del periodo e' lui, e non cambia nulla.
    if risultati_scartati and risultato_periodo_letto:
        _prima = sum(risultati_scartati, Decimal('0'))
        if abs(_prima - utile_esercizio) > Decimal('0.05'):
            riserve += _prima
            typed_riserve['g'] += _prima
            bs['_risultato_anno_prima_conti'] = _prima

    # Equity
    bs['sp11'] = capitale
    bs['sp12'] = riserve
    bs['sp13'] = utile_esercizio

    # Debiti v/banche: entro/oltre split
    bs.setdefault('sp16', Decimal('0'))
    bs.setdefault('sp17', Decimal('0'))

    if debt_bank_entro + debt_bank_oltre > 0:
        bs['sp16'] += debt_bank_entro
        bs['sp17'] += debt_bank_oltre
        remainder = debt_bank_total - debt_bank_entro - debt_bank_oltre
        if remainder > 0:
            bs['sp16'] += remainder
    else:
        # No entro/oltre markers → all breve
        bs['sp16'] += debt_bank_total

    # Bank overdrafts → sp16
    bs['sp16'] += bank_avere
    # Overdrafts are bank debt: keep them in the typed depth too.
    typed_debt_breve['a'] += bank_avere

    # -----------------------------------------------------------------
    # Typed sub-field depth (additive): emit the OIC creditor/debtor/riserve
    # breakdown the source distinguished, reconciled so the sub-fields sum
    # EXACTLY to their aggregate. This never changes an aggregate (and thus
    # never the balance) — it only exposes the detail level present in the
    # document instead of one lumped voce. When the source carries no type
    # info, the residual falls into 'altri'/'altre riserve' (same as before).
    # -----------------------------------------------------------------
    def _reconcile_typed(aggregate: Decimal, buckets: Dict[str, Decimal], altri: str) -> None:
        residual = aggregate - sum(buckets.values())
        buckets[altri] = buckets.get(altri, Decimal('0')) + residual
        if buckets[altri] < 0:
            # Contra/deduction exceeded 'altri' (rare) — clamp; the small leftover
            # gap is reconciled downstream (frontend reconcileSubfields).
            buckets[altri] = Decimal('0')

    _reconcile_typed(bs.get('sp16', Decimal('0')), typed_debt_breve, 'g')
    _reconcile_typed(bs.get('sp17', Decimal('0')), typed_debt_oltre, 'g')
    # A fondo svalutazione follows the debtor family it explicitly names.  In
    # particular, "f.do sval. crediti v/clienti" reduces sp06a rather than being
    # forced into the residual sp06g bucket (budget_615).
    for letter, deduction in typed_credit_deduction.items():
        if deduction:
            typed_credit_breve[letter] = max(
                Decimal('0'), typed_credit_breve.get(letter, Decimal('0')) - deduction
            )
    _reconcile_typed(bs.get('sp06', Decimal('0')), typed_credit_breve, 'g')
    _reconcile_typed(bs.get('sp12', Decimal('0')), typed_riserve, 'e')

    for letter, amt in typed_debt_breve.items():
        bs[_DEBT_FIELD['breve'][letter]] = amt
    for letter, amt in typed_debt_oltre.items():
        bs[_DEBT_FIELD['lungo'][letter]] = amt
    for letter, amt in typed_credit_breve.items():
        bs[_CREDIT_FIELD['breve'][letter]] = amt
    for letter, amt in typed_riserve.items():
        bs[_RISERVA_FIELD[letter]] = amt
    # Crediti lungo (sp07): not typed by this parser — expose the aggregate as 'altri'
    # so the sub-row reconciles (clienti/tributari lungo are rare in trial balances).
    if bs.get('sp07', Decimal('0')):
        bs['sp07g_crediti_altri_lungo'] = bs['sp07']

    # Defaults
    for i in range(1, 19):
        bs.setdefault(f'sp{i:02d}', Decimal('0'))

    # Recalculate totals from IV CEE values
    bs['totale_attivo'] = sum(bs[f'sp{i:02d}'] for i in range(1, 11))
    bs['totale_passivo'] = sum(bs[f'sp{i:02d}'] for i in range(11, 19))

    # =====================================================================
    # Build final CE
    # =====================================================================

    ce['ce01'] = ce01_total - ce01_returns
    ce['ce10'] = ce10_opening - ce10_closing
    ce['ce08a_tfr_accrual'] = ce_tfr_accrual

    total_amm = ce09a + ce09b + ce09c + ce09d + ce09_nd
    ce['ce09'] = total_amm
    ce['ce09a_ammort_immateriali'] = ce09a
    ce['ce09b_ammort_materiali'] = ce09b
    ce['ce09c_svalutazioni'] = ce09c
    ce['ce09d_svalutazione_crediti'] = ce09d

    # Defaults
    for i in range(1, 21):
        ce.setdefault(f'ce{i:02d}', Decimal('0'))
    for extra in ['ce08a_tfr_accrual', 'ce09a_ammort_immateriali', 'ce09b_ammort_materiali',
                  'ce09c_svalutazioni', 'ce09d_svalutazione_crediti', 'ce11b',
                  'ce13', 'ce14', 'ce16', 'ce17', 'ce18', 'ce19']:
        ce.setdefault(extra, Decimal('0'))

    return bs, ce
