"""Deterministico prima di Qwen (Task 16, punto b).

Prima di qualunque lettura del modello, prova i parser deterministici del vecchio
importatore che il repo gia' usa per la route C/IV-CEE: se uno di loro riconosce il
documento e il suo risultato, dopo la verifica di questo percorso (le stesse regole di
``misura``/``tappa``: fondi gia' netti, nomi pieni di colonna, ``Decimal``, aggregati
coerenti), quadra con esito "ok" o "tappo", si adotta come risultato snello a zero
chiamate al modello. Se non si applica, solleva o non quadra, non si tocca nulla: il
chiamante prosegue col percorso Qwen di sempre. Mai un secondo tentativo dopo il primo
che si e' applicato (nessun sommare i due candidati).
"""
from __future__ import annotations

from decimal import Decimal

from importers.import_snello.percorsi import NOMI
from importers.import_snello.verifica import misura, soglia, tappa

_C = Decimal("0.01")


def _adatta(dati: dict | None) -> dict:
    """Codici brevi (``sp03``, ``ce01``) o gia' pieni (``sp03_immob_materiali``) -> nomi
    pieni di colonna; una chiave con underscore (marcatore diagnostico del vecchio
    importatore: ``_plug_residual``, ``_unclassified_mass``, ``_netted_contra``,
    ``_skip_declared_reconcile``...) passa TALE E QUALE, mai un ``Decimal`` forzato
    (alcune sono bool o str) - stessa regola di ``_map_sc_keys`` in ``pdf_importer.py``
    (``if '_' in k: result[k] = v``), riusata qui via ``NOMI`` (percorsi.py) per non
    importare quel modulo (ciclo: pdf_importer importa import_snello). Un estrattore
    dichiara sempre le proprie chiavi diagnostiche, anche a zero: scartarle qui le
    farebbe leggere a valle come «pulito», non come «non lo so» (CLAUDE.md). Ogni
    altra chiave (totali dichiarati come ``totale_attivo``) non e' un campo sp*/ce* e
    si scarta, quella si, in silenzio."""
    if not dati:
        return {}
    out: dict = {}
    for k, v in dati.items():
        if v is None:
            continue
        if k.startswith("_"):
            out[k] = v
            continue
        pieno = k if k in NOMI.values() else NOMI.get(k)
        if pieno:
            out[pieno] = Decimal(v).quantize(_C)
    return out


def _verifica_bilancio(bs: dict, ce: dict, stampati: dict | None):
    """Le stesse regole di lean (misura/tappa/soglia). Forma sempre "bilancio": questi
    parser scrivono gia' sp13 come risultato dell'esercizio CORRENTE (mai il pregresso
    di un conto di netto) - mai l'euristica bilancio/verifica che ``importa()`` applica
    al percorso Qwen, che serve solo quando quella distinzione e' davvero incerta."""
    m = misura(bs, ce, stampati, forma="bilancio")
    s = soglia(m["attivo"])
    bs, ce, tappo, esito = tappa(bs, ce, m, s)
    return bs, ce, tappo, esito, m


def _esito(nome: str, bs_raw: dict, ce_raw: dict, stampati_raw: dict | None) -> dict:
    bs, ce = _adatta(bs_raw), _adatta(ce_raw)
    if not bs or not ce:
        # Il candidato non ha restituito nulla: e' "vuoto", non "oltre soglia" (Task 25: la
        # diagnostica non deve far pensare a una quadratura mancata dove non c'e' stata lettura).
        return {"adottato": False, "parser": nome, "esito": "vuoto"}
    stampati = {k: v for k, v in (stampati_raw or {}).items() if v is not None} or None
    bs, ce, tappo, esito, m = _verifica_bilancio(bs, ce, stampati)
    massa = Decimal(bs.get("_unclassified_mass", 0) or 0)
    s = soglia(m["attivo"])
    if esito not in ("ok", "tappo"):
        if esito == "vuoto":
            return {"adottato": False, "parser": nome, "esito": "vuoto"}
        if massa > s:
            # Task 28 fix 1: la massa non classificata si controlla PRIMA - una lettura di cui
            # non ci si fida non e' mai un ripiego, sbilanciata o no.
            return {"adottato": False, "parser": nome, "esito": "massa_non_classificata",
                    "unclassified_mass": str(massa.quantize(_C))}
        out = {"adottato": False, "parser": nome, "esito": "oltre_soglia"}
        # Task 28 (fix 2): ripiego solo per una lettura VICINA - il peggiore scarto entro la
        # soglia relativa (il vecchio limite del tappo, max(100 euro, 0,1% dell'attivo)). Una
        # lettura lontana non prende il posto del ripiego sull'importatore vecchio.
        peggiore = max(abs(m["scarto_sp"]), abs(m["scarto_ce"]), abs(m["scarto_stampati"]))
        if peggiore <= s:
            # SENZA tappo (tappa() non l'ha toccata); vuoto/errore/reso falliti non portano nulla.
            out["lettura"] = {"bs": bs, "ce": ce, "misura": m}
        return out
    # Ruling (a), Task 18 (2026-09-27): quadrare da solo non basta piu'. Un candidato
    # bilanciato la cui massa non classificata (dichiarata dal parser sottostante, mai un
    # hardcoded zero) supera la STESSA soglia che verifica.tappa() usa per lo scarto
    # (max(100 euro, 0,1% dell'attivo)) non si adotta: e' un fallback che ha gia' contato la
    # massa una volta (il foglio quadra), ma quella massa puo' comunque attraversare un
    # aggregato (ce05 finito in ce06, personale in ce08d, sp03 in sp03d, ce02/ce03 in ce10 -
    # banco TM-BUSINESS 589/590, 2026-09-27: Qwen li classificava bene in ~23s, il
    # deterministico invece li dichiarava "puliti" a zero chiamate). La massa resta
    # dichiarata (mai scartata), solo non best-effort-adottata: il chiamante prosegue col
    # percorso Qwen di oggi, invariato.
    if massa > s:
        return {"adottato": False, "parser": nome, "esito": "massa_non_classificata",
                "unclassified_mass": str(massa.quantize(_C))}
    return {"adottato": True, "parser": nome, "esito": esito, "bs": bs, "ce": ce,
            "tappo": tappo, "misura": m}


def _prova_xbrl_reso(file_path: str) -> dict | None:
    """Il PDF reso da un XBRL depositato (Task 25): tassonomia nel piede di pagina, prospetti come
    elenco di righe, totali stampati che il lettore deve riprodurre al centesimo
    (``xbrl_reso_parser``: nessuna tolleranza, nessun tappo). None se il documento non e' di
    questa famiglia. Un candidato che non chiude e' rifiutato nominando il controllo fallito
    (``rifiuto``) e la ricerca prosegue come prima; uno che chiude passa comunque dalle STESSE
    regole di adozione degli altri (``_esito``), e porta con se' l'anno precedente e i dettagli
    letti dal prospetto e dalla nota (nessuna lettura del modello, mai)."""
    from importers.xbrl_reso_parser import estrai, riconosci

    if not riconosci(file_path):
        return None
    candidato = estrai(file_path)
    if candidato is None:
        return None
    if not candidato["adottabile"]:
        return {"adottato": False, "parser": "xbrl_reso_parser", "esito": "oltre_soglia",
                "rifiuto": candidato["rifiuto"]}
    esito = _esito("xbrl_reso_parser", candidato["bs"], candidato["ce"], candidato["stampati"])
    esito["dettagli"] = candidato["dettagli"]
    esito["ignoti"] = candidato["ignoti"]
    if esito["adottato"] and candidato["prior_bs"] is not None:
        esito["prior_bs"] = _adatta(candidato["prior_bs"])
        esito["prior_ce"] = _adatta(candidato["prior_ce"])
    esito["prior_stato"] = candidato["prior_stato"]
    if len(candidato["anni"]) > 1:
        esito["anno_precedente"] = candidato["anni"][1]
    if candidato.get("prior_rifiuto"):
        esito["prior_rifiuto"] = candidato["prior_rifiuto"]
    return esito


def _prova_standard_ivcee(file_path: str) -> dict | None:
    """Schema di legge a colonne comparative, o compatto a colonna unica (Task 23):
    ``has_comparative_ivcee_columns`` falso non significa piu' "non provarci" - vuol
    dire solo che il documento non ha due colonne affiancate, e il modulo ha gia' un
    ramo compatto (``_parse_compact_balance``/``_parse_compact_income``, dietro
    ``extract_standard_ivcee_balances``/``_income``) che quel caso lo tenta comunque,
    con la stessa garanzia "il totale stampato decide" e gli stessi controlli
    incrociati. Se anche il ramo compatto non riconosce il documento (nessuna
    "stato patrimoniale"/incrocio a colonna singola), i due extract tornano
    ``None`` e qui si ritorna ``None``: mai bloccare situazione_contabile_parser
    per un documento che questo parser non ha nemmeno provato a leggere."""
    from importers.standard_ivcee_parser import (
        extract_standard_ivcee_balances,
        extract_standard_ivcee_income,
        has_comparative_ivcee_columns,
    )

    comparativo = has_comparative_ivcee_columns(file_path)
    bs_raw, _ = extract_standard_ivcee_balances(file_path)
    ce_raw, _ = extract_standard_ivcee_income(file_path)
    if bs_raw is None or ce_raw is None:
        if not comparativo:
            return None
        return {"adottato": False, "parser": "standard_ivcee_parser", "esito": "vuoto"}
    stampati = {"totale_attivo": bs_raw.get("totale_attivo"),
                "totale_passivo": bs_raw.get("totale_passivo")}
    return _esito("standard_ivcee_parser", bs_raw, ce_raw, stampati)


def _prova_schema_con_dettaglio(file_path: str) -> dict | None:
    """Schema di legge con dettaglio conti (Task 24; budget_313, budget_352): le macro voci si
    leggono dalle sole didascalie con importo, le righe con codice conto non entrano mai nella
    lettura (``extract_ivcee_didascalie``). Stesse regole di adozione dei parser standard (lo
    stesso ``_esito``: quadratura entro soglia e massa non classificata sotto soglia), nessuna
    nuova. None se il documento non porta righe-conto (non e' questa famiglia: lo leggono i
    parser di sempre); non adottato se le didascalie non chiudono sui totali stampati."""
    from importers.standard_ivcee_parser import _MIN_ACCOUNT_ROWS, extract_ivcee_didascalie

    bs_raw, ce_raw, conti = extract_ivcee_didascalie(file_path)
    if conti < _MIN_ACCOUNT_ROWS:
        return None
    if bs_raw is None or ce_raw is None:
        return {"adottato": False, "parser": "schema_legge_con_dettaglio", "esito": "vuoto",
                "conti_esclusi": conti}
    stampati = {"totale_attivo": bs_raw.get("totale_attivo"),
                "totale_passivo": bs_raw.get("totale_passivo")}
    esito = _esito("schema_legge_con_dettaglio", bs_raw, ce_raw, stampati)
    esito["conti_esclusi"] = conti
    return esito


def _prova_situazione_contabile(file_path: str, ocr_text: str | None) -> dict | None:
    """Bilancio di verifica / situazione contabile (AGO, DEPI, TeamSystem, contrapposte,
    a colonna unica...): None se il documento non e' nemmeno riconosciuto come tale,
    altrimenti l'esito di questo solo estrattore (che al suo interno sceglie da solo,
    come fa oggi la route C, quale dei suoi sotto-formati applicare)."""
    from importers.situazione_contabile_parser import (
        extract_situazione_contabile,
        is_contrapposte_file,
        is_situazione_contabile,
    )

    testo = ocr_text
    if not testo:
        import fitz
        try:
            with fitz.open(file_path) as documento:
                testo = "\n".join(pagina.get_text() for pagina in documento)
        except Exception:
            testo = ""
    if not (is_situazione_contabile(testo) or is_contrapposte_file(file_path)):
        return None
    bs_raw, ce_raw, _, _ = extract_situazione_contabile(
        file_path, return_prior=True, text_override=testo or None)
    if not bs_raw or not ce_raw:
        return {"adottato": False, "parser": "situazione_contabile_parser", "esito": "vuoto"}
    return _esito("situazione_contabile_parser", bs_raw, ce_raw, None)


def _tentativo_classico(file_path: str, ocr_text: str | None = None) -> dict:
    """Prova, in ordine, un solo parser deterministico applicabile: il primo che si
    applica decide (mai i due sommati, mai un secondo tentativo dopo il primo). Ritorna
    sempre un dict con almeno ``adottato``/``parser``/``esito``; ``esito`` pubblico e'
    uno tra "ok"/"tappo" (adottato) o "non_applicabile"/"errore"/"oltre_soglia"/
    "massa_non_classificata" (non adottato) - mai una terza via. Su "massa_non_classificata"
    il dict porta anche ``unclassified_mass`` (stringa Decimal): la massa non scompare, solo
    non basta a se stessa per l'adozione (ruling a, Task 18)."""
    # Ordine (Task 24): parser standard, poi lo schema di legge con dettaglio conti, poi la
    # situazione contabile. Il parser standard che SI APPLICA ma non quadra chiude la ricerca
    # come prima (mai due candidati sommati); lo schema con dettaglio entra solo quando il
    # parser standard non ha adottato, e se anch'esso non adotta la ricerca prosegue esattamente
    # come prima verso la situazione contabile: un bilancio di verifica vero non ha didascalie
    # di legge con importo e non lo vede mai.
    try:
        standard = _prova_standard_ivcee(file_path)
    except Exception:
        return {"adottato": False, "parser": "standard_ivcee_parser", "esito": "errore"}
    if standard is not None and standard["adottato"]:
        return standard
    try:
        con_dettaglio = _prova_schema_con_dettaglio(file_path)
    except Exception:
        con_dettaglio = None
    if con_dettaglio is not None and con_dettaglio["adottato"]:
        return con_dettaglio
    if standard is not None:
        return standard
    try:
        esito = _prova_situazione_contabile(file_path, ocr_text)
    except Exception:
        return {"adottato": False, "parser": "situazione_contabile_parser", "esito": "errore"}
    if esito is not None:
        return esito
    return {"adottato": False, "parser": None, "esito": "non_applicabile"}


def tentativo(file_path: str, ocr_text: str | None = None) -> dict:
    """Come ``_tentativo_classico``, preceduto dal lettore del PDF reso da XBRL (Task 25): se il
    documento e' di quella famiglia ed e' adottabile si adotta, senza provare nient'altro (nessun
    secondo candidato sommato). Altrimenti la ricerca prosegue ESATTAMENTE come prima; un
    candidato riconosciuto ma non adottato lascia il suo motivo nel risultato (``xbrl_reso``),
    mai un silenzio. ``esito`` pubblico: oltre ai valori dichiarati sopra, "vuoto" per un
    candidato che non ha restituito nulla."""
    try:
        reso = _prova_xbrl_reso(file_path)
    except Exception as exc:
        # il ripiego resta, ma un difetto del lettore non deve essere invisibile
        reso = {"adottato": False, "parser": "xbrl_reso_parser", "esito": "errore",
                "errore": f"{type(exc).__name__}: {exc}"}
    if reso is not None and reso["adottato"]:
        return reso
    esito = _tentativo_classico(file_path, ocr_text)
    if reso is not None:
        esito = {**esito, "xbrl_reso": {k: reso[k] for k in ("esito", "rifiuto", "unclassified_mass", "errore") if k in reso}}
    return esito
