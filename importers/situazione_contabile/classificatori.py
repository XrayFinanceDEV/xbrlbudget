"""Sezione di pagina e classificatori di conto per lato (attivo, passivo, costi, ricavi).

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import re
from typing import Dict, List, Optional, Tuple
from importers.situazione_contabile.fondi import (
    _FONDO_CATEGORY_KW, _fondo_is_immat, _is_fondo_amm,
)
from importers.situazione_contabile.regole import (
    _classify_ce_costi, _classify_ce_costi_foglia, _classify_ce_ricavi, _classify_ce_ricavi_foglia,
    _classify_sp_attivo, _classify_sp_passivo, _debt_type, _kw_any, _kw_match,
)
from importers.situazione_contabile.best_effort import (
    _be_amount,
)


def classify_page_section(page_text: str) -> Optional[Tuple[bool, bool]]:
    """(is_sp, is_ce) per una pagina di contrapposte, o None se la pagina va saltata.

    Estratta verbatim dal ciclo pagine di extract_contrapposte_best_effort perché il
    riscatto vision ha bisogno della stessa classificazione senza ri-eseguire l'intera
    estrazione. `None` significa "salta la pagina" (appendice fiscale di
    rideterminazione), che NON e' la stessa cosa di (False, False) — quest'ultima e'
    una pagina reale che non appartiene a nessuna sezione.
    """
    up = page_text.upper()
    flat = up.replace(' ', '')
    # Classify the page by its FIRST section title line — a single page may
    # carry a subtitle naming both ("Stato Patrimoniale e Conto Economico"),
    # so the title line that comes first decides.
    title = ''
    for l in page_text.split('\n'):
        lu = l.strip().upper()
        if 'PATRIMONIAL' in lu or 'ECONOMIC' in lu:
            title = lu
            break
    # Fiscal-reconciliation appendices ("RIDETERMINAZIONE RISULTATO D'ESERCIZIO"
    # for II.DD./IRAP, with VARIAZIONI IN AUMENTO/DIMINUZIONE) re-list cost/revenue
    # accounts but are NOT the income statement — skip them so they don't pollute
    # the CE (they otherwise match the loose COSTI+RICAVI test below).
    if ('RIDETERMINAZIONE' in flat or 'REDDITOIMPONIBILE' in flat
            or ('VARIAZIONIINAUMENTO' in flat and 'VARIAZIONIINDIMINUZIONE' in flat)):
        return None
    if 'PATRIMONIAL' in title and 'ECONOMIC' not in title:
        return True, False
    if 'ECONOMIC' in title and 'PATRIMONIAL' not in title:
        return False, True
    is_sp = ('PATRIMONIALE' in flat) or ('ATTIVIT' in up and 'PASSIVIT' in up and 'CONTOECONOMICO' not in flat)
    is_ce = ('CONTOECONOMICO' in flat) or ('COSTI' in up and 'RICAVI' in up)
    return is_sp, is_ce

def section_pages(file_path: str) -> Dict[str, List[int]]:
    """Indici pagina (0-based) che portano lo Stato Patrimoniale e il Conto Economico.

    Una pagina classificata come entrambe compare in entrambe le liste; una pagina da
    saltare (classify_page_section -> None) in nessuna.
    """
    out: Dict[str, List[int]] = {"sp": [], "ce": []}
    with fitz.open(file_path) as doc:
        for idx, page in enumerate(doc):
            verdict = classify_page_section(page.get_text())
            if verdict is None:
                continue
            is_sp, is_ce = verdict
            if is_sp:
                out["sp"].append(idx)
            if is_ce:
                out["ce"].append(idx)
    return out

# Classifiers map a mastro/subtotal DESCRIPTION to an IV-CEE field; the second
# element flags whether the match is specific enough to stop descending.
# Erano closure dentro extract_contrapposte_best_effort: promosse a funzioni di
# modulo perche' il riscatto vision (vision_rescue.py) classifica le stesse
# descrizioni senza ri-eseguire l'estrazione. Nessun cambiamento di regola.
# Il percorso di legge che alcuni gestionali stampano davanti alla descrizione del
# conto ("B) I) IMMOBILIZZAZ.IMMATERIALI", "A) 2) ESISTENZE INIZIALI", "4-TER) CRED.
# IMPOSTE ANTICIPATE": M.C.T. 30/06/2026). Non decide la voce — lo stesso gestionale
# scrive "B) F.DI AMMORTAM." al passivo, dove B) sarebbero i fondi rischi — ma copre le
# regole ancorate a inizio descrizione: si toglie, e decide la descrizione.
_PREFISSO_LEGALE = re.compile(
    r'^\s*(?:[A-E]\)\s*)?(?:[IVX]{1,4}\)\s*)?(?:\d{1,2}(?:\s*-\s*(?:BIS|TER|QUATER))?\)\s*)?')

_ABBREVIAZIONI = (
    (re.compile(r'\bIMMOBIL[A-Z]*\.\s*'), 'IMMOBILIZZAZIONI '),   # IMMOBILIZZAZ. / IMMOBILZZ.
    (re.compile(r'^F/A\s*-\s*'), 'F.DO AMM. '),                   # "F/A - Fabbricati industr."
    (re.compile(r'\bF\.DI\s+(?=(?:DI\s+|PER\s+)?(?:ALTRI\s+)?RISCHI)'), 'FONDI '),
    (re.compile(r'^F\.DI\s+(?=AMM)'), 'FONDI '),                    # "F.DI AMMORTAM. ORDINARIO"
    (re.compile(r'\bRAPPOR\.'), 'RAPPORTO'),
)

def _descrizione_di_conto(desc_upper: str) -> str:
    d = _PREFISSO_LEGALE.sub('', desc_upper, count=1).strip() or desc_upper
    for pattern, repl in _ABBREVIAZIONI:
        d = pattern.sub(repl, d)
    return d.strip()

def classify_attivo(desc_upper: str) -> Tuple[str, bool]:
    d = _descrizione_di_conto(desc_upper)
    # Some TeamSystem/ERP exports append the legal IV-CEE code after a run of
    # underscores (e.g. ``IMMOBILIZZAZIONI IMMATERIALI______BI``).  It is still
    # the explicit parent category, not an unknown generic caption: normalize
    # only these three exact suffixes so the hierarchy does not descend into
    # children and count the same mass again (AITEC 373/374/375).
    normalized = re.sub(r'_+(?:BIII|BII|BI)\s*$', '', d).strip()
    legal_parent = {
        'IMMOBILIZZAZIONI IMMATERIALI': 'sp02',
        'IMMOBILIZZAZIONI MATERIALI': 'sp03',
        'IMMOBILIZZAZIONI FINANZIARIE': 'sp04',
    }.get(normalized)
    if legal_parent:
        return legal_parent, True
    d = normalized
    # C.III "Attivita' finanziarie che non costituiscono immobilizzazioni" ("ATTIV.FIN.
    # NON IMMOBIL.", M.C.T. 30/06/2026: polizze e fondi assicurativi): contiene
    # IMMOBILIZZAZIONI e finiva fra le immobilizzazioni materiali, oltre il confine
    # dell'attivo circolante.
    if 'NON IMMOBILIZZ' in d or 'NON COSTIT' in d:
        return 'sp08', True
    # A malformed generic "IMMOBILIZZAZIONI ..." caption can accidentally
    # match MOBILI inside IMMOBILIZZAZIONI.  Descend to its specific children
    # (software/oneri pluriennali/etc.) unless the printed category is exact.
    if (d.startswith('IMMOBILIZZAZIONI')
            and d not in ('IMMOBILIZZAZIONI MATERIALI',
                          'IMMOBILIZZAZIONI IMMATERIALI',
                          'IMMOBILIZZAZIONI FINANZIARIE')):
        return 'sp06', False
    # Side is ground truth in a contrapposte layout: BANCHE on ATTIVO is cash,
    # not the generic-credit fallback used by the single-column classifier.
    if 'BANC' in d:
        return 'sp09', True
    # un conto corrente col suo numero e il solo nome della banca ("INTESA SANPAOLO C/C
    # 1000/2800", budget_435), stampato all'attivo: e' liquidita'
    if re.search(r'\bC/C\s*(?:N\.?\s*)?\d', d) and not _kw_any(d, ['CRED', 'ERARIO', 'DEBIT']):
        return 'sp09', True
    if ('SCORTE' in d or 'MATERIE PRIME' in d or d == 'IMBALLAGGI'):
        return 'sp05', True
    f = _classify_sp_attivo(d)
    f = {'gross_sp02': 'sp02', 'gross_sp03': 'sp03', 'gross_sp04': 'sp04'}.get(f, f)
    # Un credito non e' mai un cespite: "Crediti vs. Ad Immobiliare" prendeva la regola
    # MOBILI (mobili e arredi) dentro IMMOBILIARE (M.C.T. 30/06/2026).
    if f in ('sp02', 'sp03') and d.startswith('CRED'):
        return 'sp06', False
    return f, f != 'sp06'

def _tributari_e_previdenza(d: str) -> bool:
    return bool(re.search(r'\bTRIB|ERARI', d)) and _kw_any(d, ['PREV', 'INPS', 'INAIL'])

def classify_passivo(desc_upper: str) -> Tuple[str, bool]:
    d = _descrizione_di_conto(desc_upper)
    if _is_fondo_amm(d):
        field = 'depr_sp02' if _fondo_is_immat(d) else 'depr_sp03'
        # A category-blind aggregate must descend into children; any uncovered
        # residual is retained by _be_reclassify under the material fallback.
        specific = any(k in d for k in _FONDO_CATEGORY_KW)
        return field, specific
    tag = _classify_sp_passivo(d)
    if tag == 'equity_total':
        # "CAPITALE E RISERVE" e' una testa di due voci diverse: si scende nei figli
        # (capitale sociale -> sp11, riserve -> sp12), e cio' che non coprono resta riserva.
        # Fermarsi li' metteva la riserva legale nel capitale (budget_590, Unicarton).
        if re.search(r'CAPITALE(?:\s+SOCIALE)?\s+E\s+RISERV', d) or 'PATRIMONIO NETTO' in d:
            # anche "PATRIMONIO NETTO": capitale, riserve e utili sotto lo stesso mastro
            # (Napolitano 30/09/2026: il capitale sociale finiva nelle riserve, sp11 = 0)
            return 'sp12', False
        if _kw_match(d, ['CAPITALE']):
            return 'sp11', True
        return 'sp12', True
    if tag in ('sp16', 'debt_bank', 'bank_avere'):
        # Split debiti by OIC creditor type from the description (banche / fornitori /
        # tributari / previdenza / ...) instead of collapsing everything into the sp16
        # aggregate (which the UI then renders entirely under "altri debiti"). 'debt_bank'
        # /'bank_avere' are already bank lines; otherwise read _debt_type. A recognised
        # type stops the descent; an unknown ('g') keeps descending to find a typed child.
        letter = ('a' if tag in ('debt_bank', 'bank_avere') or 'BANC' in d
                  else _debt_type(d.upper()))
        # Una testa generica di finanziamenti senza "banca" ("FINANZIAMENTI DI TERZI",
        # "MUTUI E FINANZIAMENTI", budget_590) contiene anche il finanziamento soci: si
        # scende nei figli, e cio' che non coprono resta banca come prima.
        # Anche "DEBITI VARI DI FINANZIAMENTO" (Napolitano 30/09/2026): sotto ci sono i
        # debiti verso dipendenti, e da mastro specifico finivano tutti in banca.
        if (letter == 'a' and 'BANC' not in d
                and _kw_any(d, ['FINANZIAMENTI DI TERZI', 'MUTUI E FINANZIAMENTI',
                                'VARI DI FINANZ', 'DIVERSI DI FINANZ'])):
            return 'sp16a', False
        # Un mastro che nomina due voci, tributari E previdenza ("DEB.TRIB.-ISTIT.PREV.SOCIALE_
        # D12_D13", budget_1784), non e' di nessuna delle due: si scende nei conti, e l'IVA va
        # nei tributari invece di finire coi contributi.
        if _tributari_e_previdenza(d):
            return 'sp16g', False
        return 'sp16' + letter, letter != 'g'
    return tag, tag != 'sp16'

def classify_costi(desc_upper: str) -> Tuple[str, bool]:
    d = _descrizione_di_conto(desc_upper)
    f = _classify_ce_costi(d)
    return (f, True) if f else (_classify_ce_costi_foglia(d) or 'ce12', False)

def classify_ricavi(desc_upper: str) -> Tuple[str, bool]:
    d = _descrizione_di_conto(desc_upper)
    f = _classify_ce_ricavi(d)
    return (f, True) if f else (_classify_ce_ricavi_foglia(d) or 'ce04', False)

def _be_split_sp_ce_page(words):
    """Una pagina che si apre con lo STATO PATRIMONIALE e, chiusi i suoi totali, apre
    il CONTO ECONOMICO a meta' pagina: restituisce (parole_sp, parole_ce), divise alla
    riga del titolo «CONTO ECONOMICO»; None se la pagina non e' cosi'.

    Il titolo della pagina decide la sezione di TUTTA la pagina, quindi i mastri di
    costo e ricavo sotto il titolo finivano fra attivo e passivo. Si divide solo se
    sopra il titolo la sezione patrimoniale ha gia' chiuso (pareggio/quadratura o
    totale attivita' e passivita'), cosi' una didascalia qualunque che nomini il
    conto economico non taglia una pagina a meta'."""
    rows: Dict[int, list] = {}
    for w in words:
        rows.setdefault(round((w[1] + w[3]) / 2), []).append(w)
    ce_y = None
    sp_titolo = False       # una riga che APRE con "STATO/SITUAZIONE PATRIMONIALE", sopra
    for y in sorted(rows):
        toks = [w[4].upper() for w in sorted(rows[y], key=lambda w: w[0])]
        line = re.sub(r'\s+', '', ''.join(toks))
        if line.startswith('CONTOECONOMICO'):
            ce_y = y
            break
        if line.startswith(('STATOPATRIMONIALE', 'SITUAZIONEPATRIMONIALE')):
            sp_titolo = True
    if ce_y is None:
        return None
    sopra = [w for w in words if (w[1] + w[3]) / 2 < ce_y - 1]
    sotto = [w for w in words if (w[1] + w[3]) / 2 >= ce_y - 1]
    testo_sopra = re.sub(r'\s+', '', ''.join(w[4] for w in sopra).upper())
    sp_chiuso = 'PATRIMONIAL' in testo_sopra and (
        'PAREGGIO' in testo_sopra or 'QUADRATURA' in testo_sopra
        or ('TOTALEATTIV' in testo_sopra and 'TOTALEPASSIV' in testo_sopra))
    # Due titoli di sezione, ciascuno in apertura della propria riga, SP sopra e CE sotto,
    # bastano anche senza totali di chiusura stampati (budget_367: "STATO PATRIMONIALE"
    # in testa, poi "CONTO ECONOMICO" a meta' pagina con le sue colonne).
    if not (sp_chiuso or sp_titolo):
        return None
    if not sotto or not any(_be_amount(w[4]) is not None for w in sotto):
        return None
    return sopra, sotto
