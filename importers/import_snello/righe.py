"""Righe di un elenco di conti: saldo, segno, totali esclusi perche' somma di righe vicine.

La struttura fisica delle righe viene dal lettore del repo (collect_source_rows: rotazione,
righe fisiche, sezioni contrapposte, colonne SAP). Qui si sceglie il saldo e si tolgono i
totali: il totale stampato decide, mai il prefisso del codice di conto.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal

_AMT = re.compile(r"^\(?-?(\d{1,3}(\.\d{3})+|\d+),\d{2}\)?-?$")
_MIGLIAIA = re.compile(r"^\(?-?\d{1,3}(\.\d{3})+\)?-?$")
_AMT_TESTO = re.compile(r"\s+\(?-?[\d.]+,\d{2}\)?-?(\s+[DA](?=\s|$))?")


@dataclass
class Riga:
    id: str
    pagina: int
    lato: str
    testo: str
    valore: Decimal | None
    sezione: str = ""
    mastro: str | None = None
    totale: bool = False
    percorso: str | None = None


def _dec(t: str) -> Decimal:
    negativo = t.startswith("-") or t.endswith("-") or t.startswith("(")
    v = Decimal(t.strip("()-").replace(".", "").replace(",", "."))
    return -v if negativo else v


def importi(testo: str) -> list[tuple[Decimal, str]]:
    toks = testo.replace("_", "").split()
    out = []
    for i, t in enumerate(toks):
        if _AMT.match(t) or _MIGLIAIA.match(t):
            dopo = toks[i + 1] if i + 1 < len(toks) else ""
            out.append((_dec(t), dopo if dopo in ("D", "A") else ""))
    return out


def etichetta(testo: str) -> str:
    return re.sub(r"\s+", " ", _AMT_TESTO.sub("", " " + testo.replace("_", ""))).strip()


def regola_colonna(ruoli: list[str]) -> dict:
    for ruolo in ("saldo_corrente", "saldo_finale"):
        if ruolo in ruoli:
            return {"n": len(ruoli), "k": ruoli.index(ruolo)}
    return {}


def saldo(riga, regola: dict) -> Decimal | None:
    vs = importi(riga.text)
    if not vs:
        return None
    if not regola:
        v, m = vs[-1]
    elif len(vs) == regola["n"]:
        v, m = vs[regola["k"]]
    elif regola["k"] == regola["n"] - 1:
        v, m = vs[-1]
    elif regola["k"] == 0:
        v, m = vs[0]
    else:
        return None
    v = -abs(v) if m == "A" else v
    return v.quantize(Decimal("0.01"))


def _per_lato(righe: list[Riga]) -> dict[str, list[Riga]]:
    per_lato: dict[str, list[Riga]] = defaultdict(list)
    for r in righe:
        r.totale, r.mastro = False, None
        if r.valore is not None:
            per_lato[r.lato].append(r)
    return per_lato


def _valori_per_lato(righe: list[Riga]) -> dict[str, list[Decimal]]:
    """Come _per_lato, ma solo i valori: per contare senza mai copiare le Riga."""
    per_lato: dict[str, list[Decimal]] = defaultdict(list)
    for r in righe:
        if r.valore is not None:
            per_lato[r.lato].append(r.valore)
    return per_lato


def _lista_concatenata(vivo: list[bool]) -> tuple[list[int], list[int]]:
    """nxt/prv sulle sole posizioni vive, saltando le altre: n (fuori lista) e -1 come
    sentinelle di fine e inizio."""
    n = len(vivo)
    nxt, prv = [n] * n, [-1] * n
    precedente = -1
    for i in range(n):
        if vivo[i]:
            if precedente != -1:
                nxt[precedente] = i
            prv[i] = precedente
            precedente = i
    return nxt, prv


def _trova_totali(valori: list[Decimal], vivo: list[bool], direzione: int, kmin: int) -> list[tuple[int, list[int]]]:
    """Una sola passata, senza riavvii dopo ogni marcatura: ascendente per la direzione -1 (i
    figli sono prima; una rimozione conta solo per i candidati dopo, mai per quelli gia'
    passati), discendente per la direzione +1 (simmetrico, i figli sono dopo). Il punto fisso
    e' identico al riavvio-a-ogni-marcatura, perche' la marcatura di un candidato dipende solo
    dalle posizioni gia' visitate in quest'ordine: una lista concatenata rende O(1) la
    rimozione e il passo al vivo successivo, col tetto di 80 membri per candidato.

    Solo conteggio, usa e getta (_conta_forzata): il candidato trovato esce dalla lista viva
    per sempre, mai riabilitato come addendo - qui basta sapere QUANTO marcherebbe questa sola
    direzione, non costruire una gerarchia vera. La marcatura reale sta in ``_risolvi_totali``."""
    n = len(valori)
    nxt, prv = _lista_concatenata(vivo)
    passo = prv if direzione == -1 else nxt
    ordine = range(n) if direzione == -1 else range(n - 1, -1, -1)
    trovati: list[tuple[int, list[int]]] = []
    for i in ordine:
        if not vivo[i] or not valori[i]:
            continue
        s, j, membri = Decimal(0), passo[i], []
        while j != -1 and j != n and len(membri) < 80:
            s += valori[j]
            membri.append(j)
            if len(membri) >= kmin and s == valori[i]:
                vivo[i] = False
                a, b = prv[i], nxt[i]
                if a != -1:
                    nxt[a] = b
                if b != n:
                    prv[b] = a
                trovati.append((i, membri))
                break
            j = passo[j]
    return trovati


def _cerca_membri(valori: list[Decimal], passo: list[int], i: int, kmin: int) -> list[int] | None:
    """Cammina da ``passo[i]`` accumulando membri vivi finche' la somma non tocca
    ``valori[i]`` (con almeno ``kmin`` membri) o il cammino finisce/eccede il tetto. Non muta
    nulla: solo lettura di ``valori``/``passo``, cosi' si puo' usare sia per il candidato
    principale sia per un tentativo di risoluzione su un suo membro, senza intrecciare gli
    effetti collaterali dei due."""
    n = len(valori)
    s, j, membri = Decimal(0), passo[i], []
    while j != -1 and j != n and len(membri) < 80:
        s += valori[j]
        membri.append(j)
        if len(membri) >= kmin and s == valori[i]:
            return membri
        j = passo[j]
    return None


def _marca_come_totale(seq: list["Riga"], vivo: list[bool], candidabile: list[bool],
                       passo: list[int], i: int, membri: list[int]) -> None:
    """Applica un match gia' trovato: ``i`` resta vivo come addendo per il livello sopra, i
    suoi membri escono dalla lista viva per sempre. Isolata da ``_cerca_membri`` cosi' la
    stessa mutazione serve sia per il candidato principale di ``_risolvi_totali`` sia per la
    risoluzione on-demand di un suo membro."""
    seq[i].totale = True
    candidabile[i] = False
    for mi in membri:
        seq[mi].mastro = seq[mi].mastro or seq[i].testo
        vivo[mi] = False
    # i resta vivo (non si tocca): il suo passo salta oltre i membri appena spesi, cosi' un
    # candidato successivo nella stessa scansione che attraversa i lo trova come un unico
    # addendo, mai come i suoi vecchi membri.
    passo[i] = passo[membri[-1]]


def _risolvi_totali(seq: list["Riga"], valori: list[Decimal], vivo: list[bool],
                    candidabile: list[bool], direzione: int, kmin: int) -> int:
    """Come ``_trova_totali``, ma marca SUBITO ogni candidato trovato, nella stessa passata:
    il totale resta al suo posto nella lista concatenata (mai spliciato fuori) - solo i suoi
    membri escono, per sempre - cosi' un candidato piu' in la' nella stessa scansione (un
    totale di livello superiore) lo trova gia' pronto come addendo. Senza questo, un totale di
    terzo livello scansionato nella STESSA chiamata di un totale di secondo livello non ancora
    risolto poteva "scavalcarlo" sommando le sue foglie grezze rimaste vive per coincidenza
    (mai spliciate, perche' non erano mai state la CANDIDATA di un match) invece di aspettare
    che il livello intermedio si risolvesse per primo - lasciando il livello intermedio
    (``.totale`` mai marcato) a contare due volte la propria massa. ``candidabile`` impedisce
    di ri-marcare un totale gia' risolto (mai il bersaglio di un nuovo match), ma non lo
    esclude come addendo: e' li' apposta perche' resti disponibile.

    Un pericolo simmetrico e distinto (diagnosi TM 589/590, Task 20): un membro ``mi`` di un
    match k>=2 puo' essere a sua volta un mastro a figlio unico, risolvibile solo a k=1 - una
    passata che qui non e' ancora partita (parte solo dopo, e solo se ``marca_totali`` ha
    gia' visto un gruppo vero). Se lo si consuma cosi' com'e', ``mi`` non passa mai per
    ``.totale = True`` e il suo stesso figlio, mai reclamato, resta una foglia gemella con lo
    stesso importo: la massa raddoppia. Prima di accettare il match trovato per ``i``, ogni
    membro ancora ``candidabile`` (mai risolto) ha quindi diritto a un tentativo di
    risoluzione sul posto, con lo stesso ``passo``: se risolve, ``mi`` diventa esso
    stesso un totale (mastro dei propri figli) PRIMA di essere marcato come membro di
    ``i`` - le due cose coesistono, come per ogni totale intermedio a piu' livelli. Il
    tentativo usa solo membri gia' vivi in quel momento (mai ``i`` o gli altri membri dello
    stesso match, che sono fisicamente dall'altra parte rispetto ai figli di ``mi``), e non
    scavalca nulla: se ``mi`` non risolve, resta un membro grezzo esattamente come oggi.

    Task 22 (G4, diagnosi budget_330): il primo tentativo qui e' a k>=2 (un mastro a PIU' di un
    figlio, non solo il caso a figlio unico di Task 20), con lo stesso ``_cerca_membri`` e lo
    stesso tetto di 80 membri usato ovunque; solo se NON risolve a k>=2 si ripiega su k=1, come
    prima. L'ordine (k>=2 prima, k=1 dopo) e' lo stesso che ``marca_totali`` applica al giro
    esterno (Task 4): una catena a un solo figlio si accetta solo quando un gruppo vero non la
    precede, mai il contrario. ``mi`` puo' pero' gia' essere risolto per proprio conto (turno
    proprio, stesso ``kmin`` di questa stessa passata) prima che ``i`` lo consumi come membro -
    in quel caso e' il turno proprio, non questo tentativo, che gia' lo marca ``.totale``: qui
    resta solo il caso residuo (a k=1, come da Task 20) in cui il turno proprio di ``mi`` non e'
    mai riuscito a trovare nulla."""
    n = len(valori)
    nxt, prv = _lista_concatenata(vivo)
    passo = prv if direzione == -1 else nxt
    ordine = range(n) if direzione == -1 else range(n - 1, -1, -1)
    marcati = 0
    for i in ordine:
        if not vivo[i] or not candidabile[i] or not valori[i]:
            continue
        membri = _cerca_membri(valori, passo, i, kmin)
        if membri is None:
            continue
        for mi in membri:
            if candidabile[mi]:
                sotto = _cerca_membri(valori, passo, mi, 2)
                if sotto is None:
                    sotto = _cerca_membri(valori, passo, mi, 1)
                if sotto is not None:
                    _marca_come_totale(seq, vivo, candidabile, passo, mi, sotto)
                    marcati += 1
        _marca_come_totale(seq, vivo, candidabile, passo, i, membri)
        marcati += 1
    return marcati


def _conta_forzata(righe: list[Riga], direzione: int) -> int:
    """Su array booleani usa e getta (mai una copia delle Riga): quante righe marcherebbe
    questa sola direzione, gruppi (k>=2) e catene (k=1) insieme. Serve solo a confrontare le
    due direzioni, mai a marcare davvero."""
    marcati = 0
    for valori in _valori_per_lato(righe).values():
        vivo = [True] * len(valori)
        marcati += len(_trova_totali(valori, vivo, direzione, 2))
        marcati += len(_trova_totali(valori, vivo, direzione, 1))
    return marcati


def _voti_apprendimento(righe: list[Riga]) -> Counter:
    """Vota la direzione dai soli gruppi (k>=2), provando entrambe le direzioni riga per
    riga: usato solo per spareggiare quando le due passate forzate per intero marcano lo
    stesso numero di righe. Da solo puo' votare la direzione sbagliata quando un gruppo
    confina con l'altro (le prime righe del gruppo vicino sommano per caso al totale di
    questo) - per questo non decide mai da solo, se non a parita'."""
    per_lato = _per_lato(deepcopy(righe))
    voti: Counter = Counter()
    for seq in per_lato.values():
        cambiato = True
        while cambiato:
            cambiato = False
            vive = [r for r in seq if not r.totale]
            for i, r in enumerate(vive):
                if not r.valore:
                    continue
                for d in (1, -1):
                    s, j, membri = Decimal(0), i + d, []
                    while 0 <= j < len(vive) and len(membri) < 80:
                        s += vive[j].valore
                        membri.append(vive[j])
                        if len(membri) >= 2 and s == r.valore:
                            r.totale = cambiato = True
                            voti[d] += 1
                            for m in membri:
                                m.mastro = m.mastro or r.testo
                            break
                        j += d
                    if r.totale:
                        break
                if cambiato:
                    break
            if cambiato:
                continue
    return voti


def marca_totali(righe: list[Riga]) -> Counter:
    """Sceglie la direzione provando le due passate forzate per intero (gruppi e catene) e
    tenendo quella che marca piu' righe: l'apprendimento a coppie da solo vota anche la
    direzione sbagliata quando un gruppo confina con l'altro (le prime righe del gruppo
    vicino sommano per caso al totale di questo - senza un confine di gruppo il voto a coppie
    non lo vede). A parita' decide l'apprendimento a coppie; se anche quello e' muto, -1
    (totale dopo i figli). Le catene di un solo figlio (k=1) contano solo se la direzione
    scelta ha trovato almeno un totale vero (k>=2) nel documento: senza un gruppo reale, due
    importi uguali in fila sono spesso una coincidenza, non un mastro (80,80 non e' il totale
    di 50).

    La marcatura vera e propria e' un punto fisso, e ogni singola passata marca gia' subito
    (``_risolvi_totali``): un totale appena trovato resta al suo posto nella lista viva come
    ADDENDO per il livello sopra, mai piu' ri-marcabile - solo i suoi figli ne escono, per
    sempre. Un totale di livello superiore scansionato piu' avanti nella STESSA passata trova
    cosi' i totali sotto di lui gia' pronti (una passata sola basta per un documento con
    livelli coerenti in una direzione: "B) Immobilizzazioni" (= I+II+III) diventa raggiungibile
    anche se I, II, III sono a loro volta totali dei propri figli, e "Totale attivo" lo e'
    rispetto a B)+C)+...). Il giro esterno (k>=2 poi k=1, ripetuto finche' non emerge piu'
    nulla) resta comunque un punto fisso vero per i casi a piu' passate (un livello k=1 che ne
    sblocca uno k>=2 sopra, o viceversa). Senza tutto questo, un totale marcato usciva dalla
    lista viva per sempre e non poteva mai fare da addendo per il livello sopra (diagnosi
    AMBIENTA 2026-09-26: B, C, D e i due totali di stato patrimoniale restavano foglie non
    riconosciute anche a pagine complete)."""
    piu, meno = _conta_forzata(righe, 1), _conta_forzata(righe, -1)
    if piu != meno:
        direzione = 1 if piu > meno else -1
    else:
        voti = _voti_apprendimento(righe)
        direzione = voti.most_common(1)[0][0] if voti else -1

    per_lato = _per_lato(righe)
    valori = {lato: [r.valore for r in seq] for lato, seq in per_lato.items()}
    vivo = {lato: [True] * len(seq) for lato, seq in per_lato.items()}
    candidabile = {lato: [True] * len(seq) for lato, seq in per_lato.items()}

    trovati_totale = 0
    gruppo_visto = False
    cambiato = True
    while cambiato:
        cambiato = False
        for lato, seq in per_lato.items():
            n2 = _risolvi_totali(seq, valori[lato], vivo[lato], candidabile[lato], direzione, 2)
            if n2:
                gruppo_visto = True
                trovati_totale += n2
                cambiato = True
        if gruppo_visto:
            for lato, seq in per_lato.items():
                n1 = _risolvi_totali(seq, valori[lato], vivo[lato], candidabile[lato], direzione, 1)
                if n1:
                    trovati_totale += n1
                    cambiato = True
    return Counter({direzione: trovati_totale}) if trovati_totale else Counter()


def righe_da_pdf(file_path: str, pagine: set[int] | None, ruoli: list[str],
                 ocr_text: str | None = None) -> list[Riga]:
    from importers.detail_enrichment import collect_source_rows
    regola = regola_colonna(ruoli)
    out = []
    for r in collect_source_rows(file_path, ocr_text=ocr_text):
        if pagine and r.page not in pagine:
            continue
        out.append(Riga(id=r.id, pagina=r.page, lato=r.side, testo=etichetta(r.text),
                        valore=saldo(r, regola), sezione=r.statement))
    marca_totali(out)
    return out


def foglie(righe: list[Riga]) -> list[Riga]:
    return [r for r in righe if r.valore is not None and not r.totale and r.testo]
