"""Dai percorsi di legge agli importi dei campi, con le regole contabili di sempre:
la colonna decide il lato, un fondo si sottrae al bene, nessun conto contato due volte."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from decimal import Decimal

from calculations.ce_result import calculate_ce_result
from importers.import_snello.percorsi import (CONTROPARTE, NOMI, campo_da_percorso, completa,
                                              e_fondo, e_netto, e_risultato, famiglia, lato_di)
from importers.import_snello.risultato import control_caption, prior_caption, sign_by_caption
from importers.import_snello.verifica import misura, soglia
from importers.iv_cee_hierarchy import detail_fields

_C = Decimal("0.01")
_IMMOBILIZZAZIONI = ("sp02", "sp03", "sp04")
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


def riclassifica_ignote(foglie, diag: dict) -> None:
    """Una foglia marcata 'X' da Qwen, o rimasta senza percorso anche al secondo giro, il cui
    testo comincia con un codice di conto ('40/00000 DEBITI V/FORNITORI'), e' massa vera che
    il modello ha rinunciato a instradare - non una riga di controllo. Si riprova coi
    classificatori a parole del vecchio importatore
    (situazione_contabile_parser.classify_attivo/classify_passivo per lo SP,
    classify_costi/classify_ricavi + _resolve_ce_field per il CE), mai reinventati qui: si
    prova sia l'ipotesi attivo sia quella passivo (o costi/ricavi) sulla stessa descrizione, e
    si usa il risultato solo quando UNA sola delle due e' specifica (non il ripiego generico
    del classificatore: sp06/ce12/ce04) e non e' un campo TIER0 (immobilizzazioni nette,
    patrimonio netto, banche, ce09) - se sono specifiche entrambe, o nessuna, la foglia resta
    X/non mappata come oggi (nessuna scommessa quando la descrizione da sola non decide).

    Muta ``f.percorso`` sul posto con un marcatore ``'#<campo>'`` che ``campo_da_percorso``
    non traduce: ``da_foglie`` lo riconosce all'inizio del proprio giro e la foglia entra nel
    voto di famiglia esistente come una qualunque foglia gia' classificata - e' cosi', non con
    un nuovo calcolo di segno, che il netto Dare/Avere di uno stesso mastro si ottiene
    (FORMETAL, banco 2026-09-26: '40/00000 DEBITI V/FORNITORI' 13.542,00 e 348.578,85 su lati
    opposti -> sp16d netto 335.036,85, lo stesso voto che gia' decide gli altri debiti del
    foglio)."""
    from importers.situazione_contabile_parser import (
        TIER0_FIELDS, _resolve_ce_field, classify_attivo, classify_costi, classify_passivo,
        classify_ricavi)

    for f in foglie:
        if f.percorso not in ("X", None) or not f.testo or not _ha_codice_conto(f.testo):
            continue
        desc = " ".join(f.testo.split()[1:]).upper().strip()
        if not desc:
            continue
        candidati: set = set()
        if f.sezione == "ce":
            for direzione, classify in (("costi", classify_costi), ("ricavi", classify_ricavi)):
                c, specifico = classify(desc)
                # classify_costi/classify_ricavi arriva a un campo piu' fine (es. 'ce08b'), che
                # _resolve_ce_field non conosce (la sua allowlist di direzione vede solo gli
                # aggregati: 'ce08'): tenerlo come prima fonte, l'albero solo di ripiego quando
                # la tabella a parole non e' specifica.
                campo = c if specifico else _resolve_ce_field(desc, direzione)
                if campo is not None and campo not in TIER0_FIELDS:
                    candidati.add(campo)
        else:
            for classify in (classify_attivo, classify_passivo):
                campo, specifico = classify(desc)
                if specifico and campo not in TIER0_FIELDS:
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
         solo, o lo stesso risultato corrente ristampato) si esclude e basta, mai sommata -
         MAI su un percorso gia' risolto a un campo normale (fix round 1, review 2026-09-26:
         "Differenza cambi attivi"/CE.C.17-bis e "Totale rimanenze iniziali" sono conti veri,
         non righe di pareggio, e la didascalia non deve mai scavalcare un percorso classificato);
      3. un percorso "R" o "SPP.A.IX" la cui didascalia non e' ne' precedente ne' di
         pareggio/controllo e' ambiguo: due ipotesi si confrontano DOPO aver costruito il resto
         del foglio - corrente (esclusa) o precedente (in sp12g) - e vince quella che quadra
         meglio.

    ``risultato_duplicato`` resta dichiarato (sempre vuoto in modo "conti"): il vecchio
    dedup-per-valore riguardava solo le righe che finivano sommate in sp13, e nessuna ci
    finisce piu' per questa via."""
    diag = {"non_mappati": [], "escluse": [], "risultato_stampato": None, "lato_corretti": 0,
            "lato_irrisolti": [], "risultato_duplicato": [], "padri_esclusi": [],
            "risultato_precedente": [], "risultato_escluso": [], "risultato_ambiguo": None,
            "riclassificati_vecchio_parser": []}
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
            # legge), entra nel voto di famiglia come una qualunque foglia classificata.
            codice = f.percorso[1:]
            per_famiglia[famiglia(codice)].append((f, codice))
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
            else:
                ambigue.append(f)
            continue

        codice = campo_da_percorso(f.percorso)
        if codice is None:
            diag["non_mappati"].append([f.id, f.percorso, str(f.valore.quantize(_C))])
            continue
        per_famiglia[famiglia(codice)].append((f, codice))
    importi = defaultdict(Decimal)
    for elementi in per_famiglia.values():
        peso_corsia, peso_segno = Counter(), Counter()
        for f, _ in elementi:
            if e_fondo(f.percorso) or f.id in irrisolti_ids:
                continue
            if due_lati and e_netto(f.percorso):
                # su un prospetto Dare/Avere il capitale/riserve/risultato non deve pesare sul
                # voto delle altre voci passive: un utile grande, stampato Avere per natura,
                # sposterebbe il "lato normale" della famiglia e farebbe girare di segno un
                # debito vero. A colonna unica (senza Dare/Avere) resta nel voto come sempre.
                continue
            peso_corsia[_corsia(f, True) if due_lati else 0] += abs(f.valore)
            peso_segno[f.valore >= 0] += abs(f.valore)
        corsia_n = peso_corsia.most_common(1)[0][0] if peso_corsia else 0
        positivo_n = peso_segno.most_common(1)[0][0] if peso_segno else True
        for f, codice in elementi:
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

    # Il risultato corrente non e' mai una somma di righe stampate: e' sempre l'utile del CE
    # gia' costruito sopra (diagnose, never fabricate - la memoria/CLAUDE.md: "The RISULTATO
    # e' la balancing figure ... derive il risultato dal CE"). Una foglia ambigua (percorso "R"
    # o "SPP.A.IX", didascalia che non dice ne' precedente ne' controllo) puo' pero' essere in
    # realta' un pregresso non riconosciuto come tale (didascalia generica tipo "Risultato
    # esercizio" senza "precedente"): si sceglie l'ipotesi che fa quadrare meglio il foglio,
    # mai quella che quadra peggio, e se nessuna delle due chiude entro soglia si tiene
    # l'ipotesi "corrente" (esclusa) e si lascia che la verifica dichiari lo scarto vero (non
    # e' un risultato piu' grande da inventare, e' massa mancante da recuperare altrove).
    utile_ce = calculate_ce_result(ce).net_profit.quantize(_C)
    if ambigue:
        somma = sum((f.valore for f in ambigue), Decimal(0))
        bs_corrente = dict(bs)
        bs_corrente["sp13_utile_perdita"] = utile_ce
        bs_precedente = dict(bs)
        bs_precedente["sp12g_utili_perdite_portati"] = (
            Decimal(bs_precedente.get("sp12g_utili_perdite_portati", 0)) + somma).quantize(_C)
        bs_precedente["sp12_riserve"] = (
            Decimal(bs_precedente.get("sp12_riserve", 0)) + somma).quantize(_C)
        bs_precedente["sp13_utile_perdita"] = utile_ce
        m_corrente = misura(bs_corrente, ce, None, forma="bilancio")
        m_precedente = misura(bs_precedente, ce, None, forma="bilancio")
        s = soglia(m_corrente["attivo"])
        candidati = [[f.id, f.percorso, str(f.valore.quantize(_C))] for f in ambigue]
        if abs(m_precedente["scarto_sp"]) < abs(m_corrente["scarto_sp"]) and abs(m_precedente["scarto_sp"]) <= s:
            bs = bs_precedente
            diag["risultato_ambiguo"] = {"ipotesi": "precedente", "importo": str(somma.quantize(_C)),
                                         "candidati": candidati}
        else:
            bs = bs_corrente
            diag["risultato_ambiguo"] = {"ipotesi": "corrente", "importo": str(somma.quantize(_C)),
                                         "candidati": candidati}
    else:
        bs["sp13_utile_perdita"] = utile_ce
    return bs, ce, diag


def da_coppie(coppie):
    """Schema di legge: coppie (percorso, importo) come stampate. Un percorso che ha un discendente
    fra le coppie e' un totale e cade; una voce ripetuta conta una volta; un fondo si sottrae."""
    diag = {"non_mappati": [], "escluse": [], "risultato_stampato": None, "lato_corretti": 0,
            "lato_irrisolti": [], "risultato_duplicato": [], "padri_esclusi": []}
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
        importi[codice] += -abs(v) if e_fondo(p) else v
    bs, ce = completa(_netta_fondi_negativi(dict(importi)))
    return bs, ce, diag
