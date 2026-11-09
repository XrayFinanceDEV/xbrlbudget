"""La composizione quadrata (Fase 3, Task 4): dalle foglie classificate a SP e CE che quadrano per costruzione.

Ogni foglia somma una volta sul suo dettaglio o sul secchio «altri» della sua macro-voce; una foglia senza
classe va nel secchio «altri» del suo lato e si dichiara in `senza_classe`; se anche il lato (o il verso, nel CE)
e' ignoto, non entra in nessun lato ma resta in `senza_classe` (mai finita in un secchio). Gli aggregati sono la somma dei
dettagli (`percorsi.completa`), `sp13` e' l'utile del CE. Lo scarto attivo-passivo o utile-`sp13` fino a 1 euro
e' arrotondamento: si chiude sul secchio «altri» del lato che manca e si registra. Oltre 1 euro nulla si muove:
si misura e si dichiara, mai un plug.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from decimal import Decimal

from calculations.ce_result import calculate_ce_result
from importers.import_snello import percorsi
from importers.lettore import tavola
from importers.lettore._ereditati import (FONDO_AMM_HEAD_RE, clamp_immobilizzazioni_negative, dettaglio_sp02,
                                          dettaglio_sp03, netta_fondi_negativi)
from importers.lettore.classifica import Classe
from importers.import_snello.verifica import soglia as soglia_adozione
from importers.lettore.diagnosi import TOLLERANZA_ARROTONDAMENTO
from importers.lettore.foglie import Ancora, Foglia, e_riga_del_risultato
from importers.rimanenze_ce import e_conto_rimanenze, voce_rimanenze

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
    rettifiche: Decimal = _ZERO      # massa delle rettifiche passate dalla colonna opposta: i totali stampati la
                                     # contano, attivo e passivo composti no (entrambi scendono di tanto)
    tagliate: list = field(default_factory=list)      # [[campo, eccedenza]]: fondo oltre il cespite, azzerato
    spostati: Decimal = _ZERO        # massa dei saldi negativi passati all'altro lato (D12): attivo e passivo composti
                                     # ne salgono entrambi, i totali stampati no


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
        natura = voce_rimanenze(f.etichetta, *reversed(f.contesto))
    if natura:
        # ce02/ce03 sono ricavi, ce10 un costo: la rimanenza dal verso opposto toglie
        proprio = "costo" if natura == "ce10" else "ricavo"
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


# Saldi negativi (proprietario, regole D2/D12/D15 del 2026-10-28): un saldo negativo fra le attivita' e' un debito -
# verso banche se e' liquidita', tributario se e' un credito tributario, altrimenti fra gli altri debiti; un debito
# negativo e' un credito (tributario o altro). Non e' il ribaltamento per descrizione (vietato): e' aritmetica, e attivo
# e passivo salgono della stessa massa, quindi il pareggio resta. Un fondo o una rettifica col meno restano dove sono.
_SALDO_NEGATIVO_ATTIVO = {"sp06": "sp16g", "sp07": "sp16g", "sp09": "sp16a"}
_SALDO_NEGATIVO_PASSIVO = {"sp16": "sp06g", "sp17": "sp06g"}
_TRIBUTARI = {"sp06e": "sp16e", "sp07e": "sp16e", "sp16e": "sp06e", "sp17e": "sp06e"}
_RETTIFICA_NEL_NOME = re.compile(r"\bF(?:ONDO|\.\s*DO|/DO|DO)\b|SVALUT|RETTIFIC|\bAMM(?:\.|TO|ORT)", re.I)


def saldo_negativo(f: Foglia, classe: Classe | None) -> str | None:
    """Il campo dell'altro lato su cui va una foglia di SP a saldo negativo, o None se resta dov'e'."""
    if f.sezione != "SP" or classe is None or classe.macro is None or classe.rettifica or importo_sp(f) >= 0:
        return None
    if (f.percorso_legale and percorsi.e_fondo(f.percorso_legale)) or _RETTIFICA_NEL_NOME.search(f.etichetta):
        return None
    tabella = {"A": _SALDO_NEGATIVO_ATTIVO, "P": _SALDO_NEGATIVO_PASSIVO}.get(lato_sp(f) or "", {})
    if classe.macro not in tabella:
        return None
    return _TRIBUTARI.get(classe.dettaglio or "") or tabella[classe.macro]


def _bersaglio_sp(f: Foglia, classe: Classe | None) -> tuple[str | None, Decimal]:
    importo = importo_sp(f)
    macro = classe.macro if classe else None
    altro_lato = saldo_negativo(f, classe)
    if altro_lato:
        return altro_lato, -importo
    if macro and classe.rettifica:
        # rettifica della colonna opposta: in diminuzione del bene o del netto, sul dettaglio se noto, altrimenti
        # sull'aggregato (senza dettaglio si netta all'aggregato, come `conti.py`). Il segno e' l'opposto di quello
        # con cui la colonna la conta, cosi' attivo e passivo scendono della stessa massa e il pareggio resta.
        return (classe.dettaglio or macro), -importo
    if macro:
        return (classe.dettaglio or tavola.altri_di(macro)), importo
    lato = lato_sp(f)
    if lato == "A":
        return tavola.altri_di("sp06"), importo
    if lato == "P":
        return tavola.altri_di("sp16"), importo
    return None, importo


def _categoria_cespite(etichetta: str) -> str | None:
    """La famiglia del cespite che un conto nomina, con le stesse regole del percorso C per cespiti e fondi
    (`_sp02_detail_field`/`_sp03_detail_field`): un fondo e il suo bene cadono nella stessa famiglia. La testa
    «F.DO AMM.» di un fondo si toglie prima (la stessa testa che `_canon_fondo_amm` riconosce)."""
    testo = _senza_testa(etichetta)
    return dettaglio_sp02(testo) or dettaglio_sp03(testo)


_PAROLA = re.compile(r"[A-Z0-9]+")
# le parole che dicono «fondo ammortamento (ordinario)» e non nominano il cespite
_PAROLE_DEL_FONDO = {"FONDO", "FONDI", "FDO", "FDI", "AMM", "AMMTO", "AMMORT", "AMMORTAMENTO", "AMMORTAMENTI", "ORD",
                     "ORDINARIO", "ORDINARI", "DEL", "DELLA", "DEI", "DELLE", "PER"}


def _senza_testa(etichetta: str) -> str:
    testo = re.sub(r"^[^A-Z0-9]+", "", etichetta.upper())       # «-F.Amm.» di un elenco a trattini
    return FONDO_AMM_HEAD_RE.sub("", testo, count=1)


def _parole(etichetta: str) -> list[str]:
    """Le parole significative (3 lettere o piu') di un conto, senza la dicitura del fondo."""
    return [w for w in _PAROLA.findall(_senza_testa(etichetta)) if len(w) >= 3 and w not in _PAROLE_DEL_FONDO]


def _nomina(fondo: list[str], cespite: list[str]) -> int:
    """Quante parole del cespite il fondo nomina, se ogni parola del fondo e' l'inizio di una parola del cespite o
    viceversa (abbreviazioni: «LAV. STR. SU BENI DI TERZ» e «LAVORI STRAOR. SU BENI DI TERZI», «UFFICIO» e «UFF»);
    0 se una parola del fondo non c'e'."""
    if not fondo or not cespite:
        return 0
    usate: set[int] = set()
    for w in fondo:
        k = next((k for k, c in enumerate(cespite) if k not in usate and (c.startswith(w) or w.startswith(c))), None)
        if k is None:
            return 0
        usate.add(k)
    return len(usate)


def _campo_del_cespite(c: Classe) -> str:
    """Il campo su cui il cespite somma davvero: il suo dettaglio, o il secchio «altri» della macro. Il fondo va
    li', non sull'aggregato: un cespite nel secchio con il fondo sull'aggregato lascia il secchio lordo."""
    return c.dettaglio or tavola.altri_di(c.macro)


def _abbina_fondi(foglie: list[Foglia], classi: dict[str, Classe]) -> tuple[dict[str, Classe], list[str]]:
    """F3-16: un fondo ammortamento si netta sulla macro (e sul dettaglio) del suo cespite, anche se il modello ha
    nominato un'altra categoria. Prima l'etichetta: il fondo che nomina un solo cespite (ogni sua parola e' l'inizio
    di una parola del cespite) va su quello; poi la famiglia, con le regole del percorso C per cespiti e fondi
    (`_categoria_cespite`). Un fondo entra solo se il cespite (o la famiglia) ha ancora lordo che lo contenga
    (fondo <= cespite, i fondi dal piu' grande). Senza un cespite che lo accolga resta la classe del modello,
    dichiarata. Le classi del chiamante non si mutano: ritorna copie."""
    immob = ("sp02", "sp03")
    cespiti = [f for f in foglie
               if f.sezione == "SP" and (c := classi.get(f.id)) is not None and not c.rettifica and c.macro in immob
               and lato_sp(f) == "A" and importo_sp(f) > 0]
    fondi = [f for f in foglie if f.sezione == "SP" and f.importo and classi.get(f.id) is not None
             and classi[f.id].rettifica and percorsi.e_fondo(classi[f.id].rettifica) and classi[f.id].macro in immob]
    if not fondi:
        return classi, []
    residuo = {f.id: importo_sp(f) for f in cespiti}
    parole = {f.id: _parole(f.etichetta) for f in cespiti}
    famiglia = {f.id: _categoria_cespite(f.etichetta) for f in cespiti}
    nuove = dict(classi)
    scelte: list[str] = []

    def assegna(fondo: Foglia, macro: str, dettaglio: str | None, come: str) -> None:
        nuove[fondo.id] = replace(classi[fondo.id], macro=macro, dettaglio=dettaglio)
        scelte.append(f"fondo abbinato al cespite per {come} ({dettaglio or macro}): {fondo.id}")

    for fondo in sorted(fondi, key=lambda x: (-x.importo, x.id)):
        if fondo.importo < 0:       # un fondo col segno del cespite non si abbina: resta com'e', dichiarato
            scelte.append(f"fondo senza cespite che lo contenga, resta la classe del modello ({classi[fondo.id].macro}): "
                          f"{fondo.id}")
            continue
        # punteggio: parole nominate, poi quanta parte del cespite spiegano («Attrezzature L Sabatini» batte
        # «Attrez. Cred Imp+Sabatini» per «F.Amm.ord.Attr L Sabatini»)
        voti = [((n, n / len(parole[c.id])), c) for c in cespiti
                if (n := _nomina(_parole(fondo.etichetta), parole[c.id])) and residuo[c.id] >= fondo.importo]
        voti.sort(key=lambda x: (-x[0][0], -x[0][1]))
        if voti and (len(voti) == 1 or voti[0][0] > voti[1][0]):
            c = voti[0][1]
            residuo[c.id] -= fondo.importo
            assegna(fondo, classi[c.id].macro, _campo_del_cespite(classi[c.id]), "etichetta")
            continue
        cat = _categoria_cespite(fondo.etichetta)
        stessi = [c for c in cespiti if cat is not None and famiglia[c.id] == cat]
        if not stessi or sum((residuo[c.id] for c in stessi), _ZERO) < fondo.importo:
            scelte.append(f"fondo senza cespite che lo contenga, resta la classe del modello ({classi[fondo.id].macro}): "
                          f"{fondo.id}")
            continue
        per_macro: dict[str, Decimal] = {}
        for c in stessi:
            per_macro[classi[c.id].macro] = per_macro.get(classi[c.id].macro, _ZERO) + importo_sp(c)
        macro = max(sorted(per_macro), key=lambda m: per_macro[m])
        dettagli = {_campo_del_cespite(classi[c.id]) for c in stessi if classi[c.id].macro == macro}
        resta = fondo.importo
        for c in sorted(stessi, key=lambda c: -residuo[c.id]):
            preso = min(resta, residuo[c.id])
            residuo[c.id] -= preso
            resta -= preso
        assegna(fondo, macro, dettagli.pop() if len(dettagli) == 1 else None, "famiglia")
    return nuove, scelte


def _somma(importi: dict[str, Decimal]) -> tuple[dict, dict, list]:
    """bs, ce e le immobilizzazioni tagliate: un fondo piu' fine del lordo si netta all'aggregato, un fondo oltre
    il cespite azzera l'aggregato e si dichiara - le regole del percorso snello (`conti.py`), mai una seconda."""
    bs, ce = percorsi.completa(netta_fondi_negativi(importi))
    return bs, ce, clamp_immobilizzazioni_negative(bs)


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
    classi, scelte_fondi = _abbina_fondi(foglie, classi)
    scelte += scelte_fondi
    rettifiche = _ZERO
    rettificate: dict[str, Decimal] = {}      # id -> importo con cui la sua colonna (e il suo totale) la conta
    rettifiche_in: dict[str, Decimal] = {}    # macro -> massa portata dalle rettifiche (col loro segno)
    spostate: dict[str, Decimal] = {}         # id -> importo (negativo) dei saldi passati all'altro lato
    spostate_in: dict[str, Decimal] = {}      # macro di arrivo -> massa (positiva) che vi e' arrivata
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
        elif f.sezione != "CE" and saldo_negativo(f, classe):
            spostate[f.id] = importo_sp(f)
            spostate_in[tavola.macro_di(campo)] = spostate_in.get(tavola.macro_di(campo), _ZERO) - importo_sp(f)
            scelte.append(f"saldo negativo sull'altro lato ({campo}): {f.id}")
        elif f.sezione != "CE" and classe.rettifica:
            rettifiche += importo_sp(f)
            rettificate[f.id] = importo_sp(f)
            rettifiche_in[classe.macro] = rettifiche_in.get(classe.macro, _ZERO) - importo_sp(f)
        if campo is None:
            continue            # lato ignoto: dichiarata ma non sommata ne' di qua ne' di la'
        _aggiungi(importi, campo, valore)

    chiusure: list[dict] = []
    soglia = TOLLERANZA_ARROTONDAMENTO

    def chiudi(campo: str, importo: Decimal) -> None:
        _aggiungi(importi, campo, importo)
        chiusure.append({"campo": campo, "importo": importo, "motivo": "arrotondamento"})

    bs, ce, tagliate = _somma(importi)
    ha_ce = any(f.sezione == "CE" and f.importo for f in foglie)
    # utile stampato contro utile del CE: chiude sul secchio del lato che manca
    stampato = next((a.importo for a in ancore if a.chiave == "utile"), None)
    if stampato is not None and ha_ce:
        d = stampato - _utile(ce)
        if _ZERO < abs(d) <= soglia:
            # utile stampato piu' alto: mancano ricavi; piu' basso: mancano costi
            chiudi(tavola.altri_di("ce04") if d > 0 else tavola.altri_di("ce06"), abs(d))
            bs, ce, tagliate = _somma(importi)

    if ha_ce:
        importi["sp13"] = _utile(ce)
        sp13_da = "ce"
    elif stampato is not None:   # solo SP: il risultato stampato e' una cifra letta, non inventata
        importi["sp13"] = stampato
        sp13_da = "stampato"
    else:
        sp13_da = "assente"
    bs, ce, tagliate = _somma(importi)
    if "sp13" in importi and righe_risultato:
        s_ris = soglia_adozione(_totali(bs)[0])
        for f in righe_risultato:
            segno = risultato_con_segno(f)
            if segno is None or e_questo_risultato(f, importi["sp13"], s_ris):
                continue
            _aggiungi(importi, "sp12g", segno)
            scelte.append(f"risultato di un altro esercizio negli utili portati a nuovo (sp12g): {f.id}")
        bs, ce, tagliate = _somma(importi)

    att, pas = _totali(bs)
    gap = att - pas
    if _ZERO < abs(gap) <= soglia:
        if gap > 0:
            chiudi(tavola.altri_di("sp16"), gap)      # manca passivo
        else:
            chiudi(tavola.altri_di("sp06"), -gap)     # manca attivo
        bs, ce, tagliate = _somma(importi)
        att, pas = _totali(bs)

    spostati = -sum(spostate.values(), _ZERO)     # positivo: attivo e passivo composti ne salgono entrambi
    scarti: dict[str, Decimal] = {}
    for a in ancore:
        if a.chiave == "attivo":
            composto = att + rettifiche - spostati   # il totale stampato e' lordo delle rettifiche e conta i
        elif a.chiave == "passivo":                  # saldi negativi sul loro lato
            composto = pas + rettifiche - spostati
        elif a.chiave == "utile":
            # senza CE l'utile stampato e' la cifra di sp13 (letta, non da rifare dal CE): nessun falso blocco
            composto = _utile(ce) if sp13_da == "ce" else importi.get("sp13", _ZERO)
        else:
            pieno = percorsi.NOMI.get(a.chiave)
            composto = (bs if a.chiave.startswith("sp") else ce).get(pieno, _ZERO) if pieno else _ZERO
            # una macro stampata conta le rettifiche sotto di lei, non quelle portate dall'altra colonna
            composto += (sum((rettificate[i] for i in a.foglie if i in rettificate), _ZERO)
                         - rettifiche_in.get(a.chiave, _ZERO)
                         + sum((spostate[i] for i in a.foglie if i in spostate), _ZERO)
                         - spostate_in.get(a.chiave, _ZERO))
        scarti[a.chiave] = a.importo - composto
    blocchi = [k for k, s in scarti.items() if abs(s) > soglia]
    if abs(att - pas) > soglia:
        blocchi.append("pareggio")
    return Composizione(bs, ce, scarti, blocchi, chiusure, senza_classe, att - pas, sp13_da, scelte,
                        rettifiche, tagliate, spostati)
