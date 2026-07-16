# Documentazione XBRL Budget

Documentazione di progetto **aggiornata**. Gli artefatti storici/superati (design pre-implementazione, snapshot di sessione, dump di test) stanno in [`../archive/`](../archive/README.md), non qui.

> Le istruzioni operative per l'AI assistant e le note granulari per-parser stanno in [`../CLAUDE.md`](../CLAUDE.md).

## Import bilanci (PDF / XBRL) — [`import/`](import/)

### Regole di importazione — serie di riferimento (2026-07-16)

Specifica tecnica completa, verificata riga per riga sul codice. **In caso di conflitto con gli
altri documenti di questa cartella o con `CLAUDE.md`, vale questa serie** (i disallineamenti noti
sono elencati nel §5 dell'indice).

| Doc | Cosa copre |
|-----|------------|
| [REGOLE-IMPORT-00-INDICE.md](import/REGOLE-IMPORT-00-INDICE.md) | Indice, principio "diagnosticare mai fabbricare", soglie chiave, **drift doc↔codice** |
| [REGOLE-IMPORT-01-ROUTING.md](import/REGOLE-IMPORT-01-ROUTING.md) | Riconoscimento route: segnali, albero decisionale, scansione vs testo corrotto, gestionali |
| [REGOLE-IMPORT-02-ESTRAZIONE.md](import/REGOLE-IMPORT-02-ESTRAZIONE.md) | Pipeline in fasi, deterministico vs LLM, scelta del candidato, XBRL, CSV, politica API |
| [REGOLE-IMPORT-03-SPACCHETTATURE-NETTING.md](import/REGOLE-IMPORT-03-SPACCHETTATURE-NETTING.md) | Ricostruzione righe, netting fondi, tipizzazione debiti, entro/oltre, i 15 divieti |
| [REGOLE-IMPORT-04-QUADRATURE.md](import/REGOLE-IMPORT-04-QUADRATURE.md) | I 5 controlli, tolleranze, ordine dei messaggi di rifiuto, stati, Rettifiche |
| [REGOLE-IMPORT-05-INFRANNUALE.md](import/REGOLE-IMPORT-05-INFRANNUALE.md) | Periodi parziali, annualizzazione, roll-forward SP, gate del previsionale |
| [REGOLE-IMPORT-06-PERSISTENZA.md](import/REGOLE-IMPORT-06-PERSISTENZA.md) | Round-trip lossless, campi DB, hash e versioni, atomicità |

### Documenti di contesto e di progetto

| Doc | Cosa copre |
|-----|------------|
| [IMPORT-OVERVIEW.md](import/IMPORT-OVERVIEW.md) | Panoramica architetturale: router, rotte, validatori, anti-masking, CLI ⚠️ ferma alle sessioni 2026-06-15/17 |
| [IMPORT-ROUTING-TAXONOMY.md](import/IMPORT-ROUTING-TAXONOMY.md) | Tassonomia delle 4 rotte (A sintetico / B dettagliato / C verifica / OTHER) + `bilancio_classifier` |
| [IMPORT-BALANCING-SCHEME.md](import/IMPORT-BALANCING-SCHEME.md) | Schema di quadratura L0→L5 + identità CE↔SP (`enforce_ce_sp_identity`) |
| [IMPORT-QUADRATURA-ENGINE.md](import/IMPORT-QUADRATURA-ENGINE.md) | Motore IV-CEE condiviso (`iv_cee_hierarchy`) + anti-masking |
| [TRIAL-BALANCE-IMPORT.md](import/TRIAL-BALANCE-IMPORT.md) | Parser universale situazioni contabili (rotta C) per sottototali |

## Tassonomia & mapping XBRL — [`taxonomy/`](taxonomy/)

| Doc | Cosa copre |
|-----|------------|
| [TASSONOMIA.md](taxonomy/TASSONOMIA.md) | Schema bilancio IV-CEE (art. 2424/2425): sp01–sp18, ce01–ce20, cross-check |
| [XBRL_PCI_IV_CEE_Mapping.md](taxonomy/XBRL_PCI_IV_CEE_Mapping.md) | Mapping tassonomia XBRL PCI ↔ struttura IV-CEE |
| [SCHEMA_ENHANCEMENTS.md](taxonomy/SCHEMA_ENHANCEMENTS.md) | Colonne di dettaglio del DB (sottovoci sp/ce) |
| [PRIORITY_MAPPING_GUIDE.md](taxonomy/PRIORITY_MAPPING_GUIDE.md) | Risoluzione dei tag XBRL per priorità (v1→v2→detail→reconciliation) |
| [VBA_AGGREGATE_APPROACH.md](taxonomy/VBA_AGGREGATE_APPROACH.md) | Approccio a totali aggregati per l'import XBRL robusto |
| [XBRL_AGGREGATE_FALLBACK_EXPLANATION.md](taxonomy/XBRL_AGGREGATE_FALLBACK_EXPLANATION.md) | Perché il fallback aggregato può mostrare "somma voci = €0" |

## Budget & forecasting — [`budget/`](budget/)

| Doc | Cosa copre |
|-----|------------|
| [FORECASTING_GUIDE.md](budget/FORECASTING_GUIDE.md) | Guida utente al modulo Budget & Forecasting (workflow UI) |
| [TEST_BUDGET_API.md](budget/TEST_BUDGET_API.md) | Riferimento/test degli endpoint REST degli scenari budget |
| [FINAL-REPORT-PDF.md](budget/FINAL-REPORT-PDF.md) | Specifica del report PDF (gap analysis vs report di riferimento) |

## Deployment — [`deployment/`](deployment/)

| Doc | Cosa copre |
|-----|------------|
| [DEPLOYMENT_SUMMARY.md](deployment/DEPLOYMENT_SUMMARY.md) | Checklist deploy backend + frontend |
| [README_DEPLOYMENT.md](deployment/README_DEPLOYMENT.md) | Procedura di deploy del frontend |
| [PRODUCTION_CONFIG.md](deployment/PRODUCTION_CONFIG.md) | Configurazione di produzione (env, URL, porte) |
| [NETLIFY_CHECKLIST.md](deployment/NETLIFY_CHECKLIST.md) | Checklist specifica Netlify |
| [IFRAME_INTEGRATION.md](deployment/IFRAME_INTEGRATION.md) | Embedding dell'app via iframe (Formula Finance) + JWT Supabase `postMessage`, CORS, env |
