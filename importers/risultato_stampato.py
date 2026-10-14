"""Sbilancio chiuso dal risultato stampato: cercato nel documento, al centesimo.

Molti lettori perdono un risultato che il documento stampa: l'utile del periodo
(sp13 assente o letto male) oppure l'utile (o la perdita) dell'anno prima non ancora
destinato, che il gestionale lascia fra i conti del patrimonio netto («Utile
d'esercizio» del 2025 in una situazione al 30/06/2026, «Eccedenza esercizio
precedente»). Il foglio resta sbilanciato esattamente di quell'importo.

Qui si misura lo sbilancio attivo - passivo e lo si cerca nel testo del documento, su
una riga che porta una didascalia di risultato (utile, perdita, risultato, eccedenza,
avanzo, disavanzo). Due esiti, e nessun altro:

- lo sbilancio è la differenza fra l'utile del conto economico e sp13, e quell'utile è
  stampato: sp13 diventa l'utile del conto economico (risultato del periodo);
- lo sbilancio stesso è stampato su una riga di risultato: è il risultato dell'anno
  prima, va negli utili (perdite) portati a nuovo, sp12g.

È un ripiego che etichetta un importo stampato, non un tappo: vale solo al centesimo, e
se l'importo non è nel documento non succede nulla. Si dichiara sempre.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

_TOLLERANZA = Decimal("0.05")
_IMPORTO = re.compile(r"-?\d{1,3}(?:\.\d{3})+,\d{2}-?|-?\d{1,3},\d{2}-?|-?\d{4,},\d{2}-?")
_DIDASCALIA = re.compile(r"(?i)\b(utile|utili|perdit\w*|risultat\w*|eccedenz\w*|avanzo|disavanzo)\b")
_PERDITA = re.compile(r"(?i)perdit|disavanzo")
_UTILE = re.compile(r"(?i)\butil|eccedenz|avanzo")


def _valore(testo: str) -> Decimal:
    t = testo.replace(".", "").replace(",", ".")
    negativo = t.startswith("-") or t.endswith("-")
    v = Decimal(t.strip("-"))
    return -v if negativo else v


def righe_del_pdf(percorso: str) -> list[str]:
    """Le righe fisiche del PDF, parole ordinate per x sulla stessa y."""
    import fitz

    righe: list[str] = []
    with fitz.open(percorso) as doc:
        for page in doc:
            per_y: dict[int, list] = {}
            for w in page.get_text("words"):
                per_y.setdefault(round(w[3] / 2), []).append(w)
            for k in sorted(per_y):
                righe.append(" ".join(w[4] for w in sorted(per_y[k], key=lambda w: w[0])))
    return righe


def _stampato_come_risultato(importo: Decimal, righe: Iterable[str], segno: int) -> Optional[str]:
    """La riga che stampa ``importo`` accanto a una didascalia di risultato, o None.
    La didascalia deve stare fra l'importo e l'importo vicino, dal lato in cui il
    gestionale la stampa: dopo l'importo se la riga comincia con un importo
    ("1.406.600,60 Totale Attivita':"), prima altrimenti ("UTILE ... 269.255,83"); così
    la didascalia del conto della colonna accanto non conta. Con
    ``segno`` negativo la didascalia deve dire perdita, con positivo utile."""
    bersaglio = abs(importo)
    for riga in righe:
        trovati = list(_IMPORTO.finditer(riga))
        importo_prima = bool(trovati) and not riga[:trovati[0].start()].strip()
        for i, m in enumerate(trovati):
            if abs(abs(_valore(m.group(0))) - bersaglio) > _TOLLERANZA:
                continue
            prima = riga[(trovati[i - 1].end() if i else 0):m.start()]
            dopo = riga[m.end():(trovati[i + 1].start() if i + 1 < len(trovati) else len(riga))]
            for pezzo in ((dopo,) if importo_prima else (prima,)):
                if not _DIDASCALIA.search(pezzo):
                    continue
                if segno < 0 and not _PERDITA.search(pezzo) and not re.search(r"(?i)risultat", pezzo):
                    continue
                if segno > 0 and _PERDITA.search(pezzo) and not _UTILE.search(pezzo):
                    continue
                return riga.strip()
    return None


def chiudi_col_risultato_stampato(bs: dict, ce: Optional[dict], righe: list[str]):
    """(bs, report) — ``report`` è None quando non c'era nulla da chiudere o l'importo
    non è stampato. Tocca solo sp13, oppure sp12 + sp12g, e il totale passivo."""
    from importers.iv_cee_hierarchy import check_quadratura

    q = check_quadratura(bs, ce)
    sbilancio = q.sbilancio
    if q.is_empty or abs(sbilancio) <= _TOLLERANZA or not righe:
        return bs, None
    sp13 = Decimal(str(bs.get("sp13_utile_perdita") or 0))

    utile_ce = q.utile_ce
    if (utile_ce is not None and abs(utile_ce - sp13) > _TOLLERANZA
            and abs(sbilancio - (utile_ce - sp13)) <= _TOLLERANZA):
        riga = _stampato_come_risultato(utile_ce, righe, 1 if utile_ce >= 0 else -1)
        if riga:
            bs = dict(bs)
            bs["sp13_utile_perdita"] = utile_ce
            bs["totale_passivo"] = Decimal(str(bs.get("totale_passivo") or 0)) + (utile_ce - sp13)
            return bs, {"esito": "risultato_del_periodo", "importo": str(utile_ce),
                        "sp13_prima": str(sp13), "riga": riga[:160]}

    if utile_ce is not None and abs(abs(sbilancio) - abs(utile_ce)) <= _TOLLERANZA \
            and abs(sp13) > _TOLLERANZA:
        # lo sbilancio vale proprio l'utile del periodo, che sp13 porta già: non è un
        # anno prima, è un risultato contato due volte o mancante altrove. Non si tocca.
        return bs, None
    riga = _stampato_come_risultato(sbilancio, righe, 1 if sbilancio > 0 else -1)
    if not riga:
        return bs, None
    bs = dict(bs)
    for k in ("sp12_riserve", "sp12g_utili_perdite_portati", "totale_passivo"):
        bs[k] = Decimal(str(bs.get(k) or 0)) + sbilancio
    return bs, {"esito": "risultato_anno_prima", "importo": str(sbilancio), "riga": riga[:160]}


def avviso(report: dict) -> str:
    importo = Decimal(report["importo"])
    testo = f"{abs(importo):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if report["esito"] == "risultato_del_periodo":
        return (f"RISULTATO DEL PERIODO LETTO DAL DOCUMENTO: l'utile {testo} stampato "
                f"(«{report['riga']}») sostituisce sp13 {report['sp13_prima']}, che lasciava "
                "lo stato patrimoniale sbilanciato di quella differenza — verificare in Rettifiche")
    voce = "utile" if importo > 0 else "perdita"
    return (f"RISULTATO DELL'ANNO PRIMA NON DESTINATO: lo sbilancio di {testo} è stampato "
            f"come {voce} («{report['riga']}») ed è stato messo negli utili (perdite) portati "
            "a nuovo — verificare in Rettifiche")
