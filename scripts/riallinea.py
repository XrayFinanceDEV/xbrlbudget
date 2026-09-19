#!/usr/bin/env python3
"""Parte meccanica del riallineamento documentazione <-> codice.

Consegna quattro cose su un intervallo di commit: i COMMIT (soggetto, corpo, file di
codice toccati), i SIMBOLI mossi e chi li nomina, le MANOPOLE nuove che nessun
documento nomina, e le righe di documentazione che nominano un FILE toccato.
NON modifica documentazione: osserva e riferisce. Chi decide cosa correggere e cosa
segnalare e' lo skill `/riallinea`, che consuma questo JSON.

I commit sono la spina dorsale, non un extra: un join per nome di simbolo non vede
la prosa che descrive una regola, e su un giro reale erano 13 frasi false su 14.

Solo libreria standard: deve girare con `python3 scripts/riallinea.py`, senza venv.

Spec: docs/superpowers/specs/2026-08-14-agente-riallineamento-design.md
"""
import argparse
import datetime
import json
import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

ESTENSIONI_CODICE = {".py", ".ts", ".tsx", ".js", ".jsx"}

# Riconoscimento per riga. Deliberatamente grossolano: un falso positivo costa una
# verifica in piu', un falso negativo costa un disallineamento non visto (spec §Rischi 3).
_REGOLE = [
    ("funzione", re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)")),
    ("classe", re.compile(r"^\s*class\s+([A-Za-z_]\w*)")),
    ("rotta", re.compile(r"^\s*@router\.(?:get|post|put|patch|delete)\(\s*[\"']([^\"']+)")),
    ("funzione", re.compile(r"^\s*export\s+default\s+(?:async\s+)?function\s+([A-Za-z_]\w*)")),
    ("funzione", re.compile(r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z_]\w*)")),
    ("funzione", re.compile(r"^\s*export\s+const\s+([a-z][A-Za-z0-9_]*)\s*[:=]")),
    ("costante", re.compile(r"^\s*export\s+const\s+([A-Z][A-Z0-9_]{2,})\s*[:=]")),
    ("tipo", re.compile(r"^\s*export\s+(?:type|interface)\s+([A-Za-z_]\w*)")),
    ("colonna", re.compile(r"^\s*([a-z_]\w*)\s*=\s*Column\(")),
    ("costante", re.compile(r"^\s*([A-Z][A-Z0-9_]{2,})\s*[:=]")),
]

# File rinominato/cancellato: cattura sia il vecchio (a/) sia il nuovo (b/) percorso,
# perche' su una cancellazione "+++" vale "/dev/null" e il nome va preso da qui.
_RIGA_DIFF_GIT = re.compile(r"^diff --git a/(.+) b/(.+)$")


@dataclass(frozen=True)
class Simbolo:
    """Un simbolo che il codice ha spostato (aggiunto o rimosso) in un diff.

    genere ∈ {"funzione", "classe", "costante", "colonna", "rotta", "tipo"}
    stato  ∈ {"aggiunto", "rimosso"}
    """
    nome: str
    genere: str
    file: str
    stato: str          # "aggiunto" | "rimosso"


def _e_codice(percorso: str) -> bool:
    return Path(percorso).suffix in ESTENSIONI_CODICE


def simboli_da_diff(diff: str) -> List[Simbolo]:
    """Simboli mossi, letti da un diff unificato. Un rename appare come rimosso +
    aggiunto: riconoscerlo come tale e' compito dello skill, con `git log -M`.

    Attribuzione del file: normalmente e' il percorso "b/" (nuovo). Su una
    cancellazione intera "+++" vale "/dev/null" — in quel caso i simboli rimossi
    vanno attribuiti al percorso "a/" (vecchio), letto dalla riga "diff --git",
    altrimenti spariscono o restano agganciati al file precedente nello stesso diff.
    """
    trovati, visti = [], set()
    file_corrente = ""
    file_vecchio = ""
    for riga in diff.splitlines():
        m_git = _RIGA_DIFF_GIT.match(riga)
        if m_git:
            file_vecchio, file_corrente = m_git.group(1), m_git.group(2)
            continue
        if riga.startswith("+++ "):
            percorso = riga[4:].strip()
            if percorso == "/dev/null":
                file_corrente = file_vecchio
            elif percorso.startswith("b/"):
                file_corrente = percorso[2:]
            else:
                file_corrente = percorso
            continue
        if riga.startswith("--- "):
            continue
        if not riga or riga[0] not in "+-":
            continue
        stato = "aggiunto" if riga[0] == "+" else "rimosso"
        if not _e_codice(file_corrente):
            continue
        corpo = riga[1:]
        for genere, regola in _REGOLE:
            m = regola.match(corpo)
            if not m:
                continue
            chiave = (m.group(1), file_corrente, stato)
            if chiave in visti:
                break
            visti.add(chiave)
            trovati.append(Simbolo(m.group(1), genere, file_corrente, stato))
            break
    return trovati


def _pathspec():
    """Chiedere a git il solo codice: uno sweep completo altrimenti trascina
    i PDF tracciati in docs/examples/ e li fa decodificare per niente."""
    return [f"*{e}" for e in sorted(ESTENSIONI_CODICE)]


def simboli_mossi(rev_range: str, cwd: str = ".") -> List[Simbolo]:
    """Come simboli_da_diff, ma prende il diff da git.

    Il diff e' letto in bytes e decodificato a mano con errors="replace": un
    repository che traccia binari (i PDF di docs/examples/) non deve far esplodere
    l'intero sweep con un UnicodeDecodeError. Il pathspec dopo "--" e' la cura vera:
    non chiede a git i binari, cosi' non c'e' nulla da decodificare per sbaglio.
    """
    diff = subprocess.run(
        ["git", "diff", "-U0", "-M", rev_range, "--", *_pathspec()],
        cwd=cwd, capture_output=True, check=True,
    ).stdout.decode("utf-8", errors="replace")
    return simboli_da_diff(diff)


# ── I COMMIT: la spina dorsale del giro ──
# Misurato sul giro 2026-09-18 (`1f09819..b9ca1a6`, 126 commit): delle 14 frasi
# false corrette, UNA sola era raggiungibile dalle citazioni per simbolo. Le
# altre 13 erano prosa che descrive una REGOLA e non nominava alcun simbolo
# mosso, quindi nessun join poteva pescarle — ne' `diff` ne' `--completo`, che
# usano la stessa chiave. Il messaggio di commit e' l'unico artefatto del repo
# scritto nella stessa lingua della prosa: dice che comportamento e' cambiato.
# Per questo la raccolta lo consegna sempre, e lo skill parte da li'.
LIMITE_CORPO_COMMIT = 600
TRONCATO = " […]"

# Separatori chiesti a git: NON possono comparire in un messaggio scritto a mano.
_SEP_RECORD = "\x1e"
_SEP_CAMPO = "\x1f"
_FORMATO_LOG = (_SEP_RECORD + "COMMIT" + _SEP_CAMPO + "%H" + _SEP_CAMPO + "%ad"
                + _SEP_CAMPO + "%s" + _SEP_CAMPO + "%b" + _SEP_RECORD)


@dataclass(frozen=True)
class Commit:
    """Un commit dell'intervallo, coi soli file di CODICE che ha toccato.

    `corpo` e' troncato a LIMITE_CORPO_COMMIT: serve a decidere SE quel commit
    cambia una regola, non a rileggerlo per intero.
    """
    sha: str
    data: str
    soggetto: str
    corpo: str
    file: List[str]


def commit_da_log(testo: str) -> List[Commit]:
    """I commit, letti dall'output di `git log` nel formato `_FORMATO_LOG`.

    Parte pura, testabile senza un repo: `commits_nell_intervallo` si limita a
    chiamare git e passare qui il testo — la stessa divisione di
    `simboli_da_diff`/`simboli_mossi`.
    """
    fuori = []
    for pezzo in testo.split(_SEP_RECORD + "COMMIT" + _SEP_CAMPO)[1:]:
        testa, _, coda = pezzo.partition(_SEP_RECORD)
        campi = testa.split(_SEP_CAMPO)
        if len(campi) < 4:
            continue
        sha, data, soggetto, corpo = campi[0], campi[1], campi[2], campi[3]
        corpo = corpo.strip()
        if len(corpo) > LIMITE_CORPO_COMMIT:
            corpo = corpo[:LIMITE_CORPO_COMMIT] + TRONCATO
        file = [r.strip() for r in coda.splitlines() if r.strip()]
        fuori.append(Commit(sha, data, soggetto.strip(), corpo,
                            [f for f in file if _e_codice(f)]))
    return fuori


def commits_nell_intervallo(rev_range: str, cwd: str = ".") -> List[Commit]:
    """Come commit_da_log, ma prende il log da git. `--no-merges`: un merge non
    cambia un comportamento, lo unisce."""
    log = subprocess.run(
        ["git", "log", "--no-merges", "--date=short", "--name-only",
         "--format=" + _FORMATO_LOG, rev_range, "--", *_pathspec()],
        cwd=cwd, capture_output=True, check=True,
    ).stdout.decode("utf-8", errors="replace")
    return commit_da_log(log)


@dataclass(frozen=True)
class Citazione:
    simbolo: str
    file: str
    riga: int
    testo: str


# I rapporti di riallineamento stanno essi stessi in docs/, quindi al giro dopo
# le loro citazioni rientrerebbero nel conteggio: misurato sul giro 2026-09-18,
# 49 citazioni fantasma e un simbolo spinto sopra SOGLIA_GENERICO solo per
# questo. Il corpus non deve contenere i verbali di chi lo ha misurato.
ESCLUSI_DAL_CORPUS = ("superpowers/allineamento/",)


def _markdown_da_radici(radici):
    """I file `.md` da leggere, in ordine deterministico, esclusi i rapporti.

    Una cartella e' scandita ricorsivamente; una radice che e' essa stessa un
    file `.md` (es. CLAUDE.md, che vive nella root e non e' una cartella) viene
    letta direttamente — altrimenti sparirebbe in silenzio da ogni
    riallineamento.
    """
    for radice in radici:
        base = Path(radice)
        if not base.exists():
            continue
        if base.is_file():
            candidati = [base] if base.suffix == ".md" else []
        else:
            candidati = sorted(base.rglob("*.md"))
        for md in candidati:
            percorso = str(md).replace("\\", "/")
            if any(esc in percorso for esc in ESCLUSI_DAL_CORPUS):
                continue
            yield md


def _righe_che_corrispondono(radici, per_nome, costruisci):
    """Il cuore condiviso dei due join: una passata sui documenti, N regex."""
    out = []
    for md in _markdown_da_radici(radici):
        try:
            righe = md.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for n, testo in enumerate(righe, start=1):
            for nome, regola in per_nome.items():
                if regola.search(testo):
                    out.append(costruisci(nome, str(md), n, testo))
    return out


_SEGNAPOSTO = re.compile(r"\{[^{}]*\}")


def _regex_simbolo(simbolo) -> "re.Pattern":
    """La regex con cui si cerca un simbolo nei documenti.

    Una ROTTA si confronta coi segnaposto normalizzati: il codice scrive
    `{company_id}`, `CLAUDE.md` scrive `{id}`, ed e' la stessa rotta —
    confrontarla alla lettera la fa risultare non documentata (misurato: 1 dei 2
    rilievi del giro 2026-09-18 era proprio questo falso). Tutto il resto resta
    un confronto per parola intera, com'era.
    """
    if simbolo.genere == "rotta":
        pezzi = [re.escape(p) for p in _SEGNAPOSTO.split(simbolo.nome)]
        return re.compile(r"\{[^{}/]*\}".join(pezzi))
    return re.compile(r"\b" + re.escape(simbolo.nome) + r"\b")


def documenti_che_nominano(simboli, radici) -> List[Citazione]:
    """Le righe di documentazione che nominano uno dei simboli mossi.

    E' questa fase a rendere il costo proporzionale al CAMBIAMENTO invece che al
    corpus: solo i documenti che nominano un simbolo mosso entrano in verifica.
    Il confine di parola (\\b) evita che `resolve` peschi `_resolve_ce_field`.

    **Limite da conoscere, misurato**: la chiave e' il NOME DEL SIMBOLO, quindi
    una frase di prosa che descrive una regola senza nominare alcun
    identificatore e' invisibile a questo join — e lo e' in entrambi i modi,
    perche' `--completo` usa la stessa chiave. Sul giro 2026-09-18, 13 frasi
    false su 14 erano di quella forma: per quelle servono i `commits` e il join
    sul percorso, qui sotto.
    """
    if not simboli:
        return []
    per_nome = {}
    for s in simboli:
        per_nome.setdefault(s.nome, _regex_simbolo(s))
    return _righe_che_corrispondono(
        radici, per_nome,
        lambda nome, file, n, testo: Citazione(nome, file, n, testo.strip()[:200]))


def documenti_che_nominano_file(file_toccati, radici) -> List[Citazione]:
    """La seconda chiave di join: il PERCORSO di un file di codice toccato.

    Misurato sul giro 2026-09-18: la chiave "nome di simbolo" non tocca
    `REGOLE-IMPORT-05-INFRANNUALE.md` — la pagina che descriveva la regola
    vecchia — mentre questa la prende con 4 righe. Non sostituisce l'altra, la
    affianca: 649 righe su 61 pagine vive nello stesso intervallo.

    `Citazione.simbolo` porta il basename del file, cosi' la riduzione dei
    generici e il formato del rapporto restano gli stessi dell'altro join.
    """
    per_nome = {}
    for f in file_toccati:
        if not _e_codice(f):
            continue
        base = f.split("/")[-1]
        per_nome.setdefault(base, re.compile(re.escape(base)))
    if not per_nome:
        return []
    return _righe_che_corrispondono(
        radici, per_nome,
        lambda nome, file, n, testo: Citazione(nome, file, n, testo.strip()[:200]))


# Le manopole pubbliche: stato PERSISTITO (una colonna) e superficie di CHIAMATA
# (una rotta). Nient'altro, e la ragione e' misurata sul giro 2026-09-18:
# allargare a `costante` e `tipo` porta la lista da 1 riga a 110, quasi tutte
# costanti di layout e tipi interni. Le funzioni restano fuori per lo stesso
# motivo — un helper privato non e' una manopola.
GENERI_MANOPOLA = ("colonna", "rotta")


def _e_test(percorso: str) -> bool:
    """Un simbolo dichiarato in un test non e' una manopola dell'applicazione."""
    base = percorso.split("/")[-1]
    return (percorso.startswith("tests/") or ".test." in base
            or base.startswith("test_") or "/__tests__/" in percorso)


def simboli_non_documentati(simboli, citazioni):
    """Le manopole NUOVE che nessun documento nomina.

    E' il rilievo piu' economico che questa raccolta possa produrre, e fino al
    2026-09-19 lo buttava via: `working_capital_mode` (una `Column` con schema
    `Literal` a tre valori, una tendina e due diagnostiche) e' entrato nel giro
    2026-09-18 con ZERO citazioni. Il simbolo veniva raccolto, il join non
    produceva nulla, e il nulla era indistinguibile da «allineato».

    Solo `stato == "aggiunto"`: un simbolo rimosso che nessuno nominava e'
    pulizia riuscita, non un buco.
    """
    citati = {c.simbolo for c in citazioni}
    fuori = []
    for s in simboli:
        if s.stato != "aggiunto" or s.genere not in GENERI_MANOPOLA:
            continue
        if s.nome.startswith("_") or s.nome in citati or _e_test(s.file):
            continue
        fuori.append({"nome": s.nome, "genere": s.genere, "file": s.file})
    fuori.sort(key=lambda d: (d["genere"], d["nome"]))
    return fuori


SOGLIA_GENERICO = 40


def riduci_generici(citazioni: List[Citazione]):
    """Separa i simboli troppo comuni per essere verificati per nome (>= SOGLIA_GENERICO
    citazioni) dal resto. Non e' un troncamento silenzioso: il simbolo esce da
    `citazioni` ed entra in `generici` con il proprio conteggio totale e i primi 5
    file in cui compare, cosi' lo skill puo' dire "troppo comune per essere verificato
    per nome" invece di sommergere le poche segnalazioni vere di un diff reale sotto
    centinaia di righe (misurato: 9 nomi generici -> 1147 citazioni in un colpo solo).
    """
    per_nome = {}
    for c in citazioni:
        per_nome.setdefault(c.simbolo, []).append(c)
    generici_nomi = {nome for nome, lst in per_nome.items() if len(lst) >= SOGLIA_GENERICO}
    if not generici_nomi:
        return citazioni, []
    ridotte = [c for c in citazioni if c.simbolo not in generici_nomi]
    generici = []
    for nome in sorted(generici_nomi):
        lst = per_nome[nome]
        file_visti = []
        for c in lst:
            if c.file not in file_visti:
                file_visti.append(c.file)
            if len(file_visti) >= 5:
                break
        generici.append({"nome": nome, "citazioni": len(lst), "file": file_visti})
    return ridotte, generici


RADICI_DOC = ["docs", "CLAUDE.md"]
RADICE_MEMORIA = str(
    Path.home() / ".claude" / "projects" / "-home-peter-DEV-budget" / "memory"
)
STATO_DEFAULT = "docs/superpowers/allineamento/STATO.json"


def carica_stato(percorso: str) -> dict:
    p = Path(percorso)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salva_stato(percorso: str, sha: str, modo: str, data: str) -> None:
    """Uno sweep completo aggiorna ultimo_sha come il modo diff (ha appena verificato
    tutto) e in piu' segna ultimo_completo, che i rapporti leggono per ricordare da
    quanto non si lancia una verifica integrale."""
    p = Path(percorso)
    p.parent.mkdir(parents=True, exist_ok=True)
    stato = carica_stato(percorso)
    stato["ultimo_sha"] = sha
    stato["modo"] = modo
    stato["data"] = data
    if modo == "completo":
        stato["ultimo_completo"] = data
    else:
        stato.setdefault("ultimo_completo", None)
    p.write_text(json.dumps(stato, ensure_ascii=False, indent=1) + "\n",
                 encoding="utf-8")


# L'albero vuoto di git: diffare da qui equivale a "tutto il codice attuale".
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--da", help="sha di partenza; default: ultimo_sha dello stato")
    ap.add_argument("--a", default="HEAD")
    ap.add_argument("--completo", action="store_true",
                    help="ignora l'intervallo: tutti i simboli del codice attuale")
    ap.add_argument("--stato", default=STATO_DEFAULT)
    ap.add_argument("--memoria", default=RADICE_MEMORIA)
    ap.add_argument("--registra", metavar="SHA",
                    help="registra l'esito nello stato e termina (non raccoglie nulla): "
                         "lo chiama lo skill DOPO aver verificato")
    ap.add_argument("--modo", default="diff", choices=["diff", "completo"],
                    help="modo con cui e' stata condotta la verifica che --registra salva")
    ap.add_argument("--ripresa-l3", default=None,
                    help="ultimo documento verificato PER INTERO al Livello 3")
    ap.add_argument("--data", default=None,
                    help="data ISO della registrazione (AAAA-MM-GG); default: oggi, "
                         "calcolata dallo script se lo skill non la passa esplicitamente")
    args = ap.parse_args()

    if args.registra:
        data = args.data or datetime.date.today().isoformat()
        salva_stato(args.stato, sha=args.registra, modo=args.modo, data=data)
        if args.ripresa_l3:
            stato = carica_stato(args.stato)
            stato["ripresa_l3"] = args.ripresa_l3
            Path(args.stato).write_text(
                json.dumps(stato, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return

    stato = carica_stato(args.stato)
    if args.completo:
        # Nessun intervallo, quindi nessun commit da leggere e nessun file
        # "toccato": le due chiavi nuove non hanno senso qui e restano vuote,
        # dichiarate — mai omesse, o a valle l'assenza si legge come zero.
        simboli = simboli_mossi(_EMPTY_TREE + ".." + args.a)
        intervallo = "completo"
        commits, file_toccati = [], []
    else:
        da = args.da or stato.get("ultimo_sha")
        if not da:
            ap.error("nessuno sha di partenza: passa --da la prima volta")
        intervallo = f"{da}..{args.a}"
        simboli = simboli_mossi(intervallo)
        commits = commits_nell_intervallo(intervallo)
        file_toccati = sorted({f for c in commits for f in c.file})

    radici = RADICI_DOC + [args.memoria]
    citazioni = documenti_che_nominano(simboli, radici)
    non_documentati = simboli_non_documentati(simboli, citazioni)
    citazioni, generici = riduci_generici(citazioni)
    citazioni_file, generici_file = riduci_generici(
        documenti_che_nominano_file(file_toccati, radici))
    print(json.dumps({
        "intervallo": intervallo,
        "sha_verificato": subprocess.run(["git", "rev-parse", args.a],
                                         capture_output=True, text=True).stdout.strip(),
        "commits": [asdict(c) for c in commits],
        "simboli": [asdict(s) for s in simboli],
        "citazioni": [asdict(c) for c in citazioni],
        "generici": generici,
        "non_documentati": non_documentati,
        "citazioni_file": [asdict(c) for c in citazioni_file],
        "generici_file": generici_file,
        "radici": radici,
        "esclusi_dal_corpus": list(ESCLUSI_DAL_CORPUS),
        "stato": stato,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
