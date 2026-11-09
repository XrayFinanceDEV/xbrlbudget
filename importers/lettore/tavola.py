"""La tavola unica del lettore: percorso di legge -> campo -> macro-voce -> dettaglio -> secchio «altri».

Qui sta l'unica traduzione percorso di legge -> campo (`campo_di_legge`: lettore, conti, schema_etichette_parser, e
`percorsi.campo_da_percorso` che la richiama). Per il resto delega a `percorsi` (nomi delle colonne) e a `iv_cee_hierarchy`
(gruppi di dettaglio, secchi residui). Qui stanno solo i confini che il lettore decide: quali macro-voci
sono ammesse da un lato, quali rettifiche possono attraversarlo e fin dove si scende nei dettagli (decisioni del
proprietario, 2026-11-06 e 2026-11-09).

Il conflitto A.3/A.4 segue le colonne del DB come `percorsi`: `ce03` = A.3 lavori in corso su ordinazione,
`ce03a` = A.4 incrementi per lavori interni (`database/models.py`), e cosi' l'albero `iv_cee_tree.json`.
"""
from __future__ import annotations

from decimal import Decimal

from importers import iv_cee_hierarchy as _h
from importers.import_snello import percorsi
from importers.residual_finalization import CE_BUCKETS

MACRO_ATTIVO: tuple[str, ...] = tuple(f"sp{n:02d}" for n in range(1, 11))
MACRO_PASSIVO: tuple[str, ...] = tuple(f"sp{n:02d}" for n in range(11, 19))



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

# Profondita' decisa dal proprietario (2026-11-09, sostituisce «macro + KPI»): prima la macro-voce, poi il dettaglio
# piu' fine possibile, «altri» solo quando il dettaglio non si sa. Ogni macro con dettagli, tranne ce17: la
# rettifica di valore la decide il verso (rivalutazione o svalutazione), non il modello.
DETTAGLI: dict[str, tuple[str, ...]] = {}
for _d, _m in _MACRO_DI.items():
    if _m != "ce17":
        DETTAGLI.setdefault(_m, ())
        DETTAGLI[_m] += (_d,)

# Macro-voci di CE dalle colonne dell'ORM (senza i dettagli di ce08/ce09/ce17); ricavi = `percorsi.RICAVI`
# portati alla macro (ce17a -> ce17). `ce17` (rettifiche, segno ambiguo) sta in entrambi i versi.
_MACRO_CE = tuple(k for k in percorsi.NOMI if k.startswith("ce") and _MACRO_DI.get(k, k) == k)
MACRO_RICAVI: tuple[str, ...] = tuple(k for k in _MACRO_CE if k in {_MACRO_DI.get(r, r) for r in percorsi.RICAVI})
MACRO_COSTI: tuple[str, ...] = tuple(k for k in _MACRO_CE if k not in MACRO_RICAVI or k == "ce17")
MACRO_RICAVI = tuple(k for k in _MACRO_CE if k in MACRO_RICAVI)

# Le rettifiche stampate nella colonna opposta (decisione del proprietario, 2026-11-09: «riusare il sistema del
# vecchio importatore»): i soli conti che possono attraversare il lato, nominati col percorso di legge del percorso
# snello. Un fondo e' il percorso del bene + «.F» (`percorsi.e_fondo`, la legenda), un conto del netto in diminuzione
# e' un percorso SPP.A (`percorsi.e_netto`). Il campo viene da `percorsi.campo_da_percorso`, come per `conti.py`.
RETTIFICHE: dict[str, str] = {
    "sp02.F": "SPA.B.I.F", "sp03.F": "SPA.B.II.F", "sp04.F": "SPA.B.III.F", "sp06.F": "SPA.C.II.1.F",
    "sp12g.N": "SPP.A.VIII", "sp12h.N": "SPP.A.X",
}
_ETICHETTE_RETTIFICHE = {
    "sp02.F": "fondo ammortamento delle immobilizzazioni immateriali (rettifica dell'attivo)",
    "sp03.F": "fondo ammortamento o svalutazione delle immobilizzazioni materiali (rettifica dell'attivo)",
    "sp04.F": "fondo svalutazione delle immobilizzazioni finanziarie (rettifica dell'attivo)",
    "sp06.F": "fondo svalutazione crediti verso clienti (rettifica dell'attivo)",
    "sp12g.N": "perdite portate a nuovo (in diminuzione del patrimonio netto)",
    "sp12h.N": "azioni proprie, riserva negativa (in diminuzione del patrimonio netto)",
}

ETICHETTE_MACRO: dict[str, str] = {
    **{m: percorsi.NOMI[m].split("_", 1)[1].replace("_", " ")
       for m in MACRO_ATTIVO + MACRO_PASSIVO + MACRO_COSTI + MACRO_RICAVI},
    **_ETICHETTE_RETTIFICHE,
}


def rettifiche_ammesse(lato: str) -> tuple[str, ...]:
    """Le rettifiche che una foglia SP della colonna `lato` puo' essere: dal passivo (R) i fondi dei beni
    dell'attivo, dall'attivo (L) i conti del netto in diminuzione; sulla colonna unica senza lato nessuna."""
    voluto = {"R": "att", "L": "pas"}.get(lato)
    return tuple(c for c, p in RETTIFICHE.items() if voluto and percorsi.lato_di(p) == voluto)


# C.II.5 (verso imprese sottoposte al controllo delle controllanti, dal 2016) non ha un campo
# proprio: va negli altri crediti come i debiti D.11-bis, mai perso in un KeyError.
_CR = {"1": "a", "2": "b", "3": "c", "4": "d", "5": "g", "5-bis": "e", "5-ter": "f", "5-quater": "g"}
_DEB = {"1": "c", "2": "c", "3": "b", "4": "a", "5": "b", "6": "g", "7": "d", "8": "g", "9": "g",
        "10": "g", "11": "g", "11-bis": "g", "12": "e", "13": "f", "14": "g"}
_PN = {"I": "sp11", "II": "sp12a", "III": "sp12b", "IV": "sp12c", "V": "sp12d", "VI": "sp12e",
       "VII": "sp12f", "VIII": "sp12g", "IX": "sp13", "X": "sp12h"}
_CE = {"1": "ce01", "2": "ce02", "3": "ce03", "4": "ce03a", "5": "ce04", "6": "ce05", "7": "ce06",
       "8": "ce07", "11": "ce10", "12": "ce11", "13": "ce11b", "14": "ce12", "15": "ce13", "16": "ce14",
       "17": "ce15", "17-bis": "ce16", "18": "ce17a", "19": "ce17b", "20": "ce20"}


def campo_di_legge(p: str) -> str | None:
    """Percorso di legge («SPA.C.II.1.E», «CE.A.3») -> campo breve del DB, o None. La sola tavola del progetto."""
    if not p or p in ("X", "R") or percorsi.e_risultato(p):
        return None
    t = [x for x in p.split(".") if x != "F"]
    scad = t[-1] if len(t) > 2 and t[-1] in ("E", "O") else None
    if scad:
        t = t[:-1]
    try:
        if t[0] == "SPA" and len(t) >= 2:
            if t[1] == "A":
                return "sp01"
            if t[1] == "B":
                if len(t) == 2:
                    return None
                if len(t) == 3:
                    return {"I": "sp02", "II": "sp03", "III": "sp04"}.get(t[2])
                n = int(t[3])
                if t[2] == "I" and 1 <= n <= 7:
                    return "sp02" + "abcdefg"[n - 1]
                if t[2] == "II" and 1 <= n <= 5:
                    return "sp03" + "abcde"[n - 1]
                if t[2] == "III":
                    return {1: "sp04a", 2: "sp04c" if scad == "O" else "sp04b", 3: "sp04d", 4: "sp04e"}.get(n)
            if t[1] == "C" and len(t) >= 3:
                if t[2] == "I":
                    return "sp05" + "abcde"[int(t[3]) - 1] if len(t) > 3 else "sp05"
                if t[2] == "II":
                    base = "sp07" if scad == "O" else "sp06"
                    return base + _CR[t[3]] if len(t) > 3 else base
                if t[2] == "III":
                    return "sp08"
                if t[2] == "IV":
                    return "sp09"
            if t[1] == "D":
                return "sp10"
        if t[0] == "SPP" and len(t) >= 2:
            if t[1] == "A" and len(t) >= 3:
                return _PN.get(t[2])
            if t[1] == "B":
                # fondi per rischi e oneri: un fondo unico indistinto (nessun sotto-indice
                # arabo) va sull'aggregato, non perso in non_mappati.
                return "sp14" + "abcd"[int(t[2]) - 1] if len(t) >= 3 else "sp14"
            if t[1] == "C":
                return "sp15"
            if t[1] == "D":
                base = "sp17" if scad == "O" else "sp16"
                # debito senza scadenza dichiarata, nemmeno a livello di lettera (scad=None e
                # nessun sotto-indice arabo): a breve per prudenza, come SPP.D.E - mai perso in
                # non_mappati.
                return base + _DEB[t[2]] if len(t) > 2 else base
            if t[1] == "E":
                return "sp18"
        if t[0] == "CE":
            n = [x for x in t[1:] if x not in ("A", "B", "C", "D", "E")]
            if not n:
                return None
            voce, sub = n[0], (n[1] if len(n) > 1 else None)
            if voce == "9":
                return {"a": "ce08b", "b": "ce08c", "c": "ce08a", "d": "ce08d", "e": "ce08d"}.get(sub, "ce08") if sub else "ce08"
            if voce == "10":
                return {"a": "ce09a", "b": "ce09b", "c": "ce09c", "d": "ce09d"}.get(sub) if sub else "ce09"
            return _CE.get(voce)
    except (ValueError, KeyError, IndexError):
        return None
    return None


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
        # Decimal(1): dettaglio gia' presente, cosi' mai il ripiego «tutto clienti/materie» di somma zero
        return _corto(_h.residual_bucket(pieno, Decimal(1)))
    return macro


def macro_ammesse(lato: str, sezione: str, verso: str | None) -> tuple[str, ...]:
    """Macro-voci su cui puo' cadere una foglia. SP: L attivo, R passivo, U (colonna unica) entrambi. CE: per verso (None = tutte)."""
    if sezione == "SP":
        if lato == "U":      # F3-7: colonna unica, attivo e passivo in sequenza
            return MACRO_ATTIVO + MACRO_PASSIVO
        if lato == "L":
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
            return _MACRO_CE
        raise ValueError(f"verso sconosciuto: {verso!r}")
    raise ValueError(f"sezione sconosciuta: {sezione!r}")
