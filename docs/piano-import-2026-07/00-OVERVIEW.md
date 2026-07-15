# Piano interventi pipeline import — 2026-07-14

Audit completo della pipeline di import bilanci (router macro-aree → estrattori → livellamento IV-CEE → quadratura), della cartella `Test/sez-contrapposte`, e del backend padre apiServerIt. Questo documento è l'indice; ogni file del piano contiene **cosa, dove (file:riga) e come** intervenire.

## Come è organizzato il piano

| File | Contenuto |
|---|---|
| [01-NETTING-FONDI-AMMORTAMENTO.md](01-NETTING-FONDI-AMMORTAMENTO.md) | Fix netting immobilizzazioni/fondi (sez-contrapposte): budget_395, 210, 211, 405, 131, 337, Bilancino |
| [02-PERDITA-VOCI.md](02-PERDITA-VOCI.md) | I 10 punti dove le voci vengono perse o fuse in aggregati generici, con rimedi |
| [03-QUADRATURA-E-HARNESS.md](03-QUADRATURA-E-HARNESS.md) | Motore quadratura: arbitraggio risultato dichiarato, ancore, allineamento harness↔produzione, bug scala G6 |
| [04-BACKEND-APISERVERIT.md](04-BACKEND-APISERVERIT.md) | Integrazione con la piattaforma padre: licenze, JWT, origin-check, flow 401, doc stale |
| [05-ROADMAP.md](05-ROADMAP.md) | Sequenza operativa con priorità, effort stimato e criterio di verifica per ogni intervento |
| [06-PIANO-IMPLEMENTAZIONE.md](06-PIANO-IMPLEMENTAZIONE.md) | Piano esecutivo: 8 PR sequenziali con branch, funzioni/righe da toccare, test da scrivere prima, gate di avanzamento |

## Architettura attuale (verificata sul codice)

```
PDF → import_pdf_balance_sheet (importers/pdf_importer.py:203)
        │
        ├─ classify_bilancio (importers/bilancio_classifier.py:163)   ← router
        │     A sintetico ──────────► ROUTE_IVCEE (LLM)
        │     B dettagliato ────────► ROUTE_IVCEE (LLM, ancorato ai totali di voce)
        │     C contrapposte/SC ────► ROUTE_TRIAL (CoGe-LLM primario + deterministico fallback,
        │     OTHER ► XBRL / UNSUPPORTED           vince il candidato più vicino al totale dichiarato)
        │
        ├─ Route C post-extraction: overlay_debt_typing → net_contra_accounts (:2882)
        │                            → _reconcile_trial_to_declared (pdf_extractor_llm.py:2235)
        ├─ Route A/B: reconcile_ivcee_balance (iv_cee_hierarchy.py:335)
        │
        ├─ enforce_ce_sp_identity (iv_cee_hierarchy.py:386)   ← tutte le rotte
        ├─ validate_balance / "Formato non supportato" (pdf_importer.py:592-601)
        └─ check_quadratura (iv_cee_hierarchy.py:270)          ← diagnostico + anti-masking
```

**Le regole di trasformazione → quarta CEE** sono in tre posti (il file che cercavi):
1. `data/iv_cee_tree.json` — tassonomia canonica art. 2424/2425 (path, level, side, db_field, aliases, netting)
2. Classificatori per descrizione in `importers/situazione_contabile_parser.py` (`_classify_sp_attivo/passivo`, `_debt_type`, `_FONDO_*_KW`, `_SP_PASSIVO_RULES`) e `iv_cee_hierarchy.resolve()`
3. Documentazione: `docs/import/IMPORT-ROUTING-TAXONOMY.md`, `IMPORT-BALANCING-SCHEME.md`, `IMPORT-QUADRATURA-ENGINE.md`, `TRIAL-BALANCE-IMPORT.md`

## Esito audit Test/sez-contrapposte (9 file, path produzione deterministico)

| File | Netting | Quadratura prod. | Problema |
|---|---|---|---|
| budget_343 / 348 | ✅ corretto | ✅ plug 0 | — |
| budget_395 AGRIMIX | ❌ **sbagliato ma silente** | ✅ (falso OK) | split immat/mat perso: sp02 lordo (+111.597), sp03 over-nettato (−111.597) |
| budget_210 | ✅ corretto | ⚠️ plug 39.024 (2,6%) | anticipo "MACCHINARI" misclassificato in sp03, poi scartato dall'overwrite |
| budget_211 | ✅ corretto | ⚠️ plug 111.401 (7%) | sp13 = **utile** 20.581 invece di **perdita** 90.820 (conto PN "RISULTATO D'ESERCIZIO" scambiato per il dichiarato) |
| budget_405 | ✅ corretto | ⚠️ plug 870.467 (11%) | residuo best-effort estraneo al netting (F.DO SVAL.CREDITI, RISCONTI PASSIVI PLURIENNALI non classificati) |
| budget_131 Oprandi | n/a (nessun fondo) | ❌ plug 54,6% | parser DEPI non legge il layout a 3 colonne saldo → sotto-estrazione 35% |
| budget_337 | n/a | ❌ (deterministico) | text layer corrotto (ToUnicode); fix vision tentato e revertato il 14/07 — serve approccio diverso (prompt CoGe-LLM) |
| Bilancino 31-5-26 | n/a | skip | scansione pura → via vision (ok se OCR pulito) |

**Il caso più grave è budget_395**: è l'unico in cui il bilancio quadra e NON emette alcun warning, ma i valori di immobilizzazioni immateriali e materiali sono entrambi sbagliati. Gli altri casi almeno si dichiarano (`BILANCIO NON QUADRATO`/`QUADRATURA MASCHERATA` → Rettifiche).

## Stato del working tree (da gestire PRIMA di ogni intervento)

Branch `fix/budget-forecast-tax-credits-and-report-detail` con modifiche **non committate**:
- `importers/pdf_importer.py`, `importers/situazione_contabile_parser.py`, `tests/test_contra_netting.py` (fix netting 13-14/07: split fondi prefix-agnostic, `_dedup_parent_child` figli diretti, fondi svalutazione immobilizzazioni, riduzione ancora dichiarata)
- Untracked: `docs/examples/budget_210_Bilancio_2025.pdf`, `docs/examples/budget_211_Gustopronto_2024.pdf`

→ Primo step della roadmap: regression run + commit di questi fix, altrimenti ogni nuovo intervento è indistinguibile dal lavoro precedente. **Caveat operativo**: uvicorn `--reload` NON ricarica `importers/` — riavviare il backend per testare.

## Nota sull'harness (vale per tutto il piano)

`Test/_quadratura_harness.py` fa solo `extract → check_quadratura`:
- per le route **A/B** è **pessimista** (manca `reconcile_ivcee_balance` + `enforce_ce_sp_identity` → un "NO" può importare comunque);
- per la route **C** è **ottimista** (manca `net_contra_accounts` + `_reconcile_trial_to_declared` → un "SI" può nascondere sotto-estrazione, es. budget_131).

Vedi 03-QUADRATURA-E-HARNESS.md §3 per l'allineamento proposto (flag `--production`).
