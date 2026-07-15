# 05 — Roadmap operativa

Sequenza consigliata. Ogni task ha: riferimento al dettaglio, effort indicativo (S < ½ giornata, M ~1 giornata, L > 1 giornata), e criterio di verifica. I task import (T1-T13) sono ordinati per rapporto gravità/effort; i task backend (T14-T18) sono indipendenti e parallelizzabili.

## Fase 0 — Igiene (subito)

| # | Task | Rif. | Effort | Verifica |
|---|---|---|---|---|
| T0 | Regression run (`tests/run_contra_regression.py` + `tests/test_contra_netting.py` + harness su corpus) e **commit dei fix non committati** (`pdf_importer.py`, `situazione_contabile_parser.py`, `test_contra_netting.py`) su un branch dedicato `fix/contra-netting` | 00 §Stato | S | Suite verde; diff pulito; i 2 PDF in docs/examples committati o spostati in Test/ |

## Fase 1 — Fondamenta di misura (prima dei fix, per vederli)

| # | Task | Rif. | Effort | Verifica |
|---|---|---|---|---|
| T1 | Harness `--production`: estrarre `run_route_c_pipeline()` da `pdf_importer` e riusarla in harness; output campi finali + composizione plug | 03-Q3 | M | Su sez-contrapposte l'harness riproduce gli esiti dell'audit (395 "SI" diventa visibile come campo errato) |
| T2 | Ground truth corpus: `Test/_ground_truth/*.json` per i 9 file sez-contrapposte + casi storici; confronto automatico nell'harness | 03-Q4 | S | Scostamenti campo-per-campo riportati |
| T3 | Report righe non classificate: `Test/_unclassified_report.py` sul corpus completo | 02-V2 | S | Lista (descrizione, freq., importo, file) generata |

## Fase 2 — Netting e quadratura (il cuore della richiesta)

| # | Task | Rif. | Effort | Verifica |
|---|---|---|---|---|
| T4 | **budget_395**: split immat/mat — aggregati pre-dedup + bucketizzazione per gerarchia codice + guardia anti-regressione sullo split | 01-N1 | M | sp02=39.783,68 / sp03=1.862.490,15; 343/348/405/210/211 invariati |
| T5 | **budget_211**: arbitraggio utile/perdita col gap contabile + CE | 01-N2, 03-Q1 | S/M | sp13=−90.819,92, plug→~0; nessuna regressione sui file col solo marker "risultato d'esercizio" |
| T6 | **budget_210**: precedenza ANTICIP/ACCONT nel classificatore + overwrite conservativo (massa extra → crediti, non scartata) | 01-N3 | S/M | plug ≤ 24 €; 39.000 in sp06g |
| T7 | **budget_405 + plug detail**: alias risconti pluriennali + netting f.do svalutazione crediti entro/oltre + `_plug_detail` esposto all'utente | 01-N4, 02-V1 | M | plug < 1%; il warning elenca le voci del residuo |
| T8 | **budget_131**: parser DEPI multi-colonna (selezione colonna per data, split per coordinate) | 01-N5 | M | attivo=355.878,76; regression su DEPI esistenti (281, XX/YYYY) |
| T9 | Ancora dichiarata validata (2-su-3 coerenti o no-anchor) | 03-Q2, 02-V8 | S | Nessun ancoraggio su totali incoerenti; corpus invariato |

## Fase 3 — Perdita voci strutturale

| # | Task | Rif. | Effort | Verifica |
|---|---|---|---|---|
| T10 | Batch alias `iv_cee_tree.json` + priorità funzione>categoria nei classificatori (dal report T3) | 02-V2 | M | Plug medio corpus in calo; nessuna regressione harness |
| T11 | Debiti: fallback typed `sp16g` + rimozione proporzionale in `_reduce_debts`; strip risultato: esclusi `PRECEDENT/PORTAT.A NUOVO` | 02-V3, V9, V10 | S/M | Test dedicati; split debiti rappresentativo su 343/348 |
| T12 | Route B cross-check sottoconti vs totale di voce (generalizzare il pattern `_validate_crediti`) | 02-V4 | M | Voci divergenti flaggate su corpus route B |
| T13 | budget_337: prompt CoGe-LLM (ammortamenti CE ≠ fondi) + cross-check deterministico; gate PN loggato; retry colonna LLM malformata | 01-N6, 02-V5, V6 | M | 337 → immateriali 3.239 via LLM; nessun cambio su text layer sani |

## Fase 4 — Quadratura avanzata e scala

| # | Task | Rif. | Effort | Verifica |
|---|---|---|---|---|
| T14 | G6 scala miliardi/milioni: suite su `parse_italian_number` → fix col vincolo zero-regressioni + guardia plausibilità 10 mld | 03-Q5 | M | Suite congelata verde; caso G6 riprodotto e corretto |
| T15 | Plug CE↔SP dichiarato nel messaggio di import | 03-Q6 | S | Warning visibile quando `_ce_sp_plug` |

## Fase 5 — Backend / integrazione padre (parallelizzabile, decisioni parzialmente di business)

| # | Task | Rif. | Effort | Verifica |
|---|---|---|---|---|
| T16 | Flow 401 con retry-queue + refresh proattivo | 04-B2 | M | Sessione > 1h senza errori visibili |
| T17 | Origin fail-safe + target postMessage esplicito; guard-rail `DEV_USER_ID` in prod | 04-B3, B6 | S | Build senza env var → solo origin note; startup log |
| T18 | JWT: supporto JWKS/ES256 con fallback HS256; `verify_aud` on | 04-B4 | M | Login ok con entrambe le chiavi (coordinare col padre) |
| T19 | Enforcement licenze (richiede decisione di business + coordinamento col padre) | 04-B1 | M/L | Utente senza modulo → 403 |
| T20 | Pulizia config/doc stale (w3pro/Netlify) | 04-B5 | S | Nessun riferimento al vecchio deploy |
| T21 | `"format": "micro"` hardcoded → rilevare da classifier | 02 nota | S | Campo corretto nel result |

## Regole trasversali (valgono per ogni task)

1. **Prima il test, poi il fix**: ogni task di Fase 2-4 parte aggiungendo il caso alla ground truth (T2) e/o a `tests/test_contra_netting.py`.
2. **Zero regressioni misurate**: harness `--production` sul corpus prima/dopo ogni merge; il numero di quadrature e gli scostamenti dalla ground truth non devono peggiorare.
3. **Riavviare il backend** dopo ogni modifica a `importers/` (uvicorn `--reload` non li ricarica).
4. **Mai mascherare**: in dubbio tra "plug silenzioso" e "fallimento onesto con warning", scegliere sempre il secondo (principio già in vigore: `_plug_residual`, `QUADRATURA MASCHERATA`, "Formato non supportato").
5. Un branch per fase (o per task per T4/T8 che sono i più invasivi), commit atomici con il numero del task nel messaggio.
