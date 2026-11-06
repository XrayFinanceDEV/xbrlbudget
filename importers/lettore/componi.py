"""La composizione quadrata (Fase 3, Task 4): dalle foglie classificate a SP e CE che quadrano per costruzione.

Ogni foglia somma una volta sul suo dettaglio KPI o sul secchio «altri» della sua macro-voce; una foglia senza
classe va nel secchio «altri» del suo lato e si dichiara in `senza_classe`; se anche il lato (o il verso, nel CE)
e' ignoto, non entra in nessun lato ma resta in `senza_classe` (mai finita in un secchio). Gli aggregati sono la somma dei
dettagli (`percorsi.completa`), `sp13` e' l'utile del CE. Lo scarto attivo-passivo o utile-`sp13` fino a 1 euro
e' arrotondamento: si chiude sul secchio «altri» del lato che manca e si registra. Oltre 1 euro nulla si muove:
si misura e si dichiara, mai un plug.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from calculations.ce_result import calculate_ce_result
from importers.import_snello import percorsi
from importers.lettore import tavola
from importers.lettore.classifica import Classe
from importers.import_snello.verifica import soglia as soglia_adozione
from importers.lettore.diagnosi import TOLLERANZA_ARROTONDAMENTO
from importers.lettore.foglie import Ancora, Foglia, e_riga_del_risultato
from importers.rimanenze_ce import e_conto_rimanenze, natura_rimanenze

_ZERO = Decimal(0)
_CENT = Decimal("0.01")


@dataclass
class Composizione:
    bs: dict[str, Decimal]
    ce: dict[str, Decimal]
    scarti: dict[str, Decimal]       # per ancora: stampato - composto
    blocchi: list[str]               # chiavi delle ancore con |scarto| > 1 euro
    chiusure: list[dict] = field(default_factory=list)   # solo <= 1 euro: {"campo", "importo", "motivo"}
    senza_classe: Decimal = _ZERO    # massa (in valore assoluto) delle foglie senza macro, dichiarata
    sbilancio: Decimal = _ZERO       # attivo - passivo dopo la chiusura (0 = quadra)
    sp13_da: str = "assente"         # "ce" | "stampato" | "assente"
    scelte: list[str] = field(default_factory=list)   # scelte dichiarate (es. ce17 senza verso trattato da costo)


def lato_sp(f: Foglia) -> str | None:
    """«A» | «P» | None: decide la colonna (L/R); sulla colonna unica il lato di legge della foglia (F3-7).
    La stessa regola vale per la guardia di costo del percorso."""
    lato = f.lato
    if lato == "U":
        lato = {"A": "L", "P": "R"}.get(f.lato_sp or "", "U")
    return {"L": "A", "R": "P"}.get(lato)


def _bersaglio_ce(f: Foglia, classe: Classe | None) -> tuple[str | None, Decimal]:
    """(codice breve, importo col segno da sommare) per una foglia di CE."""
    importo = f.importo
    natura = None
    if e_conto_rimanenze(f.etichetta):
        natura = natura_rimanenze(f.etichetta, *reversed(f.antenati))
    if natura:
        # ce02 e' un ricavo, ce10 un costo: la rimanenza dal verso opposto toglie
        proprio = "ricavo" if natura == "ce02" else "costo"
        if f.verso_ce and f.verso_ce != proprio:
            importo = -importo
        return natura, importo
    macro = classe.macro if classe else None
    if macro is None:
        if f.verso_ce == "costo":
            return tavola.altri_di("ce06"), importo
        if f.verso_ce == "ricavo":
            return tavola.altri_di("ce04"), importo
        return None, importo
    if macro == "ce17":      # mai sull'aggregato nudo: calculate_ce_result lo ignora se ci sono i dettagli
        return ("ce17a" if f.verso_ce == "ricavo" else "ce17b"), importo
    return (classe.dettaglio or tavola.altri_di(macro)), importo


def importo_sp(f: Foglia) -> Decimal:
    """L'importo che una foglia di SP somma sul suo lato."""
    if f.percorso_legale and percorsi.e_fondo(f.percorso_legale) and f.importo > 0:
        return -f.importo       # un fondo rettifica il cespite: sempre in diminuzione (F3-1)
    return f.importo


def e_risultato(f: Foglia) -> bool:
    """La riga del risultato d'esercizio: nel CE mai una foglia, il risultato e' la cifra di chiusura; nello SP lo e'
    solo se vale il risultato del periodo (`e_questo_risultato`)."""
    return e_riga_del_risultato(f.etichetta)


def risultato_con_segno(f: Foglia) -> Decimal | None:
    """Il risultato che una riga di SP stampa: positivo (utile) nel passivo, negativo (perdita) nell'attivo."""
    lato = lato_sp(f)
    if lato is None:
        return None
    return importo_sp(f) if lato == "P" else -importo_sp(f)


def e_questo_risultato(f: Foglia, risultato: Decimal, soglia: Decimal) -> bool:
    """Una riga del risultato nello SP e' la cifra di chiusura di questo periodo solo se ne ha l'importo (a meno del
    segno, che un «Perdita d'esercizio» stampato positivo nel passivo sbaglia); altrimenti e' il risultato di un
    altro esercizio non ancora destinato, un conto del patrimonio netto (utili/perdite portati a nuovo)."""
    return abs(abs(f.importo) - abs(risultato)) <= soglia


def _bersaglio_sp(f: Foglia, classe: Classe | None) -> tuple[str | None, Decimal]:
    importo = importo_sp(f)
    macro = classe.macro if classe else None
    if macro:
        return (classe.dettaglio or tavola.altri_di(macro)), importo
    lato = lato_sp(f)
    if lato == "A":
        return tavola.altri_di("sp06"), importo
    if lato == "P":
        return tavola.altri_di("sp16"), importo
    return None, importo


def _somma(importi: dict[str, Decimal]) -> tuple[dict, dict]:
    return percorsi.completa(importi)


def _totali(bs: dict[str, Decimal]) -> tuple[Decimal, Decimal]:
    att = sum((bs.get(percorsi.NOMI[m], _ZERO) for m in tavola.MACRO_ATTIVO), _ZERO)
    pas = sum((bs.get(percorsi.NOMI[m], _ZERO) for m in tavola.MACRO_PASSIVO), _ZERO)
    return att, pas


def _utile(ce: dict[str, Decimal]) -> Decimal:
    return calculate_ce_result(ce).net_profit.quantize(_CENT)


def _aggiungi(importi: dict[str, Decimal], campo: str, valore: Decimal) -> None:
    importi[campo] = importi.get(campo, _ZERO) + valore


def componi(foglie: list[Foglia], classi: dict[str, Classe], ancore: list[Ancora]) -> Composizione:
    importi: dict[str, Decimal] = {}
    senza_classe = _ZERO
    scelte: list[str] = []
    righe_risultato: list[Foglia] = []
    for f in foglie:
        if not f.importo:
            continue
        if e_risultato(f):
            if f.sezione == "SP":
                righe_risultato.append(f)   # si decide dopo, contro il risultato del periodo
            continue            # nel CE la riga del risultato non e' mai una foglia
        classe = classi.get(f.id)
        if classe is not None and classe.macro in ("sp13", "ce21"):
            continue            # il risultato e' la cifra di chiusura, mai una foglia
        if (f.sezione == "CE" and classe is not None and classe.macro == "ce17"
                and f.verso_ce not in ("ricavo", "costo")):
            scelte.append(f"ce17 senza verso trattata da costo (ce17b): {f.id}")
        if f.sezione == "CE":
            campo, valore = _bersaglio_ce(f, classe)
        else:
            campo, valore = _bersaglio_sp(f, classe)
        if classe is None or classe.macro is None:
            senza_classe += abs(f.importo)
        if campo is None:
            continue            # lato ignoto: dichiarata ma non sommata ne' di qua ne' di la'
        _aggiungi(importi, campo, valore)

    chiusure: list[dict] = []
    soglia = TOLLERANZA_ARROTONDAMENTO

    def chiudi(campo: str, importo: Decimal) -> None:
        _aggiungi(importi, campo, importo)
        chiusure.append({"campo": campo, "importo": importo, "motivo": "arrotondamento"})

    bs, ce = _somma(importi)
    ha_ce = any(f.sezione == "CE" and f.importo for f in foglie)
    # utile stampato contro utile del CE: chiude sul secchio del lato che manca
    stampato = next((a.importo for a in ancore if a.chiave == "utile"), None)
    if stampato is not None and ha_ce:
        d = stampato - _utile(ce)
        if _ZERO < abs(d) <= soglia:
            # utile stampato piu' alto: mancano ricavi; piu' basso: mancano costi
            chiudi(tavola.altri_di("ce04") if d > 0 else tavola.altri_di("ce06"), abs(d))
            bs, ce = _somma(importi)

    if ha_ce:
        importi["sp13"] = _utile(ce)
        sp13_da = "ce"
    elif stampato is not None:   # solo SP: il risultato stampato e' una cifra letta, non inventata
        importi["sp13"] = stampato
        sp13_da = "stampato"
    else:
        sp13_da = "assente"
    bs, ce = _somma(importi)
    if "sp13" in importi and righe_risultato:
        s_ris = soglia_adozione(_totali(bs)[0])
        for f in righe_risultato:
            segno = risultato_con_segno(f)
            if segno is None or e_questo_risultato(f, importi["sp13"], s_ris):
                continue
            _aggiungi(importi, "sp12g", segno)
            scelte.append(f"risultato di un altro esercizio negli utili portati a nuovo (sp12g): {f.id}")
        bs, ce = _somma(importi)

    att, pas = _totali(bs)
    gap = att - pas
    if _ZERO < abs(gap) <= soglia:
        if gap > 0:
            chiudi(tavola.altri_di("sp16"), gap)      # manca passivo
        else:
            chiudi(tavola.altri_di("sp06"), -gap)     # manca attivo
        bs, ce = _somma(importi)
        att, pas = _totali(bs)

    scarti: dict[str, Decimal] = {}
    for a in ancore:
        if a.chiave == "attivo":
            composto = att
        elif a.chiave == "passivo":
            composto = pas
        elif a.chiave == "utile":
            # senza CE l'utile stampato e' la cifra di sp13 (letta, non da rifare dal CE): nessun falso blocco
            composto = _utile(ce) if sp13_da == "ce" else importi.get("sp13", _ZERO)
        else:
            pieno = percorsi.NOMI.get(a.chiave)
            composto = (bs if a.chiave.startswith("sp") else ce).get(pieno, _ZERO) if pieno else _ZERO
        scarti[a.chiave] = a.importo - composto
    blocchi = [k for k, s in scarti.items() if abs(s) > soglia]
    if abs(att - pas) > soglia:
        blocchi.append("pareggio")
    return Composizione(bs, ce, scarti, blocchi, chiusure, senza_classe, att - pas, sp13_da, scelte)
