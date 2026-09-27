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


# Fix round 1 (ruling del proprietario, 2026-09-28): un campo CE di costo o di ricavo prende il
# VALORE ASSOLUTO, mai il segno letterale della riga - lo stesso principio del vecchio
# classificatore (situazione_contabile_parser.classify_costi/classify_ricavi: un campo a segno
# fisso, mai un segno che arriva dalla riga). Il voto di famiglia per conteggio (fix precedente,
# stesso giorno) restava comunque un voto: su budget_624 la maggioranza per CONTEGGIO di 8 conti
# letti negativi contro 1 solo (ce05_materie_prime, letto positivo) ribaltava anche quell'unico
# conto - una minoranza per conteggio puo' avere il valore vero, e nessun voto lo sa. Un campo
# resta negativo (riduce il proprio aggregato) SOLO per due ragioni esplicite, mai per un voto:
_CE_SEGNO_LIBERO = {"ce02", "ce03", "ce10"}
# (b) campi a segno libero per natura: variazioni OIC che possono legittimamente ridurre il
# proprio raggruppamento - ce02 (A.2, variazioni rimanenze prodotti in corso/semilavorati/
# finiti), ce03 (A.3, variazioni lavori in corso su ordinazione - non ce03a, A.4 incrementi di
# immobilizzazioni, che non e' una variazione), ce10 (B.11, variazione rimanenze materie prime,
# convenzione OIC: un aumento di giacenza riduce il costo). Nessun'altra voce IV-CEE e' una
# "variazione": ce09c/ce09d sono svalutazioni (sempre un costo, mai negative), gli aggregati
# ce18/ce19 sono gia' separati per segno (proventi/oneri straordinari), non voci nette.

_RETTIFICA_KEYWORDS = ("RESO", "RESI", "SCONTO", "SCONTI", "ABBUONO", "ABBUONI", "RIMBORSO",
                       "RIMBORSI", "STORNO", "STORNI", "RETTIFICA", "RETTIFICHE")


def _e_rettifica_esplicita(testo: str) -> bool:
    """(a) una didascalia di rettifica esplicita (resi, sconti, abbuoni, rimborsi, storni,
    rettifiche): una riduzione VERA del campo, dichiarata dal testo del conto - non dedotta da
    un voto su altre righe. Nessuna lista del genere esiste gia' nel vecchio parser per il CE
    (solo 'RICAVI' fra i costi, un segnale diverso: una voce di ricavo letta nella sezione
    sbagliata, gia' gestita da classify_costi/riclassifica_ignote sotto)."""
    t = (testo or "").upper()
    return any(k in t for k in _RETTIFICA_KEYWORDS)


def _segno_ce(codice: str, valore: Decimal, testo: str, forza_riduzione: bool = False) -> Decimal:
    """Il segno definitivo di un campo CE (famiglia 'cos' o 'ric'): mai un voto, sempre una
    regola per campo/didascalia. ``forza_riduzione`` viene da un tag interno del vecchio
    classificatore (ce01_return/ce13_cost/ce10_close, via riclassifica_ignote piu' sotto): il
    vecchio parser ha gia' deciso che quella riga riduce il campo (letta nella sezione opposta
    alla sua vera famiglia), e questa decisione esplicita vince anche su un campo a segno
    libero come ce10 (contro-esempio: 'RIM.FIN MAGAZZINO' fra i ricavi con ce10_close, che deve
    restare una riduzione anche se ce10 di per se' e' a segno libero)."""
    if forza_riduzione:
        return -abs(valore)
    if codice in _CE_SEGNO_LIBERO:
        return valore
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
# I primi tre (fix round 1, 2026-09-28: rimosso il voto di famiglia CE) sono gia' una decisione
# esplicita del vecchio parser - una riga letta nella sezione opposta alla propria famiglia vera
# (un ricavo fra i costi, un costo fra i ricavi, rimanenze finali lette come un ricavo) - e
# vanno marcati come riduzione ESPLICITA (``_TAG_CE_RIDUCE`` sotto), non dedotti da un voto di
# corsia che non esiste piu'. 'ce08a_tfr' resta un puro rinominare (nessuna riduzione).
_TAG_CE_INTERNI = {"ce01_return": "ce01", "ce13_cost": "ce13", "ce10_close": "ce10",
                   "ce08a_tfr": "ce08a"}
_TAG_CE_RIDUCE = frozenset({"ce01_return", "ce13_cost", "ce10_close"})


def _voto_direzione_ce(foglie) -> tuple[dict, bool]:
    """Vota, sulle sole foglie CE gia' classificate a un campo reale, quale corsia fisica e'
    normalmente 'cos' (costi), quale 'ric' (ricavi) - stesso principio del voto di lato usato
    per attivo/passivo in applica_lato: l'ordine testuale delle intestazioni non e' la verita'
    (budget_405), la maggioranza dei conti gia' letti lo e'. Serve a scegliere IL
    classificatore giusto (classify_costi o classify_ricavi) per una foglia non instradata, mai
    a provare entrambi alla cieca - una parola di ricavo letta fra i costi (RICAVI, PROVENTI+
    PARTECIP) darebbe uno specifico su entrambi i lati, e la foglia resterebbe sempre esclusa."""
    ce = [f for f in foglie if f.percorso and lato_di(f.percorso) == "ce"]
    due_lati = len({f.lato for f in ce} & {"L", "R"}) == 2
    peso = Counter()
    for f in ce:
        codice = campo_da_percorso(f.percorso)
        if codice is None:
            continue
        peso[(famiglia(codice), _corsia(f, due_lati))] += abs(f.valore)
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

    Muta ``f.percorso`` sul posto con un marcatore che ``campo_da_percorso`` non traduce:
    ``'#<campo>'`` per un rinominare puro (es. 'ce08a_tfr'), ``'#-<campo>'`` quando il campo
    grezzo era uno dei tre tag di riduzione del vecchio parser (``_TAG_CE_RIDUCE``: una voce di
    ricavo letta fra i costi, un provento letto fra i costi, una rimanenza finale letta fra i
    ricavi). ``da_foglie`` lo riconosce all'inizio del proprio giro e la foglia entra come
    qualunque altra foglia gia' classificata - e' cosi', non con un nuovo calcolo di lato, che il
    netto Dare/Avere di uno stesso mastro si ottiene (FORMETAL, banco 2026-09-26: '40/00000
    DEBITI V/FORNITORI' 13.542,00 e 348.578,85 su lati opposti -> sp16d netto 335.036,85). Per il
    CE, il marcatore ``'#-'`` porta gia' la decisione del vecchio parser (fix round 1,
    2026-09-28: non c'e' piu' un voto di famiglia a dedurla dalla corsia fisica)."""
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
            riduce = campo_grezzo in _TAG_CE_RIDUCE
            campo = _TAG_CE_INTERNI.get(campo_grezzo, campo_grezzo)
            if campo in TIER0_FIELDS or campo not in NOMI:
                continue
            diag["riclassificati_vecchio_parser"].append(
                [f.id, f.testo[:60], campo, str(f.valore.quantize(_C))])
            f.percorso = f"#-{campo}" if riduce else f"#{campo}"
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
            "riclassificati_vecchio_parser": [], "ce_segno_forzato": []}
    diag["lato_corretti"] = applica_lato(foglie, diag["lato_irrisolti"])
    riclassifica_ignote(foglie, diag)
    irrisolti_ids = {r[0] for r in diag["lato_irrisolti"]}
    due_lati = len({f.lato for f in foglie} & {"L", "R"}) == 2
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
            # legge). '#-<campo>' porta gia' la decisione di riduzione del vecchio parser
            # (_TAG_CE_RIDUCE); '#<campo>' e' un puro rinominare.
            riduce = f.percorso.startswith("#-")
            codice = f.percorso[2:] if riduce else f.percorso[1:]
            per_famiglia[famiglia(codice)].append((f, codice, riduce))
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
            diag["risultato_precedente"].append([f.id, f.percorso, str(v.quantize(_C))])
            continue
        if f.percorso == "SPP.A.VIII":
            # Qwen riserva VIII al portato a nuovo: una didascalia non riconosciuta (generica,
            # o mancante) non toglie fiducia al percorso esplicito, e il segno resta quello
            # letto (nessuna contropartita per un conto di netto, come applica_lato).
            pregresso += f.valore
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
                diag["risultato_precedente"].append([f.id, f.percorso, str(f.valore.quantize(_C))])
            else:
                ambigue.append(f)
            continue

        codice = campo_da_percorso(f.percorso)
        if codice is None:
            diag["non_mappati"].append([f.id, f.percorso, str(f.valore.quantize(_C))])
            continue
        per_famiglia[famiglia(codice)].append((f, codice, False))
    importi = defaultdict(Decimal)
    for fam, elementi in per_famiglia.items():
        if fam in ("cos", "ric"):
            # Fix round 1 (ruling del proprietario, 2026-09-28): niente voto di famiglia per il
            # CE - un campo per campo/didascalia (_segno_ce), mai per maggioranza. Il voto per
            # conteggio (fix precedente) restava un voto: su budget_624 la maggioranza per
            # CONTEGGIO di 8 conti letti negativi contro 1 solo (ce05_materie_prime, letto
            # positivo, il vero valore) ribaltava anche quell'unico conto vero - una minoranza
            # per conteggio puo' avere il segno vero, e nessun voto lo sa.
            for f, codice, riduce in elementi:
                v = _segno_ce(codice, f.valore, f.testo, riduce)
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
        for f, _, _r in elementi:
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
        for f, codice, _r in elementi:
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
    return bs, ce, diag


def da_coppie(coppie):
    """Schema di legge: coppie (percorso, importo) come stampate. Un percorso che ha un discendente
    fra le coppie e' un totale e cade; una voce ripetuta conta una volta; un fondo si sottrae.

    A differenza di ``da_foglie`` (modo "conti"), qui non c'e' alcun voto di lato: il percorso e'
    gia' la voce di legge (non un mastro di ledger), quindi non c'e' mai una didascalia di
    rettifica da leggere (``_e_rettifica_esplicita`` non trova mai nulla: ``da_coppie`` non porta
    testo). Un campo CE di costo o di ricavo prende comunque il valore assoluto per lo stesso
    principio di ``da_foglie`` (fix round 1, ruling del proprietario, 2026-09-28) - mai un voto di
    famiglia (il fix precedente, Task 22 G2, ribaltava l'intera famiglia "cos" a maggioranza per
    conteggio: un documento con una vera contropartita maggioritaria per numero l'avrebbe
    ribaltata comunque) - salvo i campi a segno libero per natura (``_CE_SEGNO_LIBERO``: ce02,
    ce03, ce10), dove il segno letto e' l'unico segno che conta."""
    diag = {"non_mappati": [], "escluse": [], "risultato_stampato": None, "lato_corretti": 0,
            "lato_irrisolti": [], "risultato_duplicato": [], "padri_esclusi": [],
            "ce_segno_forzato": []}
    viste, uniche = set(), []
    for p, v in coppie:
        if p not in viste:
            viste.add(p)
            uniche.append((p, Decimal(v)))
    tutti = [p for p, _ in uniche]
    importi = defaultdict(Decimal)
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
        if e_fondo(p):
            importi[codice] += -abs(v)
            continue
        if famiglia(codice) in ("cos", "ric"):
            v_applicato = _segno_ce(codice, v, "")
            if v_applicato != v:
                diag["ce_segno_forzato"].append(
                    [p, codice, str(v.quantize(_C)), str(v_applicato.quantize(_C))])
            importi[codice] += v_applicato
            continue
        importi[codice] += v
    bs, ce = completa(_netta_fondi_negativi(dict(importi)))
    diag["immobilizzazioni_negative_tagliate"] = _clamp_immobilizzazioni_negative(bs)
    return bs, ce, diag
