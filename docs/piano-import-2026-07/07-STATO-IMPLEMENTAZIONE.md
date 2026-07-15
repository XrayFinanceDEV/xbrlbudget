# 07 — Stato implementazione (2026-07-15)

Esecuzione del piano su branch **`fix/import-netting-2026-07`**. Ogni fix è guidato dai test (rosso→verde) e verificato end-to-end con la replica del percorso di produzione (`tests/_prod_route_c_runner.py`) contro la ground truth (`tests/_ground_truth_sez_contrapposte.json`).

## Fatto e verificato

| PR | Cosa | Esito | Verifica |
|---|---|---|---|
| PR-1 | Commit dei fix netting non committati | ✅ | `tests/test_contra_netting.py` verde (baseline) |
| PR-2 | Replica percorso produzione route C + ground truth field-by-field | ✅ | rende visibile il bug silente di 395; 343/348 guardie verdi |
| **PR-3** | **budget_395 — bug SILENTE** split immat/mat | ✅ | sp02 151.380→**39.783,68**, sp03 1.750.893→**1.862.490,15**, plug 0 |
| **PR-4** | **budget_211 — segno del risultato** | ✅ | sp13 +20.581→**−90.819,92** (perdita reale) |
| **PR-5** | **budget_210 + 211 — plug anticipo** | ✅ | 210 plug 39.024→**0**; 211 residuo 39.000→**0**, ora quadra pieno |

Risultato sul corpus `Test/sez-contrapposte` (percorso produzione deterministico):

```
FILE                        quadra   sp02            sp03            sp13          plug
budget_210                  SI       169.996,00      100.363,91      28.985,08     0
budget_211                  SI       182.260,00      122.967,10     -90.819,92     0
budget_343                  SI        27.640,60      453.510,10     -41.892,29     0
budget_348                  SI        27.640,60      454.300,50     -69.804,55     0
budget_395                  SI        39.783,68    1.862.490,15     125.447,80     0
```

**Suite completa:** `50 passed, 2 skipped, 2 xfailed` (i 2 xfail sono 405/131, sotto). Corpus deterministico intero invariato a 19/27 quadrature (nessuna regressione). Backend da riavviare per testare in-app (uvicorn `--reload` non ricarica `importers/`).

### Dettaglio dei fix

- **PR-3** (`situazione_contabile_parser._contra_classify`): i fondi erano raccolti DOPO `_dedup_parent_child`, che elimina il mastro `04 F/AMM IMMOBILIZZAZIONI IMMAT.` (l'unica caption immat corretta) lasciando foglie troncate che ricadono su materiali. Ora i fondi si leggono dai RAW rows: `total` = aggregato generale se stampato altrimenti somma-foglie deduplicata; `immat` = sub-aggregato immateriali se stampato altrimenti somma-foglie immat; `mat = total − immat`. Regge il 3-livelli con grand-total (343: `41 > 4101 > foglie`).
- **PR-4** (`pdf_extractor_llm._reconcile_trial_to_declared`): `_declared_control_totals` legge il conto PN "RISULTATO D'ESERCIZIO" (anno precedente) come `utile`; ora si arbitrano i candidati utile/perdita per vicinanza al **gap contabile** (`attivo − passivo`) con il risultato del CE come arbitro di riserva. Nessun anchor → ordine legacy (utile prima). `ce_result` propagato da `pdf_importer` route C.
- **PR-5** (`situazione_contabile_parser._SP_ATTIVO_RULES`): `ANTICIP` / `ACCONT+FORNITOR` → sp06 (crediti), prima delle regole di categoria (`MACCHINAR`…) e dopo le regole immobilizzazioni-in-corso/acconti. "ANTICIPO X CANONI MACCHINARI" non finisce più in sp03 (poi scartato dall'overlay → plug).

## Rimandato (con motivazione e diagnosi)

Entrambi **importano già** con flag onesto (`BILANCIO NON QUADRATO`/`MASK` → correzione in Rettifiche): NON sono bug silenti né errori bloccanti. Sono i due item a priorità più bassa del piano (T7/T8) e richiedono modifiche più rischiose sul classificatore condiviso / un parser nuovo. Rimandati per non mettere a rischio le 19/27 quadrature del corpus a fronte di un beneficio marginale.

- **budget_405** (PR-6): in produzione **sp02/sp03/sp13 sono GIÀ corretti** (il netting funziona); resta un plug diffuso dell'11%. Causa: la colonna PASSIVO contiene ammortamenti nominati come asset ("IMMOBILIZZAZIONI MATERIALI" 8,14M, "ATTREZZATURE"…) che `_is_fondo_amm` non riconosce (nessun token AMM/FONDO) e il best-effort classifica come debiti → l'attivo resta corto. Serve estendere il rilevatore contra ai layout dotted-hierarchical con colonna di ammortamento nominata-asset — alto rischio sul classificatore condiviso.
- **budget_131** (PR-7): DEPI `XX/YYYY` con **3 colonne saldo** (30/04/26, 30/04/25, 30/04/24) + colonne %. Il sub-parser DEPI mono-colonna legge la colonna sbagliata → sotto-estrazione (~35%). Serve un lettore multi-colonna per coordinata (colonna scelta per `fiscal_year`/più recente), attivato SOLO su header multi-data così i DEPI mono-colonna non regrediscono. Nuova feature di parsing.

### Altri item del piano non ancora affrontati
`_plug_detail` (V1, composizione del plug esposta all'utente): il residuo del best-effort è un delta netto `iv_total − att_sum`, non una lista di conti; esporre la composizione richiede di instrumentare il loop di classificazione a monte in `extract_contrapposte_best_effort` — utile ma non necessario ai target raggiunti, rimandato con 405. Restano inoltre i batch di 02-PERDITA-VOCI / 03-QUADRATURA (T9-T15) e i task backend (04, T16-T20), indipendenti.

## Come riprendere

1. `git checkout fix/import-netting-2026-07`
2. `python -m pytest tests/test_contra_netting.py tests/test_prod_route_c.py -q` (deve dare i 2 xfail 405/131)
3. `python tests/_prod_route_c_runner.py Test/sez-contrapposte` per la tabella campo-per-campo
4. Per 405/131: implementare il fix, poi in `tests/_ground_truth_sez_contrapposte.json` portare lo `status` a `good` (lo strict-xfail diventa XPASS→fail se il fix funziona ma dimentichi di aggiornare lo status).
