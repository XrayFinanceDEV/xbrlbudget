"""Bilancio di verifica a «Totale Sub / Totale Mastro».

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import re
from decimal import Decimal
from typing import Dict, List
from importers.situazione_contabile.comune import (
    Entry, _parse_amount,
)
from importers.situazione_contabile.verifica_ie import (
    _entries_da_righe_verifica,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.situazione_contabile_parser")


# ---------------------------------------------------------------------------
# Bilancio di verifica a "Totale Sub / Totale Mastro" (budget_1343, "BILANCIO PROVVISORIO",
# piede "C44-1.0"): conto "NN NNNNNNN", importo del conto nella colonna "Totale Sub", sotto i
# conti la riga del mastro con lo STESSO codice dell'ultimo conto e l'importo nella colonna
# "Totale Mastro"; il segno meno in coda ("16.759,69-"). Una pagina per sezione, nominata
# nell'intestazione di colonna (Attivita' / Passivita' / Ricavi / Costi); in fondo TOTALE
# <SEZIONE>, DIFFERENZA D'ESERCIZIO e TOTALE A PAREGGIO.
# ---------------------------------------------------------------------------

_VS_AMT = re.compile(r'^\d{1,3}(?:\.\d{3})*,\d{2}-?$')

_VS_SEZIONI = {"ATTIVITA'": ('01', 1), "PASSIVITA'": ('02', -1), 'COSTI': ('03', 1), 'RICAVI': ('04', -1)}

def is_verifica_sub_mastro(text: str) -> bool:
    if 'Totale Sub' not in text or 'Totale Mastro' not in text:
        return False
    if 'TOTALE A PAREGGIO' not in text or "DIFFERENZA D'ESERCIZIO" not in text:
        return False
    return len(re.findall(r'(?m)^\d{2} \d{7}$', text)) >= 20

def _vs_importo(testo: str) -> Decimal:
    v = _parse_amount(testo.rstrip('-'))
    return -v if testo.endswith('-') else v

def parse_entries_verifica_sub_mastro(file_path: str) -> List[Entry]:
    """Le righe della verifica "Totale Sub / Totale Mastro", nella forma di
    ``_entries_da_righe_verifica``: ogni mastro deve tornare con i suoi conti, ogni sezione col
    suo TOTALE, e la DIFFERENZA D'ESERCIZIO deve pareggiare sia lo SP sia il CE (dal lato
    passivita'/costi e' un utile, dal lato attivita'/ricavi una perdita)."""
    doc = fitz.open(file_path)
    righe: list = []
    totali: Dict[str, Decimal] = {}
    pareggi: Dict[str, Decimal] = {}
    differenze: Dict[str, Decimal] = {}
    tol = Decimal('0.05')
    try:
        sezione = None
        segno = 1
        conti: list = []                       # conti in attesa della riga del loro mastro
        for page in doc:
            per_y: Dict[int, list] = {}
            for w in page.get_text('words'):
                per_y.setdefault(round((w[1] + w[3]) / 2), []).append(w)
            for y in sorted(per_y):
                ws = sorted(per_y[y], key=lambda w: w[0])
                testo = ' '.join(w[4] for w in ws)
                parole = [w[4] for w in ws]
                if parole[:2] == ['Conto', 'Descrizione']:
                    nome = next((w.upper() for w in parole if w.upper() in _VS_SEZIONI), None)
                    if nome is None:
                        raise ValueError(f"intestazione senza sezione a pagina {page.number + 1}")
                    if nome != sezione:
                        sezione = nome
                        codice_sez, segno = _VS_SEZIONI[nome]
                        righe.append(['sezione', codice_sez, nome, None, None])
                    continue
                importi = [w for w in ws if _VS_AMT.match(w[4])]
                m = re.match(r"^(TOTALE A PAREGGIO|DIFFERENZA D'ESERCIZIO|TOTALE (?:ATTIVITA'|PASSIVITA'|RICAVI|COSTI))\s", testo)
                if m and sezione:
                    if len(importi) != 1:
                        raise ValueError(f"totale senza importo: {testo[:60]}")
                    v = _vs_importo(importi[0][4])
                    if m.group(1) == 'TOTALE A PAREGGIO':
                        pareggi[sezione] = v
                    elif m.group(1).startswith('DIFFERENZA'):
                        differenze[sezione] = v
                    else:
                        totali[sezione] = v
                    continue
                if sezione is None or len(ws) < 3:
                    continue
                if not (re.fullmatch(r'\d{2}', ws[0][4]) and re.fullmatch(r'\d{7}', ws[1][4])):
                    continue
                codice = f"{ws[0][4]}{ws[1][4]}"
                desc = ' '.join(w[4] for w in ws[2:] if w not in importi)
                if len(importi) > 1:
                    raise ValueError(f"riga con due importi a pagina {page.number + 1}: {testo[:60]}")
                if not importi:
                    continue                    # conto (o mastro) a zero
                v = _vs_importo(importi[0][4])
                if importi[0][2] < 450:
                    conti.append(['conto', codice, desc, v * segno, None])
                    continue
                somma = sum((c[3] for c in conti), Decimal('0')) * segno
                if conti and abs(somma - v) > tol:
                    logger.warning(f"Verifica Sub/Mastro: il mastro {desc[:40]} ({v}) non torna con "
                                   f"i suoi conti ({somma}): lettura scartata")
                    return []
                righe.append(['mastro', codice[:2], desc, v * segno, None])
                righe.extend(conti)
                conti = []
        if conti:
            logger.warning("Verifica Sub/Mastro: conti senza la riga del loro mastro: lettura scartata")
            return []
    finally:
        doc.close()

    if set(totali) != set(_VS_SEZIONI) or len(differenze) != 2:
        logger.warning("Verifica Sub/Mastro: totali di sezione incompleti: lettura scartata")
        return []
    # la differenza sta sul lato che ha di meno: passivita'/costi per un utile
    utile_sp = differenze.get("PASSIVITA'", Decimal('0')) - differenze.get("ATTIVITA'", Decimal('0'))
    utile_ce = differenze.get('COSTI', Decimal('0')) - differenze.get('RICAVI', Decimal('0'))
    if (abs(utile_sp - utile_ce) > tol
            or abs(totali["ATTIVITA'"] - totali["PASSIVITA'"] - utile_sp) > tol
            or abs(totali['RICAVI'] - totali['COSTI'] - utile_ce) > tol):
        logger.warning("Verifica Sub/Mastro: la differenza d'esercizio non pareggia: lettura scartata")
        return []
    for r in righe:
        if r[0] == 'sezione':
            nome = r[2]
            r[3] = totali[nome] * _VS_SEZIONI[nome][1]
    return _entries_da_righe_verifica([tuple(r) for r in righe], {utile_ce}, "Verifica Sub/Mastro")
