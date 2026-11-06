"""La tavola unica del lettore: percorso di legge -> campo -> macro-voce -> dettaglio KPI -> secchio «altri».

Non copia tabelle: delega a `percorsi` (percorso -> campo, nomi delle colonne) e a `iv_cee_hierarchy`
(gruppi di dettaglio, secchi residui). Qui stanno solo i confini che il lettore decide: quali macro-voci
sono ammesse da un lato e quali dettagli hanno un KPI sopra (decisione del proprietario, 2026-11-06).

Il conflitto A.3/A.4 segue le colonne del DB come `percorsi`: `ce03` = A.3 lavori in corso su ordinazione,
`ce03a` = A.4 incrementi per lavori interni (`database/models.py`). `iv_cee_tree.json` resta com'e' (Fase 4).
"""
from __future__ import annotations

from decimal import Decimal

from importers import iv_cee_hierarchy as _h
from importers.import_snello import percorsi
from importers.residual_finalization import CE_BUCKETS

MACRO_ATTIVO: tuple[str, ...] = tuple(f"sp{n:02d}" for n in range(1, 11))
MACRO_PASSIVO: tuple[str, ...] = tuple(f"sp{n:02d}" for n in range(11, 19))

# Ricavi come `percorsi.RICAVI`, ridotti alle macro-voci (ce17a e' dettaglio di ce17).
MACRO_RICAVI: tuple[str, ...] = ("ce01", "ce02", "ce03", "ce03a", "ce04", "ce13", "ce14", "ce16", "ce18")
# `ce17` (rettifiche di attivita' finanziarie) puo' essere costo o ricavo: sta in entrambi i versi.
MACRO_COSTI: tuple[str, ...] = ("ce05", "ce06", "ce07", "ce08", "ce09", "ce10", "ce11", "ce11b", "ce12",
                                "ce15", "ce17", "ce19", "ce20")

# Profondita' decisa dal proprietario: macro-voci + questi dettagli, il resto va nel secchio «altri».
DETTAGLI_KPI: dict[str, tuple[str, ...]] = {
    "sp06": ("sp06a",),
    "sp16": ("sp16a", "sp16b", "sp16c", "sp16d"),
    "sp17": ("sp17a", "sp17b", "sp17c"),
    "ce08": ("ce08a", "ce08b", "ce08c", "ce08d"),
    "ce09": ("ce09a", "ce09b"),
}


def nome_pieno(codice: str) -> str:
    """«sp06a» -> «sp06a_crediti_clienti_breve» (dalle colonne dell'ORM)."""
    return percorsi.NOMI[codice]


def _corto(nome: str) -> str:
    return nome.split("_")[0]


def _macro_dei_dettagli() -> dict[str, str]:
    out: dict[str, str] = {}
    for agg in ("sp01", "sp02", "sp03", "sp04", "sp05", "sp06", "sp07", "sp12", "sp14", "sp16", "sp17",
                "ce08", "ce09"):
        for d in _h.detail_fields(nome_pieno(agg)):
            out[_corto(d)] = agg
    out.update({"ce17a": "ce17", "ce17b": "ce17"})   # D) rettifiche: dettaglio di ce17 (iv_cee_hierarchy)
    return out


_MACRO_DI = _macro_dei_dettagli()

ETICHETTE_MACRO: dict[str, str] = {
    m: percorsi.NOMI[m].split("_", 1)[1].replace("_", " ")
    for m in MACRO_ATTIVO + MACRO_PASSIVO + MACRO_COSTI + MACRO_RICAVI
}


def campo_da_percorso_legale(percorso: str) -> str | None:
    return percorsi.campo_da_percorso(percorso)


def macro_di(campo: str) -> str:
    return _MACRO_DI.get(campo, campo)


def altri_di(macro: str) -> str:
    """Secchio «altri» di una macro-voce; la macro stessa se non ha dettagli.

    SP: `iv_cee_hierarchy.residual_bucket` (con dettaglio gia' letto, mai il ripiego «tutto clienti»);
    CE: `residual_finalization.CE_BUCKETS` (ammortamenti sui materiali, mai su `ce09c`).
    """
    pieno = nome_pieno(macro)
    if pieno in CE_BUCKETS:
        return _corto(CE_BUCKETS[pieno])
    if _h.detail_fields(pieno):
        return _corto(_h.residual_bucket(pieno, Decimal(1)))
    return macro


def macro_ammesse(lato: str, sezione: str, verso: str | None) -> tuple[str, ...]:
    """Macro-voci su cui puo' cadere una foglia. SP: L/U attivo, R passivo. CE: per verso (None = tutte)."""
    if sezione == "SP":
        if lato in ("L", "U"):
            return MACRO_ATTIVO
        if lato == "R":
            return MACRO_PASSIVO
        raise ValueError(f"lato sconosciuto: {lato!r}")
    if sezione == "CE":
        if verso == "costo":
            return MACRO_COSTI
        if verso == "ricavo":
            return MACRO_RICAVI
        if verso is None:
            return MACRO_RICAVI + tuple(m for m in MACRO_COSTI if m not in MACRO_RICAVI)
        raise ValueError(f"verso sconosciuto: {verso!r}")
    raise ValueError(f"sezione sconosciuta: {sezione!r}")
