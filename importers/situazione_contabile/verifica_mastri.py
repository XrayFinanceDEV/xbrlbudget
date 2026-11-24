"""Bilancio di verifica «Mastri».

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
# Bilancio di verifica "Mastri" (budget_1325/1330, Santini SpA): sezioni ATTIVITÀ /
# PASSIVITÀ / COSTI / RICAVI, mastro a 4 cifre con la descrizione, conti a 8 cifre con un
# solo importo firmato nel verso della sezione (in ATTIVITÀ una banca negativa e' a saldo
# avere), "Totale <MASTRO>:" sotto i conti, il totale di sezione e un RIEPILOGO con la
# DIFFERENZA, che e' il risultato.
# ---------------------------------------------------------------------------

_VM_AMT = re.compile(r'^-?\d{1,3}(?:\.\d{3})*,\d{2}$')

_VM_SEZIONI = {'ATTIVITÀ': ('01', 1), 'PASSIVITÀ': ('02', -1), 'COSTI': ('03', 1), 'RICAVI': ('04', -1)}

def is_verifica_mastri(text: str) -> bool:
    if not re.search(r'Bilancio\s+di\s+verifica', text) or 'Descrizione conto' not in text:
        return False
    if 'RIEPILOGO' not in text or not re.search(r"TOTALE ATTIVITÀ'?:", text):
        return False
    return (len(re.findall(r'(?m)^\d{5,8}$', text)) >= 20
            and len(re.findall(r'(?m)^Totale .+:$', text)) >= 5)

def parse_entries_verifica_mastri(file_path: str) -> List[Entry]:
    """Le righe della verifica "Mastri", nella forma di ``_entries_da_righe_verifica``. Il
    totale di ogni mastro stampato sotto i suoi conti deve tornare al centesimo, come i totali
    di sezione; il risultato e' la DIFFERENZA del riepilogo, che deve essere sia attivita' meno
    passivita' sia ricavi meno costi. Altrimenti la lettura e' vuota."""
    doc = fitz.open(file_path)
    righe: list = []
    riepilogo: Dict[str, Decimal] = {}
    differenze: set = set()
    try:
        sezione = None
        segno = 1
        aperto = None                    # [riga di mastro, somma dei conti, quanti conti]
        for page in doc:
            per_y: Dict[int, list] = {}
            for w in page.get_text('words'):
                per_y.setdefault(round((w[1] + w[3]) / 2), []).append(w)
            for y in sorted(per_y):
                ws = sorted(per_y[y], key=lambda w: w[0])
                testo = ' '.join(w[4] for w in ws)
                importi = [w for w in ws if _VM_AMT.match(w[4]) and w[2] > 450]
                if testo == 'RIEPILOGO':
                    sezione = None
                    continue
                for m in re.finditer(r"TOTALE (ATTIVITÀ|PASSIVITÀ|COSTI|RICAVI)'?:\s*("
                                     + _VM_AMT.pattern[1:-1] + ')', testo):
                    if sezione is None:
                        riepilogo[m.group(1)] = _parse_amount(m.group(2))
                for m in re.finditer(r'DIFFERENZA\s+(' + _VM_AMT.pattern[1:-1] + ')', testo):
                    differenze.add(_parse_amount(m.group(1)))
                if testo in _VM_SEZIONI:
                    sezione = testo
                    codice, segno = _VM_SEZIONI[testo]
                    righe.append(['sezione', codice, testo, None, None])
                    aperto = None
                    continue
                if sezione is None or testo.startswith('TOTALE '):
                    continue
                if re.match(r'Totale .+:', testo) and ws[0][0] > 200:
                    if len(importi) != 1:
                        continue
                    stampato = _parse_amount(importi[0][4])
                    if aperto is None:
                        # un mastro con la sola riga del totale ("CLIENTI IT" / "CLIENTI ITALIA"
                        # senza conti sotto): il codice non e' numerico, il totale lo nomina
                        nome = re.sub(r'^Totale\s+|:\s*$', '', ' '.join(
                            w[4] for w in ws if w is not importi[0]))
                        # (codice numerico sintetico: build_iv_cee scarta le voci senza prefisso)
                        righe.append(['mastro', f'99{len(righe):04d}', nome, stampato * segno, None])
                        continue
                    # un mastro stampato senza conti sotto (CLIENTI WEB) vale da se'
                    if aperto[2] and abs(stampato - aperto[1]) > Decimal('0.05'):
                        logger.warning(f"Verifica Mastri: {testo[:60]} non torna con i suoi conti "
                                       f"({aperto[1]}): lettura scartata")
                        return []
                    righe[aperto[0]][3] = stampato * segno
                    aperto = None
                    continue
                codice = ws[0][4]
                if re.fullmatch(r'\d{3,4}', codice) and ws[0][0] < 40:
                    desc = ' '.join(w[4] for w in ws[1:] if w not in importi)
                    righe.append(['mastro', codice, desc, None, None])
                    aperto = [len(righe) - 1, Decimal('0'), 0]
                    continue
                if re.fullmatch(r'\d{5,8}', codice) and 50 < ws[0][0] < 110:
                    if len(importi) != 1 or aperto is None:
                        raise ValueError(f"conto senza importo a pagina {page.number + 1}: {testo[:80]}")
                    v = _parse_amount(importi[0][4])
                    desc = ' '.join(w[4] for w in ws[1:] if w is not importi[0])
                    righe.append(['conto', codice, desc, v * segno, None])
                    aperto[1] += v
                    aperto[2] += 1
    finally:
        doc.close()

    tol = Decimal('0.05')
    nomi = {'01': 'ATTIVITÀ', '02': 'PASSIVITÀ', '03': 'COSTI', '04': 'RICAVI'}
    if set(riepilogo) != set(nomi.values()) or len(differenze) != 1:
        logger.warning("Verifica Mastri: riepilogo incompleto: lettura scartata")
        return []
    differenza = next(iter(differenze))
    sp = riepilogo['ATTIVITÀ'] - riepilogo['PASSIVITÀ']
    ce = riepilogo['RICAVI'] - riepilogo['COSTI']
    # l'utile puo' stare gia' dentro la sezione PASSIVITA' come conto ("utile d'esercizio"): allora
    # attivita' e passivita' pareggiano e la DIFFERENZA e' il solo risultato del conto economico
    utile_gia_nel_passivo = abs(sp) <= tol and abs(differenza - ce) <= tol
    if not utile_gia_nel_passivo and (abs(abs(sp) - differenza) > tol or abs(sp - ce) > tol):
        logger.warning("Verifica Mastri: la differenza del riepilogo non e' il risultato: lettura scartata")
        return []
    for r in righe:
        if r[0] == 'sezione':
            r[3] = riepilogo[nomi[r[1]]] * _VM_SEZIONI[nomi[r[1]]][1]
    return _entries_da_righe_verifica([tuple(r) for r in righe], {ce}, "Verifica Mastri")
