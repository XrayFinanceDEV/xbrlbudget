# Stato lavoro e cosa manca — 21 luglio 2026

## Stato attuale

- **Suite completa: 225 passati, 3 saltati** (`$env:PYTHONPATH=(Get-Location).Path; pytest -q tests` dalla root `C:\DEV\xbrlbudget-main\xbrlbudget`).
- **NIENTE è committato.** Tutte le modifiche di questa sessione sono nel working tree, accanto al lavoro non committato preesistente (Codex). Decidere cosa/dove committare è il primo punto aperto qui sotto.
- Frontend: dev server fresco su http://localhost:3000, CSS e chunk servono 200. Serve un **hard-refresh** del browser (Ctrl+Shift+R).

## Cosa è stato fatto

### 1. Suite di test "generi diversi" (22 test, ortogonali alla matrice PDF di Codex)
- `tests/e2e_kit.py` — kit condiviso (in-memory DB, seed anno base, lettura forecast).
- `tests/test_engine_accounting_invariants.py` (5) — invarianti contabili del motore.
- `tests/test_http_full_cycle.py` (4) — ciclo intero via HTTP reale + multi-tenancy JWT.
- `tests/test_lifecycle_repeat.py` (4) — re-import, override/clear, reset, promote→budget, ri-promozione.
- `tests/test_xbrl_csv_full_cycle.py` (2) — rotte XBRL e CSV a ciclo completo.
- `tests/test_numeric_stress_cycle.py` (7) — stress numerico budget 5 anni.
- Verbale: `docs/outputs/problematiche_budget_adeguamento/PIANO-TEST-E2E-BILANCIO-2026-07-20.md` (sezione "Round 2").

### 2. Fix gap di prodotto — XBRL/CSV non forecastable (RISOLTO)
- `importers/iv_cee_hierarchy.py` — nuovo helper condiviso `reconcile_source_detail`: al momento dell'import contabilizza il residuo `aggregato − Σdettaglio` (SOLO positivo) nel bucket "altri" di ogni famiglia; aggregato e pareggio intatti; `ce09` ripartito immateriali/materiali sulla base cespiti `sp02`/`sp03`.
- Agganciato in `importers/xbrl_parser_enhanced.py` e `importers/csv_importer.py`.
- Test: `tests/test_source_detail_reconcile.py` (8 unit, incluso il caso residuo-negativo che NON va inghiottito).
- Review avversariale (opus): fix CORRETTO/ONESTO/SICURO; aggregato e Attivo=Passivo provabilmente mai alterati; idempotente; no-op su fonti ben formate; rotta PDF non toccata. Il rilievo Important (residuo negativo = bug parser da non mascherare) è stato corretto con il guard solo-positivo.

### 3. Fix ambiente — "grafica sparita" (NON era il codice)
- Causa: due dev server Next di xbrlbudget (uno del 20/07 su :3000, uno del 21/07 su :3001) sullo stesso `.next` → lo zombie di :3000 serviva HTML con hash di chunk invalidati → 404 su `_next/static/chunks/*` e `layout.css`.
- Fix applicato: uccisi entrambi i server, rimosso `.next` corrotto a server spenti, riavviato UN solo server fresco. Nessun file frontend è stato modificato in questa sessione.

---

## COSA MANCA (in ordine di priorità)

### A. Decidere ed eseguire i COMMIT — **azione richiesta**
Niente è committato. Il working tree contiene DUE insiemi di modifiche: (1) le mie di questa sessione, (2) il lavoro Codex preesistente (motore forecast/intra-year, schemi, frontend budget/infrannuale). Vanno separati.

**File di QUESTA sessione (test suite + fix gap):**
```
# solo test (nessuna modifica al motore/importer):
tests/__init__.py
tests/e2e_kit.py
tests/test_engine_accounting_invariants.py
tests/test_http_full_cycle.py
tests/test_lifecycle_repeat.py
tests/test_numeric_stress_cycle.py
tests/test_xbrl_csv_full_cycle.py
tests/test_source_detail_reconcile.py
docs/outputs/problematiche_budget_adeguamento/PIANO-TEST-E2E-BILANCIO-2026-07-20.md
docs/outputs/problematiche_budget_adeguamento/STATO-E-COSA-MANCA-2026-07-21.md
docs/superpowers/plans/2026-07-21-test-suite-generi-diversi.md

# fix gap XBRL/CSV (modifiche a codice di produzione):
importers/iv_cee_hierarchy.py     # + reconcile_source_detail
importers/xbrl_parser_enhanced.py # 1 chiamata all'helper
importers/csv_importer.py         # 1 chiamata all'helper
```

**Come farlo (consigliato: un branch dedicato, main pulito):**
```powershell
# 1) creare un branch per non mescolarsi al WIP Codex su main
git checkout -b test/generi-diversi-e-fix-forecastable

# 2) commit A — solo la suite di test + doc (a basso rischio)
git add tests/__init__.py tests/e2e_kit.py tests/test_engine_accounting_invariants.py `
        tests/test_http_full_cycle.py tests/test_lifecycle_repeat.py `
        tests/test_numeric_stress_cycle.py tests/test_xbrl_csv_full_cycle.py `
        tests/test_source_detail_reconcile.py `
        docs/superpowers/plans/2026-07-21-test-suite-generi-diversi.md `
        docs/outputs/problematiche_budget_adeguamento/PIANO-TEST-E2E-BILANCIO-2026-07-20.md `
        docs/outputs/problematiche_budget_adeguamento/STATO-E-COSA-MANCA-2026-07-21.md
git commit -m "test: suite 'generi diversi' (invarianti motore, ciclo HTTP+multitenancy, cicli ripetuti, rotte XBRL/CSV, stress numerico)"

# 3) commit B — il fix del gap (nota: xbrl_parser_enhanced.py e csv_importer.py hanno
#    ANCHE modifiche Codex? verificare `git diff` prima: se il file è tuo solo per
#    la riga dell'helper, aggiungilo; se contiene anche WIP Codex, usa `git add -p`)
git add -p importers/iv_cee_hierarchy.py importers/xbrl_parser_enhanced.py importers/csv_importer.py
git commit -m "fix(forecast): rendi proiettabili XBRL abbreviato e TEBE CSV (reconcile_source_detail nel bucket 'altri')"
```
> ⚠️ Verificare con `git diff importers/xbrl_parser_enhanced.py` e `git diff importers/csv_importer.py` che quei file **non** contengano già modifiche Codex non correlate. Se sì, usare `git add -p` per committare solo l'hunk dell'helper. `importers/iv_cee_hierarchy.py`: controllare allo stesso modo (dovrebbe essere solo il nuovo blocco helper).
>
> Chiudere ogni messaggio di commit con: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` se si vuole mantenere la convenzione.

### B. Frontend — hard-refresh del browser (azione utente)
Aprire http://localhost:3000 e fare **Ctrl+Shift+R**. Se la grafica manca ancora:
- confermare che ci sia UN SOLO dev server: `netstat -ano | findstr ":3000 :3001"` → una sola riga LISTENING;
- non cancellare `.next` con il server vivo; se serve, spegnere prima il server.

### C. Rilievi minori del fix (opzionali, non bloccanti)
Dalla review avversariale, non corretti perché non bloccanti:
1. **Debito sconosciuto in `sp16g`/`sp17g`.** Un debito senza tipo va nel bucket "altri", che il motore fa CRESCERE ma non ammortizza (il piano di rimborso tocca solo `sp16a`/`sp17a` banche). È il default prudente/onesto (non si può assumere un piano di rimborso che non si conosce). Se si vuole, documentare o instradare i finanziamenti tipizzabili verso `sp16a`.
2. **`sp02g`/`sp03g`/`sp01b` riempiti anche se non serve al gate.** Il gate non richiede `sp01/sp02/sp03/ce08`; riempirli è innocuo (piena coerenza gerarchica per il display) ma rietichetta massa in "altri". Volendo, restringere `_RESIDUAL_BUCKET` alle sole famiglie gated. Solo pulizia.

### D. WIP Codex ancora non committato (non mio)
Sul working tree restano ~37 file Codex (motore forecast/intra-year, schemi, frontend, importer) non committati. Decidere separatamente se/come committarli — fuori dallo scope di questa sessione.

---

## Come rieseguire la verifica
```powershell
cd C:\DEV\xbrlbudget-main\xbrlbudget
$env:PYTHONPATH=(Get-Location).Path
pytest -q tests
# atteso: 225 passed, 3 skipped (i 3 skip dipendono da corpus PDF locale opzionale)
```
