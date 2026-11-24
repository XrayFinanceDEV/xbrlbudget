"""SP e CE dalle righe lette in vision; anno precedente dalle righe.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import logging
from dataclasses import replace
from decimal import Decimal
from typing import Dict, List, Tuple
from importers.situazione_contabile.comune import (
    Entry,
)
from importers.situazione_contabile.regole import (
    _ATTIVO_KEYS, _CE_SUBFIELD_PARENT, _DEBT_FIELD, _PASSIVO_KEYS, _resolve_ce_field, fallback_bucket,
    fallback_field,
)
from importers.situazione_contabile.iv_cee import (
    build_iv_cee,
)
from importers.situazione_contabile.classificatori import (
    classify_attivo, classify_costi, classify_passivo, classify_ricavi,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.situazione_contabile_parser")


def build_sp_from_vision(rows, utile: Decimal) -> Dict[str, Decimal]:
    """Monta lo Stato Patrimoniale da righe MASTRO piatte lette in vision.

    `rows` = [(codice, descrizione, importo, colonna)], colonna in {'left','right'}.
    La colonna e' verita' sul lato (FIXING-IMPORT.md §1.3); la descrizione decide la
    voce. `utile` e' il risultato LETTO dal documento, non derivato qui: questa
    funzione non inventa il pareggio.

    Le righe sono gia' al livello mastro, quindi non passano da _be_reclassify (che
    serve a scegliere fra padre e figli in una gerarchia): ogni riga vale per se'.
    Chiavi corte come il best-effort — il chiamante applica _map_sc_keys.

    Dichiara sempre `_unclassified_mass`: la massa letta ma finita in un secchio
    generico (sopra la soglia di materialita') piu' l'eccedenza tagliata dal clamp
    sulle immobilizzazioni negative. Zero e' un'affermazione, non un'assenza.
    """
    Z = Decimal('0')
    bs: Dict[str, Decimal] = {}
    netted = Z
    # Massa LETTA ma non riconosciuta: la riga e' finita in un secchio generico
    # (sp06 sull'attivo, sp16 sul passivo) perche' il classificatore non ha saputo
    # dire di piu'. Si accumula qui e si pesa in fondo, quando il totale esiste.
    unclassified: List[Tuple[str, Decimal]] = []

    def add(k, v):
        bs[k] = bs.get(k, Z) + v

    for _code, desc, amount, column in rows:
        d = (desc or '').upper()
        if column == 'left':
            field, _specific = classify_attivo(d)
            if not _specific:
                unclassified.append((d, amount))
            add({'gross_sp02': 'sp02', 'gross_sp03': 'sp03',
                 'gross_sp04': 'sp04'}.get(field, field), amount)
            continue
        tag, _specific = classify_passivo(d)
        if not _specific:
            unclassified.append((d, amount))
        if tag in ('depr_sp02', 'depr_sp03', 'depr_sp04'):
            add(tag.replace('depr_', ''), -amount)     # netta il fondo dall'attivo
            netted += amount
        elif tag == 'deduct_crediti':
            add('sp06', -amount)
            netted += amount
        elif tag in ('sp11', 'sp12', 'sp14', 'sp15', 'sp18'):
            add(tag, amount)
        elif len(tag) == 5 and tag.startswith('sp16') and tag[4] in 'abcdefg':
            add('sp16', amount)                        # aggregato: pareggio invariato
            add(_DEBT_FIELD['breve'][tag[4]], amount)  # tipizzato, nome pieno
        else:
            add('sp16', amount)

    # Un fondo non puo' mai superare il proprio cespite lordo: un'immobilizzazione
    # netta negativa e' sempre una misclassificazione. Il cancello vedra' il divario.
    # La correzione pero' deve PARLARE: sp02/sp03/sp04 sono TIER0_FIELDS, e azzerare
    # in silenzio un valore negativo trasforma una contraddizione in un numero
    # plausibile. L'eccedenza tagliata e' massa che non si e' saputa collocare, quindi
    # va nello stesso canale del resto: _unclassified_mass.
    clamped = Z
    for k in ('sp02', 'sp03', 'sp04'):
        if bs.get(k, Z) < Z:
            clamped += -bs[k]
            logger.warning(
                f"Riscatto vision: {k} negativo ({bs[k]}) — il fondo supera il cespite "
                f"lordo, azzerato; {-bs[k]} di massa non collocata (verificare in "
                f"Rettifiche)")
            bs[k] = Z

    bs['sp13'] = utile
    bs['_netted_contra'] = netted
    # Il riscatto legge i mastri, non la scadenza: nessun conto dice se un debito e'
    # entro o oltre l'esercizio, quindi finiscono tutti a breve. Non e' un errore da
    # nascondere — sp16 e sp17 stanno entrambi nel passivo, quindi il pareggio non
    # se ne accorge, ma CCN, current ratio e il termine di capitale circolante di
    # Altman si'. Stessa bandiera che alzano standard_ivcee_parser e mineru_adapter.
    bs['_source_maturity_unspecified'] = Decimal('1')
    bs['totale_attivo'] = sum((bs.get(k, Z) for k in _ATTIVO_KEYS), Z)
    bs['totale_passivo'] = sum((bs.get(k, Z) for k in _PASSIVO_KEYS), Z)
    bs['_plug_residual'] = Z
    # Massa non collocata, DICHIARATA anche quando e' zero: reliability.assess legge
    # questa chiave, e una chiave assente li' vale zero — cioe' un foglio riscattato
    # si dichiarerebbe pulito solo perche' questo montatore non ha un secchio. Sopra
    # la soglia di materialita' si conta l'importo, sotto e' un'etichetta generica
    # legittima (stessa politica di fallback_bucket nel percorso best-effort);
    # l'eccedenza tagliata dal clamp si conta SEMPRE, perche' non e' un'etichetta
    # imprecisa ma una contraddizione contabile.
    material = clamped
    for _desc, _amt in unclassified:
        _field, _severity = fallback_bucket(_desc, 'bs', _amt, bs['totale_attivo'])
        if _severity == 'recorded':
            material += abs(_amt)
    bs['_unclassified_mass'] = material
    # Misurata, non assente: questo percorso SA quale massa letta e' finita in un
    # secchio generico, quindi lo zero qui significa «pulito» e non «non lo so».
    # reliability.assess distingue i due casi da questa chiave, e una chiave
    # assente vale «non misurato» — tacere non puo' valere come promessa.
    bs['_unclassified_mass_measured'] = Decimal('1')
    return bs

def build_ce_from_vision(rows) -> Dict[str, Decimal]:
    """Monta il Conto Economico da righe MASTRO piatte lette in vision.

    La colonna decide la DIREZIONE (sinistra = costi, destra = ricavi) e la direzione
    vincola la risoluzione: _resolve_ce_field rifiuta una voce del segno opposto, cosi'
    un costo non puo' finire su un nodo di ricavo (che sposterebbe il risultato di 2x).
    Ordine: tabella a parole chiave -> albero IV-CEE vincolato -> catch-all neutro.
    """
    Z = Decimal('0')
    ce: Dict[str, Decimal] = {}

    def add(k, v):
        ce[k] = ce.get(k, Z) + v

    for _code, desc, amount, column in rows:
        d = (desc or '').upper()
        direction = 'costi' if column == 'left' else 'ricavi'
        if direction == 'costi':
            tag, specific = classify_costi(d)
        else:
            tag, specific = classify_ricavi(d)
        if not specific:
            # La tabella a parole chiave non conosce questa descrizione: prova
            # l'albero condiviso, VINCOLATO alla direzione. iv_cee_hierarchy.resolve
            # non filtra per segno sui nodi CE — _resolve_ce_field si'.
            resolved = _resolve_ce_field(d, direction)
            # Ultimo ripiego, e va scelto per DIREZIONE. FALLBACK_FIELDS['ce'] e'
            # 'ce06': neutro per i KPI solo DENTRO i costi della produzione. Su una
            # riga della colonna RICAVI e' un COSTO, quindi la massa non riconosciuta
            # sposta il risultato di 2x il proprio importo — lo stesso errore che
            # _resolve_ce_field esiste per impedire. Su budget_624 ci finivano le
            # rimanenze finali e i proventi finanziari letti a destra (1.479.943,47):
            # il conto economico chiudeva a 0,00 invece che agli 8.906,79 stampati.
            # A destra si tiene il default del classificatore ('ce04'), che e' del
            # segno giusto: e' la stessa scelta che fa _be_reclassify con cl_ric sul
            # percorso deterministico, non una regola nuova.
            tag = resolved or (fallback_field('ce') if direction == 'costi' else tag)
        if tag == 'ce01_return':
            add('ce01', -amount)
        elif tag == 'ce10_close':
            add('ce10', -amount)
        elif tag == 'ce02_open':
            add('ce02', -amount)
        elif tag == 'ce13_cost':
            add('ce15', amount)
        elif tag in _CE_SUBFIELD_PARENT:
            detail, parent = _CE_SUBFIELD_PARENT[tag]
            add(parent, amount)
            add(detail, amount)
        else:
            add(tag, amount)
    return ce

def _build_prior_from_entries(entries: List[Entry], default_ce: bool):
    """Build a prior-year (BS, CE) from the second amount column of a dual-year
    trial balance, or (None, None) when there is no usable prior column.

    Dual-year DEPI files carry two saldi per line (corrente, precedente). The
    parser stores the prior saldo in Entry.amount_prior; here we re-run the
    SAME IV-CEE mapping on the prior column and keep it only if it is non-empty
    and balances (Attivo == Passivo within €1) — a single-column file has all
    amount_prior == 0, so this returns (None, None) and nothing changes.
    """
    if not any((e.amount_prior or Decimal('0')) != 0 for e in entries):
        return None, None
    prior_entries = [replace(e, amount=(e.amount_prior or Decimal('0'))) for e in entries]
    prior_bs, prior_ce = build_iv_cee(prior_entries, default_ce=default_ce)
    ta = prior_bs.get('totale_attivo') or Decimal('0')
    tp = prior_bs.get('totale_passivo') or Decimal('0')
    if ta <= 0 or abs(ta - tp) > Decimal('1'):
        logger.info(f"Prior-year column unusable (attivo={ta}, passivo={tp}) — skipping")
        return None, None
    logger.info(f"Prior-year column extracted (totale_attivo={ta})")
    return prior_bs, prior_ce
