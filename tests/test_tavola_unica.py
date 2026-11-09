"""Una funzione sola percorso di legge -> campo (`tavola.campo_di_legge`), concorde con l'albero di legge.

`data/iv_cee_tree.json` ha percorsi scritti a modo suo (`PA.I`, `5bis`, `IMP`) e campi di livello legale, piu' grossi
di quelli dei lettori (`sp06_crediti_breve` dove i lettori scendono a `sp06a`): si confronta la macro-voce.
Mai alias nell'albero (raddoppierebbe gli importi delle route A/B): al piu' si corregge un campo di destinazione.
"""
import inspect
import json
import re

import pytest

from importers import iv_cee_hierarchy as h
from importers.import_snello import percorsi
from importers.lettore import tavola

_ALBERO = json.load(open(h._TREE_PATH, encoding="utf-8"))

# Nodi dell'albero che non sono un percorso di legge del lettore, con il perche' (non sono discordanze di campo):
_NON_PERCORSI = {
    # «entro»/«oltre» sono la scadenza, che per i lettori e' un suffisso .E/.O e non una voce
    "SPA.C.II.entro", "SPA.C.II.oltre", "SPP.D.entro", "SPP.D.oltre",
    # numerazione di prima del 2016 (E.20 proventi, E.21 oneri straordinari): oggi 20 sono le imposte
    "CE.E.20", "CE.E.21",
    # D) e' l'aggregato delle rettifiche: i lettori scendono alle voci 18 e 19 (ce17a/ce17b), che sommano in ce17
    "CE.D",
}


def _corto(campo: str) -> str:
    return campo.split("_")[0]


def _percorso_del_nodo(sezione: str, nodo: dict) -> str:
    p = re.sub(r"(?<=\d)(bis|ter|quater)$", r"-\1", nodo["path"])
    if sezione == "income_statement":
        return "CE.20" if p == "IMP" else f"CE.{p}"
    if nodo["side"] == "attivo":
        return f"SPA.{p}"
    return f"SPP.{p[1:]}"        # «PA.I» -> «SPP.A.I»


def _nodi_di_legge():
    for sezione in ("balance_sheet", "income_statement"):
        for n in _ALBERO[sezione]:
            if n.get("is_legal_leaf") and n.get("db_field"):
                yield _percorso_del_nodo(sezione, n), n


def test_albero_e_percorsi_concordano():
    discordanze = []
    for p, n in _nodi_di_legge():
        if p in _NON_PERCORSI:
            continue
        campo = tavola.campo_di_legge(p)
        voluto = _corto(n["db_field"])
        if campo is None or tavola.macro_di(campo) != tavola.macro_di(voluto):
            discordanze.append((p, n["db_field"], campo))
    assert not discordanze, discordanze


def test_lavori_in_corso_e_lavori_interni_seguono_le_colonne_del_db():
    """ce03 = A.3 variazioni dei lavori in corso su ordinazione, ce03a = A.4 incrementi per lavori interni."""
    assert tavola.campo_di_legge("CE.A.3") == "ce03"
    assert tavola.campo_di_legge("CE.A.4") == "ce03a"
    campo_albero = {p: n["db_field"] for p, n in _nodi_di_legge()}["CE.A.4"]
    assert campo_albero.startswith("ce03a_")


@pytest.mark.parametrize("percorso", ["SPA.C.II.1.E", "SPP.D.4.O", "CE.B.9.a", "CE.A.4", "CE.20", "SPP.A.IX", "X", ""])
def test_percorsi_campo_da_percorso_e_la_stessa_funzione(percorso):
    assert percorsi.campo_da_percorso(percorso) == tavola.campo_di_legge(percorso)


def test_la_tavola_e_una_sola():
    """Il corpo della traduzione sta in `tavola`; `percorsi` e i chiamanti la richiamano, non ne hanno una copia."""
    assert "_PN" not in inspect.getsource(percorsi) and "_DEB" not in inspect.getsource(percorsi)
    for modulo in ("importers.import_snello.conti", "importers.schema_etichette_parser"):
        sorgente = inspect.getsource(__import__(modulo, fromlist=["x"]))
        assert "campo_di_legge" in sorgente and "campo_da_percorso" not in sorgente, modulo
