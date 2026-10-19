"""Prospetto CEE sintetico a una colonna (budget_1405, Metaldecor, weekend 10/2026).

Uno stato patrimoniale e un conto economico di due pagine con le voci di legge APPIATTITE a un
livello solo: "B) Immobilizzazioni immateriali", "C.II) Crediti", "D) Debiti entro esercizio
successivo", "B.7) Servizi", con i totali di gruppo stampati ("Totale B) Immobilizzazioni", "TOTALE
ATTIVO", "Differenza A - B", "RISULTATO PRIMA DELLE IMPOSTE") e i costi fra parentesi. Un solo anno.

Non e' un riepilogo di macro-voci da rifiutare (``import_snello.riepilogo``): ha le voci che il
modello usa (immateriali, materiali, rimanenze, crediti, liquide, debiti entro/oltre, e il CE
con materie, servizi, personale, ammortamenti...). Manca il dettaglio sotto ogni voce, e per
quello vale la convenzione di sempre dei documenti che stampano il solo aggregato: il totale va
nel sotto-campo "altri" della famiglia (``iv_cee_hierarchy.residual_bucket``, la stessa che
``residual_finalization`` applicherebbe dopo) - un fallback che etichetta massa davvero letta,
mai un plug. Unica scelta propria, del proprietario (2026-10-19): le immobilizzazioni materiali
senza dettaglio vanno in impianti e macchinari (``sp03b``) e non in altri beni. L'utente affina
in Rettifiche.

Ogni totale stampato deve essere uguale alla somma delle voci lette sotto di lui; una riga con un
importo che non si sa collocare, o un totale che non torna, rifiuta il documento (``rifiuto``
nomina quale): nessun importo corretto, nessun tappo.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Optional

import fitz

_TOL = Decimal("0.05")
_MAX_PAGINE = 3
_MIN_VOCI = 12

_IMPORTO = re.compile(r"^\(?-?\d{1,3}(?:\.\d{3})*,\d{2}\)?-?$")
_CODICE_CONTO = re.compile(r"^\d{5,}$")
_VOCE_APPIATTITA = re.compile(r"^(?:[a-e]\)|[a-d]\.(?:[ivx]+|\d{1,2}(?:-bis)?)\))")

# materiali: impianti e macchinari (scelta del proprietario); le altre famiglie usano il secchio
# "altri" della convenzione di sempre (residual_bucket con dettaglio a zero)
_MATERIALI_DEFAULT = "sp03b"

# (regex sull'etichetta normalizzata, aggregato breve della voce)
_SPA = (
    (r"^b\) immobilizzazioni immateriali$", "sp02"),
    (r"^b\) immobilizzazioni materiali$", "sp03"),
    (r"^b\) immobilizzazioni finanziarie$", "sp04"),
    (r"^c\.i\) rimanenze$", "sp05"),
    (r"^c\.ii\) crediti$", "sp06"),
    (r"^c\.iii\) attivita finanziarie.*$", "sp08"),
    (r"^c\.iv\) disponibilita liquide$", "sp09"),
    (r"^d\) ratei e risconti$", "sp10"),
)
_SPP = (
    (r"^a\) patrimonio netto$", "sp12"),
    (r"^b\) fondi per rischi e oneri$", "sp14"),
    (r"^c\) trattamento di fine rapporto.*$", "sp15"),
    (r"^d\) debiti entro.*$", "sp16"),
    (r"^d\) debiti oltre.*$", "sp17"),
    (r"^e\) ratei e risconti$", "sp18"),
)


def _norm(testo: str) -> str:
    t = unicodedata.normalize("NFKD", testo).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def _valore(token: str) -> Decimal:
    neg = token.startswith("(") or token.startswith("-") or token.endswith("-")
    v = Decimal(token.strip("()-").replace(".", "").replace(",", "."))
    return -v if neg else v


def _righe(doc: fitz.Document) -> Optional[list[tuple[str, str, Decimal]]]:
    """(sezione, etichetta normalizzata, importo) di ogni riga con un importo; None se una riga
    porta piu' di un importo (piu' colonne: non e' questo prospetto)."""
    out: list[tuple[str, str, Decimal]] = []
    sezione = None
    for pagina in doc:
        per_y: dict[int, list] = {}
        for w in pagina.get_text("words"):
            per_y.setdefault(round((w[1] + w[3]) / 2 / 3), []).append(w)
        for y in sorted(per_y):
            parole = sorted(per_y[y], key=lambda w: w[0])
            testo = " ".join(w[4] for w in parole)
            n = _norm(testo)
            importi = [w for w in parole if _IMPORTO.match(w[4])]
            if not importi:
                if n.startswith("stato patrimoniale") and "attivo" in n:
                    sezione = "SPA"
                elif n.startswith("stato patrimoniale") and "passivo" in n:
                    sezione = "SPP"
                elif n.startswith("conto economico"):
                    sezione = "CE"
                continue
            if len(importi) > 1:
                return None
            etichetta = _norm(" ".join(w[4] for w in parole if w is not importi[0]))
            if sezione is None or not etichetta or etichetta in ("voce", "2025 (eur)"):
                continue
            out.append((sezione, etichetta, _valore(importi[0][4])))
    return out


def riconosci(file_path: str) -> bool:
    """True se il PDF e' un prospetto sintetico a voci appiattite e una colonna. Solo testo
    nativo; un errore di lettura e' «non lo so»: False."""
    try:
        with fitz.open(file_path) as doc:
            if len(doc) > _MAX_PAGINE:
                return False
            righe = _righe(doc)
    except Exception:
        return False
    if not righe:
        return False
    sezioni = {s for s, _, _ in righe}
    etichette = [e for _, e, _ in righe]
    if sezioni != {"SPA", "SPP", "CE"}:
        return False
    if any(_CODICE_CONTO.match(e.split()[0]) for e in etichette if e):
        return False
    if "totale attivo" not in etichette or "totale passivo" not in etichette:
        return False
    return sum(1 for e in etichette if _VOCE_APPIATTITA.match(e)) >= _MIN_VOCI


def _secchio(aggregato_breve: str) -> Optional[str]:
    """Il sotto-campo che riceve il totale di una voce senza dettaglio, in codice breve."""
    from importers.import_snello.percorsi import NOMI
    from importers.iv_cee_hierarchy import aggregates_with_details, residual_bucket

    if aggregato_breve == "sp03":
        return _MATERIALI_DEFAULT
    pieno = NOMI.get(aggregato_breve)
    if pieno is None or pieno not in aggregates_with_details():
        return None
    return residual_bucket(pieno, Decimal(0)).split("_")[0]


def _rifiuto(controllo: str, **dettagli) -> dict:
    return {"rifiuto": {"controllo": controllo, **dettagli}}


def estrai(file_path: str) -> Optional[dict]:
    """None se il documento non e' di questa famiglia. Altrimenti ``{"bs", "ce", "stampati",
    "approssimazioni"}`` (codici brevi, importi ``Decimal``) o ``{"rifiuto": ...}``."""
    if not riconosci(file_path):
        return None
    from importers.import_snello.percorsi import NOMI, campo_da_percorso, famiglia
    from importers.schema_etichette_parser import _VALORE_PRODUZIONE

    with fitz.open(file_path) as doc:
        righe = _righe(doc)

    bs: dict[str, Decimal] = {}
    ce: dict[str, Decimal] = {}
    approssimazioni: list[dict] = []
    totali: dict[str, Decimal] = {}
    stampa_ce: dict[str, Decimal] = {}
    voci_ce: dict[str, list[Decimal]] = {"A": [], "B": [], "C": []}
    utile = None
    pn = None

    def metti(aggregato: str, valore: Decimal, voce: str) -> None:
        bucket = _secchio(aggregato)
        bs[aggregato] = bs.get(aggregato, Decimal(0)) + valore
        if bucket:
            bs[bucket] = bs.get(bucket, Decimal(0)) + valore
            approssimazioni.append({"voce": voce, "campo": bucket, "importo": str(valore)})

    for sezione, e, v in righe:
        if sezione in ("SPA", "SPP"):
            tabella = _SPA if sezione == "SPA" else _SPP
            trovata = next((agg for rx, agg in tabella if re.match(rx, e)), None)
            if trovata == "sp12":
                pn = v
                continue
            if trovata:
                metti(trovata, v, e)
                continue
            if sezione == "SPA":
                chiavi = {"totale b) immobilizzazioni": "B", "totale c) attivo circolante": "C",
                          "totale attivo": "tot"}
            else:
                chiavi = {"totale d) debiti": "D", "totale passivo": "tot"}
            if e in chiavi:
                totali[f"{sezione}.{chiavi[e]}"] = v
                continue
            return _rifiuto("riga_non_riconosciuta", didascalia=e, sezione=sezione)
        # conto economico
        m = re.match(r"^totale ([abc])\) ", e)
        if m:
            stampa_ce[m.group(1).upper()] = v
            continue
        if re.match(r"^differenza a ?- ?b$", e):
            stampa_ce["A-B"] = v
            continue
        if re.match(r"^risultato prima delle imposte$", e):
            stampa_ce["ANTE"] = v
            continue
        if re.match(r"^(utile|perdita)\b", e):
            utile = -v if e.startswith("perdita") and v > 0 else v
            continue
        m = re.match(r"^([a-d])\.(\d{1,2})(-bis)?\)", e)
        if m:
            lettera, num, bis = m.group(1).upper(), m.group(2), m.group(3) or ""
            if lettera == "A":
                campo = _VALORE_PRODUZIONE.get(num)
            else:
                campo = campo_da_percorso(f"CE.{lettera}.{num}{bis}")
            if campo is None or campo not in NOMI:
                return _rifiuto("riga_non_riconosciuta", didascalia=e, sezione="CE")
            if lettera in voci_ce:
                voci_ce[lettera].append(v)
            ce[campo] = ce.get(campo, Decimal(0)) + (v if famiglia(campo) == "ric" else -v)
            continue
        if re.match(r"^20\)", e):
            ce["ce20"] = -v
            continue
        return _rifiuto("riga_non_riconosciuta", didascalia=e, sezione="CE")

    # --- ogni totale stampato e' la somma delle voci lette sotto di lui ---------------------------
    def somma(*campi: str) -> Decimal:
        return sum((bs.get(c, Decimal(0)) for c in campi), Decimal(0))

    controlli = [
        ("SPA.B", somma("sp02", "sp03", "sp04")),
        ("SPA.C", somma("sp05", "sp06", "sp08", "sp09")),
        ("SPA.tot", somma("sp02", "sp03", "sp04", "sp05", "sp06", "sp08", "sp09", "sp10")),
        ("SPP.D", somma("sp16", "sp17")),
    ]
    for chiave, nostro in controlli:
        if chiave in totali and abs(totali[chiave] - nostro) > _TOL:
            return _rifiuto("totale_non_torna", totale=chiave, stampato=str(totali[chiave]), letto=str(nostro))
    for lettera in ("A", "B", "C"):
        if lettera in stampa_ce and abs(stampa_ce[lettera] - sum(voci_ce[lettera], Decimal(0))) > _TOL:
            return _rifiuto("totale_non_torna", totale=f"CE.{lettera}", stampato=str(stampa_ce[lettera]),
                            letto=str(sum(voci_ce[lettera], Decimal(0))))
    if {"A", "B"} <= stampa_ce.keys() and "A-B" in stampa_ce \
            and abs(stampa_ce["A-B"] - (stampa_ce["A"] + stampa_ce["B"])) > _TOL:
        return _rifiuto("totale_non_torna", totale="CE.A-B", stampato=str(stampa_ce["A-B"]))
    if utile is None or pn is None:
        return _rifiuto("manca_il_risultato" if utile is None else "manca_il_patrimonio_netto")
    passivo = pn + somma("sp14", "sp15", "sp16", "sp17", "sp18")
    if "SPP.tot" in totali and abs(totali["SPP.tot"] - passivo) > _TOL:
        return _rifiuto("totale_non_torna", totale="SPP.tot", stampato=str(totali["SPP.tot"]), letto=str(passivo))

    # --- il patrimonio netto: risultato dell'esercizio a sp13, il resto in altre riserve -------------
    bs["sp13"] = utile
    resto = pn - utile
    bs["sp12"] = resto
    bs["sp12e"] = resto
    approssimazioni.append({"voce": "a) patrimonio netto (al netto del risultato)", "campo": "sp12e",
                            "importo": str(resto)})

    stampati = {k: v for k, v in (("totale_attivo", totali.get("SPA.tot")),
                                  ("totale_passivo", totali.get("SPP.tot"))) if v is not None}
    return {"bs": bs, "ce": ce, "stampati": stampati, "approssimazioni": approssimazioni}
