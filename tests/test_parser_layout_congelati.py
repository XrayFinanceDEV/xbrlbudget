"""I parser di layout di route C sono congelati (dal 2026-11).

Criterio meccanico: e' un «parser di layout» ogni funzione di LIVELLO MODULO di
`importers/situazione_contabile_parser.py` o di un modulo del pacchetto `importers/situazione_contabile/`
(dove il codice sta dal 2026-11-24; la facciata lo ri-esporta), senza underscore iniziale, il cui nome comincia
per `parse_` o `extract_` e che restituisce un'estrazione completa (voci o bilancio) da un
formato di gestionale: `parse_entries*`, `parse_bilancio_verifica_segno`,
`extract_contrapposte_best_effort`. Sono ESCLUSI: il dispatcher
`extract_situazione_contabile` (sceglie il parser, non ne e' uno), i predicati `is_*`/`looks_*`,
gli aiutanti `_*` (`_c8_*`, `_be_*`, `_hier_*`, `_entries_da_righe_verifica`), `build_iv_cee`
e `reconstruct_contrapposte_rows` (ricostruiscono righe, non un'estrazione).
"""
import ast
import os

from importers import situazione_contabile_parser as scp

DISPATCHER = {"extract_situazione_contabile"}


def _sorgenti():
    pacchetto = os.path.join(os.path.dirname(scp.__file__), "situazione_contabile")
    return [scp.__file__] + sorted(
        os.path.join(pacchetto, f) for f in os.listdir(pacchetto) if f.endswith(".py"))


def _parser_di_layout_nel_modulo():
    trovati = set()
    for sorgente in _sorgenti():
        with open(sorgente, encoding="utf-8") as f:
            albero = ast.parse(f.read())
        trovati |= {
            n.name
            for n in albero.body
            if isinstance(n, ast.FunctionDef)
            and not n.name.startswith("_")
            and n.name.startswith(("parse_", "extract_"))
            and n.name not in DISPATCHER
        }
    return trovati


def test_nessun_parser_di_layout_nuovo():
    trovati = _parser_di_layout_nel_modulo()
    congelati = set(scp.PARSER_DI_LAYOUT)
    nuovi = sorted(trovati - congelati)
    assert not nuovi, (
        f"Parser di layout nuovo in situazione_contabile_parser.py o nel pacchetto situazione_contabile: {nuovi}. "
        "I parser per singolo gestionale sono congelati dal 2026-11 (solo correzioni di errori): "
        "un layout nuovo va nel percorso generico, in importers/lettore. "
        "Vedi CLAUDE.md, «Invarianti e trappole > Estrazione e classificazione»."
    )
    assert not (congelati - trovati), (
        f"PARSER_DI_LAYOUT cita funzioni che non esistono piu': {sorted(congelati - trovati)}"
    )


def test_i_parser_congelati_sono_dodici_e_chiamabili():
    assert len(scp.PARSER_DI_LAYOUT) == len(set(scp.PARSER_DI_LAYOUT)) == 12
    for nome in scp.PARSER_DI_LAYOUT:
        assert callable(getattr(scp, nome))
