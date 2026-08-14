"""Test dell'estrattore di simboli mossi (scripts/riallinea.py).

Spec: docs/superpowers/specs/2026-08-14-agente-riallineamento-design.md §1 fase A
Run:  python3 -m pytest tests/test_riallinea.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.riallinea import Simbolo, simboli_da_diff  # noqa: E402


def _nomi(simboli, stato=None):
    return sorted(s.nome for s in simboli if stato is None or s.stato == stato)


def test_riconosce_una_funzione_aggiunta():
    diff = (
        "diff --git a/importers/foo.py b/importers/foo.py\n"
        "--- a/importers/foo.py\n"
        "+++ b/importers/foo.py\n"
        "@@ -0,0 +1 @@\n"
        "+def calcola_totale(bs):\n"
    )
    out = simboli_da_diff(diff)
    assert _nomi(out, "aggiunto") == ["calcola_totale"]
    assert out[0].genere == "funzione"
    assert out[0].file == "importers/foo.py"


def test_riconosce_una_funzione_rimossa():
    diff = (
        "diff --git a/importers/foo.py b/importers/foo.py\n"
        "--- a/importers/foo.py\n"
        "+++ b/importers/foo.py\n"
        "@@ -1 +0,0 @@\n"
        "-def vecchio_nome(bs):\n"
    )
    assert _nomi(simboli_da_diff(diff), "rimosso") == ["vecchio_nome"]


def test_un_rename_appare_come_rimosso_piu_aggiunto():
    # Lo script NON riconosce i rename: e' lo skill, con `git log -M`, a capire se
    # una coppia rimosso/aggiunto e' un rename o due cose diverse.
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n"
        "-def vecchio(x):\n"
        "+def nuovo(x):\n"
    )
    out = simboli_da_diff(diff)
    assert _nomi(out, "rimosso") == ["vecchio"]
    assert _nomi(out, "aggiunto") == ["nuovo"]


def test_riconosce_classi_costanti_e_colonne():
    diff = (
        "diff --git a/database/models.py b/database/models.py\n"
        "--- a/database/models.py\n+++ b/database/models.py\n@@ -0,0 +4 @@\n"
        "+class ForecastYear(Base):\n"
        "+    MAX_RIGHE = 20\n"
        "+    rettifiche_log = Column(JSON, nullable=True)\n"
        "+    _privata = 1\n"
    )
    out = simboli_da_diff(diff)
    per_genere = {s.nome: s.genere for s in out}
    assert per_genere["ForecastYear"] == "classe"
    assert per_genere["MAX_RIGHE"] == "costante"
    assert per_genere["rettifiche_log"] == "colonna"
    # una minuscola non-Column non e' una costante: sarebbe rumore
    assert "_privata" not in per_genere


def test_riconosce_il_typescript():
    diff = (
        "diff --git a/frontend/lib/api.ts b/frontend/lib/api.ts\n"
        "--- a/frontend/lib/api.ts\n+++ b/frontend/lib/api.ts\n@@ -0,0 +2 @@\n"
        "+export const patchCeOverrides = async (id: number) => {\n"
        "+export function labelOf(code: string) {\n"
    )
    assert _nomi(simboli_da_diff(diff), "aggiunto") == ["labelOf", "patchCeOverrides"]


def test_ignora_i_file_non_di_codice():
    diff = (
        "diff --git a/CLAUDE.md b/CLAUDE.md\n--- a/CLAUDE.md\n+++ b/CLAUDE.md\n@@ -0,0 +1 @@\n"
        "+def questa_e_prosa(x):\n"
    )
    assert simboli_da_diff(diff) == []


def test_non_duplica_lo_stesso_simbolo():
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -0,0 +2 @@\n"
        "+def stessa(x):\n"
        "+def stessa(y):\n"
    )
    assert len(simboli_da_diff(diff)) == 1
