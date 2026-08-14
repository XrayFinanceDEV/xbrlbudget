"""Test dell'estrattore di simboli mossi (scripts/riallinea.py).

Spec: docs/superpowers/specs/2026-08-14-agente-riallineamento-design.md §1 fase A
Run:  python3 -m pytest tests/test_riallinea.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.riallinea import Citazione, Simbolo, documenti_che_nominano, simboli_da_diff  # noqa: E402


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


def test_un_file_cancellato_non_perde_i_suoi_simboli():
    # Un modulo cancellato e' il segnale piu' forte che la documentazione nomini
    # qualcosa che non esiste piu': e' il caso che va preso per primo.
    diff = (
        "diff --git a/importers/vecchio.py b/importers/vecchio.py\n"
        "deleted file mode 100644\n"
        "--- a/importers/vecchio.py\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-def funzione_sparita(x):\n"
        "-class ClasseSparita:\n"
    )
    out = simboli_da_diff(diff)
    assert _nomi(out, "rimosso") == ["ClasseSparita", "funzione_sparita"]
    assert {s.file for s in out} == {"importers/vecchio.py"}


def test_una_cancellazione_dopo_un_altro_file_non_contamina_il_precedente():
    # Il bug misurato: file_corrente restava agganciato al file precedente e i
    # simboli del file cancellato venivano attribuiti a quello sbagliato.
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -0,0 +1 @@\n"
        "+def resta_qui(x):\n"
        "diff --git a/b.py b/b.py\ndeleted file mode 100644\n--- a/b.py\n+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-def sparita(x):\n"
    )
    per_nome = {s.nome: s.file for s in simboli_da_diff(diff)}
    assert per_nome["resta_qui"] == "a.py"
    assert per_nome["sparita"] == "b.py"


def test_riconosce_le_costanti_esportate_in_maiuscolo():
    # Sono proprio i nomi che CLAUDE.md cita per nome (DETAIL_PARENTS,
    # ATTIVO_CODES, PROPOSAL_RULES...): perderli svuota lo strumento.
    diff = (
        "diff --git a/frontend/lib/x.ts b/frontend/lib/x.ts\n"
        "--- a/frontend/lib/x.ts\n+++ b/frontend/lib/x.ts\n@@ -0,0 +2 @@\n"
        "+export const DETAIL_PARENTS = {\n"
        "+export const labelOf = (c: string) => {\n"
    )
    out = simboli_da_diff(diff)
    assert _nomi(out, "aggiunto") == ["DETAIL_PARENTS", "labelOf"]
    per_genere = {s.nome: s.genere for s in out}
    assert per_genere["DETAIL_PARENTS"] == "costante"
    assert per_genere["labelOf"] == "funzione"


def test_riconosce_tipi_e_default_export():
    diff = (
        "diff --git a/frontend/types/api.ts b/frontend/types/api.ts\n"
        "--- a/frontend/types/api.ts\n+++ b/frontend/types/api.ts\n@@ -0,0 +3 @@\n"
        "+export interface AnalysisResponse {\n"
        "+export type PraticaStep = {\n"
        "+export default function Pagina() {\n"
    )
    out = simboli_da_diff(diff)
    assert _nomi(out, "aggiunto") == ["AnalysisResponse", "Pagina", "PraticaStep"]
    assert {s.genere for s in out if s.nome != "Pagina"} == {"tipo"}


def test_riconosce_una_rotta_fastapi():
    # Il genere "rotta" e' dichiarato nel vocabolario di Simbolo ma prima di questo
    # fix non veniva mai prodotto, mentre CLAUDE.md cita gli endpoint per percorso
    # in decine di punti (es. "PATCH /scenarios/{id}/ce-override").
    diff = (
        "diff --git a/backend/app/api/v1/budget_scenarios.py "
        "b/backend/app/api/v1/budget_scenarios.py\n"
        "--- a/backend/app/api/v1/budget_scenarios.py\n"
        "+++ b/backend/app/api/v1/budget_scenarios.py\n"
        "@@ -0,0 +2 @@\n"
        '+    @router.patch("/scenarios/{scenario_id}/ce-override")\n'
        "+    async def patch_ce_override(scenario_id: int):\n"
    )
    out = simboli_da_diff(diff)
    per_genere = {s.nome: s.genere for s in out}
    # la rotta e la funzione decorata sotto sono due simboli distinti: vanno entrambi
    assert per_genere["/scenarios/{scenario_id}/ce-override"] == "rotta"
    assert per_genere["patch_ce_override"] == "funzione"


def _scrivi(tmp_path, nome, testo):
    p = tmp_path / nome
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(testo, encoding="utf-8")
    return p


def test_trova_chi_nomina_un_simbolo(tmp_path):
    _scrivi(tmp_path, "docs/a.md", "Il netting usa `net_contra_accounts` due volte.\n")
    _scrivi(tmp_path, "docs/b.md", "Niente di rilevante qui.\n")
    sim = [Simbolo("net_contra_accounts", "funzione", "x.py", "rimosso")]
    cit = documenti_che_nominano(sim, [str(tmp_path)])
    assert [c.file for c in cit] == [str(tmp_path / "docs/a.md")]
    assert cit[0].riga == 1
    assert cit[0].simbolo == "net_contra_accounts"


def test_ignora_una_sottostringa_dentro_un_nome_piu_lungo(tmp_path):
    # `resolve` non deve pescare `_resolve_ce_field`: sarebbe rumore su ogni giro.
    _scrivi(tmp_path, "docs/a.md", "Usa `_resolve_ce_field` e non altro.\n")
    sim = [Simbolo("resolve", "funzione", "x.py", "rimosso")]
    assert documenti_che_nominano(sim, [str(tmp_path)]) == []


def test_legge_solo_i_markdown(tmp_path):
    _scrivi(tmp_path, "docs/a.py", "net_contra_accounts\n")
    sim = [Simbolo("net_contra_accounts", "funzione", "x.py", "rimosso")]
    assert documenti_che_nominano(sim, [str(tmp_path)]) == []


def test_piu_citazioni_dello_stesso_simbolo(tmp_path):
    _scrivi(tmp_path, "docs/a.md", "`foo_bar` qui\ne ancora `foo_bar` qui\n")
    sim = [Simbolo("foo_bar", "funzione", "x.py", "rimosso")]
    cit = documenti_che_nominano(sim, [str(tmp_path)])
    assert [c.riga for c in cit] == [1, 2]


def test_una_radice_inesistente_non_esplode(tmp_path):
    sim = [Simbolo("foo_bar", "funzione", "x.py", "rimosso")]
    assert documenti_che_nominano(sim, [str(tmp_path / "non-esiste")]) == []


def test_una_radice_che_e_un_singolo_file_viene_letta(tmp_path):
    # RADICI_DOC contiene anche "CLAUDE.md", che e' un FILE, non una cartella:
    # Path("CLAUDE.md").rglob("*.md") non rende nulla, quindi il documento piu'
    # importante di tutti verrebbe saltato in silenzio se radice fosse trattata
    # solo come directory.
    claude_md = _scrivi(tmp_path, "CLAUDE.md", "Nomina `foo_bar` qui.\n")
    sim = [Simbolo("foo_bar", "funzione", "x.py", "rimosso")]
    cit = documenti_che_nominano(sim, [str(claude_md)])
    assert [c.file for c in cit] == [str(claude_md)]
    assert cit[0].riga == 1
