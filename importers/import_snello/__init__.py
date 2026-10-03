"""Import PDF snello: struttura, macroconti per percorso di legge, verifica con tappo dichiarato."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal

from importers.import_snello.verifica import limite_tappo

# I modi di lettura che leggono lo schema di legge (macro voci dai totali stampati) invece di
# un elenco di conti. "legge_con_dettaglio" (Task 24): le macro voci vengono dalle didascalie
# senza codice conto, i dettagli dalle righe-conto che stanno sotto.
_MODI_LEGGE = ("legge", "legge_con_dettaglio")

# Parser deterministico -> modo con cui il documento risulta letto quando nessuna struttura e'
# girata. La situazione contabile e' un elenco di conti, gli altri due leggono lo schema di legge.
_MODO_DA_PARSER = {"standard_ivcee_parser": "legge",
                   "schema_legge_con_dettaglio": "legge_con_dettaglio",
                   "xbrl_reso_parser": "legge",
                   "situazione_contabile_parser": "conti"}

_IMMOBILIZZAZIONI_CAMPI = ("sp02_immob_immateriali", "sp03_immob_materiali", "sp04_immob_finanziarie")

# Nota aggiunta alla chiamata combinata di una pagina "prospetto_sp_e_ce" (Task lotto-b, fix 8):
# una pagina cosi' entra in pagine_sp E pagine_ce (TIPI_SP/TIPI_CE di analisi.py), e leggerla con
# due chiamate indipendenti manda la STESSA riga stampata a due letture separate, che possono
# risolverla con due percorsi legali diversi (es. SPP.D.O da una, SPP.D.E dall'altra) — da_coppie
# deduplica solo per percorso esatto, quindi la stessa massa finirebbe contata due volte
# (diagnosi budget_397). Una pagina cosi' si legge una volta sola, con una nota che chiede
# esplicitamente sia le voci SP sia le voci CE.
_NOTA_PAGINA_CONDIVISA = ("Questa pagina contiene sia voci di Stato Patrimoniale sia di Conto "
                         "Economico: leggi entrambe, ogni riga stampata una volta sola, mai due.")


class SnelloNonRiuscito(Exception):
    """Il percorso snello non e' arrivato a un risultato utilizzabile: ``report`` dichiara fase ed
    errore, mai un dato inventato al loro posto."""

    def __init__(self, report: dict):
        super().__init__(report.get("errore") or report.get("fase") or "ripiego")
        self.report = report


@dataclass
class Risultato:
    bs: dict
    ce: dict
    prior_bs: dict | None
    prior_ce: dict | None
    report: dict
    struttura: object


def _unisci_totali(a: dict, b: dict) -> dict:
    """Unione dei totali stampati dalle due chiamate (SP e CE): tiene il primo valore non nullo,
    ripiegando sul secondo quando il primo manca."""
    out = dict(a)
    for k, v in b.items():
        if out.get(k) is None:
            out[k] = v
    return out


def _anomalie(bs: dict, diag: dict) -> list:
    # Un'immobilizzazione negativa non sopravvive oltre conti.py (_clamp_immobilizzazioni_negative
    # la azzera sempre): il controllo diretto su bs resta solo come rete di sicurezza, mai la
    # fonte primaria - l'eccedenza tagliata la dichiara diag.
    dirette = [[campo, str(bs[campo])] for campo in _IMMOBILIZZAZIONI_CAMPI if campo in bs and bs[campo] < 0]
    return dirette + diag.get("immobilizzazioni_negative_tagliate", [])


def _unclassified_mass(diag: dict) -> Decimal:
    return sum((Decimal(v) for _, _, v in diag.get("lato_irrisolti", [])), Decimal(0))


# Task 27, item 7: le coppie (percorso, importo) che il modello ha restituito per l'anno corrente
# restano nel report, cosi' un errore di lettura (debiti «entro» salvati a sp17...) si diagnostica
# da un record del banco senza rilanciare il modello. Il report finisce nel DB con l'upload:
# un esito "ok" porta le coppie solo se sono poche; con un esito diverso da "ok" fino a _MAX_COPPIE.
_MAX_COPPIE_SE_OK = 120
_MAX_COPPIE = 600


def _coppie_nel_report(coppie, esito: str) -> dict:
    """Diagnostica pura: un'eccezione qui (importo non numerico...) non deve mai far fallire un
    import riuscito, quindi il risultato e' vuoto."""
    try:
        if not coppie:
            return {}
        righe = [f"{p}={Decimal(v).quantize(Decimal('0.01'))}" for p, v in coppie]
        if esito == "ok" and len(righe) > _MAX_COPPIE_SE_OK:
            return {"coppie_corrente_n": len(righe)}
        if len(righe) > _MAX_COPPIE:
            return {"coppie_corrente": righe[:_MAX_COPPIE], "coppie_corrente_n": len(righe)}
        return {"coppie_corrente": righe, "coppie_corrente_n": len(righe)}
    except Exception:
        return {}


def _limite_interno(s):
    """Lo scarto interno (SP e CE) oltre il quale non c'e' tappo (``verifica.limite_tappo``)."""
    return limite_tappo(s)


def _causa_stampati(m: dict, s) -> bool:
    """Vero quando lo scarto interno (SP e CE) e' entro soglia ma il totale che il documento
    stampa da solo non concorda con le voci lette: la causa e' il contraddittorio del totale
    stampato, non un vero sbilancio interno - la nota della rilettura e il report finale non
    devono dire "voci mancanti, doppie...", un messaggio pensato per l'altro caso (review
    round 1, 2026-09-27)."""
    t = _limite_interno(s)
    return abs(m["scarto_sp"]) <= t and abs(m["scarto_ce"]) <= t and m["scarto_stampati"] > s


def _documento_sbilanciato(m: dict, s, stampati: dict | None, deterministici: bool) -> bool:
    """Task 25 fix round 1 (decisione del proprietario, 2026-10-02): il documento contraddice
    se' stesso. Le voci lette riproducono i totali stampati (scarto sui totali stampati entro
    soglia) e il Totale Attivo e il Totale Passivo stampati differiscono, fra loro, dello
    stesso importo dello scarto Attivo/Passivo misurato: la lettura e' fedele, ne' una
    rilettura ne' un tappo possono aiutare. Con uno dei due totali assenti: falso (come oggi)."""
    if not deterministici or not stampati:
        # i totali riportati dal modello vengono dalla stessa chiamata che ha letto le voci:
        # non sono il documento (round 2, N4)
        return False
    ta, tp = stampati.get("totale_attivo"), stampati.get("totale_passivo")
    if ta is None or tp is None:
        return False
    t = _limite_interno(s)
    differenza = abs(Decimal(ta) - Decimal(tp))
    # Fix round 1 (review Task 27): il documento deve DAVVERO stampare due totali diversi (oltre il
    # limite interno) e lo scarto misurato deve coincidere con quella differenza entro lo stesso
    # limite: con totali uguali e uno scarto di lettura di 60 euro la colpa e' della lettura.
    if abs(m["scarto_sp"]) <= t or m["scarto_stampati"] > s or differenza <= t:
        return False
    return abs(differenza - abs(m["scarto_sp"])) <= t


def _risultato_contraddittorio(m: dict, s, risultati: dict | None, totali_spiegano_lo_sp: bool) -> dict | None:
    """Task 27, decisione 3 (2026-10-03): il risultato d'esercizio stampato nello SP differisce da
    quello stampato nel CE, e le voci lette riproducono entrambi (sp13 = risultato dello SP, utile
    ricostruito dal CE = risultato del CE, ciascuno entro il limite del tappo): la lettura e' fedele,
    la contraddizione e' del documento, ne' una rilettura ne' un tappo possono aiutare.
    ``risultati`` viene dalle righe del documento (``risultati_stampati``), mai dal modello; None
    (non letti con certezza) o un divario SP non spiegato (ne' entro il limite, ne' dai totali
    stampati): falso. Restituisce la contraddizione dichiarata, altrimenti None."""
    if not risultati:
        return None
    t = _limite_interno(s)
    sp, ce = Decimal(risultati["sp"]), Decimal(risultati["ce"])
    if abs(sp - ce) <= t or abs(m["scarto_ce"]) <= t:
        return None
    if abs(m["scarto_sp"]) > t and not totali_spiegano_lo_sp:
        return None
    if abs(Decimal(m["sp13"]) - sp) > t or abs(Decimal(m["utile_ce"]) - ce) > t:
        return None
    return {"tipo": "risultato", "sp": str(sp.quantize(Decimal("0.01"))),
            "ce": str(ce.quantize(Decimal("0.01"))), "differenza": str(abs(sp - ce).quantize(Decimal("0.01")))}


def _negativi_stampati(bs: dict | None, parser: str, anno: int | None = None) -> list:
    """Reso XBRL (Task 25): un importo SP negativo che il documento stampa davvero (fuori da
    patrimonio netto e immobilizzazioni, gia' coperte da ``_anomalie``) si tiene col suo segno ma
    non passa in silenzio: l'utente lo vede fra le anomalie e lo corregge in Rettifiche. Per la
    colonna dell'anno precedente la voce porta l'anno come terzo elemento. Il CE resta fuori: un
    segno negativo e' ordinario su ce02/ce03/ce10/ce16, rettifiche, imposte con credito e sul
    risultato, e un elenco rumoroso e' peggio di uno corto."""
    if parser != "xbrl_reso_parser" or not bs:
        return []
    return [[k, str(v)] + ([str(anno)] if anno is not None else []) for k, v in bs.items()
            if k.startswith("sp") and isinstance(v, Decimal) and v < 0
            and not k.startswith(("sp02", "sp03", "sp04", "sp12", "sp13"))]


def _risultato_deterministico(_det: dict, struttura, modo: str, t0: float) -> "Risultato":
    """Il risultato di un candidato deterministico adottato (nessuna chiamata al modello).

    Task 16 (b): deterministico prima di Qwen; Task 24: prima ancora della struttura. Mai un
    secondo tentativo dopo l'adozione, mai i due candidati sommati. Il candidato che non quadra
    e' SEMPRE rifiutato a monte (``tentativo``): non diventa mai "squadrato", solo Qwen puo'
    importare con sbilancio dichiarato (decisione del proprietario, Task 17)."""
    _bs_det = dict(_det["bs"])
    # Il plug del tappo lean si AGGIUNGE alla massa/plug che il parser sottostante
    # ha gia' dichiarato (mai l'uno al posto dell'altro): quella e' diagnostica
    # dell'ESTRATTORE (un fallback lecito che ha giа contato la massa una volta),
    # questo e' il rammendo che il percorso lean applica DOPO — sono due cose
    # diverse, e sommarle e' l'unico modo di non farne sparire una (review round 1).
    _plug_parser = Decimal(_det["bs"].get("_plug_residual", 0) or 0)
    _plug_lean = (Decimal(_det["tappo"]["importo"])
                  if _det["tappo"] and "importo" in _det["tappo"] else Decimal(0))
    _bs_det["_plug_residual"] = _plug_parser + _plug_lean
    # Mai un hardcoded zero: la massa non classificata e' quella che il parser ha
    # DICHIARATO (anche a zero, quando davvero non ne ha trovata) - un estrattore
    # dichiara sempre le proprie chiavi diagnostiche, e tacere equivarrebbe a
    # dichiararsi pulito (CLAUDE.md).
    _massa_det = Decimal(_det["bs"].get("_unclassified_mass", 0) or 0)
    _bs_det["_unclassified_mass"] = _massa_det
    # diag non e' uno scheletro fabbricato che pare pulito: porta le stesse chiavi
    # di da_foglie/da_coppie (nessun KeyError a valle) e dichiara la fonte - la
    # massa non classificata vive su bs (sopra), non su diag["lato_irrisolti"],
    # che qui non si applica per costruzione (nessun voto di lato e' girato).
    _diag_det = {"non_mappati": [], "escluse": [], "risultato_stampato": None,
                 "lato_corretti": 0, "lato_irrisolti": [], "risultato_duplicato": [],
                 "padri_esclusi": [], "fonte": _det["parser"]}
    report = {
        "esito": _det["esito"], "modo": modo, "fonte": f"deterministico:{_det['parser']}",
        "struttura": struttura.report(),
        "misura": {"corrente": {k: str(v) for k, v in _det["misura"].items()}},
        "tappo": {"corrente": _det["tappo"]},
        "letture": {"chiamate": 0, "saltate_prima": 0, "senza_percorso": 0},
        "diag": _diag_det,
        "deterministico": {"parser": _det["parser"], "esito": _det["esito"],
                           "unclassified_mass": str(_massa_det),
                           # Task 25: un anno precedente scartato si vede nel report persistito
                           **{k: _det[k] for k in ("prior_stato", "prior_rifiuto") if _det.get(k)}},
        # Task 25: i dettagli del reso XBRL stanno gia' nel risultato (prospetto e tabelle di
        # nota); il report dice da dove vengono e cosa si e' potuto applicare.
        **({"dettagli": {"fonte": "prospetto_e_nota_xbrl", **_det["dettagli"]}}
           if _det.get("dettagli") is not None else {}),
        **({"ignoti": _det["ignoti"]} if _det.get("ignoti") else {}),
        "anomalie": _anomalie(_bs_det, _diag_det) + _negativi_stampati(_bs_det, _det["parser"])
        + _negativi_stampati(_det.get("prior_bs"), _det["parser"], _det.get("anno_precedente")),
        "secondi": round(time.monotonic() - t0, 1),
    }
    return Risultato(bs=_bs_det, ce=dict(_det["ce"]), prior_bs=_det.get("prior_bs"),
                     prior_ce=_det.get("prior_ce"), report=report, struttura=struttura)


def importa(file_path: str, *, ocr_text: str | None = None, analizza=None, leggi_conti=None,
            leggi_voci=None, trascrivi=None, route_hint: str | None = None) -> Risultato:
    t0 = time.monotonic()

    # Task 24 (owner: "la vision si attiva solo quando la struttura del bilancio non si capisce"):
    # il deterministico gira PRIMA della struttura. Non legge nulla dalla struttura: il parser
    # standard e quello dello schema con dettaglio lavorano sul testo e sulla geometria del PDF,
    # la situazione contabile sul testo. Se un candidato quadra (stesse regole di sempre) lo si
    # adotta a zero chiamate al modello, vision compresa: nessuna mappa di pagina serve a un
    # risultato che il documento stesso ha gia' dichiarato. Solo senza adozione parte la struttura
    # (titoli xbrl, poi vision) e il percorso di oggi, invariato. Le pagine per il recupero dei
    # dettagli (enrich_pdf_details) le deriva il testo, mai un modello.
    from importers.import_snello.deterministico import tentativo as _tenta_deterministico
    _det = _tenta_deterministico(file_path, ocr_text)
    if _det["adottato"]:
        from importers.struttura_documento.analisi import struttura_deterministica
        modo = _MODO_DA_PARSER.get(_det["parser"], "legge")
        struttura = struttura_deterministica(file_path, modo=modo)
        return _risultato_deterministico(_det, struttura, modo, t0)

    from importers.struttura_documento.analisi import analizza_struttura
    analizza_fn = analizza or analizza_struttura
    try:
        # route_hint si inoltra solo quando il chiamante lo passa: di default resta None e la
        # chiamata e' quella di sempre, posizionale sola — una `analizza` finta dei test che non
        # accetta affatto questo parametro (`lambda p: ...`) non deve rompersi (Task lotto-b, fix 9).
        struttura = analizza_fn(file_path, route_hint=route_hint) if route_hint is not None else analizza_fn(file_path)
    except Exception as e:
        raise SnelloNonRiuscito({"esito": "ripiego", "fase": "struttura", "errore": type(e).__name__}) from e

    pagine_sp, pagine_ce = struttura.pagine_sp, struttura.pagine_ce
    if not pagine_sp and not pagine_ce:
        raise SnelloNonRiuscito({"esito": "ripiego", "fase": "struttura", "errore": "nessun prospetto"})

    modo = struttura.modo
    forma = "bilancio" if modo in _MODI_LEGGE else None

    _report_deterministico = {"parser": _det["parser"], "esito": _det["esito"]}
    if "unclassified_mass" in _det:
        # Ruling (a), Task 18: la massa che ha impedito l'adozione resta dichiarata nel
        # report anche quando si prosegue col percorso Qwen - mai un silenzio che
        # sembrerebbe "nessun problema" (CLAUDE.md, chiavi diagnostiche sempre dichiarate).
        _report_deterministico["unclassified_mass"] = _det["unclassified_mass"]
    if "xbrl_reso" in _det:
        # Task 25: un reso XBRL riconosciuto ma non adottato dichiara quale controllo e' fallito.
        _report_deterministico["xbrl_reso"] = _det["xbrl_reso"]

    from importers.import_snello.verifica import misura, normalizza_forma, soglia, tappa, totali_stampati

    # Ancora indipendente dall'estrattore, letta una sola volta (nessuna chiamata modello):
    # in modo "legge" vince sui totali riportati dall'LLM quando esiste (li' sotto, in
    # _combina). In modo "conti" il totale stampato entra SOLO sulla colonna che la
    # struttura identifica come saldo (Ruling Task 21, diagnosi TM 589/590): senza una
    # colonna certa (``regola_colonna`` vuota - "saldo_corrente"/"saldo_finale" non
    # dichiarati) non c'e' alcuna ancora, mai un falso squadrato preso dalla prima colonna
    # che il testo grezzo incontra (era "Saldo non rettificato", non "Saldo finale").
    if modo == "conti":
        from importers.import_snello.righe import regola_colonna
        _regola_stampati = regola_colonna(struttura.colonne_sp or struttura.colonne_ce)
        deterministici = (totali_stampati(file_path, regola=_regola_stampati) if _regola_stampati
                          else {"totale_attivo": None, "totale_passivo": None})
    else:
        deterministici = totali_stampati(file_path)
    # Provenienza esplicita dei totali stampati: letti dal testo (entrambi) o no.
    _totali_dal_testo = all(deterministici.get(k) is not None for k in ("totale_attivo", "totale_passivo"))

    # Task 21: la massa grezza per lato (SP, prima di applica_lato/netting dei fondi), sola
    # base di confronto valida per lo stampato quando il prospetto e' a sezioni
    # contrapposte (due lati fisici distinti) - assegnata dopo aver letto le foglie, sotto.
    # None (nessun grezzo) e' il comportamento di sempre: misura() ripiega su att/pas netti.
    _grezzo_sp: dict | None = None

    def _verifica(bs: dict, ce: dict, stampati: dict | None):
        if modo == "conti":
            # Task 14 (2026-09-26): in modo "conti" il costruttore (da_foglie) ha gia' portato
            # sp13 all'utile del CE per costruzione - non c'e' piu' un'euristica bilancio/
            # verifica da rilevare, ne' un normalizza_forma da applicare (sarebbe un no-op:
            # m["forma"] e' sempre "bilancio"). Rilevarla comunque (forma=None) rischierebbe di
            # tornare su "verifica" e sottrarre l'utile una seconda volta, mascherando un vero
            # sbilancio (budget_330) - lo stesso guasto che il doppio passaggio sotto evita per
            # modo "legge".
            m = misura(bs, ce, stampati, forma="bilancio", grezzo=_grezzo_sp)
            s = soglia(m["attivo"])
            bs, ce, tappo, esito = tappa(bs, ce, m, s)
            return bs, ce, tappo, esito, m, s
        m = misura(bs, ce, stampati, forma=forma)
        s = soglia(m["attivo"])
        bs = normalizza_forma(bs, ce, m)
        # normalizza_forma ha gia' commesso il foglio alla semantica bilancio (no-op se lo
        # era gia'): riautorilevare qui (forma=forma) puo' tornare su "verifica" e sottrarre
        # l'utile una seconda volta, mascherando un vero sbilancio (budget_330).
        m = misura(bs, ce, stampati, forma="bilancio")
        bs, ce, tappo, esito = tappa(bs, ce, m, s)
        return bs, ce, tappo, esito, m, s

    _risultati_letti: list = []
    _coppie_lette: list = []          # le coppie dell'anno corrente dell'ultima lettura (modi di legge)

    def _contraddizioni(m: dict, s, stampati: dict | None) -> list:
        """Le contraddizioni che il documento stampa da solo e che le voci lette riproducono:
        totali (Task 25) e risultato SP/CE (Task 27). Solo per i modi di legge, e solo da cio' che
        il documento stampa (mai importi riportati dal modello)."""
        if modo not in _MODI_LEGGE:
            return []
        out = []
        totali = _documento_sbilanciato(m, s, stampati, _totali_dal_testo)
        if totali:
            out.append({"tipo": "totali"})
        if abs(m["scarto_ce"]) > _limite_interno(s):
            if not _risultati_letti:               # righe fisiche del documento, lette una volta sola
                try:
                    from importers.detail_enrichment import collect_source_rows
                    from importers.import_snello.risultati_stampati import risultati_stampati
                    _risultati_letti.append(risultati_stampati(collect_source_rows(file_path, ocr_text=ocr_text)))
                except Exception:
                    _risultati_letti.append(None)
            risultato = _risultato_contraddittorio(m, s, _risultati_letti[0], totali)
            if risultato:
                out.append(risultato)
        return out

    fase = "lettura"
    try:
        if modo == "conti":
            from importers.import_snello.righe import foglie, righe_da_pdf
            from importers.import_snello.lettura import percorsi_dei_conti
            from importers.import_snello.conti import da_foglie

            leggi_conti_fn = leggi_conti or percorsi_dei_conti
            ruoli = struttura.colonne_sp or struttura.colonne_ce
            # Ruling (b), Task 18 (2026-09-27): anche le pagine_dettaglio entrano nella
            # lettura, non solo pagine_sp ∪ pagine_ce - modo "legge" le legge gia' da sempre
            # (pagine_dettagli(), per enrich_pdf_details): una pagina di continuazione del
            # prospetto (debiti/servizi che sconfinano oltre le pagine SP/CE gia' individuate)
            # restava altrimenti invisibile e la sua massa persa (diagnosi AMBIENTA
            # 2026-09-26, causa radice #1). Un insieme di pagine piu' ampio non duplica nulla:
            # marca_totali/da_foglie continuano a decidere mastri-o-foglie sul totale stampato,
            # mai sul prefisso o sulla pagina di provenienza.
            pagine_lettura = set(pagine_sp) | set(pagine_ce) | set(struttura.pagine_dettaglio)
            righe = righe_da_pdf(file_path, pagine_lettura, ruoli, ocr_text)
            fo = foglie(righe)
            # Task 21: la massa grezza per lato SOLO quando il prospetto SP e' a sezioni
            # contrapposte (entrambi i lati fisici presenti fra le foglie di SP - "bs"): un
            # elenco a colonna unica non oppone alcuna colonna attivo/passivo fisica, e
            # att/pas netti (il ramo None di misura()) restano l'unica base valida, come
            # sempre. "L"/"R" sono attivo/passivo per costruzione di ``collect_source_rows``
            # (sezioni contrapposte: attivo sempre a sinistra, passivo sempre a destra - lo
            # stesso convenzione che ``applica_lato``/CLAUDE.md presumono altrove), mai
            # ridefiniti qui per singolo documento. Il PRESUPPOSTO (un prospetto a sezioni
            # contrapposte) si legge ancora sulle foglie grezze, PRIMA di ``da_foglie`` - ma
            # la SOMMA (fix round 3, ruling del proprietario 2026-09-28, diagnosi TM 589/590)
            # viene DOPO, da ``diag["grezzo_sp"]``: sommare qui, su ``fo`` non ancora
            # classificato, include righe come "Totale Attivita'" che marca_totali lascia
            # viva come foglia (i suoi figli non sono nella pagina letta, o non si
            # risolvono) e che da_foglie scarta poi come 'X'/escluse - un totale duplicato
            # che raddoppia la massa (TM 589: grezzo attivo 2x il vero attivo).
            _fo_sp = [r for r in fo if r.sezione == "bs"]
            _sezioni_contrapposte = {"L", "R"} <= {r.lato for r in _fo_sp}
            letture = leggi_conti_fn(righe, fo)

            fase = "conti"
            bs, ce, diag = da_foglie(fo)
            if _sezioni_contrapposte:
                _grezzo = diag.get("grezzo_sp") or {}
                _grezzo_sp = {"attivo": _grezzo.get("L", Decimal(0)),
                             "passivo": _grezzo.get("R", Decimal(0))}
            # Il report finisce in validation_report via json.dumps: niente Decimal nella
            # diagnostica (TM 589/590, budget_624/330 fallivano al salvataggio, 2026-09-28).
            if "grezzo_sp" in diag:
                diag["grezzo_sp"] = {k: str(v) for k, v in diag["grezzo_sp"].items()}
            prior, stampati = None, deterministici
        else:
            from importers.detail_enrichment import collect_source_rows
            from importers.import_snello.lettura import trascrivi_pagine, voci_di_legge
            from importers.import_snello.conti import da_coppie

            leggi_voci_fn = leggi_voci or voci_di_legge
            trascrivi_fn = trascrivi or trascrivi_pagine
            righe_documento = collect_source_rows(file_path, ocr_text=ocr_text)
            if modo == "legge_con_dettaglio":
                # Le righe con codice conto non entrano nella lettura delle macro voci: le
                # didascalie portano gia' il valore netto stampato, i conti sotto il lordo e i
                # fondi, e il modello li sommerebbe due volte (budget_313: sp13 612.540 dal
                # conto economico letto sui conti; budget_352: attivo 3,45 M contro 1.675.141,10
                # stampato). Stessa regola del lettore deterministico (``_ACCOUNT_CODE``).
                from importers.standard_ivcee_parser import riga_conto

                righe_documento = [r for r in righe_documento if not riga_conto(r.text, bool(r.amounts))]
            letture = {"sp": 1, "ce": 1}

            # Ruling (c) addendum, Task 18 (owner, dopo la diagnosi AMBIENTA §7-8): un
            # "riclassificato con codici IVCEE" che e' ANCHE schema di legge coi totali
            # stampati non e' un piano dei conti piatto - le sue macro-voci possono stare
            # INTERAMENTE su una pagina che la vision ha classificato "dettaglio_conti" per
            # il solo cambio pagina fisico (AMBIENTA: "8) per godimento di beni di terzi" e
            # "9) per il personale" stanno solo a pag.5, "5)-14) Debiti..." solo a pag.3).
            # Solo per questo stesso segnale (`struttura.macro_include_dettaglio`, mai per un
            # "legge" qualunque: le sue pagine_dettaglio sono tabelle di nota integrativa
            # vere, non macro-voci) le pagine_dettaglio entrano anche nel prompt macro, non
            # solo nel recupero dettaglio a valle (enrich_pdf_details).
            if getattr(struttura, "macro_include_dettaglio", False):
                pagine_sp = sorted(set(pagine_sp) | set(struttura.pagine_dettaglio))
                pagine_ce = sorted(set(pagine_ce) | set(struttura.pagine_dettaglio))

            # Le pagine "prospetto_sp_e_ce" (SP e CE sulla stessa pagina fisica) entrano in
            # ENTRAMBE pagine_sp e pagine_ce: se ce ne sono, non le leggiamo due volte (fix 8).
            pagine_condivise = {m["pagina"] for m in struttura.mappe if m.get("tipo_pagina") == "prospetto_sp_e_ce"}

            def _leggi_sezione(pagine: list[int], intestazioni: list[str], nota: str = "") -> dict:
                pagine_insieme = set(pagine)
                if any(p in struttura.pagine_senza_testo for p in pagine):
                    testo = trascrivi_fn(file_path, pagine)
                else:
                    testo = "\n".join(f"{r.id}|{r.text}" for r in righe_documento if r.page in pagine_insieme)
                if nota:
                    return leggi_voci_fn(testo, intestazioni, nota=nota)
                return leggi_voci_fn(testo, intestazioni)

            def _leggi_sp_e_ce(nota_sp: str = "", nota_ce: str = ""):
                if pagine_condivise:
                    pagine_unione = sorted(set(pagine_sp) | set(pagine_ce))
                    intestazioni_unione = list(dict.fromkeys(list(struttura.intestazioni_sp)
                                                             + list(struttura.intestazioni_ce)))
                    nota = " ".join(n for n in (nota_sp, nota_ce) if n)
                    nota_unione = f"{_NOTA_PAGINA_CONDIVISA} {nota}" if nota else _NOTA_PAGINA_CONDIVISA
                    combinato = _leggi_sezione(pagine_unione, intestazioni_unione, nota=nota_unione)
                    return combinato, combinato
                with ThreadPoolExecutor(2) as ex:
                    fut_sp = ex.submit(_leggi_sezione, pagine_sp, struttura.intestazioni_sp, nota_sp)
                    fut_ce = ex.submit(_leggi_sezione, pagine_ce, struttura.intestazioni_ce, nota_ce)
                    return fut_sp.result(), fut_ce.result()

            def _combina(sp_res: dict, ce_res: dict):
                if sp_res is ce_res:
                    coppie_corrente = sp_res["corrente"]
                    coppie_precedente = sp_res["precedente"]
                    stampati = sp_res["totali"]
                else:
                    coppie_corrente = sp_res["corrente"] + ce_res["corrente"]
                    coppie_precedente = sp_res["precedente"] + ce_res["precedente"]
                    stampati = _unisci_totali(sp_res["totali"], ce_res["totali"])
                # I totali dichiarati dal documento (lettura deterministica, nessuna chiamata
                # modello) vincono su quelli riportati dall'LLM quando esistono entrambi: quelli
                # dell'LLM vengono dalla STESSA chiamata che ha letto le voci, quindi una
                # sotto-estrazione sistematica non troverebbe mai un contraddittorio reale.
                for chiave in ("totale_attivo", "totale_passivo"):
                    if deterministici.get(chiave) is not None:
                        stampati[chiave] = deterministici[chiave]
                _coppie_lette[:] = list(coppie_corrente)
                bs, ce, diag = da_coppie(coppie_corrente)
                prior = da_coppie(coppie_precedente) if coppie_precedente else None
                return bs, ce, diag, prior, stampati

            sp_res, ce_res = _leggi_sp_e_ce()

            fase = "conti"
            bs, ce, diag, prior, stampati = _combina(sp_res, ce_res)

        fase = "verifica"
        bs, ce, tappo, esito, m, s = _verifica(bs, ce, stampati)

        if (modo in _MODI_LEGGE and esito in ("oltre_soglia", "vuoto")
                and not _contraddizioni(m, s, stampati)):
            fase = "lettura"
            if abs(m["scarto_sp"]) > _limite_interno(s) or m["scarto_stampati"] > s:
                sezione = "sp"
            else:
                sezione = "ce"
            if esito == "vuoto":
                nota = ("Una lettura precedente non ha dato alcuna voce: attivo e passivo sono "
                        "risultati entrambi zero. Controlla se il prospetto e' stato individuato "
                        "correttamente.")
            elif _causa_stampati(m, s):
                nota = (f"Una lettura precedente dava un totale stampato dal documento (Totale "
                        f"Attivo/Totale Passivo) in disaccordo con le voci lette, per "
                        f"{m['scarto_stampati']} euro: controlla se manca o si e' duplicata una "
                        f"voce, o se il totale stampato dal documento e' quello giusto.")
            else:
                scarto = max(abs(m["scarto_sp"]), m["scarto_stampati"])
                nota = (f"Una lettura precedente dava uno scarto di {scarto} euro fra attivo e "
                        f"passivo (o fra risultato CE e SP): controlla voci mancanti, doppie o "
                        f"totali presi come voci.")
            if pagine_condivise:
                # La pagina condivisa si rilegge tutta insieme (SP e CE): entrambe le sezioni
                # dichiarano la rilettura, non solo quella scelta dall'euristica (minor 4, fix
                # round 1) — altrimenti la diagnostica mentirebbe su quale sezione e' stata
                # riletta davvero.
                letture["sp"] = letture.get("sp", 1) + 1
                letture["ce"] = letture.get("ce", 1) + 1
                sp_res, ce_res = _leggi_sp_e_ce(nota_sp=nota, nota_ce=nota)
            elif sezione == "sp":
                letture[sezione] = letture.get(sezione, 1) + 1
                sp_res = _leggi_sezione(pagine_sp, struttura.intestazioni_sp, nota=nota)
            else:
                letture[sezione] = letture.get(sezione, 1) + 1
                ce_res = _leggi_sezione(pagine_ce, struttura.intestazioni_ce, nota=nota)

            fase = "conti"
            bs, ce, diag, prior, stampati = _combina(sp_res, ce_res)

            fase = "verifica"
            bs, ce, tappo, esito, m, s = _verifica(bs, ce, stampati)

        if esito == "vuoto":
            # Un'estrazione vuota non ha nulla di sensato da salvare: resta un ripiego,
            # sempre (anche dopo l'unica rilettura in modo "legge").
            report = {
                "esito": "ripiego", "fase": "verifica", "errore": esito, "modo": modo,
                "struttura": struttura.report(), "fonte": "qwen",
                "misura": {"corrente": {k: str(v) for k, v in m.items()}},
                "tappo": {"corrente": tappo}, "letture": letture, "diag": diag,
                "anomalie": _anomalie(bs, diag), "secondi": round(time.monotonic() - t0, 1),
                "deterministico": _report_deterministico,
                **_coppie_nel_report(_coppie_lette, "vuoto"),
            }
            raise SnelloNonRiuscito(report)

        causa = None
        contraddizioni: list = []
        if esito == "oltre_soglia":
            # Task 17 (decisione del proprietario, 2026-09-27): «se il bilancio non e'
            # quadrato deve essere comunque importato con avviso, l'utente lo correggera'
            # nella tab rettifiche». Oltre soglia dopo l'unica rilettura (modo "legge") o
            # direttamente (modo "conti", che non rilegge) non e' piu' un ripiego: si
            # adotta il risultato con lo sbilancio dichiarato. Nessun tappo si applica -
            # bs/ce restano quelli restituiti da tappa() (invariati), e gli scarti
            # misurati (scarto_sp/scarto_ce/scarto_stampati) restano in "misura", letti
            # da pdf_importer per costruire l'avviso mostrato all'utente.
            esito = "squadrato"
            contraddizioni = _contraddizioni(m, s, stampati)
            causa = ("documento_sbilanciato" if contraddizioni
                     else "stampati" if _causa_stampati(m, s) else None)

        prior_bs = prior_ce = prior_diag = None
        m_prec = tappo_prec = None
        precedente_stato = None
        if modo in _MODI_LEGGE and prior is not None:
            pbs, pce, pdiag = prior
            pbs, pce, tappo_prec, esito_prec, m_prec, _ = _verifica(pbs, pce, None)
            if esito_prec in ("oltre_soglia", "vuoto"):
                precedente_stato = "escluso_oltre_soglia"
                m_prec = tappo_prec = None
            else:
                precedente_stato = "incluso"
                prior_bs, prior_ce, prior_diag = pbs, pce, pdiag
    except SnelloNonRiuscito:
        raise
    except Exception as e:
        raise SnelloNonRiuscito({"esito": "ripiego", "fase": fase, "errore": type(e).__name__}) from e

    bs["_plug_residual"] = Decimal(tappo["importo"]) if tappo and "importo" in tappo else Decimal(0)
    bs["_unclassified_mass"] = _unclassified_mass(diag)

    misura_report = {"corrente": {k: str(v) for k, v in m.items()}}
    tappo_report = {"corrente": tappo}
    if modo in _MODI_LEGGE and m_prec is not None:
        misura_report["precedente"] = {k: str(v) for k, v in m_prec.items()}
        tappo_report["precedente"] = tappo_prec

    report = {
        "esito": esito, "modo": modo, "struttura": struttura.report(), "fonte": "qwen",
        "misura": misura_report, "tappo": tappo_report, "letture": letture, "diag": diag,
        "anomalie": _anomalie(bs, diag), "secondi": round(time.monotonic() - t0, 1),
        "deterministico": _report_deterministico,
    }
    report.update(_coppie_nel_report(_coppie_lette, esito))
    if modo in _MODI_LEGGE and precedente_stato is not None:
        report["precedente"] = precedente_stato
    if causa:
        # Squadrato solo contro il totale stampato (SP e CE interni entro soglia).
        report["causa"] = causa
    if contraddizioni:
        # Una voce per contraddizione che il documento stampa da solo (Task 27): l'avviso
        # dice una frase per ciascuna, mai due volte la stessa.
        report["contraddizioni"] = contraddizioni

    return Risultato(bs=bs, ce=ce, prior_bs=prior_bs, prior_ce=prior_ce, report=report, struttura=struttura)
