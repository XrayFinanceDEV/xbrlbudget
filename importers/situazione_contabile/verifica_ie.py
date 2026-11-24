"""Bilancio di verifica a colonna unica con i marcatori IE/E.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import re
from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from importers.situazione_contabile.fondi import (
    _FONDO_MAT_KW,
)
from importers.situazione_contabile.comune import (
    Entry, _parse_amount,
)
from importers.situazione_contabile.regole import (
    _SP_ATTIVO_RULES, _SP_PASSIVO_RULES, _canon_fondo_amm, _classify_ce_costi, _classify_ce_ricavi, _kw_match,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.situazione_contabile_parser")


# ---------------------------------------------------------------------------
# Bilancio di verifica a colonna unica con marcatori IE/E (budget_680, FTC Srl).
# Una riga per conto: codice (sezione a 2 cifre, mastro a 4-5 cifre a sinistra,
# conto a 5 cifre rientrato), descrizione, poi cinque colonne numeriche - saldo
# d'apertura, dare, avere, saldo del periodo, saldo finale - ciascun saldo col
# suo segno D/A. Il marcatore "IE"/"E" sta all'estrema destra.
# ---------------------------------------------------------------------------

_IE_AMT_RE = re.compile(r'^\d{1,3}(?:\.\d{3})*,\d{2}$')

_IE_SEZIONI = {'01': 'attivo', '02': 'passivo', '03': 'costi', '04': 'ricavi'}

# Le sole voci di CE che un mastro puo' prestare a un conto che nessuna regola riconosce:
# restano sopra l'EBITDA. "ONERI FINANZIARI" con dentro assicurazioni e canoni non deve
# trascinarli in ce15 (confine di KPI): il conto va nel ripiego neutro.
_IE_CE_OPERATIVE = ('ce05', 'ce06', 'ce07', 'ce08', 'ce12', 'ce01', 'ce04', 'ce10')

def is_verifica_ie(text: str) -> bool:
    """Verifica a colonna unica con marcatori di riga "IE" (mastro) / "E" (conto) e le
    colonne "Saldo Periodo" / "Saldo al"."""
    if not re.search(r'BILANCIO\s+DI\s+VERIFICA', text, re.IGNORECASE):
        return False
    if 'Saldo Periodo' not in text or 'Saldo al' not in text:
        return False
    return (len(re.findall(r'(?m)^IE\s*$', text)) >= 3
            and len(re.findall(r'(?m)^E\s*$', text)) >= 5)

def _regola_sp(desc_upper: str, lato: str) -> Optional[str]:
    """La voce di SP che una descrizione riconosce davvero, o None se nessuna regola la
    nomina (i classificatori ripiegano allora su crediti/debiti generici)."""
    if lato == 'attivo':
        d = re.sub(r'\bRIM\.(?=\s|$|[A-Z])', 'RIMANENZE ', desc_upper)
        regole = _SP_ATTIVO_RULES
    else:
        d = _canon_fondo_amm(desc_upper)
        regole = _SP_PASSIVO_RULES
    for keywords, field in regole:
        if _kw_match(d, keywords):
            return field
    return None

def _ie_risultato_in_apertura(bs: Dict[str, Decimal], entries: List[Entry],
                              differenza: Decimal) -> Dict[str, Decimal]:
    """Verifica progressiva (saldo al 31/12 dell'anno prima + dare - avere = saldo finale):
    se la colonna d'apertura ha solo stato patrimoniale e non pareggia, e lo sbilancio della
    colonna finale e' esattamente la stessa cifra, i movimenti dell'anno pareggiano e lo
    sbilancio e' il risultato dell'anno prima che le scritture d'apertura non hanno riaperto
    (budget_680: perdita 2025 di 348.287,23, conto "PERDITA D'ESERCIZIO" vuoto in ogni
    colonna). Va negli utili (perdite) portati a nuovo e si dichiara (decisione del
    proprietario, 2026-10-15). Due controlli stampati che coincidono al centesimo, nessun
    importo inventato; altrimenti il foglio resta sbilanciato e lo dichiara."""
    ap = {e.section: e.amount for e in entries if e.level == 6}
    tol = Decimal('0.05')
    if abs(differenza) <= tol or 'attivo' not in ap or 'passivo' not in ap:
        return bs
    if ap.get('costi') or ap.get('ricavi'):
        return bs                      # un'apertura con il conto economico non e' questo caso
    apertura = ap['attivo'] + ap['passivo']          # D+ / A-: zero se pareggia
    if abs(apertura - differenza) > tol:
        return bs
    new_bs = dict(bs)
    for k in ('sp12', 'sp12g_utili_perdite_portati'):
        new_bs[k] = (new_bs.get(k) or Decimal('0')) + differenza
    new_bs['totale_passivo'] = (new_bs.get('totale_passivo') or Decimal('0')) + differenza
    new_bs['_risultato_anno_prima_apertura'] = differenza
    new_bs['_apertura_attivo'] = ap['attivo']
    new_bs['_apertura_passivo'] = -ap['passivo']
    logger.warning(f"Verifica IE/E: risultato dell'anno prima non riaperto {differenza:,.2f} "
                   f"(colonna d'apertura e saldo finale sbilanciati della stessa cifra)")
    return new_bs

def parse_entries_verifica_ie(file_path: str) -> List[Entry]:
    """Le foglie (conti) della verifica, una ``Entry`` di livello 0 ciascuna, col saldo
    FINALE. Nello SP il lato lo decide il segno D/A del saldo (la colonna e' la verita'
    sul lato): un conto bancario a saldo avere e' un debito, un rateo passivo a saldo
    dare sta all'attivo. Nel CE la sezione resta quella stampata e l'importo e' firmato.
    La voce la decide la descrizione del conto; nello SP, quando il conto porta un nome
    (clienti, fornitori) e nessuna regola lo riconosce, quella del suo mastro. Nel CE
    mai quella del mastro: i mastri raggruppano per abitudine del gestionale ("ONERI
    FINANZIARI" con assicurazioni e canoni) e attraverserebbero il confine dell'EBIT.

    Si verifica sui totali stampati di sezione e sul risultato: se le foglie lette non
    li ricostruiscono al centesimo la lettura e' vuota (mai una lettura non verificata).
    """
    doc = fitz.open(file_path)
    righe = []                                   # (livello, codice, descrizione, saldo firmato)
    utili = set()
    try:
        for page in doc:
            per_y: Dict[int, list] = {}
            for w in page.get_text('words'):
                per_y.setdefault(round((w[1] + w[3]) / 2), []).append(w)
            for y in sorted(per_y):
                ws = sorted(per_y[y], key=lambda w: w[0])
                testo = ' '.join(w[4] for w in ws)
                m = re.search(r'(UTILE|PERDITA)\s+(?:D\'\s*)?ESERCIZIO\s*:\s*(' + _IE_AMT_RE.pattern[1:-1] + ')', testo)
                if m:
                    v = _parse_amount(m.group(2))
                    utili.add(v if m.group(1) == 'UTILE' else -v)
                    continue
                codici = [w for w in ws if re.fullmatch(r'\d{2,5}', w[4]) and w[0] < 80]
                if not codici:
                    continue
                c = codici[0]
                livello = 'sezione' if len(c[4]) == 2 else ('mastro' if c[0] < 30 else 'conto')
                finali = [w for w in ws if _IE_AMT_RE.match(w[4]) and 720 < w[2] <= 780]
                segni = [w[4] for w in ws if w[4] in ('D', 'A') and 776 < w[0] < 790]
                if len(finali) > 1 or len(segni) > 1:
                    raise ValueError(f"riga ambigua a pagina {page.number + 1}: {testo[:80]}")
                saldo = None
                if finali:
                    if not segni:
                        raise ValueError(f"saldo senza segno a pagina {page.number + 1}: {testo[:80]}")
                    saldo = _parse_amount(finali[0][4]) * (1 if segni[0] == 'D' else -1)
                desc = ' '.join(w[4] for w in ws if 75 < w[0] < 400)
                apertura = None
                if livello == 'sezione':
                    # colonna "Saldo al 31/12 dell'anno prima" (importo fino a x 460, segno dopo)
                    ap = [w for w in ws if _IE_AMT_RE.match(w[4]) and 400 < w[2] <= 460]
                    sg = [w[4] for w in ws if w[4] in ('D', 'A') and 460 < w[0] < 472]
                    if len(ap) == 1 and len(sg) == 1:
                        apertura = _parse_amount(ap[0][4]) * (1 if sg[0] == 'D' else -1)
                righe.append((livello, c[4], desc, saldo, apertura))
    finally:
        doc.close()
    return _entries_da_righe_verifica(righe, utili, "Verifica IE/E")

def _entries_da_righe_verifica(righe: list, utili: set, nome: str) -> List[Entry]:
    """Dalle righe di una verifica a colonna unica - ``(livello, codice, descrizione, saldo
    firmato D+/A-, apertura)``, livello ``sezione``/``mastro``/``conto``, sezione col codice di
    ``_IE_SEZIONI`` - le ``Entry`` classificate, verificate sui totali stampati di sezione e sul
    risultato (``utili``: i risultati stampati, uno solo). Lista vuota se non tornano."""
    sezione = None
    mastro_desc = ''
    totali: Dict[str, Decimal] = {}
    aperture: Dict[str, Decimal] = {}
    foglie: Dict[str, Decimal] = defaultdict(Decimal)
    mastri: Dict[Tuple[str, str], Optional[Decimal]] = {}
    descrizioni_mastro: Dict[Tuple[str, str], str] = {}
    con_foglie: set = set()
    entries: List[Entry] = []
    mastro = None
    for livello, codice, desc, saldo, apertura in righe:
        if livello == 'sezione':
            sezione = _IE_SEZIONI.get(codice)
            if sezione and saldo is not None:
                totali[sezione] = saldo
            if sezione and apertura is not None:
                aperture[sezione] = apertura
            continue
        if sezione is None:
            continue
        if livello == 'mastro':
            mastro, mastro_desc = codice, desc
            descrizioni_mastro[(sezione, codice)] = desc
            if saldo is not None:
                mastri[(sezione, codice)] = saldo
            else:
                mastri.setdefault((sezione, codice), None)
            continue
        if saldo is None or saldo == 0:
            continue
        con_foglie.add((sezione, mastro))
        foglie[sezione] += saldo
        du = desc.upper()
        if sezione in ('attivo', 'passivo'):
            lato = 'attivo' if saldo > 0 else 'passivo'
            saldo_mastro = mastri.get((sezione, mastro))
            dal_mastro = _regola_sp(mastro_desc.upper(), lato)
            # un fondo ammortamento senza il nome del suo cespite ("F.DO AMM. MAN.E RIP.BENI
            # TERZI", "MIGLIORIE FABBR.TERZ", "PROCEDURE ELABOR.") cade nel default dei fondi
            # materiali anche sotto un mastro che dice "IMMATER.": la massa passava da sp02
            # a sp03 (COLOMBO, 88.776,72), attraversando un aggregato. Il mastro vince, e il
            # conto tiene le sue parole per il dettaglio.
            # Solo se il mastro nomina davvero la categoria immateriale: "COSTI UTILIZZO
            # PLURIENNALI" (budget_680) e' un contenitore dove stanno anche fabbricati e hardware,
            # e li' le parole del conto decidono.
            if (sezione == 'passivo' and lato == 'passivo' and dal_mastro == 'depr_sp02'
                    and any(k in mastro_desc.upper() for k in (
                        'IMMAT', 'INGEGNO', 'BREVETT', 'LICENZ', 'MARCHI', 'SOFTWARE',
                        'CONCESS', 'AVVIAMENT'))
                    and _regola_sp(du, lato) == 'depr_sp03'
                    and not any(k in du for k in _FONDO_MAT_KW)):
                du = mastro_desc.upper() + ' ' + du
            # il mastro presta la descrizione solo a un conto che sta dal suo lato: un
            # rateo passivo a saldo dare sotto "IMMOBILIZZI PASSIVI" non e' un cespite. Dal
            # suo lato vuol dire nella sezione del mastro, o col segno del suo saldo; una
            # banca resta una banca da tutti e due i lati (Santini: BPER a saldo dare sotto
            # "BANCHE", che nel complesso e' a saldo avere)
            if (_regola_sp(du, lato) is None and dal_mastro is not None
                    and (lato == sezione
                         or (saldo_mastro and (saldo_mastro > 0) == (saldo > 0))
                         or dal_mastro in ('sp09', 'debt_bank'))):
                du = mastro_desc.upper()
            # sotto un mastro di controparti il conto porta un nome di azienda, non una
            # voce: "MANTERO SETA SPA DIV.LICENZE" sotto CLIENTI non e' una licenza
            elif re.search(r'\b(CLIENTI|FORNITORI|DEBITORI|CREDITORI)\b', mastro_desc.upper()):
                du = mastro_desc.upper()
            # la scadenza la dichiara il mastro ("DEBITI V/FINANZ.ESIG.OLTRE 12M"), non il conto
            # ("MUTUO CHIROGRAFARIO B.P.S."): senza, il debito oltre l'esercizio cadeva a breve
            if (sezione == 'passivo' and lato == 'passivo' and 'OLTRE' in mastro_desc.upper()
                    and 'OLTRE' not in du and 'ENTRO' not in du and '(OE)' not in du):
                du = du + ' OLTRE'
            if (sezione == 'passivo' and lato == 'attivo'
                    and _regola_sp(du, 'passivo') == 'equity_total'):
                # una riserva a saldo dare resta nel patrimonio, in negativo (riserva per
                # operazioni di copertura, Santini): non e' un credito
                entries.append(Entry(code=codice, description=du, amount=-saldo,
                                     level=0, section='passivo'))
                continue
            entries.append(Entry(code=codice, description=du, amount=abs(saldo),
                                 level=0, section=lato))
        else:
            importo = saldo if sezione == 'costi' else -saldo
            classifica = _classify_ce_costi if sezione == 'costi' else _classify_ce_ricavi
            dal_mastro = classifica(mastro_desc.upper())
            if (classifica(du) is None and dal_mastro
                    and dal_mastro.startswith(_IE_CE_OPERATIVE)):
                du = mastro_desc.upper()
            entries.append(Entry(code=codice, description=du, amount=importo,
                                 level=0, section=sezione))
    # un mastro senza conti sotto vale da se'
    for (sez, cod), saldo in mastri.items():
        if (sez, cod) in con_foglie or not saldo:
            continue
        foglie[sez] += saldo
        # con la sua descrizione ("CLIENTI WEB", "FORNITORI ITALIA" senza conti stampati)
        desc_m = descrizioni_mastro.get((sez, cod), '').upper()
        if sez in ('attivo', 'passivo'):
            entries.append(Entry(code=cod, description=desc_m, amount=abs(saldo), level=0,
                                 section='attivo' if saldo > 0 else 'passivo'))
        else:
            entries.append(Entry(code=cod, description=desc_m, amount=saldo if sez == 'costi' else -saldo,
                                 level=0, section=sez))

    tol = Decimal('0.05')
    for sez in ('attivo', 'passivo', 'costi', 'ricavi'):
        if sez not in totali or abs(foglie[sez] - totali[sez]) > tol:
            logger.warning(f"{nome}: la sezione {sez} non ricostruisce il totale stampato "
                           f"({foglie[sez]} contro {totali.get(sez)}): lettura scartata")
            return []
    risultato = -(totali['costi'] + totali['ricavi'])       # ricavi in avere, firmati negativi
    if len(utili) != 1 or abs(next(iter(utili)) - risultato) > tol:
        logger.warning(f"{nome}: il risultato stampato non torna con costi e ricavi: lettura scartata")
        return []
    entries.append(Entry(code='', description="UTILE D'ESERCIZIO", amount=risultato,
                         level=4, section='ricavi'))
    # i totali di sezione stampati (livello 3: build_iv_cee li ignora), per dichiarare un
    # documento che non pareggia da solo
    for sez in ('attivo', 'passivo', 'costi', 'ricavi'):
        entries.append(Entry(code='', description=f'TOTALE {sez.upper()}',
                             amount=abs(totali[sez]), level=3, section=sez))
    # i totali d'apertura stampati (livello 6: build_iv_cee li ignora), firmati D+ / A-
    for sez, v in aperture.items():
        entries.append(Entry(code='', description=f'APERTURA {sez.upper()}',
                             amount=v, level=6, section=sez))
    logger.info(f"{nome}: {len(entries) - 1} conti, totali di sezione e risultato "
                f"ricostruiti al centesimo")
    return entries
