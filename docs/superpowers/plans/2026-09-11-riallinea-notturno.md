# Riallineamento notturno di /riallinea — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ogni notte, senza intervento umano, `/riallinea` gira in modo `diff` sui commit arrivati
su `origin/main` dall'ultimo giro riuscito, usando pi locale su gx10 (WSL); le correzioni
dimostrabili e il rapporto finiscono in una PR verso `main` solo quando superano controlli
automatici severi, e un giro fallito lascia un log completo più un commento su una issue GitHub
dedicata.

**Architecture:** Un runner bash sostituibile (`scripts/riallinea_notte.sh`, versionato nel repo,
installato fuori da esso in `~/riallinea-notte/bin/`) orchestra lock, precondizioni, worktree,
raccolta, invocazione di pi con un prompt versionato (`scripts/riallinea_notte.prompt.md`), i
controlli prima di pubblicare, push/PR, notifica di fallimento e pulizia. Tutta la logica che vale
la pena di testare — calcolo dell'intervallo, i cinque controlli del passo 7, il conteggio del
rapporto e la decisione/il testo del passo 8 — vive in un modulo Python a sola libreria standard,
`scripts/riallinea_notte_logica.py`, invocato dal runner come sottocomandi CLI; il bash resta un
orchestratore sottile che logga ogni passo e non prende decisioni complesse da solo.

**Tech Stack:** bash (runner), Python 3 stdlib (logica + CLI), pytest (test della logica, tramite
il venv del backend), `git`/`gh`/`pi` come comandi esterni invocati dal runner.

**Spec:** `docs/superpowers/specs/2026-09-11-riallinea-notturno-design.md`

**Branch:** `feat/riallinea-notte`, da staccare da `feat/scadenziamento-pregresso` (dove vive già
la spec approvata, commit `6c57857`).

**Esecuzione:** ogni task lo implementa **pi**, un agente coding locale; la revisione resta a
**sonnet** (decisione del proprietario, 2026-09-11 — vedi spec §10). Pi vede solo il testo del
proprio task, non questo file intero: ogni task qui sotto è scritto per essere autosufficiente,
con percorsi assoluti, codice per intero, comandi per esteso, esiti attesi.

**Cartella dei rapporti di questo piano:** `.superpowers/sdd/2026-09-11-riallinea-notturno/` (da
creare al primo task — non esiste ancora).

## Global Constraints

*(Copiate alla lettera dalla spec §5-§10; si applicano implicitamente a ogni task sotto.)*

- **Lock.** `flock -n` sul lock file: un giro già in corso esce con codice 0 e una riga di log —
  non è un fallimento (spec §5.1).
- **Una precondizione mancante è un fallimento** (spec §5.2): `git`/`gh`/`pi` esistenti, `gh auth
  status`, gx10 raggiungibile **senza mandare un prompt**.
- **Mai l'albero principale** (`/home/peter/DEV/budget` o dove lo punta `RIALLINEA_NOTTE_REPO`):
  solo `git fetch` (sola lettura) e `git worktree add/remove`. Mai checkout, stash, reset, commit
  o `--amend` su di esso (spec §4, §5.3-§5.4).
- **Il worktree di un giro precedente fallito si rimuove all'inizio del passo "worktree fresco",
  non prima** — resta sul disco fino ad allora per l'ispezione (spec §5.4, §7).
- **I cinque controlli del passo 7 sono tutti obbligatori; il primo che fallisce ferma il giro**:
  worktree pulito, solo `CLAUDE.md`/`docs/**` toccati, messaggi di commit esattamente
  `docs(allineamento): correzioni dimostrabili` e/o `docs(allineamento): rapporto <data>`, il
  rapporto `docs/superpowers/allineamento/<data>-notte.md` esiste, `STATO.json` non è stato
  toccato (spec §5.7).
- **Zero correzioni e zero voci «Da decidere» ⇒ nessuna PR**: il rapporto resta nel log, lo stato
  avanza comunque (spec §5.8).
- **`--registra` si esegue solo dopo che il passo 8 è riuscito** — mai prima, mai su un fallimento
  (spec §5.9, §7: "Stato: non avanza").
- **Worktree rimosso sempre a fine giro riuscito; branch locale cancellato solo se pubblicato**; i
  log più vecchi di 30 giorni si cancellano (spec §5.10).
- **Su un fallimento: log completo, e un commento sulla issue dedicata, mai le righe del log nel
  commento** — potrebbero contenere testo letto dal repo o dall'ambiente (spec §7).
- **Il sorgente versionato è `scripts/riallinea_notte.sh`**; `~/riallinea-notte/bin/` è
  un'installazione fuori dal repo, non toccata da `uvicorn --reload` o da un cambio di branch
  (spec §4).
- **Nessuna chiave nel runner.** Pi risolve le proprie da `~/.pi/agent/models.json`; un eventuale
  controllo HTTP passa il Bearer da stdin, mai in argv (spec §8, riga «Chiavi»).
- **`schtasks.exe` non si esegue mai automaticamente**: il piano lo stampa soltanto; lo lancia il
  proprietario, o il coordinatore con la sua approvazione esplicita (spec §9).
- **Nessuna modifica a `scripts/riallinea.py` né a `.claude/skills/riallinea/`** (spec §10): se
  servisse, è un rilievo da portare al proprietario, non un'implementazione.
- **Nessuna scrittura in rete in nessun test/verifica di questo piano** (`git fetch`/`gh issue
  list`/`gh auth status`/`pi auth check` sono letture, ammesse; `git push`/`gh pr create`/`gh
  issue create`/`gh issue comment` girano solo nel primo giro reale del Task 5, mai durante lo
  sviluppo o la revisione dei Task 1-4).

## Nota di conformità e deviazioni dichiarate

**Linguaggio dei controlli — non è una deviazione.** La spec nomina il runner e i suoi dieci
passi, non il linguaggio con cui ne è scritta la logica decisionale. Questo piano mette il calcolo
dell'intervallo, i cinque controlli del passo 7 e il conteggio/la decisione del passo 8 in un
modulo Python a sola libreria standard (`scripts/riallinea_notte_logica.py`), testato con pytest;
il runner bash lo invoca come sottocomandi CLI e resta un orchestratore sottile (lock,
precondizioni, git, `pi`, push/PR, notifica, pulizia). È la stessa scelta già fatta per
`scripts/riallinea.py` (collector in Python, decisioni nello skill) applicata al runner.

**Schema JSON del collector, misurato per scrivere questo piano** (non nella spec, necessario per
`conta_citazioni_json`): `python3 scripts/riallinea.py --da <sha> --a <sha>` produce un oggetto con
le chiavi `intervallo` (stringa), `simboli` (lista), `citazioni` (**lista piatta** di
`{simbolo, file, riga, testo}` — non annidata sotto i simboli), `generici` (lista di
`{nome, citazioni: int, file: [...]}`), `radici` (lista), `stato` (dizionario, spesso vuoto). "Zero
citazioni" del passo 5 significa `len(dati["citazioni"]) == 0`.

**Verifica di raggiungibilità di gx10 — solo `pi auth check`.** La spec ammette un fallback a una
`GET` con Bearer da stdin "se `pi auth check` non basta a provare la raggiungibilità". Questo
piano implementa solo `pi auth check --provider gx10 --json --no-refresh`, il metodo che i fatti
misurati indicano come sufficiente; il fallback resta un gap dichiarato, da aggiungere solo se il
Task 5 (primo giro reale) mostra che non basta.

**Test con un "pi" finto.** Nessun task di questo piano invoca il vero `pi`/gx10: il runner accetta
`RIALLINEA_NOTTE_PI_BIN` per sostituire il binario `pi` con uno stub che scrive un rapporto e
committa, così i Task 2-3 restano deterministici e senza rete. Il **primo** giro con `pi` vero è il
Task 5, eseguito dal coordinatore.

---

## Task 1: Logica decisionale (`riallinea_notte_logica.py`) e i suoi test

**Files:**
- Create: `/home/peter/DEV/budget/scripts/riallinea_notte_logica.py`
- Create: `/home/peter/DEV/budget/tests/test_riallinea_notte_logica.py`

**Interfaces:**
- Consumes: `carica_stato(percorso: str) -> dict` e `salva_stato(percorso: str, sha: str, modo:
  str, data: str) -> None` da `scripts/riallinea.py` (import, nessuna modifica a quel file).
- Produces (usati dai Task 2-4 come sottocomandi CLI, mai importati direttamente da bash):
  - `python3 scripts/riallinea_notte_logica.py leggi-ultimo-sha --stato <path>` — stampa lo sha su
    stdout ed esce 0 se presente; esce 1 (nulla su stdout) se assente.
  - `python3 scripts/riallinea_notte_logica.py intervallo-vuoto --repo <path> --da <sha> --a <sha>`
    — esce 0 se l'intervallo è vuoto, 10 se non lo è.
  - `python3 scripts/riallinea_notte_logica.py conta-citazioni --json <path>` — stampa il numero di
    citazioni su stdout, esce 0.
  - `python3 scripts/riallinea_notte_logica.py verifica-pubblicazione --worktree <path> --data
    <AAAA-MM-GG>` — esce 0 se tutti i controlli del passo 7 passano; esce 1 col motivo su stderr al
    primo che fallisce.
  - `python3 scripts/riallinea_notte_logica.py decisione-pr --report <path> --data <AAAA-MM-GG>
    --corpo-out <path>` — scrive il corpo della PR in `--corpo-out`, stampa su stdout quattro righe
    `CORREZIONI=<n>`, `DA_DECIDERE=<n>`, `PUBBLICA=si|no`, `TITOLO=<testo>`; esce sempre 0 (la
    decisione è nell'output, non nel codice di uscita).
  - `python3 scripts/riallinea_notte_logica.py semina-stato --sha <sha> --stato <path> --data
    <AAAA-MM-GG>` — scrive/aggiorna `<path>` con `carica_stato`/`salva_stato` di `riallinea.py`
    (`modo="diff"`); esce 0.
- Produces (funzioni Python, per i test e per riuso interno): `intervallo_vuoto`,
  `conta_citazioni_json`, `leggi_ultimo_sha`, `file_consentiti`, `messaggi_commit_validi`,
  `stato_json_non_toccato`, `report_atteso`, `EsitoControllo` (NamedTuple `ok: bool, motivo:
  Optional[str]`), `verifica_pubblicazione`, `ConteggiReport` (NamedTuple `correzioni: int,
  da_decidere: int`), `estrai_sezione`, `conta_report`, `decidi_pubblicazione`, `titolo_pr`,
  `corpo_pr`.

- [ ] **Step 1: Scrivi il file dei test (fallirà: l'implementazione non esiste ancora)**

Crea `/home/peter/DEV/budget/tests/test_riallinea_notte_logica.py`:

```python
"""Test della logica decisionale del giro notturno (scripts/riallinea_notte_logica.py).

Esegui con:
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
      tests/test_riallinea_notte_logica.py -q -p no:cacheprovider
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from riallinea_notte_logica import (  # noqa: E402
    ConteggiReport,
    EsitoControllo,
    conta_citazioni_json,
    conta_report,
    corpo_pr,
    decidi_pubblicazione,
    estrai_sezione,
    file_consentiti,
    intervallo_vuoto,
    leggi_ultimo_sha,
    messaggi_commit_validi,
    report_atteso,
    stato_json_non_toccato,
    titolo_pr,
    verifica_pubblicazione,
)

LOGICA = REPO / "scripts" / "riallinea_notte_logica.py"


def _repo_git(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def _commit(path: Path, nome_file: str, contenuto: str, messaggio: str) -> str:
    (path / nome_file).write_text(contenuto, encoding="utf-8")
    subprocess.run(["git", "add", nome_file], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", messaggio], cwd=path, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True
    ).stdout.strip()


# --- intervallo_vuoto: repo git vero in una cartella temporanea ---

def test_intervallo_vuoto_stesso_sha(tmp_path):
    _repo_git(tmp_path)
    sha = _commit(tmp_path, "a.txt", "1", "primo")
    assert intervallo_vuoto(str(tmp_path), sha, sha) is True


def test_intervallo_non_vuoto_con_nuovo_commit(tmp_path):
    _repo_git(tmp_path)
    sha1 = _commit(tmp_path, "a.txt", "1", "primo")
    _commit(tmp_path, "a.txt", "2", "secondo")
    assert intervallo_vuoto(str(tmp_path), sha1, "HEAD") is False


# --- conta_citazioni_json: schema reale del collector (misurato sul repo) ---

def test_conta_citazioni_json(tmp_path):
    percorso = tmp_path / "sample.json"
    percorso.write_text(json.dumps({
        "intervallo": "a..b",
        "simboli": [{"nome": "X", "genere": "funzione", "file": "f.py", "stato": "aggiunto"}],
        "citazioni": [
            {"simbolo": "X", "file": "docs/y.md", "riga": 1, "testo": "cita X"},
            {"simbolo": "X", "file": "docs/z.md", "riga": 2, "testo": "cita X di nuovo"},
        ],
        "generici": [],
        "radici": ["docs", "CLAUDE.md"],
        "stato": {},
    }), encoding="utf-8")
    assert conta_citazioni_json(str(percorso)) == 2


def test_conta_citazioni_json_vuoto(tmp_path):
    percorso = tmp_path / "sample.json"
    percorso.write_text(json.dumps({"citazioni": []}), encoding="utf-8")
    assert conta_citazioni_json(str(percorso)) == 0


# --- leggi_ultimo_sha ---

def test_leggi_ultimo_sha_assente(tmp_path):
    assert leggi_ultimo_sha(str(tmp_path / "nope.json")) is None


def test_leggi_ultimo_sha_presente(tmp_path):
    stato = tmp_path / "STATO.json"
    stato.write_text(json.dumps({"ultimo_sha": "abc123"}), encoding="utf-8")
    assert leggi_ultimo_sha(str(stato)) == "abc123"


# --- file_consentiti ---

@pytest.mark.parametrize("percorsi,atteso", [
    (["CLAUDE.md"], True),
    (["docs/superpowers/allineamento/2026-09-12-notte.md"], True),
    (["CLAUDE.md", "docs/x.md"], True),
    ([], True),
    (["frontend/app/pratica/page.tsx"], False),
    (["docs/x.md", "backend/app/main.py"], False),
])
def test_file_consentiti(percorsi, atteso):
    assert file_consentiti(percorsi) is atteso


# --- messaggi_commit_validi ---

def test_messaggi_commit_validi_vuoto_e_rifiutato():
    assert messaggi_commit_validi([]) is False


def test_messaggi_commit_validi_solo_rapporto():
    assert messaggi_commit_validi(["docs(allineamento): rapporto 2026-09-12"]) is True


def test_messaggi_commit_validi_correzioni_e_rapporto():
    assert messaggi_commit_validi([
        "docs(allineamento): correzioni dimostrabili",
        "docs(allineamento): rapporto 2026-09-12",
    ]) is True


def test_messaggi_commit_validi_messaggio_estraneo_rifiutato():
    assert messaggi_commit_validi([
        "docs(allineamento): correzioni dimostrabili",
        "fix: qualcosa d'altro",
    ]) is False


def test_messaggi_commit_validi_data_malformata_rifiutata():
    assert messaggi_commit_validi(["docs(allineamento): rapporto 12-09-2026"]) is False


# --- stato_json_non_toccato / report_atteso ---

def test_stato_json_non_toccato_vero_se_assente():
    assert stato_json_non_toccato(["CLAUDE.md", "docs/x.md"]) is True


def test_stato_json_non_toccato_falso_se_presente():
    assert stato_json_non_toccato(["docs/superpowers/allineamento/STATO.json"]) is False


def test_report_atteso():
    assert report_atteso("2026-09-12") == "docs/superpowers/allineamento/2026-09-12-notte.md"


# --- verifica_pubblicazione: il primo controllo che fallisce ferma il giro ---

def test_verifica_pubblicazione_worktree_sporco_prima_di_tutto():
    esito = verifica_pubblicazione(
        worktree_pulito=False,
        percorsi_modificati=["frontend/app/x.ts"],
        messaggi_commit=[],
        data="2026-09-12",
        report_esiste_su_disco=False,
    )
    assert esito.ok is False
    assert "worktree" in esito.motivo


def test_verifica_pubblicazione_file_fuori_lista():
    esito = verifica_pubblicazione(
        worktree_pulito=True,
        percorsi_modificati=["CLAUDE.md", "backend/app/main.py"],
        messaggi_commit=["docs(allineamento): rapporto 2026-09-12"],
        data="2026-09-12",
        report_esiste_su_disco=True,
    )
    assert esito.ok is False
    assert "backend/app/main.py" in esito.motivo


def test_verifica_pubblicazione_messaggi_non_validi():
    esito = verifica_pubblicazione(
        worktree_pulito=True,
        percorsi_modificati=["CLAUDE.md"],
        messaggi_commit=["fix: qualcosa"],
        data="2026-09-12",
        report_esiste_su_disco=True,
    )
    assert esito.ok is False
    assert "messaggi" in esito.motivo


def test_verifica_pubblicazione_report_mancante():
    esito = verifica_pubblicazione(
        worktree_pulito=True,
        percorsi_modificati=["CLAUDE.md"],
        messaggi_commit=["docs(allineamento): rapporto 2026-09-12"],
        data="2026-09-12",
        report_esiste_su_disco=False,
    )
    assert esito.ok is False
    assert "2026-09-12-notte.md" in esito.motivo


def test_verifica_pubblicazione_stato_toccato():
    esito = verifica_pubblicazione(
        worktree_pulito=True,
        percorsi_modificati=[
            "docs/superpowers/allineamento/2026-09-12-notte.md",
            "docs/superpowers/allineamento/STATO.json",
        ],
        messaggi_commit=["docs(allineamento): rapporto 2026-09-12"],
        data="2026-09-12",
        report_esiste_su_disco=True,
    )
    assert esito.ok is False
    assert "STATO.json" in esito.motivo


def test_verifica_pubblicazione_tutto_ok():
    esito = verifica_pubblicazione(
        worktree_pulito=True,
        percorsi_modificati=["CLAUDE.md", "docs/superpowers/allineamento/2026-09-12-notte.md"],
        messaggi_commit=["docs(allineamento): rapporto 2026-09-12"],
        data="2026-09-12",
        report_esiste_su_disco=True,
    )
    assert esito == EsitoControllo(True, None)


# --- conta_report / decidi_pubblicazione / titolo_pr / corpo_pr ---

RAPPORTO_ESEMPIO = """# Rapporto di riallineamento 2026-09-12

Modo: diff · Intervallo: abc123..def456

## Corretto automaticamente

- `docs/foo.md`: link corretto (regola 1) da `bar.md` a `baz.md`
- `CLAUDE.md`: percorso corretto (regola 2), `data/rating_tables.json` non esisteva piu' li'

## Da decidere

- `docs/x.md` riga 12 cita `funzione_vecchia`; il codice ora ha `funzione_nuova`
  (rename ambiguo, non applicato)

## Memoria — riferimenti morti

Nessuno.

## Non verificabile

Nessuno.
"""

RAPPORTO_VUOTO = """# Rapporto di riallineamento 2026-09-12

Modo: diff · Intervallo: abc123..def456

## Corretto automaticamente

Nessuna correzione.

## Da decidere

Nessuna voce.

## Memoria — riferimenti morti

Nessuno.

## Non verificabile

Nessuno.
"""


def test_conta_report_con_voci():
    assert conta_report(RAPPORTO_ESEMPIO) == ConteggiReport(correzioni=2, da_decidere=1)


def test_conta_report_vuoto():
    assert conta_report(RAPPORTO_VUOTO) == ConteggiReport(correzioni=0, da_decidere=0)


def test_decidi_pubblicazione():
    assert decidi_pubblicazione(ConteggiReport(2, 1)) is True
    assert decidi_pubblicazione(ConteggiReport(0, 0)) is False
    assert decidi_pubblicazione(ConteggiReport(0, 1)) is True


def test_titolo_pr():
    assert titolo_pr("2026-09-12", ConteggiReport(2, 1)) == (
        "Riallineamento notturno 2026-09-12: 2 correzioni, 1 da decidere"
    )


def test_corpo_pr_contiene_sezione_da_decidere():
    corpo = corpo_pr(RAPPORTO_ESEMPIO, ConteggiReport(2, 1))
    assert "Correzioni: 2" in corpo
    assert "Da decidere: 1" in corpo
    assert "funzione_vecchia" in corpo


def test_estrai_sezione_titolo_assente():
    assert estrai_sezione(RAPPORTO_ESEMPIO, "Sezione Inesistente") == ""


# --- CLI: le sottocomandi invocate da scripts/riallinea_notte.sh ---

def test_cli_leggi_ultimo_sha_exit_1_se_assente(tmp_path):
    esito = subprocess.run([sys.executable, str(LOGICA), "leggi-ultimo-sha",
                             "--stato", str(tmp_path / "nope.json")])
    assert esito.returncode == 1


def test_cli_leggi_ultimo_sha_stampa_sha(tmp_path):
    stato = tmp_path / "STATO.json"
    stato.write_text(json.dumps({"ultimo_sha": "abc123"}), encoding="utf-8")
    esito = subprocess.run([sys.executable, str(LOGICA), "leggi-ultimo-sha",
                             "--stato", str(stato)], capture_output=True, text=True)
    assert esito.returncode == 0
    assert esito.stdout.strip() == "abc123"


def test_cli_intervallo_vuoto_exit_0(tmp_path):
    _repo_git(tmp_path)
    sha = _commit(tmp_path, "a.txt", "1", "primo")
    esito = subprocess.run(
        [sys.executable, str(LOGICA), "intervallo-vuoto", "--repo", str(tmp_path),
         "--da", sha, "--a", sha],
    )
    assert esito.returncode == 0


def test_cli_intervallo_vuoto_exit_10_se_non_vuoto(tmp_path):
    _repo_git(tmp_path)
    sha1 = _commit(tmp_path, "a.txt", "1", "primo")
    _commit(tmp_path, "a.txt", "2", "secondo")
    esito = subprocess.run(
        [sys.executable, str(LOGICA), "intervallo-vuoto", "--repo", str(tmp_path),
         "--da", sha1, "--a", "HEAD"],
    )
    assert esito.returncode == 10


def test_cli_decisione_pr(tmp_path):
    report = tmp_path / "report.md"
    report.write_text(RAPPORTO_ESEMPIO, encoding="utf-8")
    corpo_out = tmp_path / "corpo.txt"
    esito = subprocess.run(
        [sys.executable, str(LOGICA), "decisione-pr", "--report", str(report),
         "--data", "2026-09-12", "--corpo-out", str(corpo_out)],
        capture_output=True, text=True,
    )
    assert esito.returncode == 0
    assert "CORREZIONI=2" in esito.stdout
    assert "DA_DECIDERE=1" in esito.stdout
    assert "PUBBLICA=si" in esito.stdout
    assert "TITOLO=Riallineamento notturno 2026-09-12: 2 correzioni, 1 da decidere" in esito.stdout
    assert "funzione_vecchia" in corpo_out.read_text(encoding="utf-8")


def test_cli_decisione_pr_pubblica_no_se_rapporto_vuoto(tmp_path):
    report = tmp_path / "report.md"
    report.write_text(RAPPORTO_VUOTO, encoding="utf-8")
    corpo_out = tmp_path / "corpo.txt"
    esito = subprocess.run(
        [sys.executable, str(LOGICA), "decisione-pr", "--report", str(report),
         "--data", "2026-09-12", "--corpo-out", str(corpo_out)],
        capture_output=True, text=True,
    )
    assert "PUBBLICA=no" in esito.stdout


def test_cli_semina_stato(tmp_path):
    stato = tmp_path / "STATO.json"
    esito = subprocess.run(
        [sys.executable, str(LOGICA), "semina-stato", "--sha", "abc123",
         "--stato", str(stato), "--data", "2026-09-12"],
    )
    assert esito.returncode == 0
    dati = json.loads(stato.read_text(encoding="utf-8"))
    assert dati["ultimo_sha"] == "abc123"
    assert dati["modo"] == "diff"
```

- [ ] **Step 2: Esegui i test, verifica che falliscano per import mancante**

Comando:
```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
    /home/peter/DEV/budget/tests/test_riallinea_notte_logica.py -q -p no:cacheprovider
```
Atteso: `ModuleNotFoundError: No module named 'riallinea_notte_logica'` (o errore di collection
equivalente) su ogni test.

- [ ] **Step 3: Scrivi `scripts/riallinea_notte_logica.py`**

Crea `/home/peter/DEV/budget/scripts/riallinea_notte_logica.py`:

```python
#!/usr/bin/env python3
"""Logica decisionale del giro notturno di /riallinea (scripts/riallinea_notte.sh).

Isola da bash tutto cio' che vale la pena di testare: il calcolo dell'intervallo, i
cinque controlli del passo 7 prima di pubblicare, e la decisione/il testo del passo 8.
Solo libreria standard, piu' un import in sola lettura da scripts/riallinea.py
(carica_stato/salva_stato) per riusare lo stesso formato di stato: NON lo modifica.

Spec: docs/superpowers/specs/2026-09-11-riallinea-notturno-design.md
Piano: docs/superpowers/plans/2026-09-11-riallinea-notturno.md
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from riallinea import carica_stato, salva_stato  # noqa: E402  (import dopo sys.path)


# --- Passo 3: intervallo ---

def intervallo_vuoto(repo: str, da: str, a: str) -> bool:
    """True se non ci sono commit nuovi fra `da` (escluso) e `a` (incluso)."""
    esito = subprocess.run(
        ["git", "-C", repo, "rev-list", "--count", f"{da}..{a}"],
        capture_output=True, text=True, check=True,
    )
    return int(esito.stdout.strip()) == 0


def leggi_ultimo_sha(percorso_stato: str) -> Optional[str]:
    """`ultimo_sha` dallo stato, o None se il file non esiste o la chiave e' assente."""
    stato = carica_stato(percorso_stato)
    valore = stato.get("ultimo_sha")
    return valore if valore else None


# --- Passo 5: zero citazioni ---

def conta_citazioni_json(percorso_json: str) -> int:
    """Numero di citazioni del collector: chiave "citazioni", lista piatta di
    {simbolo, file, riga, testo} (schema misurato sul repo, vedi il piano)."""
    dati = json.loads(Path(percorso_json).read_text(encoding="utf-8"))
    return len(dati.get("citazioni", []))


# --- Passo 7: controlli prima di pubblicare ---

def file_consentiti(percorsi: list[str]) -> bool:
    """Vero se ogni percorso e' CLAUDE.md o sta sotto docs/."""
    return all(p == "CLAUDE.md" or p.startswith("docs/") for p in percorsi)


_RE_COMMIT_CORREZIONI = re.compile(r"^docs\(allineamento\): correzioni dimostrabili$")
_RE_COMMIT_RAPPORTO = re.compile(r"^docs\(allineamento\): rapporto \d{4}-\d{2}-\d{2}$")


def messaggi_commit_validi(messaggi: list[str]) -> bool:
    """Vero se la lista non e' vuota e ogni messaggio e' uno dei due letterali attesi."""
    if not messaggi:
        return False
    return all(
        _RE_COMMIT_CORREZIONI.match(m) or _RE_COMMIT_RAPPORTO.match(m)
        for m in messaggi
    )


def stato_json_non_toccato(percorsi: list[str]) -> bool:
    return "docs/superpowers/allineamento/STATO.json" not in percorsi


def report_atteso(data: str) -> str:
    return f"docs/superpowers/allineamento/{data}-notte.md"


class EsitoControllo(NamedTuple):
    ok: bool
    motivo: Optional[str]


def verifica_pubblicazione(
    worktree_pulito: bool,
    percorsi_modificati: list[str],
    messaggi_commit: list[str],
    data: str,
    report_esiste_su_disco: bool,
) -> EsitoControllo:
    """I cinque controlli del passo 7, nell'ordine della spec. Il primo che fallisce
    ferma il giro: si restituisce quello, non un elenco di tutti i guasti."""
    if not worktree_pulito:
        return EsitoControllo(False, "worktree non pulito (git status --porcelain non vuoto)")
    if not file_consentiti(percorsi_modificati):
        fuori = [p for p in percorsi_modificati if not (p == "CLAUDE.md" or p.startswith("docs/"))]
        return EsitoControllo(False, f"file fuori da CLAUDE.md/docs/**: {', '.join(fuori)}")
    if not messaggi_commit_validi(messaggi_commit):
        return EsitoControllo(False, f"messaggi di commit non validi: {messaggi_commit!r}")
    if not report_esiste_su_disco:
        return EsitoControllo(False, f"rapporto mancante: {report_atteso(data)}")
    if not stato_json_non_toccato(percorsi_modificati):
        return EsitoControllo(False, "docs/superpowers/allineamento/STATO.json modificato")
    return EsitoControllo(True, None)


# --- Passo 8: decisione di pubblicare ---

class ConteggiReport(NamedTuple):
    correzioni: int
    da_decidere: int


def estrai_sezione(testo: str, titolo: str) -> str:
    """Testo della sezione '## <titolo>' fino alla prossima intestazione di livello 2
    (o alla fine del documento). Stringa vuota se il titolo non compare."""
    pattern = re.compile(
        rf"^##\s+{re.escape(titolo)}\s*$(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(testo)
    return m.group(1).strip() if m else ""


def _conta_voci(sezione: str) -> int:
    """Numero di voci puntate di primo livello ('- ' a inizio riga)."""
    return len(re.findall(r"^- ", sezione, re.MULTILINE))


def conta_report(testo: str) -> ConteggiReport:
    correzioni = _conta_voci(estrai_sezione(testo, "Corretto automaticamente"))
    da_decidere = _conta_voci(estrai_sezione(testo, "Da decidere"))
    return ConteggiReport(correzioni=correzioni, da_decidere=da_decidere)


def decidi_pubblicazione(conteggi: ConteggiReport) -> bool:
    return conteggi.correzioni > 0 or conteggi.da_decidere > 0


def titolo_pr(data: str, conteggi: ConteggiReport) -> str:
    return (
        f"Riallineamento notturno {data}: "
        f"{conteggi.correzioni} correzioni, {conteggi.da_decidere} da decidere"
    )


def corpo_pr(testo_report: str, conteggi: ConteggiReport) -> str:
    sezione = estrai_sezione(testo_report, "Da decidere")
    corpo = f"Correzioni: {conteggi.correzioni} · Da decidere: {conteggi.da_decidere}\n"
    if sezione:
        corpo += f"\n## Da decidere\n\n{sezione}\n"
    return corpo


# --- CLI, invocata da scripts/riallinea_notte.sh ---

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("leggi-ultimo-sha")
    p.add_argument("--stato", required=True)

    p = sub.add_parser("intervallo-vuoto")
    p.add_argument("--repo", required=True)
    p.add_argument("--da", required=True)
    p.add_argument("--a", required=True)

    p = sub.add_parser("conta-citazioni")
    p.add_argument("--json", required=True, dest="percorso_json")

    p = sub.add_parser("verifica-pubblicazione")
    p.add_argument("--worktree", required=True)
    p.add_argument("--data", required=True)

    p = sub.add_parser("decisione-pr")
    p.add_argument("--report", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--corpo-out", required=True, dest="corpo_out")

    p = sub.add_parser("semina-stato")
    p.add_argument("--sha", required=True)
    p.add_argument("--stato", required=True)
    p.add_argument("--data", required=True)

    args = ap.parse_args()

    if args.comando == "leggi-ultimo-sha":
        sha = leggi_ultimo_sha(args.stato)
        if sha is None:
            sys.exit(1)
        print(sha)
        sys.exit(0)

    if args.comando == "intervallo-vuoto":
        sys.exit(0 if intervallo_vuoto(args.repo, args.da, args.a) else 10)

    if args.comando == "conta-citazioni":
        print(conta_citazioni_json(args.percorso_json))
        sys.exit(0)

    if args.comando == "verifica-pubblicazione":
        wt = Path(args.worktree)
        pulito = subprocess.run(
            ["git", "-C", str(wt), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout.strip() == ""
        percorsi = [
            r for r in subprocess.run(
                ["git", "-C", str(wt), "diff", "--name-only", "origin/main..HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.splitlines() if r
        ]
        messaggi = [
            r for r in subprocess.run(
                ["git", "-C", str(wt), "log", "--format=%s", "origin/main..HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.splitlines() if r
        ]
        report_esiste = (wt / report_atteso(args.data)).exists()
        esito = verifica_pubblicazione(pulito, percorsi, messaggi, args.data, report_esiste)
        if not esito.ok:
            print(esito.motivo, file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    if args.comando == "decisione-pr":
        testo = Path(args.report).read_text(encoding="utf-8")
        conteggi = conta_report(testo)
        Path(args.corpo_out).write_text(corpo_pr(testo, conteggi), encoding="utf-8")
        print(f"CORREZIONI={conteggi.correzioni}")
        print(f"DA_DECIDERE={conteggi.da_decidere}")
        print(f"PUBBLICA={'si' if decidi_pubblicazione(conteggi) else 'no'}")
        print(f"TITOLO={titolo_pr(args.data, conteggi)}")
        sys.exit(0)

    if args.comando == "semina-stato":
        salva_stato(args.stato, sha=args.sha, modo="diff", data=args.data)
        sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Esegui i test, verifica che passino tutti**

Comando:
```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
    /home/peter/DEV/budget/tests/test_riallinea_notte_logica.py -q -p no:cacheprovider
```
Atteso: tutti i test PASS (nessun FAIL, nessun ERROR). Se un test sull'intervallo git fallisce per
`user.email`/`user.name` mancanti nell'ambiente CI, la fixture `_repo_git` già li imposta local al
repo temporaneo — non serve altro.

- [ ] **Step 5: Rendi eseguibile e committa**

```bash
chmod +x /home/peter/DEV/budget/scripts/riallinea_notte_logica.py
cd /home/peter/DEV/budget
git add scripts/riallinea_notte_logica.py tests/test_riallinea_notte_logica.py
git commit -m "feat(riallinea-notte): logica decisionale del giro notturno, testata"
```

---

## Task 2: Prompt di pi e runner in modo `--prova` (passi 1-7)

**Dipende da:** Task 1 (usa `scripts/riallinea_notte_logica.py` come CLI, non modificato).

**Files:**
- Create: `/home/peter/DEV/budget/scripts/riallinea_notte.prompt.md`
- Create: `/home/peter/DEV/budget/scripts/riallinea_notte.sh`
- Create: `/home/peter/DEV/budget/tests/fixtures/riallinea_notte/pi_stub_ok.sh`
- Create: `/home/peter/DEV/budget/tests/fixtures/riallinea_notte/pi_stub_file_fuori.sh`

**Interfaces:**
- Consumes: i sottocomandi CLI del Task 1 (`leggi-ultimo-sha`, `intervallo-vuoto`,
  `conta-citazioni`, `verifica-pubblicazione`).
- Produces (usati dal Task 3, che modifica questo stesso file):
  - Variabili top-level: `RIALLINEA_HOME`, `REPO_PRINCIPALE`, `PI_BIN`, `STATO_FILE`, `LOG_DIR`,
    `WT_DIR`, `LOCK_FILE`, `SCRIPT_DIR`, `LOGICA`, `PROMPT_FILE`, `DATA`, `PROVA`, `DA_OVERRIDE`,
    `A_OVERRIDE`, `INSTALLA`, `WT`, `BRANCH`, `SHA_A`, `ULTIMO_SHA`, `N_CITAZIONI`.
  - Funzioni: `log_riga <passo> <esito> <codice>`, `verifica_precondizioni`, `calcola_intervallo`
    (ritorna 0=procedi, 1=errore, 2=vuoto — non scrive stato), `crea_worktree`,
    `raccogli_citazioni` (ritorna 0=procedi, 1=errore, 2=zero citazioni), `invoca_pi`,
    `controlla_pubblicazione`.
  - Variabili d'ambiente di override per i test: `RIALLINEA_NOTTE_HOME`, `RIALLINEA_NOTTE_REPO`,
    `RIALLINEA_NOTTE_PI_BIN`.

- [ ] **Step 1: Misura come si risolve `pi` sotto un lancio non interattivo**

Da eseguire (in Windows, PowerShell o cmd) prima di scrivere `invoca_pi`:
```
wsl.exe -d Ubuntu -u peter -- bash -lc "command -v pi; node --version"
wsl.exe -d Ubuntu -u peter -- bash -c  "command -v pi; node --version"
```
La prima riga è una shell di login (legge `.bash_profile`/`.profile`, quindi in genere anche il
setup di nvm); la seconda è quella più vicina a come `schtasks.exe` lancerà lo script la notte.
Se la seconda **non** trova `pi` o mostra un Node diverso da 24, annota qui sotto l'esatto blocco
di `export`/`source` che invece la prima riga usa (tipicamente il source di
`$HOME/.nvm/nvm.sh` seguito da `nvm use 24`), e riportalo nello Step 2 sostituendo il blocco `NVM_DIR`
già scritto lì con quello misurato. Se invece la seconda riga trova già `pi` e Node 24, il blocco
dello Step 2 va bene com'è e non richiede modifiche.

- [ ] **Step 2: Scrivi `scripts/riallinea_notte.prompt.md`**

Crea `/home/peter/DEV/budget/scripts/riallinea_notte.prompt.md`:

```markdown
# Prompt del giro notturno di /riallinea

Segui la skill caricata (`.claude/skills/riallinea/SKILL.md`) **alla lettera**, con tre deroghe,
valide solo per questo giro:

1. Il rapporto si chiama `docs/superpowers/allineamento/<data>-notte.md` (non `<data>.md`), dove
   `<data>` è la data ISO (AAAA-MM-GG) di questa esecuzione.
2. I commit vanno sul branch corrente di questo worktree, non su `main`. **Non fare `git push`**:
   la pubblicazione la fa lo script che ti ha invocato, dopo aver controllato il tuo lavoro.
3. **Non eseguire `--registra`**: lo fa lo script chiamante, e solo se il tuo lavoro supera i suoi
   controlli.

Le citazioni da verificare sono già pronte in `.riallinea-notte.json`, nella radice di questo
worktree: **non rilanciare** `python3 scripts/riallinea.py` per raccoglierle di nuovo. Sei in modo
`diff`: verificale **tutte**. Se il tempo o il contesto a disposizione non bastano a verificarle
tutte, dichiaralo in testa al rapporto, elencando le citazioni non guardate — mai un campione
silenzioso spacciato per verifica completa.

Vincoli della skill che restano invariati:
- correggi solo dentro la lista chiusa (sezione "La lista chiusa" della skill); tutto il resto va
  in "Da decidere";
- un piano o una spec datati (`docs/superpowers/plans/AAAA-MM-GG-*.md`,
  `docs/superpowers/specs/AAAA-MM-GG-*.md`) non si riscrive mai: solo annotato in coda;
- `git add` **per nome**, mai `-A` né `.`;
- il messaggio di commit viene da un file (`git commit -F <file>`), mai da `-m` con testo
  improvvisato che si discosti dai due letterali della skill;
- la memoria (`~/.claude/projects/-home-peter-DEV-budget/memory/`) si legge per i riferimenti
  morti e non si modifica mai.

**Non toccare alcun file fuori da `CLAUDE.md` e da `docs/`.** Lo script chiamante lo controlla
dopo che hai finito e scarta l'intero giro se trova anche un solo file fuori posto: non è un
rischio teorico, è l'unico controllo che decide se il tuo lavoro arriva a una pull request o resta
solo nel log locale.
```

- [ ] **Step 3: Scrivi `scripts/riallinea_notte.sh` (modo `--prova`, passi 1-7)**

Crea `/home/peter/DEV/budget/scripts/riallinea_notte.sh`:

```bash
#!/usr/bin/env bash
# Giro notturno di /riallinea.
# Spec: docs/superpowers/specs/2026-09-11-riallinea-notturno-design.md
# Piano:  docs/superpowers/plans/2026-09-11-riallinea-notturno.md
#
# Uso:
#   riallinea_notte.sh --prova --da <sha> --a <sha>   # passi 1-7, nessuna scrittura in rete
#   riallinea_notte.sh --installa [--conferma]        # Task 4 del piano
#   riallinea_notte.sh                                # giro reale, Task 3 del piano
set -euo pipefail

# --- Percorsi, sovrascrivibili dai test ---
RIALLINEA_HOME="${RIALLINEA_NOTTE_HOME:-$HOME/riallinea-notte}"
REPO_PRINCIPALE="${RIALLINEA_NOTTE_REPO:-$HOME/DEV/budget}"
PI_BIN="${RIALLINEA_NOTTE_PI_BIN:-pi}"
STATO_FILE="$RIALLINEA_HOME/stato/STATO.json"
LOG_DIR="$RIALLINEA_HOME/log"
WT_DIR="$RIALLINEA_HOME/wt"
LOCK_FILE="$RIALLINEA_HOME/lock"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
LOGICA="$SCRIPT_DIR/riallinea_notte_logica.py"
PROMPT_FILE="$SCRIPT_DIR/riallinea_notte.prompt.md"

DATA="$(date +%F)"

PROVA=0
DA_OVERRIDE=""
A_OVERRIDE=""
INSTALLA=0

while [ $# -gt 0 ]; do
  case "$1" in
    --prova) PROVA=1; shift ;;
    --da) DA_OVERRIDE="$2"; shift 2 ;;
    --a) A_OVERRIDE="$2"; shift 2 ;;
    --installa) INSTALLA=1; shift ;;
    *) echo "opzione sconosciuta: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "$LOG_DIR" "$WT_DIR" "$(dirname "$STATO_FILE")"
LOG_FILE="$LOG_DIR/$DATA.log"

log_riga() {
  # log_riga <passo> <esito> <codice>
  local riga
  riga="$(date +%T) passo=$1 esito=$2 codice=$3"
  echo "$riga" | tee -a "$LOG_FILE" >&2
}

# --- pi: risoluzione del PATH. Misurato allo Step 1 di questo task:
#   wsl.exe -d Ubuntu -u peter -- bash -lc 'command -v pi; node --version'   # login
#   wsl.exe -d Ubuntu -u peter -- bash -c  'command -v pi; node --version'   # non-login
# Se la seconda non trova pi con Node 24, sostituisci questo blocco col PATH/source misurato
# nella prima. Se la seconda basta gia', questo blocco va bene com'e'.
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [ -s "$NVM_DIR/nvm.sh" ]; then
  # shellcheck source=/dev/null
  . "$NVM_DIR/nvm.sh"
  nvm use 24 >/dev/null 2>&1 || true
fi

verifica_precondizioni() {
  local cmd
  for cmd in git gh "$PI_BIN"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      log_riga "precondizioni" "manca:$cmd" "1"
      return 1
    fi
  done
  if ! gh auth status >/dev/null 2>&1; then
    log_riga "precondizioni" "gh-non-autenticato" "1"
    return 1
  fi
  if ! "$PI_BIN" auth check --provider gx10 --json --no-refresh >/dev/null 2>&1; then
    log_riga "precondizioni" "gx10-non-raggiungibile" "1"
    return 1
  fi
  log_riga "precondizioni" "ok" "0"
  return 0
}

# Calcola l'intervallo. Scrive ULTIMO_SHA e SHA_A. Ritorna:
#   0  intervallo non vuoto, si procede
#   2  intervallo vuoto ("niente di nuovo"): nessuno stato da scrivere
#   1  errore (fetch fallito, o nessuno stato e nessun --da)
calcola_intervallo() {
  if ! git -C "$REPO_PRINCIPALE" fetch origin main >/dev/null 2>&1; then
    log_riga "fetch" "fallito" "1"
    return 1
  fi
  local sha_origin_main
  sha_origin_main="$(git -C "$REPO_PRINCIPALE" rev-parse origin/main)"

  if [ -n "$DA_OVERRIDE" ]; then
    ULTIMO_SHA="$DA_OVERRIDE"
  elif ULTIMO_SHA="$(python3 "$LOGICA" leggi-ultimo-sha --stato "$STATO_FILE")"; then
    :
  else
    log_riga "intervallo" "stato-assente-e-nessun---da" "1"
    return 1
  fi

  SHA_A="${A_OVERRIDE:-$sha_origin_main}"

  if python3 "$LOGICA" intervallo-vuoto --repo "$REPO_PRINCIPALE" --da "$ULTIMO_SHA" --a "$SHA_A"; then
    log_riga "intervallo" "vuoto" "0"
    return 2
  fi
  log_riga "intervallo" "non-vuoto:$ULTIMO_SHA..$SHA_A" "0"
  return 0
}

crea_worktree() {
  local voce
  for voce in "$WT_DIR"/*; do
    [ -e "$voce" ] || continue
    [ "$(basename "$voce")" = "$DATA" ] && continue
    git -C "$REPO_PRINCIPALE" worktree remove "$voce" --force 2>/dev/null || rm -rf "$voce"
    log_riga "worktree" "rimosso-precedente:$voce" "0"
  done
  git -C "$REPO_PRINCIPALE" worktree prune >/dev/null 2>&1 || true

  local qui="$WT_DIR/$DATA"
  if [ -e "$qui" ]; then
    git -C "$REPO_PRINCIPALE" worktree remove "$qui" --force 2>/dev/null || rm -rf "$qui"
  fi
  WT="$qui"
  BRANCH="riallinea/notte-$DATA"
  if ! git -C "$REPO_PRINCIPALE" worktree add --detach "$WT" "$SHA_A" >/dev/null; then
    log_riga "worktree" "fallito" "1"
    return 1
  fi
  if ! git -C "$WT" switch -c "$BRANCH" >/dev/null; then
    log_riga "worktree" "switch-fallito" "1"
    return 1
  fi
  log_riga "worktree" "creato:$WT" "0"
  return 0
}

raccogli_citazioni() {
  local out="$WT/.riallinea-notte.json"
  if ! (cd "$WT" && python3 scripts/riallinea.py --da "$ULTIMO_SHA" --a "$SHA_A" \
        --stato "$STATO_FILE" > "$out"); then
    log_riga "raccolta" "fallita" "1"
    return 1
  fi
  N_CITAZIONI="$(python3 "$LOGICA" conta-citazioni --json "$out")"
  log_riga "raccolta" "citazioni:$N_CITAZIONI" "0"
  if [ "$N_CITAZIONI" -eq 0 ]; then
    return 2
  fi
  return 0
}

invoca_pi() {
  local prompt
  prompt="$(cat "$PROMPT_FILE")"
  if ! (cd "$WT" && timeout 2h "$PI_BIN" -p "$prompt" --provider gx10 --no-session \
        --skill "$WT/.claude/skills/riallinea"); then
    log_riga "pi" "fallito-o-timeout" "1"
    return 1
  fi
  log_riga "pi" "ok" "0"
  return 0
}

controlla_pubblicazione() {
  if ! python3 "$LOGICA" verifica-pubblicazione --worktree "$WT" --data "$DATA" 2>"$WT/.controllo-fallito"; then
    log_riga "controlli" "fallito:$(cat "$WT/.controllo-fallito")" "1"
    return 1
  fi
  log_riga "controlli" "ok" "0"
  return 0
}

# --- flusso principale ---

if [ "$INSTALLA" -eq 1 ]; then
  echo "--installa arriva nel Task 4 del piano" >&2
  exit 2
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log_riga "lock" "giro-gia-in-corso" "0"
  exit 0
fi

verifica_precondizioni || exit 1

set +e
calcola_intervallo
esito_intervallo=$?
set -e
if [ "$esito_intervallo" -eq 1 ]; then exit 1; fi
if [ "$esito_intervallo" -eq 2 ]; then
  log_riga "giro" "niente-di-nuovo" "0"
  exit 0
fi

crea_worktree || exit 1

set +e
raccogli_citazioni
esito_raccolta=$?
set -e
if [ "$esito_raccolta" -eq 1 ]; then exit 1; fi
if [ "$esito_raccolta" -eq 2 ]; then
  log_riga "giro" "zero-citazioni" "0"
  # il passo 9 (registra) e la pulizia per questo caso arrivano col Task 3;
  # in --prova non si scrive comunque stato (spec §9).
  exit 0
fi

invoca_pi || exit 1
controlla_pubblicazione || exit 1

if [ "$PROVA" -eq 1 ]; then
  log_riga "prova" "superata:$WT" "0"
  exit 0
fi

echo "modo reale non ancora implementato in questo commit (arriva col Task 3)" >&2
exit 2
```

- [ ] **Step 4: Rendi eseguibile e scrivi i due stub di `pi` per la verifica**

```bash
chmod +x /home/peter/DEV/budget/scripts/riallinea_notte.sh
mkdir -p /home/peter/DEV/budget/tests/fixtures/riallinea_notte
```

Crea `/home/peter/DEV/budget/tests/fixtures/riallinea_notte/pi_stub_ok.sh`:

```bash
#!/usr/bin/env bash
# Finto "pi" per la verifica del Task 2: ignora tutti gli argomenti (li riceve solo
# perche' il runner li passa), produce un giro valido nella cwd corrente, che il
# runner ha gia' impostato sul worktree prima di invocare $PI_BIN.
set -euo pipefail
DATA="$(date +%F)"
mkdir -p docs/superpowers/allineamento
cat > "docs/superpowers/allineamento/${DATA}-notte.md" <<EOF
# Rapporto di riallineamento notturno ${DATA}

Modo: diff (giro notturno, worktree di prova del Task 2)

## Corretto automaticamente

- prova: nessuna correzione reale, e' un giro di collaudo del Task 2

## Da decidere

Nessuna voce.

## Memoria — riferimenti morti

Nessuno.

## Non verificabile

Nessuno.
EOF
git add "docs/superpowers/allineamento/${DATA}-notte.md"
git commit -q -m "docs(allineamento): rapporto ${DATA}"
```

Crea `/home/peter/DEV/budget/tests/fixtures/riallinea_notte/pi_stub_file_fuori.sh`:

```bash
#!/usr/bin/env bash
# Come pi_stub_ok.sh, ma tocca anche un file fuori da docs/: serve al controllo
# negativo della spec §9 ("un file fuori da docs/ ... fa fallire il passo 7").
set -euo pipefail
"$(dirname "$0")/pi_stub_ok.sh"
echo "// riga estranea aggiunta dallo stub di collaudo" >> backend/app/main.py
git add backend/app/main.py
git commit -q -m "docs(allineamento): rapporto $(date +%F)"
```

```bash
chmod +x /home/peter/DEV/budget/tests/fixtures/riallinea_notte/pi_stub_ok.sh
chmod +x /home/peter/DEV/budget/tests/fixtures/riallinea_notte/pi_stub_file_fuori.sh
```

- [ ] **Step 5: Verifica il caso positivo — `--prova` supera i passi 1-7**

```bash
export RIALLINEA_NOTTE_HOME="$(mktemp -d)"
export RIALLINEA_NOTTE_REPO="/home/peter/DEV/budget"
export RIALLINEA_NOTTE_PI_BIN="/home/peter/DEV/budget/tests/fixtures/riallinea_notte/pi_stub_ok.sh"
DA="$(git -C /home/peter/DEV/budget rev-parse HEAD~15)"
A="$(git -C /home/peter/DEV/budget rev-parse HEAD)"
/home/peter/DEV/budget/scripts/riallinea_notte.sh --prova --da "$DA" --a "$A"
echo "uscita=$?"
```
Atteso: uscita 0, log finale `passo=prova esito=superata:...`. Se il log mostra
`passo=raccolta esito=citazioni:0` seguito da `passo=giro esito=zero-citazioni`, il range
scelto non tocca `docs/`/`CLAUDE.md`: allarga la finestra (`HEAD~40`, poi `HEAD~80`, ...) e
ripeti — è una proprietà del contenuto reale del repo in quel momento, non un difetto dello
script.

- [ ] **Step 6: Verifica il controllo negativo — un file fuori da `docs/` fa fallire il passo 7**

```bash
export RIALLINEA_NOTTE_HOME="$(mktemp -d)"
export RIALLINEA_NOTTE_REPO="/home/peter/DEV/budget"
export RIALLINEA_NOTTE_PI_BIN="/home/peter/DEV/budget/tests/fixtures/riallinea_notte/pi_stub_file_fuori.sh"
DA="$(git -C /home/peter/DEV/budget rev-parse HEAD~15)"
A="$(git -C /home/peter/DEV/budget rev-parse HEAD)"
/home/peter/DEV/budget/scripts/riallinea_notte.sh --prova --da "$DA" --a "$A"
echo "uscita=$?"
```
Atteso: uscita 1, e nel log una riga `passo=controlli esito=fallito:file fuori da
CLAUDE.md/docs/**: backend/app/main.py codice=1`. Usa lo stesso `--da`/`--a` (allargato allo
stesso modo, se serve) dello Step 5, per attraversare lo stesso percorso fino al passo 7.

- [ ] **Step 7: Committa**

```bash
cd /home/peter/DEV/budget
git add scripts/riallinea_notte.prompt.md scripts/riallinea_notte.sh \
    tests/fixtures/riallinea_notte/pi_stub_ok.sh \
    tests/fixtures/riallinea_notte/pi_stub_file_fuori.sh
git commit -m "feat(riallinea-notte): runner --prova (passi 1-7) e prompt di pi"
```

---

## Task 3: Modo reale del runner — pubblicazione, notifica, pulizia

**Dipende da:** Task 2 (modifica `scripts/riallinea_notte.sh`).

**Files:**
- Modify: `/home/peter/DEV/budget/scripts/riallinea_notte.sh`

**Interfaces:**
- Consumes: `decisione-pr` e `semina-stato` del Task 1; tutte le funzioni/variabili prodotte dal
  Task 2.
- Produces (usati dal Task 4): `--secco` (bash flag, dry-run: stampa i comandi `git push`/`gh pr
  create`/`gh issue comment` invece di eseguirli), funzioni `decidi_e_pubblica`,
  `notifica_fallimento`, `fallisci <passo> <codice>`, `pulizia`, `ruota_log`, variabile
  `PUBBLICATO`, lettura opzionale di `$RIALLINEA_HOME/config` (chiave `ISSUE_FALLIMENTI=<numero>`,
  scritta dal Task 4).

- [ ] **Step 1: Aggiungi il flag `--secco` e la lettura della config**

In `/home/peter/DEV/budget/scripts/riallinea_notte.sh`, cambia:

```bash
PROVA=0
DA_OVERRIDE=""
A_OVERRIDE=""
INSTALLA=0

while [ $# -gt 0 ]; do
  case "$1" in
    --prova) PROVA=1; shift ;;
    --da) DA_OVERRIDE="$2"; shift 2 ;;
    --a) A_OVERRIDE="$2"; shift 2 ;;
    --installa) INSTALLA=1; shift ;;
    *) echo "opzione sconosciuta: $1" >&2; exit 2 ;;
  esac
done
```

in:

```bash
PROVA=0
DA_OVERRIDE=""
A_OVERRIDE=""
INSTALLA=0
SECCO=0

while [ $# -gt 0 ]; do
  case "$1" in
    --prova) PROVA=1; shift ;;
    --da) DA_OVERRIDE="$2"; shift 2 ;;
    --a) A_OVERRIDE="$2"; shift 2 ;;
    --installa) INSTALLA=1; shift ;;
    --secco) SECCO=1; shift ;;
    *) echo "opzione sconosciuta: $1" >&2; exit 2 ;;
  esac
done

[ -f "$RIALLINEA_HOME/config" ] && . "$RIALLINEA_HOME/config"
```

(la riga `[ -f ... ] && . ...` va subito dopo il blocco `while`, prima di `mkdir -p "$LOG_DIR" ...`).

- [ ] **Step 2: Aggiungi `notifica_fallimento`, `fallisci`, `pulizia`, `ruota_log`, `decidi_e_pubblica`**

Subito dopo la funzione `controlla_pubblicazione` (e prima del commento `# --- flusso
principale ---`), aggiungi:

```bash
notifica_fallimento() {
  # notifica_fallimento <passo> <codice>
  local corpo="Riallineamento notturno fallito: passo=$1 data=$DATA uscita=$2"
  if [ "$SECCO" -eq 1 ]; then
    echo "[secco] gh issue comment ${ISSUE_FALLIMENTI:-<non-configurata>} --body '$corpo'"
    return 0
  fi
  if [ -n "${ISSUE_FALLIMENTI:-}" ]; then
    gh issue comment "$ISSUE_FALLIMENTI" --body "$corpo" >/dev/null 2>&1 || true
  fi
}

fallisci() {
  # fallisci <passo> <codice>
  notifica_fallimento "$1" "$2"
  exit "$2"
}

pulizia() {
  git -C "$REPO_PRINCIPALE" worktree remove "$WT" --force 2>/dev/null || true
  if [ "${PUBBLICATO:-0}" -eq 1 ]; then
    git -C "$REPO_PRINCIPALE" branch -D "$BRANCH" >/dev/null 2>&1 || true
  fi
}

ruota_log() {
  find "$LOG_DIR" -maxdepth 1 -name '*.log' -mtime +30 -delete 2>/dev/null || true
}

decidi_e_pubblica() {
  local report_rel="docs/superpowers/allineamento/${DATA}-notte.md"
  local corpo_file="$WT/.pr-corpo.txt"
  local uscita
  uscita="$(python3 "$LOGICA" decisione-pr --report "$WT/$report_rel" --data "$DATA" \
             --corpo-out "$corpo_file")"
  local correzioni da_decidere pubblica titolo
  correzioni="$(echo "$uscita" | sed -n 's/^CORREZIONI=//p')"
  da_decidere="$(echo "$uscita" | sed -n 's/^DA_DECIDERE=//p')"
  pubblica="$(echo "$uscita" | sed -n 's/^PUBBLICA=//p')"
  titolo="$(echo "$uscita" | sed -n 's/^TITOLO=//p')"
  log_riga "decisione" "correzioni:$correzioni da_decidere:$da_decidere pubblica:$pubblica" "0"

  if [ "$pubblica" = "no" ]; then
    PUBBLICATO=0
    python3 "$LOGICA" semina-stato --sha "$SHA_A" --stato "$STATO_FILE" --data "$DATA"
    log_riga "stato" "avanzato-senza-pr:$SHA_A" "0"
    return 0
  fi

  if [ "$SECCO" -eq 1 ]; then
    echo "[secco] git -C $WT push -u origin $BRANCH"
    echo "[secco] gh pr create --base main --head $BRANCH --title \"$titolo\" --body-file $corpo_file"
    PUBBLICATO=0
    return 0
  fi

  if ! git -C "$WT" push -u origin "$BRANCH"; then
    log_riga "push" "fallito" "1"
    return 1
  fi
  if ! gh pr create --base main --head "$BRANCH" --title "$titolo" --body-file "$corpo_file"; then
    log_riga "pr" "fallito" "1"
    return 1
  fi
  PUBBLICATO=1
  python3 "$LOGICA" semina-stato --sha "$SHA_A" --stato "$STATO_FILE" --data "$DATA"
  log_riga "stato" "avanzato-con-pr:$SHA_A" "0"
  return 0
}
```

- [ ] **Step 3: Sostituisci il flusso principale**

Nel blocco `# --- flusso principale ---`, sostituisci **ogni** `exit 1` che segue un passo fallito
con `fallisci "<passo>" 1` (stesso nome passo della riga di `log_riga` appena sopra), e collega la
pubblicazione reale. Il blocco intero diventa:

```bash
# --- flusso principale ---

if [ "$INSTALLA" -eq 1 ]; then
  echo "--installa arriva nel Task 4 del piano" >&2
  exit 2
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log_riga "lock" "giro-gia-in-corso" "0"
  exit 0
fi

verifica_precondizioni || fallisci "precondizioni" 1

set +e
calcola_intervallo
esito_intervallo=$?
set -e
if [ "$esito_intervallo" -eq 1 ]; then fallisci "intervallo" 1; fi
if [ "$esito_intervallo" -eq 2 ]; then
  log_riga "giro" "niente-di-nuovo" "0"
  exit 0
fi

crea_worktree || fallisci "worktree" 1

set +e
raccogli_citazioni
esito_raccolta=$?
set -e
if [ "$esito_raccolta" -eq 1 ]; then fallisci "raccolta" 1; fi
if [ "$esito_raccolta" -eq 2 ]; then
  log_riga "giro" "zero-citazioni" "0"
  if [ "$PROVA" -eq 0 ]; then
    python3 "$LOGICA" semina-stato --sha "$SHA_A" --stato "$STATO_FILE" --data "$DATA"
    PUBBLICATO=0
    pulizia
    ruota_log
  fi
  exit 0
fi

invoca_pi || fallisci "pi" 1
controlla_pubblicazione || fallisci "controlli" 1

if [ "$PROVA" -eq 1 ]; then
  log_riga "prova" "superata:$WT" "0"
  exit 0
fi

decidi_e_pubblica || fallisci "pubblicazione" 1
pulizia
ruota_log
log_riga "giro" "completato" "0"
exit 0
```

Rimuovi il vecchio blocco finale (`if [ "$PROVA" -eq 1 ]; then ... fi` seguito da `echo "modo reale
non ancora implementato..."`) che questo sostituisce per intero.

- [ ] **Step 4: Verifica `--secco` con pubblicazione (correzioni/da-decidere presenti)**

Riusa lo stub `pi_stub_ok.sh` del Task 2 (scrive 1 correzione, 0 da-decidere → `PUBBLICA=si`):

```bash
export RIALLINEA_NOTTE_HOME="$(mktemp -d)"
export RIALLINEA_NOTTE_REPO="/home/peter/DEV/budget"
export RIALLINEA_NOTTE_PI_BIN="/home/peter/DEV/budget/tests/fixtures/riallinea_notte/pi_stub_ok.sh"
DA="$(git -C /home/peter/DEV/budget rev-parse HEAD~15)"
A="$(git -C /home/peter/DEV/budget rev-parse HEAD)"
/home/peter/DEV/budget/scripts/riallinea_notte.sh --da "$DA" --a "$A" --secco
echo "uscita=$?"
cat "$RIALLINEA_NOTTE_HOME/stato/STATO.json" 2>/dev/null || echo "(stato non scritto: atteso, e' il ramo pubblica-si+secco)"
```
Atteso: uscita 0; nell'output compaiono due righe `[secco] git -C .../wt/<data> push -u origin
riallinea/notte-<data>` e `[secco] gh pr create --base main --head riallinea/notte-<data> --title
"Riallineamento notturno <data>: 1 correzioni, 0 da decidere" --body-file .../.pr-corpo.txt`; il
worktree sotto `$RIALLINEA_NOTTE_HOME/wt/` non esiste più dopo l'esecuzione (`pulizia` l'ha
rimosso); `stato/STATO.json` **non** esiste (nessun `--registra` reale è girato, coerente con
"nessuna scrittura in rete in nessun test": la pubblicazione non è realmente avvenuta).

Se allargando la finestra come nel Task 2 ottieni comunque zero correzioni "vere" non importa: lo
stub scrive sempre la stessa riga di correzione, indipendentemente da cosa ha trovato il
collector — il numero che conta per questo test è quello nel titolo stampato, non la realtà del
repo.

- [ ] **Step 5: Verifica il ramo "niente da pubblicare" (stato avanza, nessuna PR)**

Crea al volo uno stub che scrive un rapporto senza voci (riusa `RAPPORTO_VUOTO` del Task 1):
```bash
cat > /tmp/pi_stub_zero.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
DATA="$(date +%F)"
mkdir -p docs/superpowers/allineamento
cat > "docs/superpowers/allineamento/${DATA}-notte.md" <<REPORT
# Rapporto di riallineamento notturno ${DATA}

Modo: diff (giro notturno, worktree di collaudo del Task 3)

## Corretto automaticamente

Nessuna correzione.

## Da decidere

Nessuna voce.

## Memoria — riferimenti morti

Nessuno.

## Non verificabile

Nessuno.
REPORT
git add "docs/superpowers/allineamento/${DATA}-notte.md"
git commit -q -m "docs(allineamento): rapporto ${DATA}"
EOF
chmod +x /tmp/pi_stub_zero.sh

export RIALLINEA_NOTTE_HOME="$(mktemp -d)"
export RIALLINEA_NOTTE_REPO="/home/peter/DEV/budget"
export RIALLINEA_NOTTE_PI_BIN="/tmp/pi_stub_zero.sh"
DA="$(git -C /home/peter/DEV/budget rev-parse HEAD~15)"
A="$(git -C /home/peter/DEV/budget rev-parse HEAD)"
/home/peter/DEV/budget/scripts/riallinea_notte.sh --da "$DA" --a "$A" --secco
echo "uscita=$?"
cat "$RIALLINEA_NOTTE_HOME/stato/STATO.json"
```
Atteso: uscita 0; nel log `passo=decisione esito=correzioni:0 da_decidere:0 pubblica:no`; **nessuna**
riga `[secco] git push`/`[secco] gh pr create`; `stato/STATO.json` esiste e il suo `ultimo_sha` è
uguale ad `$A` (lo stato avanza comunque, spec §5.8); il worktree è stato rimosso.

- [ ] **Step 6: Verifica la notifica di fallimento in `--secco`**

```bash
export RIALLINEA_NOTTE_HOME="$(mktemp -d)"
mkdir -p "$RIALLINEA_NOTTE_HOME"
echo "ISSUE_FALLIMENTI=999" > "$RIALLINEA_NOTTE_HOME/config"
export RIALLINEA_NOTTE_REPO="/home/peter/DEV/budget"
export RIALLINEA_NOTTE_PI_BIN="/percorso/che/non/esiste"
/home/peter/DEV/budget/scripts/riallinea_notte.sh --secco
echo "uscita=$?"
```
Atteso: uscita 1; nel log una riga `passo=precondizioni esito=manca:/percorso/che/non/esiste
codice=1`; nell'output (stdout) la riga `[secco] gh issue comment 999 --body 'Riallineamento
notturno fallito: passo=precondizioni data=<oggi> uscita=1'`.

- [ ] **Step 7: Committa**

```bash
cd /home/peter/DEV/budget
git add scripts/riallinea_notte.sh
git commit -m "feat(riallinea-notte): modo reale (push/PR/registra/notifica/pulizia)"
```

---

## Task 4: `--installa`

**Dipende da:** Task 3 (modifica `scripts/riallinea_notte.sh`); usa `semina-stato` del Task 1.

**Files:**
- Modify: `/home/peter/DEV/budget/scripts/riallinea_notte.sh`

**Interfaces:**
- Consumes: `semina-stato` (Task 1); `RIALLINEA_HOME`, `REPO_PRINCIPALE`, `LOGICA`, `PROMPT_FILE`,
  `SCRIPT_DIR` (Task 2).
- Produces: flag `--conferma`; funzione `installa`; file scritti da un'installazione riuscita:
  `$RIALLINEA_HOME/bin/{riallinea_notte.sh,riallinea_notte_logica.py,riallinea_notte.prompt.md}`,
  `$RIALLINEA_HOME/stato/STATO.json` (seminato), `$RIALLINEA_HOME/config`
  (`ISSUE_FALLIMENTI=<numero>`, solo se un'issue è stata trovata o creata).

- [ ] **Step 1: Aggiungi il flag `--conferma`**

In `scripts/riallinea_notte.sh`, cambia:
```bash
PROVA=0
DA_OVERRIDE=""
A_OVERRIDE=""
INSTALLA=0
SECCO=0
```
in:
```bash
PROVA=0
DA_OVERRIDE=""
A_OVERRIDE=""
INSTALLA=0
SECCO=0
CONFERMA=0
```
e nel blocco `case "$1" in`, aggiungi una riga prima di `*)`:
```bash
    --conferma) CONFERMA=1; shift ;;
```

- [ ] **Step 2: Aggiungi la funzione `installa`**

Subito dopo la funzione `decidi_e_pubblica` (aggiunta dal Task 3), aggiungi:

```bash
installa() {
  local dest="$RIALLINEA_HOME/bin"
  mkdir -p "$dest" "$RIALLINEA_HOME/stato" "$RIALLINEA_HOME/log" "$RIALLINEA_HOME/wt"
  cp "$SCRIPT_DIR/riallinea_notte.sh" "$dest/riallinea_notte.sh"
  cp "$SCRIPT_DIR/riallinea_notte_logica.py" "$dest/riallinea_notte_logica.py"
  cp "$PROMPT_FILE" "$dest/riallinea_notte.prompt.md"
  chmod +x "$dest/riallinea_notte.sh"
  echo "copiato in $dest"

  local stato_dest="$RIALLINEA_HOME/stato/STATO.json"
  if [ ! -f "$stato_dest" ]; then
    if ! git -C "$REPO_PRINCIPALE" fetch origin main >/dev/null 2>&1; then
      echo "fetch fallito, stato non inizializzato" >&2
      return 1
    fi
    local sha_seme
    sha_seme="$(git -C "$REPO_PRINCIPALE" show origin/main:docs/superpowers/allineamento/STATO.json \
                | python3 -c "import json,sys; print(json.load(sys.stdin)['ultimo_sha'])")"
    python3 "$LOGICA" semina-stato --sha "$sha_seme" --stato "$stato_dest" --data "$(date +%F)"
    echo "stato inizializzato da origin/main: ultimo_sha=$sha_seme"
  else
    echo "stato gia' presente in $stato_dest, non toccato"
  fi

  local trovata
  trovata="$(gh issue list --search "Riallineamento notturno: giri falliti" --state all \
             --json number,title \
             --jq '.[] | select(.title=="Riallineamento notturno: giri falliti") | .number' \
             2>/dev/null | head -1)"
  if [ -n "$trovata" ]; then
    echo "issue di notifica gia' presente: #$trovata"
    echo "ISSUE_FALLIMENTI=$trovata" > "$RIALLINEA_HOME/config"
  elif [ "$CONFERMA" -eq 1 ]; then
    local numero
    numero="$(gh issue create --title "Riallineamento notturno: giri falliti" \
               --label documentation \
               --body "Un commento per ogni giro notturno fallito: data, passo, codice d'uscita." \
               | grep -o '[0-9]\+$')"
    echo "issue creata: #$numero"
    echo "ISSUE_FALLIMENTI=$numero" > "$RIALLINEA_HOME/config"
  else
    echo "[senza --conferma] avrei eseguito:"
    echo "  gh issue create --title \"Riallineamento notturno: giri falliti\" --label documentation --body \"Un commento per ogni giro notturno fallito: data, passo, codice d'uscita.\""
  fi

  echo
  echo "Comando da eseguire in Windows (PowerShell o cmd, come amministratore) per il Pianificatore attivita':"
  echo "  schtasks.exe /create /tn \"RiallineaNotte\" /sc daily /st 02:17 /tr \"wsl.exe -d Ubuntu -u peter -- $dest/riallinea_notte.sh\" /f"
  echo "(non eseguito automaticamente: lo lancia il proprietario, o il coordinatore con la sua approvazione esplicita)"
}
```

- [ ] **Step 3: Collega `--installa` al flusso principale**

Sostituisci:
```bash
if [ "$INSTALLA" -eq 1 ]; then
  echo "--installa arriva nel Task 4 del piano" >&2
  exit 2
fi
```
con:
```bash
if [ "$INSTALLA" -eq 1 ]; then
  installa
  exit $?
fi
```

- [ ] **Step 4: Verifica `--installa` senza `--conferma`**

```bash
export RIALLINEA_NOTTE_HOME="$(mktemp -d)"
export RIALLINEA_NOTTE_REPO="/home/peter/DEV/budget"
/home/peter/DEV/budget/scripts/riallinea_notte.sh --installa
echo "uscita=$?"
ls "$RIALLINEA_NOTTE_HOME/bin"
cat "$RIALLINEA_NOTTE_HOME/stato/STATO.json"
```
Atteso: uscita 0; `bin/` contiene i tre file copiati ed eseguibile `riallinea_notte.sh`;
`stato/STATO.json` ha un `ultimo_sha` non vuoto (letto da `origin/main`); l'output contiene la riga
`schtasks.exe /create /tn "RiallineaNotte" ...` con il percorso `$RIALLINEA_NOTTE_HOME/bin/...`; se
l'issue "Riallineamento notturno: giri falliti" non esiste ancora su GitHub, l'output mostra
`[senza --conferma] avrei eseguito: gh issue create ...` e **nessuna** issue nuova compare
(verificabile con `gh issue list --search "Riallineamento notturno: giri falliti" --state all`).

- [ ] **Step 5: Committa**

```bash
cd /home/peter/DEV/budget
git add scripts/riallinea_notte.sh
git commit -m "feat(riallinea-notte): --installa (copia, semina stato, issue, schtasks stampato)"
```

---

## Task 5: Accettazione — eseguita dal coordinatore, non da pi

**Perché non lo fa pi:** richiede il vero `pi`/gx10, una vera pull request su GitHub, e
l'approvazione esplicita del proprietario per installare un task pianificato che gira ogni notte
senza supervisione (spec §9-§10). Nessun test automatico di questo piano può sostituirlo.

**Dipende da:** Task 1-4 mergiati sul branch del lotto.

- [ ] **Step 1: `--prova` reale, con `pi` vero, su un intervallo reale di `origin/main`**

```bash
cd /home/peter/DEV/budget
git fetch origin main
DA="$(git rev-parse origin/main~15)"
A="$(git rev-parse origin/main)"
./scripts/riallinea_notte.sh --prova --da "$DA" --a "$A"
```
Criterio di accettazione (spec §9): produce `docs/superpowers/allineamento/<data>-notte.md` nel
worktree e supera il passo 7, con almeno una citazione verificata per davvero da `pi` (non dallo
stub). Se l'intervallo scelto produce zero citazioni, allarga la finestra (`~30`, poi `~60`) come
nei Task 2-3.

Leggi il rapporto prodotto e confronta i suoi conteggi dichiarati con `.riallinea-notte.json` nello
stesso worktree (spec §8, rischio "pi campiona senza dirlo"): se il rapporto dichiara di aver
saltato delle citazioni, verifica che le elenchi, non che le taccia.

- [ ] **Step 2: Installazione, con l'approvazione esplicita del proprietario**

Solo dopo un sì esplicito del proprietario a procedere:
```bash
/home/peter/DEV/budget/scripts/riallinea_notte.sh --installa --conferma
```
Poi, in Windows (PowerShell o cmd, come amministratore), esegui **esattamente** il comando
`schtasks.exe` che l'installazione ha stampato.

- [ ] **Step 3: Il mattino dopo il primo giro reale**

Controlla, in quest'ordine:
1. `cat ~/riallinea-notte/log/<data-di-ieri-notte>.log` (dentro WSL) — il giro è arrivato in fondo?
   Se si è fermato, a quale passo?
2. `gh pr list --search "Riallineamento notturno"` — è comparsa una PR (se il rapporto aveva
   correzioni o voci «Da decidere»), o nessuna (se il rapporto era vuoto — controlla comunque il
   log per la riga `pubblica:no`)?
3. Se una PR è comparsa, la sua revisione (manuale, non di questo runner) verifica anche il rischio
   "pi campiona senza dirlo" del passo 1: i conteggi del rapporto contro `.riallinea-notte.json` del
   worktree (che resta sul disco solo se il giro non ha fatto `pulizia`, cioè solo su un
   fallimento — su un successo il worktree è già stato rimosso, quindi questo controllo va fatto
   leggendo il rapporto stesso, non il JSON).
4. Il job "Budget" su Jenkins **non** deve mostrare una build innescata dal push su
   `riallinea/notte-<data>` (spec §8, rischio "una push su un branch fa ripartire Jenkins — da
   verificare al primo giro reale"): apri la cronologia del job nell'interfaccia di Jenkins e
   controlla che l'ultima build resti quella precedente al push, non una nuova innescata subito
   dopo.

Se un controllo fallisce, il giro successivo recupera comunque l'intervallo perso (lo stato non è
avanzato su un fallimento) — non serve un intervento manuale sull'intervallo, solo la diagnosi del
perché quel passo ha fallito.
