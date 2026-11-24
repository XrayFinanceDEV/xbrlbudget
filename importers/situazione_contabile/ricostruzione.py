"""Ricostruzione gerarchica dai mastri di primo livello.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import re
from decimal import Decimal
from typing import Dict
from importers.situazione_contabile.fondi import (
    _is_fondo_amm,
)
from importers.situazione_contabile.comune import (
    _parse_amount,
)
from importers.situazione_contabile.regole import (
    _ATTIVO_KEYS, _CE09_SOTTO, _CE_HIER_SUBPARENT, _CE_SUBFIELD_PARENT, _albero_da_dettagliare,
    _ce09_dal_dettaglio, _classify_ce_costi, _classify_ce_costi_foglia, _classify_ce_ricavi,
    _classify_ce_ricavi_foglia, _classify_ce_sinonimo, _classify_sp_attivo, _classify_sp_passivo,
    _figli_puntati, _kw_match, _natura_unanime, _resolve_ce_field, _rimanenze_dal_dettaglio, fallback_bucket,
    fallback_field,
)
from importers.situazione_contabile.best_effort import (
    _BE_AMT_RE, _be_amount, _be_cluster_physical_rows, _be_split,
)
from importers.situazione_contabile.mastri_gerarchici import (
    _hier_collect, _hier_lvl1, _hier_prior_result, _hier_split_ai_codici, _is_prior_result_caption,
)


def _hier_reconstruct(pages_data, full: str):
    """Reconstruct a balanced IV-CEE sheet from level-1 mastri. Returns (bs, ce) or
    None when the layout does not reconcile (caller then keeps the best-effort result).
    """
    Z = Decimal('0')
    att, pas, cos, ric = [], [], [], []
    prior_pn = Z
    unclassified = []          # (desc, amount, assigned_field)
    for words, is_sp, is_ce, up, width in pages_data:
        split = _be_split(words)
        if split is None:
            split = width / 2
        split = _hier_split_ai_codici(words, split, width)
        left = _hier_collect(words, -1e9, split)
        right = _hier_collect(words, split, 1e9)
        if is_sp and not is_ce:
            att += left
            pas += right
            # A trial balance often does NOT consolidate the previous year's
            # result into the capital/reserve accounts: it is printed as a
            # code-less row in the SP footer ("Utile esercizio precedente").
            # It is patrimonio netto (utili portati a nuovo) — a credit balance
            # on the passivo side, a debit balance on the attivo side.
            prior_pn += _hier_prior_result(words, split, 1e9)
            prior_pn -= _hier_prior_result(words, -1e9, split)
        elif is_ce and not is_sp:
            # Il lato dei costi lo dicono le DESCRIZIONI dei conti, non l'ordine delle
            # parole d'intestazione nel testo lineare (budget_405 stampa "RICAVI COSTI"
            # ma i costi stanno a sinistra). L'ordine del testo resta solo quando le
            # descrizioni non decidono.
            _lc = sum(1 for _c, _d, _a in left if _classify_ce_costi(_d))
            _lr = sum(1 for _c, _d, _a in left if _classify_ce_ricavi(_d))
            _rc = sum(1 for _c, _d, _a in right if _classify_ce_costi(_d))
            _rr = sum(1 for _c, _d, _a in right if _classify_ce_ricavi(_d))
            if _lc + _rr != _rc + _lr:
                scambiate = _rc + _lr > _lc + _rr
            else:
                scambiate = ('COSTI' in up[:400] and 'RICAVI' in up[:400]
                             and up[:400].find('RICAVI') < up[:400].find('COSTI'))
            if scambiate:
                cos += right
                ric += left
            else:
                cos += left
                ric += right

    ma, mp = _hier_lvl1(att), _hier_lvl1(pas)
    mc, mr = _hier_lvl1(cos), _hier_lvl1(ric)
    if len(ma) < 4 or len(mp) < 4:
        return None                       # not a clean two-column mastri layout

    bs: Dict[str, Decimal] = {}
    netted = Z

    def addb(k, v):
        bs[k] = bs.get(k, Z) + v

    def _net_fondo(code, desc, amount, side_rows):
        """Net a fondi-ammortamento mastro SPLITTING immat/mat: the level-1
        caption ("FONDI AMMORTAMENTO IMMOBILIZ") is category-blind, so read the
        split from its DIRECT child rows (level-2 mastri: "FONDI AMMORT.
        IMMOBILIZZAZ. IMM" → sp02) when they reconcile to the mastro amount;
        otherwise fall back to the mastro's own classification. Unattributed
        mass keeps netting sp03 (the historical behaviour)."""
        nonlocal netted

        def _immateriale(c0, a0, profondita=0):
            # La quota immateriale di un nodo: tutta se la didascalia lo dice; altrimenti
            # quella dei figli diretti, se lo ricostruiscono, scendendo di un livello
            # quando un figlio non lo dice da solo (Nicole: "FONDI AMMORT. IMMOBILIZZAZ.
            # IM", troncata, con sotto avviamento e software).
            desc_rows = [(c, d2, a2) for c, d2, a2 in side_rows
                         if c != c0 and c.startswith(c0)]
            direct = [(c, d2, a2) for c, d2, a2 in desc_rows
                      if not any(o != c and c.startswith(o)
                                 for o, _d3, _a3 in desc_rows)]
            covered = sum(a2 for _c2, _d2, a2 in direct)
            tol = max(Decimal('2'), abs(a0) * Decimal('0.01'))
            if not (c0 and direct and abs(covered - a0) <= tol):
                return None
            im0 = Z
            for c2, d2, a2 in direct:
                if _classify_sp_passivo(d2) == 'depr_sp02':
                    im0 += a2
                elif profondita < 3:
                    im0 += _immateriale(c2, a2, profondita + 1) or Z
            return im0

        im = Z
        if code:
            im = _immateriale(code, amount) or Z
        if im == Z and _classify_sp_passivo(desc) == 'depr_sp02':
            im = amount
        addb('sp02', -im)
        addb('sp03', -(amount - im))
        netted += amount

    for _c, d, a in ma:
        if _is_fondo_amm(d):
            _net_fondo(_c, d, a, att)
        else:
            f = _classify_sp_attivo(d)
            addb({'gross_sp02': 'sp02', 'gross_sp03': 'sp03', 'gross_sp04': 'sp04'}.get(f, f), a)
    def _passivo_parts(code, desc, amount):
        """Keep parent totals but inspect children of ambiguous equity/debt heads.

        A root named RISULTATI DELL'ESERCIZIO can contain PORTATI A NUOVO;
        CAPITALE E RISERVE contains two different equity destinations. Stopping
        at these roots preserves quadratura while misclassifying their nature.
        Only disjoint direct children fitting the parent are used; any uncovered
        amount retains the parent's original classification.
        """
        tag = _classify_sp_passivo(desc)
        ambiguous = (tag == 'equity_total' and 'CAPITALE' in desc and 'RISERV' in desc)
        ambiguous = ambiguous or (tag == 'sp16' and 'RISULTAT' in desc)
        # Un mastro "FONDI ..." che nessuna regola riconosce ("FONDI SVALUTAZIONE")
        # cadrebbe nel default debiti: un fondo non e' mai un debito. I figli diretti
        # dicono di che fondo si tratta (svalutazione CREDITI -> nettato dai crediti).
        ambiguous = ambiguous or (tag == 'sp16' and 'FOND' in desc)
        # Sul passivo un nome di CESPITE ("IMMOBILIZZAZIONI MATERIALI", "TERRENI E
        # FABBRICATI") e' la testa dei fondi ammortamento della categoria: i figli sono
        # i fondi, che si nettano dal loro cespite; da solo cadrebbe fra i debiti.
        # Stesso discorso per una testa di CREDITI stampata sul passivo: sotto ci sono
        # il fondo svalutazione (che netta i crediti) e i crediti a saldo avere.
        ambiguous = ambiguous or (tag == 'sp16' and (
            _classify_sp_attivo(desc) in ('gross_sp02', 'gross_sp03')
            or re.search(r'\bCRED(?:IT[IO]\b|\.)', desc)))   # non CREDITORI
        if ambiguous:
            descendants = list(dict.fromkeys(
                (c, d, a) for c, d, a in pas if c.startswith(code + '.')
            ))
            direct = [(c, d, a) for c, d, a in descendants
                      if not any(c.startswith(other + '.') for other, _, _ in descendants)]
            covered = sum((a for _, _, a in direct), Z)
            # Duplicate/incomplete geometries must not double count the parent.
            if direct and len({c for c, _, _ in direct}) == len(direct) and covered == amount:
                for c, d, a in direct:
                    yield from _passivo_parts(c, d, a)
                return
        yield code, desc, amount

    passivo_parts = [part for c, d, a in mp for part in _passivo_parts(c, d, a)]
    for _c, d, a in passivo_parts:
        if _is_fondo_amm(d):
            _net_fondo(_c, d, a, pas)
            continue
        t = _classify_sp_passivo(d)
        if _is_prior_result_caption(d):
            addb('sp12', a)
            addb('sp12g_utili_perdite_portati', a)
        elif t == 'equity_total':
            addb('sp11' if (_kw_match(d, ['CAPITALE']) and 'RISERV' not in d) else 'sp12', a)
        elif t in ('depr_sp02', 'depr_sp03', 'depr_sp04'):
            addb(t.replace('depr_', ''), -a)
            netted += a
        elif t == 'deduct_crediti':
            addb('sp06', -a)
            netted += a
        elif t in ('sp14', 'sp15', 'sp18'):
            addb(t, a)
        else:
            addb('sp16', a)

    # Unconsolidated prior-year result -> utili (perdite) portati a nuovo.
    if prior_pn:
        addb('sp12', prior_pn)

    # CE: every cost mastro lands in a cost field and every revenue mastro in a
    # revenue field, so the net (ricavi - costi) is sign-correct regardless of the
    # exact bucket (used both for the import P&L and for the reconciliation check).
    ce: Dict[str, Decimal] = {}

    def adde(k, v):
        ce[k] = ce.get(k, Z) + v

    figli_costi, figli_ricavi = _figli_puntati(cos), _figli_puntati(ric)
    ripiego_costi = _natura_unanime(d for _c, d, _a in ric)
    ripiego_ricavi = _natura_unanime(d for _c, d, _a in cos)
    da_dettagliare = []
    for _c, d, a in mc:
        f = (_classify_ce_costi(d) or _resolve_ce_field(d, 'costi')
             or _classify_ce_costi_foglia(d) or _classify_ce_sinonimo(d, 'costi'))
        if f is None:
            f = fallback_field('ce')
            unclassified.append((d, a, 'ce'))
        if f == 'ce09' or f in _CE09_SOTTO:
            for t, x in _ce09_dal_dettaglio(_c, d, a, figli_costi):
                adde('ce09', x)
                if t != 'ce09':
                    adde(_CE_SUBFIELD_PARENT[t][0], x)
            continue
        if f in ('ce10', 'ce02_open'):
            for t, x in _rimanenze_dal_dettaglio(f, _c, d, a, figli_costi, _classify_ce_costi,
                                                 ripiego_costi):
                if t == 'ce02_open':
                    adde('ce02', -x)
                elif t in _CE_HIER_SUBPARENT:
                    adde(_CE_HIER_SUBPARENT[t], x)
                else:
                    adde(t, x)
            continue
        if f == 'ce01_return':
            adde('ce01', -a)
        elif f == 'ce10_close':
            adde('ce10', -a)
        elif f == 'ce13_cost':
            adde('ce15', a)
        elif f in _CE_HIER_SUBPARENT:
            adde(_CE_HIER_SUBPARENT[f], a)
        elif f == 'ce08':
            # Personale senza sotto-voce: le parole chiave non bastano a ripartirlo, lo
            # fa il modello sui conti sotto il mastro (importers/dettaglio_dal_modello.py)
            adde('ce08', a)
            da_dettagliare.append(_albero_da_dettagliare('ce08', _c, d, a, figli_costi))
        else:
            adde(f, a)
    if da_dettagliare:
        ce['_ce_da_dettagliare'] = da_dettagliare
    for _c, d, a in mr:
        f = (_classify_ce_ricavi(d) or _resolve_ce_field(d, 'ricavi')
             or _classify_ce_ricavi_foglia(d) or _classify_ce_sinonimo(d, 'ricavi'))
        if f is None:
            f = 'ce04'
            unclassified.append((d, a, 'ce'))
        for t, x in _rimanenze_dal_dettaglio(f, _c, d, a, figli_ricavi, _classify_ce_ricavi,
                                             ripiego_ricavi):
            if t == 'ce10_close':
                adde('ce10', -x)
            else:
                adde(t, x)

    att_sum = sum((bs.get(k, Z) for k in _ATTIVO_KEYS), Z)

    # Mass assigned by fallback rather than recognised. Only the MATERIAL part is
    # reported: below the threshold a generic bucket is a legitimate label; above
    # it the composition is guesswork and must be visible. fallback_bucket is the
    # single policy entry point, called here where the total is finally known.
    material = Z
    for _desc, _amt, _stmt in unclassified:
        _field, _severity = fallback_bucket(_desc, _stmt, _amt, att_sum)
        if _severity == 'recorded':
            material += abs(_amt)
    bs['_unclassified_mass'] = material
    # Misurata, non assente: questo percorso SA quale massa letta e' finita in un
    # secchio generico, quindi lo zero qui significa «pulito» e non «non lo so».
    # reliability.assess distingue i due casi da questa chiave, e una chiave
    # assente vale «non misurato» — tacere non puo' valere come promessa.
    bs['_unclassified_mass_measured'] = Decimal('1')

    pas_sum = sum((bs.get(k, Z) for k in ('sp11', 'sp12', 'sp14', 'sp15', 'sp16', 'sp17', 'sp18')), Z)
    sp13 = att_sum - pas_sum               # result as the SP gap → attivo == passivo

    # --- validation: keep ONLY when it genuinely reconciles ---
    up1 = re.sub(r'\s+', ' ', full.upper())
    flat1 = re.sub(r'\s+', '', full.upper())

    def _ft(spaced, flat):
        if spaced in up1:
            return _be_amount(up1.split(spaced, 1)[1][:40])
        if flat in flat1:
            return _be_amount(flat1.split(flat, 1)[1][:40])
        return None

    # Prefer the rightmost coordinate-backed ``TOTALE ATTIVITA`` printed in the
    # SP footer.  On adjusted four-column statements the linear text is laid out
    # as ``saldo non rettificato / rettifiche / saldo finale``: ``_ft`` therefore
    # sees the first (pre-adjustment) value, while every mastro above is read from
    # the last (final) column.  Comparing those different columns rejects an
    # otherwise exact reconstruction (budget_588).  Do not use ``PAREGGIO`` here:
    # on a loss it includes the perdita parked on the attivo side, while the
    # gross asset mastri correctly reconcile to ``TOTALE ATTIVITA`` (343/348).
    final_attivi = []
    for words, is_sp, is_ce, _up, width in pages_data:
        if not is_sp or is_ce:
            continue
        split = _be_split(words) or width / 2
        for lo, hi in ((-1e9, split), (split, 1e9)):
            for row_words in _be_cluster_physical_rows(words, lo, hi):
                tokens = [w[4].strip() for w in row_words if w[4].strip()]
                caption = ' '.join(tokens).upper()
                if 'TOTALE' not in caption or 'ATTIVIT' not in caption:
                    continue
                amounts = [_parse_amount(token) for token in tokens
                           if _BE_AMT_RE.fullmatch(token)]
                if amounts and amounts[-1] > 0:
                    final_attivi.append(amounts[-1])

    tot_att = final_attivi[-1] if final_attivi else _ft(
        'TOTALE ATTIV', 'TOTALEATTIV')
    if not tot_att:
        # nessuna didascalia "TOTALE ATTIVITA'": il gestionale stampa il totale sulla riga
        # di sezione ("1 ATTIVITA' 2.303.519,78", budget_703)
        sezioni = [a for c, d, a in att
                   if len(c) == 1 and d.startswith('ATTIVIT') and 'PASSIV' not in d]
        tot_att = sezioni[0] if len(sezioni) == 1 else None
    if not tot_att or tot_att <= 0:
        return None
    tol = max(Decimal('50'), Decimal('0.005') * tot_att)
    # (1) gross attivo (net classified + fondi netted back) matches the declared total
    if abs((att_sum + netted) - tot_att) > tol:
        return None
    # (2) the SP result gap equals the CE result (ricavi - costi); otherwise the
    #     passivo composition is wrong and we must not trust the gap as sp13.
    ce_result = sum(ric_a for _c, _d, ric_a in mr) - sum(cos_a for _c, _d, cos_a in mc)
    if abs(sp13 - ce_result) > tol:
        return None

    bs['sp13'] = sp13
    bs['totale_attivo'] = att_sum
    bs['totale_passivo'] = att_sum
    bs['_plug_residual'] = Z
    # This result is independently corroborated by final-column SP controls and
    # the CE result.  Do not let the later generic declared-total reader replace
    # it with the first (pre-adjustment) column or interpret the adjustment/final
    # columns as a comparative year.
    bs['_skip_declared_reconcile'] = True
    return bs, ce
