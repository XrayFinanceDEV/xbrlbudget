"""Verifica del percorso snello: stesse formule dell'app (campi di quadratura, risultato CE canonico),
soglia relativa, tappo dichiarato entro soglia su altri crediti, altri debiti, servizi (decisione del
proprietario, 2026-09-26). Oltre soglia non si tocca nulla: decide il chiamante."""
from __future__ import annotations

from decimal import Decimal

import config
from calculations.ce_result import calculate_ce_result
from importers.iv_cee_hierarchy import _ATTIVO_FIELDS, _PASSIVO_FIELDS

_C = Decimal("0.01")


def soglia(totale_attivo: Decimal) -> Decimal:
    minimo = Decimal(str(config.IMPORT_SNELLO_SOGLIA_MIN))
    pct = Decimal(str(config.IMPORT_SNELLO_SOGLIA_PCT))
    return max(minimo, abs(Decimal(totale_attivo)) * pct / 100).quantize(_C)


def _coerente(letti: dict, tolleranza: Decimal) -> bool:
    """Attivo e passivo dichiarati si tengono in piedi da soli: presenti entro
    ``tolleranza`` l'uno dall'altro, o dall'altro PIU' l'utile dichiarato (una situazione a
    sezioni contrapposte puo' stampare il passivo al netto del risultato d'esercizio - stesso
    principio di ``_fold_utile_in_passivo`` sotto, qui solo per decidere se fidarsi della
    lettura, non per correggerla). Nessuno dei due presente, o troppo distanti da entrambi i
    confronti: non coerente."""
    a, p = letti.get("attivo"), letti.get("passivo")
    if a is None or p is None:
        return False
    a, p = Decimal(a), Decimal(p)
    if abs(a - p) <= tolleranza:
        return True
    u = letti.get("utile")
    return u is not None and abs(a - (p + Decimal(u))) <= tolleranza


def totali_stampati(file_path: str, regola: dict | None = None) -> dict:
    """I totali che il documento stampa da solo (regex sul testo grezzo, nessuna chiamata
    modello): ancora indipendente dall'estrattore, riusata dal vecchio importatore
    (``pdf_extractor_llm._declared_control_totals``) per dare a ``misura()``/``tappa()`` un
    contraddittorio reale - solo apparente in modo "legge" (i "totali stampati" vengono
    dalla stessa chiamata LLM che legge le voci, non da una lettura indipendente).

    ``regola`` (Task 21, modo "conti" soltanto): quando un rigo di controllo stampa piu'
    importi per lato (es. "Saldo non rettificato | Rettifiche | Saldo finale"), il default
    (nessun ``regola``, comportamento di sempre per modo "legge") prende il primo numero
    dopo il marcatore - sulle situazioni contabili a piu' colonne e' quasi sempre quello
    sbagliato. Passando ``regola`` (stessa forma di ``righe.regola_colonna()``, gia' usata
    per leggere le foglie) si legge invece la colonna che la struttura ha identificato come
    saldo; il chiamante deve passare ``regola=None`` (o non chiamare affatto) quando quella
    colonna non si identifica con certezza - qui non c'e' alcun ripiego silenzioso.

    Fix round 2 (ruling del proprietario, 2026-09-28, diagnosi budget_297): la lettura sul
    testo ordinato per POSIZIONE (``_extract_full_text(..., forza_ordinamento=True)``) si prova
    SOLO quando la lettura primaria (testo di sempre) non e' coerente (``_coerente``: attivo e
    passivo assenti, o troppo distanti anche tenendo conto dell'utile) - mai come fonte IN PIU'
    da fondere con "il maggiore vince" (fix round 1, scartato: budget_297/664 si sistemavano,
    ma budget_280/320/379/TM 589/590 si rompevano - ``_section_heading_total``, un meccanismo
    diverso della stessa funzione, legge un'etichetta su una riga e il proprio importo sulla
    riga IMMEDIATAMENTE seguente, e l'ordinamento per posizione unisce le due righe in una,
    rompendolo). Se anche la lettura ordinata non e' coerente, resta quella primaria (mai
    peggiorare un dato assente/incoerente con uno diverso ma ugualmente incoerente)."""
    try:
        from importers.pdf_extractor_llm import _declared_control_totals, _extract_full_text
        letti = _declared_control_totals(file_path, colonna=regola)
        tolleranza = soglia(letti["attivo"]) if letti.get("attivo") is not None else soglia(Decimal(0))
        if not _coerente(letti, tolleranza):
            testo_ordinato = _extract_full_text(file_path, forza_ordinamento=True)
            ordinato = _declared_control_totals(file_path, text=testo_ordinato, colonna=regola)
            tolleranza_ord = (soglia(ordinato["attivo"]) if ordinato.get("attivo") is not None
                              else tolleranza)
            if _coerente(ordinato, tolleranza_ord):
                letti = ordinato
    except Exception:
        letti = {}
    return {"totale_attivo": letti.get("attivo"), "totale_passivo": letti.get("passivo")}


def _fold_utile_in_passivo(stampati: dict | None, utile: Decimal) -> dict | None:
    """Il 'Totale Passivo' di una situazione contabile a sezioni contrapposte puo' non
    includere il risultato d'esercizio (stampato a parte, accanto al pareggio): senza
    correggerlo apparirebbe uno scarto quanto l'utile che non e' una sotto-estrazione, e'
    solo una convenzione di stampa. Riusa la regola del vecchio importatore
    (``pdf_extractor_llm._reconcile_utile_in_passivo``): ripiega il risultato dentro il
    totale passivo SOLO quando il gap coincide col risultato entro tolleranza - un gap
    diverso e' massa vera mancante, e resta com'e'."""
    if not stampati:
        return stampati
    ta, tp = stampati.get("totale_attivo"), stampati.get("totale_passivo")
    if ta is None or tp is None:
        return stampati
    from importers.pdf_extractor_llm import _reconcile_utile_in_passivo
    corretto = _reconcile_utile_in_passivo(
        {"totale_attivo": Decimal(ta), "totale_passivo": Decimal(tp), "sp13_utile_perdita": utile},
        "snello")
    nuovo_tp = corretto["totale_passivo"]
    if nuovo_tp == Decimal(tp):
        return stampati
    nuovo = dict(stampati)
    nuovo["totale_passivo"] = nuovo_tp
    return nuovo


def misura(bs: dict, ce: dict, stampati: dict | None = None, forma: str | None = None,
           grezzo: dict | None = None) -> dict:
    """``grezzo`` (Task 21, modo "conti" a sezioni contrapposte soltanto): la somma per
    lato delle foglie COSI' COME STAMPATE, prima di ``applica_lato``/netting dei fondi -
    quando un fondo o un altro contro-conto sta fisicamente nella colonna opposta a quella
    del suo bene/debito, ``att``/``pas`` (sotto, gia' netti) non sono piu' la stessa massa
    del totale che il documento stampa per QUELLA colonna: confrontare lo stampato contro
    ``att``/``pas`` netti scambierebbe un artefatto della classificazione per un vero
    sbilancio (ruling Task 21: "la colonna e' la verita' sul lato", CLAUDE.md). Con
    ``grezzo`` fornito, SOLO il confronto ``scarto_stampati`` usa la massa grezza per lato;
    ``att``/``pas`` restituiti (e quindi ``scarto_sp``/``scarto_ce``) restano quelli netti
    di sempre, invariati."""
    att = sum((Decimal(bs.get(k, 0)) for k in _ATTIVO_FIELDS), Decimal(0))
    pas = sum((Decimal(bs.get(k, 0)) for k in _PASSIVO_FIELDS), Decimal(0))
    sp13 = Decimal(bs.get("sp13_utile_perdita", 0))
    utile = calculate_ce_result(ce).net_profit
    stampati = _fold_utile_in_passivo(stampati, utile)
    bilancio = (att - pas, utile - sp13)                     # sp13 e' il risultato corrente
    verifica = (att - pas - utile, Decimal(0))               # sp13 e' l'anno prima (resta nel netto); il corrente e' l'utile CE
    if forma is None:
        forma, (s_sp, s_ce) = min((("bilancio", bilancio), ("verifica", verifica)),
                                  key=lambda x: abs(x[1][0]) + abs(x[1][1]))
    elif forma == "bilancio":
        s_sp, s_ce = bilancio
    elif forma == "verifica":
        s_sp, s_ce = verifica
    else:
        raise ValueError(f"forma sconosciuta: {forma!r} (attesa 'bilancio', 'verifica' o None)")
    att_grezzo = Decimal(grezzo["attivo"]) if grezzo and grezzo.get("attivo") is not None else att
    pas_grezzo = Decimal(grezzo["passivo"]) if grezzo and grezzo.get("passivo") is not None else pas
    scarto_stampati = Decimal(0)
    for chiave, nostro in (("totale_attivo", att_grezzo),
                           ("totale_passivo", pas_grezzo if forma == "bilancio" else pas_grezzo + utile)):
        v = (stampati or {}).get(chiave)
        if v is not None:
            scarto_stampati = max(scarto_stampati, abs(nostro - Decimal(v)))
    return {"attivo": att, "passivo": pas, "utile_ce": utile, "sp13": sp13, "forma": forma,
            "scarto_sp": s_sp.quantize(_C), "scarto_ce": s_ce.quantize(_C), "scarto_stampati": scarto_stampati.quantize(_C)}


def normalizza_forma(bs: dict, ce: dict, m: dict) -> dict:
    bs = dict(bs)
    if m["forma"] == "verifica":
        precedente = Decimal(bs.get("sp13_utile_perdita", 0))
        bs["sp12g_utili_perdite_portati"] = Decimal(bs.get("sp12g_utili_perdite_portati", 0)) + precedente
        bs["sp12_riserve"] = Decimal(bs.get("sp12_riserve", 0)) + precedente
        bs["sp13_utile_perdita"] = m["utile_ce"].quantize(_C)
    return bs


def _aggiungi(d: dict, campo: str, aggregato: str, v: Decimal) -> None:
    d[campo] = (Decimal(d.get(campo, 0)) + v).quantize(_C)
    d[aggregato] = (Decimal(d.get(aggregato, 0)) + v).quantize(_C)


def tappa(bs: dict, ce: dict, m: dict, s: Decimal):
    if m["attivo"] == 0 and m["passivo"] == 0:   # estrazione vuota: mai "ok"
        return bs, ce, None, "vuoto"
    if abs(m["scarto_sp"]) > s or abs(m["scarto_ce"]) > s or m["scarto_stampati"] > s:
        return bs, ce, None, "oltre_soglia"
    if m["scarto_sp"] == 0 and m["scarto_ce"] == 0:
        return bs, ce, None, "ok"
    nuovo_ce06 = None
    if m["scarto_ce"] != 0:       # utile CE diverso da sp13: i servizi assorbirebbero la differenza
        nuovo_ce06 = (Decimal(ce.get("ce06_servizi", 0)) + m["scarto_ce"]).quantize(_C)
        if nuovo_ce06 < 0:        # ma non sotto zero: il tappo non si applica, nulla si tocca
            return bs, ce, None, "oltre_soglia"
    bs, ce, tappo = dict(bs), dict(ce), {"soglia": str(s)}
    if m["scarto_sp"] > 0:        # attivo in piu': manca passivo
        _aggiungi(bs, "sp16g_altri_debiti_breve", "sp16_debiti_breve", m["scarto_sp"])
        tappo.update(campo="sp16g_altri_debiti_breve", importo=str(m["scarto_sp"]))
    elif m["scarto_sp"] < 0:      # manca attivo
        _aggiungi(bs, "sp06g_crediti_altri_breve", "sp06_crediti_breve", -m["scarto_sp"])
        tappo.update(campo="sp06g_crediti_altri_breve", importo=str(-m["scarto_sp"]))
    if nuovo_ce06 is not None:
        ce["ce06_servizi"] = nuovo_ce06
        tappo["ce"] = {"campo": "ce06_servizi", "importo": str(m["scarto_ce"])}
    return bs, ce, tappo, "tappo"
