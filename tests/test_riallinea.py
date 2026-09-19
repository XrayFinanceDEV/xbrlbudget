"""Test dell'estrattore di simboli mossi (scripts/riallinea.py).

Spec: docs/superpowers/specs/2026-08-14-agente-riallineamento-design.md §1 fase A
Run:  python3 -m pytest tests/test_riallinea.py -v
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.riallinea import (  # noqa: E402
    ESTENSIONI_CODICE,
    Citazione,
    Simbolo,
    SOGLIA_GENERICO,
    _pathspec,
    carica_stato,
    documenti_che_nominano,
    RADICI_DOC,
    riduci_generici,
    salva_stato,
    simboli_da_diff,
    LIMITE_CORPO_COMMIT,
    TRONCATO,
    commit_da_log,
    commits_nell_intervallo,
    documenti_che_nominano_file,
    simboli_non_documentati,
)


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


def test_le_istruzioni_agli_agenti_sono_corpus():
    # Un'istruzione a un agente e' il posto PIU' costoso dove una regola puo'
    # essere sbagliata: non la legge una persona che dubita, la ESEGUE. Sul giro
    # 2026-09-19 la regola dell'aliquota rovesciata viveva proprio in
    # `.claude/agents/collaudatore.md`, e nessun giro l'aveva mai vista perche'
    # RADICI_DOC si fermava a `docs/` + `CLAUDE.md`: un limite di corpus, non
    # una mancata verifica.
    assert ".claude/agents" in RADICI_DOC
    assert ".claude/skills" in RADICI_DOC


def test_una_regola_sotto_claude_agents_viene_raccolta_dalle_radici_veri(tmp_path, monkeypatch):
    # Non basta che la radice sia nell'elenco: `.claude` inizia con un punto,
    # e una scansione che saltasse le directory nascoste farebbe sparire IL SOLO
    # file che contiene una regola sbagliata, senza alcun errore.
    _scrivi(tmp_path, "docs/vivo.md", "Il netting usa `net_contra_accounts`.\n")
    _scrivi(tmp_path, "CLAUDE.md", "Also mentions `net_contra_accounts`.\n")
    _scrivi(tmp_path, ".claude/agents/collaudatore.md", "Il motore usa `net_contra_accounts`.\n")
    monkeypatch.chdir(tmp_path)
    sim = [Simbolo("net_contra_accounts", "funzione", "calculations/x.py", "aggiunto")]
    trovati = {Path(c.file).as_posix() for c in documenti_che_nominano(sim, RADICI_DOC)}
    assert ".claude/agents/collaudatore.md" in trovati
    assert {"docs/vivo.md", "CLAUDE.md"} <= trovati


# --- riduci_generici -------------------------------------------------------
# Misurato sul repo vero: nove nomi generici plausibili producono 1147 citazioni
# in un colpo solo. Un simbolo comune fra i ~40 di un diff reale seppellirebbe
# le segnalazioni vere, quindi va SEPARATO (mai troncato in silenzio): esce da
# `citazioni` ed entra in `generici` col proprio conteggio e i primi file.

def test_riduci_generici_lascia_stare_i_simboli_sotto_soglia():
    citazioni = [Citazione("foo_bar", "docs/a.md", i, "x") for i in range(SOGLIA_GENERICO - 1)]
    ridotte, generici = riduci_generici(citazioni)
    assert ridotte == citazioni
    assert generici == []


def test_riduci_generici_sposta_i_simboli_alla_soglia_o_sopra():
    citazioni = [Citazione("resolve", f"docs/doc{i}.md", 1, "x") for i in range(SOGLIA_GENERICO)]
    ridotte, generici = riduci_generici(citazioni)
    assert ridotte == []
    assert len(generici) == 1
    assert generici[0]["nome"] == "resolve"
    assert generici[0]["citazioni"] == SOGLIA_GENERICO
    assert generici[0]["file"] == [f"docs/doc{i}.md" for i in range(5)]


def test_riduci_generici_non_tocca_i_simboli_rari_nello_stesso_elenco():
    comuni = [Citazione("resolve", f"docs/doc{i}.md", 1, "x") for i in range(SOGLIA_GENERICO)]
    raro = Citazione("net_contra_accounts", "docs/a.md", 3, "y")
    ridotte, generici = riduci_generici(comuni + [raro])
    assert ridotte == [raro]
    assert [g["nome"] for g in generici] == ["resolve"]


def test_riduci_generici_su_elenco_vuoto():
    assert riduci_generici([]) == ([], [])


# --- carica_stato / salva_stato ---------------------------------------------

def test_stato_assente_da_un_dizionario_vuoto(tmp_path):
    assert carica_stato(str(tmp_path / "STATO.json")) == {}


def test_salva_e_rilegge_lo_stato(tmp_path):
    p = str(tmp_path / "STATO.json")
    salva_stato(p, sha="abc1234", modo="diff", data="2026-08-21")
    letto = carica_stato(p)
    assert letto["ultimo_sha"] == "abc1234"
    assert letto["modo"] == "diff"
    assert letto["ultimo_completo"] is None


def test_lo_sweep_completo_aggiorna_ultimo_completo_e_lo_sha(tmp_path):
    # Uno sweep ha appena verificato tutto: il punto di ripartenza e' lo stesso del
    # modo diff, e in piu' resta traccia di QUANDO si e' fatto l'ultimo integrale.
    p = str(tmp_path / "STATO.json")
    salva_stato(p, sha="abc1234", modo="diff", data="2026-08-21")
    salva_stato(p, sha="def5678", modo="completo", data="2026-08-28")
    letto = carica_stato(p)
    assert letto["ultimo_sha"] == "def5678"
    assert letto["ultimo_completo"] == "2026-08-28"


def test_il_pathspec_copre_tutte_le_estensioni_di_codice():
    # Uno sweep completo non deve chiedere a git i PDF tracciati in docs/examples/:
    # li decodificherebbe per niente, ed e' cosi' che --completo andava in crash.
    spec = _pathspec()
    assert {s.lstrip("*") for s in spec} == set(ESTENSIONI_CODICE)
    assert all(s.startswith("*") for s in spec)


def test_un_diff_successivo_non_cancella_ultimo_completo(tmp_path):
    p = str(tmp_path / "STATO.json")
    salva_stato(p, sha="def5678", modo="completo", data="2026-08-28")
    salva_stato(p, sha="aaa1111", modo="diff", data="2026-09-04")
    letto = carica_stato(p)
    assert letto["ultimo_completo"] == "2026-08-28"
    assert letto["ultimo_sha"] == "aaa1111"


# --- --registra (CLI) -------------------------------------------------------
# `main()` non chiamava mai `salva_stato`: 27 test coprivano una funzione che la CLI
# non raggiungeva, e STATO.json era stato scritto a mano. Questo e' l'unico percorso
# di esecuzione che scrive davvero lo stato: lo skill lo chiama DOPO aver verificato,
# mai in fase di raccolta.

_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "scripts", "riallinea.py")


def _registra(stato_path, *extra_args):
    return subprocess.run(
        [sys.executable, _SCRIPT, "--registra", *extra_args, "--stato", str(stato_path)],
        capture_output=True, text=True,
    )


def test_registra_scrive_davvero_lo_stato(tmp_path):
    stato_path = tmp_path / "STATO.json"
    r = _registra(stato_path, "abc1234", "--modo", "diff", "--data", "2026-08-21")
    assert r.returncode == 0, r.stderr
    letto = json.loads(stato_path.read_text(encoding="utf-8"))
    assert letto["ultimo_sha"] == "abc1234"
    assert letto["modo"] == "diff"
    assert letto["data"] == "2026-08-21"
    assert "ripresa_l3" not in letto


def test_registra_con_ripresa_l3_sopravvive_a_una_registrazione_successiva(tmp_path):
    stato_path = tmp_path / "STATO.json"
    r1 = _registra(stato_path, "def5678", "--modo", "completo", "--data", "2026-08-28",
                    "--ripresa-l3", "docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md")
    assert r1.returncode == 0, r1.stderr
    letto = json.loads(stato_path.read_text(encoding="utf-8"))
    assert letto["ultimo_completo"] == "2026-08-28"
    assert letto["ripresa_l3"] == "docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md"

    # una registrazione successiva SENZA --ripresa-l3 non la cancella
    r2 = _registra(stato_path, "aaa1111", "--modo", "diff", "--data", "2026-09-04")
    assert r2.returncode == 0, r2.stderr
    letto = json.loads(stato_path.read_text(encoding="utf-8"))
    assert letto["ultimo_sha"] == "aaa1111"
    assert letto["ripresa_l3"] == "docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md"


# --- commit dell'intervallo: la spina dorsale del giro ---------------------
# Misurato sul giro 2026-09-18 (`1f09819..b9ca1a6`): delle 14 frasi false
# corrette a mano, UNA sola era raggiungibile dalle citazioni per simbolo
# (`_tax_components` in M2-02E). Le altre 13 non nominavano alcun simbolo
# mosso: sono prosa che descrive una REGOLA. L'unico artefatto del repo che
# parla la stessa lingua della prosa e' il messaggio di commit, quindi la
# raccolta lo porta a galla invece di lasciarlo alla buona volonta' di chi
# legge.

def _log_finto(*record):
    """Il formato che `commits_nell_intervallo` chiede a git, costruito a mano."""
    fuori = ""
    for sha, data, soggetto, corpo, file in record:
        fuori += (
            "\x1eCOMMIT\x1f" + sha + "\x1f" + data + "\x1f" + soggetto + "\x1f" + corpo + "\x1e"
            + "\n" + "".join(f + "\n" for f in file)
        )
    return fuori


def test_commit_da_log_legge_sha_data_soggetto_corpo_e_file():
    testo = _log_finto(
        ("abc1234", "2026-09-18", "feat(imposte): il calcolo secondo il commercialista",
         "L'aliquota scritta e' quella che gira.\n", ["calculations/forecast_engine.py"]),
    )
    out = commit_da_log(testo)
    assert len(out) == 1
    c = out[0]
    assert c.sha == "abc1234"
    assert c.data == "2026-09-18"
    assert c.soggetto == "feat(imposte): il calcolo secondo il commercialista"
    assert "quella che gira" in c.corpo
    assert c.file == ["calculations/forecast_engine.py"]


def test_commit_da_log_tiene_i_commit_separati():
    testo = _log_finto(
        ("aaa", "2026-09-17", "primo", "", ["a.py"]),
        ("bbb", "2026-09-18", "secondo", "corpo\n", ["b.py", "c.ts"]),
    )
    out = commit_da_log(testo)
    assert [c.sha for c in out] == ["aaa", "bbb"]
    assert out[1].file == ["b.py", "c.ts"]


def test_commit_da_log_su_log_vuoto():
    assert commit_da_log("") == []


def test_commit_da_log_tronca_un_corpo_lunghissimo():
    # Il corpo serve a capire SE il commit cambia una regola, non a rileggerlo
    # tutto: 126 commit con i corpi interi farebbero un JSON illeggibile.
    lungo = "x" * (LIMITE_CORPO_COMMIT + 500)
    out = commit_da_log(_log_finto(("aaa", "2026-09-18", "s", lungo, ["a.py"])))
    assert len(out[0].corpo) <= LIMITE_CORPO_COMMIT + len(TRONCATO)
    assert out[0].corpo.endswith(TRONCATO)


def test_commits_nell_intervallo_su_un_repo_vero(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "T")
    (tmp_path / "a.py").write_text("def uno():\n    pass\n", encoding="utf-8")
    (tmp_path / "nota.md").write_text("niente codice\n", encoding="utf-8")
    git("add", "a.py", "nota.md")
    git("commit", "-q", "-m", "primo")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                          capture_output=True, text=True).stdout.strip()
    (tmp_path / "a.py").write_text("def uno():\n    return 1\n", encoding="utf-8")
    (tmp_path / "nota.md").write_text("cambiata\n", encoding="utf-8")
    git("add", "a.py", "nota.md")
    git("commit", "-q", "-m", "secondo: cambia una regola")
    out = commits_nell_intervallo(f"{base}..HEAD", cwd=str(tmp_path))
    assert [c.soggetto for c in out] == ["secondo: cambia una regola"]
    # Solo file di codice: un commit di sola documentazione non serve a nulla qui.
    assert out[0].file == ["a.py"]


# --- simboli mossi che nessun documento nomina -----------------------------
# `working_capital_mode` (Column), `MODI_CIRCOLANTE` (costante esportata) e le
# loro diagnostiche sono entrati nel giro 2026-09-18 con ZERO citazioni: il
# simbolo veniva raccolto, il join non produceva niente, e il niente veniva
# buttato. Una manopola pubblica che nessun documento nomina e' il rilievo piu'
# economico che questa raccolta possa produrre, e prima non lo produceva.

def test_manopola_nuova_senza_citazioni_e_un_rilievo():
    sim = [Simbolo("working_capital_mode", "colonna", "database/models.py", "aggiunto")]
    out = simboli_non_documentati(sim, [])
    assert [s["nome"] for s in out] == ["working_capital_mode"]
    assert out[0]["genere"] == "colonna"
    assert out[0]["file"] == "database/models.py"


def test_una_manopola_citata_non_e_un_rilievo():
    sim = [Simbolo("working_capital_mode", "colonna", "database/models.py", "aggiunto")]
    cit = [Citazione("working_capital_mode", "CLAUDE.md", 1, "...")]
    assert simboli_non_documentati(sim, cit) == []


def test_un_simbolo_rimosso_non_e_una_manopola_da_documentare():
    # Un simbolo cancellato che nessuno nominava e' pulizia riuscita, non un buco.
    sim = [Simbolo("vecchia_colonna", "colonna", "database/models.py", "rimosso")]
    assert simboli_non_documentati(sim, []) == []


def test_una_funzione_interna_nuova_non_e_una_manopola():
    # Altrimenti ogni helper privato di ogni commit diventerebbe un rilievo.
    sim = [
        Simbolo("_cerca_equilibrio", "funzione", "calculations/intra_year_engine.py", "aggiunto"),
        Simbolo("helper", "funzione", "x.py", "aggiunto"),
    ]
    assert simboli_non_documentati(sim, []) == []


def test_una_rotta_nuova_senza_citazioni_e_un_rilievo():
    sim = [Simbolo("/companies/{id}/aliquota-proposta", "rotta",
                   "backend/app/api/v1/financial_years.py", "aggiunto")]
    assert [s["nome"] for s in simboli_non_documentati(sim, [])] == [
        "/companies/{id}/aliquota-proposta"]


# --- la seconda chiave di join: il PERCORSO del file ----------------------
# Misurato sullo stesso giro: la chiave "nome di simbolo" non tocca
# REGOLE-IMPORT-05 (la pagina che descriveva la regola vecchia), mentre la
# chiave "percorso del file toccato" la prende con 4 righe. Non le sostituisce:
# `FORECASTING_GUIDE.md` non nomina alcun file di codice e resta invisibile a
# entrambe — per quella serve il messaggio di commit.

def test_trova_chi_nomina_un_file_toccato(tmp_path):
    _scrivi(tmp_path, "docs/a.md", "Il motore sta in `calculations/intra_year_engine.py`.\n")
    _scrivi(tmp_path, "docs/b.md", "Niente.\n")
    cit = documenti_che_nominano_file(["calculations/intra_year_engine.py"], [str(tmp_path)])
    assert [c.file for c in cit] == [str(tmp_path / "docs/a.md")]
    assert cit[0].simbolo == "intra_year_engine.py"


def test_il_join_sul_percorso_basta_il_nome_del_file(tmp_path):
    _scrivi(tmp_path, "docs/a.md", "vedi `intra_year_engine.py` al blocco CASH PLUG\n")
    cit = documenti_che_nominano_file(["calculations/intra_year_engine.py"], [str(tmp_path)])
    assert len(cit) == 1


def test_il_join_sul_percorso_ignora_i_file_non_di_codice(tmp_path):
    _scrivi(tmp_path, "docs/a.md", "vedi `README.md` e `dati.csv`\n")
    assert documenti_che_nominano_file(["README.md", "dati.csv"], [str(tmp_path)]) == []


# --- il corpus non si auto-inquina ----------------------------------------
# Il rapporto di un giro finisce in docs/, quindi al giro successivo le sue
# citazioni rientrano nel conteggio: misurato, 49 citazioni fantasma e un
# simbolo spinto sopra SOGLIA_GENERICO solo per questo.

def test_i_rapporti_di_allineamento_non_entrano_nel_corpus(tmp_path):
    _scrivi(tmp_path, "docs/superpowers/allineamento/2026-09-18.md", "`foo_bar` citato qui\n")
    _scrivi(tmp_path, "docs/vivo.md", "`foo_bar` citato qui\n")
    sim = [Simbolo("foo_bar", "funzione", "x.py", "aggiunto")]
    cit = documenti_che_nominano(sim, [str(tmp_path)])
    assert [c.file for c in cit] == [str(tmp_path / "docs/vivo.md")]


def test_l_esclusione_vale_anche_per_il_join_sul_percorso(tmp_path):
    _scrivi(tmp_path, "docs/superpowers/allineamento/2026-09-18.md", "`x.py` citato\n")
    assert documenti_che_nominano_file(["x.py"], [str(tmp_path)]) == []


def test_una_costante_interna_non_e_una_manopola():
    # Misurato sul giro 2026-09-18: allargare a `costante` e `tipo` porta la
    # lista da 1 riga a 110, quasi tutte costanti di layout e tipi interni
    # (`CHART_HEIGHT_COMPACT_MM`, `DownloadGuardState`). Una lista di 110 righe
    # non e' un rilievo: e' il rumore che seppellisce quello vero.
    sim = [
        Simbolo("CHART_HEIGHT_COMPACT_MM", "costante", "backend/app/renderers/x.py", "aggiunto"),
        Simbolo("DownloadGuardState", "tipo", "frontend/lib/final-report-download.ts", "aggiunto"),
    ]
    assert simboli_non_documentati(sim, []) == []


def test_una_manopola_dentro_i_test_non_conta(tmp_path):
    # Una colonna dichiarata in una fixture di test non e' una manopola
    # dell'applicazione: nessuno deve documentarla.
    sim = [
        Simbolo("colonna_finta", "colonna", "tests/test_qualcosa.py", "aggiunto"),
        Simbolo("altra", "colonna", "frontend/lib/x.test.ts", "aggiunto"),
    ]
    assert simboli_non_documentati(sim, []) == []


def test_una_rotta_documentata_con_altri_segnaposto_e_documentata(tmp_path):
    # Il codice scrive `{company_id}`, `CLAUDE.md` scrive `{id}`: e' la stessa
    # rotta, e confrontarla alla lettera la fa risultare non documentata.
    # Misurato: era 1 dei 2 rilievi del giro 2026-09-18, ed era un falso.
    _scrivi(tmp_path, "docs/a.md",
            "La proposta sta su `GET /companies/{id}/years/{year}/aliquota-proposta`.\n")
    sim = [Simbolo("/companies/{company_id}/years/{year}/aliquota-proposta", "rotta",
                   "backend/app/api/v1/financial_years.py", "aggiunto")]
    cit = documenti_che_nominano(sim, [str(tmp_path)])
    assert len(cit) == 1
    assert simboli_non_documentati(sim, cit) == []


def test_due_rotte_diverse_non_si_confondono(tmp_path):
    _scrivi(tmp_path, "docs/a.md", "`GET /companies/{id}/years/{year}/altra-cosa`\n")
    sim = [Simbolo("/companies/{company_id}/years/{year}/aliquota-proposta", "rotta",
                   "x.py", "aggiunto")]
    assert documenti_che_nominano(sim, [str(tmp_path)]) == []
