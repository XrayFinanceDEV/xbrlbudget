"""Bilancio di verifica con la sezione in colonna (SEZBIL).

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import re
from decimal import Decimal
from typing import Dict, List
from importers.situazione_contabile.comune import (
    Entry,
)
from importers.situazione_contabile.verifica_ie import (
    _entries_da_righe_verifica,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.situazione_contabile_parser")


# ---------------------------------------------------------------------------
# Bilancio di verifica con la sezione in colonna (COLOMBO 2026): "Mastro | Descrizione | Conto |
# Descrizione | Importo | SEZBIL". Un solo importo per conto, sempre nel verso della sezione,
# senza separatore delle migliaia e con uno o due decimali ("203441,8"); la lettera della
# colonna SEZBIL e' la sezione (A attivita', P passivita', C costi, R ricavi; "X" una riga
# vuota). "Totale <MASTRO>" sotto i conti, e un RIEPILOGO con TOTALE ATTIVITA'/PASSIVITA'/
# COSTI/RICAVI e la DIFFERENZA, che e' il risultato. Nessun "bilancio di verifica" ne'
# "TOTALE A PAREGGIO": prima il classificatore lo rifiutava come documento non riconosciuto.
# ---------------------------------------------------------------------------

# fino a tre decimali: il gestionale stampa "1712097,143" (conto di un factor) e "2721068,787"
_SB_AMT = re.compile(r'^-?\d{1,3}(?:\.\d{3})+(?:,\d{1,3})?$|^-?\d+(?:,\d{1,3})?$')

_SB_SEZIONI = {'A': ('01', 1), 'P': ('02', -1), 'C': ('03', 1), 'R': ('04', -1)}

_SB_RIEPILOGO = {"ATTIVITA'": 'A', "PASSIVITA'": 'P', 'COSTI': 'C', 'RICAVI': 'R'}

def is_verifica_sezbil(text: str) -> bool:
    if 'SEZBIL' not in text or 'RIEPILOGO' not in text:
        return False
    upper = text.upper()
    if not all(f"TOTALE {s}" in upper for s in _SB_RIEPILOGO):
        return False
    # l'importo e la lettera della sezione: "3845 A", "203441,8 A" (o la lettera da sola)
    return len(re.findall(r'(?m)^(?:-?[\d.]+(?:,\d{1,3})? )?[APCR]$', text)) >= 10

def _sb_importo(testo: str) -> Decimal:
    neg = testo.startswith('-')
    v = Decimal(testo.lstrip('-').replace('.', '').replace(',', '.'))
    return -v if neg else v

def parse_entries_verifica_sezbil(file_path: str) -> List[Entry]:
    """Le righe della verifica con la sezione in colonna, nella forma di
    ``_entries_da_righe_verifica``. Le colonne si leggono dall'intestazione di ogni pagina. Ogni
    mastro deve tornare al centesimo con i suoi conti, ogni sezione col suo totale del
    riepilogo, e la DIFFERENZA deve essere sia attivita' meno passivita' sia ricavi meno costi.
    Altrimenti la lettura e' vuota."""
    tol = Decimal('0.05')
    mastri: List[dict] = []              # nell'ordine di stampa
    totali: Dict[str, Decimal] = {}
    differenze: List[Decimal] = []
    doc = fitz.open(file_path)
    try:
        colonne = None
        mastro = None
        for page in doc:
            per_y: Dict[int, list] = {}
            for w in page.get_text('words'):
                per_y.setdefault(round((w[1] + w[3]) / 2), []).append(w)
            for y in sorted(per_y):
                ws = sorted(per_y[y], key=lambda w: w[0])
                parole = [w[4] for w in ws]
                if 'SEZBIL' in parole and 'Conto' in parole and 'Importo' in parole:
                    x = {w[4]: w for w in ws}
                    colonne = {'mastro': ws[0][0], 'conto': x['Conto'][0],
                               'importo': x['Importo'][0], 'sezbil': x['SEZBIL'][0]}
                    continue
                if colonne is None:
                    continue
                testo = ' '.join(parole)
                # riepilogo: "TOTALE ATTIVITA' 7721026,18 TOTALE COSTI 5883928,84", "DIFFERENZA x DIFFERENZA x"
                coppie = re.findall(r"TOTALE (ATTIVITA'|PASSIVITA'|COSTI|RICAVI) (\S+)", testo)
                if coppie and all(_SB_AMT.match(v) for _, v in coppie):
                    for nome, v in coppie:
                        totali[_SB_RIEPILOGO[nome]] = _sb_importo(v)
                    continue
                if parole[0] == 'DIFFERENZA':
                    differenze.extend(_sb_importo(v) for v in parole if _SB_AMT.match(v))
                    continue
                lettera = next((w[4] for w in ws if abs(w[0] - colonne['sezbil']) <= 8
                                and w[4] in ('A', 'P', 'C', 'R', 'X')), None)
                if lettera is None or lettera == 'X':
                    continue
                importi = [w for w in ws if _SB_AMT.match(w[4])
                           and colonne['importo'] - 60 <= w[2] < colonne['sezbil'] + 2]
                if len(importi) != 1:
                    continue
                v = _sb_importo(importi[0][4])
                codice_conto = next((w[4] for w in ws if abs(w[0] - colonne['conto']) <= 10
                                     and re.fullmatch(r'[0-9A-Z]{3,8}', w[4])
                                     and re.search(r'\d', w[4])), None)
                codice_mastro = next((w[4] for w in ws if abs(w[0] - colonne['mastro']) <= 10
                                      and re.fullmatch(r'\d{2,4}', w[4])), None)
                if codice_conto is None and parole.count('Totale') == 2:
                    # Mastro di un solo conto, entrambi senza codice numerico (COLOMBO: "CLIENTI IT
                    # Totale CLIENTI ITALIA CLIENTI IT Totale CLIENTI ITALIA 2721068,787 A"): la riga
                    # e' insieme il conto e il totale del suo mastro. Mastro, conto e descrizioni si
                    # separano dalle due parole "Totale"; senza quelle due, la riga non si legge.
                    t1, t2 = [i for i, w in enumerate(ws) if w[4] == 'Totale']
                    i_conto = next((i for i, w in enumerate(ws) if w[0] >= colonne['conto'] - 10), None)
                    if i_conto is not None and t1 < i_conto < t2:
                        def _testo(da, a):
                            return ' '.join(w[4] for w in ws[da:a] if w not in importi and w[4] != lettera)
                        mastri.append({'codice': _testo(0, t1), 'desc': _testo(t1 + 1, i_conto),
                                       'sezione': lettera,
                                       # il prefisso "00" e' un segnaposto: build_iv_cee scarta un conto
                                                 # il cui codice non comincia per due cifre
                                       'conti': [('00 ' + _testo(i_conto, t2), _testo(t2 + 1, len(ws)), v)],
                                       'stampato': v})
                        mastro = None
                    continue
                if codice_conto is None:
                    # "Totale <MASTRO>" o il totale della sezione ("Totale", "Totale ricavi")
                    if mastro is not None and parole[0] == 'Totale' and len(parole) > 3:
                        mastro['stampato'] = v
                        mastro = None
                    continue
                desc_x = (colonne['conto'] + 20, colonne['importo'] - 60)
                desc = ' '.join(w[4] for w in ws if desc_x[0] < w[0] and w[2] <= desc_x[1]
                                and w not in importi)
                if codice_mastro is not None or mastro is None or mastro['sezione'] != lettera:
                    desc_m = ' '.join(w[4] for w in ws if colonne['mastro'] + 30 < w[0] < colonne['conto'] - 5)
                    mastro = {'codice': codice_mastro or (mastro or {}).get('codice', ''),
                              'desc': desc_m or (mastro or {}).get('desc', ''),
                              'sezione': lettera, 'conti': [], 'stampato': None}
                    mastri.append(mastro)
                mastro['conti'].append((codice_conto, desc, v))
    finally:
        doc.close()

    if set(totali) != set(_SB_SEZIONI) or len(differenze) != 2 or not mastri:
        logger.warning("Verifica SEZBIL: riepilogo incompleto: lettura scartata")
        return []
    for m in mastri:
        somma = sum((c[2] for c in m['conti']), Decimal('0'))
        if m['stampato'] is not None and abs(somma - m['stampato']) > tol:
            logger.warning(f"Verifica SEZBIL: il mastro {m['desc'][:40]} ({m['stampato']}) non torna "
                           f"con i suoi conti ({somma}): lettura scartata")
            return []
    utile_sp = totali['A'] - totali['P']
    utile_ce = totali['R'] - totali['C']
    if (abs(utile_sp - utile_ce) > tol
            or any(abs(d - utile_sp) > tol for d in differenze)):
        logger.warning("Verifica SEZBIL: la differenza non pareggia lo SP e il CE: lettura scartata")
        return []
    righe: list = []
    for lettera, (codice_sez, segno) in _SB_SEZIONI.items():
        nome = {'A': "ATTIVITA'", 'P': "PASSIVITA'", 'C': 'COSTI', 'R': 'RICAVI'}[lettera]
        righe.append(('sezione', codice_sez, nome, totali[lettera] * segno, None))
        for m in mastri:
            if m['sezione'] != lettera:
                continue
            righe.append(('mastro', m['codice'], m['desc'], None, None))
            for codice, desc, v in m['conti']:
                righe.append(('conto', codice, desc, v * segno, None))
    return _entries_da_righe_verifica(righe, {utile_ce}, "Verifica SEZBIL")
