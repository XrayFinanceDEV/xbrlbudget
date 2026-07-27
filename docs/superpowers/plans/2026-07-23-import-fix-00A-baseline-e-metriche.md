# Piano 00A — Fondazione di test: probe, baseline versionata, metriche per spazio

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans oppure
> superpowers:subagent-driven-development. Steps con checkbox (`- [ ]`).
> **Questo piano va eseguito PER PRIMO.** Senza di esso nessun altro piano ha un gate di regressione
> reale: `Test/` è gitignorato, i valori pre-fix non sono versionati, e le route A/B sono
> LLM-non-deterministiche (SI/NO può flippare fra due run sullo stesso file senza che nulla sia cambiato).

**Goal:** poter dimostrare, in modo riproducibile e senza crediti LLM, che un fix migliora qualcosa e non
rompe nient'altro.

**Perché serve.** Il Quadro §8.4 lo dice: il "gate di regressione" descritto nei piani è una checklist
manuale per chi ha il corpus in locale. Non gira in CI, non è riproducibile da un secondo sviluppatore, e
non distingue una regressione dal rumore LLM. In più — punto centrale — **la quadratura non è una prova di
correttezza**: un bilancio può avere sbilancio 0 ed essere classificato male (massa nel campo sbagliato,
fondi non nettati, debiti tutti in "altri"). Serve confrontare i **campi**, non solo i totali.

**Tech stack:** Python, pytest, SQLite in-memory. Nessun LLM per i Task 1 e 3.

## Vincoli globali
Quadro generale §7. In più: **nessun PDF del corpus entra nel repo**. Nella baseline entrano solo numeri,
hash e nomi di file — non sono dati sensibili.

---

### Task 1: correggere `tests/_import_probe.py` — FATTO (2026-07-27)

Difetti trovati e corretti nel ramo `ocr` (mai eseguito finora perché Docker era spento, quindi invisibile):
- `from importers.mineru_adapter import to_extraction_context` → **la funzione non esiste**; quella reale è
  `build_extraction_context` (`importers/mineru_adapter.py:240`);
- `MinerUClient()` → `__init__` è **keyword-only e richiede `base_url`**;
- `client.parse(...)` → il metodo reale è **`parse_pdf(*, content, filename)` ed è `async`**, e va preceduto
  da `await client.health()`.

- [x] Corretto: `_mineru_context` costruisce il client con `base_url` (override via `MINERU_BASE_URL`),
  chiama `health()` + `parse_pdf()` dentro `asyncio.run`, e passa il risultato a `build_extraction_context`.

- [ ] **Step 1: verificare** che il ramo `standard` sia intatto e che il ramo `ocr` fallisca **con un
messaggio onesto** quando MinerU non c'è (non con un `ImportError`):

```bash
python tests/_import_probe.py "Test/june_sample/success/budget_353_Bilancio 31.12.25.pdf" standard
python tests/_import_probe.py "Test/june_sample/success/budget_353_Bilancio 31.12.25.pdf" ocr
# atteso ocr: "MINERU_UNAVAILABLE: ..." (non un ImportError / AttributeError)
```

---

### Task 2: la probe registra TUTTI i campi, non solo i totali

**Files:**
- Modify: `tests/_import_probe.py`

**Interfaces:**
- Produces: record JSONL con, in aggiunta a quelli attuali: `sha256` del file, `route`/`macro_area`/
  `macro_subcategory`, `extraction_method` (provenienza: `deterministico` / `coge-llm` / `ivcee-llm` /
  `mineru+…`), **tutti** i campi `sp*` e `ce*` non nulli come **stringhe Decimal** (mai float),
  `validation_status`, `warnings`, `plug_residual`, `netted_contra`, `prior_year_imported`.

**Perché Decimal come stringa.** I confronti di baseline su float producono falsi diff da arrotondamento;
e il repo impone Decimal ovunque per gli importi (Quadro §7).

- [ ] **Step 1: test che fallisce**

```python
# tests/test_import_probe_record.py
import json, subprocess, sys, os

def test_record_contiene_i_campi_necessari_alla_baseline(tmp_path):
    """La probe deve registrare abbastanza da poter dire 'questo import e' cambiato',
    non solo 'quadra ancora'. Un bilancio puo' quadrare ed essere classificato male."""
    from tests._import_probe import probe   # import diretto, niente subprocess
    rec = probe(os.environ["PROBE_SAMPLE_PDF"], "standard")
    for k in ("file", "sha256", "method", "ok", "macro_area", "macro_subcategory",
              "extraction_method", "validation_status", "totale_attivo", "sbilancio",
              "masked", "warnings", "fields"):
        assert k in rec, k
    if rec["ok"]:
        assert isinstance(rec["fields"], dict) and rec["fields"]
        # importi come STRINGHE Decimal, mai float
        assert all(isinstance(v, str) for v in rec["fields"].values())
```

Il test è gated su `PROBE_SAMPLE_PDF` (skip se non impostata) perché il corpus non è nel repo.

- [ ] **Step 2: verificare che fallisca.**
- [ ] **Step 3: implementare** in `tests/_import_probe.py`: aggiungere `sha256`, `extraction_method`,
  `fields` (`{nome_colonna: str(Decimal)}` per ogni `sp*`/`ce*` non nullo, letti dal DB in-memory),
  `plug_residual` e `netted_contra` se presenti nel `validation_report`.
- [ ] **Step 4: verificare** — `PROBE_SAMPLE_PDF="Test/june_sample/success/budget_353_Bilancio 31.12.25.pdf" python -m pytest tests/test_import_probe_record.py -q`
- [ ] **Step 5: Commit** — `git commit -m "test(probe): il record registra tutti i campi sp/ce come Decimal + provenienza"`

---

### Task 3: baseline versionata + test di confronto

**Files:**
- Create: `tests/fixtures/import_baseline.json`
- Create: `tests/test_import_baseline.py`
- Create: `scripts/refresh_import_baseline.py`

**Interfaces:**
- `import_baseline.json` = `{ "<sha256>": {"file": ..., "expected": {…record…}, "verified": bool,
  "verified_note": "…"} }`. La chiave è l'**hash del documento**, non il nome (i file del corpus vengono
  rinominati e duplicati fra cartelle).

**Distinzione obbligatoria — `verified`.** Sono due cose diverse:
- `verified: false` → "questo è ciò che il software produce OGGI": serve solo a intercettare **cambi**
  (regressioni o miglioramenti), non dice che il numero sia giusto;
- `verified: true` → "questo è il numero **letto sulla fonte** da un umano": è un'asserzione di
  correttezza, e va accompagnata da `verified_note` (es. "TOTALE A PAREGGIO stampato a pag. 4").

Il test tratta i due casi diversamente: un cambio su `verified: true` è **sempre** un fallimento; un
cambio su `verified: false` è un fallimento che il commit può accettare **aggiornando esplicitamente** la
baseline, con la motivazione nel messaggio di commit.

- [ ] **Step 1: test che fallisce**

```python
# tests/test_import_baseline.py
import json, os
import pytest

BASELINE = os.path.join(os.path.dirname(__file__), "fixtures", "import_baseline.json")
CORPUS = os.environ.get("IMPORT_CORPUS_ROOT")      # es. "Test"


def _load():
    with open(BASELINE, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.skipif(not CORPUS, reason="corpus locale assente (Test/ e' gitignorato)")
def test_nessuna_regressione_sui_file_di_baseline():
    from tests._import_probe import probe, sha256_of
    import glob
    base = _load()
    by_hash = {}
    for p in glob.glob(os.path.join(CORPUS, "**", "*.pdf"), recursive=True):
        by_hash.setdefault(sha256_of(p), p)

    diffs = []
    for h, entry in base.items():
        p = by_hash.get(h)
        if p is None:
            continue                                    # file non presente in locale: skip
        got = probe(p, "standard")
        exp = entry["expected"]
        for k in ("ok", "macro_area", "totale_attivo", "sbilancio", "masked"):
            if str(got.get(k)) != str(exp.get(k)):
                diffs.append((entry["file"], k, exp.get(k), got.get(k), entry.get("verified")))
        for f, v in (exp.get("fields") or {}).items():
            if str((got.get("fields") or {}).get(f)) != str(v):
                diffs.append((entry["file"], f, v, (got.get("fields") or {}).get(f),
                              entry.get("verified")))
    hard = [d for d in diffs if d[4]]                   # su 'verified' non si negozia
    assert not hard, f"REGRESSIONE su valori verificati: {hard}"
    assert not diffs, ("differenze rispetto alla baseline non verificata "
                       f"(aggiornarla esplicitamente se attese): {diffs}")
```

- [ ] **Step 2: verificare che fallisca** (`tests/fixtures/import_baseline.json` non esiste).

- [ ] **Step 3: implementare.**
  (a) `sha256_of(path)` in `tests/_import_probe.py`.
  (b) `scripts/refresh_import_baseline.py`: gira la probe su una cartella e **fonde** il risultato nella
  baseline **senza mai sovrascrivere le entry `verified: true`** (quelle si aggiornano solo a mano).
  (c) Generare la baseline iniziale sulle cartelle disponibili, tutte a `verified: false`:
  ```bash
  python scripts/refresh_import_baseline.py Test/successSecondo Test/june_sample/success Test/june_sample/errori
  ```
  ⚠️ **Con i crediti esauriti** la baseline conterrebbe fallimenti spuri `credit balance is too low`:
  `refresh_import_baseline.py` deve **scartare** i record il cui errore contiene `credit balance` e non
  scriverli affatto (mai congelare un errore d'ambiente come comportamento atteso).
  (d) Promuovere a `verified: true` **almeno i 18 file "problema software"** dell'audit, leggendo il
  totale a pareggio / l'utile stampati sul PDF e annotandoli in `verified_note`. È lavoro manuale e va
  fatto: è l'unica cosa che trasforma i piani da "il numero è cambiato" a "il numero è giusto".

- [ ] **Step 4: verificare** — `IMPORT_CORPUS_ROOT=Test python -m pytest tests/test_import_baseline.py -q`
- [ ] **Step 5: Commit** — `git commit -m "test: baseline versionata degli import (hash-keyed, verified vs osservato)"`

---

### Task 4: metriche di copertura per spazio semantico

**Files:**
- Modify: `tests/_label_coverage.py`

**Perché.** La misura attuale (58,3% di righe non risolte, 56,5% della massa) **è sovrastimata e non è un
target valido**: mescola in un unico denominatore voci civilistiche, conti del piano dei conti,
intestazioni di colonna, marcatori e totali, e interroga solo il vecchio `resolve` — che per progetto
copre **solo** le voci legali. Non si può accettare o rifiutare il Piano 05 su quel numero.

- [ ] **Step 1:** classificare ogni riga misurata in uno dei quattro insiemi **prima** di interrogare il
resolver, con euristiche dichiarate nel codice:
  - `legal` — la riga porta un path civilistico (`B.II.1.a`, `C.II.5 quater`) o una voce di legge;
  - `account` — la riga porta un codice di conto (DEPI `XX/YY/ZZZ`, 8-digit, dotted, TeamSystem…);
  - `marker` — totali/sezioni/intestazioni (`TOTALE …`, `A T T I V I T A'`, `Differenza`, `Scost.`);
  - `other` — prosa di nota integrativa, righe di intestazione documento (**da escludere dal
    denominatore**: oggi inquinano la misura, es. «i ricavi caratteristici crescono di circa il 18%»).

- [ ] **Step 2:** riportare **tre** coperture separate (`legal`, `account`, `marker`), ciascuna su righe e
su massa, e interrogare per ognuna lo spazio corretto del motore semantico (Piano 05).

- [ ] **Step 3:** ri-misurare la baseline attuale e **scriverla nel Piano 05** come punto di partenza dei
tre target (uno per spazio). Il vecchio target unico `< 30%` va cancellato.

- [ ] **Step 4: Commit** — `git commit -m "test: copertura etichette misurata per spazio semantico (legal/account/marker)"`

---

## Accettazione del piano

- `tests/_import_probe.py` funziona su entrambi i metodi e fallisce onestamente quando MinerU è assente.
- `tests/fixtures/import_baseline.json` esiste, è hash-keyed, distingue `verified` da osservato, e non
  contiene alcun record inquinato da errori d'ambiente (crediti/rete).
- `tests/test_import_baseline.py` passa in locale e **skippa** dove il corpus non c'è (quindi non rompe CI).
- Le coperture sono riportate per i tre spazi, con denominatori dichiarati.
- Almeno i 18 file "problema software" hanno un valore atteso **verificato sulla fonte**.
