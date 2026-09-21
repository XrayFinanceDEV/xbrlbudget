"""Independently cross-foot printed legal subtotals before replacing hypotheses.

Only legal rows are authoritative here, never account balances, movements or a
balancing difference. Unsupported/ambiguous sources leave the extraction intact.
"""
from collections import defaultdict
from decimal import Decimal
import re

from importers.detail_enrichment import collect_source_rows
from importers.iv_cee_hierarchy import detail_fields, _net_profit_from_ce
from importers.standard_ivcee_parser import _normalise, has_comparative_ivcee_columns

ZERO = Decimal('0')
TOL = Decimal('2')  # printed legal statements may be rounded to euros
AGG = ('sp01_crediti_soci', 'sp02_immob_immateriali', 'sp03_immob_materiali',
       'sp04_immob_finanziarie', 'sp05_rimanenze', 'sp06_crediti_breve', 'sp07_crediti_lungo',
       'sp08_attivita_finanziarie', 'sp09_disponibilita_liquide', 'sp10_ratei_risconti_attivi',
       'sp11_capitale', 'sp12_riserve', 'sp13_utile_perdita', 'sp14_fondi_rischi', 'sp15_tfr',
       'sp16_debiti_breve', 'sp17_debiti_lungo', 'sp18_ratei_risconti_passivi')


def _family(label, section):
    if section == 'ce':
        return None
    for pattern, family in (
        (r'^i\b.*immobilizzazioni immateriali', 'sp02'),
        (r'^ii\b.*immobilizzazioni materiali', 'sp03'),
        (r'^iii\b.*immobilizzazioni finanziarie', 'sp04'),
        (r'^i\b.*rimanenze', 'sp05'), (r'^ii\b.*crediti', 'credit'),
        (r'^iii\b.*attivit.*finanziarie', 'sp08'), (r'^iv\b.*disponibilit', 'sp09'),
        (r'^a\b.*patrimonio netto', 'pn'), (r'^b\b.*fondi per rischi', 'sp14'),
        (r'^c\b.*trattamento di fine rapporto', 'sp15'), (r'^d\b.*debiti', 'debt'),
        (r'^d\b.*ratei e risconti', 'sp10'), (r'^e\b.*ratei e risconti', 'sp18'),
    ):
        if re.search(pattern, label):
            return family
    return None


def _category(label, debt):
    if debt:
        if ('soci' in label and 'finanziam' in label) or 'altri finanziatori' in label:
            return 'b'
        for word, letter in (('banche', 'a'), ('obbligazion', 'c'), ('fornitori', 'd'),
                             ('tributar', 'e'), ('previdenza', 'f')):
            if word in label:
                return letter
        return 'g'
    if 'controllo delle controllanti' in label:
        return 'g'
    for word, letter in (('clienti', 'a'), ('controllate', 'b'), ('collegate', 'c'),
                         ('controllanti', 'd'), ('tributar', 'e'), ('anticipate', 'f')):
        if word in label:
            return letter
    return 'g'


def _read_column(rows, column, cutoff):
    facts, errors, evidence = {}, [], []
    partitions = defaultdict(dict)
    section = family = category = None
    ce_item = None

    def put(key, value, row):
        if key in facts and facts[key] != value:
            errors.append(f'contradictory source: {key}')
        facts[key] = value
        evidence.append({'field': key, 'row': row.id, 'page': row.page, 'value': str(value), 'text': row.text})

    for row in rows:
        if row.side != 'T' or row.code:
            continue
        label = _normalise(row.text)
        if label.startswith('conto economico'):
            section, family = 'ce', None
        elif label.startswith(('stato patrimoniale attivo', "attivita'")):
            section = 'asset'
        elif label.startswith(('stato patrimoniale passivo', "passivita'")):
            section = 'liability'
        if section is None:
            continue
        new_family = _family(label, section)
        if new_family:
            family, category = new_family, None
        # Physical coordinates, not the ordinal numeric index: blank current
        # cells must never steal the previous year's amount.
        cells = [(v, x) for v, x in zip(row.amounts, row.positions) if x > 350]
        values = [v for v, x in cells if (0 if cutoff is None or x < cutoff else 1) == column]
        if len(values) > 1:
            errors.append(f'ambiguous numeric column: {row.id}')
            continue
        value = values[0] if values else None

        if section == 'ce':
            item = re.match(r'^(?:totale )?(\d+)(?:[ -]?(bis))?\)', label)
            if item:
                ce_item = item[1] + ('bis' if item[2] else '')
                if value is not None:
                    put('ceitem_' + ce_item, value, row)
            subitem = re.match(r'^(?:totale )?([a-e])\)', label)
            if subitem and value is not None and ce_item in ('9', '10'):
                fields = ({'a': 'ce08b_salari_stipendi', 'b': 'ce08c_oneri_sociali',
                           'c': 'ce08a_tfr_accrual', 'd': 'ce08_pensions', 'e': 'ce08_other'}
                          if ce_item == '9' else dict(zip('abcd', detail_fields('ce09_ammortamenti'))))
                if subitem[1] in fields:
                    put(fields[subitem[1]], value, row)
            if value is not None:
                for prefix, key in (
                    ('totale valore della produzione', 'ce_a'), ('totale costi della produzione', 'ce_b'),
                    ('totale costi per il personale', 'ceitem_9'), ('totale ammortamenti e svalutazioni', 'ceitem_10'),
                    ('totale altri ricavi e proventi', 'ceitem_5'), ('totale proventi da partecipazioni', 'ceitem_15'),
                    ('totale altri proventi finanziari', 'ceitem_16'), ('totale interessi e altri oneri', 'ceitem_17'),
                    ('totale rivalutazioni', 'ceitem_18'), ('totale svalutazioni', 'ceitem_19'),
                    ('totale delle imposte sul reddito', 'ceitem_20'), ('risultato prima delle imposte', 'ce_pretax'),
                    ("utile (perdita) dell'esercizio", 'ce_result'), ('21) utile', 'ce_result'),
                ):
                    if label.startswith(prefix):
                        put(key, value, row)
            continue

        if family in ('credit', 'debt'):
            header = re.match(r'^(\d+(?:[ -]?(?:bis|ter|quater))?)(?:\)|(?=\s*verso\b))', label)
            if header:
                category = header[1]
                partitions[family, category]['letter'] = _category(label, family == 'debt')
            if category is not None and 'esigibili' in label and value is not None:
                maturity = 'long' if 'oltre' in label else 'short' if 'entro' in label else None
                if maturity:
                    key = f'{family}:{category}:{maturity}'
                    put(key, value, row)
                    partitions[family, category][maturity] = value

        if value is None:
            continue
        for prefix, key in (
            ('totale immobilizzazioni immateriali', AGG[1]), ('totale immobilizzazioni materiali', AGG[2]),
            ('totale immobilizzazioni finanziarie', AGG[3]), ('totale immobilizzazioni (b)', 'total_fixed'),
            ('totale rimanenze', AGG[4]), ('totale attivita finanziarie', AGG[7]),
            ('totale attivit… finanziarie', AGG[7]), ('totale disponibilita liquide', AGG[8]),
            ('totale disponibilit… liquide', AGG[8]), ('totale attivo circolante', 'total_current'),
            ('totale patrimonio netto', 'total_equity'), ('totale fondi per rischi', AGG[13]),
        ):
            if label.startswith(prefix):
                put(key, value, row)
        if re.match(r'^totale (crediti|debiti)(?:\s+\(|\s+-?\d|$)', label):
            if family in ('credit', 'debt'):
                put('total_' + family, value, row)
        if re.match(r'^totale (attivo|passivo)(?:\s+\(|\s+\d|$)', label):
            put('totale_attivo' if 'attivo' in label else 'totale_passivo', value, row)
        if re.match(r'^totale disponibilit.*liquide', label):
            put(AGG[8], value, row)
        if re.match(r'^totale attivit.*finanziarie', label):
            put(AGG[7], value, row)
        if family in ('sp10', 'sp15', 'sp18') and (
                re.match(r'^totale (?:ratei e risconti|c\) trattamento)', label) or new_family):
            put(next(k for k in AGG if k.startswith(family + '_')), value, row)
        if family == 'pn':
            if re.match(r'^(?:totale )?i\b.*capitale', label):
                put(AGG[10], value, row)
            elif re.match(r'^(?:ix\b.*)?utile \(perdita\)', label):
                put(AGG[12], value, row)
            for pattern, field in (
                (r'^(?:totale )?ii\b.*sovrapprezzo', 'sp12a_riserva_sovrapprezzo'),
                (r'^(?:totale )?iii\b.*rivalutaz', 'sp12b_riserve_rivalutazione'),
                (r'^(?:totale )?iv\b.*legale', 'sp12c_riserva_legale'),
                (r'^(?:totale )?v\b.*statutar', 'sp12d_riserve_statutarie'),
                (r'^totale altre riserve', 'sp12e_altre_riserve'),
                (r'^(?:totale )?vii\b.*copertura', 'sp12f_riserva_copertura_flussi'),
                (r'^(?:totale )?viii\b.*portat', 'sp12g_utili_perdite_portati'),
                (r'^(?:totale )?x\b.*azioni proprie', 'sp12h_riserva_neg_azioni_proprie'),
            ):
                if re.search(pattern, label):
                    put(field, value, row)
        if family == 'sp04':
            if label.startswith('totale partecipazioni'):
                put('sp04a_partecipazioni', value, row)
            elif 'esigibili' in label:
                field = ('sp04c_crediti_immob_lungo' if 'oltre' in label else
                         'sp04b_crediti_immob_breve' if 'entro' in label else None)
                if field:
                    put(field, value, row)
        # Fixed and inventory subheadings have either a number on the heading
        # itself or a closing 'Totale n)'. They are never summed with accounts.
        if family in ('sp02', 'sp03', 'sp05', 'sp14'):
            item = re.match(r'^(?:totale )?(\d+)\)', label)
            if item:
                fields = detail_fields(next(k for k in AGG if k.startswith(family + '_')))
                index = int(item[1]) - 1
                if 0 <= index < len(fields):
                    put(fields[index], value, row)

    tol = Decimal('.01') if any(v.as_tuple().exponent < 0 for v in facts.values()) else TOL
    bs = {k: facts.get(k, ZERO) for k in AGG}
    for group, short_index, long_index in (('credit', 5, 6), ('debt', 15, 16)):
        for (kind, cat), parts in partitions.items():
            if kind != group:
                continue
            for maturity, index in (('short', short_index), ('long', long_index)):
                value = parts.get(maturity, ZERO)
                field = next(f for f in detail_fields(AGG[index]) if f[4] == parts['letter'])
                bs[field] = bs.get(field, ZERO) + value
                bs[AGG[index]] += value
    if 'total_equity' in facts:
        bs[AGG[11]] = facts['total_equity'] - bs[AGG[10]] - bs[AGG[12]]
    bs.update({k: v for k, v in facts.items() if re.match(r'^sp\d\d[a-z]_', k)})
    checks = {
        'fixed': (sum(bs[k] for k in AGG[1:4]), facts.get('total_fixed')),
        'credits': (bs[AGG[5]] + bs[AGG[6]], facts.get('total_credit')),
        'current': (sum(bs[k] for k in AGG[4:9]), facts.get('total_current')),
        'debts': (bs[AGG[15]] + bs[AGG[16]], facts.get('total_debt')),
        'assets': (sum(bs[k] for k in AGG[:10]), facts.get('totale_attivo')),
        'liabilities': (sum(bs[k] for k in AGG[10:]), facts.get('totale_passivo')),
    }
    for key, (calculated, printed) in checks.items():
        if printed is None or abs(calculated - printed) > tol:
            errors.append(f'{key}: calculated={calculated}, printed={printed}')
    if abs(facts.get('totale_attivo', ZERO) - facts.get('totale_passivo', ZERO)) > tol:
        errors.append('printed sides do not reconcile')
    if not {AGG[10], AGG[12], 'total_equity'}.issubset(facts):
        errors.append('missing printed equity controls')
    for aggregate in AGG:
        fields = detail_fields(aggregate)
        if any(f in bs for f in fields) and abs(sum(bs.get(f, ZERO) for f in fields) - bs[aggregate]) > tol:
            errors.append(f'{aggregate}: incomplete detail partition')
    if errors:
        return None, None, {'status': 'declined', 'errors': errors, 'evidence': evidence}
    bs.update({k: facts[k] for k in ('totale_attivo', 'totale_passivo')})
    bs['_source_standard_ivcee'] = Decimal('1')
    ce = _income(facts, bs[AGG[12]], tol=tol)
    return bs, ce, {'status': 'verified', 'method': 'legal_subtotals', 'tolerance': str(tol),
                    'evidence': evidence, 'income_verified': ce is not None}


def _income(facts, sp_profit, tol=TOL):
    if not {'ce_a', 'ce_b', 'ce_pretax', 'ce_result'}.issubset(facts):
        return None
    mapping = {1: 'ce01_ricavi_vendite', 2: 'ce02_variazioni_rimanenze', 4: 'ce03_lavori_interni',
               5: 'ce04_altri_ricavi', 6: 'ce05_materie_prime', 7: 'ce06_servizi', 8: 'ce07_godimento_beni',
               9: 'ce08_costi_personale', 10: 'ce09_ammortamenti', 11: 'ce10_var_rimanenze_mat_prime',
               12: 'ce11_accantonamenti', 13: 'ce11b_altri_accantonamenti', 14: 'ce12_oneri_diversi',
               15: 'ce13_proventi_partecipazioni', 16: 'ce14_altri_proventi_finanziari', 17: 'ce15_oneri_finanziari',
               20: 'ce20_imposte'}
    sign = -1 if facts['ce_b'] < 0 else 1
    ce = {field: facts.get(f'ceitem_{i}', ZERO) * (sign if 6 <= i <= 14 else 1) for i, field in mapping.items()}
    ce['ce02_variazioni_rimanenze'] += facts.get('ceitem_3', ZERO)
    ce['ce15_oneri_finanziari'] = abs(ce['ce15_oneri_finanziari'])
    ce['ce20_imposte'] *= sign
    ce['ce16_utili_perdite_cambi'] = facts.get('ceitem_17bis', ZERO)
    ce['ce17a_rivalutazioni'] = abs(facts.get('ceitem_18', ZERO))
    ce['ce17b_svalutazioni'] = abs(facts.get('ceitem_19', ZERO))
    ce['ce17_rettifiche_attivita_fin'] = ce['ce17a_rivalutazioni'] - ce['ce17b_svalutazioni']
    for aggregate in ('ce08_costi_personale', 'ce09_ammortamenti'):
        for field in detail_fields(aggregate):
            if field in facts:
                ce[field] = facts[field] * sign
    if 'ce08_pensions' in facts or 'ce08_other' in facts:
        ce['ce08d_altri_costi_personale'] = (facts.get('ce08_pensions', ZERO) + facts.get('ce08_other', ZERO)) * sign
    production = sum(ce[mapping[i]] for i in (1, 2, 4, 5))
    costs = sum(ce[mapping[i]] for i in range(6, 15))
    result = _net_profit_from_ce(ce)
    if any(abs(a - b) > tol for a, b in (
        (production, facts['ce_a']), (costs, abs(facts['ce_b'])),
        (result + ce['ce20_imposte'], facts['ce_pretax']),
        (result, facts['ce_result']), (result, sp_profit))):
        return None
    return ce


def extract_legal_source(file_path):
    rows = collect_source_rows(file_path)
    comparative = has_comparative_ivcee_columns(file_path)
    # Infer the gutter from paired monetary cells, not from account numbers or
    # dates in the page header. Refuse overlapping bands.
    pairs = [(r.positions[-2], r.positions[-1]) for r in rows
             if not r.code and len(r.amounts) == 2 and r.positions[-2] > 350]
    cutoff = None
    if comparative:
        if not pairs or max(a for a, b in pairs) >= min(b for a, b in pairs):
            return [(None, None, {'status': 'declined', 'errors': ['ambiguous year columns']})]
        cutoff = (max(a for a, b in pairs) + min(b for a, b in pairs)) / 2
    return [_read_column(rows, column, cutoff) for column in range(2 if comparative else 1)]


def extract_ago_source(file_path):
    """Physical master rows, checked against four independently printed totals.

    Account codes identify hierarchy, NOT accounting meaning. Opposite-side
    prior losses reduce equity; separate funds reduce their corresponding asset.
    An incomplete CE text layer cannot invalidate an independently proved SP.
    """
    from importers.situazione_contabile_parser import Entry, build_iv_cee, _classify_sp_passivo
    from importers.detail_enrichment import _ledger_maturity
    from importers.pdf_importer import _map_sc_keys

    rows = collect_source_rows(file_path)
    masters = [r for r in rows if re.fullmatch(r'\d{8}', r.code) and r.side in ('L', 'R')
               and r.amounts and r.kinds[-1] in ('ledger_final', 'income')]
    if len(masters) < 10:
        return None, None, {'status': 'unsupported'}
    totals, evidence, entries, maturities = {}, [], [], []
    for row in rows:
        if row.code or len(row.amounts) != 1:
            continue
        label = row.text.upper()
        for word, key in (("ATTIVITA'", 'attivo'), ("PASSIVITA'", 'passivo'),
                          ('COSTI', 'costi'), ('RICAVI', 'ricavi')):
            if label.startswith(('TOTALE ' + word, word + ' ')):
                totals[key] = row.amounts[0]
        if "PERDITA D'ESERCIZIO" in label:
            totals['profit'] = -row.amounts[0]
        elif "UTILE D'ESERCIZIO" in label:
            totals['profit'] = row.amounts[0]
    sums = defaultdict(Decimal)
    prior_loss = ZERO
    for row in masters:
        section = ('attivo' if row.side == 'L' else 'passivo') if row.kinds[-1] == 'ledger_final' else (
            'costi' if row.side == 'L' else 'ricavi')
        amount = row.amounts[-1]
        label = re.sub(r'^\d{8}\s*-?\s*', '', row.text)
        sums[section] += amount
        if section == 'attivo' and re.search(r'PERDITE.*PORTATE.*NUOVO', label.upper()):
            section, amount = 'passivo', -amount
            prior_loss -= amount
        if section == 'passivo' and _classify_sp_passivo(label.upper()) in ('debt_bank', 'sp16', 'bank_avere'):
            maturity, basis = _ledger_maturity(row, rows, debt=True)
            if maturity == 'unknown':
                return None, None, {'status': 'declined', 'errors': ['contradictory source maturity']}
            if maturity == 'long' and '(OE)' not in label.upper() and 'OLTRE' not in label.upper():
                label += ' OLTRE 12 MESI'
            maturities.append({'row': row.id, 'text': row.text, 'amount': str(amount),
                               'maturity': maturity, 'basis': basis})
        entries.append(Entry(row.code, label, amount, level=1, section=section))
        evidence.append({'row': row.id, 'page': row.page, 'text': row.text,
                         'section': section, 'value': str(amount)})
    errors = [f'{side}: read={sums[side]}, printed={totals.get(side)}'
              for side in ('attivo', 'passivo')
              if side not in totals or abs(sums[side] - totals[side]) > Decimal('.01')]
    profit = totals.get('profit')
    if profit is None or abs(sums['attivo'] - sums['passivo'] - (profit or ZERO)) > Decimal('.01'):
        errors.append('missing/inconsistent printed result')
    if errors:
        return None, None, {'status': 'declined', 'errors': errors, 'evidence': evidence}
    entries.append(Entry('****', 'Risultato corrente', profit, level=4, section='passivo'))
    raw_bs, raw_ce = build_iv_cee(entries)
    bs, ce = _map_sc_keys(raw_bs), _map_sc_keys(raw_ce)
    expected_net = totals['attivo'] - prior_loss - bs.get('_netted_contra', ZERO)
    if any(abs(bs[k] - expected_net) > Decimal('.01') for k in ('totale_attivo', 'totale_passivo')):
        return None, None, {'status': 'declined', 'errors': ['mapped SP does not cross-foot'], 'evidence': evidence}
    ce_ok = all(k in totals and abs(sums[k] - totals[k]) <= Decimal('.01') for k in ('costi', 'ricavi'))
    ce_ok = ce_ok and abs(_net_profit_from_ce(ce) - profit) <= Decimal('.01')
    bs['_source_ago_coordinates'] = Decimal('1')
    bs['_source_debt_maturities_verified'] = Decimal('1')
    return bs, ce if ce_ok else None, {
        'status': 'verified', 'method': 'ago_physical_masters', 'income_verified': ce_ok, 'evidence': evidence,
        'controls': {k: str(v) for k, v in totals.items()},
        'maturity': maturities,
        'errors': [] if ce_ok else ['CE source rows incomplete or inconsistent with printed controls'],
    }


def extract_source_candidates(file_path):
    """Return current/prior proofs, never a best-effort balancing hypothesis."""
    from importers.legal_path_evidence import extract_path_source
    qualified = extract_path_source(file_path)
    if qualified:
        return qualified
    legal = extract_legal_source(file_path)
    if legal[0][0] is not None:
        return legal
    ago = extract_ago_source(file_path)
    if ago[2]['status'] != 'unsupported':
        return [ago]
    from importers.ledger_evidence import extract_ledger_source
    ledger = extract_ledger_source(file_path)
    if ledger[2]['status'] != 'unsupported':
        return [ledger]
    controls = inspect_signed_closing_controls(file_path)
    if controls:
        return [(None, None, controls)]
    return legal


def inspect_signed_closing_controls(file_path):
    """Check a five-column D/A trial balance without confusing flows and stocks.

    Roots are controls only, never additive accounts. A pre-existing opening
    imbalance must not be hidden in current profit/reserves by any extractor.
    """
    import fitz
    from importers.detail_enrichment import _amount
    from importers.situazione_contabile_parser import _be_cluster_physical_rows

    roots, evidence, profits = {}, [], set()
    with fitz.open(file_path) as doc:
        for page in doc:
            words = page.get_text('words')
            text = page.get_text()
            if 'Saldo Periodo' not in text or text.count('Saldo al') < 2:
                continue
            for line in _be_cluster_physical_rows(words, -1e9, 1e9):
                label = ' '.join(w[4] for w in line)
                # A final amount followed by an explicit D/A, beyond the last
                # movement column; never take the last nonempty numeric cell.
                cells = [(w, _amount(w[4])) for w in line
                         if w[2] > page.rect.width * .90 and _amount(w[4]) is not None]
                if len(cells) != 1:
                    continue
                word, value = cells[0]
                sign = next((w[4] for w in line if 0 <= w[0] - word[2] < 10 and w[4] in ('D', 'A')), None)
                if label.startswith(('UTILE ESERCIZIO:', 'PERDITA ESERCIZIO:')):
                    profits.add(value if label.startswith('UTILE') else -value)
                if not re.fullmatch(r'\d{2}', line[0][4]) or not sign:
                    continue
                kind = next((k for token, k in (("ATTIVITA'", 'assets'), ("PASSIVITA'", 'liabilities'),
                                              ('COSTI', 'costs'), ('RICAVI', 'revenues'))
                             if token in label), None)
                if kind:
                    signed = value if sign == ('D' if kind in ('assets', 'costs') else 'A') else -value
                    if kind in roots and roots[kind] != signed:
                        return None  # not the same statement/period
                    roots[kind] = signed
                    evidence.append({'page': page.number + 1, 'text': label, 'field': kind, 'value': str(signed)})
    if len(roots) != 4 or len(profits) != 1:
        return None
    profit = profits.pop()
    if abs(roots['revenues'] - roots['costs'] - profit) > Decimal('.01'):
        return None
    difference = roots['assets'] - roots['liabilities'] - profit
    if abs(difference) <= Decimal('.01'):
        return None
    return {'status': 'source_conflict', 'requires_review': True, 'evidence': evidence,
            'controls': {**{k: str(v) for k, v in roots.items()}, 'profit': str(profit),
                         'unreconciled': str(difference)},
            'errors': ['Il saldo finale SP non riconcilia con il risultato CE stampato: '
                       f'scarto {difference}. Non compensare in riserve, debiti o risultato corrente.']}


def apply_source_candidate(bs, ce, candidate):
    """Replace proved statements, including stale specific fields and plug flags.

    This is deliberately different from detail enrichment: evidence can disprove
    the original parent. No mutation and no mixing of old/new accounting fields.
    """
    source_bs, source_ce, audit = candidate
    report = dict(audit)
    if audit.get('status') != 'verified':
        return bs, ce, {**report, 'changes': {}}
    changes = {}
    for old, source, prefix in ((bs, source_bs, 'sp'), (ce, source_ce, 'ce')):
        if source is None:
            continue
        for key in sorted(set(old or {}) | set(source)):
            if key.startswith(prefix) and (old or {}).get(key, ZERO) != source.get(key, ZERO):
                changes[key] = {'before': str((old or {}).get(key, ZERO)), 'after': str(source.get(key, ZERO))}
    report['changes'] = changes
    return (dict(source_bs) if source_bs is not None else bs,
            dict(source_ce) if source_ce is not None else ce, report)
