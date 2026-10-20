"""Il dettaglio di un aggregato che il codice ha letto ma non sa ripartire: Qwen nomina la
voce di legge dei conti sotto, il codice decide.

Il lettore delle contrapposte legge gli importi e la gerarchia dei conti al centesimo, ma
ripartisce un mastro sulle sotto-voci di legge solo con parole chiave. Unicarton 31/08/2026:
"67 COSTI PERSONALE DIPENDENTE" 238.731,12 con Retribuzioni lorde, Contributi INPS e costi
diversi, nessuna parola che l'elenco conosca, tutto in ``ce08d``. Inseguire le parole file
per file e' la strada che il proprietario ha scartato (2026-10-20): la classificazione la fa
il modello, sulle sole descrizioni.

Il parser dichiara in ``_ce_da_dettagliare`` ogni mastro che non sa ripartire, con le sue
foglie (``albero``): si scende nei conti solo dove i figli sommano al padre al centesimo, la
stessa regola di sempre ("la profondita' propone, il totale decide"). Qui le foglie vanno a
Qwen con il prompt dei conti del percorso snello (``lettura.percorsi_dei_conti``) e il
percorso si traduce con ``percorsi.campo_da_percorso``. Una foglia si accetta solo se la voce
e' una sotto-voce dello STESSO aggregato: il modello non porta massa fuori dal personale, non
inventa importi e non tocca l'aggregato. Cio' che non spiega resta a
``residual_finalization``, che lo mette nel secchio di ripiego dichiarandolo, come prima.
"""
from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
CENTESIMO = Decimal("0.01")

# Aggregato -> (chiave piena dell'aggregato, {sotto-voce breve di campo_da_percorso: chiave piena}).
SOTTOVOCI = {
    "ce08": ("ce08_costi_personale", {
        "ce08a": "ce08a_tfr_accrual", "ce08b": "ce08b_salari_stipendi",
        "ce08c": "ce08c_oneri_sociali", "ce08d": "ce08d_altri_costi_personale"}),
    "ce09": ("ce09_ammortamenti", {
        "ce09a": "ce09a_ammort_immateriali", "ce09b": "ce09b_ammort_materiali",
        "ce09c": "ce09c_svalutazioni", "ce09d": "ce09d_svalutazione_crediti"}),
}


def foglie(codice: str, descrizione: str, importo: Decimal, figli) -> list[tuple]:
    """I conti foglia sotto un mastro: si scende in un conto solo quando i suoi figli
    sommano al suo importo al centesimo, altrimenti il conto resta foglia intera.
    ``figli(codice)`` -> [(codice, descrizione, importo)]."""
    sotto = figli(codice)
    if sotto and abs(sum((x[2] for x in sotto), ZERO) - importo) <= CENTESIMO:
        out = []
        for c, d, a in sotto:
            out.extend(foglie(c, d, a, figli))
        return out
    return [(codice, descrizione, importo)]


def albero(aggregato: str, codice: str, descrizione: str, importo: Decimal, figli) -> dict:
    """La dichiarazione di un mastro da ripartire, come la scrive il parser."""
    return {"aggregato": aggregato, "codice": codice, "descrizione": descrizione,
            "importo": importo, "foglie": foglie(codice, descrizione, importo, figli)}


def _q(v: Decimal) -> str:
    return str(v.quantize(CENTESIMO))


def dettaglia(ce: dict, *, chiama=None) -> tuple[dict, dict]:
    """Ripartisce sulle sotto-voci i mastri dichiarati in ``_ce_da_dettagliare``.

    Restituisce una copia del CE (senza la chiave diagnostica) e un report JSON-safe.
    L'aggregato non cambia mai; un errore del modello lascia il CE com'era."""
    ce = dict(ce)
    alberi = ce.pop("_ce_da_dettagliare", None) or []
    alberi = [a for a in alberi if a.get("aggregato") in SOTTOVOCI and a.get("foglie")]
    if not alberi:
        return ce, {"status": "niente_da_dettagliare"}

    from importers.import_snello.righe import Riga
    from importers.import_snello.lettura import _testo, percorsi_dei_conti
    if chiama is None:
        from importers import llm_provider
        if not llm_provider.gx10_disponibile():
            return ce, {"status": "modello_non_disponibile"}
        chiama = _testo

    righe, per_albero = [], []
    for n, a in enumerate(alberi):
        # una riga senza importo davanti alle foglie: il contesto del mastro (# ...)
        righe.append(Riga(id=f"m{n}", pagina=0, lato="L", sezione="CE", valore=None,
                          testo=f"CONTO ECONOMICO, COSTI - {a['codice']} {a['descrizione']}"))
        mie = []
        for c, d, v in a["foglie"]:
            r = Riga(id=f"m{n}:{c}", pagina=0, lato="L", sezione="CE", valore=v,
                     testo=d, mastro=a["descrizione"])
            righe.append(r)
            mie.append((c, d, v, r))
        per_albero.append(mie)
    da_classificare = [r for mie in per_albero for *_x, r in mie]
    try:
        esito_chiamate = percorsi_dei_conti(righe, da_classificare, chiama=chiama)
    except Exception as exc:  # noqa: BLE001 - un guasto del modello non blocca l'import
        logger.warning("dettaglio dal modello non disponibile: %s", exc)
        return ce, {"status": "errore", "errore": str(exc)[:200]}

    from importers.import_snello.percorsi import campo_da_percorso
    report = {"status": "applicato", "chiamate": esito_chiamate.get("chiamate"), "alberi": []}
    spiegato_tot = non_spiegato_tot = ZERO
    for a, mie in zip(alberi, per_albero):
        chiave_aggr, sotto = SOTTOVOCI[a["aggregato"]]
        assegnate: dict[str, Decimal] = {}
        respinte = []
        for c, d, v, r in mie:
            campo = sotto.get(campo_da_percorso(r.percorso) or "")
            if campo is None:
                respinte.append([c, d, _q(v), r.percorso])
                continue
            assegnate[campo] = assegnate.get(campo, ZERO) + v
        for campo, v in assegnate.items():
            ce[campo] = Decimal(str(ce.get(campo) or 0)) + v
        spiegato = sum(assegnate.values(), ZERO)
        non_spiegato = a["importo"] - spiegato
        spiegato_tot += spiegato
        non_spiegato_tot += non_spiegato
        report["alberi"].append({
            "aggregato": chiave_aggr, "mastro": f"{a['codice']} {a['descrizione']}",
            "importo": _q(a["importo"]), "assegnate": {k: _q(v) for k, v in assegnate.items()},
            "respinte": respinte})
    report["spiegato"], report["non_spiegato"] = _q(spiegato_tot), _q(non_spiegato_tot)
    return ce, report
