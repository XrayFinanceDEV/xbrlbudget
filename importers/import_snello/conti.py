"""Dai percorsi di legge agli importi dei campi, con le regole contabili di sempre:
la colonna decide il lato, un fondo si sottrae al bene, nessun conto contato due volte."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from decimal import Decimal
from itertools import product

from calculations.ce_result import calculate_ce_result
from importers.import_snello.percorsi import (CONTROPARTE, NOMI, campo_da_percorso, completa,
                                              e_fondo, e_netto, e_risultato, famiglia, lato_di)
from importers.import_snello.risultato import (control_caption, has_account_code, prior_caption,
                                               sign_by_caption)
from importers.import_snello.verifica import misura, soglia
from importers.iv_cee_hierarchy import detail_fields

_C = Decimal("0.01")
_IMMOBILIZZAZIONI = ("sp02", "sp03", "sp04")
# Oltre questo numero di GRUPPI ambigui (le foglie identiche - stessa didascalia, stesso
# importo - contano una volta sola: round 3), provare tutte le 2**n combinazioni non e' piu'
# proponibile (8 gruppi = 256 fogli da ricalcolare): tutti "corrente", dichiarato, mai un
# tentativo parziale che sembrerebbe piu' sicuro di quanto sia.
_MAX_AMBIGUE_COMBINATORIE = 3
# Nessuna contropartita nota: la colonna resta la verita' sul lato, e l'importo va nel secchio
# esplicito di quel lato (credito se stampato fra gli attivi, debito se fra i passivi) - mai
# lasciato a rovesciare il segno di un campo TIER0 per un voto di famiglia.
_FALLBACK = {"att": "SPA.C.II.5-quater", "pas": "SPP.D.14"}
# Una scadenza (.E/.O) o un fondo (.F) non fa di un conto il padre di un altro: e' lo stesso
# sotto-conto, solo annotato entro/oltre l'esercizio o al netto del fondo - non un totale che i
# figli spiegherebbero. "SPA.C.II.5-quater.E" non e' figlio di "SPA.C.II.5-quater" (banco,
# 2026-09-26: 14.863,84 di massa vera persi perche' il primo veniva escluso come "padre con
# figli"); "SPP.D.4" resta figlio di "SPP.D", e "SPP.D.4.E" resta figlio di "SPP.D" (la scadenza
# e' in coda al codice del FIGLIO, non subito dopo il padre).
_SUFFISSI_SCADENZA = (".E", ".O")


def _e_discendente_vero(p: str, q: str) -> bool:
    if q == p or not q.startswith(p + "."):
        return False
    if e_fondo(q):
        return False
    return q[len(p):] not in _SUFFISSI_SCADENZA


def _corsia(f, due_lati: bool):
    return (1 if f.lato == "R" else 0) if due_lati else (f.valore >= 0)


# Fix round 2 (ruling del proprietario, 2026-09-28): il segno di un campo CE dipende dal MODO.
# In modo "conti" (da_foglie) ogni foglia porta una colonna fisica (lato L/R): la colonna
# decide, come applica_lato gia' fa per lo SP (vedi il ramo "cos"/"ric" del per_famiglia qui
# sotto - nessun campo a segno libero li', nemmeno ce10: la colonna lo governa come ogni altro).
# In modo "legge" (da_coppie) c'e' una sola colonna con un segno letterale: qui, e solo qui,
# alcuni campi restano a SEGNO LIBERO per natura - variazioni OIC che possono legittimamente
# ridurre il proprio raggruppamento - ce02 (A.2, variazioni rimanenze prodotti in corso/
# semilavorati/finiti), ce03 (A.3, variazioni lavori in corso su ordinazione - non ce03a, A.4
# incrementi di immobilizzazioni, che non e' una variazione), ce10 (B.11, variazione rimanenze
# materie prime, convenzione OIC: un aumento di giacenza riduce il costo). Nessun'altra voce
# IV-CEE e' una "variazione": ce09c/ce09d sono svalutazioni (sempre un costo, mai negative), gli
# aggregati ce18/ce19 sono gia' separati per segno (proventi/oneri straordinari), non voci nette.
# Task 27, item 6 (diagnosi budget_397): anche ce16 (17-bis, utili e perdite su cambi) e' un netto a
# segno libero - una perdita stampata (1.059) e' una perdita, non un utile: con ``abs`` il risultato
# si spostava di 2x il suo importo. ce13/ce14 (proventi da partecipazioni, altri proventi
# finanziari) restano a segno fisso: un provento non e' mai negativo.
_CE_SEGNO_LIBERO = {"ce02", "ce03", "ce10", "ce16"}

# Solo modo "legge" (da_coppie): RIMBORSO/RIMBORSI e RETTIFICA/RETTIFICHE sono state tolte dal
# giro precedente (fix round 1) - "Rimborsi" e' spesso una voce di ricavo NORMALE (TM 589: un
# leaf ce04 "Rimborsi" da 4.022,90, non una riduzione), e "rettifiche" e' un termine troppo
# generico per contare come riduzione esplicita. Restano solo le quattro didascalie che sono
# SEMPRE una riduzione del proprio campo, mai un conto a se': resi, sconti, abbuoni, storni.
_RETTIFICA_KEYWORDS = ("RESO", "RESI", "SCONTO", "SCONTI", "ABBUONO", "ABBUONI", "STORNO", "STORNI")


def _e_rettifica_esplicita(testo: str) -> bool:
    """Una didascalia di rettifica esplicita (resi, sconti, abbuoni, storni): una riduzione VERA
    del campo, dichiarata dal testo del conto - non dedotta da un voto su altre righe. Usata
    solo in modo "legge" (da_coppie), che non porta mai testo (nessuna coppia percorso/importo
    ha una didascalia libera): resta quindi sempre False li' - una precondizione strutturale
    del modo, non un difetto - documentata qui per chi estendesse ``da_coppie`` con un testo in
    futuro."""
    t = (testo or "").upper()
    return any(k in t for k in _RETTIFICA_KEYWORDS)


# ce02 (variazione rimanenze prodotti) e ce03 (incrementi per lavori interni) stanno nella sezione A
# (valore della produzione): seguono la convenzione di stampa dei RICAVI, mai quella dei costi.
# ce10 (OIC B.11) sta fra i costi e segue la convenzione dei costi (fix round 1 Task 24, F2:
# budget_297, ricavi positivi e costi negativi, ce02 +30.077 stampato letto -30.077, scarto 2x).
_CE_SEGNO_LIBERO_RICAVI = {"ce02", "ce03", "ce16"}


def _segno_ce_legge(codice: str, valore: Decimal, testo: str, convenzione: int,
                    convenzione_ricavi: int = 1) -> Decimal:
    """Segno di un campo CE in modo "legge" (da_coppie): un'unica colonna, un segno letterale.
    Un campo a segno fisso prende il valore assoluto, salvo una didascalia di rettifica
    esplicita (``_e_rettifica_esplicita``, mai vera qui: da_coppie non porta testo). Un campo a
    segno libero (``_CE_SEGNO_LIBERO``) prende il segno letto MOLTIPLICATO per la convenzione di
    stampa del documento (``convenzione``, +1 o -1: vedi ``_convenzione_costi`` in da_coppie) -
    la stessa convenzione di stampa che riguarda ogni altro costo della sezione riguarda anche
    lui (budget_115/297: costi stampati negativi, quindi ce10 letto -30.517 diventa +30.517 -
    fix round 1 lo lasciava invariato, ignorando la convenzione)."""
    if codice in _CE_SEGNO_LIBERO_RICAVI:
        return valore * convenzione_ricavi
    if codice in _CE_SEGNO_LIBERO:
        return valore * convenzione
    if _e_rettifica_esplicita(testo):
        return -abs(valore)
    return abs(valore)


def _netta_fondi_negativi(importi: dict) -> dict:
    """Un fondo puo' essere piu' fine del lordo stampato: se un dettaglio di immobilizzazioni
    (sp02/sp03/sp04) resta negativo dopo la sottrazione del fondo, l'importo si sposta sul
    valore diretto dell'aggregato e il dettaglio sparisce - senza dettaglio si netta
    all'aggregato."""
    importi = dict(importi)
    for aggregato in _IMMOBILIZZAZIONI:
        pieno = NOMI.get(aggregato)
        if not pieno:
            continue
        for dettaglio_pieno in detail_fields(pieno):
            codice = dettaglio_pieno.split("_")[0]
            v = importi.get(codice)
            if v is not None and v < 0:
                importi[aggregato] = importi.get(aggregato, Decimal(0)) + importi.pop(codice)
    return importi


def _clamp_immobilizzazioni_negative(bs: dict) -> list:
    """Un fondo non puo' mai superare il proprio cespite lordo: un'immobilizzazione netta
    ancora negativa a livello di AGGREGATO (dopo ``_netta_fondi_negativi``, che copre solo il
    dettaglio) e' sempre una misclassificazione, mai un valore IV-CEE valido. Si azzera - mai
    spostata su un altro campo, ne' lasciata negativa - e l'eccedenza tagliata si dichiara:
    stessa regola del vecchio importatore
    (situazione_contabile_parser.build_sp_from_vision, ~L5177-5185: "un fondo non puo' mai
    superare il proprio cespite lordo ... l'eccedenza tagliata e' massa che non si e' saputa
    collocare, quindi va nello stesso canale del resto")."""
    tagliate = []
    for breve in _IMMOBILIZZAZIONI:
        pieno = NOMI.get(breve)
        if pieno and bs.get(pieno, Decimal(0)) < 0:
            tagliate.append([pieno, str((-bs[pieno]).quantize(_C))])
            bs[pieno] = Decimal(0)
    return tagliate


def applica_lato(foglie, irrisolti: list | None = None) -> int:
    """Un conto il cui percorso sta dall'altra parte rispetto a dove e' stampato passa alla voce
    corrispondente del lato giusto (c/c fra le passivita' -> debiti verso banche). La colonna e' la
    verita' sul lato; la descrizione decide la voce. Senza una contropartita nota il conto resta
    comunque sul lato che la colonna dichiara: cade su un secchio esplicito (mai su un voto di
    segno che lo confonderebbe con un campo TIER0), e viene dichiarato in ``irrisolti`` se dato."""
    sp = [f for f in foglie if f.percorso and lato_di(f.percorso) in ("att", "pas") and not e_fondo(f.percorso)]
    due_lati = len({f.lato for f in sp} & {"L", "R"}) == 2
    peso = Counter()
    for f in sp:
        peso[(lato_di(f.percorso), _corsia(f, due_lati))] += abs(f.valore)
    lato_normale = {}
    for sez in ("att", "pas"):
        candidati = [(v, k) for (s, k), v in peso.items() if s == sez]
        if candidati:
            lato_normale[sez] = max(candidati)[1]
    if len(set(lato_normale.values())) < 2:
        return 0
    n = 0
    for f in sp:
        if e_netto(f.percorso):
            # capitale/riserve/risultato: contano per stabilire il lato normale delle altre
            # voci della sezione, ma non sono mai loro stessi un bersaglio di correzione - non
            # esiste una contropartita per un conto che cambia lato col proprio segno.
            continue
        if _corsia(f, due_lati) == lato_normale[lato_di(f.percorso)]:
            continue
        corretto = False
        for prefisso, destinazione in CONTROPARTE.items():
            if f.percorso == prefisso or f.percorso.startswith(prefisso + "."):
                f.percorso = destinazione
                n += 1
                corretto = True
                break
        if not corretto:
            sezione_stampata = "att" if _corsia(f, due_lati) == lato_normale["att"] else "pas"
            originale, valore = f.percorso, abs(f.valore)
            f.percorso = _FALLBACK[sezione_stampata]
            f.valore = valore
            if irrisolti is not None:
                irrisolti.append([f.id, originale, str(valore.quantize(_C))])
    return n


_CODICE_CONTO = re.compile(r"^[\d./*]+$")


def _prima_parola(testo: str) -> str:
    toks = (testo or "").split()
    return toks[0] if toks else ""


def _ha_codice_conto(testo: str) -> bool:
    """Vero se la prima parola del testo e' un codice di conto (solo cifre, punti, slash,
    asterischi): lo stesso test del vecchio parser
    (situazione_contabile_parser.py, righe 3161/3452/3521) per distinguere un mastro vero da
    una didascalia di contesto."""
    return bool(_CODICE_CONTO.match(_prima_parola(testo)))


# Le stesse parole che il vecchio parser usa per riconoscere una riga di controllo/subtotale
# (is_control in _be_collect_side_facts, situazione_contabile_parser.py ~L3120-3122: 'TOTALE',
# 'PAREGGIO'), estese a SALDO FINALE/GENERALE: un totale stampato con un pseudo-codice davanti
# ('40/99999 TOTALE DEBITI V/FORNITORI') non e' un conto, anche se il codice lo fa sembrare
# tale - riclassificarlo raddoppierebbe la massa che i conti veri gia' spiegano (review
# round 1, 2026-09-27).
_PAROLE_CONTROLLO = ("TOTALE", "PAREGGIO", "SALDO FINALE", "SALDO GENERALE")


def _e_riga_di_controllo(testo: str) -> bool:
    d = (testo or "").upper()
    return any(p in d for p in _PAROLE_CONTROLLO)


# Tag interni del vecchio classificatore CE che NON sono nomi di campo (situazione_contabile_
# parser.py ~L1199-1237, chiamante di _classify_ce_costi/_classify_ce_ricavi; l'assegnazione
# finale e' a ~L1500-1502): usarli verbatim come percorso forzato fa scartare la foglia in
# silenzio da completa() (NOMI non conosce questi nomi), mentre diag dichiarerebbe un recupero
# che non c'e' mai stato (review round 1, 2026-09-27: "55/01000 ACCANTONAMENTO TFR" 300
# spariva). Si traduce nel campo VERO che il vecchio chiamante scrive alla fine:
#   - 'ce01_return' (resa/sconto letta fra i costi) -> 'ce01' (ce01_total - ce01_returns)
#   - 'ce13_cost'   (proventi da partecip. letti fra i costi) -> 'ce13' (ce13 - entry.amount)
#   - 'ce10_close'  (rimanenze finali lette fra i ricavi) -> 'ce10' (opening - closing)
#   - 'ce08a_tfr'   (e' gia' il dettaglio vero, solo rinominato) -> 'ce08a' (ce08a_tfr_accrual)
# Fix round 2 (ruling del proprietario, 2026-09-28): non serve piu' marcare i primi tre come
# riduzione esplicita - la foglia entra nel voto di colonna di ``da_foglie`` (sotto) con la
# FAMIGLIA del campo tradotto ('ce01'/'ce13'/'ce10', non piu' il tag grezzo), e siccome questi
# tre tag esistono solo quando la foglia e' fisicamente nella colonna OPPOSTA alla propria vera
# famiglia (e' li' che classify_costi/classify_ricavi trova un ricavo fra i costi, un provento
# fra i costi, una rimanenza finale fra i ricavi), il voto di colonna la marca gia' "fuori
# colonna" da solo - lo stesso risultato di prima, senza bisogno di un marcatore apposito.
_TAG_CE_INTERNI = {"ce01_return": "ce01", "ce13_cost": "ce13", "ce10_close": "ce10",
                   "ce08a_tfr": "ce08a"}


def _voto_direzione_ce(foglie) -> tuple[dict, bool]:
    """Vota, sulle sole foglie CE gia' classificate a un campo reale, quale corsia fisica e'
    normalmente 'cos' (costi), quale 'ric' (ricavi) - stesso principio del voto di lato usato
    per attivo/passivo in applica_lato: l'ordine testuale delle intestazioni non e' la verita'
    (budget_405), la maggioranza dei conti gia' letti lo e'. Serve a scegliere IL
    classificatore giusto (classify_costi o classify_ricavi) per una foglia non instradata, mai
    a provare entrambi alla cieca - una parola di ricavo letta fra i costi (RICAVI, PROVENTI+
    PARTECIP) darebbe uno specifico su entrambi i lati, e la foglia resterebbe sempre esclusa.

    Voto per CONTEGGIO (fix round 2, 2026-09-28, diagnosi budget_624): pesare in euro lascia
    un'unica riga enorme fuori posto dominare la scelta della direzione - lo stesso difetto
    del voto di segno gia' corretto in ``da_foglie`` qui sotto, sulla stessa colonna."""
    ce = [f for f in foglie if f.percorso and lato_di(f.percorso) == "ce"]
    due_lati = len({f.lato for f in ce} & {"L", "R"}) == 2
    peso = Counter()
    for f in ce:
        codice = campo_da_percorso(f.percorso)
        if codice is None:
            continue
        peso[(famiglia(codice), _corsia(f, due_lati))] += 1
    normale = {}
    for sez in ("cos", "ric"):
        candidati = [(v, k) for (s, k), v in peso.items() if s == sez]
        if candidati:
            normale[sez] = max(candidati)[1]
    return normale, due_lati


def _direzione_ce(f, normale: dict, due_lati: bool) -> str | None:
    if len(normale) < 2 or len(set(normale.values())) < 2:
        return None
    corsia = _corsia(f, due_lati)
    for direzione, sezione in (("costi", "cos"), ("ricavi", "ric")):
        if normale.get(sezione) == corsia:
            return direzione
    return None


def riclassifica_ignote(foglie, diag: dict) -> None:
    """Una foglia marcata 'X' da Qwen, o rimasta senza percorso anche al secondo giro, il cui
    testo comincia con un codice di conto ('40/00000 DEBITI V/FORNITORI') e non e' una riga di
    controllo/subtotale, e' massa vera che il modello ha rinunciato a instradare. Si riprova
    coi classificatori a parole del vecchio importatore
    (situazione_contabile_parser.classify_attivo/classify_passivo per lo SP,
    classify_costi/classify_ricavi + _resolve_ce_field per il CE), mai reinventati qui.

    Per lo SP si prova sia l'ipotesi attivo sia quella passivo sulla stessa descrizione, e si
    usa il risultato solo quando UNA sola delle due e' specifica (non il ripiego generico del
    classificatore: sp06) - non c'e' collisione strutturale fra le due tabelle. Per il CE la
    direzione si vota sulla corsia fisica (``_voto_direzione_ce``/``_direzione_ce``: stesso
    principio del voto di lato SP) e si chiama SOLO il classificatore di quella direzione, mai
    entrambi: una parola di ricavo letta fra i costi (RICAVI, PROVENTI+PARTECIP) matcherebbe
    specificamente su tutte e due le tabelle, e "provarle entrambe" lascerebbe sempre due
    candidati. Senza un'ancora votata su entrambe le direzioni, nessuna scommessa.

    Il campo trovato passa da ``_TAG_CE_INTERNI`` quando e' un tag interno del vecchio
    classificatore CE (mai un nome di campo: ce01_return/ce13_cost/ce10_close/ce08a_tfr) e,
    in ogni caso, deve comparire in ``percorsi.NOMI`` - altrimenti resta X/non mappata (mai un
    campo inventato: catture anche gli altri tag interni non tradotti, es. 'depr_sp02',
    'deduct_crediti', che classify_passivo puo' restituire come "specifico").

    Muta ``f.percorso`` sul posto con un marcatore ``'#<campo>'`` che ``campo_da_percorso`` non
    traduce: ``da_foglie`` lo riconosce all'inizio del proprio giro e la foglia entra nel voto di
    colonna (per il CE) o di lato (per lo SP) come qualunque altra foglia gia' classificata - e'
    cosi', non con un nuovo calcolo, che il netto Dare/Avere di uno stesso mastro si ottiene
    (FORMETAL, banco 2026-09-26: '40/00000 DEBITI V/FORNITORI' 13.542,00 e 348.578,85 su lati
    opposti -> sp16d netto 335.036,85). Per il CE (fix round 2, 2026-09-28), un tag interno che
    era una riduzione implicita (ce01_return/ce13_cost/ce10_close) resta tale da solo: la foglia
    e' fisicamente sulla colonna OPPOSTA alla famiglia del campo tradotto (e' per questo che
    classify_costi/classify_ricavi l'hanno trovata li'), e il voto di colonna di ``da_foglie``
    la marca "fuori colonna" - una riduzione - senza bisogno di saperlo in anticipo."""
    from importers.situazione_contabile_parser import (
        TIER0_FIELDS, _resolve_ce_field, classify_attivo, classify_costi, classify_passivo,
        classify_ricavi)

    normale_ce, due_lati_ce = _voto_direzione_ce(foglie)

    for f in foglie:
        if f.percorso not in ("X", None) or not f.testo or not _ha_codice_conto(f.testo):
            continue
        if _e_riga_di_controllo(f.testo):
            continue
        desc = " ".join(f.testo.split()[1:]).upper().strip()
        if not desc:
            continue
        if f.sezione == "ce":
            direzione = _direzione_ce(f, normale_ce, due_lati_ce)
            if direzione is None:
                continue
            classify = classify_costi if direzione == "costi" else classify_ricavi
            c, specifico = classify(desc)
            # classify_costi/classify_ricavi arriva a un campo piu' fine (es. 'ce08b'), che
            # _resolve_ce_field non conosce (la sua allowlist di direzione vede solo gli
            # aggregati: 'ce08'): tenerlo come prima fonte, l'albero solo di ripiego quando la
            # tabella a parole non e' specifica.
            campo_grezzo = c if specifico else _resolve_ce_field(desc, direzione)
            if campo_grezzo is None:
                continue
            campo = _TAG_CE_INTERNI.get(campo_grezzo, campo_grezzo)
            if campo in TIER0_FIELDS or campo not in NOMI:
                continue
            diag["riclassificati_vecchio_parser"].append(
                [f.id, f.testo[:60], campo, str(f.valore.quantize(_C))])
            f.percorso = f"#{campo}"
        else:
            candidati: set = set()
            for classify in (classify_attivo, classify_passivo):
                campo, specifico = classify(desc)
                if specifico and campo not in TIER0_FIELDS and campo in NOMI:
                    candidati.add(campo)
            if len(candidati) == 1:
                campo = candidati.pop()
                diag["riclassificati_vecchio_parser"].append(
                    [f.id, f.testo[:60], campo, str(f.valore.quantize(_C))])
                f.percorso = f"#{campo}"


def da_foglie(foglie):
    """Percorsi di legge -> campi, con una regola in piu' per il risultato d'esercizio (modo
    "conti", Task 14 2026-09-26): il corrente non entra MAI dalle righe stampate, sp13 e'
    sempre l'utile del CE (``calculate_ce_result``). Riusa le regole del vecchio parser
    best-effort (``importers.import_snello.risultato``, adattatori di
    ``situazione_contabile_parser``) invece di reinventarle:

      1. una didascalia di ESERCIZI PRECEDENTI (qualunque percorso Qwen le abbia dato: 'IX' per
         un errore del modello conta comunque) va a sp12g, col segno della didascalia;
      2. un percorso "R" o "SPP.A.IX" con una didascalia di pareggio/controllo dichiarata
         (TOTALE A PAREGGIO, DIFFERENZA insieme ad ATTIVO/PASSIVO/DARE/AVERE, SBILANCIO da
         solo - MAI la sola frase del risultato, corrente o precedente che sia: quella e'
         esattamente il caso che il punto 4 deve risolvere, round 2) si esclude e basta, mai
         sommata - MAI su un percorso gia' risolto a un campo normale (fix round 1, review
         2026-09-26: "Differenza cambi attivi"/CE.C.17-bis e "Totale rimanenze iniziali" sono
         conti veri, non righe di pareggio, e la didascalia non deve mai scavalcare un percorso
         classificato);
      3. un percorso "R" o "SPP.A.IX" la cui didascalia comincia con un codice di conto
         (``has_account_code``, round 2, banco FORMETAL-TEST) e' SEMPRE l'anno precedente,
         deterministico: durante l'anno il risultato corrente non e' mai registrato su un
         conto, solo il pregresso puo' esserlo ("28/45/090 RISULTATO DI ESERCIZIO" e' un vero
         conto di patrimonio netto, non la riga di quadratura);
      4. un percorso "R" o "SPP.A.IX" senza codice conto e la cui didascalia non e' ne'
         precedente ne' di pareggio/controllo e' ambiguo: si prova ogni combinazione
         corrente/precedente (fino a 3 GRUPPI ambigui: oltre, tutti "corrente" e si dichiara)
         DOPO aver costruito il resto del foglio, e vince quella che fa quadrare meglio -
         owner: "a volte c'e' scritto risultato ma in realta' e' il risultato dell'anno
         precedente, mentre quello di quest'anno e' la differenza". Due foglie ambigue
         IDENTICHE (stessa didascalia, stesso importo: lo stesso risultato stampato due volte,
         budget_132, round 3) formano UN solo gruppo con un solo destino - mai una si' e una
         no, che spaccherebbe una riga sola in un conto vero e uno escluso a caso.

    ``risultato_duplicato`` dichiara le foglie ambigue oltre la prima di un gruppo identico
    (round 3): il vecchio dedup-per-valore (pre-Task 14) riguardava le righe che finivano
    sommate in sp13 direttamente, e nessuna ci finisce piu' per quella via - ma un duplicato
    letterale fra le foglie ambigue e' un problema diverso, riapparso quando quelle foglie
    vengono valutate una per una invece che in blocco (round 2)."""
    diag = {"non_mappati": [], "escluse": [], "risultato_stampato": None, "lato_corretti": 0,
            "lato_irrisolti": [], "risultato_duplicato": [], "padri_esclusi": [],
            "risultato_precedente": [], "risultato_escluso": [], "risultato_ambiguo": None,
            "riclassificati_vecchio_parser": [], "ce_segno_forzato": [], "grezzo_sp": {}}
    diag["lato_corretti"] = applica_lato(foglie, diag["lato_irrisolti"])
    riclassifica_ignote(foglie, diag)
    irrisolti_ids = {r[0] for r in diag["lato_irrisolti"]}
    due_lati = len({f.lato for f in foglie} & {"L", "R"}) == 2
    # Fix round 3 (ruling del proprietario, 2026-09-28, diagnosi TM 589/590): la massa grezza
    # per lato (Task 21, "grezzo": la base di confronto per l'ancora dei totali stampati sui
    # prospetti a sezioni contrapposte) si accumula QUI, sulle SOLE foglie SP che ENTRANO
    # davvero nel risultato - mai su ``foglie(righe)`` prima di questa funzione (il difetto:
    # una riga come "Totale Attivita'" che marca_totali lascia viva come foglia, perche' i
    # suoi figli non sono nella pagina letta o non si risolvono, veniva sommata nel grezzo
    # PRIMA che da_foglie la scartasse come 'X'/escluse - un totale duplicato che raddoppia la
    # massa, TM 589: grezzo attivo 2x il vero attivo). Si aggiorna a OGNI punto del ciclo dove
    # una foglia SP (``f.sezione == "bs"``) contribuisce davvero al foglio finale - mai per le
    # foglie escluse/non mappate/pareggio/ambigue non ancora risolte (quelle ultime si sommano
    # dopo, quando la loro sorte e' decisa).
    grezzo_sp: dict[str, Decimal] = {}

    def _grezzo(f) -> None:
        if f.sezione == "bs":
            grezzo_sp[f.lato] = grezzo_sp.get(f.lato, Decimal(0)) + f.valore

    # Un percorso stampato ACCANTO a un percorso piu' specifico che lo prolunga (es. "SPP.D"
    # bare insieme a "SPP.D.4") e' lo stesso totale gia' spiegato dai figli: va escluso, mai
    # sommato di nuovo (come gia' fa da_coppie in modo "legge"). Un fondo o una scadenza da
    # sole (.F/.E/.O) non contano mai come figlio ai fini di questa regola (_e_discendente_vero).
    tutti_percorsi = [f.percorso for f in foglie if f.percorso]
    per_famiglia = defaultdict(list)
    ambigue: list = []
    pregresso = Decimal(0)
    for f in foglie:
        if f.percorso and f.percorso.startswith("#"):
            # marcatore di riclassifica_ignote: gia' un campo corto valido (mai un percorso di
            # legge). Riceve un segno dal voto di colonna/lato come qualunque altra foglia, ma
            # non VOTA (terzo campo True): e' per costruzione una foglia che il classificatore
            # diretto ha rinunciato a instradare, spesso proprio perche' fisicamente fuori
            # posto (ce01_return/ce13_cost/ce10_close) - lasciarla votare la propria stessa
            # colonna falserebbe il voto con un pareggio auto-riferito (test preesistente,
            # ce10_close: un solo altro conto "cos" vero e questa foglia stessa, 1 a 1).
            codice = f.percorso[1:]
            if famiglia(codice) in ("att", "pas"):
                _grezzo(f)
            per_famiglia[famiglia(codice)].append((f, codice, True))
            continue
        if f.percorso and e_risultato(f.percorso):
            diag["risultato_stampato"] = str(abs(f.valore).quantize(_C))
            continue
        if f.percorso == "X":
            diag["escluse"].append([f.id, f.percorso, str(f.valore.quantize(_C))])
            continue
        if not f.percorso:
            # mai classificata (nemmeno al secondo giro di lettura): massa reale non
            # classificata, non una riga dichiarata non contabile - non va confusa con 'X'.
            diag["non_mappati"].append([f.id, "", str(f.valore.quantize(_C))])
            continue
        if any(_e_discendente_vero(f.percorso, q) for q in tutti_percorsi):
            diag["padri_esclusi"].append([f.id, f.percorso, str(f.valore.quantize(_C))])
            continue

        # --- risultato d'esercizio: mai dalle righe stampate (regole del vecchio parser) ---
        if prior_caption(f.testo):
            v = sign_by_caption(f.testo, f.valore)
            pregresso += v
            _grezzo(f)
            diag["risultato_precedente"].append([f.id, f.percorso, str(v.quantize(_C))])
            continue
        if f.percorso == "SPP.A.VIII":
            # Qwen riserva VIII al portato a nuovo: una didascalia non riconosciuta (generica,
            # o mancante) non toglie fiducia al percorso esplicito, e il segno resta quello
            # letto (nessuna contropartita per un conto di netto, come applica_lato).
            pregresso += f.valore
            _grezzo(f)
            diag["risultato_precedente"].append([f.id, f.percorso, str(f.valore.quantize(_C))])
            continue
        if f.percorso in ("R", "SPP.A.IX"):
            # control_caption e' un test sulla didascalia: si applica SOLO qui, su un percorso
            # gia' non classificato come conto vero (fix round 1, review 2026-09-26). Non deve
            # mai girare su un percorso risolto a un campo normale, o "Differenza cambi attivi"
            # (CE.C.17-bis, un conto vero) e "Totale rimanenze iniziali" sparirebbero solo
            # perche' la didascalia somiglia a un rigo di pareggio.
            if control_caption(f.testo):
                diag["risultato_escluso"].append([f.id, f.percorso, str(f.valore.quantize(_C))])
            elif has_account_code(f.testo):
                # Round 2 (banco FORMETAL-TEST): un risultato con un codice conto davanti e' un
                # vero conto di patrimonio netto - durante l'anno il corrente non e' mai
                # registrato su un conto - quindi e' SEMPRE l'anno precedente, deterministico,
                # mai un candidato per l'ipotesi ambigua (che resta per le righe di quadratura
                # senza codice, "candidate current" per la classificazione del vecchio parser).
                pregresso += f.valore
                _grezzo(f)
                diag["risultato_precedente"].append([f.id, f.percorso, str(f.valore.quantize(_C))])
            else:
                ambigue.append(f)
            continue

        codice = campo_da_percorso(f.percorso)
        if codice is None:
            diag["non_mappati"].append([f.id, f.percorso, str(f.valore.quantize(_C))])
            continue
        if famiglia(codice) in ("att", "pas"):
            _grezzo(f)
        per_famiglia[famiglia(codice)].append((f, codice, False))
    importi = defaultdict(Decimal)
    for fam, elementi in per_famiglia.items():
        if fam in ("cos", "ric"):
            # Fix round 2 (ruling del proprietario, 2026-09-28): "la colonna decide, contro la
            # famiglia del campo" - lo stesso principio del voto di lato SP (applica_lato),
            # applicato al CE. Si vota per CONTEGGIO (mai per euro: budget_624, 5 conti veri su
            # "L" contro 1 solo fuori posto su "R" da 1.468.999,24 - pesare in euro fa vincere
            # l'unico conto sbagliato) quale corsia e' normale per "cos", quale per "ric". Una
            # foglia sulla propria colonna normale porta il segno letto COSI' COM'E' (un importo
            # gia' negativo dentro la propria colonna resta una vera contropartita, mai
            # "raddrizzato" a positivo); una foglia sulla colonna dell'ALTRA famiglia e' sempre
            # una riduzione (-abs), a prescindere dal segno letto - fisicamente fuori posto,
            # quindi il segno letto da solo non e' piu' attendibile. ce10 conta come "cos" (un
            # costo, sp05a lato materie prime), ce02/ce03 come "ric" (RICAVI): nessuna eccezione
            # "a segno libero" qui - quella esiste solo in modo "legge" (da_coppie), dove non
            # c'e' alcuna colonna fisica da cui dedurre nulla.
            if not due_lati:
                # Colonna unica: _corsia degenera al segno stesso (nessuna colonna fisica da
                # cui dedurre nulla - un "voto" qui sarebbe un voto sul segno letto, che e'
                # esattamente cio' che non ci si puo' fidare), quindi ogni campo prende il
                # valore assoluto, come un campo a segno fisso (test preesistente,
                # colonna_unica: CE.A.1 letto -60 e' comunque un ricavo vero, +60,00).
                for f, codice, _t in elementi:
                    v = abs(f.valore)
                    if v != f.valore:
                        diag["ce_segno_forzato"].append(
                            [f.id, codice, str(f.valore.quantize(_C)), str(v.quantize(_C))])
                    importi[codice] += v
                continue
            # Il voto NON include le foglie tradotte da riclassifica_ignote (terzo campo True):
            # sono per costruzione conti che il classificatore diretto ha rinunciato a
            # instradare, spesso proprio perche' fisicamente fuori posto (ce01_return/
            # ce13_cost/ce10_close) - lasciarle votare la propria stessa colonna falserebbe il
            # voto con un pareggio auto-riferito (test preesistente, ce10_close: un solo altro
            # conto "cos" vero contro questa foglia stessa, 1 a 1 invece di una maggioranza
            # chiara). Il segno si applica comunque a TUTTE le foglie della famiglia, tradotte
            # incluse: solo il voto le esclude, non l'esito.
            voti_colonna = Counter()
            for f, codice, tradotta in elementi:
                if tradotta:
                    continue
                voti_colonna[(famiglia(codice), _corsia(f, due_lati))] += 1
            normale = {}
            for sez in ("cos", "ric"):
                candidati = [(v, k) for (s, k), v in voti_colonna.items() if s == sez]
                if candidati:
                    normale[sez] = max(candidati)[1]
            for f, codice, _t in elementi:
                corsia = _corsia(f, due_lati)
                atteso = normale.get(famiglia(codice))
                v = f.valore if (atteso is None or corsia == atteso) else -abs(f.valore)
                if v != f.valore:
                    diag["ce_segno_forzato"].append(
                        [f.id, codice, str(f.valore.quantize(_C)), str(v.quantize(_C))])
                importi[codice] += v
            continue
        # SP (att/pas): voto per CONTEGGIO invariato (Task 22, G2 originale) - qui un fondo/una
        # contropartita di lato restano un voto fra conti fisicamente sullo stesso prospetto,
        # non toccato dal ruling sul segno CE.
        voti_corsia, euro_corsia = Counter(), Counter()
        voti_segno, euro_segno = Counter(), Counter()
        for f, _, _t in elementi:
            if e_fondo(f.percorso) or f.id in irrisolti_ids:
                continue
            if due_lati and e_netto(f.percorso):
                # su un prospetto Dare/Avere il capitale/riserve/risultato non deve pesare sul
                # voto delle altre voci passive: un utile grande, stampato Avere per natura,
                # sposterebbe il "lato normale" della famiglia e farebbe girare di segno un
                # debito vero. A colonna unica (senza Dare/Avere) resta nel voto come sempre.
                continue
            corsia, positivo = (_corsia(f, True) if due_lati else 0), f.valore >= 0
            voti_corsia[corsia] += 1
            euro_corsia[corsia] += abs(f.valore)
            voti_segno[positivo] += 1
            euro_segno[positivo] += abs(f.valore)
        corsia_n = (max(voti_corsia, key=lambda k: (voti_corsia[k], euro_corsia[k]))
                    if voti_corsia else 0)
        positivo_n = (max(voti_segno, key=lambda k: (voti_segno[k], euro_segno[k]))
                      if voti_segno else True)
        for f, codice, _t in elementi:
            if due_lati and e_netto(f.percorso):
                # colonna=lato NON vale per capitale/riserve/risultato: un utile e una perdita
                # hanno naturalmente lato invertito. Nessuna contropartita per ribaltarli: il
                # valore letto porta gia' il segno giusto (una perdita e' negativa).
                importi[codice] += f.valore
                continue
            v = abs(f.valore)
            if e_fondo(f.percorso):
                contro = True
            elif f.id in irrisolti_ids:
                # gia' sul lato giusto (la colonna l'ha deciso in applica_lato): il voto di
                # famiglia non lo deve piu' ribaltare.
                contro = False
            else:
                corsia = _corsia(f, True) if due_lati else 0
                contro = (corsia != corsia_n) ^ ((f.valore >= 0) != positivo_n)
            importi[codice] += -v if contro else v
    if pregresso:
        importi["sp12g"] += pregresso.quantize(_C)
    bs, ce = completa(_netta_fondi_negativi(dict(importi)))
    diag["immobilizzazioni_negative_tagliate"] = _clamp_immobilizzazioni_negative(bs)

    # Il risultato corrente non e' mai una somma di righe stampate: e' sempre l'utile del CE
    # gia' costruito sopra (diagnose, never fabricate - la memoria/CLAUDE.md: "The RISULTATO
    # e' la balancing figure ... derive il risultato dal CE"). Una foglia ambigua (percorso "R"
    # o "SPP.A.IX", senza codice conto, didascalia che non dice ne' precedente ne' controllo)
    # puo' pero' essere in realta' un pregresso non riconosciuto come tale: si sceglie, PER
    # OGNI FOGLIA AMBIGUA INDIPENDENTEMENTE (round 2, banco FORMETAL-TEST: due righe di
    # risultato diverse - una con codice conto, gia' instradata sopra, una senza - non sono
    # la stessa ipotesi), la combinazione corrente/precedente che fa quadrare meglio il resto
    # del foglio - mai quella che quadra peggio - e se nessuna combinazione chiude entro soglia
    # si tengono tutte "corrente" (escluse) e si lascia che la verifica dichiari lo scarto vero
    # (non e' un risultato piu' grande da inventare, e' massa mancante da recuperare altrove).
    utile_ce = calculate_ce_result(ce).net_profit.quantize(_C)
    if not ambigue:
        bs["sp13_utile_perdita"] = utile_ce
        diag["grezzo_sp"] = dict(grezzo_sp)
        return bs, ce, diag

    candidati = [[f.id, f.percorso, str(f.valore.quantize(_C))] for f in ambigue]
    importo_totale = str(sum((f.valore for f in ambigue), Decimal(0)).quantize(_C))

    # Round 3: due foglie ambigue IDENTICHE (stessa didascalia normalizzata, stesso importo,
    # nessun codice conto - altrimenti sarebbero gia' finite nel ramo deterministico) sono lo
    # stesso risultato stampato due volte (budget_132), non due conti distinti: condividono UN
    # solo destino nella ricerca combinatoria, mai una si' e una no (spaccarle inventerebbe una
    # riserva che per caso quadra il foglio). Le foglie oltre la prima di un gruppo identico si
    # dichiarano in risultato_duplicato e il gruppo pesa per l'INTERA somma quando l'ipotesi e'
    # "precedente" - la stessa somma che pooling di gruppo dava prima del round 2, ma solo per i
    # duplicati veri: due foglie con importo diverso restano due candidati indipendenti.
    gruppi: dict[tuple, list] = {}
    ordine_gruppi: list[tuple] = []
    for f in ambigue:
        chiave = (f.testo.strip().upper(), f.valore.quantize(_C))
        if chiave not in gruppi:
            gruppi[chiave] = []
            ordine_gruppi.append(chiave)
        gruppi[chiave].append(f)
    for membri in gruppi.values():
        for extra in membri[1:]:
            diag["risultato_duplicato"].append([extra.id, extra.percorso, str(extra.valore.quantize(_C))])
    gruppi_ambigui = [gruppi[chiave] for chiave in ordine_gruppi]

    if len(gruppi_ambigui) > _MAX_AMBIGUE_COMBINATORIE:
        # Troppi gruppi ambigui per provare ogni combinazione (2**n esploderebbe): si tengono
        # tutti "corrente" e si dichiara il fatto, mai un tentativo parziale non verificato.
        bs["sp13_utile_perdita"] = utile_ce
        diag["risultato_ambiguo"] = {"ipotesi": "corrente", "importo": importo_totale,
                                     "candidati": candidati, "motivo": "troppe_foglie_ambigue"}
        diag["grezzo_sp"] = dict(grezzo_sp)
        return bs, ce, diag

    def _foglio_per_assegnazione(precedenti: tuple[bool, ...]) -> dict:
        somma = sum((sum((f.valore for f in gruppo), Decimal(0))
                    for gruppo, prec in zip(gruppi_ambigui, precedenti) if prec), Decimal(0))
        candidato = dict(bs)
        if somma:
            candidato["sp12g_utili_perdite_portati"] = (
                Decimal(candidato.get("sp12g_utili_perdite_portati", 0)) + somma).quantize(_C)
            candidato["sp12_riserve"] = (
                Decimal(candidato.get("sp12_riserve", 0)) + somma).quantize(_C)
        candidato["sp13_utile_perdita"] = utile_ce
        return candidato

    tutte_corrente = (False,) * len(gruppi_ambigui)
    bs_corrente = _foglio_per_assegnazione(tutte_corrente)
    m_corrente = misura(bs_corrente, ce, None, forma="bilancio")
    scarto_corrente = abs(m_corrente["scarto_sp"])
    s = soglia(m_corrente["attivo"])

    migliore_assegnazione, migliore_bs, migliore_scarto = tutte_corrente, bs_corrente, scarto_corrente
    for precedenti in product((False, True), repeat=len(gruppi_ambigui)):
        if precedenti == tutte_corrente:
            continue
        candidato = _foglio_per_assegnazione(precedenti)
        scarto = abs(misura(candidato, ce, None, forma="bilancio")["scarto_sp"])
        if scarto < migliore_scarto:
            migliore_assegnazione, migliore_bs, migliore_scarto = precedenti, candidato, scarto

    if migliore_assegnazione != tutte_corrente and migliore_scarto <= s:
        bs = migliore_bs
    else:
        bs, migliore_assegnazione = bs_corrente, tutte_corrente

    diag["risultato_ambiguo"] = {
        "ipotesi": "precedente" if any(migliore_assegnazione) else "corrente",
        "importo": importo_totale,
        "candidati": candidati,
    }
    if len(gruppi_ambigui) > 1:
        diag["risultato_ambiguo"]["per_foglia"] = [
            "precedente" if prec else "corrente" for prec in migliore_assegnazione]
    # Un gruppo ambiguo assegnato "precedente" entra nel pregresso (sp12g, sopra): la stessa
    # massa entra ora anche nel grezzo per lato, per lo stesso motivo (e' un vero conto di
    # patrimonio netto, solo scoperto a posteriori) - un gruppo "corrente" resta escluso dal
    # grezzo come dal foglio (sp13 viene sempre dal CE).
    for gruppo, prec in zip(gruppi_ambigui, migliore_assegnazione):
        if prec:
            for f in gruppo:
                _grezzo(f)
    diag["grezzo_sp"] = dict(grezzo_sp)
    return bs, ce, diag


def _convenzione_costi(voci) -> int:
    """La convenzione di stampa dei costi in modo "legge": +1 se il documento stampa i costi a
    segno fisso positivi (il caso normale), -1 se li stampa negativi (budget_664/115/297: ogni
    voce di costo fra parentesi, una convenzione di stampa, non un segno semantico riga per
    riga). Votata per CONTEGGIO sui soli campi CE a segno FISSO della famiglia "cos" (mai i
    campi a segno libero, ce02/ce03/ce10, che non dicono nulla sulla convenzione - il loro
    stesso segno dipende dalla convenzione, non puo' votarla) - mai per euro, stesso principio
    del voto di colonna in da_foglie."""
    segni = Counter()
    for _, v, codice in voci:
        if v != 0 and codice.startswith("ce") and famiglia(codice) == "cos" and codice not in _CE_SEGNO_LIBERO:
            segni[v < 0] += 1
    return -1 if segni.get(True, 0) > segni.get(False, 0) else 1


def _convenzione_ricavi(voci) -> int:
    """+1 se il documento stampa i ricavi a segno fisso (ce01, ce04) positivi, -1 se li stampa
    negativi: voto per CONTEGGIO, come ``_convenzione_costi``. Decide il segno di ce02/ce03."""
    segni = Counter()
    for _, v, codice in voci:
        if v != 0 and codice.startswith("ce") and famiglia(codice) == "ric" and codice not in _CE_SEGNO_LIBERO:
            segni[v < 0] += 1
    return -1 if segni.get(True, 0) > segni.get(False, 0) else 1


def da_coppie(coppie):
    """Schema di legge: coppie (percorso, importo) come stampate. Un percorso che ha un discendente
    fra le coppie e' un totale e cade; una voce ripetuta conta una volta; un fondo si sottrae.

    A differenza di ``da_foglie`` (modo "conti"), qui non c'e' alcuna colonna fisica da cui
    dedurre un lato: il percorso e' gia' la voce di legge (non un mastro di ledger), quindi non
    c'e' mai una didascalia di rettifica da leggere (``_e_rettifica_esplicita`` non trova mai
    nulla: ``da_coppie`` non porta testo). Un campo CE a segno fisso prende il valore assoluto;
    un campo a segno libero (``_CE_SEGNO_LIBERO``: ce02, ce03, ce10, ce16) prende il segno letto
    MOLTIPLICATO per la convenzione di stampa del documento (``_convenzione_costi``, fix round 2,
    2026-09-28: il fix precedente lasciava il segno libero invariato, ignorando che la stessa
    convenzione che stampa i costi negativi riguarda anche un campo a segno libero -
    budget_115/297, ce10 letto -30.517/-7.831 con costi in convenzione negativa diventa
    +30.517/+7.831)."""
    diag = {"non_mappati": [], "escluse": [], "risultato_stampato": None, "lato_corretti": 0,
            "lato_irrisolti": [], "risultato_duplicato": [], "padri_esclusi": [],
            "ce_segno_forzato": []}
    viste, uniche = set(), []
    for p, v in coppie:
        if p not in viste:
            viste.add(p)
            uniche.append((p, Decimal(v)))
    tutti = [p for p, _ in uniche]
    voci: list[tuple[str, Decimal, str]] = []
    for p, v in uniche:
        if e_risultato(p):
            diag["risultato_stampato"] = str(v.quantize(_C))
            continue
        if any(q != p and q.startswith(p + ".") and not e_fondo(q) for q in tutti):
            continue
        codice = campo_da_percorso(p)
        if codice is None:
            diag["non_mappati" if p not in ("X", "R") else "escluse"].append([p, p, str(v.quantize(_C))])
            continue
        voci.append((p, v, codice))

    convenzione = _convenzione_costi(voci)
    convenzione_ricavi = _convenzione_ricavi(voci)

    importi = defaultdict(Decimal)
    for p, v, codice in voci:
        if e_fondo(p):
            importi[codice] += -abs(v)
            continue
        if famiglia(codice) in ("cos", "ric"):
            v_applicato = _segno_ce_legge(codice, v, "", convenzione, convenzione_ricavi)
            if v_applicato != v:
                diag["ce_segno_forzato"].append(
                    [p, codice, str(v.quantize(_C)), str(v_applicato.quantize(_C))])
            importi[codice] += v_applicato
            continue
        importi[codice] += v
    bs, ce = completa(_netta_fondi_negativi(dict(importi)))
    diag["immobilizzazioni_negative_tagliate"] = _clamp_immobilizzazioni_negative(bs)
    return bs, ce, diag
