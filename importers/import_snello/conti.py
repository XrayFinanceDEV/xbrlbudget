"""Dai percorsi di legge agli importi dei campi, con le regole contabili di sempre:
la colonna decide il lato, un fondo si sottrae al bene, nessun conto contato due volte."""
from __future__ import annotations

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
            "risultato_precedente": [], "risultato_escluso": [], "risultato_ambiguo": None}
    diag["lato_corretti"] = applica_lato(foglie, diag["lato_irrisolti"])
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
