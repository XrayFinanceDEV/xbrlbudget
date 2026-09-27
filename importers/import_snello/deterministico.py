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
        return {"adottato": False, "parser": nome, "esito": "oltre_soglia"}
    stampati = {k: v for k, v in (stampati_raw or {}).items() if v is not None} or None
    bs, ce, tappo, esito, m = _verifica_bilancio(bs, ce, stampati)
    if esito not in ("ok", "tappo"):
        return {"adottato": False, "parser": nome, "esito": "oltre_soglia"}
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
    massa = Decimal(bs.get("_unclassified_mass", 0) or 0)
    s = soglia(m["attivo"])
    if massa > s:
        return {"adottato": False, "parser": nome, "esito": "massa_non_classificata",
                "unclassified_mass": str(massa.quantize(_C))}
    return {"adottato": True, "parser": nome, "esito": esito, "bs": bs, "ce": ce,
            "tappo": tappo, "misura": m}


def _prova_standard_ivcee(file_path: str) -> dict | None:
    """Schema di legge a colonne comparative (o compatto a colonna unica): None se il
    documento non e' nemmeno riconosciuto come tale (``has_comparative_ivcee_columns``
    falso), altrimenti l'esito (adottato o no) di questo solo parser."""
    from importers.standard_ivcee_parser import (
        extract_standard_ivcee_balances,
        extract_standard_ivcee_income,
        has_comparative_ivcee_columns,
    )

    if not has_comparative_ivcee_columns(file_path):
        return None
    bs_raw, _ = extract_standard_ivcee_balances(file_path)
    ce_raw, _ = extract_standard_ivcee_income(file_path)
    if bs_raw is None or ce_raw is None:
        return {"adottato": False, "parser": "standard_ivcee_parser", "esito": "oltre_soglia"}
    stampati = {"totale_attivo": bs_raw.get("totale_attivo"),
                "totale_passivo": bs_raw.get("totale_passivo")}
    return _esito("standard_ivcee_parser", bs_raw, ce_raw, stampati)


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
        return {"adottato": False, "parser": "situazione_contabile_parser", "esito": "oltre_soglia"}
    return _esito("situazione_contabile_parser", bs_raw, ce_raw, None)


def tentativo(file_path: str, ocr_text: str | None = None) -> dict:
    """Prova, in ordine, un solo parser deterministico applicabile: il primo che si
    applica decide (mai i due sommati, mai un secondo tentativo dopo il primo). Ritorna
    sempre un dict con almeno ``adottato``/``parser``/``esito``; ``esito`` pubblico e'
    uno tra "ok"/"tappo" (adottato) o "non_applicabile"/"errore"/"oltre_soglia"/
    "massa_non_classificata" (non adottato) - mai una terza via. Su "massa_non_classificata"
    il dict porta anche ``unclassified_mass`` (stringa Decimal): la massa non scompare, solo
    non basta a se stessa per l'adozione (ruling a, Task 18)."""
    for nome, prova in (
        ("standard_ivcee_parser", lambda: _prova_standard_ivcee(file_path)),
        ("situazione_contabile_parser", lambda: _prova_situazione_contabile(file_path, ocr_text)),
    ):
        try:
            esito = prova()
        except Exception:
            return {"adottato": False, "parser": nome, "esito": "errore"}
        if esito is not None:
            return esito
    return {"adottato": False, "parser": None, "esito": "non_applicabile"}
