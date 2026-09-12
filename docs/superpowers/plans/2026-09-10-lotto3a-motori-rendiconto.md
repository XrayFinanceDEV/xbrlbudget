# Lotto 3A — motori del previsionale e rendiconto — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il motore budget e quello infrannuale smettono di dare numeri sbagliati su sweep, debito bancario, imposte, magazzino e cassa negativa; il rendiconto conta i dividendi; il bulk rifiuta l'input invalido prima di scrivere; i messaggi nascono in italiano.

**Architecture:** Le regole del debito bancario (divisione del contratto misto, separazione pregresso/nuovo, quota a breve) e quelle sugli acconti e sulla soglia del magazzino passano in `calculations/projection_common.py`, usate da entrambi i motori. Lo sweep diventa un oggetto `_Sweep` che `_normalize_balance_sheet_cents` applica sulla cassa gia' al centesimo e dopo gli `sp_overrides`, accanto al cancello unico dello scoperto; `details['debito_bancario']` dichiara le componenti riconciliate col persistito. Il bulk valida ogni riga con lo schema Pydantic prima di cancellare o scrivere e risponde 422 con un elenco italiano per campo.

**Tech Stack:** Python 3 + SQLAlchemy + FastAPI + Pydantic 2.10.4 (motori in `calculations/`, servizi in `backend/app/services/`), Next.js 15 + TypeScript + Vitest (`environment: node`), SQLite in memoria nei test, banco di parita' `scripts/parita_motore.py`.

**Spec:** `docs/superpowers/specs/2026-09-10-lotto3a-motori-rendiconto-design.md` (vincolante; §4.1-§4.9, ordine in §5).

**Branch di esecuzione:** `feat/lotto3a-motori`, da staccare dal branch integrato del lotto 2 (`feat/scadenziamento-pregresso`) **dopo** la sua revisione finale e dopo il suo giro finale di correzione su `forecast_engine.py` (riallineamento di `details['imposte']` dopo gli override, rifiuto di un override sul lato lungo di un saldo con piano attivo, residuo di `sp16`/`sp17` solo su `d-g`). Ogni task gira in un worktree Orca figlio di `feat/lotto3a-motori`.

**Materiale:** `.superpowers/sdd/2026-09-08-scadenziamento-pregresso/lotto3-ricognizione.md`, `lotto3-codice.md`, `final-review.md` (I2). I numeri attesi dei test sono stati misurati con sonde sullo snapshot `452112d` (codice identico all'HEAD della spec); lo scarto dalla spec e' in «Numeri ricontrollati», in coda.

## Global Constraints

Copiati alla lettera dalla spec §3:

- Soldi in `Decimal`; percentuali assolute. Un divario si misura e si dichiara, mai si tappa.
- **Dichiarato = persistito:** ogni valore che il motore dichiara in `details` è quello che finisce nel DB, al centesimo.
- **Il banco di parità è lo strumento di misura del lotto** (`scripts/parita_motore.py`, `--controllo-negativo`). Ogni
  task dichiara prima quali celle devono muoversi e in quali scenari; il merge verifica che si muovano solo quelle. Se
  nessun profilo del banco esercita il caso del task, il task aggiunge prima il profilo, in un commit separato che dà 0
  divergenze sul motore invariato.
- Una prova rossa vale solo se fallisce sulle **asserzioni**, non su un simbolo mancante.
- `CLAUDE.md` e `docs/budget/API-PREVISIONALE.md` si aggiornano **nello stesso commit** del comportamento che
  descrivono; ogni `file:riga` scritto si apre e si controlla.
- Terminatori CRLF da preservare: `frontend/types/api.ts`, `backend/app/services/analysis_service.py`,
  `backend/app/calculations/cashflow.py`, `backend/app/calculations/cashflow_detailed.py`,
  `docs/budget/FORECASTING_GUIDE.md`.
- **Esecutore pi, revisore Claude** (decisione del proprietario, 2026-09-10): pi (LLM locale via orchestrazione Orca)
  implementa ogni task, motore compreso; la revisione e' di Claude, opus sui task del motore e sonnet sugli altri.
- **Ordine di integrazione col lotto gemello.** Il piano 3B (`feat/lotto3b-client`) tocca `CLAUDE.md` in «Invarianti
  e trappole › Frontend»; questo piano lo tocca nei Task 2, 4, 5, 7a, 8, 10, 11, 12, nelle sezioni «Forecasting
  Engine», «Intra-Year Engine» e «Invarianti e trappole › Previsionale» — testualmente disgiunte da quella del 3B, ma
  nessuno dei due branch lo sa finche' qualcuno non li unisce. **Il 3B, piu' piccolo, si integra per primo**: il
  Task 13 di questo lotto, prima della sua verifica di fine lotto, unisce nel proprio branch quello dove il 3B e'
  confluito e rilegge le sezioni di `CLAUDE.md` toccate da entrambi — non basta `/riallinea` sul solo diff del 3A.

## Convenzioni di esecuzione (ripetute dentro ogni task che le usa)

Ogni task e' la specifica di un worker Orca: pi vede **solo** il testo del proprio task. Per questo ogni task
ripete percorsi, comandi e trappole che gli servono, invece di rimandare a un altro task. Le regole comuni:

- **Radice.** Tutti i comandi partono dalla radice del worktree Orca del task. Python sempre col percorso
  assoluto: `/home/peter/DEV/budget/backend/venv/bin/python`.
- **Test Python.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest <file> -q -p no:cacheprovider`.
- **Frontend.** Una volta per worktree: `test -e frontend/node_modules || ln -s /home/peter/DEV/budget/frontend/node_modules frontend/node_modules`.
  Poi `cd frontend && npx vitest run lib/<nome>.test.ts` e `cd frontend && npx tsc --noEmit`.
- **Base del task.** Primo passo di ogni task: `git rev-parse HEAD > /tmp/lotto3a-taskN-base` (N = numero del task).
- **Banco.** `/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/lotto3a-taskN-base)" --anni 4 --controllo-negativo --json /tmp/lotto3a-taskN-parita.json --log /tmp/lotto3a-taskN-parita.log`
  (seconda versione omessa = albero di lavoro, prima del commit). Codici d'uscita: 0 nessuna divergenza, 1
  divergenze, 3 controllo negativo fallito (banco da riparare: fermarsi e riferire). Poi, dal Task 1 in avanti,
  `/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_riepilogo.py /tmp/lotto3a-taskN-parita.json --attese <pattern…>`:
  esce 1 ed elenca ogni divergenza che nessun pattern ammette.
- **Git.** Mai `git checkout`, `git stash`, `git reset --hard`, `git add -A`, `git add .`. Un solo commit per task,
  `git add` dei file per nome.
- **Terminatori.** Prima di toccare un file: `file <percorso>`. File interamente CRLF (i cinque dei Global Constraints,
  piu' `backend/app/services/assumptions_service.py`, `backend/app/schemas/budget.py`,
  `backend/app/schemas/cashflow_detailed.py`): dopo la modifica si riportano a CRLF con
  `/home/peter/DEV/budget/backend/venv/bin/python -c "import sys;p=sys.argv[1];b=open(p,'rb').read().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n');open(p,'wb').write(b)" <percorso>`.
  File a terminatori misti (`calculations/intra_year_engine.py`, `backend/app/api/v1/budget_scenarios.py`,
  `backend/app/services/promote_service.py`): **mai** normalizzarli; le righe nuove copiano il terminatore delle vicine.
  In ogni caso, prima del commit, `git diff --stat` deve contare solo le righe davvero cambiate (un file intero
  riscritto e' un difetto da correggere prima del commit).
- **Rapporto.** `/home/peter/DEV/budget/.superpowers/sdd/2026-09-10-lotto3a-motori-rendiconto/task-N-report.md`
  (creare la cartella se manca), con: prova rossa (comando e fallimento, righe salienti), prova verde (comando ed
  esito), banco (comando, uscita, divergenze osservate contro attese, esito del riepilogo), `git diff --stat`, e ogni
  scarto dai numeri del task con la sua spiegazione.
- **Codice che cambia sotto i piedi.** I numeri di riga di questo piano sono dello snapshot `452112d`: si cercano i
  **simboli**. Il giro finale del lotto 2 riscrive parti di `compute_forecast`, `_apply_sp_overrides` e
  `_normalize_balance_sheet_cents`: chi tocca quelle funzioni le rilegge sul branch del lotto 3A prima di cambiarle.
- **Un test esistente che diventa rosso** si corregge solo se il task lo nomina. Altrimenti ci si ferma e lo si
  riferisce nel rapporto: e' quasi sempre un difetto del codice nuovo, non del test.

## Ondate

```
Ondata A (serie, motore budget):   T1 → T2 → T3
Ondata B (parallela):              T4 → T5 (infrannuale, in serie)   ‖   T6 (rendiconto; parte insieme a T3)
Ondata C (serie):                  T7a → T7b → T8
Ondata D:                          T9 → T10   ‖   T11   (T11 dopo T4-T5; se in parallelo a T10, merge di T11 dopo T10:
                                                          stesso file intra_year_engine.py, funzioni diverse)
Ondata E (da sola):                T12
Ondata F:                          T13 (verifica di lotto)
```

| Task | Voce spec | Esecutore | Revisore |
|---|---|---|---|
| 1 | §3 banco — profili dello sweep | pi (Orca) | sonnet |
| 2 | §4.1 sweep, override, `details['debito_bancario']` | pi (Orca) | opus |
| 3 | §4.2 refactor sulle funzioni condivise (0 divergenze) | pi (Orca) | opus |
| 4 | §4.2 infrannuale sul codice condiviso | pi (Orca) | opus |
| 5 | §4.3 infrannuale, imposte al 31/12 | pi (Orca) | opus |
| 6 | §4.4 rendiconto | pi (Orca) | sonnet |
| 7a | §4.5 bulk tipizzato, backend (schema, validazione, 422) | pi (Orca) | sonnet |
| 7b | §4.5 bulk tipizzato, frontend (wizard e Startup mostrano l'elenco) | pi (Orca) | sonnet |
| 8 | §4.6 messaggi in italiano | pi (Orca) | sonnet |
| 9 | §3 banco — fixture di settore con magazzino lungo | pi (Orca) | sonnet |
| 10 | §4.8 guardia del magazzino per settore | pi (Orca) | opus |
| 11 | §4.9 §11.1 sull'infrannuale | pi (Orca) | opus |
| 12 | §4.7 centesimi su voci neutre | pi (Orca) | opus |
| 13 | §6 verifica di lotto | pi (Orca) + collaudatore + coordinatore | sonnet |

## File map

- `scripts/parita_motore.py` — profili dello sweep (T1), fixture di settore e settore nel driver (T9).
- `scripts/parita_riepilogo.py` (nuovo, T1).
- `calculations/forecast_engine.py` — `_Sweep`, `_DebitoBancarioAnno`, `_q2`, `_residuo_contratto`,
  `_contratti_dell_anno`, `_dichiara_debito_bancario`, `_quota_breve_dichiarata` (T2); alias verso le funzioni
  condivise (T3); messaggi (T8); soglia del magazzino (T10); tabella dei campi neutri (T12).
- `calculations/projection_common.py` — `e_contratto_pregresso`, `contratti_da_riga_finanziamento`,
  `residuo_prestiti_nuovi`, `quota_breve_prestiti_nuovi`, `separa_prestiti_nuovi` (T3); `acconti_dovuti`,
  `PosizioneTributariaFineAnno`, `posizione_tributaria_fine_anno`, rimozione di `tax_closing_position` (T5);
  `eur_it` (T8); `soglia_giorni_magazzino` (T10).
- `calculations/intra_year_engine.py` — `_financing_contracts`, `_apply_debt_repayment` (T4); posizione tributaria
  (T5); messaggi (T8); `_turnover_ratio`, `_scaled_or_carried`, `generate_projection` (T10, T11).
- `backend/app/calculations/cashflow_detailed.py`, `backend/app/schemas/cashflow_detailed.py`, `frontend/types/api.ts` (T6).
- `backend/app/schemas/budget.py`, `backend/app/services/assumptions_service.py`,
  `backend/app/api/v1/budget_scenarios.py` (T7a); `frontend/lib/budget-bulk-errors.ts` (nuovo),
  `frontend/components/budget/wizard/BudgetWizard.tsx`, `frontend/app/budget/page.tsx` (T7b).
- Messaggi: `backend/app/services/{assumptions_service,forecast_preview_service,promote_service}.py`,
  `backend/app/api/v1/budget_scenarios.py`, `frontend/lib/{budget-preview-notice,budget-preview-rows,budget-wizard-steps}.ts` (T8).
- Test nuovi: `tests/test_parita_riepilogo.py` (T1), `tests/test_forecast_sweep_piani.py` (T2),
  `tests/test_projection_common_debito_bancario.py` (T3), `tests/test_intra_year_debito_bancario.py` (T4),
  `tests/test_intra_year_imposte.py` (T5), `tests/test_cashflow_dividendi.py` (T6), `tests/test_bulk_tipizzato.py`
  (T7a) e `frontend/lib/budget-bulk-errors.test.ts` (T7b), `tests/test_forecast_magazzino_settore.py` (T10),
  `tests/test_intra_year_override_cassa.py` (T11), `tests/test_forecast_residuo_neutro.py` (T12).
- Documenti: `CLAUDE.md`, `docs/budget/API-PREVISIONALE.md`, `docs/budget/FORECASTING_GUIDE.md` (CRLF),
  `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md`.

---

## Ondata A — motore budget

### Task 1: Il banco esercita lo sweep con e senza piano (commit a 0 divergenze)

**Esecutore:** pi (Orca) · **Revisore:** sonnet · **Ondata:** A, primo

**Target.** Il banco di parita' `scripts/parita_motore.py` oggi accende il cash sweep solo nel profilo `finanziamento`,
sempre con un prestito nuovo. Nessun profilo combina lo sweep con il debito bancario pregresso senza piano, con gli
anni di rimborso, con i contratti col residuo iniziale o con un `sp_overrides`. Il Task 2 cambia proprio quei casi:
senza profili il banco non vedrebbe nulla. Serve anche uno strumento che dica quali divergenze sono fuori dalle attese.

**Change.**
1. In `scripts/parita_motore.py` aggiungi **in coda** a `PROFILI` (dopo `"pregresso"`) quattro profili, e le loro
   funzioni subito prima del dizionario `PROFILI`:

```python
def profilo_sweep_senza_piano(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Cash sweep sul solo debito bancario pregresso SENZA piano (lotto 3A, Task 1).

    Sui fixture del kit il pregresso senza piano e' il `sp17a` di 50.000; su `banca` anche
    il breve. Nessun prestito: e' il perimetro che lo sweep conserva anche dopo il Task 2.
    """
    return {"cash_sweep_enabled": True, "cash_sweep_min_cash": _eur(rng, 5000, 40000)}


def profilo_sweep_anni_rimborso(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Cash sweep con il pregresso su un piano di anni di rimborso: dal Task 2 lo sweep non lo tocca."""
    return {
        "cash_sweep_enabled": True,
        "cash_sweep_min_cash": _eur(rng, 5000, 40000),
        "existing_debt_repayment_years": _anni_frazionari(rng, 2, 5),
    }


def profilo_sweep_contratti(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Il contratto misto di `profilo_finanziamento_misto` con il cash sweep acceso ogni anno.

    `costruisci_griglia` riempie i due `opening_residual` anche per questo profilo, col debito
    bancario reale del fixture: senza, `assemble_financing` rifiuterebbe lo scenario.
    """
    valori = profilo_finanziamento_misto(rng, anno_idx)
    valori.update({"cash_sweep_enabled": True, "cash_sweep_min_cash": _eur(rng, 5000, 40000)})
    return valori


def profilo_sweep_override(rng: random.Random, anno_idx: int) -> Dict[str, Any]:
    """Il caso I2 della revisione finale del lotto 2: un `sp_overrides` su un attivo nel primo anno,
    lo sweep acceso e lo scoperto concesso. Fino al Task 2 lo sweep decide sulla cassa di PRIMA
    dell'override e apre uno scoperto per pagare un rimborso anticipato."""
    valori: Dict[str, Any] = {"cash_sweep_enabled": True, "cash_sweep_min_cash": _eur(rng, 5000, 20000)}
    if anno_idx == 0:
        valori["sp_overrides"] = {"sp08_attivita_finanziarie": _eur(rng, 60000, 120000)}
        valori["overdraft_allowed"] = True
    return valori
```

```python
    "pregresso": profilo_pregresso,
    "sweep_senza_piano": profilo_sweep_senza_piano,
    "sweep_anni_rimborso": profilo_sweep_anni_rimborso,
    "sweep_contratti": profilo_sweep_contratti,
    "sweep_override": profilo_sweep_override,
}
```

2. In `costruisci_griglia` sostituisci la condizione `if profilo_nome == "finanziamento_misto" and i == 0:` con
   `if profilo_nome in ("finanziamento_misto", "sweep_contratti") and i == 0:` (il blocco sotto resta identico).
3. Crea `scripts/parita_riepilogo.py`:

```python
#!/usr/bin/env python3
"""Riepilogo delle divergenze del banco di parita' (`scripts/parita_motore.py --json`).

Perche' esiste (lotto 3A, Task 1). Ogni task del lotto dichiara PRIMA quali celle del banco
devono muoversi e in quali scenari. Questo script raggruppa le divergenze per profilo e campo e,
con `--attese`, elenca quelle che nessun pattern ammette. Un pattern e' `fnmatch` su
`<scenario>|<campo>`: lo scenario e' `<fixture>__<profilo>`, il campo e' quello del banco
(`balance_sheet.sp09_disponibilita_liquide`, `details.debito_bancario`, `@errore`, `@anno`).

Uso:
    backend/venv/bin/python scripts/parita_riepilogo.py /tmp/parita.json
    backend/venv/bin/python scripts/parita_riepilogo.py /tmp/parita.json \\
        --attese '*__finanziamento|balance_sheet.sp17a_*' '*|details.debito_bancario'

Uscita: 0 se nessuna divergenza e' fuori dalle attese (o se `--attese` manca), 1 altrimenti.
"""
import argparse
import fnmatch
import json
import sys
from collections import Counter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("json", help="il file scritto da parita_motore.py --json")
    parser.add_argument("--attese", nargs="*", default=None,
                        help="pattern fnmatch '<fixture>__<profilo>|<campo>' delle divergenze ammesse")
    argomenti = parser.parse_args()
    with open(argomenti.json, encoding="utf-8") as fh:
        dati = json.load(fh)
    divergenze = dati.get("divergenze") or []
    gruppi: Counter = Counter()
    fuori = []
    for d in divergenze:
        profilo = d["scenario"].partition("__")[2] or d["scenario"]
        gruppi[(profilo, d["campo"])] += 1
        chiave = f"{d['scenario']}|{d['campo']}"
        if argomenti.attese is not None and not any(fnmatch.fnmatchcase(chiave, p) for p in argomenti.attese):
            fuori.append(d)
    for (profilo, campo), n in sorted(gruppi.items()):
        print(f"{n:5d}  {profilo:28s} {campo}")
    print(f"totale divergenze: {len(divergenze)}; controllo negativo: {dati.get('controllo_negativo')}")
    if argomenti.attese is None:
        return 0
    print(f"fuori dalle attese: {len(fuori)}")
    for d in fuori[:60]:
        print(f"  [{d['scenario']} · {d['anno']}] {d['campo']}: {d['valore_a']} -> {d['valore_b']}")
    return 1 if fuori else 0


if __name__ == "__main__":
    sys.exit(main())
```

**Constraints.** I profili nuovi vanno **in coda**: ogni fixture ha un proprio generatore consumato profilo dopo
profilo, quindi un profilo in mezzo cambierebbe le estrazioni dei successivi (misurato: con i quattro in coda i 77
scenari di prima restano identici). Nessuna modifica al motore. Nessun `git checkout`.

**Ownership.** `scripts/parita_motore.py`, `scripts/parita_riepilogo.py` (nuovo), `tests/test_parita_riepilogo.py` (nuovo).

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task1-base`
- [ ] **Step 2: Test del riepilogo**, `tests/test_parita_riepilogo.py`:

```python
"""Il riepilogo del banco di parita' raggruppa e filtra le divergenze (lotto 3A, Task 1)."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "parita_riepilogo.py"

DIVERGENZE = [
    {"scenario": "base__finanziamento", "anno": 2028, "campo": "balance_sheet.sp17a_debiti_banche_lungo",
     "valore_a": "0,00", "valore_b": "10,00"},
    {"scenario": "banca__finanziamento", "anno": 2028, "campo": "balance_sheet.sp17a_debiti_banche_lungo",
     "valore_a": "1,00", "valore_b": "2,00"},
    {"scenario": "base__crescita", "anno": 2027, "campo": "income_statement.ce15_oneri_finanziari",
     "valore_a": "1,00", "valore_b": "2,00"},
]


def _json(tmp_path):
    percorso = tmp_path / "parita.json"
    percorso.write_text(json.dumps({"divergenze": DIVERGENZE, "controllo_negativo": True}), encoding="utf-8")
    return str(percorso)


def _esegui(*argomenti):
    return subprocess.run([sys.executable, str(SCRIPT), *argomenti], capture_output=True, text=True)


def test_senza_attese_raggruppa_ed_esce_zero(tmp_path):
    esito = _esegui(_json(tmp_path))
    assert esito.returncode == 0, esito.stderr
    assert "    2  finanziamento" in esito.stdout
    assert "totale divergenze: 3" in esito.stdout


def test_una_divergenza_fuori_dalle_attese_esce_uno_e_la_nomina(tmp_path):
    esito = _esegui(_json(tmp_path), "--attese", "*__finanziamento|balance_sheet.sp17a_*")
    assert esito.returncode == 1, esito.stdout
    assert "fuori dalle attese: 1" in esito.stdout
    assert "[base__crescita · 2027] income_statement.ce15_oneri_finanziari" in esito.stdout


def test_tutte_nelle_attese_esce_zero(tmp_path):
    esito = _esegui(_json(tmp_path), "--attese", "*__finanziamento|balance_sheet.*", "*|income_statement.ce15_*")
    assert esito.returncode == 0, esito.stdout
    assert "fuori dalle attese: 0" in esito.stdout
```

- [ ] **Step 3: Prova rossa.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_parita_riepilogo.py -q -p no:cacheprovider`
  Atteso: 3 failed sulle asserzioni `returncode == …` (lo script non esiste, il sottoprocesso esce 2).
- [ ] **Step 4: Implementa** i punti 1-3 del Change.
- [ ] **Step 5: Verde** con lo stesso comando dello Step 3: 3 passed.
- [ ] **Step 6: Banco.** `/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/lotto3a-task1-base)" --anni 4 --controllo-negativo --json /tmp/lotto3a-task1-parita.json --log /tmp/lotto3a-task1-parita.log`
  Atteso: uscita 0, «NESSUNA DIVERGENZA — 105 scenari», controllo negativo superato. Poi conta gli scenari nuovi con
  `/home/peter/DEV/budget/backend/venv/bin/python -c "import sys; sys.path.insert(0, '.'); from scripts import parita_motore as b; g=b.costruisci_griglia(20260910,4); print(len(g), sum(1 for s in g if '__sweep_' in s['id']))"`
  → `105 28`.
- [ ] **Step 7: Commit.** `git add scripts/parita_motore.py scripts/parita_riepilogo.py tests/test_parita_riepilogo.py && git commit -m "test(banco): quattro profili dello sweep e il riepilogo delle divergenze attese (lotto 3A, task 1)"`
- [ ] **Step 8: Rapporto** in `/home/peter/DEV/budget/.superpowers/sdd/2026-09-10-lotto3a-motori-rendiconto/task-1-report.md`:
  prova rossa, verde, banco (uscita, righe finali del log), `git diff --stat HEAD~1`.

**Observable acceptance.** 3 test verdi; banco a 0 divergenze su 105 scenari con controllo negativo superato;
`scripts/parita_riepilogo.py` presente ed eseguibile col Python del venv.

---

### Task 2: Lo sweep rimborsa solo il pregresso senza piano, sulla cassa di dopo gli override, e il debito bancario si dichiara per componenti

**Esecutore:** pi (Orca) · **Revisore:** opus · **Ondata:** A, dopo il Task 1 (usa i suoi profili e `scripts/parita_riepilogo.py`)

**Target (spec §4.1, decisione 3 del proprietario).**
- Oggi il cash sweep, dentro `ForecastEngine._calculate_balance_sheet`, rimborsa prima `sp16a` e poi `sp17a` sull'aggregato,
  quando pregresso e prestiti nuovi sono gia' fusi: un prestito nuovo estinto dallo sweep continua a maturare interessi
  (misurato: 80.000 / 5 anni / 5%, sweep a soglia zero, `sp16a` e `sp17a` a 0,00 dal 2027 e `ce15` 9.000 / 8.200 / 7.400 /
  6.600, cioe' 7.200 di oneri su debito a zero).
- Oggi lo sweep decide sulla cassa di **prima** degli `sp_overrides` (rilievo I2 della revisione finale del lotto 2):
  caso misurato con aliquota 24, override `sp08` = 100.000 nel 2027, minimo 10.000 → «Unfunded financing requirement
  11,053.98»; con lo scoperto concesso rimborsa 50.000 di `sp17a` e apre 11.053,98 di scoperto nello stesso anno.
- Dopo: il perimetro dello sweep e' (1) lo scoperto, come oggi (la cassa netta lo contiene gia'), (2) il debito bancario
  pregresso **senza alcun piano** — nell'anno non ci sono contratti con residuo iniziale (`use_detailed_existing_schedule`
  falso) e `existing_debt_repayment_years` di quella riga e' assente o ≤ 0 — prima a breve poi a lungo. Nient'altro. I
  contratti della griglia, il legacy `financing_amount` e il pregresso con anni di rimborso seguono solo il loro piano. La
  cassa eccedente resta in `sp09`. Lo sweep decide una volta sola, sulla cassa gia' al centesimo e dopo gli override.
- Nuova chiave `details['debito_bancario']`, dichiarata ogni anno:
  `{"pregresso_senza_piano": {apertura, rimborso_sweep, breve, lungo} | None, "pregresso_piano_anni": {apertura, rimborso,
  breve, lungo} | None, "contratti": [{indice, anno, tasso, erogato, residuo_iniziale, rimborso, interessi, breve, lungo}]}`.
  **Invariante:** somma dei `breve` + `scoperto_residuo` = `sp16a`; somma dei `lungo` = `sp17a`, al centesimo, ogni anno.
  Sostituisce `details['prestiti_nuovi_quota_breve']`, che sparisce.

**Da leggere prima, per simbolo, sul branch del lotto 3A** (il giro finale del lotto 2 ha riscritto parti di
`compute_forecast`, `_apply_sp_overrides` e `_normalize_balance_sheet_cents`: i numeri di riga dello snapshot non
valgono piu'):
- `calculations/forecast_engine.py`: classe `_Overdraft` (in particolare `copri`), `_ha_residuo_pregresso`,
  `_e_contratto_pregresso`, `_residuo_prestiti_nuovi`, `_quota_breve_prestiti_nuovi`, `ForecastEngine.assemble_financing`,
  `ForecastEngine.compute_forecast` (il blocco che scrive `details['prestiti_nuovi_quota_breve']` dopo la normalizzazione,
  e il riallineamento di `details['imposte']` aggiunto dal lotto 2), `ForecastEngine._normalize_balance_sheet_cents` (il
  ramo `recompute_cash`), `ForecastEngine._apply_sp_overrides`, e in `ForecastEngine._calculate_balance_sheet` i blocchi
  che iniziano con `sp16a = max(ZERO, _prev('sp16a_debiti_banche_breve') - overdraft.opening)`,
  `quota_breve_apertura = min(`, `prestiti_nuovi = [loan for loan`, `if (\n not use_detailed_existing_schedule`,
  `es_raised, es_repayment, _ = new_financing_schedule(`, `fin_raised, fin_repayment, _ = new_financing_schedule(`,
  il commento `── CASH SWEEP (opt-in) ──` e `quota_breve = _quota_breve_prestiti_nuovi(`.
- `calculations/projection_common.py`: `new_financing_schedule`.
- `tests/test_forecast_prestito_quota_breve.py`, `tests/test_forecast_finanziamento_pregresso.py`,
  `tests/test_forecast_dichiarato_vs_persistito.py`, `tests/test_forecast_scoperto.py` (le parti nominate sotto).

**Trappole note (CLAUDE.md › Invarianti e trappole › Previsionale, e il Forecasting Engine):**
- Il fabbisogno si misura **una volta sola**, in `_Overdraft.copri`, dopo ogni rettifica. Lo sweep non aggiunge un secondo
  cancello e non chiama `copri`: gira subito prima, sulla stessa cassa.
- Lo scoperto si rimborsa per primo **anche sotto** `cash_sweep_min_cash`: la cassa netta lo contiene gia', non va
  toccato.
- Dichiarato = persistito: `details['debito_bancario']` si scrive **dopo** la normalizzazione, dai valori persistiti.
- Una chiave diagnostica si dichiara sempre, anche vuota: a valle una chiave assente vale zero.
- Diagnose, never fabricate: la riconciliazione al centesimo sposta centesimi fra componenti, non crea debito oltre
  `sp16a`/`sp17a`.
- `_BANK_DEBT_SPLIT_FIELDS` resta nei campi protetti dal residuo di quadratura.
- Un `sp_overrides` su `sp16a`/`sp16` o `sp17a`/`sp17` fissa il totale: lo sweep non paga un lato forzato.

**Change — funzioni nuove in `calculations/forecast_engine.py`** (a livello di modulo, subito dopo la classe
`_Overdraft`; aggiungi `field` all'import `from dataclasses import dataclass`):

```python
def _q2(valore) -> Decimal:
    """Al centesimo con la regola del motore (ROUND_HALF_UP)."""
    return Decimal(str(valore)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


@dataclass
class _Sweep:
    """Il cash sweep di UN anno: rimborsa il solo debito bancario pregresso SENZA piano.

    Decisione 3 del proprietario (lotto 3A): i finanziamenti con un piano — contratti della
    griglia, `financing_amount`, pregresso con `existing_debt_repayment_years` — seguono solo il
    loro piano, capitale e interessi. `_calculate_balance_sheet` riempie perimetro e disponibile;
    `_normalize_balance_sheet_cents` chiama `applica` sulla cassa NETTA gia' al centesimo e DOPO gli
    `sp_overrides`, subito prima di `_Overdraft.copri` (rilievo I2 della revisione finale del
    lotto 2: deciso prima degli override, lo sweep fabbricava un fabbisogno). Lo scoperto viene
    prima per costruzione: la cassa netta lo contiene gia'.
    """
    attivo: bool = False
    minimo: Decimal = Decimal('0')
    breve_disponibile: Decimal = Decimal('0')
    lungo_disponibile: Decimal = Decimal('0')
    breve_forzato: bool = False
    lungo_forzato: bool = False
    rimborso_breve: Decimal = Decimal('0')
    rimborso_lungo: Decimal = Decimal('0')

    def applica(self, cassa: Decimal) -> Tuple[Decimal, Decimal, Decimal]:
        """(cassa, pagato a breve, pagato a lungo). Un minimo negativo vale zero."""
        zero = Decimal('0')
        self.rimborso_breve = self.rimborso_lungo = zero
        minimo = max(zero, _q2(self.minimo))
        if not self.attivo or cassa <= minimo:
            return cassa, zero, zero
        eccesso = cassa - minimo
        if not self.breve_forzato:
            self.rimborso_breve = min(eccesso, max(zero, _q2(self.breve_disponibile)))
        eccesso -= self.rimborso_breve
        if not self.lungo_forzato:
            self.rimborso_lungo = min(eccesso, max(zero, _q2(self.lungo_disponibile)))
        return cassa - self.rimborso_breve - self.rimborso_lungo, self.rimborso_breve, self.rimborso_lungo


@dataclass
class _DebitoBancarioAnno:
    """Le componenti del debito bancario di UN anno, grezze, come `_calculate_balance_sheet` le separa.

    Al piu' uno fra `senza_piano` e `piano_anni` e' valorizzato; entrambi sono `None` quando il
    pregresso e' descritto da contratti (`opening_residual`). `contratti` elenca OGNI contratto del
    piano (misti gia' divisi), nell'ordine di `assemble_financing`, anche quelli non ancora erogati.
    """
    senza_piano: Optional[Dict[str, Decimal]] = None
    piano_anni: Optional[Dict[str, Decimal]] = None
    contratti: List[Dict[str, Any]] = field(default_factory=list)


def _residuo_contratto(loan, fino_al_anno: int) -> Decimal:
    """Il residuo di UN contratto a fine `fino_al_anno`, con la catena al centesimo del motore.

    Parte da `opening_residual` (zero per un prestito nuovo) prima del suo anno; un contratto non
    ancora erogato resta al valore di partenza. Per un prestito nuovo coincide con
    `_residuo_prestiti_nuovi([loan], fino_al_anno)`.
    """
    zero = Decimal('0')
    residuo = Decimal(str(loan.get('opening_residual') or 0))
    for anno in range(int(loan['year']), fino_al_anno + 1):
        erogato, rimborso, _ = new_financing_schedule([loan], anno)
        residuo = _q2(max(zero, residuo + erogato - rimborso))
    return residuo


def _contratti_dell_anno(loans, anno: int, quota_breve_nuovi: Decimal, residuo_nuovi: Decimal,
                         breve_pregresso: Decimal, lungo_pregresso: Decimal) -> List[Dict[str, Any]]:
    """Le righe `contratti` di `details['debito_bancario']`, grezze (le quantizza `_dichiara_debito_bancario`).

    Per ogni contratto: erogato, rimborso e interessi dell'anno dal kernel sul solo contratto, e il
    residuo di fine anno dalla sua catena. La ripartizione ricompone ESATTAMENTE i totali che il
    motore scrive in `sp16a`/`sp17a`:
    - contratti nuovi: la propria quota a breve (`_quota_breve_prestiti_nuovi` sul solo contratto);
      l'ultimo nuovo in ordine assorbe la differenza verso `quota_breve_nuovi` e verso
      `residuo_nuovi - quota_breve_nuovi`;
    - contratti col residuo iniziale: `breve_pregresso` si assegna in ordine, fino al residuo di
      ciascuno; l'ultimo assorbe la differenza verso `breve_pregresso` e verso `lungo_pregresso`.
    """
    zero = Decimal('0')
    righe: List[Dict[str, Any]] = []
    for indice, loan in enumerate(loans or []):
        erogato, rimborso, interessi = new_financing_schedule([loan], anno)
        righe.append({
            'indice': indice,
            'anno': int(loan['year']),
            'tasso': Decimal(str(loan.get('rate') or 0)) * Decimal('100'),
            'erogato': erogato,
            'residuo_iniziale': Decimal(str(loan.get('opening_residual') or 0)),
            'rimborso': rimborso,
            'interessi': interessi,
            '_residuo': _residuo_contratto(loan, anno),
            '_pregresso': _e_contratto_pregresso(loan),
            '_loan': loan,
        })
    nuovi = [r for r in righe if not r['_pregresso']]
    pregressi = [r for r in righe if r['_pregresso']]
    for r in nuovi:
        r['breve'] = _quota_breve_prestiti_nuovi([r['_loan']], anno, r['_residuo'])
        r['lungo'] = r['_residuo'] - r['breve']
    if nuovi:
        ultimo = nuovi[-1]
        ultimo['breve'] += quota_breve_nuovi - sum((r['breve'] for r in nuovi), zero)
        ultimo['lungo'] += (residuo_nuovi - quota_breve_nuovi) - sum((r['lungo'] for r in nuovi), zero)
    resto = breve_pregresso
    for r in pregressi:
        r['breve'] = min(max(zero, r['_residuo']), max(zero, resto))
        r['lungo'] = r['_residuo'] - r['breve']
        resto -= r['breve']
    if pregressi:
        ultimo = pregressi[-1]
        ultimo['breve'] += breve_pregresso - sum((r['breve'] for r in pregressi), zero)
        ultimo['lungo'] += lungo_pregresso - sum((r['lungo'] for r in pregressi), zero)
    for r in righe:
        for chiave in ('_residuo', '_pregresso', '_loan'):
            del r[chiave]
    return righe


def _dichiara_debito_bancario(debito: "_DebitoBancarioAnno", sweep: "Optional[_Sweep]",
                              sp16a: Decimal, sp17a: Decimal, scoperto: Decimal) -> Dict[str, Any]:
    """`details['debito_bancario']` al centesimo, riconciliato con cio' che `sp16a`/`sp17a` persistono.

    Somma dei `breve` + `scoperto` = `sp16a`, somma dei `lungo` = `sp17a`, per costruzione. La
    differenza fra le componenti grezze quantizzate e il persistito (centesimi di arrotondamento,
    un `sp_overrides` sul debito bancario, lo sweep) si posa cosi':
    - in aumento, sulla «casa del pregresso»: `pregresso_senza_piano`, altrimenti
      `pregresso_piano_anni`, altrimenti l'ultimo contratto col residuo iniziale, altrimenti
      l'ultimo contratto nuovo;
    - in riduzione, prima sul pregresso (le due componenti, poi i contratti col residuo dall'ultimo),
      poi sui contratti nuovi dall'ultimo, mai sotto zero: e' la precedenza con cui la quota a breve
      dei prestiti nuovi si riduceva sotto un override di `sp16a` fino al lotto 2.
    """
    zero = Decimal('0')
    senza_piano = None
    if debito.senza_piano is not None:
        pagato_breve = sweep.rimborso_breve if sweep is not None else zero
        pagato_lungo = sweep.rimborso_lungo if sweep is not None else zero
        senza_piano = {
            'apertura': _q2(debito.senza_piano['apertura']),
            'rimborso_sweep': pagato_breve + pagato_lungo,
            'breve': _q2(debito.senza_piano['breve']) - pagato_breve,
            'lungo': _q2(debito.senza_piano['lungo']) - pagato_lungo,
        }
    piano_anni = None
    if debito.piano_anni is not None:
        piano_anni = {k: _q2(debito.piano_anni[k]) for k in ('apertura', 'rimborso', 'breve', 'lungo')}
    contratti = [
        {**c, **{k: _q2(c[k]) for k in ('erogato', 'residuo_iniziale', 'rimborso', 'interessi', 'breve', 'lungo')}}
        for c in debito.contratti
    ]
    pregressi = [c for c in contratti if c['residuo_iniziale'] > zero]
    nuovi = [c for c in contratti if c['residuo_iniziale'] == zero]
    componenti_pregresso = [c for c in (senza_piano, piano_anni) if c is not None]
    tutte = componenti_pregresso + contratti
    casa = (componenti_pregresso[0] if componenti_pregresso
            else pregressi[-1] if pregressi else nuovi[-1] if nuovi else None)
    ordine_riduzione = componenti_pregresso + list(reversed(pregressi)) + list(reversed(nuovi))
    for lato, bersaglio in (('breve', sp16a - scoperto), ('lungo', sp17a)):
        delta = bersaglio - sum((c[lato] for c in tutte), zero)
        if delta > zero and casa is not None:
            casa[lato] += delta
        elif delta < zero:
            for c in ordine_riduzione:
                tolto = min(max(zero, c[lato]), -delta)
                c[lato] -= tolto
                delta += tolto
                if delta == zero:
                    break
    return {'pregresso_senza_piano': senza_piano, 'pregresso_piano_anni': piano_anni, 'contratti': contratti}


def _quota_breve_dichiarata(prev_details) -> Decimal:
    """La quota a breve dei prestiti NUOVI che l'anno prima ha dichiarato (e `sp16a` persistito).

    Somma dei `breve` dei contratti senza residuo iniziale in `details['debito_bancario']`. Sostituisce la
    lettura di `details['prestiti_nuovi_quota_breve']`, che il lotto 3A toglie.
    """
    debito = (prev_details or {}).get('debito_bancario') or {}
    return sum(
        (Decimal(str(c.get('breve') or 0)) for c in (debito.get('contratti') or [])
         if Decimal(str(c.get('residuo_iniziale') or 0)) == 0),
        Decimal('0'),
    )
```

**Change — contratto delle modifiche nel motore** (codice da scrivere dopo averlo letto sul branch):
1. `_calculate_balance_sheet`: due parametri keyword nuovi, `sweep: "Optional[_Sweep]" = None` e
   `debito_bancario: "Optional[_DebitoBancarioAnno]" = None` (default `None`: i chiamanti diretti non cambiano).
2. Nel blocco `quota_breve_apertura = min(sp16a, …)`: la seconda voce del `min` diventa `_quota_breve_dichiarata(prev_details)`.
3. Subito dopo `sp17a_pregresso = sp17a - nuovo_apertura` salva `apertura_pregresso = sp16a + sp17a_pregresso`.
4. Subito prima di `fin_raised, fin_repayment, _ = new_financing_schedule(prestiti_nuovi, …)` (cioe' dopo il piano ad
   anni e dopo i contratti pregressi):
   `piano_anni_attivo = (not use_detailed_existing_schedule and existing_repay_years is not None and D(str(existing_repay_years)) > 0)`.
   Se `debito_bancario` non e' `None` e `not use_detailed_existing_schedule`: con `piano_anni_attivo` scrivi
   `debito_bancario.piano_anni = {'apertura': apertura_pregresso, 'rimborso': apertura_pregresso - (sp16a + sp17a_pregresso), 'breve': sp16a, 'lungo': sp17a_pregresso}`,
   altrimenti `debito_bancario.senza_piano = {'apertura': apertura_pregresso, 'rimborso_sweep': ZERO, 'breve': sp16a, 'lungo': sp17a_pregresso}`.
   Se `sweep` non e' `None`: `sweep.attivo = bool(getattr(assumption, 'cash_sweep_enabled', False)) and not use_detailed_existing_schedule and not piano_anni_attivo`;
   `sweep.minimo = D(str(minimo))` se `cash_sweep_min_cash` non e' `None`, altrimenti `ZERO`;
   `sweep.breve_disponibile = sp16a`; `sweep.lungo_disponibile = sp17a_pregresso`.
5. Cancella per intero il blocco del cash sweep che segue `overdraft.copri(sp09)` (quello introdotto dal commento
   `── CASH SWEEP (opt-in) ──`, fino alle righe `sp17a -= pay_long; …`). La riga `if sp09 < 0 and not gate_downstream:` resta.
6. Nel blocco della quota a breve: salva `breve_pregresso_fine = sp16a` **prima** di `sp16a += quota_breve`; poi
   sostituisci `details['prestiti_nuovi_quota_breve'] = quota_breve` con, se `debito_bancario` non e' `None`:
   `debito_bancario.contratti = _contratti_dell_anno(financing_loans, assumption.forecast_year, quota_breve, nuovo_residuo, breve_pregresso_fine if use_detailed_existing_schedule else ZERO, sp17a_pregresso if use_detailed_existing_schedule else ZERO)`.
7. `_normalize_balance_sheet_cents`: parametro keyword nuovo `sweep: "Optional[_Sweep]" = None`. Nel ramo
   `recompute_cash`, dopo il calcolo di `cassa` e **prima** di `if overdraft is not None:`:

```python
            if sweep is not None:
                cassa, pagato_breve, pagato_lungo = sweep.applica(cassa)
                result["sp16a_debiti_banche_breve"] -= pagato_breve
                result["sp16_debiti_breve"] -= pagato_breve
                result["sp17a_debiti_banche_lungo"] -= pagato_lungo
                result["sp17_debiti_lungo"] -= pagato_lungo
```

8. `compute_forecast`, per ogni anno: crea
   `sweep = _Sweep(breve_forzato=any(sp_ov.get(c) is not None for c in ('sp16a_debiti_banche_breve', 'sp16_debiti_breve')), lungo_forzato=any(sp_ov.get(c) is not None for c in ('sp17a_debiti_banche_lungo', 'sp17_debiti_lungo')))`
   e `debito = _DebitoBancarioAnno()`; passali a `_calculate_balance_sheet(…, sweep=sweep, debito_bancario=debito)` e
   `sweep=sweep` a `_normalize_balance_sheet_cents`. Sostituisci il blocco che scrive
   `details['prestiti_nuovi_quota_breve'] = min(…)` con
   `details['debito_bancario'] = _dichiara_debito_bancario(debito, sweep, forecast_bs['sp16a_debiti_banche_breve'], forecast_bs['sp17a_debiti_banche_lungo'], overdraft.outstanding)`.
   Subito sopra quel blocco c'e' un commento di 7 righe che inizia con «La quota a breve dei prestiti nuovi (Task 17)
   si dichiara per quello che `sp16a` persiste DAVVERO»: descrive il campo `prestiti_nuovi_quota_breve` che questo
   punto elimina, quindi aggiornalo per descrivere `details['debito_bancario']` (o rimuovilo, se la spiegazione
   risulta ridondante col docstring di `_dichiara_debito_bancario`) — non lasciarlo a parlare di un campo che non
   esiste piu'. Il riallineamento di `details['imposte']` scritto dal lotto 2 resta dov'e'.

**Constraints.** Zero celle di CE sul banco. Nessun `copri` in piu'. `prestiti_nuovi_quota_breve` non compare piu' in
nessun `details`. L'infrannuale (`intra_year_engine`) chiama `_normalize_balance_sheet_cents` senza `sweep`: non cambia.
`forecast_engine.py` e' LF.

**Ownership.** `calculations/forecast_engine.py`, `tests/test_forecast_sweep_piani.py` (nuovo),
`tests/test_forecast_prestito_quota_breve.py`, `tests/test_forecast_finanziamento_pregresso.py`,
`tests/test_forecast_dichiarato_vs_persistito.py`, `CLAUDE.md`, `docs/budget/API-PREVISIONALE.md`,
`docs/budget/FORECASTING_GUIDE.md` (CRLF).

**Numeri attesi.** Misurati sullo snapshot `452112d` col gemello senza sweep meno il pregresso senza piano che la cassa
sopra il minimo puo' rimborsare (conto economico e imposte del gemello non dipendono dal pregresso bancario). Il giro
finale del lotto 2 sposta solo centesimi fra sotto-voci operative di `sp16`/`sp17` e la posizione tributaria dopo un
override di `sp06e`/`sp16e`: nessuno di questi scenari li tocca. Se lo Step 3 mostra valori di **oggi** diversi da quelli
scritti nei docstring, fermati e riferisci prima di implementare.

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task2-base`
- [ ] **Step 2: Test nuovi**, `tests/test_forecast_sweep_piani.py`:

```python
"""Lo sweep rimborsa solo il debito bancario pregresso senza piano, sulla cassa di dopo gli override (lotto 3A, Task 2).

Decisione 3 del proprietario: i finanziamenti con un piano seguono solo il loro piano (contratti della griglia,
`financing_amount`, pregresso con `existing_debt_repayment_years`). Lo sweep rimborsa lo scoperto (sulla cassa netta,
come prima) e il debito bancario pregresso SENZA piano, prima a breve poi a lungo; la cassa eccedente resta. Decide sulla
cassa di DOPO gli `sp_overrides` (rilievo I2 della revisione finale del lotto 2).

Oracolo: il gemello senza sweep sullo snapshot `452112d`, meno il pregresso senza piano rimborsabile dalla cassa sopra
il minimo, anno per anno.
"""
import json
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.app.services import assumptions_service, forecast_preview_service
from database.models import BalanceSheet, BudgetScenario, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

SP09, SP16A, SP17A = "sp09_disponibilita_liquide", "sp16a_debiti_banche_breve", "sp17a_debiti_banche_lungo"
BREVE, LUNGO = D("12345.67"), D("23456.79")
SWEEP0 = {"cash_sweep_enabled": True, "cash_sweep_min_cash": 0}
PRESTITO = {"financing_amount": 100000.38, "financing_duration_years": 4, "financing_interest_rate": 4.35}


def _riga(anno, crescita=3, aliquota=27.9, **extra):
    riga = {"forecast_year": anno, "revenue_growth_pct": crescita, "tax_rate": aliquota}
    riga.update(extra)
    return riga


def _dec(valore):
    return D(str(valore))


def _genera(user, rows, breve=None, lungo=None):
    """`(risposta del bulk, {anno: (sp, ce, details)}, errore dell'anteprima)` dal percorso persistito.

    Con `breve`/`lungo` il debito bancario pregresso del kit (50.000 su `sp17a`) si sostituisce con quello
    dato; la cassa riassorbe la differenza.
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=user)
            if breve is not None:
                fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
                b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
                delta_lungo = lungo - b.sp17a_debiti_banche_lungo
                b.sp16a_debiti_banche_breve = breve
                b.sp16_debiti_breve += breve
                b.sp17a_debiti_banche_lungo = lungo
                b.sp17_debiti_lungo += delta_lungo
                b.sp09_disponibilita_liquide += breve + delta_lungo
                db.commit()
            sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
            db.add(sc)
            db.commit()
            res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in rows], auto_generate=True)
            prev = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in rows])
            det = {a["year"]: a["details"] for a in prev["forecast_years"]}
            anni = {}
            if res["forecast_generated"]:
                anni = {anno: (sp, ce, det.get(anno)) for anno, sp, ce in read_forecast_maps(db, sc.id)}
            return res, anni, prev["error"]
    finally:
        engine.dispose()


def _confronta(anni, attesi, campi):
    fuori = []
    for anno, valori in attesi.items():
        sp, ce, _det = anni[anno]
        for (etichetta, dove, chiave), atteso in zip(campi, valori):
            letto = (sp if dove == "sp" else ce)[chiave]
            if letto != D(atteso):
                fuori.append(f"{anno} {etichetta}: {letto}, atteso {atteso}")
    return fuori


CAMPI_CASSA_DEBITO_ONERI = (("sp09", "sp", SP09), ("sp16a", "sp", SP16A), ("sp17a", "sp", SP17A),
                            ("ce15", "ce", "ce15_oneri_finanziari"))


def test_il_prestito_nuovo_segue_il_piano_e_la_cassa_eccedente_resta():
    """Sonda della ricognizione (voce 5), kit: 80.000 / 5 anni / 5% nel 2027, sweep a soglia zero.

    Oggi: `sp16a` e `sp17a` a 0,00 ogni anno, `ce15` 9.000 / 8.200 / 7.400 / 6.600. Dopo: quota a breve 16.000,00, il
    resto a lungo, gli stessi interessi, la cassa piu' alta del capitale non rimborsato; lo sweep paga nel 2027 i 50.000
    di pregresso senza piano del kit.
    """
    rows = [_riga(2027, financing_amount=80000, financing_duration_years=5, financing_interest_rate=5, **SWEEP0)]
    rows += [_riga(anno, **SWEEP0) for anno in (2028, 2029, 2030)]
    res, anni, errore = _genera("sweep-p5", rows)
    assert res["forecast_generated"] is True, res["message"]
    assert errore is None
    fuori = _confronta(anni, {
        2027: ("119122.22", "16000.00", "48000.00", "9000.00"),
        2028: ("223995.44", "16000.00", "32000.00", "8200.00"),
        2029: ("343211.41", "16000.00", "16000.00", "7400.00"),
        2030: ("477183.12", "16000.00", "0.00", "6600.00"),
    }, CAMPI_CASSA_DEBITO_ONERI)
    assert not fuori, "\n".join(fuori)
    debito = anni[2027][2]["debito_bancario"]
    assert _dec(debito["pregresso_senza_piano"]["rimborso_sweep"]) == D("50000.00")
    assert debito["pregresso_piano_anni"] is None
    (contratto,) = debito["contratti"]
    assert [_dec(contratto[k]) for k in ("erogato", "rimborso", "interessi", "breve", "lungo")] == [
        D("80000.00"), D("16000.00"), D("4000.00"), D("16000.00"), D("48000.00")]


def _righe_i2(scoperto, aliquota=24):
    """Caso I2 della revisione finale, kit: `sp08` forzato a 100.000 nel 2027, minimo 10.000, sweep acceso.

    Due aliquote, entrambe misurate in «Numeri ricontrollati» §1 e in `misure.md` §4.1: **24** riproduce esattamente
    la sonda della revisione finale del lotto 2, che scriveva le righe sull'ORM dove il default di colonna di
    `tax_rate` e' 24, ed e' l'aliquota con cui la spec cita gli 11.053,98 di fabbisogno. **27,9** e' l'aliquota che
    ogni schermata reale invia (CLAUDE.md, «Tax rate: the 24 in the schema is not what runs»: nessuno schermo la
    manda mai) — il caso rappresentativo del percorso di produzione, con un fabbisogno piu' alto (14.563,20: meno
    imposta pagata sull'utile ante, a parita' di crescita e di override, avrebbe lasciato piu' cassa; qui e' il
    contrario, il 27,9 sottrae piu' cassa del 24 e il fabbisogno cresce).
    """
    rows = []
    for i, anno in enumerate((2027, 2028, 2029)):
        riga = _riga(anno, crescita=3.33, aliquota=aliquota, sp06e_growth_pct=0, sp16e_growth_pct=0,
                     cash_sweep_enabled=True, cash_sweep_min_cash=10000, overdraft_allowed=scoperto)
        if i == 0:
            riga["sp_overrides"] = {"sp08_attivita_finanziarie": 100000}
        rows.append(riga)
    return rows


@pytest.mark.parametrize("scoperto", [False, True], ids=["scoperto non concesso", "scoperto concesso"])
def test_lo_sweep_decide_sulla_cassa_di_dopo_gli_override(scoperto):
    """Oggi: senza scoperto il previsionale si ferma per 11.053,98 di fabbisogno; con lo scoperto `sp17a` va a zero e
    `sp16a` porta 11.053,98 di scoperto. Dopo: la cassa post-override paga 28.946,02 di pregresso e resta al minimo."""
    res, anni, errore = _genera(f"sweep-i2-{scoperto}", _righe_i2(scoperto))
    assert res["forecast_generated"] is True, res["message"]
    assert errore is None
    fuori = _confronta(anni, {
        2027: ("10000.00", "0.00", "21053.98"),
        2028: ("113393.98", "0.00", "0.00"),
        2029: ("253860.09", "0.00", "0.00"),
    }, CAMPI_CASSA_DEBITO_ONERI[:3])
    fuori += [f"{a} scoperto_residuo {anni[a][2]['scoperto_residuo']}" for a in anni if _dec(anni[a][2]["scoperto_residuo"]) != 0]
    assert not fuori, "\n".join(fuori)
    rimborsi = [_dec(anni[a][2]["debito_bancario"]["pregresso_senza_piano"]["rimborso_sweep"]) for a in (2027, 2028, 2029)]
    assert rimborsi == [D("28946.02"), D("21053.98"), D("0.00")]


@pytest.mark.parametrize("scoperto", [False, True], ids=["scoperto non concesso", "scoperto concesso"])
def test_lo_sweep_decide_sulla_cassa_di_dopo_gli_override_aliquota_27_9(scoperto):
    """Stesso caso I2 del test gemello, con l'aliquota **27,9** che ogni schermata reale invia (CLAUDE.md, «Tax rate:
    the 24 in the schema is not what runs»): il gemello con 24 riproduce solo la sonda della revisione finale del
    lotto 2, questo e' il caso che il percorso di produzione esercita davvero. Oggi (senza il fix di questo task) il
    fabbisogno e' 14.563,20, contro gli 11.053,98 dell'aliquota 24. Dopo: la cassa post-override lo assorbe per
    intero come col 24, e il previsionale riesce con o senza scoperto concesso.

    Attesi da «Numeri ricontrollati» §1 e da `misure.md` §4.1: solo questi tre campi sono misurati la' (non i nove
    del test gemello), quindi solo questi tre si verificano — gli altri non si inventano.
    """
    res, anni, errore = _genera(f"sweep-i2-279-{scoperto}", _righe_i2(scoperto, aliquota=27.9))
    assert res["forecast_generated"] is True, res["message"]
    assert errore is None
    attesi = {2027: ("sp17a", SP17A, "24563.20"), 2028: ("sp09", SP09, "105570.37"), 2029: ("sp09", SP09, "240890.12")}
    fuori = []
    for anno, (etichetta, chiave, atteso) in attesi.items():
        letto = anni[anno][0][chiave]
        if letto != D(atteso):
            fuori.append(f"{anno} {etichetta}: {letto}, atteso {atteso}")
    assert not fuori, "\n".join(fuori)


CON_PIANO = {
    "anni di rimborso": (
        [_riga(anno, existing_debt_repayment_years=3) for anno in (2027, 2028, 2029)],
        {2027: ("82990.53", "411.52", "23456.79"), 2028: ("194013.60", "0.00", "11934.16"), 2029: ("318802.62", "0.00", "0.01")},
    ),
    "contratti col residuo iniziale": (
        [_riga(2027, financing_loans=[{"name": "Pregresso", "amount": 0, "opening_residual": 35802.46,
                                        "duration_years": 5, "interest_rate": 4}]), _riga(2028), _riga(2029)],
        {2027: ("91332.09", "5185.18", "23456.79"), 2028: ("209987.69", "0.00", "21481.48"), 2029: ("342615.76", "0.00", "14320.99")},
    ),
}


@pytest.mark.parametrize("nome", list(CON_PIANO))
def test_un_pregresso_con_un_piano_non_e_toccato_dallo_sweep(nome):
    """Base banca (12.345,67 a breve, 23.456,79 a lungo). Con un piano lo sweep a soglia zero non ha nulla da
    rimborsare: lo scenario e' identico, cella per cella, al gemello senza sweep. Oggi lo sweep chiude tutto nel 2027."""
    righe, ancore = CON_PIANO[nome]
    _res_g, gemello, _ = _genera(f"gemello-{nome}", righe, BREVE, LUNGO)
    res, sweep, _errore = _genera(f"sweep-{nome}", [dict(r, **SWEEP0) for r in righe], BREVE, LUNGO)
    assert res["forecast_generated"] is True, res["message"]
    fuori = _confronta(sweep, ancore, CAMPI_CASSA_DEBITO_ONERI[:3])
    for anno in ancore:
        sp, ce, _ = sweep[anno]
        sp_g, ce_g, _ = gemello[anno]
        fuori += [f"{anno} {k}: sweep {sp[k]}, gemello {sp_g[k]}" for k in sp if sp[k] != sp_g[k]]
        fuori += [f"{anno} {k}: sweep {ce[k]}, gemello {ce_g[k]}" for k in ce if ce[k] != ce_g[k]]
    assert not fuori, "\n".join(fuori)


def test_senza_piano_lo_sweep_paga_il_pregresso_prima_a_breve_poi_a_lungo_e_mai_il_prestito():
    """Base banca, prestito 100.000,38 / 4 anni / 4,35% nel 2027, sweep a soglia zero. Oggi `sp16a` e `sp17a` a zero."""
    rows = [_riga(2027, **PRESTITO, **SWEEP0), _riga(2028, **SWEEP0), _riga(2029, **SWEEP0)]
    res, anni, errore = _genera("sweep-senza-piano", rows, BREVE, LUNGO)
    assert res["forecast_generated"] is True, res["message"]
    fuori = _confronta(anni, {
        2027: ("129772.48", "25000.09", "50000.20", "9350.02"),
        2028: ("225680.76", "25000.09", "25000.11", "8262.51"),
        2029: ("336139.07", "25000.09", "0.02", "7175.01"),
    }, CAMPI_CASSA_DEBITO_ONERI)
    assert not fuori, "\n".join(fuori)
    senza_piano = anni[2027][2]["debito_bancario"]["pregresso_senza_piano"]
    assert [_dec(senza_piano[k]) for k in ("apertura", "rimborso_sweep", "breve", "lungo")] == [
        D("35802.46"), D("35802.46"), D("0.00"), D("0.00")]


def test_lo_sweep_paga_il_pregresso_senza_piano_solo_dopo_lo_scoperto():
    """Base banca. 2027: un investimento apre 255.075,69 di scoperto. 2028: la cassa netta lo riduce a 128.224,59,
    niente da rimborsare. 2029: chiude lo scoperto e con i 24.530,92 che restano paga tutto il breve pregresso
    (12.345,67) e 12.185,25 del lungo. Oggi il 2029 chiude con 0,01 di cassa e 11.271,55 su `sp17a`: lo sweep
    decideva sulla cassa grezza, prima del centesimo."""
    comuni = {"overdraft_allowed": True, "financing_interest_rate": 6.13}
    rows = [_riga(2027, tangible_investments=350000.37, **comuni), _riga(2028, **comuni, **SWEEP0),
            _riga(2029, **comuni, **SWEEP0)]
    res, anni, errore = _genera("sweep-dopo-scoperto", rows, BREVE, LUNGO)
    assert res["forecast_generated"] is True, res["message"]
    fuori = _confronta(anni, {
        2027: ("0.00", "267421.36", "23456.79"),
        2028: ("0.00", "140570.26", "23456.79"),
        2029: ("0.00", "0.00", "11271.54"),
    }, CAMPI_CASSA_DEBITO_ONERI[:3])
    assert not fuori, "\n".join(fuori)
    assert [_dec(anni[a][2]["scoperto_residuo"]) for a in (2027, 2028, 2029)] == [D("255075.69"), D("128224.59"), D("0")]
    senza_piano = anni[2029][2]["debito_bancario"]["pregresso_senza_piano"]
    assert [_dec(senza_piano[k]) for k in ("rimborso_sweep", "breve", "lungo")] == [D("24530.92"), D("0.00"), D("11271.54")]


def test_debito_bancario_quadra_con_sp16a_e_sp17a_su_tutta_la_griglia_del_banco(tmp_path):
    """L'invariante della spec §4.1 su ogni anno di ogni scenario del banco (seme 20260910, 4 anni): somma dei `breve`
    piu' `scoperto_residuo` = `sp16a`, somma dei `lungo` = `sp17a`, al centesimo. Gira il driver del banco
    sull'albero corrente, in un sottoprocesso."""
    from scripts import parita_motore as banco
    ingresso, uscita, driver = tmp_path / "in.json", tmp_path / "out.json", tmp_path / "driver.py"
    ingresso.write_text(json.dumps({"scenari": banco.costruisci_griglia(20260910, 4)}), encoding="utf-8")
    driver.write_text(banco.DRIVER, encoding="utf-8")
    esiti = banco.esegui_driver(Path(sys.executable), driver, banco.REPO_ROOT, ingresso, uscita)
    fuori, anni_visti = [], 0
    for sid, esito in sorted(esiti.items()):
        for anno in esito["anni"]:
            det, sp = anno["details"], anno["balance_sheet"]
            dove = f"[{sid} · {anno['anno']}]"
            if "prestiti_nuovi_quota_breve" in det:
                fuori.append(f"{dove} prestiti_nuovi_quota_breve ancora dichiarata")
            debito = det.get("debito_bancario")
            if not isinstance(debito, dict):
                fuori.append(f"{dove} debito_bancario non dichiarato")
                continue
            anni_visti += 1
            if debito.get("pregresso_senza_piano") and debito.get("pregresso_piano_anni"):
                fuori.append(f"{dove} pregresso senza piano e con anni di rimborso insieme")
            componenti = [c for c in (debito.get("pregresso_senza_piano"), debito.get("pregresso_piano_anni")) if c]
            componenti += list(debito.get("contratti") or [])
            breve = sum((D(str(c["breve"])) for c in componenti), D("0")) + D(str(det.get("scoperto_residuo") or 0))
            lungo = sum((D(str(c["lungo"])) for c in componenti), D("0"))
            if breve != D(sp[SP16A]):
                fuori.append(f"{dove} breve {breve} != sp16a {sp[SP16A]}")
            if lungo != D(sp[SP17A]):
                fuori.append(f"{dove} lungo {lungo} != sp17a {sp[SP17A]}")
    assert anni_visti >= 380, f"troppo pochi anni-scenario confrontati: {anni_visti}"
    assert not fuori, f"{len(fuori)} violazioni:\n" + "\n".join(fuori[:40])
```

- [ ] **Step 3: Prova rossa.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_sweep_piani.py -q -p no:cacheprovider`
  Atteso: 10 failed (il caso I2 e' parametrizzato su due aliquote — 24 e 27,9 — per due stati di `scoperto`, quattro
  esiti in tutto), tutti su asserzioni (valori di cassa/debito, `forecast_generated is True` nel caso I2 senza
  scoperto, «debito_bancario non dichiarato» sulla griglia). Nessun `ImportError`, nessun `KeyError` prima di un `assert`.
- [ ] **Step 4: Implementa** le funzioni nuove e i punti 1-8 del contratto.
- [ ] **Step 5: Test esistenti da aggiornare (e solo questi).**
  - `tests/test_forecast_prestito_quota_breve.py`: togli la costante `QUOTA`; sostituisci il corpo di `_quota(det)` con
    la somma dei `breve` dei contratti senza residuo iniziale:

```python
def _quota(det):
    """La quota a breve dei prestiti NUOVI dichiarata: somma dei `breve` dei contratti senza residuo iniziale in
    `details['debito_bancario']` (lotto 3A, Task 2). Assente vale zero — ed e' l'asserzione a dirlo, non un KeyError."""
    contratti = (det.get("debito_bancario") or {}).get("contratti") or []
    return sum((D(str(c["breve"])) for c in contratti if D(str(c.get("residuo_iniziale") or 0)) == 0), D("0"))
```

    e ogni altro uso di `QUOTA` (per esempio `det.get(QUOTA)` nei messaggi) con `_quota(det)`. Rinomina
    `test_lo_sweep_rimborsa_prima_il_pregresso_poi_il_prestito_nuovo` in `test_lo_sweep_rimborsa_solo_il_pregresso_senza_piano`
    e scrivi nel docstring che l'eccedenza del 2027 (22.346,22) non supera il pregresso, quindi i numeri restano quelli
    (misurato: identici). Sostituisci il blocco `EROSIONE` e `test_uno_sweep_che_erode_il_prestito_lascia_a_breve_solo_cio_che_ne_resta` con:

```python
# ══ Uno sweep che fino al lotto 2 erodeva il prestito nuovo ══
#
# Stessa base e stessi due minimi della sonda 6b della revisione del Task 16: la cassa del 2027 sopra il minimo supera il
# pregresso (35.802,46). Dal lotto 3A (decisione 3 del proprietario) il prestito segue il suo piano, lo sweep si ferma al
# pregresso e la cassa resta: i due minimi danno gli stessi numeri. Oracolo: gemello senza sweep meno il pregresso,
# sullo snapshot `452112d`.
OLTRE_IL_PREGRESSO = dict(
    totale=("75000.29", "50000.20", "25000.11", "0.02", "0.02"),
    cassa=("131191.48", "230036.16", "345042.90", "476723.82", "650608.13"),
    quota=("25000.09", "25000.09", "25000.09", "0", "0"),
    oltre=("50000.20", "25000.11", "0.02", "0.02", "0.02"),
)


@pytest.mark.parametrize("minimo", ["71191.48", "91190.93"])
def test_uno_sweep_oltre_il_pregresso_lascia_il_prestito_al_suo_piano(minimo):
    engine, sessions = memory_sessions()
    try:
        rows = _righe(A5, None, {0: {**PRESTITO, "cash_sweep_enabled": True, "cash_sweep_min_cash": float(D(minimo))}})
        with sessions() as db:
            run = _genera(db, "oltre-pregresso", rows)
        fuori = []
        for i, anno in enumerate(A5):
            c, _ce, det = run[anno]
            dove = f"[minimo {minimo} | {anno}]"
            confronti = {
                "debito bancario sp16a+sp17a": (c[SP16A] + c[SP17A], OLTRE_IL_PREGRESSO["totale"][i]),
                "cassa sp09": (c[SP09], OLTRE_IL_PREGRESSO["cassa"][i]),
                "quota a breve in sp16a": (c[SP16A] - _scoperto(det), OLTRE_IL_PREGRESSO["quota"][i]),
                "quota dichiarata": (_quota(det), OLTRE_IL_PREGRESSO["quota"][i]),
                "oltre in sp17a": (c[SP17A], OLTRE_IL_PREGRESSO["oltre"][i]),
            }
            for etichetta, (valore, atteso) in confronti.items():
                if valore != D(atteso):
                    fuori.append(f"{dove} {etichetta}: {valore}, atteso {atteso}")
            _al_centesimo(fuori, dove, c, det)
        assert not fuori, "\n".join(fuori)
    finally:
        engine.dispose()
```

  - `tests/test_forecast_finanziamento_pregresso.py`: sostituisci `test_un_cash_sweep_che_rimborsa_oltre_il_pregresso_non_fa_rinascere_debito` con:

```python
def test_un_cash_sweep_nel_2028_paga_il_pregresso_e_lascia_il_prestito_al_suo_piano():
    """Lo sweep del 2028 ha cassa per chiudere pregresso E prestito nuovo. Fino al lotto 2 li chiudeva entrambi; dal lotto
    3A il prestito segue il suo piano (decisione 3 del proprietario): nel 2028 restano 25.000,09 a breve e 25.000,11 a
    lungo, nel 2029 la quota e i 0,02 che la catena lascia oltre, e la cassa tiene il capitale non rimborsato. Oracolo:
    gemello senza sweep meno il pregresso (35.802,46), sullo snapshot `452112d`."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            sweep = {"cash_sweep_enabled": True, "cash_sweep_min_cash": 1000.55}
            rows = [
                dict(forecast_year=2027, revenue_growth_pct=3.33, tax_rate=27.9, **PRESTITO),
                dict(forecast_year=2028, revenue_growth_pct=3.33, tax_rate=27.9, **sweep),
                dict(forecast_year=2029, revenue_growth_pct=3.33, tax_rate=27.9),
            ]
            sp = _genera(db, "sweep-oltre", rows, BREVE, LUNGO)
        assert sp[2027]["sp16a_debiti_banche_breve"] == BREVE + QUOTA_BREVE_PRESTITO[2027]
        for anno, (breve, lungo, cassa) in {2028: ("25000.09", "25000.11", "230036.16"),
                                             2029: ("25000.09", "0.02", "345042.90")}.items():
            assert sp[anno]["sp16a_debiti_banche_breve"] == D(breve), anno
            assert sp[anno]["sp17a_debiti_banche_lungo"] == D(lungo), anno
            assert sp[anno]["sp09_disponibilita_liquide"] == D(cassa), anno
            assert sp[anno]["_total_assets"] == sp[anno]["_total_liabilities"], anno
    finally:
        engine.dispose()
```

  - `tests/test_forecast_dichiarato_vs_persistito.py`, in `_divergenze`: nell'elenco delle chiavi sempre dichiarate
    sostituisci `"prestiti_nuovi_quota_breve"` con `"debito_bancario"`; sostituisci il controllo della quota
    (`quota = D(str(det.get("prestiti_nuovi_quota_breve") or 0))` e l'`if` che segue) con:

```python
    # Il debito bancario per componenti (lotto 3A, Task 2): somma dei `breve` piu' lo scoperto = `sp16a`,
    # somma dei `lungo` = `sp17a`, al centesimo.
    debito = det.get("debito_bancario") or {}
    componenti = [c for c in (debito.get("pregresso_senza_piano"), debito.get("pregresso_piano_anni")) if c]
    componenti += list(debito.get("contratti") or [])
    breve = sum((D(str(c["breve"])) for c in componenti), D("0")) + residuo
    lungo = sum((D(str(c["lungo"])) for c in componenti), D("0"))
    if breve != bs["sp16a_debiti_banche_breve"]:
        fuori.append(("debito_bancario breve", f"breve dichiarato {breve}, sp16a {bs['sp16a_debiti_banche_breve']}"))
    if lungo != bs["sp17a_debiti_banche_lungo"]:
        fuori.append(("debito_bancario lungo", f"lungo dichiarato {lungo}, sp17a {bs['sp17a_debiti_banche_lungo']}"))
```

    Nel secondo test del file, ogni `D(str(det_c.get("prestiti_nuovi_quota_breve") or 0))` diventa `_quota_nuovi(det_c)`,
    con questo helper a livello di modulo:

```python
def _quota_nuovi(det):
    contratti = (det.get("debito_bancario") or {}).get("contratti") or []
    return sum((D(str(c["breve"])) for c in contratti if D(str(c.get("residuo_iniziale") or 0)) == 0), D("0"))
```

- [ ] **Step 6: Documenti, nello stesso commit.**
  - `CLAUDE.md`, sezione «Forecasting Engine (Budget)»: dopo la frase che finisce con «…and shown in the wizard preview.»
    aggiungi: «**The cash sweep repays only what has no plan.** With `cash_sweep_enabled`, cash above
    `cash_sweep_min_cash` repays the overdraft first (it is already inside net cash) and then pre-existing bank debt
    **without any plan** — no contract with an opening residual and no `existing_debt_repayment_years` that year —
    short side first, then long. Grid contracts, the legacy `financing_amount` loan and pre-existing debt on a years plan
    follow **only their plan**, capital and interest alike, and the excess stays in `sp09` (owner's decision, lotto 3A).
    The sweep decides on the cash **after** `sp_overrides`, in `_normalize_balance_sheet_cents` right before
    `_Overdraft.copri`: deciding before the overrides turned a fundable plan into a funding requirement or opened an
    overdraft to pay an optional early repayment. `details['debito_bancario']`, declared every year, splits bank debt
    into `pregresso_senza_piano`, `pregresso_piano_anni` and one row per contract, and adds up exactly: Σ`breve` +
    `scoperto_residuo` = `sp16a`, Σ`lungo` = `sp17a`.» Nello stesso paragrafo sostituisci «declared in
    `details['prestiti_nuovi_quota_breve']`» con «declared per contract in `details['debito_bancario']['contratti']`».
  - `docs/budget/API-PREVISIONALE.md` §4-bis: il periodo «Avviene dopo il cash sweep, che rimborsa prima il debito
    bancario pregresso e poi il prestito nuovo; il debito bancario pregresso conserva la propria ripartizione.» diventa
    «Il cash sweep non la tocca mai: rimborsa solo lo scoperto e il debito bancario pregresso senza piano (§4-ter); il
    debito bancario pregresso conserva la propria ripartizione.»; il punto su `details['prestiti_nuovi_quota_breve']`
    diventa «`details['debito_bancario']['contratti']` dichiara ogni anno il `breve` di ogni prestito, riconciliato con
    quanto `sp16a` persiste davvero (§4-ter).». Aggiungi dopo §4-bis una sezione `## 4-ter. Il cash sweep e
    `details['debito_bancario']`` con: il perimetro (lo stesso testo della spec §4.1, «Comportamento richiesto»), la
    decisione dopo gli override, e questa tabella:

| Chiave | Valore |
|---|---|
| `pregresso_senza_piano` | `{apertura, rimborso_sweep, breve, lungo}` quando nell'anno non ci sono contratti con `opening_residual` né `existing_debt_repayment_years` > 0; altrimenti `null` |
| `pregresso_piano_anni` | `{apertura, rimborso, breve, lungo}` con `existing_debt_repayment_years` > 0 e nessun contratto col residuo; altrimenti `null` |
| `contratti` | una riga per contratto (misti gia' divisi, anche non ancora erogati), nell'ordine di `financing_amount` e poi della griglia: `{indice, anno, tasso, erogato, residuo_iniziale, rimborso, interessi, breve, lungo}` |

    seguita dall'invariante (Σ`breve` + `scoperto_residuo` = `sp16a`, Σ`lungo` = `sp17a`) e dalla regola dei centesimi
    (docstring di `_dichiara_debito_bancario`).
  - `docs/budget/FORECASTING_GUIDE.md` (CRLF): trova la riga con `grep -n "Il cash sweep" docs/budget/FORECASTING_GUIDE.md`
    e sostituisci il punto con «- **Il cash sweep** usa la cassa in eccesso per rimborsare il debito che non ha un piano:
    lo scoperto, e il debito bancario pregresso senza anni di rimborso e senza contratti, prima a breve poi a lungo. I
    finanziamenti con un piano seguono solo il loro piano, e la cassa in piu' resta in cassa.» (le righe successive sullo
    scoperto restano). Riporta il file a CRLF col comando delle convenzioni.
- [ ] **Step 7: Verde.**
  `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_sweep_piani.py tests/test_forecast_prestito_quota_breve.py tests/test_forecast_finanziamento_pregresso.py tests/test_forecast_dichiarato_vs_persistito.py tests/test_forecast_scoperto.py -q -p no:cacheprovider`
  poi `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_budget_pregresso.py tests/test_forecast_compute.py tests/test_forecast_preview.py tests/test_forecast_semantics.py tests/test_forecast_stale.py tests/test_forecast_indicizzazione.py tests/test_forecast_override_residuo.py tests/test_intra_year_plug_negativo.py tests/test_intra_year_semantics.py tests/test_cashflow_debito_finanziario.py -q -p no:cacheprovider`.
  `tests/test_forecast_scoperto.py::test_ruling_38_lo_scoperto_si_rimborsa_per_primo_anche_sotto_la_cassa_minima` deve
  restare verde senza modifiche (la cassa del 2029 torna esattamente al minimo 20.000,55).
- [ ] **Step 8: Banco.** Comando delle convenzioni con `task2`, poi:
  `/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_riepilogo.py /tmp/lotto3a-task2-parita.json --attese '*|details.debito_bancario' '*|details.prestiti_nuovi_quota_breve' '*__finanziamento|balance_sheet.sp09_disponibilita_liquide' '*__finanziamento|balance_sheet.sp16a_debiti_banche_breve' '*__finanziamento|balance_sheet.sp16_debiti_breve' '*__finanziamento|balance_sheet.sp17a_debiti_banche_lungo' '*__finanziamento|balance_sheet.sp17_debiti_lungo' '*__finanziamento|details.cassa_assorbita' '*__finanziamento|details.residuo_quadratura' '*__sweep_*|balance_sheet.sp09_disponibilita_liquide' '*__sweep_*|balance_sheet.sp16a_debiti_banche_breve' '*__sweep_*|balance_sheet.sp16_debiti_breve' '*__sweep_*|balance_sheet.sp17a_debiti_banche_lungo' '*__sweep_*|balance_sheet.sp17_debiti_lungo' '*__sweep_*|details.cassa_assorbita' '*__sweep_*|details.cassa_sotto_minimo' '*__sweep_*|details.residuo_quadratura' '*__sweep_override|details.scoperto_generato' '*__sweep_override|details.scoperto_residuo' '*__sweep_override|details.fabbisogno_picco' '*__sweep_override|details.fabbisogno_picco_anno' '*__sweep_override|details.oneri_scoperto' '*__sweep_override|@errore' '*__sweep_override|@anno'`
  Atteso: uscita del banco 1 (divergenze), controllo negativo superato, «fuori dalle attese: 0». Nessuna cella
  `income_statement.*`: i profili con scoperto del banco hanno tasso zero, quindi gli oneri dello scoperto non cambiano.
  Nei `sweep_senza_piano` puo' spostarsi un centesimo fra `sp09` e `sp16a`/`sp17a` (lo sweep ora decide sulla cassa al
  centesimo): e' ammesso dai pattern e va contato nel rapporto.
- [ ] **Step 9: Commit.** `git add calculations/forecast_engine.py tests/test_forecast_sweep_piani.py tests/test_forecast_prestito_quota_breve.py tests/test_forecast_finanziamento_pregresso.py tests/test_forecast_dichiarato_vs_persistito.py CLAUDE.md docs/budget/API-PREVISIONALE.md docs/budget/FORECASTING_GUIDE.md && git commit -m "fix(engine): lo sweep rimborsa solo il pregresso senza piano, dopo gli override, e dichiara il debito bancario per componenti (lotto 3A, task 2)"`
- [ ] **Step 10: Rapporto** `task-2-report.md` (contenuto delle convenzioni), con il conteggio delle divergenze per gruppo
  del riepilogo.

**Observable acceptance.** 10 test nuovi verdi (rossi prima sulle asserzioni; il caso I2 conta le due aliquote, 24 e
27,9, ciascuna con e senza scoperto); i quattro file di test aggiornati verdi; banco con sole divergenze ammesse e
controllo negativo superato; `grep -rn "prestiti_nuovi_quota_breve" calculations CLAUDE.md docs/budget`
senza risultati.

---

### Task 3: Le regole del debito bancario vivono in `projection_common.py` (refactor a 0 divergenze)

**Esecutore:** pi (Orca) · **Revisore:** opus · **Ondata:** A, dopo il Task 2 (primo commit della voce §4.2: il cambio
dell'infrannuale e' il Task 4 e parte solo dopo questo)

**Target (spec §4.2, «Ordine interno obbligato»).** Tre regole vivono oggi solo in `calculations/forecast_engine.py`:
la divisione del contratto misto (Ruling 45, dentro `ForecastEngine.assemble_financing`), la separazione pregresso /
prestito nuovo prima di ogni piano (`_calculate_balance_sheet`, blocco `nuovo_apertura = min(sp17a, _residuo_prestiti_nuovi(…))`)
e la quota a breve del prestito nuovo (`_residuo_prestiti_nuovi`, `_quota_breve_prestiti_nuovi`). L'infrannuale non le
ha. Questo task le sposta in `calculations/projection_common.py` come funzioni pure; il motore budget le usa al posto
delle copie. Nessun numero cambia.

**Da leggere prima, per simbolo, sul branch del lotto 3A:** in `calculations/forecast_engine.py` `_ha_residuo_pregresso`,
`_e_contratto_pregresso`, `_residuo_prestiti_nuovi`, `_quota_breve_prestiti_nuovi` (e i due docstring lunghi: vanno
spostati con le funzioni), `ForecastEngine.assemble_financing`, e in `_calculate_balance_sheet` le righe
`prestiti_nuovi = [loan for loan …]`, `nuovo_apertura = min(`, `sp17a_pregresso = sp17a - nuovo_apertura`. Dal Task 2
esistono anche `_residuo_contratto` e `_contratti_dell_anno`, che usano `_e_contratto_pregresso` e
`_quota_breve_prestiti_nuovi`: restano in `forecast_engine.py`.

**Trappole note.** Un refactor che muove un centesimo non e' un refactor: la prova e' il banco a 0 divergenze contro
l'HEAD di partenza. Le funzioni si spostano col loro corpo **identico** (stessa quantizzazione `ROUND_HALF_UP`, stesso
`ROUND_DOWN` finale nella quota). I nomi privati del motore restano importabili (i test li importano).

**Change.**
1. In `calculations/projection_common.py`: aggiungi `ROUND_DOWN, ROUND_HALF_UP` all'import da `decimal`, e
   `Any, Dict, List, Mapping, Tuple` all'import da `typing`. In coda al modulo:

```python
# ── Debito bancario: le regole condivise dai due motori (lotto 3A, Task 3) ──

def e_contratto_pregresso(loan) -> bool:
    """Un contratto con `opening_residual` > 0 descrive debito bancario GIA' in bilancio (pregresso).

    Dopo `contratti_da_riga_finanziamento` nessun contratto porta insieme `amount` e `opening_residual`,
    quindi il predicato basta da solo.
    """
    return Decimal(str(loan.get('opening_residual') or 0)) > ZERO


def contratti_da_riga_finanziamento(loan: Mapping[str, Any], anno: int) -> List[Dict[str, Any]]:
    """Una riga di `financing_loans` → 0, 1 o 2 contratti del kernel (Ruling 45).

    Un contratto MISTO (`amount` e `opening_residual` insieme) diventa due contratti con le stesse
    condizioni: uno col solo importo nuovo, uno col solo residuo pregresso. Un calendario di
    ammortamento e' lineare nel capitale, quindi la somma dei due equivale al contratto unico. Durata
    nulla o negativa: nessun contratto (il kernel lo salterebbe comunque).
    """
    importo = Decimal(str(loan.get('amount') or 0))
    residuo = Decimal(str(loan.get('opening_residual') or 0))
    durata = Decimal(str(loan.get('duration_years') or 0))
    if durata <= ZERO:
        return []
    condizioni = {
        'year': anno,
        'duration': durata,
        'rate': Decimal(str(loan.get('interest_rate') or 0)) / Decimal('100'),
        'grace_years': Decimal(str(loan.get('grace_years') or 0)),
        'balloon_pct': Decimal(str(loan.get('balloon_pct') or 0)),
    }
    contratti = []
    if importo > ZERO:
        contratti.append({**condizioni, 'amount': importo, 'opening_residual': ZERO})
    if residuo > ZERO:
        contratti.append({**condizioni, 'amount': ZERO, 'opening_residual': residuo})
    return contratti


def separa_prestiti_nuovi(sp17a_apertura: Decimal, prestiti_nuovi, anno: int) -> Tuple[Decimal, Decimal]:
    """(pregresso, residuo nuovo di apertura) dal debito bancario a lungo di apertura dell'anno `anno`.

    Il residuo nuovo di apertura e' la catena dei prestiti nuovi a fine `anno - 1`, mai oltre
    `sp17a_apertura`: un cash sweep o un `sp_overrides` che l'anno prima ha abbassato `sp17a` sotto la
    catena lo ha abbassato prima sul pregresso e poi sul nuovo. Va fatto PRIMA di ogni piano di rimborso:
    ogni debito si riduce solo col proprio rimborso (I1 esteso, Task 16 del lotto 2).
    """
    nuovo = min(sp17a_apertura, residuo_prestiti_nuovi(prestiti_nuovi, anno - 1))
    return sp17a_apertura - nuovo, nuovo
```

   Poi **sposta** in `projection_common.py`, subito prima di `separa_prestiti_nuovi` (che le usa), le due funzioni
   `_residuo_prestiti_nuovi` e `_quota_breve_prestiti_nuovi` di `forecast_engine.py`, rinominate `residuo_prestiti_nuovi`
   e `quota_breve_prestiti_nuovi`, con firma, corpo e docstring immutati. Unica modifica al corpo: in
   `quota_breve_prestiti_nuovi` la chiamata a `_residuo_prestiti_nuovi(loans, anno)` diventa
   `residuo_prestiti_nuovi(loans, anno)`. Se il corpo usa `new_financing_schedule`, e' gia' nello stesso modulo.
2. In `calculations/forecast_engine.py`: importa le cinque funzioni da `calculations.projection_common`; cancella le
   definizioni di `_residuo_prestiti_nuovi`, `_quota_breve_prestiti_nuovi`, `_e_contratto_pregresso`,
   `_ha_residuo_pregresso` e al loro posto scrivi gli alias

```python
# Le regole del debito bancario vivono in `projection_common` (lotto 3A, Task 3): questi nomi restano per
# chi li importa dal motore budget (test e helper del Task 2).
_ha_residuo_pregresso = e_contratto_pregresso
_e_contratto_pregresso = e_contratto_pregresso
_residuo_prestiti_nuovi = residuo_prestiti_nuovi
_quota_breve_prestiti_nuovi = quota_breve_prestiti_nuovi
```

3. In `assemble_financing`, nel ciclo su `financing_loans` di ogni riga: restano identici il controllo «opening_residual
   solo nel primo anno» e l'accumulo di `detailed_opening_total`; tutto cio' che segue (lettura di durata/tasso,
   `condizioni`, i due `append` del Ruling 45 e il `continue` su durata nulla) diventa
   `financing_loans.extend(contratti_da_riga_finanziamento(loan, a.forecast_year))`. Il commento lungo del Ruling 45 si
   riduce a una riga che rimanda a `projection_common.contratti_da_riga_finanziamento`. Il prestito legacy
   `financing_amount` resta com'e'.
4. In `_calculate_balance_sheet`: le due righe `nuovo_apertura = min(…)` e `sp17a_pregresso = sp17a - nuovo_apertura`
   diventano `sp17a_pregresso, nuovo_apertura = separa_prestiti_nuovi(sp17a, prestiti_nuovi, assumption.forecast_year)`.

**Constraints.** Zero divergenze sul banco. Nessun test esistente modificato. `forecast_engine.py` e `projection_common.py` sono LF.

**Ownership.** `calculations/projection_common.py`, `calculations/forecast_engine.py`,
`tests/test_projection_common_debito_bancario.py` (nuovo).

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task3-base`
- [ ] **Step 2: Test**, `tests/test_projection_common_debito_bancario.py` (numeri misurati sullo snapshot `452112d` con le
  funzioni del motore budget):

```python
"""Le tre regole del debito bancario vivono in `projection_common` e il motore budget le usa (lotto 3A, Task 3).

Numeri: la catena del prestito 100.000,38 / 4 anni / 4,35% erogato nel 2027, misurata sullo snapshot `452112d`
con `forecast_engine._residuo_prestiti_nuovi` e `_quota_breve_prestiti_nuovi`.
"""
from decimal import Decimal as D

import calculations.forecast_engine as motore_budget
import calculations.projection_common as comune

PRESTITO = [{"year": 2027, "amount": D("100000.38"), "duration": D("4"), "rate": D("0.0435")}]


def _funzione(nome):
    fn = getattr(comune, nome, None)
    assert callable(fn), f"projection_common.{nome} non esiste: la regola vive ancora solo nel motore budget"
    return fn


def test_un_contratto_misto_diventa_due_contratti_con_le_stesse_condizioni():
    dividi = _funzione("contratti_da_riga_finanziamento")
    riga = {"name": "Misto", "amount": 120000, "opening_residual": 12345.67, "duration_years": 4,
            "interest_rate": 5, "grace_years": 1, "balloon_pct": 10}
    condizioni = {"year": 2027, "duration": D("4"), "rate": D("0.05"), "grace_years": D("1"), "balloon_pct": D("10")}
    assert dividi(riga, 2027) == [
        {**condizioni, "amount": D("120000"), "opening_residual": D("0")},
        {**condizioni, "amount": D("0"), "opening_residual": D("12345.67")},
    ]
    assert dividi({"amount": 5000, "duration_years": 2}, 2028) == [
        {"year": 2028, "duration": D("2"), "rate": D("0"), "grace_years": D("0"), "balloon_pct": D("0"),
         "amount": D("5000"), "opening_residual": D("0")}]
    assert dividi({"amount": 5000, "opening_residual": 100, "duration_years": 0}, 2028) == []


def test_residuo_e_quota_a_breve_dei_prestiti_nuovi_sono_la_catena_persistita():
    residuo = _funzione("residuo_prestiti_nuovi")
    quota = _funzione("quota_breve_prestiti_nuovi")
    assert [residuo(PRESTITO, anno) for anno in (2026, 2027, 2028, 2029)] == [
        D("0"), D("75000.29"), D("50000.20"), D("25000.11")]
    assert quota(PRESTITO, 2027, D("75000.29")) == D("25000.09")
    assert quota(PRESTITO, 2029, D("25000.11")) == D("25000.09")
    assert quota(PRESTITO, 2027, D("5000.005")) == D("5000.00")


def test_la_separazione_toglie_al_debito_di_apertura_solo_la_catena_dei_nuovi():
    separa = _funzione("separa_prestiti_nuovi")
    assert separa(D("98457.08"), PRESTITO, 2028) == (D("23456.79"), D("75000.29"))
    assert separa(D("40000.00"), PRESTITO, 2028) == (D("0.00"), D("40000.00"))
    assert separa(D("12345.67"), [], 2028) == (D("12345.67"), D("0"))


def test_un_contratto_col_residuo_e_pregresso_uno_nuovo_no():
    pregresso = _funzione("e_contratto_pregresso")
    assert pregresso({"opening_residual": D("0.01")}) is True
    assert pregresso({"amount": D("1000"), "opening_residual": D("0")}) is False


def test_il_motore_budget_usa_le_funzioni_condivise_non_una_copia():
    assert motore_budget._residuo_prestiti_nuovi is getattr(comune, "residuo_prestiti_nuovi", None)
    assert motore_budget._quota_breve_prestiti_nuovi is getattr(comune, "quota_breve_prestiti_nuovi", None)
    assert motore_budget._e_contratto_pregresso is getattr(comune, "e_contratto_pregresso", None)
```

- [ ] **Step 3: Prova rossa.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_projection_common_debito_bancario.py -q -p no:cacheprovider`
  Atteso: 5 failed, sulle asserzioni «projection_common.… non esiste» e `is None`.
- [ ] **Step 4: Implementa** i punti 1-4.
- [ ] **Step 5: Verde.** Lo stesso comando: 5 passed. Poi, invariati:
  `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_sweep_piani.py tests/test_forecast_prestito_quota_breve.py tests/test_forecast_finanziamento_pregresso.py tests/test_forecast_dichiarato_vs_persistito.py tests/test_forecast_scoperto.py tests/test_forecast_residuo_sp16a_sp17a.py tests/test_budget_pregresso.py -q -p no:cacheprovider`
- [ ] **Step 6: Banco.** Comando delle convenzioni con `task3`. Atteso: uscita **0**, «NESSUNA DIVERGENZA», controllo
  negativo superato. Qualunque divergenza e' un difetto del refactor: si corregge, non si ammette.
- [ ] **Step 7: Commit.** `git add calculations/projection_common.py calculations/forecast_engine.py tests/test_projection_common_debito_bancario.py && git commit -m "refactor(engine): le regole del debito bancario in projection_common, motore budget invariato (lotto 3A, task 3)"`
- [ ] **Step 8: Rapporto** `task-3-report.md` (contenuto delle convenzioni).

**Observable acceptance.** 5 test nuovi verdi (rossi prima sulle asserzioni); banco a 0 divergenze con controllo
negativo superato; nessuna definizione con corpo di `_residuo_prestiti_nuovi` o `_quota_breve_prestiti_nuovi` resta in
`forecast_engine.py` (`grep -n "^def _residuo_prestiti_nuovi\|^def _quota_breve_prestiti_nuovi" calculations/forecast_engine.py` vuoto).

---

## Ondata B — infrannuale (in serie) e rendiconto (in parallelo)

### Task 4: L'infrannuale usa le regole condivise del debito bancario

**Esecutore:** pi (Orca) · **Revisore:** opus · **Ondata:** B, dopo il Task 3 (servono le funzioni condivise)

**Target (spec §4.2).** `IntraYearEngine._apply_debt_repayment` (in `calculations/intra_year_engine.py`) somma il prestito
nuovo al debito bancario e prende la sua rata «prima dal breve»: la prima rata di un prestito nuovo azzera il pregresso
a breve. Misurato (sonda p4, `sp16` bancario 12.345,67, prestito 120.000 / 4 anni / 5% erogato nell'anno):
oggi `sp16a` 0,00 e `sp17a` 102.345,67. `_financing_contracts` non divide il contratto misto. Dopo: il pregresso
conserva la propria ripartizione (le sue sole rate lo riducono, prima dal breve); il prestito nuovo si ammortizza per
conto suo, con la quota che scade l'anno dopo a breve: `sp16a` 42.345,67 (12.345,67 + 30.000,00), `sp17a` 60.000,00.
Il totale del debito, gli interessi e la cassa non cambiano.

**Da leggere prima, per simbolo, sul branch del lotto 3A:** in `calculations/intra_year_engine.py` `_financing_contracts`,
`IntraYearEngine._apply_debt_repayment`, e i due chiamanti (`_project_balance_sheet` e `_project_balance_sheet_annualized`,
righe `sp16a, sp17a, sp17b = self._apply_debt_repayment(`), piu' i due punti che calcolano `financing_interest` in
`_project_income_statement` e `_project_income_statement_annualized`. In `calculations/projection_common.py` le funzioni
del Task 3: `e_contratto_pregresso(loan) -> bool`, `contratti_da_riga_finanziamento(loan, anno) -> list[dict]`,
`residuo_prestiti_nuovi(loans, fino_al_anno) -> Decimal`, `quota_breve_prestiti_nuovi(loans, anno, lungo) -> Decimal`,
`separa_prestiti_nuovi(sp17a_apertura, prestiti_nuovi, anno) -> (pregresso, nuovo)`, oltre a `new_financing_schedule`,
`base_bank_debt`, `financial_repayment_instalment`, `altri_finanz_repayment_instalment`.

**Trappole note.**
- `intra_year_engine.py` ha terminatori **misti** CRLF+LF: non normalizzarlo; le righe nuove copiano quelle vicine;
  `git diff --stat` deve contare solo le righe cambiate.
- «Un solo motore di proiezione» (CLAUDE.md): la regola si usa dal codice condiviso, non si ricopia.
- Il messaggio «The sum of financing opening residuals must equal source bank debt» resta com'e' in questo task: lo
  traduce il Task 8.
- Gli interessi in `ce15` non cambiano: la divisione del misto e' lineare (misurato: stessi 6.617,2835 di interessi e
  33.086,4175 di rata col misto intero e diviso).

**Change (contratto).**
1. `_financing_contracts(assumption, include_opening=True)`: il prestito legacy `financing_amount` resta com'e'; ogni
   riga di `financing_loans` passa da `contratti_da_riga_finanziamento(loan, year)`; con `include_opening=False` si
   scartano i contratti per cui `e_contratto_pregresso` e' vero.
2. `_apply_debt_repayment(base_bs, sp16_bank, sp17_bank, sp17_altri, assumption)` — stessa firma, stesso valore di
   ritorno `(sp16a, sp17a, sp17b)`, aritmetica nuova:
   - `contratti = _financing_contracts(assumption, include_opening=True)`; `pregressi` = quelli con
     `e_contratto_pregresso`; `nuovi` = gli altri; `anno = int(assumption.forecast_year)`.
   - Pregresso per contratti (somma dei `opening_residual` > 0): stessa validazione di oggi contro `base_bank_debt`;
     `_, rata, _ = new_financing_schedule(pregressi, anno)`; `breve = min(sp16_bank, rata)`;
     `sp16_bank -= breve`; `sp17_bank = max(0, sp17_bank - (rata - breve))`.
   - Altrimenti: il piano ad anni di oggi (`financial_repayment_instalment`, prima dal breve), invariato.
   - Altri finanziatori: invariato.
   - Nuovi: `sp17_bank, nuovo_apertura = separa_prestiti_nuovi(sp17_bank, nuovi, anno)` (nell'infrannuale il residuo
     nuovo di apertura e' zero: i contratti nascono nell'anno proiettato, ma la funzione condivisa si usa lo stesso);
     `erogato, rimborso, _ = new_financing_schedule(nuovi, anno)`;
     `residuo_nuovo = max(0, nuovo_apertura + erogato - rimborso)`;
     `quota = quota_breve_prestiti_nuovi(nuovi, anno, residuo_nuovo)`;
     ritorna `(sp16_bank + quota, sp17_bank + residuo_nuovo - quota, sp17_altri)`.
   - La rata del prestito nuovo non tocca mai `sp16_bank` ne' il `sp17_bank` pregresso.

**Constraints.** Motore budget non toccato: banco a 0 divergenze. Cassa, `ce15` e totale del debito bancario
dell'infrannuale invariati negli scenari dei test; si muove solo la ripartizione `sp16a`/`sp17a`.

**Ownership.** `calculations/intra_year_engine.py`, `tests/test_intra_year_debito_bancario.py` (nuovo),
`CLAUDE.md`, `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md`.

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task4-base`
- [ ] **Step 2: Test**, `tests/test_intra_year_debito_bancario.py` (numeri dello snapshot `452112d`; gli attesi sono la
  regola del motore budget applicata con le sue funzioni):

```python
"""L'infrannuale separa il debito bancario pregresso dal prestito nuovo, con la quota a breve (lotto 3A, Task 4).

Oggi la prima rata di un prestito nuovo azzera il pregresso a breve: con 12.345,67 di pregresso e un prestito di
120.000 / 4 anni / 5% erogato nell'anno, `sp16a` 0,00 e `sp17a` 102.345,67. Dopo: il pregresso resta, il prestito
nuovo mette a breve la rata dell'anno dopo (30.000,00) e a lungo il resto (60.000,00).
"""
from decimal import ROUND_HALF_UP, Decimal as D
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)

BREVE = D("12345.67")
NUOVO = dict(financing_amount=D("120000"), financing_duration_years=D("4"), financing_interest_rate=D("5"))
MISTO = [{"name": "Misto", "amount": 120000, "opening_residual": 12345.67, "duration_years": 4, "interest_rate": 5}]
DUE_RIGHE = [
    {"name": "Nuovo", "amount": 120000, "opening_residual": 0, "duration_years": 4, "interest_rate": 5},
    {"name": "Pregresso", "amount": 0, "opening_residual": 12345.67, "duration_years": 4, "interest_rate": 5},
]


def _q(x):
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def _base():
    campi = {f: D("0") for f in (
        "sp16b_debiti_altri_finanz_breve", "sp16c_debiti_obbligazioni_breve", "sp16d_debiti_fornitori_breve",
        "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve", "sp16g_altri_debiti_breve",
        "sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo", "sp17c_debiti_obbligazioni_lungo",
        "sp17d_debiti_fornitori_lungo", "sp17e_debiti_tributari_lungo", "sp17f_debiti_previdenza_lungo",
        "sp17g_altri_debiti_lungo", "sp17_debiti_lungo")}
    return SimpleNamespace(sp16a_debiti_banche_breve=BREVE, sp16_debiti_breve=BREVE, **campi)


def _ipotesi(**extra):
    valori = dict(forecast_year=2027, financing_amount=D("0"), financing_duration_years=D("0"),
                  financing_interest_rate=D("0"), financing_loans=None, existing_debt_repayment_years=None,
                  altri_finanz_repayment_years=None)
    valori.update(extra)
    return SimpleNamespace(**valori)


def _rimborso(**extra):
    motore = IntraYearEngine.__new__(IntraYearEngine)
    sp16a, sp17a, sp17b = motore._apply_debt_repayment(_base(), BREVE, D("0"), D("0"), _ipotesi(**extra))
    return _q(sp16a), _q(sp17a), _q(sp17b)


def test_la_rata_del_prestito_nuovo_non_consuma_il_pregresso_a_breve():
    assert _rimborso(**NUOVO) == (D("42345.67"), D("60000.00"), D("0.00"))


@pytest.mark.parametrize("prestiti", [MISTO, DUE_RIGHE], ids=["contratto misto", "due righe"])
def test_il_contratto_misto_e_le_due_righe_danno_gli_stessi_numeri_giusti(prestiti):
    # Pregresso: rata 12.345,67 / 4 = 3.086,4175 dal breve → 9.259,2525; nuovo: 30.000,00 a breve, 60.000,00 a lungo.
    assert _rimborso(financing_loans=prestiti) == (D("39259.25"), D("60000.00"), D("0.00"))


@pytest.mark.parametrize("piano", [{}, {"existing_debt_repayment_years": D("3")}], ids=["senza piano", "anni di rimborso 3"])
def test_i1_esteso_la_componente_pregressa_e_la_stessa_con_e_senza_prestito_nuovo(piano):
    motore = IntraYearEngine.__new__(IntraYearEngine)
    senza = motore._apply_debt_repayment(_base(), BREVE, D("0"), D("0"), _ipotesi(**piano))
    con = motore._apply_debt_repayment(_base(), BREVE, D("0"), D("0"), _ipotesi(**piano, **NUOVO))
    assert _q(con[0] - D("30000.00")) == _q(senza[0])
    assert _q(con[1] - D("60000.00")) == _q(senza[1])


def _sessione():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _proietta(**ipotesi):
    db = _sessione()
    azienda = Company(name="Banca infra", tax_id="BANCA-INFRA", sector=1)
    db.add(azienda)
    db.flush()
    stato = dict(sp09_disponibilita_liquide=D("201000"), sp11_capitale=D("188654.33"),
                 sp16_debiti_breve=BREVE, sp16a_debiti_banche_breve=BREVE)
    for anno, mesi in ((2024, None), (2025, 9)):
        fy = FinancialYear(company_id=azienda.id, year=anno, period_months=mesi,
                           validation_status="verified", forecastable=True)
        db.add(fy)
        db.flush()
        db.add(BalanceSheet(financial_year_id=fy.id, **stato))
        db.add(IncomeStatement(financial_year_id=fy.id))
    scenario = BudgetScenario(company_id=azienda.id, name="infra", base_year=2024,
                              scenario_type="infrannuale", period_months=9)
    db.add(scenario)
    db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"), **ipotesi))
    db.commit()
    IntraYearEngine(db).generate_projection(scenario.id)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    return sp.sp16a_debiti_banche_breve, sp.sp17a_debiti_banche_lungo, sp.sp09_disponibilita_liquide


@pytest.mark.parametrize("ipotesi, attesi", [
    ({}, ("12345.67", "0.00", "201000.00")),
    (NUOVO, ("42345.67", "60000.00", "285000.00")),
    ({"financing_loans": MISTO}, ("39259.25", "60000.00", "281296.30")),
    ({"financing_loans": DUE_RIGHE}, ("39259.25", "60000.00", "281296.30")),
], ids=["solo pregresso", "prestito nuovo", "contratto misto", "due righe"])
def test_la_proiezione_persiste_la_ripartizione_e_la_cassa_non_cambia(ipotesi, attesi):
    """Oggi: prestito nuovo 0,00 / 102.345,67, misto e due righe 0,00 / 99.259,25; cassa 285.000,00 e 281.296,30."""
    assert _proietta(**ipotesi) == tuple(D(v) for v in attesi)
```

- [ ] **Step 3: Prova rossa.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_intra_year_debito_bancario.py -q -p no:cacheprovider`
  Atteso: falliscono sulle asserzioni i casi con prestito nuovo o misto (unitari ed end-to-end) e il caso I1 «senza
  piano»; passano «solo pregresso» end-to-end. Se il caso I1 «anni di rimborso 3» passa gia', annotalo nel rapporto.
- [ ] **Step 4: Implementa** i punti 1-2.
- [ ] **Step 5: Verde.** Lo stesso comando, tutto verde; poi
  `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_intra_year_semantics.py tests/test_intra_year_plug_negativo.py tests/test_intra_year_end_to_end_periods.py tests/test_budget_remediation_plan.py -q -p no:cacheprovider`
- [ ] **Step 6: Documenti.** `CLAUDE.md`, «Intra-Year Engine (Infrannuale)», bullet «Projection»: aggiungi alla fine
  «Bank debt follows the budget engine's rules from the shared code (`projection_common.contratti_da_riga_finanziamento`,
  `separa_prestiti_nuovi`, `quota_breve_prestiti_nuovi`): pre-existing bank debt keeps its own split and is reduced only by
  its own instalments, a new loan amortises on its own with next year's instalment in `sp16a`.»
  `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §5, tabella del roll-forward: la riga «Debiti a lungo» diventa
  «**solo movimenti espliciti**: rimborsi e nuovi finanziamenti; la rata del prestito nuovo che scade l'anno dopo sta
  nei debiti a breve, e il debito bancario pregresso si riduce solo con le proprie rate»; e nella sezione «La rata di
  rimborso» aggiungi un paragrafo con lo stesso contenuto e i numeri del test (12.345,67 pregresso; 30.000,00 / 60.000,00).
- [ ] **Step 7: Banco.** Comando delle convenzioni con `task4`. Atteso: uscita 0 (il banco usa solo il motore budget).
- [ ] **Step 8: Commit.** `git add calculations/intra_year_engine.py tests/test_intra_year_debito_bancario.py CLAUDE.md docs/import/REGOLE-IMPORT-05-INFRANNUALE.md && git commit -m "fix(infrannuale): il prestito nuovo non consuma il debito bancario pregresso e ha la sua quota a breve (lotto 3A, task 4)"`
- [ ] **Step 9: Rapporto** `task-4-report.md`.

**Observable acceptance.** Test nuovi verdi (rossi prima sulle asserzioni); suite dell'infrannuale verde; banco a 0
divergenze; `git diff --stat` di `intra_year_engine.py` limitato alle righe cambiate.

---

### Task 5: L'infrannuale chiude le imposte al 31/12 col solo saldo dell'anno

**Esecutore:** pi (Orca) · **Revisore:** opus · **Ondata:** B, dopo il Task 4 (stesso file `intra_year_engine.py`)

**Target (spec §4.3, decisione 4 del proprietario).** `projection_common.tax_closing_position`, usata dai due rami di
`IntraYearEngine` che proiettano lo stato patrimoniale, somma l'imposta dei mesi restanti al debito tributario di
apertura meno gli acconti e non paga mai nulla: misurato 1.150.949,04 → 1.171.701,78, e un secondo anno 1.251.701,78.
Il budget che nasce dal promote eredita il debito gonfiato (misurato: `details['imposte']['saldo_paid']` 1.171.701,78
nel primo anno di budget). Dopo:
- posizione netta a fine anno = imposta dell'anno − acconti versati nell'anno; positiva → `sp16e`, negativa → credito `sp06e`;
- acconti = `tax_advances_paid` se **maggiore di zero**, altrimenti il 100% dell'imposta dell'anno di riferimento
  (`ce20_imposte` del riferimento; senza anno di riferimento, zero);
- uscita di cassa = posizione netta di apertura + imposta residua dell'anno − posizione netta di fine anno (cio' che il
  parziale ha gia' versato sta gia' nella posizione di apertura); nel motore la cassa resta il plug, quindi l'uscita la
  dichiara il kernel e la verifica il test end-to-end;
- le rate tributarie oltre l'anno (`sp17e`) restano intatte;
- la regola sugli acconti e' una funzione sola, usata anche da `tax_settlement_saldo_acconto` del budget.

**Da leggere prima, per simbolo, sul branch del lotto 3A:** in `calculations/projection_common.py`
`tax_closing_position`, `TaxYear`, `tax_settlement_saldo_acconto` (il giro finale del lotto 2 puo' averne toccato i
chiamanti: rileggili); in `calculations/intra_year_engine.py` `_tax_components` e, dentro `_project_balance_sheet` e
`_project_balance_sheet_annualized`, il blocco `if not manual_tax_position:` che chiama `tax_closing_position`.
`backend/app/services/promote_service.py::promote_projection_to_financial_year` (solo lettura).

**Trappole note.**
- Zero in `tax_advances_paid` vuol dire «non dichiarato» (colonna NOT NULL default 0), in entrambi i motori.
- La via manuale (`sp06e_growth_pct` o `sp16e_growth_pct` valorizzati) salta la posizione automatica: non cambia.
- `intra_year_engine.py` ha terminatori misti: niente normalizzazione, `git diff --stat` solo sulle righe cambiate.
- Il banco confronta il motore budget: il refactor degli acconti in `tax_settlement_saldo_acconto` deve dare 0 divergenze.

**Change.**
1. `calculations/projection_common.py`: cancella `tax_closing_position`; subito prima di `TaxYear` aggiungi

```python
def acconti_dovuti(explicit_advances, reference_tax, acconto_pct=Decimal('100')) -> Decimal:
    """Gli acconti dell'anno: l'importo esplicito se maggiore di zero, altrimenti la percentuale dell'imposta di riferimento.

    Zero (il default di colonna di `tax_advances_paid`) e un negativo valgono «non dichiarato». Regola unica dei due
    motori: il budget la chiama con l'imposta dell'anno prima, l'infrannuale con l'imposta dell'anno di riferimento.
    """
    d = lambda v: Decimal(str(v or 0))
    if d(explicit_advances) > ZERO:
        return d(explicit_advances)
    return max(ZERO, d(reference_tax) * d(acconto_pct) / Decimal('100'))


@dataclass(frozen=True)
class PosizioneTributariaFineAnno:
    closing_credit: Decimal
    closing_debt: Decimal
    acconti: Decimal
    cash_out: Decimal


def posizione_tributaria_fine_anno(*, opening_credit, opening_debt, remaining_current_tax, current_tax,
                                   reference_tax, explicit_advances) -> PosizioneTributariaFineAnno:
    """La posizione tributaria al 31/12 dell'infrannuale (spec lotto 3A §4.3, decisione 4 del proprietario).

    Al 31/12 resta solo il saldo dell'anno in corso: imposta dell'anno meno acconti versati nell'anno. Quanto era
    aperto al mese del parziale esce di cassa entro fine anno: `cash_out` = posizione netta di apertura + imposta
    che matura nei mesi restanti − posizione netta di fine anno. Il budget che nasce dal promote scadenzia quel saldo.
    """
    d = lambda v: Decimal(str(v or 0))
    acconti = acconti_dovuti(explicit_advances, reference_tax)
    netto_fine = d(current_tax) - acconti
    netto_apertura = d(opening_debt) - d(opening_credit)
    return PosizioneTributariaFineAnno(
        closing_credit=max(ZERO, -netto_fine),
        closing_debt=max(ZERO, netto_fine),
        acconti=acconti,
        cash_out=netto_apertura + d(remaining_current_tax) - netto_fine,
    )
```

   In `tax_settlement_saldo_acconto` sostituisci il ramo `if d(explicit_advances) > ZERO: … else: …` con
   `acconti = acconti_dovuti(explicit_advances, previous_tax, acconto_pct)` e aggiorna il docstring: togli «Solo il
   motore budget: l'infrannuale continua a usare tax_closing_position.» e scrivi che la regola degli acconti e'
   `acconti_dovuti`, condivisa con `posizione_tributaria_fine_anno`.
2. `calculations/intra_year_engine.py`: nell'import da `projection_common` sostituisci `tax_closing_position` con
   `posizione_tributaria_fine_anno`. In `_project_balance_sheet` (ramo con riferimento) il blocco diventa

```python
            posizione = posizione_tributaria_fine_anno(
                opening_credit=_get_field(partial_bs, 'sp06e_crediti_tributari_breve'),
                opening_debt=_get_field(partial_bs, 'sp16e_debiti_tributari_breve'),
                remaining_current_tax=remaining_current_tax,
                current_tax=current_tax,
                reference_tax=_get_field(ref_inc, 'ce20_imposte'),
                explicit_advances=getattr(assumption, 'tax_advances_paid', None),
            )
            sp06e, sp16e = posizione.closing_credit, posizione.closing_debt
```

   e in `_project_balance_sheet_annualized` lo stesso con `reference_tax=Decimal('0')` e un commento: «Senza anno di
   riferimento l'imposta su cui commisurare gli acconti non esiste: zero, cioe' tutta l'imposta dell'anno resta da
   versare al 31/12 (il lato prudente), mai un acconto inventato.»

**Constraints.** Banco a 0 divergenze. `sp17e` non si tocca. Nessun cambio a `promote_service.py`.

**Ownership.** `calculations/projection_common.py`, `calculations/intra_year_engine.py`,
`tests/test_intra_year_imposte.py` (nuovo), `tests/test_budget_remediation_plan.py`, `CLAUDE.md`,
`docs/budget/API-PREVISIONALE.md`, `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md`.

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task5-base`
- [ ] **Step 2: Test**, `tests/test_intra_year_imposte.py` (end-to-end misurato sullo snapshot `452112d`: oggi
  `sp16e` 1.270.949,04 / 1.270.949,04 / 1.171.701,78 e cassa 3.150.949,04 / 3.150.949,04 / 3.051.701,78 nei tre casi):

```python
"""Al 31/12 l'infrannuale lascia solo il saldo d'imposta dell'anno (lotto 3A, Task 5, decisione 4 del proprietario)."""
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import calculations.projection_common as comune
from backend.app.services import assumptions_service, forecast_preview_service
from backend.app.services.promote_service import promote_projection_to_financial_year
from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)

APERTURA = D("1150949.04")


def _kernel():
    fn = getattr(comune, "posizione_tributaria_fine_anno", None)
    assert callable(fn), "projection_common.posizione_tributaria_fine_anno non esiste"
    return fn


def test_i_numeri_della_sonda_sono_quelli_del_kernel_budget():
    p = _kernel()(opening_credit=0, opening_debt=APERTURA, remaining_current_tax=D("120000"),
                  current_tax=D("120000"), reference_tax=D("0"), explicit_advances=D("99247.26"))
    assert (p.closing_debt, p.closing_credit, p.acconti, p.cash_out) == (
        D("20752.74"), D("0"), D("99247.26"), D("1250196.30"))
    budget = comune.tax_settlement_saldo_acconto(opening_credit=0, saldo_due=APERTURA, rate_due=0,
                                                 current_tax=D("120000"), previous_tax=0, acconto_pct=D("100"),
                                                 explicit_advances=D("99247.26"))
    assert (budget.generated_debt, budget.cash_out) == (p.closing_debt, p.cash_out)


@pytest.mark.parametrize("dichiarati", [D("0"), D("-5")], ids=["zero", "negativo"])
def test_acconti_non_dichiarati_valgono_il_cento_per_cento_dell_imposta_di_riferimento(dichiarati):
    p = _kernel()(opening_credit=0, opening_debt=APERTURA, remaining_current_tax=D("120000"),
                  current_tax=D("120000"), reference_tax=D("80000"), explicit_advances=dichiarati)
    assert (p.acconti, p.closing_debt, p.cash_out) == (D("80000"), D("40000"), D("1230949.04"))


def test_una_posizione_negativa_diventa_credito():
    p = _kernel()(opening_credit=0, opening_debt=APERTURA, remaining_current_tax=D("120000"),
                  current_tax=D("120000"), reference_tax=D("150000"), explicit_advances=0)
    assert (p.closing_credit, p.closing_debt, p.cash_out) == (D("30000"), D("0"), D("1300949.04"))


def test_il_credito_di_apertura_e_l_imposta_gia_maturata_non_si_ripagano():
    con_credito = _kernel()(opening_credit=D("50000"), opening_debt=0, remaining_current_tax=D("120000"),
                            current_tax=D("120000"), reference_tax=0, explicit_advances=D("99247.26"))
    assert (con_credito.closing_debt, con_credito.cash_out) == (D("20752.74"), D("49247.26"))
    maturata = _kernel()(opening_credit=0, opening_debt=D("30000"), remaining_current_tax=D("30000"),
                         current_tax=D("120000"), reference_tax=0, explicit_advances=D("99247.26"))
    assert (maturata.closing_debt, maturata.cash_out) == (D("20752.74"), D("39247.26"))


def _sessione():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _infrannuale(db, imposta_riferimento, acconti):
    """Riferimento 2024 con imposta R e 1.000.000 di debito tributario; parziale 2025 (9 mesi) con 1.150.949,04."""
    azienda = Company(name="Imposte infra", tax_id="IMPOSTE-INFRA", sector=1)
    db.add(azienda)
    db.flush()
    anni = (
        (2024, None, dict(sp11_capitale=D("1000"), sp13_utile_perdita=-imposta_riferimento,
                          sp16_debiti_breve=D("1000000"), sp16e_debiti_tributari_breve=D("1000000"),
                          sp09_disponibilita_liquide=D("1000") - imposta_riferimento + D("1000000")),
         dict(ce20_imposte=imposta_riferimento)),
        (2025, 9, dict(sp11_capitale=D("2000000"), sp13_utile_perdita=D("0"), sp16_debiti_breve=APERTURA,
                       sp16e_debiti_tributari_breve=APERTURA, sp09_disponibilita_liquide=D("2000000") + APERTURA), {}),
    )
    for anno, mesi, stato, conto in anni:
        fy = FinancialYear(company_id=azienda.id, year=anno, period_months=mesi,
                           validation_status="verified", forecastable=True)
        db.add(fy)
        db.flush()
        db.add(BalanceSheet(financial_year_id=fy.id, **stato))
        db.add(IncomeStatement(financial_year_id=fy.id, **conto))
    scenario = BudgetScenario(company_id=azienda.id, name="infra", base_year=2024,
                              scenario_type="infrannuale", period_months=9)
    db.add(scenario)
    db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"),
                             ce20_override=D("120000"), tax_advances_paid=acconti))
    db.commit()
    IntraYearEngine(db).generate_projection(scenario.id)
    return azienda, scenario


@pytest.mark.parametrize("riferimento, acconti, attesi", [
    (D("80000"), D("0"), ("40000.00", "0.00", "1920000.00")),
    (D("150000"), D("0"), ("0.00", "30000.00", "1850000.00")),
    (D("80000"), D("99247.26"), ("20752.74", "0.00", "1900752.74")),
], ids=["acconti non dichiarati", "posizione a credito", "acconti dichiarati"])
def test_la_proiezione_persiste_il_solo_saldo_e_paga_il_resto_di_cassa(riferimento, acconti, attesi):
    db = _sessione()
    _azienda, scenario = _infrannuale(db, riferimento, acconti)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    assert (sp.sp16e_debiti_tributari_breve, sp.sp06e_crediti_tributari_breve, sp.sp09_disponibilita_liquide) == tuple(
        D(v) for v in attesi)


def test_il_budget_nato_dal_promote_non_eredita_il_debito_dell_anno_prima():
    db = _sessione()
    azienda, scenario = _infrannuale(db, D("80000"), D("99247.26"))
    promote_projection_to_financial_year(db, scenario.id)
    budget = BudgetScenario(company_id=azienda.id, name="budget", base_year=2025, scenario_type="budget")
    db.add(budget)
    db.commit()
    righe = [{"forecast_year": 2026, "revenue_growth_pct": 0, "tax_rate": 27.9}]
    esito = assumptions_service.bulk_upsert_assumptions(db, budget.id, [dict(r) for r in righe], auto_generate=True)
    assert esito["forecast_generated"] is True, esito["message"]
    anteprima = forecast_preview_service.preview_forecast(db, budget.id, [dict(r) for r in righe])
    assert D(str(anteprima["forecast_years"][0]["details"]["imposte"]["saldo_paid"])) == D("20752.74")
```

- [ ] **Step 3: Prova rossa.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_intra_year_imposte.py -q -p no:cacheprovider`
  Atteso: i test del kernel falliscono su «posizione_tributaria_fine_anno non esiste», i tre end-to-end sui valori di
  `sp16e`/cassa, la catena sul `saldo_paid` 1.171.701,78. Se la catena fallisce prima (per esempio `forecast_generated`
  falso), riporta il messaggio nel rapporto: sul branch del lotto 3A il riallineamento del lotto 2 puo' averlo cambiato.
- [ ] **Step 4: Implementa** i punti 1-2. In `tests/test_budget_remediation_plan.py` togli `tax_closing_position`
  dall'import e sostituisci `test_tax_settlement_reclassifies_overpayment_without_negative_balances` con:

```python
def test_tax_year_end_position_reclassifies_overpayment_without_negative_balances():
    from calculations.projection_common import posizione_tributaria_fine_anno as posizione

    sopra = posizione(opening_credit=0, opening_debt=0, remaining_current_tax=D("30"), current_tax=D("30"),
                      reference_tax=0, explicit_advances=D("100"))
    assert (sopra.closing_credit, sopra.closing_debt) == (D("70"), D("0"))
    sotto = posizione(opening_credit=0, opening_debt=0, remaining_current_tax=D("30"), current_tax=D("30"),
                      reference_tax=0, explicit_advances=D("10"))
    assert (sotto.closing_credit, sotto.closing_debt) == (D("0"), D("20"))
```

- [ ] **Step 5: Verde.** Il comando dello Step 3, poi
  `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_budget_remediation_plan.py tests/test_intra_year_semantics.py tests/test_intra_year_plug_negativo.py tests/test_intra_year_end_to_end_periods.py tests/test_intra_year_debito_bancario.py tests/test_budget_pregresso.py tests/test_forecast_dichiarato_vs_persistito.py -q -p no:cacheprovider`
  e `grep -rn "tax_closing_position" calculations backend tests` vuoto.
- [ ] **Step 6: Documenti.**
  - `CLAUDE.md`, «Intra-Year Engine», bullet «Projection»: «taxes are recomputed on projected pre-tax profit» diventa
    «taxes are recomputed on projected pre-tax profit, and at 31/12 only the current year's balance remains: tax of the
    year minus the advances paid in the year (`tax_advances_paid` if greater than zero, otherwise 100% of the reference
    year's `ce20`); whatever was open at the partial month leaves cash by year end
    (`projection_common.posizione_tributaria_fine_anno`), so a budget born from the promote no longer inherits it».
  - `docs/budget/API-PREVISIONALE.md` §9: «l'infrannuale continua a usare `tax_closing_position`, invariata» diventa
    «l'infrannuale usa `posizione_tributaria_fine_anno`, con la stessa regola degli acconti (`acconti_dovuti`)»; in §5
    (promote) aggiungi: «La proiezione promossa porta a `sp16e` il solo saldo dell'anno proiettato: il primo anno di budget
    lo versa come saldo (`details['imposte']['saldo_paid']`).»
  - `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §4, «Imposte»: aggiungi un paragrafo con la regola, la formula
    dell'uscita di cassa e i numeri del test (1.150.949,04 di apertura, 120.000 di imposta, 99.247,26 di acconti →
    20.752,74 a `sp16e`, 1.250.196,30 di uscita).
- [ ] **Step 7: Banco.** Comando delle convenzioni con `task5`. Atteso: uscita 0.
- [ ] **Step 8: Commit.** `git add calculations/projection_common.py calculations/intra_year_engine.py tests/test_intra_year_imposte.py tests/test_budget_remediation_plan.py CLAUDE.md docs/budget/API-PREVISIONALE.md docs/import/REGOLE-IMPORT-05-INFRANNUALE.md && git commit -m "fix(infrannuale): al 31/12 resta solo il saldo d'imposta dell'anno, il resto esce di cassa (lotto 3A, task 5)"`
- [ ] **Step 9: Rapporto** `task-5-report.md`.

**Observable acceptance.** 9 test nuovi verdi (rossi prima sulle asserzioni); banco a 0 divergenze; nessun uso residuo
di `tax_closing_position`.

---

### Task 6: Il rendiconto conta i dividendi incassati e dichiara lo scarto dei mezzi di terzi

**Esecutore:** pi (Orca) · **Revisore:** sonnet · **Ondata:** B, in parallelo ai Task 3-5 su un worktree suo (non tocca i motori)

**Target (spec §4.4).** In `backend/app/calculations/cashflow_detailed.py`, `DetailedCashFlowCalculator.calculate`
sottrae `ce13_proventi_partecipazioni` dall'utile nel primo blocco (`profit_before_adjustments = net_profit + income_taxes
+ interest_expense_income - dividends + …`) e poi lascia `dividends_received = Decimal("0")`: i dividendi escono dal
flusso operativo e non rientrano mai. Il netto dei mezzi di terzi (`debt_net`, calcolato per residuo) assorbe l'errore
in silenzio. Misurato sulla holding del kit (`ce13` 30.000, 2027 e 2028): operativo −10.000,00, mezzi di terzi
30.000,00 contro una variazione misurata del debito finanziario di 0,00, scarto 30.000,00. Dopo: dividendi incassati
30.000,00, operativo 20.000,00, mezzi di terzi 0,00, e un campo nuovo della riconciliazione dichiara lo scarto (0,00).
`backend/app/calculations/cashflow.py` (anni storici) parte da `inc_current.net_profit`, che contiene gia' `ce13`, e non
lo sottrae mai: **non si modifica** (lo si scrive nel rapporto).

**Da leggere prima:** `backend/app/calculations/cashflow_detailed.py` (`calculate`, le variabili `dividends`,
`dividends_received`, `delta_total_debt`, `debt_net`, la costruzione di `CashReconciliation`),
`backend/app/schemas/cashflow_detailed.py` (`CashReconciliation`), `frontend/types/api.ts` (`interface CashReconciliation`),
`tests/test_cashflow_debito_finanziario.py` (docstring del modulo e di
`test_il_residuo_dei_mezzi_di_terzi_uguaglia_il_debito_finanziario_misurato`).

**Trappole note.**
- Tre file **interamente CRLF**: `backend/app/calculations/cashflow_detailed.py`, `backend/app/schemas/cashflow_detailed.py`,
  `frontend/types/api.ts`. Dopo la modifica riportali a CRLF con
  `/home/peter/DEV/budget/backend/venv/bin/python -c "import sys;p=sys.argv[1];b=open(p,'rb').read().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n');open(p,'wb').write(b)" <percorso>`
  e controlla con `git diff --stat` che contino solo le righe cambiate.
- Diagnose, never fabricate: lo scarto si **dichiara**; `debt_net` resta il residuo che fa quadrare la cassa.
- «Cassa del rendiconto = variazione di `sp09`» non prova nulla (il residuo quadra per costruzione): la prova e' lo scarto a zero.

**Change.**
1. `cashflow_detailed.py`: la riga `dividends_received = Decimal("0")` e il suo commento diventano

```python
        # Dividends received (OIC 10): `ce13` was taken out of profit above as a non-operating item
        # (`profit_before_adjustments`); in the projection it is cash — nothing books it as a
        # receivable — so it comes back here. Left at zero it silently moved into third-party funds.
        dividends_received = dividends
```

   e, subito prima della costruzione di `CashReconciliation`:

```python
        # Declared, never corrected: third-party funds are a residual, so any movement this statement
        # does not classify ends up there. Zero means the residual IS the measured change in financial debt.
        third_party_funds_gap = debt_net - delta_total_debt
```

   con `third_party_funds_gap=R(third_party_funds_gap)` fra gli argomenti di `CashReconciliation(...)`.
2. `backend/app/schemas/cashflow_detailed.py`, in `CashReconciliation`, dopo `verification_ok`:

```python
    third_party_funds_gap: Decimal = Field(
        default=Decimal("0"),
        description="Scarto fra i mezzi di terzi calcolati per residuo e la variazione misurata del debito finanziario (dichiarato, non corretto)",
    )
```

3. `frontend/types/api.ts`, in `interface CashReconciliation`, dopo `verification_ok: boolean;`: `third_party_funds_gap: number;`
4. `tests/test_cashflow_debito_finanziario.py`: nell'ultimo paragrafo del docstring del modulo (quello che misura lo
   scarto costante di 30.000,00 / 32.194,80 sulla holding e lo dichiara «fuori dal perimetro di F1: dichiarato qui, non
   corretto») aggiungi in coda «Corretto dal lotto 3A (Task 6): `dividends_received` rimette `ce13` nell'operativo e lo
   scarto e' zero anche sulla holding (`tests/test_cashflow_dividendi.py`).»; nel docstring di
   `test_il_residuo_dei_mezzi_di_terzi_uguaglia_il_debito_finanziario_misurato` togli «vedi il docstring del modulo per
   dove NON lo e' (fixture holding, fuori perimetro)».

**Constraints.** Nessun motore toccato: banco a 0 divergenze. `cashflow.py` invariato. I numeri del caso A di
`tests/test_cashflow_debito_finanziario.py` (operativo 76.191,19, finanziario 75.000,29) non cambiano: quel kit non ha `ce13`.

**Ownership.** `backend/app/calculations/cashflow_detailed.py`, `backend/app/schemas/cashflow_detailed.py`,
`frontend/types/api.ts`, `tests/test_cashflow_dividendi.py` (nuovo), `tests/test_cashflow_debito_finanziario.py`,
`docs/budget/API-PREVISIONALE.md`.

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task6-base`
- [ ] **Step 2: Test**, `tests/test_cashflow_dividendi.py` (numeri misurati sullo snapshot `452112d`):

```python
"""Il rendiconto dettagliato rimette i dividendi nell'operativo e dichiara lo scarto dei mezzi di terzi (lotto 3A, Task 6).

Holding del kit (`ce13` 30.000): oggi operativo −10.000,00, mezzi di terzi 30.000,00, debito finanziario misurato 0,00.
Kit senza partecipazioni: operativo 80.541,22 (2027) e 125.893,62 (2028), scarto zero, e tale resta.
"""
from decimal import Decimal as D

from backend.app.calculations.cashflow_detailed import DetailedCashFlowCalculator
from backend.app.services import assumptions_service
from database.models import BudgetScenario, FinancialYear, ForecastYear
from tests.e2e_kit import memory_sessions, seed_base_year


def _rendiconti(holding):
    engine, sessions = memory_sessions()
    db = sessions()
    try:
        company_id, fy_id = seed_base_year(db, user_id=f"dividendi-{holding}", holding=holding)
        base = db.query(FinancialYear).get(fy_id)
        scenario = BudgetScenario(company_id=company_id, name="dividendi", base_year=2026, scenario_type="budget")
        db.add(scenario)
        db.commit()
        righe = [dict(forecast_year=anno, revenue_growth_pct=3.33, tax_rate=27.9) for anno in (2027, 2028)]
        esito = assumptions_service.bulk_upsert_assumptions(db, scenario.id, righe, auto_generate=True)
        assert esito["forecast_generated"] is True, esito["message"]
        precedente, rendiconti = base.balance_sheet, {}
        for anno in (2027, 2028):
            fy = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id, ForecastYear.year == anno).one()
            rendiconti[anno] = DetailedCashFlowCalculator.calculate(
                bs_current=fy.balance_sheet, bs_previous=precedente, inc_current=fy.income_statement, year=anno)
            precedente = fy.balance_sheet
        return rendiconti
    finally:
        db.close()
        engine.dispose()


def test_sulla_holding_i_dividendi_incassati_stanno_nell_operativo_e_lo_scarto_e_zero():
    fuori = []
    for anno, cf in _rendiconti(holding=True).items():
        op, rec = cf.operating_activities, cf.cash_reconciliation
        confronti = {
            "dividendi sottratti all'utile": (op.start.dividends, "30000.00"),
            "dividendi incassati": (op.cash_adjustments.dividends_received, "30000.00"),
            "flusso operativo": (op.total_operating_cashflow, "20000.00"),
            "mezzi di terzi": (cf.financing_activities.third_party_funds.net, "0.00"),
            "scarto dichiarato": (getattr(rec, "third_party_funds_gap", None), "0.00"),
            "variazione di cassa del rendiconto": (rec.total_cashflow, "20000.00"),
        }
        fuori += [f"{anno} {k}: {v}, atteso {a}" for k, (v, a) in confronti.items() if v != D(a)]
        if rec.total_cashflow != rec.difference:
            fuori.append(f"{anno} controllo di sanita': rendiconto {rec.total_cashflow} != variazione sp09 {rec.difference}")
    assert not fuori, "\n".join(fuori)


def test_senza_partecipazioni_nulla_cambia_e_lo_scarto_e_dichiarato_a_zero():
    attesi = {2027: "80541.22", 2028: "125893.62"}
    fuori = []
    for anno, cf in _rendiconti(holding=False).items():
        op, rec = cf.operating_activities, cf.cash_reconciliation
        if op.total_operating_cashflow != D(attesi[anno]):
            fuori.append(f"{anno} operativo {op.total_operating_cashflow}, atteso {attesi[anno]}")
        if op.cash_adjustments.dividends_received != D("0.00"):
            fuori.append(f"{anno} dividendi incassati {op.cash_adjustments.dividends_received}")
        if getattr(rec, "third_party_funds_gap", None) != D("0.00"):
            fuori.append(f"{anno} scarto {getattr(rec, 'third_party_funds_gap', None)}, atteso 0,00")
    assert not fuori, "\n".join(fuori)
```

- [ ] **Step 3: Prova rossa.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_cashflow_dividendi.py -q -p no:cacheprovider`
  Atteso: 2 failed sulle asserzioni (dividendi incassati 0,00, operativo −10.000,00, scarto `None`).
- [ ] **Step 4: Implementa** i punti 1-4 e riporta i tre file CRLF a CRLF.
- [ ] **Step 5: Verde.** Lo stesso comando; poi
  `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_cashflow_debito_finanziario.py -q -p no:cacheprovider`
  e `test -e frontend/node_modules || ln -s /home/peter/DEV/budget/frontend/node_modules frontend/node_modules; cd frontend && npx tsc --noEmit`.
- [ ] **Step 6: Documento.** `docs/budget/API-PREVISIONALE.md` §4-bis, dopo la frase che spiega che la riclassifica non
  attraversa il confine operativo/finanziario del rendiconto, aggiungi: «I proventi da partecipazioni (`ce13`) tolti
  dall'utile nel primo blocco rientrano come dividendi incassati, e `cash_reconciliation.third_party_funds_gap` dichiara
  lo scarto fra i mezzi di terzi per residuo e la variazione misurata del debito finanziario: zero quando il rendiconto
  classifica ogni movimento.»
- [ ] **Step 7: Banco.** Comando delle convenzioni con `task6`. Atteso: uscita 0.
- [ ] **Step 8: Commit.** `git add backend/app/calculations/cashflow_detailed.py backend/app/schemas/cashflow_detailed.py frontend/types/api.ts tests/test_cashflow_dividendi.py tests/test_cashflow_debito_finanziario.py docs/budget/API-PREVISIONALE.md && git commit -m "fix(rendiconto): i dividendi incassati rientrano nell'operativo e lo scarto dei mezzi di terzi si dichiara (lotto 3A, task 6)"`
- [ ] **Step 9: Rapporto** `task-6-report.md`, con la riga su `cashflow.py` non modificato e perche'.

**Observable acceptance.** 2 test nuovi verdi (rossi prima); `tests/test_cashflow_debito_finanziario.py` verde; `tsc`
pulito; i tre file CRLF restano CRLF (`file` lo conferma); banco a 0 divergenze.

---

## Ondata C — bulk e messaggi

### Task 7a: Il bulk rifiuta l'input invalido prima di scrivere, con un 422 italiano per campo (backend)

**Esecutore:** pi (Orca) · **Revisore:** sonnet · **Ondata:** C, dopo i Task 1-6

**Target (spec §4.5, decisione 2 del proprietario).** `PUT /companies/{id}/scenarios/{sid}/assumptions`
(`backend/app/api/v1/budget_scenarios.py::bulk_upsert_assumptions`, `request: Any = Body(...)`) non passa da nessuno
schema: `assumptions_service.bulk_upsert_assumptions` controlla solo `forecast_year` e poi **cancella** le ipotesi
esistenti. Misurato: tetto di scoperto −100 accettato (poi errore confuso ogni anno), `tax_advances_paid` −5.000
accettato e ignorato in silenzio, driver `"magia"` accettato, tasso 500% applicato; righe 2027 e 2029 senza 2028
accettate (ricavi con un passo di crescita, prestito con due). Dopo:
- ogni riga passa lo schema tipizzato (`BudgetAssumptionsBulkRow`, gli stessi vincoli di `BudgetAssumptionsCreate`)
  **prima** di qualunque cancellazione o scrittura; gli anni devono essere consecutivi e successivi all'anno base;
- un errore risponde **422** con `detail = {"message": "Ipotesi non valide: nulla è stato salvato", "errori":
  [{forecast_year, campo, messaggio}]}`, messaggi italiani tradotti per tipo d'errore di Pydantic; nulla si salva;
- **invariato**: un input valido che il motore rifiuta risponde ancora 200 con `forecast_generated: false`;
  un primo anno diverso da anno base + 1 resta accettato (oggi lo e': solo gli anni ≤ anno base sono rifiutati);
  l'anteprima (`POST /preview`) non applica lo schema tipizzato e continua a rispondere 400 sugli errori di
  `validate_assumptions_list`.
- **Fuori da questo task:** oggi il wizard budget e la schermata Startup mostrano, su questo 422 come su ogni altro
  errore, un solo messaggio grezzo. Restano cosi': il Task 7b, dopo che questo e' integrato nel branch del lotto,
  li fa leggere `detail.errori` e mostrare un elenco. Questo task tocca **solo** backend.

**Da leggere prima:** `backend/app/services/assumptions_service.py` (`validate_assumptions_list`,
`build_assumption_row` — i null coalizzati sui default — e `bulk_upsert_assumptions`, fino alla `DELETE`);
`backend/app/schemas/budget.py` (`FinancingLoanInput` e il suo `validate_contract`, `BudgetAssumptionsBase`,
`BudgetAssumptionsCreate`); `backend/app/api/v1/budget_scenarios.py` (`bulk_upsert_assumptions`,
`preview_forecast_route`).

**Trappole note.**
- `assumptions_service.py` e `schemas/budget.py` sono **interamente CRLF**: riportali a CRLF dopo la modifica
  (`/home/peter/DEV/budget/backend/venv/bin/python -c "import sys;p=sys.argv[1];b=open(p,'rb').read().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n');open(p,'wb').write(b)" <percorso>`).
  `budget_scenarios.py` e' a terminatori **misti**: non normalizzarlo. `git diff --stat` solo sulle righe cambiate.
- Il client manda `null` per i campi svuotati, e `build_assumption_row` li coalizza sui default: `null` vale «campo
  omesso», quindi prima dello schema i `null` si tolgono (anche dentro `financing_loans`, `tax_temporary_differences`,
  `sp_overrides` e i piani di `pregresso`). Misurato: con questa pulizia lo schema rifiuta solo 3 payload fra i 162 test
  che usano il bulk, tutti nominati sotto.
- CLAUDE.md › Previsionale: il 200 con `forecast_generated: false` resta il contratto per un input **valido** rifiutato dal motore.

**Change.**
1. `backend/app/schemas/budget.py`: i due messaggi di `FinancingLoanInput.validate_contract` in italiano,
   «l'importo o il residuo iniziale devono essere maggiori di zero» e «gli anni di preammortamento devono essere meno
   della durata»; dopo `BudgetAssumptionsCreate`:

```python
class BudgetAssumptionsBulkRow(BudgetAssumptionsBase):
    """Una riga del bulk `PUT /assumptions`: gli stessi vincoli di `BudgetAssumptionsCreate`, senza `scenario_id` obbligatorio
    (lo scenario e' nel percorso). Serve SOLO a validare: le righe si costruiscono ancora da `build_assumption_row`,
    cosi' un input valido produce esattamente le righe di prima."""
    scenario_id: Optional[int] = None
```

2. `backend/app/services/assumptions_service.py`: import `from pydantic import ValidationError` e
   `from app.schemas.budget import BudgetAssumptionsBulkRow`; prima di `validate_assumptions_list`:

```python
class AssumptionsValidationError(ValueError):
    """Ipotesi che le rotte tipizzate rifiutano (lotto 3A, Task 7a): `errori` e' un elenco di
    `{forecast_year, campo, messaggio}` in italiano. Sottoclasse di `ValueError`, cosi' l'anteprima — che cattura
    `ValueError` e risponde 400 — non cambia; il bulk la cattura prima e risponde 422."""

    def __init__(self, errori):
        self.errori = list(errori)
        super().__init__("Ipotesi non valide: " + "; ".join(
            (f"{e['forecast_year']} · " if e.get("forecast_year") is not None else "") + f"{e['campo']}: {e['messaggio']}"
            for e in self.errori
        ))


def _errore(anno, campo, messaggio):
    return {"forecast_year": anno, "campo": campo, "messaggio": messaggio}


_TIPO_ATTESO = {
    "decimal_parsing": "un numero", "decimal_type": "un numero", "float_parsing": "un numero", "float_type": "un numero",
    "int_parsing": "un numero intero", "int_type": "un numero intero", "int_from_float": "un numero intero",
    "bool_parsing": "vero o falso", "bool_type": "vero o falso",
    "dict_type": "un oggetto", "model_type": "un oggetto", "model_attributes_type": "un oggetto",
    "list_type": "un elenco", "string_type": "un testo",
}


def messaggio_errore_campo(err) -> str:
    """Un errore di Pydantic in italiano, per tipo. Un tipo non mappato dice comunque che il valore non e' valido;
    il valore ricevuto si mostra sempre, tranne per un campo mancante."""
    tipo, ctx = err.get("type"), err.get("ctx") or {}
    if tipo == "missing":
        return "campo obbligatorio mancante"
    if tipo == "greater_than_equal":
        testo = f"deve essere maggiore o uguale a {ctx.get('ge')}"
    elif tipo == "greater_than":
        testo = f"deve essere maggiore di {ctx.get('gt')}"
    elif tipo == "less_than_equal":
        testo = f"deve essere minore o uguale a {ctx.get('le')}"
    elif tipo == "less_than":
        testo = f"deve essere minore di {ctx.get('lt')}"
    elif tipo == "literal_error":
        testo = "valore non ammesso: sono ammessi " + str(ctx.get("expected", "")).replace(" or ", " o ")
    elif tipo == "string_pattern_mismatch":
        testo = "valore non ammesso"
    elif tipo == "string_too_short":
        testo = f"testo troppo corto (minimo {ctx.get('min_length')} caratteri)"
    elif tipo == "string_too_long":
        testo = f"testo troppo lungo (massimo {ctx.get('max_length')} caratteri)"
    elif tipo == "value_error":
        testo = str(err.get("msg", "")).removeprefix("Value error, ")
    elif tipo in _TIPO_ATTESO:
        testo = f"tipo sbagliato: serve {_TIPO_ATTESO[tipo]}"
    else:
        testo = "valore non valido"
    return f"{testo} (ricevuto: {err.get('input')!r})"


def _senza_null(riga):
    """`null` dal client vale «campo omesso» (`build_assumption_row` lo coalizza sul default): lo si toglie prima dello schema."""
    pulita = {k: v for k, v in riga.items() if v is not None}
    for chiave in ("financing_loans", "tax_temporary_differences"):
        if isinstance(pulita.get(chiave), list):
            pulita[chiave] = [{k: v for k, v in voce.items() if v is not None} if isinstance(voce, dict) else voce
                              for voce in pulita[chiave]]
    if isinstance(pulita.get("sp_overrides"), dict):
        pulita["sp_overrides"] = {k: v for k, v in pulita["sp_overrides"].items() if v is not None}
    if isinstance(pulita.get("pregresso"), dict):
        pulita["pregresso"] = {k: ({kk: vv for kk, vv in piano.items() if vv is not None} if isinstance(piano, dict) else piano)
                               for k, piano in pulita["pregresso"].items() if piano is not None}
    return pulita


def validate_bulk_rows(assumptions_list, forecast_years) -> None:
    """Ogni riga del bulk contro `BudgetAssumptionsBulkRow`, tutti gli errori insieme; alza `AssumptionsValidationError`."""
    errori = []
    for riga, anno in zip(assumptions_list, forecast_years):
        try:
            BudgetAssumptionsBulkRow(**_senza_null(riga))
        except ValidationError as exc:
            for err in exc.errors():
                errori.append(_errore(anno, ".".join(str(p) for p in err["loc"]), messaggio_errore_campo(err)))
    if errori:
        raise AssumptionsValidationError(errori)
```

   Riscrivi `validate_assumptions_list` (stesso docstring sul ruolo, stessa firma, stesso valore di ritorno: gli anni
   coerciati nell'ordine delle righe):

```python
    if not assumptions_list:
        raise AssumptionsValidationError([_errore(None, "assumptions", "serve almeno una riga di ipotesi")])
    years: List[int] = []
    for assumption in assumptions_list:
        if "forecast_year" not in assumption:
            raise AssumptionsValidationError([_errore(None, "forecast_year", "ogni riga di ipotesi deve avere forecast_year")])
        raw_year = assumption["forecast_year"]
        try:
            forecast_year = int(raw_year)
        except (TypeError, ValueError):
            raise AssumptionsValidationError([_errore(None, "forecast_year", f"forecast_year non valido: {raw_year!r}")])
        years.append(forecast_year)
    errori = [_errore(a, "forecast_year", f"l'anno di previsione {a} deve essere successivo all'anno base {base_year}")
              for a in years if a <= base_year]
    visti = set()
    for a in years:
        if a in visti:
            errori.append(_errore(a, "forecast_year", f"l'anno di previsione {a} e' ripetuto"))
        visti.add(a)
    ordinati = sorted(set(years))
    for prima, dopo in zip(ordinati, ordinati[1:]):
        if dopo != prima + 1:
            errori.append(_errore(dopo, "forecast_year",
                                  f"anni non consecutivi: dopo il {prima} viene il {dopo}, manca il {prima + 1}"))
    if errori:
        raise AssumptionsValidationError(errori)
    return years
```

   In `bulk_upsert_assumptions`, subito dopo `coerced_years = validate_assumptions_list(...)` e prima della `DELETE`:
   `validate_bulk_rows(assumptions_list, coerced_years)`.
3. `backend/app/api/v1/budget_scenarios.py::bulk_upsert_assumptions`: prima di `except ValueError as e:` aggiungi

```python
    except assumptions_service.AssumptionsValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"message": "Ipotesi non valide: nulla è stato salvato", "errori": e.errori},
        )
```

**Constraints.** Banco a 0 divergenze (usa input validi). Nessun cambio a `build_assumption_row`, a
`preview_forecast_route` o al motore. Nessun file frontend toccato.

**Ownership.** `backend/app/schemas/budget.py`, `backend/app/services/assumptions_service.py`,
`backend/app/api/v1/budget_scenarios.py`, `tests/test_bulk_tipizzato.py` (nuovo), `tests/test_forecast_preview.py`,
`tests/test_forecast_scoperto.py`, `tests/test_budget_pregresso.py`, `CLAUDE.md`, `docs/budget/API-PREVISIONALE.md`.

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task7a-base`
- [ ] **Step 2: Test**, `tests/test_bulk_tipizzato.py` (tipi e contesti d'errore misurati con Pydantic 2.10.4):

```python
"""Il bulk delle ipotesi rifiuta l'input invalido prima di scrivere, con un 422 italiano per campo (lotto 3A, Task 7a)."""
import pytest
from fastapi import HTTPException

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from backend.app.services import assumptions_service
from database import models
from tests.e2e_kit import memory_sessions, seed_base_year

USER = "bulk-tipizzato"
VALIDE = [{"forecast_year": 2027, "revenue_growth_pct": 5}, {"forecast_year": 2028, "revenue_growth_pct": 5}]


def _scenario_salvato(db):
    company_id, _ = seed_base_year(db, user_id=USER)
    sc = budget_scenarios.create_budget_scenario(
        company_id, BudgetScenarioCreate(company_id=company_id, name="bulk", base_year=2026, scenario_type="budget"),
        user_id=USER, db=db)
    esito = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": [dict(r) for r in VALIDE], "auto_generate": True}, user_id=USER, db=db)
    assert esito["forecast_generated"] is True, esito["message"]
    return company_id, sc.id


def _stato(db, sid):
    db.expire_all()
    righe = (db.query(models.BudgetAssumptions).filter(models.BudgetAssumptions.scenario_id == sid)
             .order_by(models.BudgetAssumptions.forecast_year).all())
    anni = db.query(models.ForecastYear).filter(models.ForecastYear.scenario_id == sid).count()
    return [(r.forecast_year, r.revenue_growth_pct, r.overdraft_limit, r.tax_advances_paid) for r in righe], anni


def _rifiuto(db, company_id, sid, righe):
    with pytest.raises(HTTPException) as e:
        budget_scenarios.bulk_upsert_assumptions(
            company_id, sid, request={"assumptions": righe, "auto_generate": True}, user_id=USER, db=db)
    assert e.value.status_code == 422
    return e.value.detail


CASI = {
    "tetto di scoperto negativo": ({"overdraft_allowed": True, "overdraft_limit": -100}, "overdraft_limit",
                                   "deve essere maggiore o uguale a 0 (ricevuto: -100)"),
    "acconti negativi": ({"tax_advances_paid": -5000}, "tax_advances_paid",
                         "deve essere maggiore o uguale a 0 (ricevuto: -5000)"),
    "driver sconosciuto": ({"sp_indexing": {"sp16g": "magia"}}, "sp_indexing.sp16g",
                           "valore non ammesso: sono ammessi 'ricavi', 'acquisti' o 'personale' (ricevuto: 'magia')"),
    "tasso al 500%": ({"financing_loans": [{"amount": 50000, "duration_years": 3, "interest_rate": 500}]},
                      "financing_loans.0.interest_rate", "deve essere minore o uguale a 100 (ricevuto: 500)"),
}


@pytest.mark.parametrize("nome", list(CASI))
def test_un_input_che_lo_schema_rifiuta_risponde_422_e_non_scrive_nulla(nome, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    extra, campo, messaggio = CASI[nome]
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, sid = _scenario_salvato(db)
            prima = _stato(db, sid)
            righe = [dict(VALIDE[0], revenue_growth_pct=9, **extra), dict(VALIDE[1], revenue_growth_pct=9)]
            detail = _rifiuto(db, company_id, sid, righe)
            assert detail["errori"] == [{"forecast_year": 2027, "campo": campo, "messaggio": messaggio}]
            assert _stato(db, sid) == prima
    finally:
        engine.dispose()


def test_anni_non_consecutivi_rispondono_422_e_non_scrivono_nulla(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, sid = _scenario_salvato(db)
            prima = _stato(db, sid)
            righe = [{"forecast_year": 2027, "revenue_growth_pct": 9}, {"forecast_year": 2029, "revenue_growth_pct": 9}]
            assert _rifiuto(db, company_id, sid, righe)["errori"] == [{
                "forecast_year": 2029, "campo": "forecast_year",
                "messaggio": "anni non consecutivi: dopo il 2027 viene il 2029, manca il 2028"}]
            assert _stato(db, sid) == prima
    finally:
        engine.dispose()


def test_il_servizio_alza_l_errore_con_l_elenco(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    classe = getattr(assumptions_service, "AssumptionsValidationError", None)
    assert classe is not None, "assumptions_service.AssumptionsValidationError non esiste"
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _company_id, sid = _scenario_salvato(db)
            with pytest.raises(classe) as e:
                assumptions_service.bulk_upsert_assumptions(db, sid, [dict(VALIDE[0], tax_advances_paid=-1), VALIDE[1]])
            assert isinstance(e.value, ValueError)
            assert e.value.errori[0]["campo"] == "tax_advances_paid"
    finally:
        engine.dispose()


def test_i_null_del_client_non_sono_errori_e_un_primo_anno_dopo_base_piu_uno_resta_accettato(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, sid = _scenario_salvato(db)
            con_null = [
                {"forecast_year": 2027, "revenue_growth_pct": 5, "financing_amount": None, "dso_days": None,
                 "tax_advances_paid": None, "cash_sweep_min_cash": None, "overdraft_limit": None,
                 "sp_overrides": {"sp10_ratei_risconti_attivi": None},
                 "financing_loans": [{"name": None, "amount": 50000, "opening_residual": 0, "duration_years": 5,
                                      "interest_rate": 3, "grace_years": None, "balloon_pct": None}]},
                {"forecast_year": 2028, "revenue_growth_pct": 5},
            ]
            esito = budget_scenarios.bulk_upsert_assumptions(
                company_id, sid, request={"assumptions": con_null, "auto_generate": True}, user_id=USER, db=db)
            assert esito["forecast_generated"] is True, esito["message"]
            dopo_la_base = [{"forecast_year": 2028, "revenue_growth_pct": 5}, {"forecast_year": 2029, "revenue_growth_pct": 5}]
            esito = budget_scenarios.bulk_upsert_assumptions(
                company_id, sid, request={"assumptions": dopo_la_base, "auto_generate": True}, user_id=USER, db=db)
            assert esito["success"] is True
            assert [a for a, *_ in _stato(db, sid)[0]] == [2028, 2029]
    finally:
        engine.dispose()
```

- [ ] **Step 3: Prova rossa.**
  `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_bulk_tipizzato.py -q -p no:cacheprovider`
  (atteso: 7 failed, «DID NOT RAISE» o asserzioni; nessun `ImportError`).
- [ ] **Step 4: Implementa** i punti 1-3.
- [ ] **Step 5: Test esistenti da aggiornare (e solo questi).**
  - `tests/test_forecast_preview.py`: rinomina `test_forecast_year_not_convertible_is_400_and_writes_nothing_on_both_endpoints`
    in `test_forecast_year_not_convertible_is_rejected_and_writes_nothing_on_both_endpoints`; nel ramo del **bulk**
    `assert e.value.status_code == 400` diventa `assert e.value.status_code == 422` seguito da
    `assert e.value.detail["errori"] == [{"forecast_year": None, "campo": "forecast_year", "messaggio": "forecast_year non valido: 'abc'"}]`;
    il ramo dell'anteprima resta 400.
  - `tests/test_forecast_scoperto.py`: sostituisci `test_tetto_negativo_ha_un_messaggio_onesto_non_quello_del_tetto_superato` con

```python
def test_tetto_negativo_rifiutato_dal_bulk_e_dichiarato_dal_motore_in_anteprima():
    """Dal lotto 3A (Task 7a) il bulk valida le righe con lo schema tipizzato: un tetto negativo non arriva piu' al
    motore per quella porta. L'anteprima non valida lo schema, e li' il motore continua a dire il difetto vero."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _, sid = _scenario(db, "scoperto-tetto-negativo")
            rows = [_riga(2027, overdraft_allowed=True, overdraft_limit=-1000)]
            with pytest.raises(assumptions_service.AssumptionsValidationError) as e:
                assumptions_service.bulk_upsert_assumptions(db, sid, [dict(r) for r in rows], auto_generate=True)
            assert e.value.errori == [{"forecast_year": 2027, "campo": "overdraft_limit",
                                       "messaggio": "deve essere maggiore o uguale a 0 (ricevuto: -1000)"}]
            _dettagli_anni, errore = _dettagli(db, sid, rows)
        assert "Il limite di scoperto non puo' essere negativo" in errore["message"], errore
        assert "ricevuto -1.000,00" in errore["message"], errore
        assert "tetto concesso" not in errore["message"], errore
        with sessions() as db2:
            assert db2.query(ForecastBalanceSheet).count() == 0
    finally:
        engine.dispose()
```

  - `tests/test_budget_pregresso.py`: nel test che costruisce `differences = [{"kind": "deductible", "maturity": "long", …}]`
    (circa riga 350) aggiungi `"name": "Differenza temporanea 1"` al dizionario.
- [ ] **Step 6: Verde.**
  `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_bulk_tipizzato.py tests/test_forecast_preview.py tests/test_forecast_scoperto.py tests/test_budget_pregresso.py tests/test_build_assumption_row.py -q -p no:cacheprovider`;
  poi tutti i file che usano il bulk:
  `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest $(grep -l bulk_upsert_assumptions tests/*.py) -q -p no:cacheprovider`
  (atteso: tutto verde; un rifiuto nuovo su un payload valido e' un difetto della pulizia dei `null`, non del test).
- [ ] **Step 7: Documenti.**
  - `CLAUDE.md`, «Invarianti e trappole › Previsionale», bullet «Chi chiama l'endpoint bulk…»: aggiungi in coda «Un
    input che le rotte tipizzate rifiutano non arriva fin li': il bulk valida ogni riga con `BudgetAssumptionsBulkRow`
    e la contiguita' degli anni **prima** di cancellare, e risponde **422** con `detail.errori`
    (`{forecast_year, campo, messaggio}`, in italiano) senza salvare nulla.»
  - `docs/budget/API-PREVISIONALE.md` §1: aggiungi `### 1.2 Input invalido: 422, e nulla si salva` con la forma del
    `detail`, la tabella dei tipi tradotti (quella di `messaggio_errore_campo`), la pulizia dei `null`, la contiguita'
    degli anni, e la frase «Il 200 con `forecast_generated: false` vale per un input **valido** che il motore rifiuta.
    Un primo anno diverso da anno base + 1 resta accettato. L'anteprima non applica lo schema tipizzato.»
- [ ] **Step 8: Banco.** Comando delle convenzioni con `task7a`. Atteso: uscita 0 (usa solo input validi).
- [ ] **Step 9: Commit.** `git add backend/app/schemas/budget.py backend/app/services/assumptions_service.py backend/app/api/v1/budget_scenarios.py tests/test_bulk_tipizzato.py tests/test_forecast_preview.py tests/test_forecast_scoperto.py tests/test_budget_pregresso.py CLAUDE.md docs/budget/API-PREVISIONALE.md && git commit -m "fix(bulk): le ipotesi invalide si rifiutano con un 422 italiano prima di scrivere (lotto 3A, task 7a)"`
- [ ] **Step 10: Rapporto** `task-7a-report.md`.

**Observable acceptance.** 7 test nuovi verdi (rossi prima); tutti i test che usano il bulk verdi; banco a 0
divergenze; i due file CRLF (`assumptions_service.py`, `schemas/budget.py`) restano CRLF.

---

### Task 7b: Il wizard e Startup mostrano l'elenco degli errori del bulk, non il messaggio grezzo (frontend)

**Esecutore:** pi (Orca) · **Revisore:** sonnet · **Ondata:** C, dopo il Task 7a — **apri questo worktree solo dopo
che il Task 7a è integrato nel branch del lotto** (`feat/lotto3a-motori`): il backend non risponde ancora 422 nella
forma sotto finché quel task non c'è, e non c'è nulla da consumare.

**Target (spec §4.5, decisione 2 del proprietario).** Dal Task 7a, `PUT /scenarios/{id}/assumptions` risponde, su un
input che lo schema tipizzato rifiuta, **422** con questo corpo esatto (forma prodotta da
`backend/app/api/v1/budget_scenarios.py::bulk_upsert_assumptions`; verificala sul branch dopo il merge del Task 7a
con una chiamata reale, non fidarti solo di questo testo):

```json
{
  "detail": {
    "message": "Ipotesi non valide: nulla è stato salvato",
    "errori": [
      {"forecast_year": 2027, "campo": "overdraft_limit", "messaggio": "deve essere maggiore o uguale a 0 (ricevuto: -100)"},
      {"forecast_year": null, "campo": "forecast_year", "messaggio": "forecast_year non valido: 'abc'"}
    ]
  }
}
```

`detail.errori` è sempre un elenco di `{forecast_year: number|null, campo: string, messaggio: string}`, con
`messaggio` già in italiano (tradotto lato backend per tipo di errore Pydantic: «deve essere maggiore o uguale
a…», «tipo sbagliato: serve un numero (ricevuto: …)», «campo obbligatorio mancante», eccetera — non serve saperne
la logica per questo task, solo che è già pronto per essere mostrato). Un 422 **senza** quella forma (per esempio
la validazione automatica di FastAPI sul corpo della richiesta, prima ancora di arrivare al servizio) non ha
`detail.errori` come elenco: va trattato come un errore generico, non come questo caso.

Oggi il wizard budget (`frontend/components/budget/wizard/BudgetWizard.tsx`) e la schermata Startup
(`frontend/app/budget/page.tsx`) mostrano, su qualunque errore del salvataggio delle ipotesi, un solo messaggio
grezzo via `getErrorMessage`. Dopo: quando l'errore è un 422 nella forma sopra, il toast mostra un elenco — una riga
per campo, con l'anno quando c'è — invece del messaggio grezzo; ogni altro errore continua a mostrare
`getErrorMessage` esattamente come oggi.

**Da leggere prima (sul branch del lotto 3A, per simbolo, dopo il merge del Task 7a):**
`frontend/components/budget/wizard/BudgetWizard.tsx` (la funzione `save`, il suo blocco `catch`, oggi
`toast.error(getErrorMessage(err, "Impossibile salvare le ipotesi"))`); `frontend/app/budget/page.tsx`
(`handleSave` di `ScenarioFormStartup`, il suo blocco `catch`, oggi
`toast.error(getErrorMessage(err, "Impossibile salvare lo scenario"))`); `frontend/lib/utils.ts`
(`getErrorMessage`, per capire il fallback che resta per ogni altro errore).

**Trappole note.**
- `lib/budget-*` non importa mai da `app/` o `components/` (regola generale di `CLAUDE.md` › Frontend): il modulo
  nuovo di questo task resta puro.
- Nessuna emoji; nessuna icona nuova; il toast resta `sonner` come oggi.
- Nessun file di questo task è CRLF (`BudgetWizard.tsx`, `page.tsx` e i moduli `lib/` sono tutti LF): `git diff --stat`
  deve comunque contare solo le righe davvero cambiate, non un file riscritto per intero.

**Change.**
1. Crea `frontend/lib/budget-bulk-errors.ts` (allo Step 3 con il corpo ridotto a `return null;`, allo Step 5 completo):

```ts
/**
 * Le righe da mostrare quando il bulk delle ipotesi risponde 422 (lotto 3A, Task 7b).
 *
 * `PUT /scenarios/{id}/assumptions` valida ogni riga PRIMA di scrivere (Task 7a) e, se qualcosa non va, risponde
 * 422 con `detail.errori`: un elenco `{forecast_year, campo, messaggio}` gia' in italiano. Un 422 senza quell'elenco
 * (la validazione di FastAPI sul corpo) non e' nostro e torna `null`: il chiamante ricade su `getErrorMessage`.
 * Modulo puro: nessun import da `app/` o `components/`.
 */
export interface ErroreCampoIpotesi {
  forecast_year: number | null;
  campo: string;
  messaggio: string;
}

function eErroreCampo(voce: unknown): voce is ErroreCampoIpotesi {
  return !!voce && typeof voce === "object"
    && typeof (voce as ErroreCampoIpotesi).campo === "string"
    && typeof (voce as ErroreCampoIpotesi).messaggio === "string";
}

export function righeErroriIpotesi(error: unknown): string[] | null {
  const risposta = (error as { response?: { status?: number; data?: { detail?: unknown } } } | undefined)?.response;
  if (!risposta || risposta.status !== 422) return null;
  const detail = risposta.data?.detail as { errori?: unknown } | undefined;
  if (!detail || !Array.isArray(detail.errori)) return null;
  const righe = detail.errori.filter(eErroreCampo).map((e) =>
    typeof e.forecast_year === "number" ? `${e.forecast_year} · ${e.campo}: ${e.messaggio}` : `${e.campo}: ${e.messaggio}`);
  return righe.length > 0 ? righe : null;
}
```

2. `BudgetWizard.tsx`, nel `catch` di `save` (oggi `toast.error(getErrorMessage(err, "Impossibile salvare le ipotesi"))`),
   e `app/budget/page.tsx`, nel `catch` di `handleSave` (oggi `toast.error(getErrorMessage(err, "Impossibile salvare lo scenario"))`):

```tsx
      const righe = righeErroriIpotesi(err);
      if (righe) {
        toast.error("Ipotesi non salvate: correggi i campi indicati", {
          description: (
            <ul className="list-disc pl-4">
              {righe.map((riga) => <li key={riga}>{riga}</li>)}
            </ul>
          ),
        });
      } else {
        toast.error(getErrorMessage(err, "Impossibile salvare le ipotesi"));   // in page.tsx: "Impossibile salvare lo scenario"
      }
```

   con `import { righeErroriIpotesi } from "@/lib/budget-bulk-errors";`. Nessuna emoji; niente icone nuove.

**Constraints.** Nessun cambio al backend, al motore o a `getErrorMessage`. Nessun cambio al comportamento per un
errore che non è un 422 nella forma sopra: resta `getErrorMessage` come oggi.

**Ownership.** `frontend/lib/budget-bulk-errors.ts` (nuovo), `frontend/lib/budget-bulk-errors.test.ts` (nuovo),
`frontend/components/budget/wizard/BudgetWizard.tsx`, `frontend/app/budget/page.tsx`.

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task7b-base`
- [ ] **Step 2: Node modules del frontend** (il worktree non li ha):
  `test -e frontend/node_modules || ln -s /home/peter/DEV/budget/frontend/node_modules frontend/node_modules`
- [ ] **Step 3: Test.** Crea `frontend/lib/budget-bulk-errors.ts` con la sola firma
  `export function righeErroriIpotesi(error: unknown): string[] | null { return null; }` e il test
  `frontend/lib/budget-bulk-errors.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { righeErroriIpotesi } from "./budget-bulk-errors";

const errore422 = (detail: unknown) => ({ response: { status: 422, data: { detail } } });

describe("righeErroriIpotesi", () => {
  it("un 422 del bulk diventa una riga per campo, con l'anno quando c'e'", () => {
    expect(righeErroriIpotesi(errore422({
      message: "Ipotesi non valide: nulla è stato salvato",
      errori: [
        { forecast_year: 2027, campo: "overdraft_limit", messaggio: "deve essere maggiore o uguale a 0 (ricevuto: -100)" },
        { forecast_year: null, campo: "forecast_year", messaggio: "forecast_year non valido: 'abc'" },
      ],
    }))).toEqual([
      "2027 · overdraft_limit: deve essere maggiore o uguale a 0 (ricevuto: -100)",
      "forecast_year: forecast_year non valido: 'abc'",
    ]);
  });

  it("un 422 di FastAPI senza l'elenco italiano non e' nostro: null", () => {
    expect(righeErroriIpotesi(errore422([{ loc: ["body"], msg: "Field required", type: "missing" }]))).toBeNull();
  });

  it("un altro status, un errore senza risposta o nessun errore: null", () => {
    expect(righeErroriIpotesi({ response: { status: 400, data: { detail: "x" } } })).toBeNull();
    expect(righeErroriIpotesi(new Error("rete"))).toBeNull();
    expect(righeErroriIpotesi(undefined)).toBeNull();
  });

  it("voci malformate si scartano; se non resta nulla, null", () => {
    expect(righeErroriIpotesi(errore422({ errori: [{ campo: 3 }] }))).toBeNull();
  });
});
```

- [ ] **Step 4: Prova rossa.** `cd frontend && npx vitest run lib/budget-bulk-errors.test.ts`
  Atteso: fallisce solo il primo `it` (sull'`toEqual`); gli altri tre passano già con lo stub che ritorna sempre
  `null`.
- [ ] **Step 5: Implementa** il corpo completo di `righeErroriIpotesi` (punto 1 del Change) e i due punti del `catch`
  (punto 2).
- [ ] **Step 6: Verde.** `cd frontend && npx vitest run lib/budget-bulk-errors.test.ts && npx tsc --noEmit`
- [ ] **Step 7: Commit.** `git add frontend/lib/budget-bulk-errors.ts frontend/lib/budget-bulk-errors.test.ts frontend/components/budget/wizard/BudgetWizard.tsx frontend/app/budget/page.tsx && git commit -m "feat(bulk): il wizard e Startup mostrano l'elenco degli errori del 422, non il messaggio grezzo (lotto 3A, task 7b)"`
- [ ] **Step 8: Rapporto** `task-7b-report.md` (contenuto delle convenzioni: prova rossa, prova verde, `git diff --stat`).

**Observable acceptance.** 4 test vitest verdi (1 rosso prima); `tsc` pulito; nessun file backend toccato.

---

### Task 8: I messaggi del previsionale nascono in italiano

**Esecutore:** pi (Orca) · **Revisore:** sonnet · **Ondata:** C, dopo il Task 7b (tocca testi in tutti i file dei task precedenti)

**Target (spec §4.6, decisione 5 del proprietario).** I messaggi che arrivano all'utente dal motore budget, dal motore
infrannuale e dai servizi del previsionale e del promote sono ancora in inglese, e il client ne traduce uno solo
(`saveNotice`). Dopo: si scrivono in italiano alla fonte, con lo stesso contenuto e gli importi all'europea
(«1.100.700,90»); i **codici** diagnostici (`unfunded_financing_requirement`, `degenerate_turnover_ratio`, chiavi dei
`details`) non cambiano; il client smette di tradurre. Fuori: `backend/app/services/calculation_service.py` e le rotte
che non sono del previsionale (aziende, anni, rendiconto, indici). I messaggi di `validate_assumptions_list` e di
`FinancingLoanInput` sono gia' italiani dal Task 7a.

**Da leggere prima (sul branch del lotto 3A, per simbolo):** i punti della tabella sotto; `frontend/lib/budget-preview-rows.ts`
(`unfundedAmountFromMessage`, `unfundedFromError`), `frontend/lib/budget-wizard-steps.ts` (`stepForErrorMessage`,
`saveOutcome`), `frontend/lib/budget-preview-notice.ts` (`previewNotice`, `saveNotice`, `BACKEND_WRAPPER_RE`).

**Trappole note.**
- `assumptions_service.py` e' interamente CRLF (riportarlo a CRLF col comando delle convenzioni); `intra_year_engine.py`,
  `budget_scenarios.py` e `promote_service.py` sono a terminatori misti (mai normalizzarli). `git diff --stat` solo sulle
  righe cambiate.
- Il banco confronta anche i messaggi d'errore: cambiano solo le celle `@errore`.
- Un test o un documento che cita un testo si aggiorna nello stesso commit. Un commento o un docstring che cita il testo
  vecchio si aggiorna anche lui (il test di guardia sotto legge i sorgenti).

**Change.**
1. `calculations/projection_common.py`: sposta qui `_eur_it` del motore budget come `eur_it(amount) -> str` (stesso corpo:
   quantizza `ROUND_HALF_UP` al centesimo, migliaia col punto e decimali con la virgola); in `forecast_engine.py` resta
   `_eur_it = eur_it` importato. `intra_year_engine.py` importa `eur_it`.
2. I messaggi (a sinistra il simbolo e l'inizio del testo di oggi; a destra il testo nuovo; `{…}` sono le stesse variabili
   di oggi, gli importi passati da `eur_it`):

| File · simbolo | Oggi | Italiano |
|---|---|---|
| `forecast_engine.py` · `_Overdraft.copri` | `Unfunded financing requirement {nuovo:,.2f}: add an explicit financing assumption; …` | `f"Fabbisogno finanziario scoperto di {eur_it(nuovo)}: aggiungi un'ipotesi di finanziamento esplicita; nessun debito bancario è stato creato automaticamente"` |
| `forecast_engine.py` · `load_forecast_source` | `Budget scenario {scenario_id} not found` | `f"Scenario di budget {scenario_id} non trovato"` |
| idem | `Base year {…} data not found or incomplete` | `f"Dati dell'anno base {scenario.base_year} non trovati o incompleti"` |
| idem, chiamata a `_validate_forecast_source` | etichetta `"Base source"` | `"Anno base"` |
| `forecast_engine.py` · `_normalize_balance_sheet_cents` | `balance sheet incomplete: the overdraft gate needs every SP aggregate` | `"Stato patrimoniale incompleto: il controllo dello scoperto richiede tutti gli aggregati dello SP"` |
| `forecast_engine.py` · `_get_split_investments` | `Aggregate investments cannot be allocated automatically; …` | `"Gli investimenti aggregati non si ripartiscono automaticamente: indica gli investimenti immateriali e/o materiali (intangible_investments, tangible_investments)"` |
| `forecast_engine.py` · `assemble_financing` | `opening_residual is allowed only in the first forecast year` | `"Il residuo iniziale di un finanziamento (opening_residual) è ammesso solo nel primo anno di previsione"` |
| idem | `The sum of financing opening residuals must equal base-year bank debt ({a} != {b})` | `f"La somma dei residui iniziali dei finanziamenti ({eur_it(detailed_opening_total)}) deve coincidere con il debito bancario dell'anno base ({eur_it(base_bank_total)})"` |
| `forecast_engine.py` · `compute_forecast` e `generate_forecast` | `No assumptions found for scenario {…}` | `f"Nessuna ipotesi trovata per lo scenario {…}"` |
| `forecast_engine.py` · `compute_forecast` | `pregresso is allowed only in the first forecast year (…)` | `"Lo scadenziamento del pregresso (pregresso) vale solo sulla riga del primo anno di previsione"` |
| `forecast_engine.py` · `_calculate_balance_sheet` | `Debt aggregate/detail mismatch: creditor categories are required; …` | `"Debiti: l'aggregato non coincide con la somma delle categorie dei creditori; servono le categorie, e la differenza non è stata attribuita alle banche"` |
| `intra_year_engine.py` · `_get_split_investments` | `Investments must be split into …` | `"Gli investimenti vanno divisi fra immateriali e materiali (intangible_investments, tangible_investments): la ripartizione automatica 50/50 è disattivata"` |
| `intra_year_engine.py` · `_period_months_from_record` | `Financial year {y} is not a valid period (period_months=…)` | `f"L'esercizio {financial_year.year} non ha un periodo valido (period_months={period_months!r})"` |
| idem | `… is not a valid partial period (…; expected 1-11 or full year)` | `f"L'esercizio {financial_year.year} non ha un periodo parziale valido (period_months={period_months!r}; attesi 1-11 o l'anno intero)"` |
| `intra_year_engine.py` · `_validate_forecast_source` | `{label}: original balance-sheet diagnostics are unreadable` | `f"{label}: le diagnostiche originali dello stato patrimoniale non sono leggibili"` |
| idem, voci di `blocking` | `empty balance sheet` · `SP imbalance {x}` · `CE/SP profit mismatch {a} vs {b}` · `source plug {x}` · `aggregate/detail mismatch: {key} ({diff}), …` | `"stato patrimoniale vuoto"` · `f"SP non quadrato di {eur_it(x)}"` · `f"utile del CE ({eur_it(a)}) diverso da sp13 ({eur_it(b)})"` · `f"plug nella fonte {eur_it(x)}"` · `f"aggregati e dettagli non coincidono: {key} ({eur_it(diff)}), …"` |
| idem, finale | `{label} {y}/{m}M is not forecastable: {…}` | `f"{label} {financial_year.year}/{financial_year.period_months}M non è utilizzabile per la previsione: {'; '.join(blocking)}"` |
| `intra_year_engine.py` · `generate_projection` | etichette `"Partial source"`, `"Reference source"` | `"Anno parziale"`, `"Anno di riferimento"` |
| idem | `No assumptions found for scenario {…}` | `f"Nessuna ipotesi trovata per lo scenario {scenario_id}"` |
| `intra_year_engine.py` · `_load_scenario` | `Scenario {id} not found` · `… is not infrannuale type` · `… requires period_months between 1 and 12` | `f"Scenario {scenario_id} non trovato"` · `f"Lo scenario {scenario_id} non è di tipo infrannuale"` · `f"Lo scenario {scenario_id} richiede period_months fra 1 e 12"` |
| `intra_year_engine.py` · i due diagnostici `unfunded_financing_requirement` (campo `message`) | `Projected assets exceed explicit funding. …` | `"L'attivo proiettato supera le fonti di finanziamento esplicite: aggiungi un'ipotesi di finanziamento esplicita; nessun debito è stato creato automaticamente."` |
| `intra_year_engine.py` · `_distribute_sp16` (diagnostico `missing_short_debt_breakdown`) | `Short-term debt breakdown is unavailable; …` | `"La ripartizione dei debiti a breve non è disponibile: nessuna categoria è stata inventata."` |
| `intra_year_engine.py` · `_apply_debt_repayment` | `The sum of financing opening residuals must equal source bank debt (…)` | `f"La somma dei residui iniziali dei finanziamenti ({eur_it(detailed_opening)}) deve coincidere con il debito bancario della fonte ({eur_it(bank_debt)})"` |
| `assumptions_service.py` · tre funzioni | `Scenario {scenario_id} not found` | `f"Scenario {scenario_id} non trovato"` |
| `assumptions_service.py` · `bulk_upsert_assumptions` | `Assumptions saved successfully, but forecast generation failed: {e}` · `Assumptions saved and forecast generated successfully` · `Assumptions saved successfully` | `f"Ipotesi salvate, ma il previsionale non è stato calcolato: {str(e)}"` · `"Ipotesi salvate e previsionale calcolato"` · `"Ipotesi salvate"` |
| `assumptions_service.py` · `apply_ce_overrides`, `apply_sp_overrides` | `overrides list is required` · `Each override needs forecast_year and field` · `Invalid override field: {field}` · `No assumptions found for year {y}` | `"Serve l'elenco degli override (overrides)"` · `"Ogni override richiede forecast_year e field"` · `f"Campo di override non valido: {field}"` · `f"Nessuna ipotesi per l'anno {forecast_year}"` |
| `forecast_preview_service.py` · `preview_forecast` | `Budget scenario {scenario_id} not found` | `f"Scenario di budget {scenario_id} non trovato"` |
| `promote_service.py` · `promote_projection_to_financial_year` | `Scenario {id} not found` · `Only infrannuale scenarios can be promoted` · `No projection found — run the projection first` · `Projection is incomplete (missing BS or IS)` · `Promotion aborted: field-by-field verification failed for …` · `Promotion aborted: copied target failed semantic validation: …` · `Projection {y} promoted to full-year financial data` | `f"Scenario {scenario_id} non trovato"` · `"Solo gli scenari infrannuali si possono promuovere"` · `"Nessuna proiezione trovata: genera prima la proiezione"` · `"La proiezione è incompleta (manca lo SP o il CE)"` · `"Promozione annullata: la verifica campo per campo non è riuscita per " + …` · `"Promozione annullata: la copia non supera la validazione semantica: " + …` · `f"Proiezione {target_year} promossa a esercizio annuale"` |
| `budget_scenarios.py` · `get_intra_year_comparison` | `Comparison is only available for infrannuale scenarios` | `"Il confronto è disponibile solo per gli scenari infrannuali"` |
| `budget_scenarios.py` · `promote_projection` | `Only infrannuale scenarios can be promoted` | `"Solo gli scenari infrannuali si possono promuovere"` |
| `budget_scenarios.py` · `create_budget_assumptions` | `Forecast year {…} must be greater than base year {…}` · `Assumptions for year {…} already exist in scenario {…}` | `f"L'anno di previsione {…} deve essere successivo all'anno base {…}"` · `f"Le ipotesi per l'anno {…} esistono già nello scenario {scenario_id}"` |
| `budget_scenarios.py` · `update_budget_assumptions`, `generate_forecasts` | `Forecast generation failed: {e}` · `Internal error during forecast generation: {e}` | `f"Generazione del previsionale non riuscita: {str(e)}"` · `f"Errore interno durante la generazione del previsionale: {str(e)}"` |
| `budget_scenarios.py` · `generate_forecasts` | `Cannot generate forecast: no assumptions found for scenario {…}. Add assumptions first.` | `f"Impossibile generare il previsionale: nessuna ipotesi per lo scenario {scenario_id}. Aggiungi prima le ipotesi."` |
| `budget_scenarios.py` · `bulk_upsert_assumptions` | `Error saving assumptions: {e}` | `f"Errore nel salvataggio delle ipotesi: {str(e)}"` |
| `budget_scenarios.py` · `patch_ce_override`, `patch_sp_override` | `Forecast regeneration failed, no override was applied: {e}` | `f"Rigenerazione del previsionale non riuscita, nessun override è stato applicato: {str(e)}"` |
| `budget_scenarios.py` · `preview_forecast_route` | `Internal error during forecast preview: {e}` | `f"Errore interno durante l'anteprima del previsionale: {str(e)}"` |

3. Client. `frontend/lib/budget-preview-rows.ts`, `unfundedAmountFromMessage`:

```ts
export function unfundedAmountFromMessage(message: string): number | null {
  const m = /Fabbisogno finanziario scoperto di ([\d.]+,\d{2})/.exec(message);
  return m ? parseFloat(m[1].replace(/\./g, "").replace(",", ".")) : null;
}
```

   (docstring: il messaggio del motore e' italiano alla fonte, importo all'europea). `frontend/lib/budget-wizard-steps.ts`,
   `stepForErrorMessage`: la regex diventa `/fabbisogno finanziario scoperto di|scoperto di conto corrente oltre il tetto/i`
   e il commento di `saveOutcome` non parla piu' di «regex del motore in inglese». `frontend/lib/budget-preview-notice.ts`:
   cancella `BACKEND_WRAPPER_RE`, `BACKEND_WRAPPER_IT` e il loro commento; `saveNotice` diventa

```ts
export function saveNotice(message: string): string {
  const amount = unfundedAmountFromMessage(message);
  if (amount !== null) return `Ipotesi salvate. ${unfundedText(amount, null)}`;
  return message;
}
```

   con il docstring riscritto: il prefisso del servizio nasce gia' italiano, il client riconosce solo il fabbisogno
   scoperto per dire importo e rimedio. I commenti che citano i testi inglesi in `frontend/lib/base-bank-debt.ts` e
   `frontend/lib/budget-horizon.ts` citano il testo nuovo.

**Constraints.** Nessun codice diagnostico o chiave di `details` rinominati. Nessun cambio di logica.

**Ownership.** I file della tabella; `calculations/projection_common.py`; i tre moduli client; `tests/test_messaggi_italiani.py`
(nuovo); i test e i documenti elencati negli Step 5-6.

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task8-base`
- [ ] **Step 2: Test**, `tests/test_messaggi_italiani.py`:

```python
"""I messaggi del previsionale nascono in italiano, importi all'europea, codici diagnostici invariati (lotto 3A, Task 8)."""
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.app.services import assumptions_service
from calculations.forecast_engine import _Overdraft
from calculations.intra_year_engine import IntraYearEngine
from database.models import BudgetScenario
from tests.e2e_kit import memory_sessions, seed_base_year
from tests.test_intra_year_semantics import _assumption, _zero_projection

REPO = Path(__file__).resolve().parents[1]

# Frammenti dei testi inglesi di oggi, file per file: nessuno deve restare, commenti compresi.
FRASI_INGLESI = {
    "calculations/forecast_engine.py": [
        "Unfunded financing requirement", "Budget scenario {scenario_id} not found", "data not found or incomplete",
        "the overdraft gate needs", "Aggregate investments cannot be allocated", "is allowed only in the first forecast year",
        "must equal base-year", "No assumptions found for scenario", "creditor categories are required", '"Base source"'],
    "calculations/intra_year_engine.py": [
        "Investments must be split", "is not a valid period", "is not a valid partial period", "diagnostics are unreadable",
        "empty balance sheet", "SP imbalance", "profit mismatch", "source plug", "aggregate/detail mismatch",
        "is not forecastable", "No assumptions found for scenario", 'Scenario {scenario_id} not found"',
        "is not infrannuale type", "requires period_months between 1 and 12", "Projected assets exceed explicit funding",
        "Short-term debt breakdown is unavailable", "must equal source bank", '"Partial source"', '"Reference source"'],
    "backend/app/services/assumptions_service.py": [
        'Scenario {scenario_id} not found"', "Assumptions saved", "forecast generated successfully",
        "overrides list is required", "needs forecast_year and field", "Invalid override field", "No assumptions found for year"],
    "backend/app/services/forecast_preview_service.py": ['Budget scenario {scenario_id} not found"'],
    "backend/app/services/promote_service.py": [
        'Scenario {scenario_id} not found"', "Only infrannuale scenarios", "No projection found", "Projection is incomplete",
        "Promotion aborted", "promoted to full-year"],
    "backend/app/api/v1/budget_scenarios.py": [
        "Comparison is only available", "Only infrannuale scenarios", "must be greater than base year",
        "already exist in scenario", "Forecast generation failed", "Internal error during forecast",
        "Error saving assumptions", "regeneration failed, no override", "Cannot generate forecast"],
}


def test_nessun_testo_inglese_del_perimetro_resta_nei_sorgenti():
    fuori = []
    for percorso, frasi in FRASI_INGLESI.items():
        testo = (REPO / percorso).read_text(encoding="utf-8")
        fuori += [f"{percorso}: «{frase}»" for frase in frasi if frase in testo]
    assert not fuori, "testi inglesi rimasti:\n" + "\n".join(fuori)


def test_il_fabbisogno_scoperto_si_dice_in_italiano_con_l_importo_all_europea():
    with pytest.raises(ValueError) as e:
        _Overdraft(allowed=False).copri(D("-1100700.90"))
    assert str(e.value).startswith("Fabbisogno finanziario scoperto di 1.100.700,90: "), str(e.value)


def test_il_bulk_che_non_genera_lo_dice_in_italiano(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id="messaggi")
            sc = BudgetScenario(company_id=company_id, name="messaggi", base_year=2026, scenario_type="budget")
            db.add(sc)
            db.commit()
            righe = [{"forecast_year": 2027, "revenue_growth_pct": 3, "tax_rate": 27.9, "tangible_investments": 5000000}]
            esito = assumptions_service.bulk_upsert_assumptions(db, sc.id, righe, auto_generate=True)
        assert esito["forecast_generated"] is False
        assert esito["message"].startswith(
            "Ipotesi salvate, ma il previsionale non è stato calcolato: Fabbisogno finanziario scoperto di "), esito["message"]
    finally:
        engine.dispose()


def test_il_diagnostico_dell_infrannuale_e_italiano_e_il_codice_resta():
    from types import SimpleNamespace
    motore = IntraYearEngine(None)
    motore._project_balance_sheet_annualized(
        SimpleNamespace(sp02_immob_immateriali=D("1000"), sp16_debiti_breve=D("0")),
        SimpleNamespace(), _zero_projection(), _assumption(), 9)
    diagnostico = next(d for d in motore._diagnostics if d["code"] == "unfunded_financing_requirement")
    assert diagnostico["message"] == (
        "L'attivo proiettato supera le fonti di finanziamento esplicite: aggiungi un'ipotesi di finanziamento "
        "esplicita; nessun debito è stato creato automaticamente.")
```

- [ ] **Step 3: Prova rossa.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_messaggi_italiani.py -q -p no:cacheprovider`
  Atteso: 4 failed sulle asserzioni.
- [ ] **Step 4: Implementa** i punti 1-3.
- [ ] **Step 5: Test esistenti da aggiornare (e solo questi).** Python:
  `tests/test_forecast_preview.py` (`"Unfunded financing requirement" in out["error"]["message"]` → `"Fabbisogno finanziario scoperto di"`);
  `tests/test_forecast_scoperto.py` (`_importo_scoperto`: regex `r"Fabbisogno finanziario scoperto di ([\d.]+,\d{2})"` e
  `D(m.group(1).replace(".", "").replace(",", "."))`; i docstring che citano il testo inglese);
  `tests/test_numeric_stress_cycle.py`, `tests/test_forecast_compute.py` (stessa sostituzione nell'`assert … in`);
  `tests/test_sp_override_multi_year_batch.py`, `tests/test_override_rejection_not_persisted.py`
  (`match="Unfunded financing requirement"` → `match="Fabbisogno finanziario scoperto"`, e il commento);
  `tests/test_intra_year_semantics.py` (`match="CE/SP profit mismatch"` → `match="utile del CE"`; `match="source plug 5"`
  → `match="plug nella fonte 5,00"`); i commenti che citano i testi in `tests/test_engine_accounting_invariants.py`,
  `tests/test_forecast_stale.py`, `tests/test_xbrl_csv_full_cycle.py`, `tests/e2e_kit.py`.
  Frontend: in `lib/budget-preview-notice.test.ts`, `lib/budget-preview-rows.test.ts`, `lib/budget-wizard-steps.test.ts`,
  `lib/budget-pregresso-step.test.ts`, `lib/budget-preview-state.test.ts` ogni messaggio `Unfunded financing requirement
  84,120.50…` diventa `Fabbisogno finanziario scoperto di 84.120,50: aggiungi un'ipotesi di finanziamento esplicita`
  (stesso importo, formato europeo; `1,000.00` → `1.000,00`, `1,234.56` → `1.234,56`, `195,418,034.86` →
  `195.418.034,86`); il prefisso `Assumptions saved successfully, but forecast generation failed: ` diventa
  `Ipotesi salvate, ma il previsionale non è stato calcolato: `; le asserzioni `not.toContain("Unfunded")` diventano
  `not.toContain("nessun debito bancario è stato creato")`; i due test del prefisso fisso (rilievo 6) diventano uno
  solo: `saveNotice` restituisce **invariato** un messaggio che comincia gia' con «Ipotesi salvate, ma il previsionale non
  è stato calcolato: » e non riconosce un fabbisogno.
- [ ] **Step 6: Documenti.** `CLAUDE.md` («Forecasting Engine»: «`Unfunded financing requirement <importo>`» →
  «`Fabbisogno finanziario scoperto di <importo>`»); `docs/budget/API-PREVISIONALE.md` (il messaggio del §1, i due
  «Unfunded financing requirement» di §2.1 e §4, «pregresso is allowed only in the first forecast year» di §8,
  «Unfunded financing requirement <importo>» di §10: `grep -n "Unfunded\|Assumptions saved\|is allowed only" docs/budget/API-PREVISIONALE.md`);
  `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §6 (il testo «{label} {anno}/{mesi}M is not forecastable: …»).
- [ ] **Step 7: Verde.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_messaggi_italiani.py tests/test_forecast_preview.py tests/test_forecast_scoperto.py tests/test_numeric_stress_cycle.py tests/test_forecast_compute.py tests/test_sp_override_multi_year_batch.py tests/test_override_rejection_not_persisted.py tests/test_intra_year_semantics.py tests/test_bulk_tipizzato.py tests/test_intra_year_debito_bancario.py tests/test_intra_year_imposte.py -q -p no:cacheprovider`;
  `test -e frontend/node_modules || ln -s /home/peter/DEV/budget/frontend/node_modules frontend/node_modules; cd frontend && npx vitest run lib/budget-preview-notice.test.ts lib/budget-preview-rows.test.ts lib/budget-wizard-steps.test.ts lib/budget-pregresso-step.test.ts lib/budget-preview-state.test.ts && npx tsc --noEmit`;
  `grep -rn "Unfunded financing requirement\|Assumptions saved successfully" calculations backend frontend/lib frontend/components frontend/app tests CLAUDE.md docs/budget docs/import` vuoto.
- [ ] **Step 8: Banco.** Comando delle convenzioni con `task8`, poi
  `/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_riepilogo.py /tmp/lotto3a-task8-parita.json --attese '*|@errore'`.
  Atteso: uscita del banco 1, controllo negativo superato, «fuori dalle attese: 0» (cambiano solo i testi dei tre o
  quattro scenari che il motore rifiuta per fabbisogno).
- [ ] **Step 9: Commit.** `git add` di ogni file toccato, per nome (la lista esce da `git status --short`), poi
  `git commit -m "feat(messaggi): il previsionale e il promote parlano italiano alla fonte (lotto 3A, task 8)"`
- [ ] **Step 10: Rapporto** `task-8-report.md`, con l'elenco dei file toccati.

**Observable acceptance.** 4 test nuovi verdi (rossi prima); suite nominate verdi; nessun testo inglese del perimetro nei
sorgenti; banco con sole divergenze `@errore`.

---

## Ondata D — magazzino per settore e cassa negativa dell'infrannuale

### Task 9: Il banco ha un'azienda di Edilizia con magazzino lungo (commit a 0 divergenze)

**Esecutore:** pi (Orca) · **Revisore:** sonnet · **Ondata:** D, prima del Task 10

**Target (spec §4.8, «Celle attese»).** Il Task 10 cambia la guardia dei giorni di magazzino per i settori 5 e 6. Il
banco non ha fixture di quei settori e il suo driver crea ogni azienda con `sector=1`; nessun fixture ha un DIO dedotto
oltre 365 su ricavi veri (la holding ha ricavi zero). Questo task aggiunge due fixture con lo stesso bilancio (magazzino
di 1.000.000 sui 600.000 di ricavi del kit, cioe' 600 giorni), uno di settore 6 e uno di settore 1 per contrasto, e fa
passare il settore al driver. Motore invariato: 0 divergenze.

**Da leggere prima:** `scripts/parita_motore.py` — `_con_tributari_pregressi` (modello del fixture), `FIXTURES`,
`costruisci_griglia` (il dizionario appeso a `scenari`), la stringa `DRIVER` (la riga `Company(… sector=1, …)`).

**Trappole note.** I fixture nuovi vanno **in coda** a `FIXTURES`: ogni fixture ha il proprio generatore, quelli di prima
restano identici. Il cancello del motore vuole utile del CE = `sp13`: le rimanenze in piu' si bilanciano con le riserve,
non col risultato (misurato: con questo bilancio il previsionale si genera). `scripts/parita_motore.py` e' LF.

**Change.**
1. Dopo `TRIBUTARI_BS = …`:

```python
def _con_magazzino_lungo(bs: Dict[str, Decimal], rimanenze: Decimal) -> Dict[str, Decimal]:
    """Il fixture del kit con un magazzino oltre l'anno (lotto 3A, Task 9).

    Perche' esiste: la guardia dei giorni dedotti tiene fermo un DIO oltre 365 giorni; il lotto 3A la toglie per
    Immobiliare (5) ed Edilizia (6), dove un magazzino lungo e' normale. Le rimanenze salgono a `rimanenze` (1.000.000
    sui 600.000 di ricavi del kit = 600 giorni) e le riserve riassorbono la differenza: il CE resta quello del kit, e
    il cancello utile CE = `sp13` regge.
    """
    out = dict(bs)
    delta = rimanenze - D(str(bs.get("sp05_rimanenze", 0)))
    out["sp05_rimanenze"] = rimanenze
    out["sp05a_materie_prime"] = D(str(bs.get("sp05a_materie_prime", 0))) + delta
    out["sp12_riserve"] = D(str(bs.get("sp12_riserve", 0))) + delta
    out["sp12e_altre_riserve"] = D(str(bs.get("sp12e_altre_riserve", 0))) + delta
    return out


MAGAZZINO_BS = _con_magazzino_lungo(BASE_BS, D("1000000"))
```

2. In coda a `FIXTURES`: `("edilizia_magazzino", MAGAZZINO_BS, BASE_CE, D("1")),` e `("industria_magazzino", MAGAZZINO_BS, BASE_CE, D("1")),`;
   subito dopo la lista: `SETTORE_FIXTURE: Dict[str, int] = {"edilizia_magazzino": 6}` con un commento («il settore di
   ogni fixture; assente = 1, Industria»).
3. In `costruisci_griglia`, nel dizionario dello scenario aggiungi `"settore": SETTORE_FIXTURE.get(fixture_nome, 1),`.
4. In `DRIVER`, `sector=1` diventa `sector=scenario_def.get("settore", 1)`.

**Constraints.** Motore non toccato. 135 scenari (9 fixture × 15 profili).

**Ownership.** `scripts/parita_motore.py`, `tests/test_parita_griglia.py` (nuovo).

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task9-base`
- [ ] **Step 2: Test**, `tests/test_parita_griglia.py`:

```python
"""La griglia del banco ha un'azienda di Edilizia con magazzino lungo, e il driver usa il settore (lotto 3A, Task 9)."""
from decimal import Decimal as D

from scripts import parita_motore as banco


def test_la_griglia_ha_i_due_fixture_col_magazzino_lungo_e_il_loro_settore():
    griglia = banco.costruisci_griglia(20260910, 4)
    settori = {s["id"].split("__")[0]: s.get("settore") for s in griglia}
    assert len(griglia) == 135, len(griglia)
    assert settori.get("edilizia_magazzino") == 6
    assert settori.get("industria_magazzino") == 1
    assert settori.get("base") == 1
    edilizia = next(s for s in griglia if s["id"] == "edilizia_magazzino__neutro")
    giorni = D(edilizia["bs"]["sp05_rimanenze"]) / D(edilizia["ce"]["ce01_ricavi_vendite"]) * 360
    assert giorni == D("600")
    assert 'scenario_def.get("settore", 1)' in banco.DRIVER
```

- [ ] **Step 3: Prova rossa.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_parita_griglia.py -q -p no:cacheprovider`
  Atteso: 1 failed su `len(griglia) == 135` (oggi 105).
- [ ] **Step 4: Implementa** i punti 1-4.
- [ ] **Step 5: Verde.** Lo stesso comando.
- [ ] **Step 6: Banco.** Comando delle convenzioni con `task9`. Atteso: uscita 0, «NESSUNA DIVERGENZA — 135 scenari»,
  controllo negativo superato.
- [ ] **Step 7: Commit.** `git add scripts/parita_motore.py tests/test_parita_griglia.py && git commit -m "test(banco): due aziende col magazzino lungo, di Edilizia e di Industria, e il settore nel driver (lotto 3A, task 9)"`
- [ ] **Step 8: Rapporto** `task-9-report.md`.

**Observable acceptance.** Test verde (rosso prima); banco a 0 divergenze su 135 scenari.

---

### Task 10: Per Immobiliare ed Edilizia un magazzino oltre l'anno scala coi ricavi

**Esecutore:** pi (Orca) · **Revisore:** opus · **Ondata:** D, dopo i Task 8 e 9

**Target (spec §4.8, decisione del proprietario).** Il motore budget (`ForecastEngine._calculate_balance_sheet`,
funzione interna `_derived_days`, soglia `MAX_DERIVED_TURNOVER_DAYS` = 365) tratta un DIO dedotto oltre 365 come
degenere e tiene le rimanenze al valore base; l'infrannuale fa lo stesso con `_turnover_ratio` (rapporto oltre 1). Per
Immobiliare (settore 5) ed Edilizia (6) un magazzino oltre l'anno e' normale. Dopo: per i settori 5 e 6 la soglia non
si applica alle **rimanenze** (il DIO dedotto, anche oltre 365, scala coi ricavi nel budget e coi costi dei materiali
nell'infrannuale); negli altri settori resta com'e'. DSO e DPO invariati. Un denominatore nullo resta degenere in ogni
settore. La soglia per settore sta in una tabella sola (`projection_common`) e si dichiara. Misurato sullo snapshot
`452112d` (kit con magazzino 1.000.000, DIO dedotto 600, crescita ricavi 10%): oggi settori 1 e 6 identici, `sp05`
1.000.000,00 e cassa 144.222,22 nel 2027; il bersaglio del settore 6 (misurato con `dio_days` 600 esplicito) e' `sp05`
1.100.000,00 e cassa 44.222,22 nel 2027, 1.210.000,00 e 126.974,44 nel 2028. Oggi nessuno dei due motori legge il settore.

**Da leggere prima (sul branch del lotto 3A, per simbolo):** `calculations/forecast_engine.py` —
`MAX_DERIVED_TURNOVER_DAYS`, `ForecastEngine.compute_forecast` (la chiamata a `_calculate_balance_sheet`),
`_calculate_balance_sheet` (la sua firma, `_derived_days`, il blocco `# DIO → sp05 (inventory)`, la riga
`details['degenerate_turnover_ratio'] = degenerate_days`); `calculations/intra_year_engine.py` — `_MAX_TURNOVER_RATIO`,
`_turnover_ratio`, `IntraYearEngine.__init__`, `generate_projection`, `_scaled_or_carried`; `config.Sector`;
`database/models.py` — `BudgetScenario.company`, `Company.sector`.

**Trappole note.**
- Diagnose, never fabricate: fuori dai settori 5 e 6 la guardia resta identica; dentro, un DIO dedotto e' un dato
  dell'anno base, non un moltiplicatore inventato. La soglia applicata si dichiara sempre.
- `intra_year_engine.py` ha terminatori misti: niente normalizzazione; `git diff --stat` solo sulle righe cambiate.
- Un giorno **esplicito** dell'utente non passa dalla guardia (resta cosi').
- «Una chiave diagnostica si dichiara sempre, anche vuota»: `details['soglia_giorni_magazzino']` ogni anno.

**Change.**
1. `calculations/projection_common.py` (aggiungi `Optional` all'import da `typing`), in coda:

```python
# ── Giorni di magazzino dedotti: la soglia per settore (lotto 3A, Task 10) ──
# Oltre un anno di giacenza un DIO dedotto smette di descrivere l'azienda — tranne dove un magazzino lungo e' il
# mestiere: Immobiliare (5, immobili in rimanenza) ed Edilizia (6, lavori in corso). Un solo punto per la tabella,
# usato dal motore budget e dall'infrannuale. `None` = nessuna soglia.
GIORNI_MAGAZZINO_MAX_DEFAULT = Decimal('365')
GIORNI_MAGAZZINO_MAX_PER_SETTORE: Dict[int, Optional[Decimal]] = {5: None, 6: None}


def soglia_giorni_magazzino(settore) -> Optional[Decimal]:
    """La soglia oltre cui un DIO dedotto e' degenere nel settore dato, o `None` se non ce n'e'. Settore assente o
    non intero: la soglia di sempre."""
    try:
        chiave = int(settore) if settore is not None else None
    except (TypeError, ValueError):
        chiave = None
    return GIORNI_MAGAZZINO_MAX_PER_SETTORE.get(chiave, GIORNI_MAGAZZINO_MAX_DEFAULT)
```

2. Motore budget: `compute_forecast` legge `settore = getattr(getattr(source.scenario, 'company', None), 'sector', None)`
   una volta e lo passa a `_calculate_balance_sheet(…, settore=settore)` (parametro keyword nuovo, default `None`).
   `_derived_days(stock, flow_base, name, soglia=MAX_DERIVED_TURNOVER_DAYS)`: la condizione degenere diventa
   `days < 0 or (soglia is not None and days > soglia)`; il ramo `flow_base is None or flow_base <= 0` resta degenere.
   Nel blocco del DIO: `soglia_dio = soglia_giorni_magazzino(settore)` e `_derived_days(base_sp05, base_revenue, 'dio', soglia=soglia_dio)`.
   Accanto a `details['degenerate_turnover_ratio'] = degenerate_days`:
   `details['soglia_giorni_magazzino'] = {'settore': settore, 'giorni_max': soglia_giorni_magazzino(settore)}`.
3. Infrannuale: `IntraYearEngine.__init__` inizializza `self._settore = None`; `generate_projection`, subito dopo
   `_load_scenario`, scrive `self._settore = scenario.company.sector if scenario.company is not None else None`.
   `_turnover_ratio(stock, base, max_ratio=_MAX_TURNOVER_RATIO)`: `if max_ratio is not None and ratio > max_ratio: return None`.
   `_scaled_or_carried`: se `field == 'sp05_rimanenze'`, `soglia = soglia_giorni_magazzino(self._settore)`, altrimenti
   `soglia = Decimal('365')`; `max_ratio = None if soglia is None else soglia / Decimal('365')`; il diagnostico
   `degenerate_turnover_ratio` aggiunge `'soglia_giorni': None if soglia is None else str(soglia)`.

**Constraints.** DSO, DPO e gli altri rapporti dell'infrannuale invariati. Settori diversi da 5 e 6: nessun numero cambia.

**Ownership.** `calculations/projection_common.py`, `calculations/forecast_engine.py`, `calculations/intra_year_engine.py`,
`tests/test_forecast_magazzino_settore.py` (nuovo), `CLAUDE.md`, `docs/budget/API-PREVISIONALE.md`,
`docs/import/REGOLE-IMPORT-05-INFRANNUALE.md`.

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task10-base`
- [ ] **Step 2: Test**, `tests/test_forecast_magazzino_settore.py`:

```python
"""Per Immobiliare ed Edilizia un magazzino oltre l'anno scala coi ricavi; negli altri settori la guardia resta (lotto 3A, Task 10).

Budget: kit con rimanenze 1.000.000 (600 giorni sui 600.000 di ricavi), crescita ricavi 10%. Numeri dello snapshot
`452112d`: settore 1 com'e' oggi; settore 6 misurato con `dio_days` 600 esplicito, che e' il bersaglio. Il settore 5
segue la stessa regola del 6: il motore budget non legge il settore in nessun altro punto.
Infrannuale: rimanenze di riferimento 150.000 su 100.000 di materiali (rapporto 1,5), parziale 140.000.
"""
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services import assumptions_service, forecast_preview_service
from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year


def _budget(settore):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=f"magazzino-{settore}")
            db.query(Company).filter(Company.id == company_id).one().sector = settore
            fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
            b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
            b.sp05_rimanenze = D("1000000.00")
            b.sp05a_materie_prime = D("1000000.00")
            b.sp12_riserve += D("950000.00")
            b.sp12e_altre_riserve += D("950000.00")
            db.commit()
            sc = BudgetScenario(company_id=company_id, name="magazzino", base_year=2026, scenario_type="budget")
            db.add(sc)
            db.commit()
            righe = [{"forecast_year": anno, "revenue_growth_pct": 10, "tax_rate": 27.9} for anno in (2027, 2028)]
            esito = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in righe], auto_generate=True)
            assert esito["forecast_generated"] is True, esito["message"]
            anteprima = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in righe])
            dettagli = {a["year"]: a["details"] for a in anteprima["forecast_years"]}
            return {anno: (sp, dettagli[anno]) for anno, sp, _ce in read_forecast_maps(db, sc.id)}
    finally:
        engine.dispose()


@pytest.mark.parametrize("settore", [5, 6])
def test_immobiliare_ed_edilizia_scalano_le_rimanenze_coi_ricavi(settore):
    anni = _budget(settore)
    attesi = {2027: ("1100000.00", "44222.22"), 2028: ("1210000.00", "126974.44")}
    fuori = []
    for anno, (rimanenze, cassa) in attesi.items():
        sp, det = anni[anno]
        if sp["sp05_rimanenze"] != D(rimanenze) or sp["sp09_disponibilita_liquide"] != D(cassa):
            fuori.append(f"{anno}: sp05 {sp['sp05_rimanenze']} (atteso {rimanenze}), sp09 {sp['sp09_disponibilita_liquide']} (atteso {cassa})")
        if "dio" in det["degenerate_turnover_ratio"]:
            fuori.append(f"{anno}: dio dichiarato degenere")
        if D(str(det["dio_applied"])).quantize(D("0.000001")) != D("600"):
            fuori.append(f"{anno}: dio_applied {det['dio_applied']}")
        if det.get("soglia_giorni_magazzino") != {"settore": settore, "giorni_max": None}:
            fuori.append(f"{anno}: soglia dichiarata {det.get('soglia_giorni_magazzino')}")
    assert not fuori, "\n".join(fuori)


def test_negli_altri_settori_la_guardia_resta_com_e():
    anni = _budget(1)
    fuori = []
    for anno, cassa in {2027: "144222.22", 2028: "336974.44"}.items():
        sp, det = anni[anno]
        if sp["sp05_rimanenze"] != D("1000000.00") or sp["sp09_disponibilita_liquide"] != D(cassa):
            fuori.append(f"{anno}: sp05 {sp['sp05_rimanenze']}, sp09 {sp['sp09_disponibilita_liquide']}")
        if det["degenerate_turnover_ratio"] != ["dio"]:
            fuori.append(f"{anno}: degeneri {det['degenerate_turnover_ratio']}")
        soglia = det.get("soglia_giorni_magazzino") or {}
        if soglia.get("settore") != 1 or D(str(soglia.get("giorni_max"))) != D("365"):
            fuori.append(f"{anno}: soglia dichiarata {det.get('soglia_giorni_magazzino')}")
    assert not fuori, "\n".join(fuori)


def _infrannuale(settore):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    azienda = Company(name="Magazzino infra", tax_id="MAGAZZINO-INFRA", sector=settore)
    db.add(azienda)
    db.flush()
    for anno, mesi, stato, conto in (
        (2024, None, dict(sp05_rimanenze=D("150000"), sp05a_materie_prime=D("150000"), sp11_capitale=D("151000"),
                          sp09_disponibilita_liquide=D("1000")), dict(ce05_materie_prime=D("100000"), ce01_ricavi_vendite=D("100000"))),
        (2025, 9, dict(sp05_rimanenze=D("140000"), sp05a_materie_prime=D("140000"), sp11_capitale=D("151000"),
                       sp09_disponibilita_liquide=D("11000")), dict(ce05_materie_prime=D("90000"), ce01_ricavi_vendite=D("90000"))),
    ):
        fy = FinancialYear(company_id=azienda.id, year=anno, period_months=mesi, validation_status="verified", forecastable=True)
        db.add(fy)
        db.flush()
        db.add(BalanceSheet(financial_year_id=fy.id, **stato))
        db.add(IncomeStatement(financial_year_id=fy.id, **conto))
    scenario = BudgetScenario(company_id=azienda.id, name="infra", base_year=2024, scenario_type="infrannuale", period_months=9)
    db.add(scenario)
    db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0")))
    db.commit()
    esito = IntraYearEngine(db).generate_projection(scenario.id)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    diagnostici = [d for d in esito["diagnostics"]
                   if d["code"] == "degenerate_turnover_ratio" and d.get("field") == "sp05_rimanenze"]
    return sp.sp05_rimanenze, sp.sp09_disponibilita_liquide, diagnostici


def test_nell_infrannuale_l_edilizia_scala_il_magazzino_e_l_industria_lo_riporta():
    rimanenze, cassa, diagnostici = _infrannuale(6)
    assert (rimanenze, cassa, diagnostici) == (D("150000.00"), D("1000.00"), [])
    rimanenze, cassa, diagnostici = _infrannuale(1)
    assert (rimanenze, cassa) == (D("140000.00"), D("11000.00"))
    assert [d.get("soglia_giorni") for d in diagnostici] == ["365"]
```

- [ ] **Step 3: Prova rossa.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_magazzino_settore.py -q -p no:cacheprovider`
  Atteso: 4 failed sulle asserzioni (settori 5 e 6 fermi a 1.000.000; soglia non dichiarata; infrannuale di Edilizia
  riportato a 140.000).
- [ ] **Step 4: Implementa** i punti 1-3.
- [ ] **Step 5: Verde.** Lo stesso comando, poi
  `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_giorni_degeneri.py tests/test_intra_year_semantics.py tests/test_intra_year_plug_negativo.py tests/test_forecast_dichiarato_vs_persistito.py tests/test_budget_pregresso.py -q -p no:cacheprovider`
- [ ] **Step 6: Documenti.** `CLAUDE.md`, «Intra-Year Engine», bullet «Working capital»: dopo «… a `degenerate_turnover_ratio`
  diagnostic» aggiungi «— except for inventory in Real estate (sector 5) and Construction (6), where a stock longer than a
  year is the business: there the ratio scales (`projection_common.soglia_giorni_magazzino`, one table for both engines;
  the budget engine declares it in `details['soglia_giorni_magazzino']`)». `docs/budget/API-PREVISIONALE.md` §4:
  aggiungi la regola e la chiave `soglia_giorni_magazzino` `{settore, giorni_max}` (`giorni_max` `null` = nessuna soglia).
  `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §5, «Rapporti di rotazione degeneri»: un paragrafo sull'eccezione di
  settore per le rimanenze e sul campo `soglia_giorni` del diagnostico.
- [ ] **Step 7: Banco.** Comando delle convenzioni con `task10`, poi
  `/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_riepilogo.py /tmp/lotto3a-task10-parita.json --attese '*|details.soglia_giorni_magazzino' 'edilizia_magazzino__*|balance_sheet.*' 'edilizia_magazzino__*|details.*' 'edilizia_magazzino__*|@errore' 'edilizia_magazzino__*|@anno'`.
  Atteso: uscita del banco 1, controllo negativo superato, «fuori dalle attese: 0»; nessuna divergenza su
  `industria_magazzino` salvo `details.soglia_giorni_magazzino`, nessuna `income_statement.*`.
- [ ] **Step 8: Commit.** `git add calculations/projection_common.py calculations/forecast_engine.py calculations/intra_year_engine.py tests/test_forecast_magazzino_settore.py CLAUDE.md docs/budget/API-PREVISIONALE.md docs/import/REGOLE-IMPORT-05-INFRANNUALE.md && git commit -m "feat(engine): per Immobiliare ed Edilizia il magazzino oltre l'anno scala, soglia per settore dichiarata (lotto 3A, task 10)"`
- [ ] **Step 9: Rapporto** `task-10-report.md`.

**Observable acceptance.** 4 test nuovi verdi (rossi prima); suite nominate verdi; banco con sole divergenze ammesse.

---

### Task 11: Sull'infrannuale un override che squilibra non persiste una cassa negativa

**Esecutore:** pi (Orca) · **Revisore:** opus · **Ondata:** D, dopo i Task 4, 5 e 8 (stesso file, messaggi gia' italiani);
se gira in parallelo al Task 10, il suo merge va dopo quello del Task 10

**Target (spec §4.9, difetto §11.1 della spec del lotto 2).** `IntraYearEngine.generate_projection` applica gli
`sp_overrides` (`ForecastEngine._apply_sp_overrides`, con il clamp a zero della cassa) e poi
`ForecastEngine._normalize_balance_sheet_cents(projected_bs, recompute_cash=not ha_errori)`, che senza diagnostiche
d'errore ricalcola la cassa come passivo meno attivo **senza clamp**. **Confermato con una sonda sullo snapshot
`452112d`:** riferimento 2024 (cassa 1.000, capitale 1.000), parziale 2025 di 9 mesi (cassa 1.100, capitale 1.000,
utile 100, ricavi 100), ipotesi con `ce01_override` 555 e `sp_overrides` `{"sp05_rimanenze": 5000000}` → `sp09`
**−4.998.445,00** persistita, con le sole diagnostiche `degenerate_turnover_ratio` di severita' warning. Con `sp08` a 1.500
la cassa resta 55,00; con `sp11` a 1.200 resta 1.755,00. Dopo: la stessa regola del previsionale — il fabbisogno si
misura una volta sola, dopo l'override, sulla cassa ricalcolata — e sull'infrannuale diventa l'avviso
`unfunded_financing_requirement` (severita' `error`) con la cassa a zero, come ogni altro fabbisogno di quel motore.
Mai una `sp09` negativa persistita.

**Da leggere prima (sul branch del lotto 3A):** `calculations/intra_year_engine.py` — `generate_projection` (dalla
proiezione dello SP al `_save_forecast`) e i due diagnostici `unfunded_financing_requirement` gia' presenti in
`_project_balance_sheet` e `_project_balance_sheet_annualized` (il loro testo, italiano dal Task 8, e' quello da
riusare); `calculations/forecast_engine.py` — `_apply_sp_overrides` e `_normalize_balance_sheet_cents` (il giro finale
del lotto 2 li ha toccati: rileggili, ma questo task **non** li modifica); `backend/app/services/promote_service.py`
(solo lettura: il cancello semantico rifiuta un foglio che non quadra).

**Trappole note.**
- CLAUDE.md › Intra-Year Engine: sull'infrannuale un fabbisogno scoperto e' un avviso con la cassa a zero, **non** un
  errore che ferma la proiezione e **non** un debito a breve. Il foglio che ne esce non quadra, e il promote lo rifiuta: e'
  il comportamento di sempre per quel motore.
- «Un difetto che quadra si corregge a monte»: il controllo va sulla cifra finale, dopo la normalizzazione, non prima
  dell'override.
- `intra_year_engine.py` ha terminatori misti: niente normalizzazione; `git diff --stat` solo sulle righe cambiate.

**Change.** In `generate_projection`, subito dopo la chiamata a `ForecastEngine._normalize_balance_sheet_cents(...)` e
prima di `self._save_forecast(...)`:

```python
        # §11.1 sull'infrannuale (lotto 3A, Task 11): un `sp_overrides` che squilibra lo SP arriva qui con una cassa
        # ricalcolata negativa, perche' il ricalcolo della normalizzazione scavalca il clamp degli override. Il
        # fabbisogno si misura una volta sola, su questa cifra finale, e su questo motore e' un avviso con la cassa a
        # zero — mai una `sp09` negativa persistita.
        cassa = projected_bs.get('sp09_disponibilita_liquide')
        if cassa is not None and cassa < 0:
            self._diagnostics.append({
                'code': 'unfunded_financing_requirement',
                'severity': 'error',
                'amount': str(-cassa),
                'message': (
                    "L'attivo proiettato supera le fonti di finanziamento esplicite: aggiungi un'ipotesi di "
                    "finanziamento esplicita; nessun debito è stato creato automaticamente."
                ),
            })
            projected_bs['sp09_disponibilita_liquide'] = Decimal('0.00')
```

Il testo del `message` si copia dal diagnostico gia' presente in `_project_balance_sheet` (dal Task 8:
«L'attivo proiettato supera le fonti di finanziamento esplicite: aggiungi un'ipotesi di finanziamento esplicita; nessun
debito è stato creato automaticamente.»); se nel file e' diverso, vince quello del file e lo si scrive nel rapporto.

**Constraints.** Nessun cambio al motore budget: banco a 0 divergenze. Una proiezione senza cassa negativa non cambia.

**Ownership.** `calculations/intra_year_engine.py`, `tests/test_intra_year_override_cassa.py` (nuovo), `CLAUDE.md`,
`docs/import/REGOLE-IMPORT-05-INFRANNUALE.md`.

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task11-base`
- [ ] **Step 2: Test**, `tests/test_intra_year_override_cassa.py`:

```python
"""Sull'infrannuale un override che squilibra non persiste una cassa negativa (lotto 3A, Task 11; §11.1 del lotto 2).

Sonda sullo snapshot `452112d`: con `sp05_rimanenze` forzato a 5.000.000 la proiezione persisteva `sp09` −4.998.445,00
con le sole diagnostiche warning.
"""
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.promote_service import promote_projection_to_financial_year
from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)


def _proietta(override):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    azienda = Company(name="Override infra", tax_id="OVERRIDE-INFRA", sector=1)
    db.add(azienda)
    db.flush()
    for anno, mesi, utile in ((2024, None, D("0")), (2025, 9, D("100"))):
        fy = FinancialYear(company_id=azienda.id, year=anno, period_months=mesi, validation_status="verified", forecastable=True)
        db.add(fy)
        db.flush()
        db.add(BalanceSheet(financial_year_id=fy.id, sp09_disponibilita_liquide=D("1000") + utile,
                            sp11_capitale=D("1000"), sp13_utile_perdita=utile))
        db.add(IncomeStatement(financial_year_id=fy.id, ce01_ricavi_vendite=utile))
    scenario = BudgetScenario(company_id=azienda.id, name="infra", base_year=2024, scenario_type="infrannuale", period_months=9)
    db.add(scenario)
    db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"),
                             ce01_override=D("555"), sp_overrides=override))
    db.commit()
    esito = IntraYearEngine(db).generate_projection(scenario.id)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    fabbisogni = [d for d in esito["diagnostics"] if d["code"] == "unfunded_financing_requirement"]
    return db, scenario, sp.sp09_disponibilita_liquide, fabbisogni


def test_un_override_che_squilibra_diventa_un_fabbisogno_dichiarato_con_la_cassa_a_zero():
    db, scenario, cassa, fabbisogni = _proietta({"sp05_rimanenze": 5000000})
    assert cassa == D("0.00"), f"cassa persistita {cassa}"
    assert [(d["severity"], d["amount"]) for d in fabbisogni] == [("error", "4998445.00")]
    with pytest.raises(ValueError):
        promote_projection_to_financial_year(db, scenario.id)


@pytest.mark.parametrize("override, cassa_attesa", [
    ({"sp08_attivita_finanziarie": 1500}, "55.00"),
    ({"sp11_capitale": 1200}, "1755.00"),
], ids=["attivo che la cassa copre", "capitale forzato"])
def test_un_override_che_la_cassa_copre_non_cambia_nulla(override, cassa_attesa):
    _db, _scenario, cassa, fabbisogni = _proietta(override)
    assert (cassa, fabbisogni) == (D(cassa_attesa), [])
```

- [ ] **Step 3: Prova rossa.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_intra_year_override_cassa.py -q -p no:cacheprovider`
  Atteso: 1 failed su `cassa == 0.00` (oggi −4.998.445,00); gli altri due passano gia' (sono il contrasto).
- [ ] **Step 4: Implementa** il Change.
- [ ] **Step 5: Verde.** Lo stesso comando, poi
  `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_intra_year_plug_negativo.py tests/test_intra_year_semantics.py tests/test_intra_year_end_to_end_periods.py tests/test_intra_year_debito_bancario.py tests/test_intra_year_imposte.py -q -p no:cacheprovider`
- [ ] **Step 6: Documenti.** `CLAUDE.md`, «Intra-Year Engine», bullet che dice «qui è **clampato a zero** con una diagnostica
  `unfunded_financing_requirement`»: aggiungi «— anche quando il fabbisogno nasce da un `sp_overrides` che squilibra lo
  SP: il controllo sta sulla cassa finale, dopo la normalizzazione (`generate_projection`), e mai una `sp09` negativa
  resta persistita». `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §5, «Il fabbisogno scoperto è un diagnostico, non un
  debito»: un paragrafo con lo stesso contenuto e il caso del test (rimanenze forzate a 5.000.000 → avviso di
  4.998.445,00, cassa a zero, promote rifiutato).
- [ ] **Step 7: Banco.** Comando delle convenzioni con `task11`. Atteso: uscita 0.
- [ ] **Step 8: Commit.** `git add calculations/intra_year_engine.py tests/test_intra_year_override_cassa.py CLAUDE.md docs/import/REGOLE-IMPORT-05-INFRANNUALE.md && git commit -m "fix(infrannuale): un override che squilibra diventa un fabbisogno dichiarato, mai una cassa negativa persistita (lotto 3A, task 11)"`
- [ ] **Step 9: Rapporto** `task-11-report.md`, con i numeri della prova rossa.

**Observable acceptance.** Il test rosso diventa verde, i due di contrasto restano verdi; suite dell'infrannuale verde;
banco a 0 divergenze.

---

## Ondata E — da sola

### Task 12: Il residuo di quadratura dello SP si posa solo su campi neutri, e si dichiara quando non ce n'e' uno libero

**Esecutore:** pi (Orca) · **Revisore:** opus · **Ondata:** E, per ultima fra le modifiche al motore e da sola

**Target (spec §4.7).** `ForecastEngine._normalize_balance_sheet_cents` posa il residuo di arrotondamento di ogni gruppo
sul campo di default e, se quello e' protetto, su un altro campo del gruppo. **Parte gia' fatta dal giro finale del
lotto 2** (non si rifa'): per `sp16`/`sp17` il ripiego sta solo su `d-g` e `_declared_sp_fields` non entra piu' fra i
campi protetti quando il default non e' gia' forzato. Misurato prima di quel giro, sullo snapshot `452112d`: 16 posature
su `sp16c` nella sonda della ricognizione, 8 sul banco (profili `crescita` e `misto`). **Resta da fare:**
1. una tabella nel codice dei campi **neutri rispetto ai confini di KPI** per **ogni** gruppo normalizzato, con l'ordine;
2. la regola unica: il residuo va sul primo campo neutro non protetto; i campi protetti sono solo quelli scritti di
   proposito e dichiarati da un piano **attivo** in quello scenario (lati di un saldo con piano di pregresso, voci
   indicizzate, la ripartizione `sp16a`/`sp17a`, e `sp16e` quando la posizione tributaria e' governata dal kernel,
   `details['imposte']['mode'] == 'saldo_acconto'`);
3. se nessun campo neutro e' libero, il residuo va sul primo campo neutro del gruppo e si **dichiara**:
   ogni voce di `details['residuo_quadratura']` porta `campo_dichiarato: bool`, vero solo in quel caso;
4. dichiarato = persistito anche quando il residuo cade su un campo che `details['pregresso']` descrive in modo
   `legacy` (senza piano): quel `generated` si riallinea dell'importo posato;
5. il test storico `tests/test_forecast_dichiarato_vs_persistito.py` si aggiorna.

**Tabella (esame del proprietario del piano sui confini di KPI del codice: la PFN e il rendiconto leggono
`sp16a-c`/`sp17a-c`; il DSO e le masse del pregresso escludono `sp06e/f`, `sp07e/f`; `sp14b` e' scritto dalle imposte
differite; `sp12h` ha segno proprio; `sp04b` e' un credito immobilizzato esigibile entro l'anno e `sp04e`/`sp14c` sono
derivati). Il primo campo di ogni tupla e' il default di oggi, cosi' un gruppo senza protezioni non si muove:**

```python
    _CAMPI_NEUTRI_RESIDUO: Dict[str, Tuple[str, ...]] = {
        "sp01_crediti_soci": ("sp01b_parte_da_richiamare", "sp01a_parte_richiamata"),
        "sp02_immob_immateriali": ("sp02g_altre_immob_imm", "sp02a_costi_impianto", "sp02b_costi_sviluppo",
                                   "sp02c_brevetti", "sp02d_concessioni", "sp02e_avviamento", "sp02f_immob_in_corso"),
        "sp03_immob_materiali": ("sp03d_altri_beni", "sp03a_terreni_fabbricati", "sp03b_impianti_macchinari",
                                 "sp03c_attrezzature", "sp03e_immob_in_corso"),
        "sp04_immob_finanziarie": ("sp04d_altri_titoli", "sp04a_partecipazioni", "sp04c_crediti_immob_lungo"),
        "sp05_rimanenze": ("sp05e_acconti", "sp05a_materie_prime", "sp05b_prodotti_in_corso",
                           "sp05c_lavori_in_corso", "sp05d_prodotti_finiti"),
        "sp06_crediti_breve": ("sp06g_crediti_altri_breve", "sp06d_crediti_controllanti_breve",
                               "sp06c_crediti_collegate_breve", "sp06b_crediti_controllate_breve",
                               "sp06a_crediti_clienti_breve"),
        "sp07_crediti_lungo": ("sp07g_crediti_altri_lungo", "sp07d_crediti_controllanti_lungo",
                               "sp07c_crediti_collegate_lungo", "sp07b_crediti_controllate_lungo",
                               "sp07a_crediti_clienti_lungo"),
        "sp12_riserve": ("sp12g_utili_perdite_portati", "sp12e_altre_riserve", "sp12a_riserva_sovrapprezzo",
                         "sp12b_riserve_rivalutazione", "sp12c_riserva_legale", "sp12d_riserve_statutarie",
                         "sp12f_riserva_copertura_flussi"),
        "sp14_fondi_rischi": ("sp14d_altri_fondi", "sp14a_fondi_trattamento_quiescenza"),
        "sp16_debiti_breve": ("sp16g_altri_debiti_breve", "sp16f_debiti_previdenza_breve",
                              "sp16e_debiti_tributari_breve", "sp16d_debiti_fornitori_breve"),
        "sp17_debiti_lungo": ("sp17g_altri_debiti_lungo", "sp17f_debiti_previdenza_lungo",
                              "sp17e_debiti_tributari_lungo", "sp17d_debiti_fornitori_lungo"),
    }
```

Mai bersaglio: `sp04b`, `sp04e`, `sp06e`, `sp06f`, `sp07e`, `sp07f`, `sp12h`, `sp14b`, `sp14c`, `sp16a-c`, `sp17a-c`.

**Da leggere prima, sul branch del lotto 3A (il giro finale del lotto 2 ha riscritto proprio questa zona: lo snapshot
non vale):** `calculations/forecast_engine.py` — `_normalize_balance_sheet_cents` (il dizionario `groups`, il cammino del
residuo, `posati`), `_declared_sp_fields`, `_pregresso_sp_forced_fields`, `_indexed_sp_forced_fields`,
`_BANK_DEBT_SPLIT_FIELDS`, l'unione dei `forced_fields` in `compute_forecast`, e il blocco che scrive
`details['pregresso']` e `details['imposte']` in `_calculate_balance_sheet`. Dal Task 2: `_Sweep` (attributi
`rimborso_breve`, `rimborso_lungo`) e il parametro `sweep` di `_normalize_balance_sheet_cents`.
`tests/test_forecast_dichiarato_vs_persistito.py` (`_divergenze`, `PIANI`, il commento sulla «sesta occorrenza»).

**Trappole note.**
- Dichiarato = persistito; «un errore che attraversa un confine di KPI no» (CLAUDE.md › Contabilita').
- Il centesimo non sparisce mai: se nessun campo e' libero si posa e si dichiara.
- Un gruppo senza protezioni non deve muoversi di un centesimo: per questo il default di oggi e' il primo della tupla.
- Se il codice del lotto 2 fa gia' uno dei punti 2-4, lo si verifica col test e non lo si duplica; lo si scrive nel rapporto.
- `forecast_engine.py` e' LF.

**Change (contratto).** `_CAMPI_NEUTRI_RESIDUO` come attributo di classe di `ForecastEngine` (sopra). In
`_normalize_balance_sheet_cents` il dizionario `groups` resta la fonte dei campi di ogni gruppo; per ogni gruppo il
bersaglio e' `next((c for c in _CAMPI_NEUTRI_RESIDUO[aggregato] if c not in forced_fields), None)`; se `None`, il
bersaglio e' `_CAMPI_NEUTRI_RESIDUO[aggregato][0]` e la voce posata e' dichiarata. Ogni voce di `posati` diventa
`{'campo': bersaglio, 'importo': residuo, 'campo_dichiarato': <bool>}`. Riallineamento (punto 4): dopo aver posato, se
`details` contiene `pregresso` e il bersaglio e' il campo **breve** di un saldo (`_PREGRESSO_SP_FIELDS`) il cui
`details['pregresso'][saldo]['mode'] == 'legacy'`, allora `details['pregresso'][saldo]['generated'] += residuo`.
`forced_fields` passato da `compute_forecast` = `_pregresso_sp_forced_fields(pregresso)` ∪
`_indexed_sp_forced_fields(details)` ∪ `_BANK_DEBT_SPLIT_FIELDS` ∪ `{'sp16e_debiti_tributari_breve'}` se
`details['imposte']['mode'] == 'saldo_acconto'`; `_declared_sp_fields` non entra piu' nell'unione (se resta usata altrove,
lasciala; se non ha altri usi, cancellala e scrivilo nel rapporto).

**Constraints.** Aggregati, totali, cassa e CE invariati. Mai una posatura su un campo fuori dalla tabella.

**Ownership.** `calculations/forecast_engine.py`, `tests/test_forecast_residuo_neutro.py` (nuovo),
`tests/test_forecast_dichiarato_vs_persistito.py`, `CLAUDE.md`, `docs/budget/API-PREVISIONALE.md`.

- [ ] **Step 1: Base.** `git rev-parse HEAD > /tmp/lotto3a-task12-base`
- [ ] **Step 2: Test**, `tests/test_forecast_residuo_neutro.py`:

```python
"""Il residuo di quadratura dello SP va solo su campi neutri; se nessuno e' libero si posa sul default e si dichiara (lotto 3A, Task 12)."""
import json
import sys
from decimal import ROUND_HALF_UP, Decimal as D

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from calculations.forecast_engine import ForecastEngine
from database.models import BalanceSheet, FinancialYear
from tests.e2e_kit import memory_sessions, seed_base_year

NEUTRI = {
    "sp01_crediti_soci": ("sp01b_parte_da_richiamare", "sp01a_parte_richiamata"),
    "sp02_immob_immateriali": ("sp02g_altre_immob_imm", "sp02a_costi_impianto", "sp02b_costi_sviluppo",
                               "sp02c_brevetti", "sp02d_concessioni", "sp02e_avviamento", "sp02f_immob_in_corso"),
    "sp03_immob_materiali": ("sp03d_altri_beni", "sp03a_terreni_fabbricati", "sp03b_impianti_macchinari",
                             "sp03c_attrezzature", "sp03e_immob_in_corso"),
    "sp04_immob_finanziarie": ("sp04d_altri_titoli", "sp04a_partecipazioni", "sp04c_crediti_immob_lungo"),
    "sp05_rimanenze": ("sp05e_acconti", "sp05a_materie_prime", "sp05b_prodotti_in_corso",
                       "sp05c_lavori_in_corso", "sp05d_prodotti_finiti"),
    "sp06_crediti_breve": ("sp06g_crediti_altri_breve", "sp06d_crediti_controllanti_breve",
                           "sp06c_crediti_collegate_breve", "sp06b_crediti_controllate_breve", "sp06a_crediti_clienti_breve"),
    "sp07_crediti_lungo": ("sp07g_crediti_altri_lungo", "sp07d_crediti_controllanti_lungo",
                           "sp07c_crediti_collegate_lungo", "sp07b_crediti_controllate_lungo", "sp07a_crediti_clienti_lungo"),
    "sp12_riserve": ("sp12g_utili_perdite_portati", "sp12e_altre_riserve", "sp12a_riserva_sovrapprezzo",
                     "sp12b_riserve_rivalutazione", "sp12c_riserva_legale", "sp12d_riserve_statutarie",
                     "sp12f_riserva_copertura_flussi"),
    "sp14_fondi_rischi": ("sp14d_altri_fondi", "sp14a_fondi_trattamento_quiescenza"),
    "sp16_debiti_breve": ("sp16g_altri_debiti_breve", "sp16f_debiti_previdenza_breve",
                          "sp16e_debiti_tributari_breve", "sp16d_debiti_fornitori_breve"),
    "sp17_debiti_lungo": ("sp17g_altri_debiti_lungo", "sp17f_debiti_previdenza_lungo",
                          "sp17e_debiti_tributari_lungo", "sp17d_debiti_fornitori_lungo"),
}
FINANZIARI = ("sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve", "sp16c_debiti_obbligazioni_breve",
              "sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo", "sp17c_debiti_obbligazioni_lungo")


def _q(x):
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def test_la_tabella_dei_campi_neutri_sta_nel_codice():
    assert getattr(ForecastEngine, "_CAMPI_NEUTRI_RESIDUO", None) == NEUTRI


def _griglia_in_processo(tmp_path):
    """Il driver del banco eseguito in questo processo (seme 20260910, 4 anni): una spia sul motore lo vede."""
    from scripts import parita_motore as banco
    ingresso, uscita = tmp_path / "in.json", tmp_path / "out.json"
    ingresso.write_text(json.dumps({"scenari": banco.costruisci_griglia(20260910, 4)}), encoding="utf-8")
    spazio = {"__name__": "driver_banco"}
    exec(compile(banco.DRIVER, "driver_banco", "exec"), spazio)
    argv = sys.argv
    sys.argv = ["driver_banco", str(banco.REPO_ROOT), str(ingresso), str(uscita)]
    try:
        assert spazio["main"]() == 0
    finally:
        sys.argv = argv
    return json.loads(uscita.read_text(encoding="utf-8"))


def test_sulla_griglia_ogni_residuo_sta_su_un_campo_neutro_e_i_debiti_finanziari_non_si_muovono(tmp_path, monkeypatch):
    originale = ForecastEngine.__dict__["_normalize_balance_sheet_cents"].__func__
    violazioni, chiamate = [], []

    def spia(cls, values, **kw):
        risultato = originale(cls, values, **kw)
        scoperto = kw.get("overdraft")
        if scoperto is not None:
            sweep = kw.get("sweep")
            rimborsato = (sweep.rimborso_breve + sweep.rimborso_lungo) if sweep is not None else D("0")
            prima = sum((_q(values[f]) for f in FINANZIARI), D("0"))
            dopo = sum((risultato[f] for f in FINANZIARI), D("0"))
            chiamate.append(1)
            if dopo != prima + scoperto.outstanding - rimborsato:
                violazioni.append(f"debiti finanziari: prima {prima}, dopo {dopo}, scoperto {scoperto.outstanding}, sweep {rimborsato}")
        return risultato

    monkeypatch.setattr(ForecastEngine, "_normalize_balance_sheet_cents", classmethod(spia))
    esiti = _griglia_in_processo(tmp_path)
    neutri = {campo for campi in NEUTRI.values() for campo in campi}
    for sid, esito in sorted(esiti.items()):
        for anno in esito["anni"]:
            for posa in anno["details"].get("residuo_quadratura", []):
                dove = f"[{sid} · {anno['anno']}] {posa}"
                if not isinstance(posa.get("campo_dichiarato"), bool):
                    violazioni.append(f"{dove}: campo_dichiarato assente")
                if posa["campo"] not in neutri:
                    violazioni.append(f"{dove}: campo non neutro")
    assert len(chiamate) >= 380, len(chiamate)
    assert not violazioni, f"{len(violazioni)} violazioni:\n" + "\n".join(violazioni[:40])


PIANI_TUTTI = {
    "debiti_fornitori": {"opening": 100000, "amounts": [33333.335, 33333.335, 33333.33]},
    "debiti_tributari": {"opening": 10000, "saldo": 6000, "rateizzato": 4000, "amounts": [1333.335, 1333.335, 1333.33]},
    "debiti_previdenziali": {"opening": 25000, "amounts": [8333.335, 8333.335, 8333.33]},
    "altri_debiti": {"opening": 55000, "amounts": [18333.335, 18333.335, 18333.33]},
}
INVESTIMENTI = {"intangible_investments": 0.02, "tangible_investments": 0.02, "depreciation_rate": 20, "depreciation_rate_intangible": 20}
CRESCITE = (1.11, 3.33, 7.77, 0.37, 2.5, 4.44, 6.66, 9.99)


def _base_ricca(db, user):
    """La base di `tests/test_forecast_dichiarato_vs_persistito.py`: massa su ogni debito operativo, a breve e oltre."""
    company_id, _ = seed_base_year(db, user_id=user)
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
    for campo, valore in {
        "sp16_debiti_breve": "145000", "sp16b_debiti_altri_finanz_breve": "5000", "sp16d_debiti_fornitori_breve": "80000",
        "sp16e_debiti_tributari_breve": "10000", "sp16f_debiti_previdenza_breve": "15000", "sp16g_altri_debiti_breve": "35000",
        "sp17a_debiti_banche_lungo": "0", "sp17d_debiti_fornitori_lungo": "20000", "sp17f_debiti_previdenza_lungo": "10000",
        "sp17g_altri_debiti_lungo": "20000", "sp03_immob_materiali": "140000", "sp04_immob_finanziarie": "20000",
        "sp04a_partecipazioni": "20000", "sp01_crediti_soci": "3000", "sp01b_parte_da_richiamare": "3000",
        "sp08_attivita_finanziarie": "4000", "sp10_ratei_risconti_attivi": "5000", "sp14_fondi_rischi": "6000",
        "sp14d_altri_fondi": "6000", "sp18_ratei_risconti_passivi": "2000", "sp09_disponibilita_liquide": "31000",
    }.items():
        setattr(b, campo, D(valore))
    db.commit()
    return company_id


def test_con_tutti_i_debiti_operativi_pianificati_il_residuo_resta_sul_default_e_si_dichiara(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    posature = []
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            for crescita in CRESCITE:
                user = f"residuo-{crescita}"
                company_id = _base_ricca(db, user)
                righe = [dict(forecast_year=anno, revenue_growth_pct=crescita, **INVESTIMENTI) for anno in (2027, 2028, 2029)]
                righe[0]["pregresso"] = PIANI_TUTTI
                sc = budget_scenarios.create_budget_scenario(
                    company_id, BudgetScenarioCreate(company_id=company_id, name="residuo", base_year=2026, scenario_type="budget"),
                    user_id=user, db=db)
                esito = budget_scenarios.bulk_upsert_assumptions(
                    company_id, sc.id, request={"assumptions": [dict(r) for r in righe], "auto_generate": True}, user_id=user, db=db)
                assert esito["forecast_generated"] is True, esito["message"]
                anteprima = budget_scenarios.preview_forecast_route(
                    company_id, sc.id, request={"assumptions": [dict(r) for r in righe]}, user_id=user, db=db)
                for anno in anteprima["forecast_years"]:
                    posature += [(crescita, anno["year"], p) for p in anno["details"]["residuo_quadratura"]
                                 if p["campo"].startswith(("sp16", "sp17"))]
    finally:
        engine.dispose()
    assert posature, "nessun residuo su sp16/sp17 in questi scenari: vedi lo Step 3"
    fuori = [p for p in posature
             if p[2]["campo"] not in ("sp16g_altri_debiti_breve", "sp17g_altri_debiti_lungo") or p[2].get("campo_dichiarato") is not True]
    assert not fuori, "\n".join(str(p) for p in fuori)
```

- [ ] **Step 3: Misura prima del rosso, e prova rossa.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_residuo_neutro.py -q -p no:cacheprovider`
  Atteso: `test_la_tabella_…` fallisce (attributo assente); il test della griglia fallisce su «campo_dichiarato assente»
  (e, se il lotto 2 ha lasciato qualche caso, su «campo non neutro»); il terzo fallisce su `campo_dichiarato is not True`.
  **Questo scenario non e' stato misurato dopo il giro finale del lotto 2.** Se il terzo fallisce invece su «nessun
  residuo su sp16/sp17», aggiungi a `CRESCITE` i valori `2.22, 5.55, 8.88, 1.23, 3.21` e rilancia; se ancora nessuna
  posatura compare, fermati e riferisci (lo scenario non esercita il caso: il revisore decide come costruirlo).
- [ ] **Step 4: Implementa** il contratto.
- [ ] **Step 5: Test storico.** In `tests/test_forecast_dichiarato_vs_persistito.py`, `_divergenze`: prima dei confronti
  costruisci `tolleranze = {p["campo"]: D(str(p["importo"])) for p in det["residuo_quadratura"] if p.get("campo_dichiarato")}`;
  in `confronta` accetta `_q(letto or 0) - _q(atteso) == tolleranze.get(campo, D("0"))` al posto dell'uguaglianza; nel
  controllo finale sui `dichiarati` salta le posature con `campo_dichiarato` vero e aggiungi
  `if posa["campo"] in FINANZIARI: fuori.append((posa["campo"], f"residuo di {posa['importo']} su un debito finanziario"))`
  con `FINANZIARI` = i sei campi `sp16a-c`/`sp17a-c`. Riscrivi il commento del piano «tributari + previdenziali + altri»
  (quello della «sesta occorrenza»): il bersaglio non e' ne' `sp16d` ne' `sp16c`, e' il primo campo neutro libero della
  tabella `_CAMPI_NEUTRI_RESIDUO` (qui `sp16d`, perche' e, f e g hanno un piano).
- [ ] **Step 6: Verde.** Lo stesso comando dello Step 3, poi
  `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_dichiarato_vs_persistito.py tests/test_forecast_sweep_piani.py tests/test_forecast_prestito_quota_breve.py tests/test_forecast_scoperto.py tests/test_forecast_indicizzazione.py tests/test_budget_pregresso.py tests/test_forecast_override_residuo.py tests/test_intra_year_plug_negativo.py -q -p no:cacheprovider`
- [ ] **Step 7: Documenti.** `grep -n "residuo_quadratura\|residuo di quadratura" CLAUDE.md docs/budget/API-PREVISIONALE.md`:
  dove il bersaglio del residuo e' descritto, sostituisci la descrizione con la regola del contratto; se non e' descritto
  da nessuna parte, aggiungi in `CLAUDE.md` «Invarianti e trappole › Previsionale» il punto «**Il centesimo di quadratura
  dello SP si posa solo su un campo neutro del proprio gruppo** (`ForecastEngine._CAMPI_NEUTRI_RESIDUO`), mai su un
  debito finanziario, un credito o fondo fiscale, una riserva negativa: attraversare un confine di KPI cambia PFN e
  rendiconto di un centesimo senza che nessun controllo lo veda. Se ogni campo neutro e' gia' scritto da un piano, il
  centesimo si posa sul primo e `details['residuo_quadratura']` lo dichiara con `campo_dichiarato: true`.» e in
  `docs/budget/API-PREVISIONALE.md` §2.2 una riga su `residuo_quadratura` (`{campo, importo, campo_dichiarato}`).
- [ ] **Step 8: Banco.** Comando delle convenzioni con `task12`, poi
  `/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_riepilogo.py /tmp/lotto3a-task12-parita.json --attese '*|details.residuo_quadratura' '*|details.pregresso' '*|balance_sheet.sp1[67][defg]_*'`
  Atteso: controllo negativo superato, «fuori dalle attese: 0». Poi verifica che i movimenti siano coppie di segno opposto
  nello stesso anno-scenario:
  `/home/peter/DEV/budget/backend/venv/bin/python -c "import json,collections,decimal;d=json.load(open('/tmp/lotto3a-task12-parita.json'));s=collections.defaultdict(decimal.Decimal);n=lambda v: decimal.Decimal(v.replace('.','').replace(',','.')) if v not in ('—','(assente)') else decimal.Decimal(0);[s.__setitem__((x['scenario'],x['anno']), s[(x['scenario'],x['anno'])]+n(x['valore_b'])-n(x['valore_a'])) for x in d['divergenze'] if x['campo'].startswith('balance_sheet.')];print({k:v for k,v in s.items() if v})"`
  → `{}` (nessun anno-scenario con somma dei movimenti diversa da zero).
- [ ] **Step 9: Commit.** `git add calculations/forecast_engine.py tests/test_forecast_residuo_neutro.py tests/test_forecast_dichiarato_vs_persistito.py CLAUDE.md docs/budget/API-PREVISIONALE.md && git commit -m "fix(engine): il centesimo di quadratura dello SP solo su campi neutri, dichiarato quando nessuno e' libero (lotto 3A, task 12)"`
- [ ] **Step 10: Rapporto** `task-12-report.md`, con: quali punti del contratto il lotto 2 aveva gia' fatto, il numero
  di posature per campo sulla griglia prima e dopo, e le coppie di movimenti del banco.

**Observable acceptance.** 3 test nuovi verdi (rossi prima sulle asserzioni); `test_forecast_dichiarato_vs_persistito.py`
verde; banco con soli movimenti ammessi, in coppie a somma zero; nessuna posatura fuori tabella sulla griglia.

---

## Ondata F — verifica di lotto

### Task 13: Verifica di fine lotto

**Esecutore:** pi (Orca) per suite, banco e brief; agente `collaudatore` per il collaudo a schermo; coordinatore per
`/riallinea` · **Revisore:** sonnet · **Ondata:** F, dopo tutti gli altri

**Target (spec §6).** Suite intere pulite, banco con le sole divergenze attese dai task sommate, collaudo a schermo dei
cinque percorsi, riallineamento della documentazione sul diff del lotto.

**Da leggere prima:** i rapporti `/home/peter/DEV/budget/.superpowers/sdd/2026-09-10-lotto3a-motori-rendiconto/task-*-report.md`
(divergenze osservate e scarti dichiarati).

**Constraints.** Nessuna modifica al codice in questo task: un difetto trovato si riferisce, non si corregge qui. Nessun
`git checkout`.

**Ownership.** `/home/peter/DEV/budget/.superpowers/sdd/2026-09-10-lotto3a-motori-rendiconto/task-13-report.md` e
`collaudo-brief.md` (registro, non si committano).

- [ ] **Step 1: Base del lotto.** `git merge-base HEAD feat/scadenziamento-pregresso > /tmp/lotto3a-base-lotto`
- [ ] **Step 2: Unione col lotto 3B, prima di tutto** (Global Constraints, «Ordine di integrazione col lotto
  gemello»: il 3B si integra per primo). Verifica se e' gia' dentro l'albero:
  `git merge-base --is-ancestor feat/lotto3b-client HEAD && echo integrato || echo da-unire`. Se «da-unire»:
  `git merge feat/lotto3b-client` (mai `git checkout`, `git stash` o `git reset --hard`; un conflitto su `CLAUDE.md`
  si risolve tenendo **entrambe** le aggiunte, le sezioni sono disgiunte: «Invarianti e trappole › Frontend» dal 3B,
  il resto dal 3A). In ogni caso, unione appena fatta o gia' presente:
  `git diff "$(cat /tmp/lotto3a-base-lotto)" HEAD -- CLAUDE.md` e rileggi per intero le sezioni toccate da entrambi
  i lotti («Forecasting Engine», «Intra-Year Engine», «Invarianti e trappole › Previsionale» e «› Frontend»). Questo
  task non modifica codice: un'affermazione che l'unione dei due lotti ha reso falsa si riferisce nel rapporto, non
  si corregge qui in silenzio.
- [ ] **Step 3: Suite Python intera.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests -q -p no:cacheprovider 2>&1 | tail -40`.
  Ogni fallimento si classifica: file di test toccato dal lotto (`git diff --name-only "$(cat /tmp/lotto3a-base-lotto)" HEAD -- tests`)
  oppure no. Un fallimento in un file non toccato si verifica sull'albero principale del branch integrato del lotto 2
  (`/home/peter/DEV/budget` non si tocca: si legge solo il rapporto della sua ultima suite) prima di dirlo preesistente.
- [ ] **Step 4: Frontend.** `test -e frontend/node_modules || ln -s /home/peter/DEV/budget/frontend/node_modules frontend/node_modules; cd frontend && npx vitest run && npx tsc --noEmit`
- [ ] **Step 5: Banco del lotto.** `/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/lotto3a-base-lotto)" HEAD --anni 4 --controllo-negativo --json /tmp/lotto3a-lotto-parita.json --log /tmp/lotto3a-lotto-parita.log`
  poi `/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_riepilogo.py /tmp/lotto3a-lotto-parita.json --attese '*|details.debito_bancario' '*|details.prestiti_nuovi_quota_breve' '*__finanziamento|balance_sheet.sp09_disponibilita_liquide' '*__finanziamento|balance_sheet.sp16a_debiti_banche_breve' '*__finanziamento|balance_sheet.sp16_debiti_breve' '*__finanziamento|balance_sheet.sp17a_debiti_banche_lungo' '*__finanziamento|balance_sheet.sp17_debiti_lungo' '*__finanziamento|details.cassa_assorbita' '*__sweep_*|balance_sheet.sp09_disponibilita_liquide' '*__sweep_*|balance_sheet.sp16a_debiti_banche_breve' '*__sweep_*|balance_sheet.sp16_debiti_breve' '*__sweep_*|balance_sheet.sp17a_debiti_banche_lungo' '*__sweep_*|balance_sheet.sp17_debiti_lungo' '*__sweep_*|details.cassa_assorbita' '*__sweep_*|details.cassa_sotto_minimo' '*__sweep_override|details.scoperto_generato' '*__sweep_override|details.scoperto_residuo' '*__sweep_override|details.fabbisogno_picco' '*__sweep_override|details.fabbisogno_picco_anno' '*__sweep_override|details.oneri_scoperto' '*__sweep_override|@anno' '*|@errore' '*|details.soglia_giorni_magazzino' 'edilizia_magazzino__*|balance_sheet.*' 'edilizia_magazzino__*|details.*' '*|details.residuo_quadratura' '*|details.pregresso' '*|balance_sheet.sp1[67][defg]_*'`
  Nota: la base del lotto non ha i profili dello sweep ne' i fixture di magazzino, ma il banco li genera dallo script
  dell'albero che lo lancia: le due versioni girano sulla stessa griglia di 135 scenari. Atteso: controllo negativo
  superato, «fuori dalle attese: 0», e nessuna divergenza `income_statement.*`.
- [ ] **Step 6: Brief del collaudo** in `collaudo-brief.md`, per l'agente `collaudatore` (server di sviluppo avviati dal
  coordinatore da `backend/` e `frontend/`, `DEV_USER_ID=dev-user-001`): cinque percorsi, ciascuno con i numeri da vedere.
  1. Wizard budget sul kit con un prestito nuovo (80.000 / 5 anni / 5%) e cash sweep a soglia zero: in SP Prev. la cassa
     cresce e il debito bancario segue il piano (16.000 a breve ogni anno), gli oneri finanziari in CE Prev. scendono di
     800 all'anno.
  2. Infrannuale con debito bancario a breve e un prestito nuovo, e con debito tributario d'apertura: la Proiezione mostra
     il pregresso a breve intatto piu' la rata del prestito, e i debiti tributari al solo saldo dell'anno; poi promote e un
     budget su quell'anno che genera, col saldo d'imposta del primo anno pari al debito proiettato.
  3. Rendiconto di una holding con proventi da partecipazioni: dividendi incassati nell'operativo, mezzi di terzi a zero.
  4. Bulk dal wizard con un tetto di scoperto negativo o un tasso oltre 100: toast con l'elenco dei campi in italiano, e le
     ipotesi di prima ancora li' ricaricando la pagina.
  5. Un piano che il motore rifiuta per fabbisogno: il messaggio in anteprima e nel toast e' italiano, importo all'europea.
- [ ] **Step 7: Collaudo.** Il coordinatore lancia l'agente `collaudatore` col brief; i rilievi vanno nel rapporto.
- [ ] **Step 8: Riallineamento.** Il coordinatore lancia `/riallinea` sul diff `$(cat /tmp/lotto3a-base-lotto)..HEAD`;
  i `file:riga` corretti meccanicamente si committano a parte, il resto va nel rapporto.
- [ ] **Step 9: Rapporto** `task-13-report.md`: esito delle suite (con la classificazione dei fallimenti), banco
  (divergenze per gruppo del riepilogo), rilievi del collaudo, esito di `/riallinea`, e quanto osservato nell'unione
  col lotto 3B (Step 2).

**Observable acceptance.** Suite Python, vitest e `tsc` puliti (o ogni fallimento classificato e riferito); banco del
lotto con sole divergenze attese e controllo negativo superato; collaudo senza rilievi bloccanti; `/riallinea` eseguito.

---

## Numeri ricontrollati

Misure con sonde sullo snapshot `452112d`, registrate in
`.superpowers/sdd/2026-09-10-lotto3a-motori-rendiconto/misure.md`. Qui solo cio' che diverge dalla spec o la precisa.

1. **§4.1, caso I2.** Gli «11.053,98» e i «50.000 di `sp17a`» della spec si riproducono solo con aliquota **24**: la sonda
   della revisione scriveva le righe sull'ORM, dove il default di colonna di `tax_rate` e' 24. Col 27,9 che mandano le
   schermate il fabbisogno e' 14.563,20 (atteso dopo: `sp17a` 24.563,20 nel 2027, cassa 105.570,37 nel 2028). Il test del
   Task 2 usa l'aliquota 24.
2. **§4.1, «Celle attese solo negli scenari con sweep e almeno un piano».** Spostare lo sweep sulla cassa al centesimo
   sposta fino a 0,01 fra `sp09` e `sp16a`/`sp17a` anche in scenari con sweep **senza** piano (misurato: 2029 del caso
   «dopo lo scoperto», cassa 0,01 → 0,00 e `sp17a` 11.271,55 → 11.271,54). I pattern del banco del Task 2 lo ammettono per
   i profili `sweep_*`.
3. **§4.1, «Zero celle di CE».** Vale sul banco perche' i suoi profili con scoperto hanno tasso zero. In uno scenario con
   scoperto concesso e `financing_interest_rate` > 0, lo scoperto che il vecchio ordine apriva (caso I2) non si apre piu',
   e gli `oneri_scoperto` dell'anno dopo — quindi `ce15`, imposte e risultato — cambiano.
4. **§4.1, sonda p5.** I 7.200 «indebiti» si confermano (3.200 + 2.400 + 1.600). Dopo la correzione `ce15` resta
   9.000 / 8.200 / 7.400 / 6.600: gli interessi erano giusti, sbagliato era estinguere il prestito.
5. **§4.2, «Contratto misto = due righe, zero differenze».** Oggi misto e due righe danno gia' gli stessi numeri, entrambi
   sbagliati (`sp16a` 0,00, `sp17a` 99.259,25): la prova rossa sta sui valori (39.259,25 / 60.000,00), non
   sull'uguaglianza.
6. **§4.3.** I numeri della spec si confermano (20.752,74 e 1.250.196,30). Senza anno di riferimento l'imposta su cui
   commisurare gli acconti non esiste: il piano la fissa a zero (tutta l'imposta dell'anno resta da versare), scelta non
   scritta nella spec.
7. **§4.4.** Scarto di 30.000,00 sulla holding confermato; `cashflow.py` non tratta i dividendi allo stesso modo (parte
   dall'utile netto e non sottrae `ce13`) e non cambia.
8. **§4.5.** Oggi un primo anno diverso da anno base + 1 e' accettato: il piano lo dichiara e non lo cambia. Con la
   pulizia dei `null`, lo schema tipizzato rifiuta 3 payload fra i 162 test che usano il bulk (2 in
   `test_budget_pregresso.py:350`, 1 in `test_forecast_scoperto.py:191`), e
   `test_forecast_preview.py::test_forecast_year_not_convertible_is_400_and_writes_nothing_on_both_endpoints` passa da 400
   a 422 sul bulk.
9. **§4.7, «sonda: 19 posature su 20».** Sullo snapshot `452112d` la sonda p2 da' **16** posature su `sp16c` e 4 su `sp06g`
   (20 in tutto); sul banco 8 su `sp16c` (profili `crescita` e `misto`). La parte `sp16`/`sp17` e' chiusa dal giro finale
   del lotto 2; lo scenario «tutti e quattro i debiti operativi pianificati» del Task 12 non e' stato misurato dopo quel
   giro (verifica esplicita allo Step 3).
10. **§4.8, «DIO dedotto 500».** Sui 600.000 di ricavi del kit 500 giorni non danno rimanenze al centesimo; il piano usa 600
    giorni (rimanenze 1.000.000). Il settore 5 non e' stato misurato a parte: il motore budget non legge il settore in
    nessun altro punto, quindi segue il 6 per costruzione.
11. **§4.9.** Confermato: `sp09` −4.998.445,00 persistita con sole diagnostiche warning.
12. **Banco.** Il default dello script e' `--anni 2`; il piano usa sempre `--anni 4` (lo sweep di `finanziamento` parte
    dal secondo anno). Anche `backend/app/schemas/cashflow_detailed.py` e' interamente CRLF, benche' non sia nell'elenco
    della spec.

## Copertura della spec

| Spec | Task |
|---|---|
| §3 banco come strumento, profili prima del cambio | 1, 9 (profili e fixture a 0 divergenze); contratto di parita' in ogni task |
| §4.1 perimetro dello sweep, sweep dopo gli override, `details['debito_bancario']` | 2 |
| §4.2 regole condivise, refactor a 0 divergenze, infrannuale | 3, 4 |
| §4.3 imposte dell'infrannuale, catena promote → budget | 5 |
| §4.4 dividendi, scarto dichiarato, `cashflow.py` | 6 |
| §4.5 schema tipizzato, contiguita', 422 italiano, nulla salvato | 7a |
| §4.5 wizard e Startup mostrano l'elenco degli errori | 7b |
| §4.6 messaggi italiani, codici invariati, client che smette di tradurre | 8 |
| §4.7 campi neutri per gruppo, dichiarazione, test storico | 12 |
| §4.8 soglia del magazzino per settore, budget e infrannuale | 9, 10 |
| §4.9 §11.1 sull'infrannuale | 11 |
| §6 verifica di fine lotto | 13 |
